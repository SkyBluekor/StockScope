from __future__ import annotations

import asyncio
from collections import defaultdict

from .models import QuoteCacheKey, QuoteSnapshot


class QuoteEventHub:
    """Process-local latest-only fan-out for browser quote streams."""

    def __init__(self) -> None:
        self._subscribers: dict[
            QuoteCacheKey, set[asyncio.Queue[QuoteSnapshot]]
        ] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, key: QuoteCacheKey) -> asyncio.Queue[QuoteSnapshot]:
        queue: asyncio.Queue[QuoteSnapshot] = asyncio.Queue(maxsize=1)
        async with self._lock:
            self._subscribers[key].add(queue)
        return queue

    async def unsubscribe(
        self,
        key: QuoteCacheKey,
        queue: asyncio.Queue[QuoteSnapshot],
    ) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(key)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(key, None)

    async def publish(self, key: QuoteCacheKey, snapshot: QuoteSnapshot) -> None:
        async with self._lock:
            subscribers = tuple(self._subscribers.get(key, ()))

        for queue in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(snapshot)
            except asyncio.QueueFull:
                # Another publisher won the race; latest-only semantics allow drop.
                pass

    async def subscriber_count(self, key: QuoteCacheKey) -> int:
        async with self._lock:
            return len(self._subscribers.get(key, ()))


quote_event_hub = QuoteEventHub()
