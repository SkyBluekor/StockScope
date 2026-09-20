from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .sim1_enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioStatus,
    PositionSource,
    PositionStatus,
    SimulationMode,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


class SimulationDomainError(ValueError):
    pass


def as_decimal(value: Any, *, field: str, allow_zero: bool = True, allow_negative: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise SimulationDomainError(f"{field} must be numeric")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SimulationDomainError(f"{field} must be a valid decimal") from exc
    if not result.is_finite():
        raise SimulationDomainError(f"{field} must be finite")
    if not allow_negative and result < ZERO:
        raise SimulationDomainError(f"{field} must not be negative")
    if not allow_zero and result == ZERO:
        raise SimulationDomainError(f"{field} must be greater than zero")
    return result


def money_text(value: Decimal) -> str:
    value = as_decimal(value, field="money", allow_negative=True)
    if value == ZERO:
        return "0"
    return format(value.normalize(), "f")


def require_positive_quantity(quantity: int, *, field: str = "quantity") -> int:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise SimulationDomainError(f"{field} must be a positive integer")
    return quantity


def require_timezone_aware(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SimulationDomainError(f"{field} must be timezone-aware")
    return value


def weighted_average_entry(
    existing_quantity: int,
    existing_average: Decimal,
    added_quantity: int,
    added_price: Decimal,
) -> Decimal:
    require_positive_quantity(existing_quantity, field="existing_quantity")
    require_positive_quantity(added_quantity, field="added_quantity")
    existing_average = as_decimal(existing_average, field="existing_average", allow_zero=False)
    added_price = as_decimal(added_price, field="added_price", allow_zero=False)
    total_quantity = existing_quantity + added_quantity
    return (
        existing_average * existing_quantity + added_price * added_quantity
    ) / Decimal(total_quantity)


@dataclass(frozen=True, slots=True)
class SimulationPortfolio:
    id: str
    name: str
    mode: SimulationMode
    initial_cash: Decimal
    cash_balance: Decimal
    realized_pnl: Decimal
    default_scanner_baseline_id: str
    status: PortfolioStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise SimulationDomainError("portfolio id is required")
        if not self.name.strip():
            raise SimulationDomainError("portfolio name is required")
        object.__setattr__(self, "initial_cash", as_decimal(self.initial_cash, field="initial_cash", allow_zero=False))
        object.__setattr__(self, "cash_balance", as_decimal(self.cash_balance, field="cash_balance"))
        object.__setattr__(self, "realized_pnl", as_decimal(self.realized_pnl, field="realized_pnl", allow_negative=True))
        if not self.default_scanner_baseline_id.strip():
            raise SimulationDomainError("default_scanner_baseline_id is required")
        require_timezone_aware(self.created_at, field="created_at")
        require_timezone_aware(self.updated_at, field="updated_at")


@dataclass(frozen=True, slots=True)
class SimulationPosition:
    id: str
    portfolio_id: str
    stock_code: str
    stock_name: str
    market: str
    source: PositionSource
    status: PositionStatus
    quantity: int
    average_entry_price: Decimal
    current_price: Decimal
    realized_pnl: Decimal
    scanner_baseline_id: str
    opened_at: datetime
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.portfolio_id.strip():
            raise SimulationDomainError("position id and portfolio_id are required")
        if not self.stock_code.strip():
            raise SimulationDomainError("stock_code is required")
        if not self.stock_name.strip():
            raise SimulationDomainError("stock_name is required")
        if not self.market.strip():
            raise SimulationDomainError("market is required")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity < 0:
            raise SimulationDomainError("quantity must be a non-negative integer")
        if self.status == PositionStatus.OPEN and self.quantity <= 0:
            raise SimulationDomainError("OPEN position must have positive quantity")
        if self.status == PositionStatus.CLOSED and self.quantity != 0:
            raise SimulationDomainError("CLOSED position must have zero quantity")
        if self.status == PositionStatus.CLOSED and self.closed_at is None:
            raise SimulationDomainError("CLOSED position requires closed_at")
        object.__setattr__(self, "average_entry_price", as_decimal(self.average_entry_price, field="average_entry_price", allow_zero=False))
        object.__setattr__(self, "current_price", as_decimal(self.current_price, field="current_price", allow_zero=False))
        object.__setattr__(self, "realized_pnl", as_decimal(self.realized_pnl, field="realized_pnl", allow_negative=True))
        if not self.scanner_baseline_id.strip():
            raise SimulationDomainError("scanner_baseline_id is required")
        require_timezone_aware(self.opened_at, field="opened_at")
        if self.closed_at is not None:
            require_timezone_aware(self.closed_at, field="closed_at")

    @property
    def cost_basis(self) -> Decimal:
        return self.average_entry_price * self.quantity

    @property
    def market_value(self) -> Decimal:
        return self.current_price * self.quantity

    @property
    def unrealized_pnl(self) -> Decimal:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> Decimal:
        if self.cost_basis == ZERO:
            return ZERO
        return self.unrealized_pnl / self.cost_basis * HUNDRED


@dataclass(frozen=True, slots=True)
class SimulationOrder:
    id: str
    portfolio_id: str
    position_id: str | None
    stock_code: str
    stock_name: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    requested_price: Decimal | None
    status: OrderStatus
    requested_at: datetime
    filled_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.portfolio_id.strip():
            raise SimulationDomainError("order id and portfolio_id are required")
        if not self.stock_code.strip() or not self.stock_name.strip():
            raise SimulationDomainError("order stock identity is required")
        require_positive_quantity(self.quantity)
        if self.requested_price is not None:
            object.__setattr__(self, "requested_price", as_decimal(self.requested_price, field="requested_price", allow_zero=False))
        if self.order_type == OrderType.LIMIT and self.requested_price is None:
            raise SimulationDomainError("LIMIT order requires requested_price")
        require_timezone_aware(self.requested_at, field="requested_at")
        if self.filled_at is not None:
            require_timezone_aware(self.filled_at, field="filled_at")


@dataclass(frozen=True, slots=True)
class SimulationTrade:
    id: str
    portfolio_id: str
    order_id: str
    position_id: str
    stock_code: str
    side: OrderSide
    quantity: int
    price: Decimal
    gross_amount: Decimal
    fee: Decimal
    tax: Decimal
    slippage: Decimal
    net_amount: Decimal
    realized_pnl: Decimal
    executed_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("id", "portfolio_id", "order_id", "position_id", "stock_code"):
            if not str(getattr(self, field_name)).strip():
                raise SimulationDomainError(f"{field_name} is required")
        require_positive_quantity(self.quantity)
        object.__setattr__(self, "price", as_decimal(self.price, field="price", allow_zero=False))
        object.__setattr__(self, "gross_amount", as_decimal(self.gross_amount, field="gross_amount"))
        object.__setattr__(self, "fee", as_decimal(self.fee, field="fee"))
        object.__setattr__(self, "tax", as_decimal(self.tax, field="tax"))
        object.__setattr__(self, "slippage", as_decimal(self.slippage, field="slippage"))
        object.__setattr__(self, "net_amount", as_decimal(self.net_amount, field="net_amount"))
        object.__setattr__(self, "realized_pnl", as_decimal(self.realized_pnl, field="realized_pnl", allow_negative=True))
        expected_gross = self.price * self.quantity
        if self.gross_amount != expected_gross:
            raise SimulationDomainError("gross_amount must equal price * quantity")
        require_timezone_aware(self.executed_at, field="executed_at")


@dataclass(frozen=True, slots=True)
class PortfolioSummary:
    portfolio: SimulationPortfolio
    positions_market_value: Decimal
    unrealized_pnl: Decimal
    total_equity: Decimal
    total_return_pct: Decimal
    open_position_count: int
