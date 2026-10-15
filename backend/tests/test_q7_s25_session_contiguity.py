"""S25: sourced KRX closures, local session continuity, and fail-closed research-only capture."""
from __future__ import annotations

from datetime import datetime, date
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from app.jev.market_session_s25 import inspect_latest_session_readonly
from app.jev.research_scanner_s24 import ResearchCaptureError
from tools.data import q7_research_scanner as research

KST = ZoneInfo("Asia/Seoul")
FRIDAY = datetime(2026, 10, 16, 7, 0, tzinfo=KST)
THURSDAY = datetime(2026, 10, 15, 7, 0, tzinfo=KST)
MONDAY = datetime(2026, 10, 12, 7, 0, tzinfo=KST)


def _db(tmp_path, *, dates=("20261014",), market="KOSPI"):
    path = tmp_path / "market.db"
    with sqlite3.connect(path) as c:
        c.executescript("""
            CREATE TABLE day_status (
                market TEXT, bas_dd TEXT, kind TEXT, status TEXT
            );
            CREATE TABLE stock_daily (
                market TEXT, bas_dd TEXT, stock_code TEXT, row_json TEXT
            );
            CREATE TABLE main_index_daily (
                market TEXT, bas_dd TEXT, row_json TEXT
            );
        """)
        for stamp in dates:
            _complete(c, market, stamp)
    return path


def _complete(c, market, stamp):
    c.executemany("INSERT INTO day_status VALUES (?,?,?,'data')", [
        (market, stamp, "stock"), (market, stamp, "index"),
    ])
    c.execute(
        "INSERT INTO stock_daily VALUES (?,?,?,?)",
        (market, stamp, "005930", "{}"),
    )
    c.execute(
        "INSERT INTO main_index_daily VALUES (?,?,?)",
        (market, stamp, "{}"),
    )


