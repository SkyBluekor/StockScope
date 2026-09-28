from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

import app.api.quotes as quotes_api
from app.quotes.event_hub import QuoteEventHub
from app.quotes.models import QuoteCacheKey, QuoteSnapshot
from app.quotes.store import QuoteStore


def _key(ticker: str = "005930") -> QuoteCacheKey:
    return QuoteCacheKey(
        environment="real",
        credential_fingerprint="fingerprint",
        market="KOSPI",
        ticker=ticker,
        venue="INTEGRATED",
    )


def _snapshot(
    *,
    ticker: str = "005930",
    price: str = "84200",
    provider_timestamp: str = "2026-09-28T09:30:12+09:00",
) -> QuoteSnapshot:
    return QuoteSnapshot(
        market="KOSPI",
        ticker=ticker,
        name="삼성전자" if ticker == "005930" else None,
        venue="INTEGRATED",
        provider_market_division="UN",
        environment="real",
        current_price=Decimal(price),
        change_amount=Decimal("1200"),
        change_rate=Decimal("1.45"),
        change_sign="2",
        open_price=Decimal("83300"),
        high_price=Decimal("85000"),
        low_price=Decimal("82900"),
        base_price=Decimal("83000"),
        accumulated_volume=Decimal("12345678"),
        provider_timestamp=provider_timestamp,
        received_at=datetime.now(timezone.utc),
        transport="WEBSOCKET",
    )


@pytest.mark.asyncio
async def test_event_hub_fans_out_same_key_and_isolates_other_keys() -> None:
    hub = QuoteEventHub()
    samsung = _key("005930")
    hynix = _key("000660")
    first = await hub.subscribe(samsung)
    second = await hub.subscribe(samsung)
    other = await hub.subscribe(hynix)

    snapshot = _snapshot()
    await hub.publish(samsung, snapshot)

    assert await first.get() is snapshot
    assert await second.get() is snapshot
    assert other.empty()
    assert await hub.subscriber_count(samsung) == 2
    assert await hub.subscriber_count(hynix) == 1

    await hub.unsubscribe(samsung, first)
    await hub.unsubscribe(samsung, second)
    await hub.unsubscribe(hynix, other)

    assert await hub.subscriber_count(samsung) == 0
    assert await hub.subscriber_count(hynix) == 0


@pytest.mark.asyncio
async def test_event_hub_slow_client_keeps_latest_only() -> None:
    hub = QuoteEventHub()
    key = _key()
    queue = await hub.subscribe(key)
    first = _snapshot(price="84100", provider_timestamp="2026-09-28T09:30:11+09:00")
    second = _snapshot(price="84200", provider_timestamp="2026-09-28T09:30:12+09:00")

    await hub.publish(key, first)
    await hub.publish(key, second)

    assert queue.qsize() == 1
    assert await queue.get() is second


class _Request:
    def __init__(self) -> None:
        self.checks = 0

    async def is_disconnected(self) -> bool:
        self.checks += 1
        return False


class _Service:
    def __init__(self, key: QuoteCacheKey) -> None:
        self.key = key

    def resolve_key(self, *, market, ticker, venue):
        assert (market, ticker, venue) == ("KOSPI", "005930", "INTEGRATED")
        return self.key


class _Manager:
    def __init__(
        self,
        *,
        transport: str = "CONNECTED",
        subscription: str | None = "SUBSCRIBED",
        error: str | None = None,
    ) -> None:
        self.transport_state = transport
        self.subscription = subscription
        self.error = error
        self.touched: list[QuoteCacheKey] = []

    def touch_demand(self, key: QuoteCacheKey) -> bool:
        self.touched.append(key)
        return True

    def subscription_state(self, key: QuoteCacheKey):
        return self.subscription

    def subscription_error(self, key: QuoteCacheKey):
        return self.error


