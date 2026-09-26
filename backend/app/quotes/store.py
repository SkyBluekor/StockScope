from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from .models import QuoteCacheKey, QuoteSnapshot


class QuoteStore:
    """Process-local last-observation store for KIS quote snapshots."""

    def __init__(self, *, max_entries: int = 512) -> None:
        self._max_entries = max(16, int(max_entries))
        self._entries: dict[QuoteCacheKey, QuoteSnapshot] = {}
        self._lock = Lock()

    def put(self, key: QuoteCacheKey, snapshot: QuoteSnapshot) -> None:
        with self._lock:
            self._entries[key] = snapshot
            if len(self._entries) <= self._max_entries:
                return
            oldest_key = min(
                self._entries,
                key=lambda candidate: self._entries[candidate].received_at,
            )
            self._entries.pop(oldest_key, None)

    def peek(self, key: QuoteCacheKey) -> QuoteSnapshot | None:
        with self._lock:
            return self._entries.get(key)

    def age_ms(self, snapshot: QuoteSnapshot) -> int:
        now = datetime.now(timezone.utc)
        return max(0, int((now - snapshot.received_at).total_seconds() * 1000))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


quote_store = QuoteStore()
