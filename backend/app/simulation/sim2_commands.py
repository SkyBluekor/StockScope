from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .sim1_enums import OrderType, PositionSource
from .sim1_models import SimulationDomainError, as_decimal, require_positive_quantity


@dataclass(frozen=True, slots=True)
class BuyCommand:
    portfolio_id: str
    stock_code: str
    stock_name: str
    quantity: int
    execution_price: Decimal
    source: PositionSource
    market: str = "KRX"
    scanner_baseline_id: str | None = None
    order_type: OrderType = OrderType.MARKET
    client_request_id: str | None = None

    def __post_init__(self) -> None:
        if not self.portfolio_id.strip():
            raise SimulationDomainError("portfolio_id is required")
        if not self.stock_code.strip() or not self.stock_name.strip():
            raise SimulationDomainError("stock identity is required")
        if not self.market.strip():
            raise SimulationDomainError("market is required")
        require_positive_quantity(self.quantity)
        object.__setattr__(self, "execution_price", as_decimal(self.execution_price, field="execution_price", allow_zero=False))
        if self.client_request_id is not None and not self.client_request_id.strip():
            raise SimulationDomainError("client_request_id must not be blank")


@dataclass(frozen=True, slots=True)
class SellCommand:
    portfolio_id: str
    position_id: str
    quantity: int
    execution_price: Decimal
    order_type: OrderType = OrderType.MARKET
    client_request_id: str | None = None

    def __post_init__(self) -> None:
        if not self.portfolio_id.strip() or not self.position_id.strip():
            raise SimulationDomainError("portfolio_id and position_id are required")
        require_positive_quantity(self.quantity)
        object.__setattr__(self, "execution_price", as_decimal(self.execution_price, field="execution_price", allow_zero=False))
        if self.client_request_id is not None and not self.client_request_id.strip():
            raise SimulationDomainError("client_request_id must not be blank")
