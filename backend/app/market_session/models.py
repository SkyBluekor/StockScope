from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


MarketSessionPhase = Literal[
    "PRE_MARKET",
    "REGULAR",
    "INTERMISSION",
    "AFTER_MARKET",
    "CLOSED",
    "UNKNOWN",
]
MarketSessionSource = Literal[
    "WEEKEND_RULE",
    "KIS_HOLIDAY",
    "SESSION_CLOCK",
    "UNKNOWN",
]


@dataclass(frozen=True, slots=True)
class DomesticMarketSession:
    market: str
    venue: str
    timezone: str
    checked_at: str
    local_date: str
    trading_day: bool | None
    phase: MarketSessionPhase
    quote_polling_allowed: bool
    market_active: bool | None
    next_transition_at: str | None
    source: MarketSessionSource
    reason_code: str | None = None


class DomesticMarketSessionResponse(BaseModel):
    market: Literal["DOMESTIC_EQUITY"] = "DOMESTIC_EQUITY"
    venue: Literal["INTEGRATED"] = "INTEGRATED"
    timezone: Literal["Asia/Seoul"] = "Asia/Seoul"
    checked_at: str
    local_date: str
    trading_day: bool | None
    phase: MarketSessionPhase
    quote_polling_allowed: bool
    market_active: bool | None
    next_transition_at: str | None
    source: MarketSessionSource
    reason_code: str | None = None
