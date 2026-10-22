"""P0-02 operational SQLite inspection: never touch a user's original database."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "data" / "p0_02_operational_store_audit.py"
audit = runpy.run_path(str(SCRIPT), run_name="p0_02_audit_import")["inspect_operational_store"]
AS_OF = date(2026, 10, 21)


def _db(path: Path) -> Path:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE day_status(
                market TEXT NOT NULL, bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL, status TEXT NOT NULL
            );
            CREATE TABLE stock_daily(
                market TEXT NOT NULL, bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL, row_json TEXT NOT NULL
            );
            CREATE TABLE main_index_daily(
                market TEXT NOT NULL, bas_dd TEXT NOT NULL, row_json TEXT NOT NULL
            );
        """)
    return path


def _insert(path: Path, market: str, dd: str, kind: str, *, marker: str = "data", rows: bool = True) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO day_status VALUES (?,?,?,?)", (market, dd, kind, marker))
        if rows and kind == "stock":
            conn.execute(
                "INSERT INTO stock_daily VALUES (?,?,?,?)",
                (market, dd, "000001", json.dumps({"date": dd, "code": "000001"})),
            )
        if rows and kind == "index":
            conn.execute(
                "INSERT INTO main_index_daily VALUES (?,?,?)",
                (market, dd, json.dumps({"date": dd, "name": market})),
            )


def test_missing_db_does_not_get_created(tmp_path: Path) -> None:
    target = tmp_path / "missing.db"
    result = audit(target, as_of=AS_OF)
    assert result["status"] == "BLOCKED_OPERATIONAL_DB_MISSING"
    assert not target.exists()
    assert result["provider_calls"] == result["db_writes"] == 0


def test_both_markets_are_required_at_the_same_date(tmp_path: Path) -> None:
    target = _db(tmp_path / "store.db")
    for market in ("KOSPI", "KOSDAQ"):
        for kind in ("stock", "index"):
            _insert(target, market, "20261019", kind)
    _insert(target, "KOSPI", "20261020", "stock")
    _insert(target, "KOSPI", "20261020", "index")
    _insert(target, "KOSDAQ", "20261021", "stock")
    _insert(target, "KOSDAQ", "20261021", "index")

    result = audit(target, as_of=AS_OF, lookback_calendar_days=7)
    assert result["last_common_marked_stock_index_date"] == "2026-10-19"
    assert result["calendar_days_behind_cutoff"] == 2
    assert result["markets"]["KOSPI"]["latest_same_day_stock_index_date"] == "2026-10-20"
    assert result["markets"]["KOSDAQ"]["latest_same_day_stock_index_date"] == "2026-10-21"
    assert result["provider_data_confirmed"] is False
    assert result["full_strategy_lookback_proven"] is False


def test_markers_without_rows_are_not_verified_data(tmp_path: Path) -> None:
    target = _db(tmp_path / "store.db")
    for kind in ("stock", "index"):
        _insert(target, "KOSPI", "20261020", kind, rows=False)
    result = audit(target, as_of=AS_OF, market_scope="KOSPI", lookback_calendar_days=7)
    m = result["markets"]["KOSPI"]
    assert result["last_common_marked_stock_index_date"] is None
    assert m["data_markers_without_rows"]["stock"] == 1
    assert m["data_markers_without_rows"]["index"] == 1
    assert result["status"] == "NO_COMMON_MARKED_EOD"


def test_empty_marker_is_not_proven_holiday(tmp_path: Path) -> None:
    target = _db(tmp_path / "store.db")
    _insert(target, "KOSPI", "20261020", "stock", marker="empty", rows=False)
    _insert(target, "KOSPI", "20261020", "index")
    result = audit(target, as_of=AS_OF, market_scope="KOSPI", lookback_calendar_days=7)
    assert result["markets"]["KOSPI"]["unverified_empty_markers"]["stock"] == 1
    assert result["official_holidays_checked"] is False


def test_unmarked_rows_are_not_an_analysis_ready_day(tmp_path: Path) -> None:
    target = _db(tmp_path / "store.db")
    with sqlite3.connect(target) as conn:
        conn.execute(
            "INSERT INTO stock_daily VALUES (?,?,?,?)",
            ("KOSPI", "20261020", "000001", "{}"),
        )
    _insert(target, "KOSPI", "20261020", "index")
    result = audit(target, as_of=AS_OF, market_scope="KOSPI", lookback_calendar_days=7)
    assert result["last_common_marked_stock_index_date"] is None
    assert result["markets"]["KOSPI"]["rows_without_data_markers"]["stock"] == 1


def test_report_reads_but_does_not_mutate_db_or_leak_prices(tmp_path: Path) -> None:
    target = _db(tmp_path / "store.db")
    for market in ("KOSPI", "KOSDAQ"):
        for kind in ("stock", "index"):
            _insert(target, market, "20261020", kind)
    original = target.read_bytes()
    result = audit(target, as_of=AS_OF, lookback_calendar_days=7)
    assert target.read_bytes() == original
    encoded = json.dumps(result, ensure_ascii=False)
    assert '"code"' not in encoded
    assert '"close"' not in encoded
    assert '"api_key"' not in encoded
    assert result["provider_calls"] == result["db_writes"] == 0


def test_schema_failure_closed_and_does_not_migrate(tmp_path: Path) -> None:
    target = tmp_path / "bad.db"
    with sqlite3.connect(target) as conn:
        conn.execute("CREATE TABLE only_this(x INTEGER)")
    original = target.read_bytes()
    result = audit(target, as_of=AS_OF)
    assert result["status"] == "BLOCKED_MARKET_SCHEMA_MISSING"
    assert target.read_bytes() == original


def test_cli_outputs_json_without_network_or_database_write(tmp_path: Path) -> None:
    target = _db(tmp_path / "store.db")
    original = target.read_bytes()
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--market-db", str(target),
         "--as-of", "2026-10-21", "--lookback-calendar-days", "7"],
        check=False, capture_output=True, text=True,
    )
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["version"] == "STOCKSCOPE_P0_02_OPERATIONAL_STORE_AUDIT_V1"
    assert result["last_common_marked_stock_index_date"] is None
    assert target.read_bytes() == original
