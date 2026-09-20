from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .sim1_enums import OrderType, PositionSource
from .sim1_models import SimulationDomainError, money_text
from .sim1_service import default_paths
from .sim1_store import BaselineRegistry, SimulationRepository
from .sim2_commands import BuyCommand, SellCommand
from .sim2_trading_service import SimulationTradingError, SimulationTradingService

router = APIRouter(prefix="/simulation", tags=["simulation-trading"])


class BuyRequest(BaseModel):
    stock_code: str = Field(min_length=1, max_length=24)
    stock_name: str = Field(min_length=1, max_length=120)
    market: str = Field(default="KRX", min_length=1, max_length=24)
    quantity: int = Field(gt=0)
    execution_price: Decimal = Field(gt=0)
    source: PositionSource = PositionSource.MANUAL
    scanner_baseline_id: str | None = None
    order_type: OrderType = OrderType.MARKET
    client_request_id: str | None = Field(default=None, min_length=1, max_length=120)


class SellRequest(BaseModel):
    position_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    execution_price: Decimal = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    client_request_id: str | None = Field(default=None, min_length=1, max_length=120)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _service() -> SimulationTradingService:
    root = _project_root()
    default_db, baseline_dir = default_paths(root)
    db_path = Path(os.getenv("STOCKSCOPE_SIM_DB", str(default_db)))
    service = SimulationTradingService(SimulationRepository(db_path), BaselineRegistry(baseline_dir))
    service.initialize()
    return service


def _raise_trading(exc: Exception) -> None:
    if isinstance(exc, SimulationTradingError):
        status = 404 if exc.code in {"SIM_PORTFOLIO_NOT_FOUND", "SIM_POSITION_NOT_FOUND"} else 409
        if exc.code in {"SIM_BASELINE_REQUIRED", "SIM_BASELINE_INVALID"}:
            status = 400
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc
    if isinstance(exc, SimulationDomainError):
        raise HTTPException(status_code=400, detail={"code": "SIM_DOMAIN_INVALID", "message": str(exc)}) from exc
    raise exc


@router.post("/portfolios/{portfolio_id}/buy")
def buy(portfolio_id: str, request: BuyRequest):
    try:
        result = _service().buy(
            BuyCommand(
                portfolio_id=portfolio_id,
                stock_code=request.stock_code,
                stock_name=request.stock_name,
                market=request.market,
                quantity=request.quantity,
                execution_price=request.execution_price,
                source=request.source,
                scanner_baseline_id=request.scanner_baseline_id,
                order_type=request.order_type,
                client_request_id=request.client_request_id,
            )
        )
    except (SimulationTradingError, SimulationDomainError) as exc:
        _raise_trading(exc)
    return {
        "order_id": result.order.id,
        "trade_id": result.trade.id,
        "position_id": result.position.id,
        "status": result.order.status.value,
        "cash_balance": money_text(result.portfolio.cash_balance),
        "quantity": result.position.quantity,
        "average_entry_price": money_text(result.position.average_entry_price),
        "idempotent_replay": result.idempotent_replay,
    }


@router.post("/portfolios/{portfolio_id}/sell")
def sell(portfolio_id: str, request: SellRequest):
    try:
        result = _service().sell(
            SellCommand(
                portfolio_id=portfolio_id,
                position_id=request.position_id,
                quantity=request.quantity,
                execution_price=request.execution_price,
                order_type=request.order_type,
                client_request_id=request.client_request_id,
            )
        )
    except (SimulationTradingError, SimulationDomainError) as exc:
        _raise_trading(exc)
    return {
        "order_id": result.order.id,
        "trade_id": result.trade.id,
        "position_id": result.position.id,
        "status": result.order.status.value,
        "remaining_quantity": result.position.quantity,
        "position_status": result.position.status.value,
        "realized_pnl": money_text(result.realized_pnl),
        "cash_balance": money_text(result.portfolio.cash_balance),
        "idempotent_replay": result.idempotent_replay,
    }
