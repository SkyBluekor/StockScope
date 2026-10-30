"""P0-05/G1: local read-only preflight, distinct from an authorized Scanner run."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tools.data import prospective_daily as daily


WEDNESDAY = datetime(2026, 10, 28, 7, 0, tzinfo=daily.KST)


def _stores(tmp_path: Path, dates: dict[str, str] | None = None):
    sim = tmp_path / "PRIVATE_SIMULATION.db"
    market = tmp_path / "PRIVATE_MARKET.db"
    with sqlite3.connect(sim) as db:
        db.executescript("""
            CREATE TABLE prospective_capture_run(
                id TEXT,market_scope TEXT,requested_as_of TEXT,
                actual_data_date TEXT,status TEXT,created_at TEXT
            );
        """)
    with sqlite3.connect(market) as db:
        db.executescript("""
            CREATE TABLE day_status(
                market TEXT,bas_dd TEXT,kind TEXT,status TEXT
            );
            CREATE TABLE stock_daily(
                market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT
            );
            CREATE TABLE main_index_daily(
                market TEXT,bas_dd TEXT,row_json TEXT
            );
        """)
        for market_name, asof in (dates or {
            "KOSPI": "20261027", "KOSDAQ": "20261027"
        }).items():
            for kind in ("stock", "index"):
                db.execute("INSERT INTO day_status VALUES(?,?,?,?)",
                           (market_name, asof, kind, "data"))
            db.execute("INSERT INTO stock_daily VALUES(?,?,?,?)",
                       (market_name, asof, "PRIVATE_STOCK", "{}"))
            db.execute("INSERT INTO main_index_daily VALUES(?,?,?)",
                       (market_name, asof, "{}"))
    return sim, market


def _run(sim, market, tmp_path, **kwargs):
    return daily.preflight_local_g1(
        simulation_db=sim, market_db=market,
        log_root=tmp_path / "MUST_NOT_BE_CREATED",
        now=WEDNESDAY, scope="ALL", **kwargs,
    )


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_g1_stored_both_markets_ready_but_cannot_authorize_capture(tmp_path, monkeypatch):
    sim, market = _stores(tmp_path)
    before = (_digest(sim), _digest(market))
    monkeypatch.setattr(daily, "_http", lambda *a, **kw: pytest.fail("HTTP forbidden"))
    monkeypatch.setattr(daily, "_backend_session", lambda *a: pytest.fail("backend forbidden"))
    report = _run(sim, market, tmp_path)
    assert report["status"] == "LOCAL_STORED_EOD_READY_APPROVAL_REQUIRED"
    assert report["stored_common_data_date"] == "2026-10-27"
    assert report["stored_eod_calendar_lag"] == 1
    assert report["execution_window_open"] is True
    assert report["production_capture_approved"] is False
    assert report["official_latest_eod_verified"] is False
    assert report["external_source_rights_verified"] is False
    assert report["provider_budget_approved"] is False
    assert report["db_write_calls"] == report["external_requests"] == 0
    assert report["scanner_job_started"] is False
    assert not (tmp_path / "MUST_NOT_BE_CREATED").exists()
    assert (_digest(sim), _digest(market)) == before
    assert "PRIVATE_" not in json.dumps(report)


@pytest.mark.parametrize("dates,expected", [
    ({"KOSPI":"20261021","KOSDAQ":"20261021"}, "HOLD_STALE_LOCAL_EOD"),
    ({"KOSPI":"20261027","KOSDAQ":"20261021"}, "HOLD_MARKET_DATES_MISMATCH"),
    ({"KOSPI":"20261027"}, "HOLD_NO_COMMON_STORED_EOD"),
])
def test_g1_stale_or_cross_market_mismatch_never_claims_ready(
    tmp_path, dates, expected,
):
    sim, market = _stores(tmp_path, dates)
    report = _run(sim, market, tmp_path)
    assert report["status"] == expected
    assert report["official_latest_eod_verified"] is False
    assert report["new_capture_created"] is False


def test_g1_existing_complete_or_pending_blocks_duplicate_capture(tmp_path):
    sim, market = _stores(tmp_path)
    with sqlite3.connect(sim) as db:
        db.execute(
            "INSERT INTO prospective_capture_run VALUES(?,?,?,?,?,?)",
            ("PRIVATE_CAPTURE", "ALL", "2026-10-27",
             "2026-10-27", "PENDING", "2026-10-28T06:58:00+09:00"),
        )
    report = _run(sim, market, tmp_path)
    assert report["status"] == "HOLD_EXISTING_CAPTURE_OR_PENDING"
    assert report["existing_capture_status"] == "PENDING"
    assert "PRIVATE_CAPTURE" not in json.dumps(report)


def test_g1_outside_window_and_lock_are_blocked_without_creating_files(tmp_path):
    sim, market = _stores(tmp_path)
    outside = daily.preflight_local_g1(
        simulation_db=sim, market_db=market,
        log_root=tmp_path / "NEW_LOG_DIRECTORY",
        now=datetime(2026,10,28,13,0,tzinfo=daily.KST),
        scope="ALL",
    )
    assert outside["status"] == "HOLD_EXECUTION_WINDOW_CLOSED"
    assert not (tmp_path / "NEW_LOG_DIRECTORY").exists()
    log_root = tmp_path / "EXISTING_DIRECTORY"
    log_root.mkdir()
    lock = log_root / "2026-10-28_all.lock"
    lock.write_text("PRIVATE_RUN_LOCK")
    report = daily.preflight_local_g1(
        simulation_db=sim, market_db=market,
        log_root=log_root, now=WEDNESDAY, scope="ALL",
    )
    assert report["status"] == "HOLD_EXISTING_RUN_LOCK"
    assert lock.read_text() == "PRIVATE_RUN_LOCK"


def test_g1_missing_simulation_or_market_fails_closed_without_creating_db(tmp_path):
    sim, market = _stores(tmp_path)
    absent_sim = tmp_path / "MISSING_SIM.db"
    absent_market = tmp_path / "MISSING_MARKET.db"
    assert _run(absent_sim, market, tmp_path)["status"] == "HOLD_SIMULATION_STORE_UNAVAILABLE"
    assert _run(sim, absent_market, tmp_path)["status"] == "HOLD_MARKET_STORE_UNAVAILABLE"
    assert not absent_sim.exists()
    assert not absent_market.exists()


def test_g1_preflight_cli_does_not_echo_private_paths_or_create_log(tmp_path):
    sim, market = _stores(tmp_path)
    script = Path(daily.__file__)
    result = subprocess.run(
        [sys.executable, str(script), "--preflight", "--scope", "ALL",
         "--simulation-db", str(sim), "--market-db", str(market)],
        capture_output=True, text=True, check=False,
    )
    report = json.loads(result.stdout)
    assert report["version"] == daily.G1_PREFLIGHT_VERSION
    assert report["external_requests"] == report["db_write_calls"] == 0
    assert report["production_capture_approved"] is False
    for secret in ("PRIVATE_SIMULATION", "PRIVATE_MARKET", "PRIVATE_STOCK"):
        assert secret not in result.stdout
    assert "Traceback" not in result.stderr