def test_missing_yesterday_blocks_recent_but_stale_research_source(tmp_path):
    market = _db(tmp_path)
    original = market.read_bytes()
    r = research.plan(market="KOSPI", market_db=market, now=FRIDAY)
    assert r["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert r["source_date"] == "2026-10-14"
    assert r["local_market_date_age_days"] == 2  # old S24 age gate would PASS
    assert r["market_data_ready"] is False
    assert r["data_readiness_reason"] == "UNVERIFIED_PRIOR_WEEKDAY_GAP"
    assert r["reason_code"] == "RESEARCH_UNVERIFIED_PRIOR_WEEKDAY_GAP"
    assert r["unverified_prior_weekday_dates"] == ["2026-10-15"]
    assert r["unverified_prior_weekday_states"] == [{
        "date": "2026-10-15", "state": "MISSING",
    }]
    assert r["verified_latest_actual_session"] is False
    assert r["market_publication_time_proven"] is False
    assert r["capture_permitted_now"] is False
    assert r["production_market_db_writes"] == r["research_db_writes"] == 0
    assert r["network_requests"] == 0
    assert market.read_bytes() == original


@pytest.mark.asyncio
async def test_unverified_recent_weekday_stops_capture_before_network_or_file(tmp_path):
    market = _db(tmp_path)
    root = tmp_path / "research"
    before = market.read_bytes()
    calls = []

    async def never_run(**kw):
        calls.append(kw)
        raise AssertionError("would run Scanner")

    result = await research.capture(
        market="KOSPI", market_db=market, root=root,
        now=FRIDAY, acknowledge=True, execute_scan=never_run,
    )
    assert result["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert result["reason_code"] == "RESEARCH_UNVERIFIED_PRIOR_WEEKDAY_GAP"
    assert not root.exists()
    assert calls == []
    assert market.read_bytes() == before


def test_partial_market_session_still_blocks_and_is_labeled_partial(tmp_path):
    market = _db(tmp_path)
    with sqlite3.connect(market) as c:
        c.execute(
            "INSERT INTO day_status VALUES ('KOSPI','20261015','stock','data')"
        )
        c.execute(
            "INSERT INTO stock_daily VALUES ('KOSPI','20261015','005930','{}')"
        )
    r = research.plan(market="KOSPI", market_db=market, now=FRIDAY)
    assert r["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert r["source_date"] == "2026-10-14"
    assert r["unverified_prior_weekday_states"] == [
        {"date": "2026-10-15", "state": "PARTIAL_OR_UNVERIFIED_EXISTING"},
    ]


def test_latest_complete_prior_weekday_reopens_research_window(tmp_path):
    market = _db(tmp_path, dates=("20261014", "20261015"))
    r = research.plan(market="KOSPI", market_db=market, now=FRIDAY)
    assert r["status"] == "RESEARCH_WINDOW_READY_NOT_Q7_APPROVED"
    assert r["source_date"] == "2026-10-15"
    assert r["market_data_ready"] is True
    assert r["session_evidence_status"] == "LOCAL_SESSION_CONTIGUITY_CHECKED"
    assert r["unverified_prior_weekday_dates"] == []
    assert r["capture_permitted_now"] is True
    assert r["q7_approval_eligible"] is False
    assert r["verified_latest_actual_session"] is False


def test_verified_krx_holiday_and_weekend_allow_four_day_prior_eod(tmp_path):
    market = _db(tmp_path, dates=("20261008",))
    r = research.plan(market="KOSPI", market_db=market, now=MONDAY)
    assert r["status"] == "RESEARCH_WINDOW_READY_NOT_Q7_APPROVED"
    assert r["source_date"] == "2026-10-08"
    assert r["local_market_date_age_days"] == 4
    assert r["unverified_prior_weekday_dates"] == []
    assert [item["date"] for item in r["verified_closure_dates"]] == [
        "2026-10-09", "2026-10-10", "2026-10-11",
    ]
    assert r["exchange_calendar_complete"] is False
    assert r["market_publication_time_proven"] is False


@pytest.mark.asyncio
async def test_verified_holiday_with_stray_stock_row_fails_closed(tmp_path):
    market = _db(tmp_path, dates=("20261008",))
    with sqlite3.connect(market) as c:
        c.execute(
            "INSERT INTO stock_daily VALUES ('KOSPI','20261009','005930','{}')"
        )
    r = research.plan(market="KOSPI", market_db=market, now=MONDAY)
    assert r["reason_code"] == "RESEARCH_CLOSURE_MARKET_DATA_CONFLICT"
    assert r["closure_data_conflict_dates"] == ["2026-10-09"]
    assert r["capture_permitted_now"] is False
    calls = []

    async def never_run(**kw):
        calls.append(kw)
        raise AssertionError("would run Scanner")

    folder = tmp_path / "research"
    result = await research.capture(
        market="KOSPI", market_db=market, root=folder,
        now=MONDAY, acknowledge=True, execute_scan=never_run,
    )
    assert result["reason_code"] == "RESEARCH_CLOSURE_MARKET_DATA_CONFLICT"
    assert not folder.exists()
    assert calls == []


def test_no_assumption_about_other_markets_and_undocumented_holidays(tmp_path):
    market = _db(tmp_path, dates=("20261014", "20261015"), market="KOSPI")
    with sqlite3.connect(market) as c:
        _complete(c, "KOSDAQ", "20261014")
    r = research.plan(market="KOSDAQ", market_db=market, now=FRIDAY)
    assert r["source_date"] == "2026-10-14"
    assert r["unverified_prior_weekday_dates"] == ["2026-10-15"]
    assert r["capture_permitted_now"] is False
    assert r["calendar_evidence_version"].startswith("KRX_CASH_EOD_VERIFIED_CLOSURES_")


@pytest.mark.asyncio
async def test_copied_market_snapshot_is_rechecked_before_scanner(tmp_path, monkeypatch):
    market = _db(tmp_path, dates=("20261014", "20261015"))
    orig = market.read_bytes()
    root = tmp_path / "research"
    original_clone = research._clone_readonly_source
    calls = []

    def tamper_copy(src, dest):
        original_clone(src, dest)
        # A source disagreement after the initial plan must fail closed.
        # The source Market Store remains pristine; only research copy changes.
        with sqlite3.connect(dest) as c:
            c.execute(
                "DELETE FROM main_index_daily WHERE market='KOSPI' AND bas_dd='20261015'"
            )

    async def never_run(**kw):
        calls.append(kw)
        raise AssertionError("research scanner called despite changed snapshot")

    monkeypatch.setattr(research, "_clone_readonly_source", tamper_copy)
    with pytest.raises(ResearchCaptureError) as error:
        await research.capture(
            market="KOSPI", market_db=market, root=root,
            now=FRIDAY, acknowledge=True, execute_scan=never_run,
        )
    assert error.value.code == "RESEARCH_COPIED_MARKET_SNAPSHOT_NOT_CURRENT"
    assert calls == []
    assert market.read_bytes() == orig
    assert not (root / "2026-10-15_kospi" / "scanner_research_capture.json").exists()


def test_helper_no_local_complete_date_is_not_implicitly_weekday_open(tmp_path):
    market = _db(tmp_path, dates=())
    result = inspect_latest_session_readonly(
        market, market="KOSPI", latest_eod=None, today=date(2026, 10, 16),
    )
    assert result["session_evidence_status"] == "NO_COMPLETE_LOCAL_EOD"
    assert result["verified_latest_actual_session"] is False
    r = research.plan(market="KOSPI", market_db=market, now=FRIDAY)
    assert r["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert r["market_data_ready"] is False
    assert r["capture_permitted_now"] is False
