"""DATA-AUTO-S1: no-network local planning and first-device consent decisions."""
from __future__ import annotations

from datetime import date, timedelta
import gzip
import json
from pathlib import Path
import sqlite3

import pytest

from app.backtest.data_preparation_plan import plan_scanner_data, plan_scanner_evidence_data
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
        conn.execute(
            "CREATE TABLE stock_daily(market TEXT, bas_dd TEXT, stock_code TEXT, row_json TEXT)"
        )
        conn.execute(
            "CREATE TABLE main_index_daily(market TEXT, bas_dd TEXT, row_json TEXT)"
        )
        if complete:
            start = END - timedelta(days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS)
            for i in range((END - start).days + 1):
                day = start + timedelta(days=i)
                if day.weekday() >= 5 or day == END:
                    continue
                for market in ("KOSPI", "KOSDAQ"):
                    for kind in ("stock", "index"):
                        dd = day.strftime("%Y%m%d")
                        conn.execute(
                            "INSERT INTO day_status VALUES (?,?,?,?)",
                            (market, dd, kind, "data"),
                        )
                        if kind == "stock":
                            conn.execute(
                                "INSERT INTO stock_daily VALUES (?,?,?,?)",
                                (market, dd, "005930", json.dumps({"date": dd, "code": "005930"})),
                            )
                        else:
                            conn.execute(
                                "INSERT INTO main_index_daily VALUES (?,?,?)",
                                (market, dd, json.dumps({"date": dd, "name": market})),
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


def test_data_marker_without_stock_rows_is_not_reused(tmp_path):
    db = _db(tmp_path, complete=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "DELETE FROM stock_daily WHERE market='KOSPI' AND bas_dd='20261008'"
        )
    result = _plan(tmp_path, db)
    assert result["data_markers_missing_rows"]["KOSPI"] == 1
    assert result["store_slots_missing"]["KOSPI"] == 3
    assert "MARKET_DATA_MARKER_WITHOUT_PERSISTED_ROWS" in result["warnings"]
    assert {"market": "KOSPI", "date": "2026-10-08", "kind": "stock", "reason": "DATA_MARKER_WITHOUT_ROWS"} in result["unverified_status_samples"]
    assert result["estimated_missing_krx_slots"] == 5
    assert result["provider_calls"] == result["db_writes"] == 0


def test_empty_marker_never_proves_holiday_or_cached_market_rows(tmp_path):
    db = _db(tmp_path, complete=True)
    cache = tmp_path / "cache"
    cache.mkdir()
    endpoint = KrxProvider._endpoint_for_kind("KOSPI", "index")
    (cache / (endpoint.path.replace("/", "__") + "__20261009.empty")).write_text("")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE day_status SET status='empty' WHERE market='KOSPI' AND bas_dd='20261008' AND kind='index'"
        )
        conn.execute(
            "DELETE FROM main_index_daily WHERE market='KOSPI' AND bas_dd='20261008'"
        )
    result = _plan(tmp_path, db)
    assert result["unverified_empty_slots"]["KOSPI"] == 1
    assert "MARKET_EMPTY_RESPONSE_NOT_PROVEN_HOLIDAY" in result["warnings"]
    assert {"market": "KOSPI", "date": "2026-10-08", "kind": "index", "reason": "EMPTY_NOT_PROVEN_HOLIDAY"} in result["unverified_status_samples"]
    assert result["store_slots_missing"]["KOSPI"] == 3
    assert result["estimated_missing_krx_slots"] == 5
    assert result["raw_cache_slots_reusable"] == 0
    assert result["provider_calls"] == result["db_writes"] == 0


def test_operational_eod_reports_real_common_rows_not_latest_per_kind(tmp_path):
    db = _db(tmp_path, complete=True)
    with sqlite3.connect(db) as conn:
        # KOSPI 10/08 has stock but not index; KOSDAQ 10/08 has
        # index but not stock. Their latest independent dates cannot
        # be mistaken for a common all-market Scanner date.
        conn.execute("DELETE FROM main_index_daily WHERE market='KOSPI' AND bas_dd='20261008'")
        conn.execute("DELETE FROM stock_daily WHERE market='KOSDAQ' AND bas_dd='20261008'")
    result = _plan(tmp_path, db)
    observed = result["operational_eod"]
    assert observed["source"] == "OPERATIONAL_MARKET_STORE_READONLY"
    assert observed["stored_same_day_stock_index_date"] == "2026-10-07"
    assert observed["days_behind_inspection_end"] == 2
    assert observed["markets"]["KOSPI"]["last_stock_rows_date"] == "2026-10-08"
    assert observed["markets"]["KOSPI"]["last_index_row_date"] == "2026-10-07"
    assert observed["markets"]["KOSDAQ"]["last_stock_rows_date"] == "2026-10-07"
    assert observed["markets"]["KOSDAQ"]["last_index_row_date"] == "2026-10-08"
    assert observed["provider_publication_time_verified"] is False
    assert observed["official_holiday_calendar_verified"] is False
    assert observed["full_lookback_ready"] is False
    assert result["provider_calls"] == result["db_writes"] == 0


