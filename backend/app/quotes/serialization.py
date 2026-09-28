from __future__ import annotations

from .models import QuoteDeliverySource, QuoteSnapshot, StockQuoteResponse


def _decimal_text(value) -> str:
    return format(value, "f")


def build_stock_quote_response(
    snapshot: QuoteSnapshot,
    *,
    delivery_source: QuoteDeliverySource,
    cache_age_ms: int,
) -> StockQuoteResponse:
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
            "source": delivery_source,
            "cache_age_ms": cache_age_ms,
        },
    )
