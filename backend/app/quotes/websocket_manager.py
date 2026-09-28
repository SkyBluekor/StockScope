from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Callable

from websockets.asyncio.client import connect as websocket_connect

from app.core.config import Settings, get_settings
from app.integrations.kis.client import KisConfigurationError, normalize_environment, validate_settings
from app.integrations.kis.token_cache import credential_fingerprint
from app.integrations.kis.ws_approval import KisWebSocketApproval, get_ws_approval_key, invalidate_ws_approval_key
from app.market_session.service import DomesticMarketSessionService, market_session_service

from .event_hub import QuoteEventHub, quote_event_hub
from .models import QuoteCacheKey, QuoteSnapshot, VENUE_TO_KIS_MARKET_DIVISION
from .store import QuoteStore, quote_store
from .websocket_parser import VENUE_TO_WS_TR_ID, WebSocketQuoteParseError, parse_quote_frame
from .websocket_state import SubscriptionLease, SubscriptionState, TransportState


logger = logging.getLogger(__name__)
_ACTIVE_PHASES = {"PRE_MARKET", "REGULAR", "AFTER_MARKET", "UNKNOWN"}


class _AuthRefreshReconnect(RuntimeError):
    pass


class QuoteWebSocketManager:
    def __init__(
        self,
        *,
        store: QuoteStore | None = None,
        settings_getter: Callable[[], Settings] = get_settings,
        session_service: DomesticMarketSessionService | None = None,
        approval_getter: Callable[[Settings], KisWebSocketApproval] = get_ws_approval_key,
        approval_invalidator: Callable[..., bool] = invalidate_ws_approval_key,
        connect_factory=websocket_connect,
        monotonic: Callable[[], float] = time.monotonic,
        event_hub: QuoteEventHub | None = None,
    ) -> None:
        self.store = store or quote_store
        self.settings_getter = settings_getter
        self.session_service = session_service or market_session_service
        self.approval_getter = approval_getter
        self.approval_invalidator = approval_invalidator
        self.connect_factory = connect_factory
        self.monotonic = monotonic
        self.event_hub = event_hub or quote_event_hub
        self._lock = Lock()
        self._leases: dict[QuoteCacheKey, SubscriptionLease] = {}
        self._state: TransportState = "IDLE"
        self._task: asyncio.Task[None] | None = None
        self._ws = None
        self._approval_key: str | None = None
        self._stop = False
        self._auth_refresh_used = False

    @property
    def transport_state(self) -> TransportState:
        with self._lock:
            return self._state

    def _set_state(self, value: TransportState) -> None:
        with self._lock:
            self._state = value

    def touch_demand(self, key: QuoteCacheKey) -> bool:
        settings = self.settings_getter()
        if not settings.kis_ws_enabled:
            return False
        ttl = max(1.0, float(settings.kis_ws_demand_ttl_seconds))
        limit = max(1, int(settings.kis_ws_max_subscriptions))
        now = self.monotonic()
        with self._lock:
            lease = self._leases.get(key)
            if lease is not None:
                lease.touched_at = now
                if lease.state == "ERROR" and lease.error_code == "SUBSCRIPTION_LIMIT":
                    active = sum(
                        1 for item in self._leases.values()
                        if now - item.touched_at <= ttl
                        and item.key != key
                        and item.error_code != "SUBSCRIPTION_LIMIT"
                    )
                    if active < limit:
                        lease.state, lease.error_code = "REQUESTED", None
                return lease.error_code != "SUBSCRIPTION_LIMIT"

            active = sum(
                1 for item in self._leases.values()
                if now - item.touched_at <= ttl
                and item.error_code != "SUBSCRIPTION_LIMIT"
            )
            if active >= limit:
                self._leases[key] = SubscriptionLease(
                    key, now, state="ERROR", error_code="SUBSCRIPTION_LIMIT"
                )
                return False
            self._leases[key] = SubscriptionLease(key, now)
            return True

    def subscription_state(self, key: QuoteCacheKey) -> SubscriptionState | None:
        with self._lock:
            lease = self._leases.get(key)
            return lease.state if lease else None

    def subscription_error(self, key: QuoteCacheKey) -> str | None:
        with self._lock:
            lease = self._leases.get(key)
            return lease.error_code if lease else None

    def is_subscription_ready(self, key: QuoteCacheKey) -> bool:
        with self._lock:
            lease = self._leases.get(key)
            return self._state == "CONNECTED" and lease is not None and lease.state == "SUBSCRIBED"

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop = False
            self._task = asyncio.create_task(self._run(), name="kis-quote-websocket")

    async def stop(self) -> None:
        self._stop = True
        self._set_state("STOPPING")
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        await self._close()

    async def _session_phase(self) -> str:
        try:
            session = await asyncio.to_thread(self.session_service.get_session, "INTEGRATED")
            return session.phase
        except Exception:
            return "UNKNOWN"

    async def _expire(self, settings: Settings) -> None:
        ttl = max(1.0, float(settings.kis_ws_demand_ttl_seconds))
        env = normalize_environment(settings.kis_env)
        fingerprint = credential_fingerprint(settings)
        now = self.monotonic()
        with self._lock:
            expired = [
                (key, lease.state)
                for key, lease in self._leases.items()
                if now - lease.touched_at > ttl
                or key.environment != env
                or key.credential_fingerprint != fingerprint
            ]
            for key, _ in expired:
                lease = self._leases.get(key)
                if lease and lease.state == "SUBSCRIBED":
                    lease.state = "EXPIRING"
        for key, old_state in expired:
            if old_state == "SUBSCRIBED" and self._ws is not None:
                try:
                    await self._send(key, "0")
                except Exception:
                    pass
            with self._lock:
                self._leases.pop(key, None)

    def _has_demand(self, settings: Settings) -> bool:
        ttl = max(1.0, float(settings.kis_ws_demand_ttl_seconds))
        now = self.monotonic()
        with self._lock:
            return any(
                now - lease.touched_at <= ttl and lease.error_code != "SUBSCRIPTION_LIMIT"
                for lease in self._leases.values()
            )

    async def _connect(self, settings: Settings) -> None:
        self._set_state("CONNECTING")
        approval = await asyncio.to_thread(self.approval_getter, settings)
        self._approval_key = approval.approval_key
        url = settings.kis_ws_real_url if normalize_environment(settings.kis_env) == "real" else settings.kis_ws_virtual_url
        self._ws = await self.connect_factory(
            url, ping_interval=30, ping_timeout=10, open_timeout=15, close_timeout=5
        )
        self._set_state("CONNECTED")
        with self._lock:
            for lease in self._leases.values():
                if lease.state in {"SUBSCRIBING", "SUBSCRIBED", "EXPIRING"}:
                    lease.state, lease.error_code = "REQUESTED", None

    async def _close(self) -> None:
        ws, self._ws = self._ws, None
        self._approval_key = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        with self._lock:
            for lease in self._leases.values():
                if lease.state in {"SUBSCRIBING", "SUBSCRIBED", "EXPIRING"}:
                    lease.state, lease.error_code = "REQUESTED", None

    async def _send(self, key: QuoteCacheKey, tr_type: str) -> None:
        if self._ws is None or not self._approval_key:
            raise RuntimeError("websocket is not connected")
        payload = {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": tr_type,
                "content-type": "utf-8",
            },
            "body": {"input": {"tr_id": VENUE_TO_WS_TR_ID[key.venue], "tr_key": key.ticker}},
        }
        await self._ws.send(json.dumps(payload, ensure_ascii=False))

    async def _reconcile(self, settings: Settings) -> None:
        await self._expire(settings)
        limit = max(1, int(settings.kis_ws_max_subscriptions))
        with self._lock:
            used = sum(
                lease.state in {"SUBSCRIBING", "SUBSCRIBED"}
                for lease in self._leases.values()
            )
            pending = [lease.key for lease in self._leases.values() if lease.state == "REQUESTED"]
        for key in pending:
            if used >= limit:
                with self._lock:
                    lease = self._leases.get(key)
                    if lease:
                        lease.state, lease.error_code = "ERROR", "SUBSCRIPTION_LIMIT"
                continue
            with self._lock:
                lease = self._leases.get(key)
                if not lease or lease.state != "REQUESTED":
                    continue
                lease.state = "SUBSCRIBING"
            await self._send(key, "1")
            used += 1
            await asyncio.sleep(0.05)

    def _find_key(self, tr_id: str, ticker: str) -> QuoteCacheKey | None:
        with self._lock:
            return next(
                (
                    key for key in self._leases
                    if key.ticker == ticker and VENUE_TO_WS_TR_ID[key.venue] == tr_id
                ),
                None,
            )

    @staticmethod
    def _auth_error(body: dict) -> bool:
        text = " ".join(str(body.get(k) or "") for k in ("msg_cd", "msg1", "message", "error")).upper()
        return any(token in text for token in ("APPROVAL", "AUTH", "인증", "접속키"))

    async def _system(self, raw: str, settings: Settings) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
        tr_id = str(header.get("tr_id") or "")
        if tr_id == "PINGPONG":
            if self._ws is not None:
                await self._ws.pong(raw.encode("utf-8"))
            return
        ticker = str(header.get("tr_key") or "").strip()
        body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
        key = self._find_key(tr_id, ticker)
        if key is None or not body:
            return

        message = str(body.get("msg1") or "").strip()
        if str(body.get("rt_cd") or "") == "0" or message == "ALREADY IN SUBSCRIBE":
            with self._lock:
                lease = self._leases.get(key)
                if lease and lease.state != "EXPIRING":
                    lease.state, lease.error_code = "SUBSCRIBED", None
            self._auth_refresh_used = False
            return

        with self._lock:
            lease = self._leases.get(key)
            if lease:
                lease.state = "ERROR"
                lease.error_code = str(body.get("msg_cd") or "SUBSCRIPTION_REJECTED")
        if self._auth_error(body) and not self._auth_refresh_used:
            self._auth_refresh_used = True
            await asyncio.to_thread(
                self.approval_invalidator,
                settings,
                expected_approval_key=self._approval_key,
            )
            with self._lock:
                lease = self._leases.get(key)
                if lease:
                    lease.state, lease.error_code = "REQUESTED", None
            raise _AuthRefreshReconnect()

    async def _realtime(self, raw: str) -> None:
        try:
            ticks = parse_quote_frame(raw)
        except WebSocketQuoteParseError as exc:
            logger.warning("Dropping invalid KIS websocket quote frame: %s", exc)
            return
        for tick in ticks:
            key = self._find_key(VENUE_TO_WS_TR_ID[tick.venue], tick.ticker)
            if key is None or not self.is_subscription_ready(key):
                continue
            old = self.store.peek(key)
            snapshot = QuoteSnapshot(
                market=key.market,
                ticker=tick.ticker,
                name=old.name if old else None,
                venue=tick.venue,
                provider_market_division=VENUE_TO_KIS_MARKET_DIVISION[tick.venue],
                environment=key.environment,
                current_price=tick.current_price,
                change_amount=tick.change_amount,
                change_rate=tick.change_rate,
                change_sign=tick.change_sign,
                open_price=tick.open_price,
                high_price=tick.high_price,
                low_price=tick.low_price,
                base_price=tick.base_price,
                accumulated_volume=tick.accumulated_volume,
                provider_timestamp=tick.provider_timestamp,
                received_at=datetime.now(timezone.utc),
                transport="WEBSOCKET",
            )
            if self.store.put(key, snapshot):
                await self.event_hub.publish(key, snapshot)

    async def _message(self, raw, settings: Settings) -> None:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError:
                return
        if not isinstance(raw, str) or not raw:
            return
        if raw[0] in {"0", "1"}:
            await self._realtime(raw)
        else:
            await self._system(raw, settings)

    async def _run(self) -> None:
        backoff = 1.0
        try:
            while not self._stop:
                try:
                    settings = self.settings_getter()
                    if not settings.kis_ws_enabled:
                        await self._close()
                        self._set_state("DISABLED")
                        await asyncio.sleep(0.5)
                        continue
                    try:
                        validate_settings(settings)
                    except KisConfigurationError:
                        await self._close()
                        self._set_state("DEGRADED")
                        await asyncio.sleep(1.0)
                        continue
                    await self._expire(settings)
                    if not self._has_demand(settings):
                        await self._close()
                        self._set_state("IDLE")
                        backoff = max(1.0, float(settings.kis_ws_reconnect_base_seconds))
                        await asyncio.sleep(0.5)
                        continue
                    if await self._session_phase() not in _ACTIVE_PHASES:
                        await self._close()
                        self._set_state("IDLE")
                        await asyncio.sleep(1.0)
                        continue
                    if self._ws is None:
                        await self._connect(settings)
                        backoff = max(1.0, float(settings.kis_ws_reconnect_base_seconds))
                    await self._reconcile(settings)
                    try:
                        raw = await asyncio.wait_for(self._ws.recv(), timeout=0.75)
                    except asyncio.TimeoutError:
                        continue
                    await self._message(raw, settings)
                except asyncio.CancelledError:
                    raise
                except _AuthRefreshReconnect:
                    await self._close()
                    self._set_state("CONNECTING")
                except Exception as exc:
                    logger.warning("KIS quote websocket transport error: %s", exc)
                    await self._close()
                    self._set_state("BACKOFF")
                    try:
                        maximum = max(1.0, float(self.settings_getter().kis_ws_reconnect_max_seconds))
                    except Exception:
                        maximum = 30.0
                    await asyncio.sleep(backoff)
                    backoff = min(maximum, max(1.0, backoff * 2.0))
        finally:
            await self._close()
            if self._stop:
                self._set_state("STOPPING")


quote_websocket_manager = QuoteWebSocketManager()
