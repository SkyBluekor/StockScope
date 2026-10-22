"""P0-02: real frozen Scanner, isolated snapshot, offline provider boundary."""
from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import runpy
import socket
import sqlite3

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "data" / "p0_02_offline_scanner_replay.py"
mod = runpy.run_path(str(SCRIPT), run_name="p0_02_offline_import")
snapshot = mod["snapshot_sqlite_readonly"]
offline_replay = mod["offline_replay"]
network_guard = mod["prohibit_external_connections"]
OfflineKrx = mod["OfflineKrx"]


def _db(path: Path, *, complete: bool = False, as_of: date = date(2026, 10, 21)) -> Path:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT);
        CREATE TABLE stock_daily(market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT);
        CREATE TABLE main_index_daily(market TEXT,bas_dd TEXT,row_json TEXT);
        """)
        if complete:
            start = as_of - timedelta(days=220)
            day = start
            while day <= as_of:
                if day.weekday() < 5:
                    dd = day.strftime("%Y%m%d")
                    for market in ("KOSPI", "KOSDAQ"):
                        conn.execute("INSERT INTO day_status VALUES (?,?,?,?)", (market, dd, "stock", "data"))
                        conn.execute("INSERT INTO day_status VALUES (?,?,?,?)", (market, dd, "index", "data"))
                        row = {"date": dd, "code": "005930", "name": "Synthetic", "open": 10000,
                               "high": 10010, "low": 9990, "close": 10000, "volume": 100000,
                               "trade_value": 2000000000, "market_cap": 1000000000000}
                        conn.execute("INSERT INTO stock_daily VALUES (?,?,?,?)", (market, dd, "005930", json.dumps(row)))
                        index = {"date": dd, "name": market, "close": 3000, "change_rate": 0.01}
                        conn.execute("INSERT INTO main_index_daily VALUES (?,?,?)", (market, dd, json.dumps(index)))
                day += timedelta(days=1)
    return path


def test_snapshot_includes_committed_wal_and_preserves_original(tmp_path: Path) -> None:
    src = _db(tmp_path / "original.db")
    with sqlite3.connect(src) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO day_status VALUES ('KOSPI','20261021','stock','data')")
    before = src.stat().st_size
    dst = tmp_path / "scratch.db"
    snapshot(src, dst)
    with sqlite3.connect(dst) as conn:
        assert conn.execute("SELECT COUNT(*) FROM day_status").fetchone()[0] == 1
    assert src.stat().st_size == before


def test_snapshot_refuses_missing_database(tmp_path: Path) -> None:
    target = tmp_path / "no.db"
    with pytest.raises(FileNotFoundError):
        snapshot(target, tmp_path / "scratch.db")
    assert not target.exists()


def test_offline_krx_refuses_all_real_market_requests() -> None:
    provider = OfflineKrx(date(2026, 10, 21))
    with pytest.raises(mod["NetworkAttemptBlocked"]):
        provider.assert_budget(1)
    assert provider.request_stats()["network_requests"] == 0


def test_socket_guard_denies_external_connections() -> None:
    with network_guard() as blocked:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            with pytest.raises(mod["NetworkAttemptBlocked"]):
                sock.connect(("192.0.2.10", 443))
    assert blocked == ["SOCKET_CONNECT_DENIED"]


def test_replay_holds_when_latest_market_date_missing(tmp_path: Path) -> None:
    db = _db(tmp_path / "original.db")
    original = db.read_bytes()
    result = offline_replay(db, as_of=date(2026, 10, 21), operational_repo=tmp_path)
    assert result["status"] == "HOLD_COMMON_AS_OF_MISMATCH"
    assert result["krx_calls"] == 0
    assert db.read_bytes() == original


def test_replay_holds_when_history_has_unmarked_slot(tmp_path: Path) -> None:
    db = _db(tmp_path / "original.db", complete=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "DELETE FROM day_status WHERE market='KOSDAQ' AND bas_dd='20261020' AND kind='stock'"
        )
    result = offline_replay(db, as_of=date(2026, 10, 21), operational_repo=tmp_path)
    assert result["status"] == "HOLD_OFFLINE_LOOKBACK_INCOMPLETE"
    assert result["missing_history_slots_by_market"]["KOSDAQ"] >= 1
    assert result["krx_calls"] == 0


def test_actual_scanner_runs_with_no_provider_network_on_snapshot(tmp_path: Path) -> None:
    db = _db(tmp_path / "original.db", complete=True)
    original = db.read_bytes()
    result = offline_replay(
        db, as_of=date(2026, 10, 21), market_scope="ALL",
        operational_repo=tmp_path,
    )
    assert result["status"] == "OFFLINE_SCANNER_COMPUTATION_VERIFIED", result
    assert result["real_scanner_service"] is True
    assert result["api_job_executed"] is False
    assert result["prospective_capture_persisted"] is False
    assert result["scanner_requested_as_of"] == "2026-10-21"
    assert result["scanner_data_dates"] == {"KOSPI":"2026-10-21","KOSDAQ":"2026-10-21"}
    assert result["scanner_input_fingerprint"]["id"]
    assert result["partial_data"] is False
    assert result["scanner_cache_hit"] is False
    assert result["network_attempts"] == 0
    assert result["krx_calls"] == 0
    assert db.read_bytes() == original


def test_windows_worker_can_exit_before_snapshot_cleanup(tmp_path: Path) -> None:
    """The isolated worker must never own the original DB or a parent cleanup handle."""
    import subprocess
    import sys

    db = _db(tmp_path / "original.db", complete=True)
    original = db.read_bytes()
    # Mimics the parent: make a consistent copy, invoke the worker, then
    # remove the parent scratch directory only *after* child process exit.
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix="StockScope_P0_02_OfflineScanner_") as root:
        snap = Path(root) / "market_snapshot.sqlite3"
        snapshot(db, snap)
        run = subprocess.run(
            [
                sys.executable, str(SCRIPT), "--_snapshot-worker",
                "--market-db", str(snap), "--operational-repo", str(tmp_path),
                "--as-of", "2026-10-21", "--market-scope", "ALL",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert run.returncode == 0, run.stderr + "\n" + run.stdout
        result = json.loads(run.stdout)
        assert result["status"] == "OFFLINE_SCANNER_COMPUTATION_VERIFIED", result
        assert result["krx_calls"] == 0
        assert result["network_attempts"] == 0
    assert db.read_bytes() == original


def test_worker_rejects_non_snapshot_path_without_touching_operational_db(tmp_path: Path) -> None:
    db = _db(tmp_path / "original.db")
    original = db.read_bytes()
    outcome = offline_replay(
        db, as_of=date(2026, 10, 21),
        operational_repo=tmp_path, _snapshot_worker=True,
    )
    assert outcome["status"] == "HOLD_UNSAFE_WORKER_SNAPSHOT_PATH"
    assert db.read_bytes() == original
