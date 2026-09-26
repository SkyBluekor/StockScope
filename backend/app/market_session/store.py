from __future__ import annotations

from threading import Lock

from .models import DomesticMarketSession


class MarketSessionStore:
    """Process-local latest market-session observation for read-only consumers."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[str, DomesticMarketSession] = {}

    def put(self, session: DomesticMarketSession) -> None:
        with self._lock:
            self._sessions[session.venue] = session

    def peek(self, venue: str = "INTEGRATED") -> DomesticMarketSession | None:
        with self._lock:
            return self._sessions.get((venue or "INTEGRATED").strip().upper())

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


market_session_store = MarketSessionStore()
