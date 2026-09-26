from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


QuoteVenue = Literal["INTEGRATED", "KRX", "NXT"]
QuoteDeliverySource = Literal["UPSTREAM", "CACHE", "SINGLE_FLIGHT", "WEBSOCKET"]
QuoteTransport = Literal["REST", "WEBSOCKET"]

VENUE_TO_KIS_MARKET_DIVISION: dict[QuoteVenue, str] = {
    "INTEGRATED": "UN",
    "KRX": "J",
    "NXT": "NX",
}


@dataclass(frozen=True, slots=True)
class QuoteCacheKey:
    environment: str
    credential_fingerprint: str
    market: str
    ticker: str
    venue: QuoteVenue


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    market: str
    ticker: str
    name: str | None
    venue: QuoteVenue
    provider_market_division: str
    environment: str
    current_price: Decimal
    change_amount: Decimal
    change_rate: Decimal
    change_sign: str | None
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    base_price: Decimal
    accumulated_volume: Decimal
    provider_timestamp: str | None
    received_at: datetime
    transport: QuoteTransport = "REST"


@dataclass(frozen=True, slots=True)
class QuoteResult:
    snapshot: QuoteSnapshot
    delivery_source: QuoteDeliverySource
    cache_age_ms: int


@dataclass(frozen=True, slots=True)
class CachedQuoteObservation:
    capable: bool
    present: bool
    source: str
    market: str
    ticker: str
    venue: QuoteVenue
    provider: str | None = None
    mode: str | None = None
    current_price: Decimal | None = None
    provider_timestamp: str | None = None
    received_at: datetime | None = None
    age_ms: int | None = None
    freshness_seconds: float | None = None
    reason: str | None = None


class QuoteDeliveryResponse(BaseModel):
    source: QuoteDeliverySource
    cache_age_ms: int


class StockQuoteResponse(BaseModel):
    resource_key: str
    provider: Literal["KIS"] = "KIS"
    mode: Literal["SNAPSHOT"] = "SNAPSHOT"
    market: Literal["KOSPI", "KOSDAQ"]
    ticker: str
    name: str | None
    venue: QuoteVenue
    provider_market_division: str
    environment: Literal["real", "virtual"]
    current_price: str
    change_amount: str
    change_rate: str
    change_sign: str | None
    open_price: str
    high_price: str
    low_price: str
    base_price: str
    accumulated_volume: str
    provider_timestamp: str | None
    received_at: str
    delivery: QuoteDeliveryResponse
