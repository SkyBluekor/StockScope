from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.integrations.kis.quote import KisDomesticPrice
from app.integrations.kis.token_cache import credential_fingerprint
from app.integrations.kis.ws_approval import KisWebSocketApproval
from app.quotes.event_hub import QuoteEventHub
from app.quotes.models import QuoteCacheKey, QuoteSnapshot
from app.quotes.service import QuoteService
from app.quotes.store import QuoteStore
from app.quotes.websocket_manager import QuoteWebSocketManager
from app.quotes.websocket_parser import QUOTE_COLUMNS


def _settings(**overrides) -> Settings:
    values = {
        "kis_app_key": "app-key",
        "kis_app_secret": "app-secret",
        "kis_env": "real",
        "kis_quote_cache_ttl_seconds": 60.0,
        "kis_quote_min_upstream_interval_seconds": 0.0,
        "kis_ws_enabled": True,
        "kis_ws_max_subscriptions": 40,
        "kis_ws_demand_ttl_seconds": 45.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _key(settings: Settings, ticker: str = "005930") -> QuoteCacheKey:
    return QuoteCacheKey(
        environment="real",
        credential_fingerprint=credential_fingerprint(settings),
        market="KOSPI",
        ticker=ticker,
        venue="INTEGRATED",
    )


def _snapshot(
    *,
    price: str,
    transport: str,
    provider_timestamp: str | None,
    received_at: datetime | None = None,
) -> QuoteSnapshot:
    return QuoteSnapshot(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
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
        received_at=received_at or datetime.now(timezone.utc),
        transport=transport,
    )


class _ReadyManager:
    def __init__(self, ready: bool) -> None:
        self.ready = ready
        self.touched: list[QuoteCacheKey] = []

    def touch_demand(self, key: QuoteCacheKey) -> bool:
        self.touched.append(key)
        return True

    def is_subscription_ready(self, key: QuoteCacheKey) -> bool:
        return self.ready


def test_quote_service_prefers_ready_websocket_snapshot_without_rest_call() -> None:
    settings = _settings()
    store = QuoteStore()
    key = _key(settings)
    store.put(
        key,
        _snapshot(
            price="84200",
            transport="WEBSOCKET",
            provider_timestamp="2026-09-28T09:30:12+09:00",
        ),
    )
    manager = _ReadyManager(True)

    service = QuoteService(
        store=store,
        settings_getter=lambda: settings,
        token_getter=lambda _settings: (_ for _ in ()).throw(
            AssertionError("REST token must not be requested")
        ),
        quote_fetcher=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("REST quote must not be requested")
        ),
        websocket_manager=manager,
        min_upstream_interval_seconds=0,
    )

    result = service.get_quote(market="KOSPI", ticker="005930")

    assert result.delivery_source == "WEBSOCKET"
    assert result.snapshot.current_price == Decimal("84200")
    assert manager.touched == [key]


def test_unready_websocket_snapshot_falls_back_to_rest() -> None:
    settings = _settings()
    store = QuoteStore()
    key = _key(settings)
    store.put(
        key,
        _snapshot(
            price="84200",
            transport="WEBSOCKET",
            provider_timestamp="2026-09-28T09:30:12+09:00",
        ),
    )

    quote = KisDomesticPrice(
        ticker="005930",
        name="삼성전자",
        market_division="UN",
        current_price=Decimal("84100"),
        change_amount=Decimal("1100"),
        change_rate=Decimal("1.33"),
        change_sign="2",
        open_price=Decimal("83300"),
        high_price=Decimal("85000"),
        low_price=Decimal("82900"),
        base_price=Decimal("83000"),
        volume=Decimal("12345000"),
    )

    class Token:
        access_token = "rest-token"

    service = QuoteService(
        store=store,
        settings_getter=lambda: settings,
        token_getter=lambda _settings: Token(),
        quote_fetcher=lambda *_args, **_kwargs: quote,
        websocket_manager=_ReadyManager(False),
        min_upstream_interval_seconds=0,
    )

    result = service.get_quote(market="KOSPI", ticker="005930")

    assert result.delivery_source == "UPSTREAM"
    assert result.snapshot.transport == "REST"
    assert result.snapshot.current_price == Decimal("84100")
    assert store.peek(key).transport == "WEBSOCKET"


