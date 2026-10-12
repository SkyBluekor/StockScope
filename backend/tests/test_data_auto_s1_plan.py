"""DATA-AUTO-S1: no-network local planning and first-device consent decisions."""
from __future__ import annotations

from datetime import date, timedelta
import gzip
import json
from pathlib import Path
import sqlite3

import pytest

from app.backtest.data_preparation_plan import plan_scanner_data
from app.backtest.scanner import StockScannerService
from app.market.providers.krx import KrxProvider


END = date(2026, 10, 9)
TODAY = date(2026, 10, 12)


def _db(tmp_path: Path, *, complete: bool):
    db = tmp_path / "market.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE day_status(market TEXT, bas_dd TEXT, kind TEXT, status TEXT)"
        )
        if complete:
            start = END - timedelta(days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS)
            for i in range((END - start).days + 1):
                day = start + timedelta(days=i)
                if day.weekday() >= 5 or day == END:
                    continue
                for market in ("KOSPI", "KOSDAQ"):
                    for kind in ("stock", "index"):
                        conn.execute(
                            "INSERT INTO day_status VALUES (?,?,?,?)",
                            (market, day.strftime("%Y%m%d"), kind, "data"),
                        )
    return db


def _cache(root: Path, market: str, kind: str, *, corrupt=False, bad_date=False):
    root.mkdir(parents=True, exist_ok=True)
    endpoint = KrxProvider._endpoint_for_kind(market, kind)
    name = endpoint.path.replace("/", "__") + "__20261009.json.gz"
    p = root / name
    if corrupt:
        p.write_bytes(b"not a gzip file")
    else:
        with gzip.open(p, "wt", encoding="utf-8") as file:
            json.dump([{"BAS_DD": "20261008" if bad_date else "20261009",
                        "ISU_CD": "000001"}], file)
    return p


def _plan(tmp_path: Path, market_db: Path, **kwargs):
    return plan_scanner_data(
        market_scope="ALL", as_of_date="2026-10-09", candidate_limit=5,
        market_db=market_db, raw_cache_root=tmp_path / "cache",
        budget_db=tmp_path / "no-budget.sqlite3", today=TODAY, **kwargs,
    )


def test_fresh_device_asof_scoped_and_requires_one_time_consent(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Provider constructor must not be called by planning")

    monkeypatch.setattr(KrxProvider, "__init__", forbidden)
    result = _plan(tmp_path, tmp_path / "missing.db")
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["estimated_missing_krx_slots"] > result["fast_request_limit"]
    assert result["date_is_confirmed"] is False
    assert result["provider_calls"] == result["db_writes"] == 0
    assert not (tmp_path / "missing.db").exists()
    assert not (tmp_path / "cache").exists()


def test_only_missing_local_days_and_valid_raw_cache_are_counted(tmp_path):
    db = _db(tmp_path, complete=True)
    cache = tmp_path / "cache"
    good = _cache(cache, "KOSPI", "stock")
    corrupt = _cache(cache, "KOSPI", "index", corrupt=True)
    incorrect = _cache(cache, "KOSDAQ", "stock", bad_date=True)
    before = {p: p.read_bytes() for p in (good, corrupt, incorrect)}
    mtime = db.stat().st_mtime_ns

    result = _plan(tmp_path, db)
    assert result["status"] == "AUTO_ALLOWED"
    assert result["store_slots_missing"] == {"KOSPI": 2, "KOSDAQ": 2}
    assert result["raw_cache_slots_reusable"] == 1
    assert result["estimated_missing_krx_slots"] == 3
    assert db.stat().st_mtime_ns == mtime
    assert all(p.read_bytes() == contents for p, contents in before.items())


def test_budget_gate_takes_priority_over_bulk_approval(tmp_path):
    db = _db(tmp_path, complete=False)
    budget = tmp_path / "krx_budget.sqlite3"
    with sqlite3.connect(budget) as conn:
        conn.execute("CREATE TABLE krx_daily_usage(day TEXT, requests INTEGER)")
        conn.execute("INSERT INTO krx_daily_usage VALUES('2026-10-12', 7999)")
    result = plan_scanner_data(
        market_scope="ALL", as_of_date="2026-10-09", candidate_limit=5,
        market_db=db, raw_cache_root=tmp_path / "cache", budget_db=budget,
        today=TODAY,
    )
    assert result["status"] == "REVIEW_BUDGET"
    assert result["daily_budget_remaining"] == 1
    assert result["provider_calls"] == 0


def test_invalid_date_and_malformed_existing_database_are_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        plan_scanner_data(
            market_scope="ILLEGAL",
            as_of_date="2026-10-09",
            market_db=tmp_path / "missing.db",
            today=TODAY,
        )
    fresh = tmp_path / "empty.db"
    sqlite3.connect(fresh).close()
    first_install = _plan(tmp_path, fresh)
    assert first_install["status"] == "APPROVAL_REQUIRED"
    assert "NEW_DEVICE_MARKET_SCHEMA_NOT_INITIALIZED" in first_install["warnings"]
    assert fresh.stat().st_size == 0
    malformed = tmp_path / "malformed.db"
    with sqlite3.connect(malformed) as conn:
        conn.execute("CREATE TABLE unrelated(id INT)")
    assert _plan(tmp_path, malformed)["status"] == "BLOCKED_SCHEMA"
