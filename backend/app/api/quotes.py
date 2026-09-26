from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from app.quotes import QuoteServiceError, StockQuoteResponse, quote_service
from app.quotes.event_hub import quote_event_hub
from app.quotes.serialization import build_stock_quote_response
from app.quotes.store import quote_store
from app.quotes.websocket_manager import quote_websocket_manager


router = APIRouter(prefix="/quotes", tags=["quotes"])
_HEARTBEAT_SECONDS = 15.0
_STATUS_CHECK_SECONDS = 1.0


def _http_error(exc: QuoteServiceError) -> HTTPException:
    detail = {
        "code": exc.code,
        "message": exc.message,
    }
    if exc.provider_code:
        detail["provider_code"] = exc.provider_code
    return HTTPException(status_code=exc.status_code, detail=detail)


def _sse_event(event: str, payload: dict[str, object]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"


def _stream_status(key) -> dict[str, object]:
    transport = quote_websocket_manager.transport_state
    subscription = quote_websocket_manager.subscription_state(key)
    subscription_error = quote_websocket_manager.subscription_error(key)

    if transport == "CONNECTED" and subscription == "SUBSCRIBED":
        state = "LIVE"
        reason_code = None
    elif transport in {"DISABLED", "STOPPING"}:
        state = "UNAVAILABLE"
        reason_code = (
            subscription_error
            or ("WEBSOCKET_DISABLED" if transport == "DISABLED" else "WEBSOCKET_STOPPING")
        )
    elif transport in {"BACKOFF", "DEGRADED"} or subscription == "ERROR":
        state = "DEGRADED"
        reason_code = subscription_error or f"WEBSOCKET_{transport}"
    else:
        state = "CONNECTING"
        reason_code = subscription_error

    return {
        "resource_key": f"{key.market}:{key.ticker}",
        "market": key.market,
        "ticker": key.ticker,
        "venue": key.venue,
        "state": state,
        "transport_state": transport,
        "subscription_state": subscription,
        "reason_code": reason_code,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _status_signature(status: dict[str, object]) -> tuple[object, ...]:
    return (
        status["state"],
        status["transport_state"],
        status["subscription_state"],
        status["reason_code"],
    )


def _quote_signature(snapshot) -> tuple[object, ...]:
    return (
        snapshot.provider_timestamp,
        snapshot.received_at,
        snapshot.transport,
    )


@router.get("/stocks/{ticker}", response_model=StockQuoteResponse)
async def stock_quote(
    response: Response,
    ticker: str = Path(..., pattern=r"^\d{6}$"),
    market: Literal["KOSPI", "KOSDAQ"] = Query(...),
    venue: Literal["INTEGRATED", "KRX", "NXT"] = Query("INTEGRATED"),
) -> StockQuoteResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        result = await run_in_threadpool(
            quote_service.get_quote,
            market=market,
            ticker=ticker,
            venue=venue,
        )
    except QuoteServiceError as exc:
        raise _http_error(exc) from exc

    return build_stock_quote_response(
        result.snapshot,
        delivery_source=result.delivery_source,
        cache_age_ms=result.cache_age_ms,
    )


@router.get("/stocks/{ticker}/stream")
async def stock_quote_stream(
    request: Request,
    ticker: str = Path(..., pattern=r"^\d{6}$"),
    market: Literal["KOSPI", "KOSDAQ"] = Query(...),
    venue: Literal["INTEGRATED", "KRX", "NXT"] = Query("INTEGRATED"),
) -> StreamingResponse:
    try:
        key = quote_service.resolve_key(
            market=market,
            ticker=ticker,
            venue=venue,
        )
    except QuoteServiceError as exc:
        raise _http_error(exc) from exc

    queue = await quote_event_hub.subscribe(key)

    async def event_stream():
        loop = asyncio.get_running_loop()
        next_heartbeat = loop.time()
        last_status: tuple[object, ...] | None = None
        last_quote: tuple[object, ...] | None = None
        try:
            while True:
                if await request.is_disconnected():
                    break

                now = loop.time()
                if now >= next_heartbeat:
                    try:
                        quote_websocket_manager.touch_demand(key)
                    except Exception:
                        pass
                    if next_heartbeat != now:
                        yield ": heartbeat\n\n"
                    next_heartbeat = now + _HEARTBEAT_SECONDS

                status = _stream_status(key)
                signature = _status_signature(status)
                if signature != last_status:
                    last_status = signature
                    yield _sse_event("status", status)

                    if status["state"] == "LIVE":
                        snapshot = quote_store.peek(key)
                        if snapshot is not None and snapshot.transport == "WEBSOCKET":
                            quote_signature = _quote_signature(snapshot)
                            if quote_signature != last_quote:
                                last_quote = quote_signature
                                payload = build_stock_quote_response(
                                    snapshot,
                                    delivery_source="WEBSOCKET",
                                    cache_age_ms=quote_store.age_ms(snapshot),
                                )
                                yield _sse_event(
                                    "quote",
                                    payload.model_dump(mode="json"),
                                )

                try:
                    snapshot = await asyncio.wait_for(
                        queue.get(),
                        timeout=_STATUS_CHECK_SECONDS,
                    )
                except asyncio.TimeoutError:
                    continue

                if snapshot.transport != "WEBSOCKET":
                    continue
                quote_signature = _quote_signature(snapshot)
                if quote_signature == last_quote:
                    continue
                last_quote = quote_signature
                payload = build_stock_quote_response(
                    snapshot,
                    delivery_source="WEBSOCKET",
                    cache_age_ms=quote_store.age_ms(snapshot),
                )
                yield _sse_event("quote", payload.model_dump(mode="json"))
        finally:
            await quote_event_hub.unsubscribe(key, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
