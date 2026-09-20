from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


class PriceStatus(str, Enum):
    FRESH = "FRESH"
    MISSING = "MISSING"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class SimulationSession:
    id: str
    portfolio_id: str
    start_date: date
    end_date: date | None
    current_date: date
    status: SessionStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PositionMarkState:
    position_id: str
    session_id: str
    mark_date: date
    source_bar_date: date | None
    price_status: PriceStatus
    valuation_stale: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DateStepRecord:
    id: str
    session_id: str
    from_date: date
    to_date: date
    updated_positions: int
    missing_positions: int
    cash_balance: Decimal
    positions_market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_equity: Decimal
    created_at: datetime