def test_store_does_not_let_unordered_rest_overwrite_websocket() -> None:
    store = QuoteStore()
    settings = _settings()
    key = _key(settings)
    ws = _snapshot(
        price="84200",
        transport="WEBSOCKET",
        provider_timestamp="2026-09-28T09:30:12+09:00",
    )
    rest = _snapshot(price="84100", transport="REST", provider_timestamp=None)

    assert store.put(key, ws) is True
    assert store.put(key, rest) is False
    assert store.peek(key) is ws


def test_store_prefers_websocket_for_equal_provider_timestamp() -> None:
    store = QuoteStore()
    settings = _settings()
    key = _key(settings)
    stamp = "2026-09-28T09:30:12+09:00"
    rest = _snapshot(price="84100", transport="REST", provider_timestamp=stamp)
    ws = _snapshot(price="84200", transport="WEBSOCKET", provider_timestamp=stamp)

    assert store.put(key, rest) is True
    assert store.put(key, ws) is True
    assert store.peek(key) is ws
    assert store.put(key, rest) is False


def _frame() -> str:
    row = {name: "0" for name in QUOTE_COLUMNS}
    row.update(
        {
            "MKSC_SHRN_ISCD": "005930",
            "STCK_CNTG_HOUR": "093012",
            "STCK_PRPR": "84200",
            "PRDY_VRSS_SIGN": "2",
            "PRDY_VRSS": "1200",
            "PRDY_CTRT": "1.45",
            "STCK_OPRC": "83300",
            "STCK_HGPR": "85000",
            "STCK_LWPR": "82900",
            "CNTG_VOL": "15",
            "ACML_VOL": "12345678",
            "BSOP_DATE": "20260928",
            "TRHT_YN": "N",
        }
    )
    return "0|H0UNCNT0|1|" + "^".join(row[name] for name in QUOTE_COLUMNS)


@pytest.mark.asyncio
async def test_manager_marks_ack_subscribed_then_publishes_tick() -> None:
    settings = _settings()
    store = QuoteStore()
    manager = QuoteWebSocketManager(
        store=store,
        settings_getter=lambda: settings,
        approval_getter=lambda _settings: KisWebSocketApproval(
            "approval", credential_fingerprint(settings)
        ),
    )
    key = _key(settings)
    assert manager.touch_demand(key) is True

    manager._set_state("CONNECTED")
    manager._leases[key].state = "SUBSCRIBING"

    ack = json.dumps(
        {
            "header": {"tr_id": "H0UNCNT0", "tr_key": "005930"},
            "body": {"rt_cd": "0", "msg_cd": "OPSP0000", "msg1": "SUBSCRIBE SUCCESS"},
        }
    )
    await manager._system(ack, settings)

    assert manager.subscription_state(key) == "SUBSCRIBED"

    await manager._realtime(_frame())
    snapshot = store.peek(key)
    assert snapshot is not None
    assert snapshot.transport == "WEBSOCKET"
    assert snapshot.current_price == Decimal("84200")
    assert snapshot.provider_timestamp == "2026-09-28T09:30:12+09:00"


def test_subscription_limit_never_evicts_existing_demand() -> None:
    settings = _settings(kis_ws_max_subscriptions=1)
    manager = QuoteWebSocketManager(
        store=QuoteStore(),
        settings_getter=lambda: settings,
    )
    first = _key(settings, "005930")
    second = _key(settings, "000660")

    assert manager.touch_demand(first) is True
    assert manager.touch_demand(second) is False
    assert manager.subscription_state(first) == "REQUESTED"
    assert manager.subscription_state(second) == "ERROR"


@pytest.mark.asyncio
async def test_manager_publishes_only_store_accepted_websocket_tick() -> None:
    settings = _settings()
    store = QuoteStore()
    hub = QuoteEventHub()
    key = _key(settings)
    queue = await hub.subscribe(key)
    manager = QuoteWebSocketManager(
        store=store,
        settings_getter=lambda: settings,
        event_hub=hub,
    )
    manager.touch_demand(key)
    manager._set_state("CONNECTED")
    manager._leases[key].state = "SUBSCRIBED"

    await manager._realtime(_frame())

    published = await queue.get()
    assert published.current_price == Decimal("84200")
    assert published.transport == "WEBSOCKET"

    newer = _snapshot(
        price="84300",
        transport="WEBSOCKET",
        provider_timestamp="2026-09-28T09:30:13+09:00",
    )
    assert store.put(key, newer) is True

    await manager._realtime(_frame())

    assert queue.empty()