def test_operational_eod_is_unavailable_without_actual_persisted_rows(tmp_path):
    db = _db(tmp_path, complete=False)
    with sqlite3.connect(db) as conn:
        for market in ("KOSPI", "KOSDAQ"):
            for kind in ("stock", "index"):
                conn.execute(
                    "INSERT INTO day_status VALUES (?,?,?,?)",
                    (market, "20261008", kind, "data"),
                )
    result = _plan(tmp_path, db)
    observed = result["operational_eod"]
    assert observed["stored_same_day_stock_index_date"] is None
    assert observed["days_behind_inspection_end"] is None
    assert observed["markets"]["KOSPI"]["last_stock_rows_date"] is None
    assert result["estimated_missing_krx_slots"] > 0
    assert result["provider_calls"] == result["db_writes"] == 0


def test_operational_eod_preserves_market_file_bytes(tmp_path):
    db = _db(tmp_path, complete=True)
    before = db.read_bytes()
    observed = _plan(tmp_path, db)["operational_eod"]
    assert observed["stored_same_day_stock_index_date"] == "2026-10-08"
    assert db.read_bytes() == before



def test_three_year_evidence_plan_counts_full_warmup_and_requires_consent(tmp_path):
    db = _db(tmp_path, complete=True)  # only recent fast-history rows exist
    before = db.read_bytes()
    result = plan_scanner_evidence_data(
        market="KOSPI", data_end="2026-10-09", market_db=db,
        raw_cache_root=tmp_path / "cache", budget_db=tmp_path / "budget.db", today=TODAY,
    )
    assert result["version"] == "SCANNER_EVIDENCE_DATA_PREFLIGHT_V1"
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["requires_explicit_large_sync_approval"] is True
    assert result["estimated_missing_krx_slots"] > result["fast_request_limit"]
    assert result["validation_start"] == "2023-10-09"
    assert date.fromisoformat(result["warmup_start"]) < date(2023, 10, 9)
    assert result["provider_calls"] == result["db_writes"] == 0
    assert db.read_bytes() == before


def test_three_year_evidence_plan_rejects_future_or_bad_market_before_io(tmp_path):
    with pytest.raises(ValueError, match="EVIDENCE_DATE_NOT_CONFIRMED_EOD"):
        plan_scanner_evidence_data(
            market="KOSPI", data_end="2026-10-12", market_db=tmp_path / "missing.db",
            today=TODAY,
        )
    with pytest.raises(ValueError, match="INVALID_EVIDENCE_MARKET"):
        plan_scanner_evidence_data(
            market="ALL", data_end="2026-10-09", market_db=tmp_path / "missing.db",
            today=TODAY,
        )
    assert not (tmp_path / "missing.db").exists()



def test_evidence_api_refuses_bulk_without_consent_before_job_or_provider(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from app.api import backtest as api

    monkeypatch.setattr(api, "plan_scanner_evidence_data", lambda **_: {
        "status": "APPROVAL_REQUIRED",
        "estimated_missing_krx_slots": 1200,
    })

    def forbidden(*args, **kwargs):
        raise AssertionError("A blocked evidence request must never allocate a job or provider")

    monkeypatch.setattr(api.backtest_jobs, "create", forbidden)
    monkeypatch.setattr(api, "get_settings", forbidden)
    payload = api.ScannerEvidencePrepareRequest(
        market="KOSPI", code="005930", data_end="2026-10-09",
        market_scope="ALL",
    )
    with pytest.raises(HTTPException) as err:
        asyncio.run(api.create_scanner_evidence_job(payload))
    assert err.value.status_code == 409
    assert err.value.detail["code"] == "EVIDENCE_LARGE_SYNC_APPROVAL_REQUIRED"
    assert err.value.detail["estimated_missing_krx_slots"] == 1200


def test_evidence_api_blocks_insufficient_budget_even_with_consent(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from app.api import backtest as api

    monkeypatch.setattr(api, "plan_scanner_evidence_data", lambda **_: {
        "status": "REVIEW_BUDGET",
        "estimated_missing_krx_slots": 1200,
    })
    monkeypatch.setattr(api.backtest_jobs, "create", lambda: (_ for _ in ()).throw(
        AssertionError("Budget block must happen before job creation")
    ))
    payload = api.ScannerEvidencePrepareRequest(
        market="KOSDAQ", code="000001", data_end="2026-10-09",
        allow_large_sync=True,
    )
    with pytest.raises(HTTPException) as err:
        asyncio.run(api.create_scanner_evidence_job(payload))
    assert err.value.status_code == 409
    assert err.value.detail["code"] == "EVIDENCE_DATA_PREFLIGHT_BLOCKED"


def test_evidence_api_bad_date_is_rejected_before_job(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from app.api import backtest as api

    monkeypatch.setattr(api.backtest_jobs, "create", lambda: (_ for _ in ()).throw(
        AssertionError("Date validation must happen before job creation")
    ))
    payload = api.ScannerEvidencePrepareRequest(
        market="KOSPI", code="005930", data_end="not-a-date",
    )
    with pytest.raises(HTTPException) as err:
        asyncio.run(api.create_scanner_evidence_job(payload))
    assert err.value.status_code == 400
