from __future__ import annotations

from enum import StrEnum


class PortfolioStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class SimulationMode(StrEnum):
    HISTORICAL = "HISTORICAL"
    MANUAL_TRACKING = "MANUAL_TRACKING"
    PAPER = "PAPER"


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PositionSource(StrEnum):
    SCANNER = "SCANNER"
    MANUAL = "MANUAL"
    KIS_IMPORT = "KIS_IMPORT"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
