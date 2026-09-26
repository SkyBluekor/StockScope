from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Path, Query, Response
from starlette.concurrency import run_in_threadpool

from app.quotes import QuoteServiceError, StockQuoteResponse, quote_service


router = APIRouter(prefix="/quotes", tags=["quotes"])


def _decimal_text(value) -> str:
    return format(value, "f")


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
        from fastapi import HTTPException

        detail = {
            "code": exc.code,
            "message": exc.message,
        }
        if exc.provider_code:
            detail["provider_code"] = exc.provider_code
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc

    snapshot = result.snapshot
    return StockQuoteResponse(
        resource_key=f"{snapshot.market}:{snapshot.ticker}",
        market=snapshot.market,  # type: ignore[arg-type]
        ticker=snapshot.ticker,
        name=snapshot.name,
        venue=snapshot.venue,
        provider_market_division=snapshot.provider_market_division,
        environment=snapshot.environment,  # type: ignore[arg-type]
        current_price=_decimal_text(snapshot.current_price),
        change_amount=_decimal_text(snapshot.change_amount),
        change_rate=_decimal_text(snapshot.change_rate),
        change_sign=snapshot.change_sign,
        open_price=_decimal_text(snapshot.open_price),
        high_price=_decimal_text(snapshot.high_price),
        low_price=_decimal_text(snapshot.low_price),
        base_price=_decimal_text(snapshot.base_price),
        accumulated_volume=_decimal_text(snapshot.accumulated_volume),
        provider_timestamp=snapshot.provider_timestamp,
        received_at=snapshot.received_at.isoformat(),
        delivery={
            "source": result.delivery_source,
            "cache_age_ms": result.cache_age_ms,
        },
    )
