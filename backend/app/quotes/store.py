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

    @staticmethod
    def _provider_time(snapshot: QuoteSnapshot) -> datetime | None:
        raw = (snapshot.provider_timestamp or "").strip()
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _should_replace(cls, current: QuoteSnapshot, incoming: QuoteSnapshot) -> bool:
        current_time = cls._provider_time(current)
        incoming_time = cls._provider_time(incoming)

        if current_time is not None and incoming_time is not None:
            if incoming_time < current_time:
                return False
            if incoming_time == current_time:
                return not (
                    current.transport == "WEBSOCKET"
                    and incoming.transport == "REST"
                )

        if current.transport == "WEBSOCKET" and incoming.transport == "REST":
            # REALTIME.1 REST snapshots don't expose provider_timestamp.
            # Never let an unorderable REST response overwrite a WS observation.
            if incoming_time is None:
                return False

        if current.transport == "REST" and incoming.transport == "WEBSOCKET":
            return True

        return incoming.received_at >= current.received_at

    def put(self, key: QuoteCacheKey, snapshot: QuoteSnapshot) -> bool:
        with self._lock:
            current = self._entries.get(key)
            if current is not None and not self._should_replace(current, snapshot):
                return False
            self._entries[key] = snapshot
            if len(self._entries) > self._max_entries:
                oldest_key = min(
                    self._entries,
                    key=lambda candidate: self._entries[candidate].received_at,
                )
                self._entries.pop(oldest_key, None)
            return True

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