@pytest.mark.asyncio
async def test_sse_live_status_catches_up_latest_websocket_quote_and_cleans_up(
    monkeypatch,
) -> None:
    key = _key()
    hub = QuoteEventHub()
    store = QuoteStore()
    store.put(key, _snapshot())
    manager = _Manager()

    monkeypatch.setattr(quotes_api, "quote_service", _Service(key))
    monkeypatch.setattr(quotes_api, "quote_event_hub", hub)
    monkeypatch.setattr(quotes_api, "quote_store", store)
    monkeypatch.setattr(quotes_api, "quote_websocket_manager", manager)

    response = await quotes_api.stock_quote_stream(
        _Request(),
        ticker="005930",
        market="KOSPI",
        venue="INTEGRATED",
    )

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert await hub.subscriber_count(key) == 1

    iterator = response.body_iterator
    first = await anext(iterator)
    second = await anext(iterator)

    assert isinstance(first, str)
    assert first.startswith("event: status\n")
    status_payload = json.loads(first.split("data: ", 1)[1])
    assert status_payload["state"] == "LIVE"
    assert status_payload["transport_state"] == "CONNECTED"
    assert status_payload["subscription_state"] == "SUBSCRIBED"

    assert isinstance(second, str)
    assert second.startswith("event: quote\n")
    quote_payload = json.loads(second.split("data: ", 1)[1])
    assert quote_payload["resource_key"] == "KOSPI:005930"
    assert quote_payload["current_price"] == "84200"
    assert quote_payload["delivery"]["source"] == "WEBSOCKET"

    serialized = first + second
    assert "app-secret" not in serialized
    assert "approval" not in serialized.lower()
    assert "access_token" not in serialized.lower()
    assert "fingerprint" not in serialized.lower()

    await iterator.aclose()
    assert await hub.subscriber_count(key) == 0
    assert manager.touched == [key]


@pytest.mark.asyncio
async def test_sse_emits_heartbeat_and_renews_demand(monkeypatch) -> None:
    key = _key()
    hub = QuoteEventHub()
    manager = _Manager(transport="CONNECTING", subscription="REQUESTED")

    monkeypatch.setattr(quotes_api, "quote_service", _Service(key))
    monkeypatch.setattr(quotes_api, "quote_event_hub", hub)
    monkeypatch.setattr(quotes_api, "quote_websocket_manager", manager)
    monkeypatch.setattr(quotes_api, "_HEARTBEAT_SECONDS", 0.001)
    monkeypatch.setattr(quotes_api, "_STATUS_CHECK_SECONDS", 0.001)

    response = await quotes_api.stock_quote_stream(
        _Request(),
        ticker="005930",
        market="KOSPI",
        venue="INTEGRATED",
    )
    iterator = response.body_iterator

    first = await anext(iterator)
    assert isinstance(first, str)
    assert first.startswith("event: status\n")
    assert json.loads(first.split("data: ", 1)[1])["state"] == "CONNECTING"

    heartbeat = await anext(iterator)
    while isinstance(heartbeat, str) and not heartbeat.startswith(": heartbeat"):
        heartbeat = await anext(iterator)

    assert heartbeat == ": heartbeat\n\n"
    assert len(manager.touched) >= 2

    await iterator.aclose()
    assert await hub.subscriber_count(key) == 0


def test_stream_status_degraded_and_unavailable(monkeypatch) -> None:
    key = _key()

    monkeypatch.setattr(
        quotes_api,
        "quote_websocket_manager",
        _Manager(transport="BACKOFF", subscription="SUBSCRIBED"),
    )
    degraded = quotes_api._stream_status(key)
    assert degraded["state"] == "DEGRADED"
    assert degraded["reason_code"] == "WEBSOCKET_BACKOFF"

    monkeypatch.setattr(
        quotes_api,
        "quote_websocket_manager",
        _Manager(transport="DISABLED", subscription=None),
    )
    unavailable = quotes_api._stream_status(key)
    assert unavailable["state"] == "UNAVAILABLE"
    assert unavailable["reason_code"] == "WEBSOCKET_DISABLED"
