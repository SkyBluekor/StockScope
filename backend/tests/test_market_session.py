from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.market_session.service import DomesticMarketSessionService
from app.market_session.store import MarketSessionStore


SEOUL = ZoneInfo("Asia/Seoul")


class FakeHolidayProvider:
    def __init__(self, result: bool = True, *, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def is_open_day(self, _target_date):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def _service_at(value: str, provider: FakeHolidayProvider | None = None):
    current = datetime.fromisoformat(value)
    return DomesticMarketSessionService(
        holiday_provider=provider or FakeHolidayProvider(True),  # type: ignore[arg-type]
        store=MarketSessionStore(),
        now_provider=lambda: current,
    )


@pytest.mark.parametrize(
    ("clock", "phase", "allowed", "transition_suffix"),
    [
        ("2026-09-25T07:59:00+09:00", "CLOSED", False, "08:00:00+09:00"),
        ("2026-09-25T08:00:00+09:00", "PRE_MARKET", True, "08:50:00+09:00"),
        ("2026-09-25T08:49:59+09:00", "PRE_MARKET", True, "08:50:00+09:00"),
        ("2026-09-25T08:50:00+09:00", "INTERMISSION", False, "09:00:00+09:00"),
        ("2026-09-25T08:59:59+09:00", "INTERMISSION", False, "09:00:00+09:00"),
        ("2026-09-25T09:00:00+09:00", "REGULAR", True, "15:30:00+09:00"),
        ("2026-09-25T15:29:59+09:00", "REGULAR", True, "15:30:00+09:00"),
        ("2026-09-25T15:30:00+09:00", "INTERMISSION", False, "15:40:00+09:00"),
        ("2026-09-25T15:39:59+09:00", "INTERMISSION", False, "15:40:00+09:00"),
        ("2026-09-25T15:40:00+09:00", "AFTER_MARKET", True, "20:00:00+09:00"),
        ("2026-09-25T19:59:59+09:00", "AFTER_MARKET", True, "20:00:00+09:00"),
        ("2026-09-25T20:00:00+09:00", "CLOSED", False, None),
    ],
)
def test_integrated_market_session_clock_boundaries(
    clock: str,
    phase: str,
    allowed: bool,
    transition_suffix: str | None,
) -> None:
    session = _service_at(clock).get_session()

    assert session.timezone == "Asia/Seoul"
    assert session.trading_day is True
    assert session.phase == phase
    assert session.quote_polling_allowed is allowed
    assert session.market_active is allowed
    if transition_suffix is None:
        assert session.next_transition_at is None
    else:
        assert session.next_transition_at is not None
        assert session.next_transition_at.endswith(transition_suffix)


def test_weekend_is_closed_without_kis_holiday_call() -> None:
    provider = FakeHolidayProvider(True)
    service = _service_at("2026-09-26T10:00:00+09:00", provider)

    session = service.get_session()

    assert session.phase == "CLOSED"
    assert session.trading_day is False
    assert session.source == "WEEKEND_RULE"
    assert session.reason_code == "WEEKEND"
    assert session.quote_polling_allowed is False
    assert provider.calls == 0


def test_weekday_holiday_is_closed() -> None:
    provider = FakeHolidayProvider(False)
    service = _service_at("2026-09-25T10:00:00+09:00", provider)

    session = service.get_session()

    assert session.phase == "CLOSED"
    assert session.trading_day is False
    assert session.source == "KIS_HOLIDAY"
    assert session.reason_code == "MARKET_HOLIDAY"
    assert provider.calls == 1


def test_holiday_lookup_failure_becomes_unknown_without_disabling_quotes() -> None:
    provider = FakeHolidayProvider(error=RuntimeError("provider unavailable"))
    service = _service_at("2026-09-25T10:00:00+09:00", provider)

    session = service.get_session()

    assert session.phase == "UNKNOWN"
    assert session.trading_day is None
    assert session.market_active is None
    assert session.quote_polling_allowed is True
    assert session.reason_code == "HOLIDAY_STATUS_UNAVAILABLE"


def test_open_day_status_is_cached_for_the_date() -> None:
    provider = FakeHolidayProvider(True)
    times = iter(
        [
            datetime.fromisoformat("2026-09-25T09:00:00+09:00"),
            datetime.fromisoformat("2026-09-25T15:40:00+09:00"),
        ]
    )
    service = DomesticMarketSessionService(
        holiday_provider=provider,  # type: ignore[arg-type]
        store=MarketSessionStore(),
        now_provider=lambda: next(times),
    )

    assert service.get_session().phase == "REGULAR"
    assert service.get_session().phase == "AFTER_MARKET"
    assert provider.calls == 1


def test_service_always_normalizes_naive_clock_to_seoul() -> None:
    provider = FakeHolidayProvider(True)
    service = DomesticMarketSessionService(
        holiday_provider=provider,  # type: ignore[arg-type]
        store=MarketSessionStore(),
        now_provider=lambda: datetime(2026, 9, 25, 9, 0, 0),
    )

    session = service.get_session()

    assert session.phase == "REGULAR"
    assert session.checked_at.endswith("+09:00")
