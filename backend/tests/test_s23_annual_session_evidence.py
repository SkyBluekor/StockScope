"""S23 annual KRX evidence: synthetic manifests only; no provider or runtime writes."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.market.session_calendar_s21 import (
    AnnualSessionEvidence, CALENDAR_VERSION, ANNUAL_SCHEDULE_SOURCE,
    closure_evidence, market_day_evidence, session_evidence, unresolved_weekdays,
)


def _full_year(year: int, closed: set[date]) -> AnnualSessionEvidence:
    day = date(year, 1, 1)
    limit = date(year + 1, 1, 1)
    open_days = []
    while day < limit:
        if day.weekday() < 5 and day not in closed:
            open_days.append(day)
        day += timedelta(days=1)
    return AnnualSessionEvidence(
        year=year, version=f"SYNTHETIC_{year}_V1", coverage="FULL",
        source_url=ANNUAL_SCHEDULE_SOURCE, source_sha256="a" * 64,
        closed_days=tuple((d, "SYNTHETIC_SPECIAL_CLOSE", ANNUAL_SCHEDULE_SOURCE)
                          for d in sorted(closed)),
        open_days=tuple(open_days),
    )


def test_dated_existing_evidence_is_preserved_but_other_weekdays_are_unknown():
    assert closure_evidence(date(2026, 10, 5))["reason"] == "개천절 대체휴일"
    assert closure_evidence(date(2026, 10, 9))["reason"] == "한글날"
    assert closure_evidence(date(2026, 10, 10))["reason"] == "WEEKEND"
    assert session_evidence(date(2026, 10, 12))["calendar_state"] == "UNKNOWN"
    assert session_evidence(date(2025, 12, 31))["calendar_state"] == "UNKNOWN"
    assert session_evidence(date(2026, 10, 12))["source"] is None
    assert CALENDAR_VERSION.startswith("KRX_CASH_SESSION_EVIDENCE_S23")


def test_full_year_fixture_handles_special_holiday_and_year_end():
    last = date(2027, 12, 31)
    exceptional = date(2027, 6, 3)
    cal = _full_year(2027, {last, exceptional})
    assert session_evidence(last, calendar=cal)["calendar_state"] == "CLOSED_VERIFIED"
    assert session_evidence(exceptional, calendar=cal)["calendar_state"] == "CLOSED_VERIFIED"
    day = date(2027, 12, 30)
    assert session_evidence(day, calendar=cal)["calendar_state"] == "OPEN_VERIFIED"
    assert market_day_evidence(day, calendar=cal)["state"] == "OPEN_BUT_MISSING_EOD"
    assert market_day_evidence(day, calendar=cal, stock_status="data",
                               index_status="data", stock_rows=110,
                               index_rows=1)["state"] == "STORED_COMPLETE"


def test_partial_year_never_promotes_unsourced_weekdays():
    cal = AnnualSessionEvidence(
        year=2025, version="SYNTHETIC_PARTIAL", coverage="PARTIAL",
        source_url=ANNUAL_SCHEDULE_SOURCE, source_sha256=None,
        closed_days=((date(2025, 12, 31), "YEAR_END_FIXTURE",
                      ANNUAL_SCHEDULE_SOURCE),),
    )
    assert session_evidence(date(2025, 12, 31), calendar=cal)["calendar_state"] == "CLOSED_VERIFIED"
    assert market_day_evidence(date(2025, 12, 30), calendar=cal)["state"] == "UNKNOWN"
    assert market_day_evidence(date(2025, 12, 30), calendar=cal,
                               stock_status="data", index_status="data",
                               stock_rows=110, index_rows=1)["state"] == "STORED_COMPLETE"


def test_eod_on_a_sourced_closure_fails_closed():
    holiday = date(2026, 10, 9)
    assert market_day_evidence(holiday)["state"] == "CLOSED_VERIFIED"
    assert market_day_evidence(holiday, stock_status="data", index_status="data",
                               stock_rows=110, index_rows=1)["state"] == "CLOSURE_DATA_CONFLICT"
    assert unresolved_weekdays(date(2026, 10, 8), date(2026, 10, 9),
                               [holiday]) == ["2026-10-09"]


def test_missing_single_ticker_is_not_proof_market_closed():
    day = date(2026, 10, 12)
    assert market_day_evidence(day, stock_status="data", index_status="data",
                               stock_rows=110, index_rows=1)["state"] == "STORED_COMPLETE"
    assert market_day_evidence(day, stock_status="data", index_status="empty",
                               stock_rows=110, index_rows=0)["state"] == "PARTIAL_OR_UNVERIFIED_EXISTING"
    assert market_day_evidence(day)["state"] == "UNKNOWN"


def test_unverified_span_crosses_year_boundary_without_guessed_holiday():
    assert unresolved_weekdays(date(2025, 12, 30), date(2026, 1, 2), []) == [
        "2025-12-31", "2026-01-01", "2026-01-02",
    ]


def test_full_ledger_requires_every_weekday_and_a_source_digest():
    cal = _full_year(2027, {date(2027, 12, 31)})
    kwargs = dict(
        year=2027, version=cal.version, coverage="FULL",
        source_url=cal.source_url, source_sha256=cal.source_sha256,
        closed_days=cal.closed_days, open_days=cal.open_days,
    )
    with pytest.raises(ValueError, match="COVERAGE_INCOMPLETE"):
        AnnualSessionEvidence(**{**kwargs, "open_days":cal.open_days[:-1]})
    with pytest.raises(ValueError, match="OFFICIAL_SOURCE_REQUIRED"):
        AnnualSessionEvidence(**{**kwargs, "source_url":"https://example.com/holidays"})
    with pytest.raises(ValueError, match="OFFICIAL_SOURCE_REQUIRED"):
        AnnualSessionEvidence(**{**kwargs, "source_sha256":None})
    with pytest.raises(ValueError, match="DUPLICATE_OR_DAY_INVALID"):
        AnnualSessionEvidence(**{**kwargs, "open_days":cal.open_days + cal.open_days[:1]})
    with pytest.raises(ValueError, match="DUPLICATE_OR_DAY_INVALID"):
        AnnualSessionEvidence(**{**kwargs, "open_days":cal.open_days + (date(2027, 12, 31),)})
    with pytest.raises(ValueError, match="PARTIAL_CALENDAR_CANNOT_CERTIFY_OPEN_DAYS"):
        AnnualSessionEvidence(**{**kwargs, "coverage":"PARTIAL", "open_days":(date(2027, 12, 30),)})
    with pytest.raises(ValueError, match="YEAR_MISMATCH"):
        session_evidence(date(2026, 10, 10), calendar=cal)
