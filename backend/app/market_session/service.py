from __future__ import annotations

from datetime import date, datetime, time
from threading import Lock
from typing import Callable
from zoneinfo import ZoneInfo

from app.integrations.kis.holiday import KisHolidayProvider, kis_holiday_provider

from .models import DomesticMarketSession, MarketSessionPhase
from .store import MarketSessionStore, market_session_store


SEOUL = ZoneInfo("Asia/Seoul")
_ACTIVE_PHASES = {"PRE_MARKET", "REGULAR", "AFTER_MARKET"}


class DomesticMarketSessionService:
    """Resolve the integrated domestic-equity trading session in Asia/Seoul."""

    def __init__(
        self,
        *,
        holiday_provider: KisHolidayProvider | None = None,
        store: MarketSessionStore | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.holiday_provider = holiday_provider or kis_holiday_provider
        self.store = store or market_session_store
        self.now_provider = now_provider or (lambda: datetime.now(SEOUL))
        self._holiday_cache: dict[date, bool] = {}
        self._holiday_lock = Lock()

    def clear_cache(self) -> None:
        with self._holiday_lock:
            self._holiday_cache.clear()

    def _is_open_day(self, local_date: date) -> bool:
        cached = self._holiday_cache.get(local_date)
        if cached is not None:
            return cached
        with self._holiday_lock:
            cached = self._holiday_cache.get(local_date)
            if cached is not None:
                return cached
            resolved = self.holiday_provider.is_open_day(local_date)
            self._holiday_cache[local_date] = resolved
            return resolved

    @staticmethod
    def _at(local_date: date, value: time) -> datetime:
        return datetime.combine(local_date, value, tzinfo=SEOUL)

    @classmethod
    def _clock_phase(
        cls,
        now: datetime,
    ) -> tuple[MarketSessionPhase, datetime | None]:
        local_date = now.date()
        pre_open = cls._at(local_date, time(8, 0))
        pre_close = cls._at(local_date, time(8, 50))
        regular_open = cls._at(local_date, time(9, 0))
        regular_close = cls._at(local_date, time(15, 30))
        after_open = cls._at(local_date, time(15, 40))
        after_close = cls._at(local_date, time(20, 0))

        if now < pre_open:
            return "CLOSED", pre_open
        if now < pre_close:
            return "PRE_MARKET", pre_close
        if now < regular_open:
            return "INTERMISSION", regular_open
        if now < regular_close:
            return "REGULAR", regular_close
        if now < after_open:
            return "INTERMISSION", after_open
        if now < after_close:
            return "AFTER_MARKET", after_close
        return "CLOSED", None

    def get_session(self, venue: str = "INTEGRATED") -> DomesticMarketSession:
        normalized_venue = (venue or "INTEGRATED").strip().upper()
        if normalized_venue != "INTEGRATED":
            raise ValueError("market session currently supports INTEGRATED venue only")

        now = self.now_provider()
        if now.tzinfo is None:
            now = now.replace(tzinfo=SEOUL)
        else:
            now = now.astimezone(SEOUL)
        local_date = now.date()

        if local_date.weekday() >= 5:
            session = DomesticMarketSession(
                market="DOMESTIC_EQUITY",
                venue="INTEGRATED",
                timezone="Asia/Seoul",
                checked_at=now.isoformat(),
                local_date=local_date.isoformat(),
                trading_day=False,
                phase="CLOSED",
                quote_polling_allowed=False,
                market_active=False,
                next_transition_at=None,
                source="WEEKEND_RULE",
                reason_code="WEEKEND",
            )
            self.store.put(session)
            return session

        try:
            open_day = self._is_open_day(local_date)
        except Exception:
            session = DomesticMarketSession(
                market="DOMESTIC_EQUITY",
                venue="INTEGRATED",
                timezone="Asia/Seoul",
                checked_at=now.isoformat(),
                local_date=local_date.isoformat(),
                trading_day=None,
                phase="UNKNOWN",
                quote_polling_allowed=True,
                market_active=None,
                next_transition_at=None,
                source="UNKNOWN",
                reason_code="HOLIDAY_STATUS_UNAVAILABLE",
            )
            self.store.put(session)
            return session

        if not open_day:
            session = DomesticMarketSession(
                market="DOMESTIC_EQUITY",
                venue="INTEGRATED",
                timezone="Asia/Seoul",
                checked_at=now.isoformat(),
                local_date=local_date.isoformat(),
                trading_day=False,
                phase="CLOSED",
                quote_polling_allowed=False,
                market_active=False,
                next_transition_at=None,
                source="KIS_HOLIDAY",
                reason_code="MARKET_HOLIDAY",
            )
            self.store.put(session)
            return session

        phase, next_transition = self._clock_phase(now)
        active = phase in _ACTIVE_PHASES
        session = DomesticMarketSession(
            market="DOMESTIC_EQUITY",
            venue="INTEGRATED",
            timezone="Asia/Seoul",
            checked_at=now.isoformat(),
            local_date=local_date.isoformat(),
            trading_day=True,
            phase=phase,
            quote_polling_allowed=active,
            market_active=active,
            next_transition_at=next_transition.isoformat() if next_transition else None,
            source="SESSION_CLOCK",
            reason_code=(
                "MARKET_INTERMISSION"
                if phase == "INTERMISSION"
                else "MARKET_CLOSED"
                if phase == "CLOSED"
                else None
            ),
        )
        self.store.put(session)
        return session


market_session_service = DomesticMarketSessionService()


def peek_market_session(venue: str = "INTEGRATED") -> DomesticMarketSession | None:
    """Read the last resolved session only; never calls KIS."""
    return market_session_store.peek(venue)
