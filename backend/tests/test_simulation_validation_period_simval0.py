from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.simulation.validation_period import HistoricalValidationPeriodResolver, ValidationPeriodError


class FakeStore:
    def __init__(self, start: date, end: date):
        self.days = set()
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5:
                self.days.add(cursor.strftime("%Y%m%d"))
            cursor += timedelta(days=1)

    def latest_complete_date(self, market, instrument_type, as_of):
        eligible = [day for day in self.days if day <= as_of]
        return max(eligible) if eligible else None


def test_preset_uses_latest_market_store_month_not_system_month():
    resolver = HistoricalValidationPeriodResolver(FakeStore(date(2025, 1, 2), date(2026, 9, 18)))
    result = resolver.preview(preset="1y", market_scope="ALL")
    assert result["requested_end_month"] == "2026-09"
    assert result["requested_start_month"] == "2025-10"
    assert result["resolved_end_date"] == "2026-09-18"
    assert result["trading_days"] >= 60
    assert result["valid"] is True


def test_direct_month_range_resolves_to_first_and_last_actual_trading_day():
    resolver = HistoricalValidationPeriodResolver(FakeStore(date(2026, 1, 1), date(2026, 9, 18)))
    result = resolver.preview(start_month="2026-01", end_month="2026-03", market_scope="ALL")
    assert result["resolved_start_date"] == "2026-01-01"
    assert result["resolved_end_date"] == "2026-03-31"


def test_minimum_boundary_59_rejected_60_allowed():
    # Use custom minimum to test the exact contract without relying on holiday calendars.
    store = FakeStore(date(2026, 1, 1), date(2026, 4, 30))
    probe = HistoricalValidationPeriodResolver(store, minimum_trading_days=60)
    result = probe.preview(start_month="2026-01", end_month="2026-03", market_scope="ALL")
    assert result["trading_days"] >= 60
    assert probe.require_valid(start_month="2026-01", end_month="2026-03", market_scope="ALL")["valid"] is True

    strict = HistoricalValidationPeriodResolver(store, minimum_trading_days=result["trading_days"] + 1)
    short = strict.preview(start_month="2026-01", end_month="2026-03", market_scope="ALL")
    assert short["valid"] is False
    with pytest.raises(ValidationPeriodError) as caught:
        strict.require_valid(start_month="2026-01", end_month="2026-03", market_scope="ALL")
    assert caught.value.code == "SIM_VALIDATION_PERIOD_TOO_SHORT"


def test_future_month_is_rejected_instead_of_silent_clamp():
    resolver = HistoricalValidationPeriodResolver(FakeStore(date(2026, 1, 1), date(2026, 9, 18)))
    with pytest.raises(ValidationPeriodError) as caught:
        resolver.preview(start_month="2026-01", end_month="2026-12", market_scope="ALL")
    assert caught.value.code == "SIM_VALIDATION_FUTURE_MONTH"


def test_missing_boundary_month_is_explicit_error_not_silent_range_shift():
    resolver = HistoricalValidationPeriodResolver(FakeStore(date(2026, 2, 2), date(2026, 9, 18)))
    with pytest.raises(ValidationPeriodError) as caught:
        resolver.preview(start_month="2026-01", end_month="2026-03", market_scope="ALL")
    assert caught.value.code == "SIM_VALIDATION_START_MONTH_DATA_MISSING"
