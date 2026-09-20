from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .sim1_enums import PositionStatus, SimulationMode
from .sim1_models import SimulationDomainError, money_text
from .sim1_service import SimulationNotFoundError, SimulationPortfolioService, default_paths
from .sim1_store import BaselineRegistry, SimulationRepository

router = APIRouter(prefix="/simulation", tags=["simulation"])


class CreatePortfolioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    initial_cash: Decimal = Field(gt=0)
    mode: SimulationMode = SimulationMode.HISTORICAL
    scanner_baseline_id: str | None = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _service() -> SimulationPortfolioService:
    root = _project_root()
    default_db, baseline_dir = default_paths(root)
    db_path = Path(os.getenv("STOCKSCOPE_SIM_DB", str(default_db)))
    service = SimulationPortfolioService(
        SimulationRepository(db_path),
        BaselineRegistry(baseline_dir),
    )
    service.initialize()
    return service


def _position_payload(p):
    return {
        "id": p.id,
        "portfolio_id": p.portfolio_id,
        "stock_code": p.stock_code,
        "stock_name": p.stock_name,
        "market": p.market,
        "source": p.source.value,
        "status": p.status.value,
        "quantity": p.quantity,
        "average_entry_price": money_text(p.average_entry_price),
        "current_price": money_text(p.current_price),
        "cost_basis": money_text(p.cost_basis),
        "market_value": money_text(p.market_value),
        "unrealized_pnl": money_text(p.unrealized_pnl),
        "unrealized_pnl_pct": money_text(p.unrealized_pnl_pct),
        "realized_pnl": money_text(p.realized_pnl),
        "scanner_baseline_id": p.scanner_baseline_id,
        "opened_at": p.opened_at.isoformat(),
        "closed_at": p.closed_at.isoformat() if p.closed_at else None,
    }


@router.post("/portfolios", status_code=201)
def create_portfolio(request: CreatePortfolioRequest):
    try:
        p = _service().create_portfolio(
            name=request.name,
            initial_cash=request.initial_cash,
            mode=request.mode,
            scanner_baseline_id=request.scanner_baseline_id,
        )
    except SimulationDomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": p.id,
        "name": p.name,
        "mode": p.mode.value,
        "initial_cash": money_text(p.initial_cash),
        "cash_balance": money_text(p.cash_balance),
        "realized_pnl": money_text(p.realized_pnl),
        "default_scanner_baseline_id": p.default_scanner_baseline_id,
        "status": p.status.value,
    }


@router.get("/portfolios/{portfolio_id}")
def get_portfolio(portfolio_id: str):
    try:
        summary = _service().summary(portfolio_id)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    p = summary.portfolio
    return {
        "id": p.id,
        "name": p.name,
        "mode": p.mode.value,
        "status": p.status.value,
        "initial_cash": money_text(p.initial_cash),
        "cash_balance": money_text(p.cash_balance),
        "realized_pnl": money_text(p.realized_pnl),
        "positions_market_value": money_text(summary.positions_market_value),
        "unrealized_pnl": money_text(summary.unrealized_pnl),
        "total_equity": money_text(summary.total_equity),
        "total_return_pct": money_text(summary.total_return_pct),
        "open_position_count": summary.open_position_count,
        "default_scanner_baseline_id": p.default_scanner_baseline_id,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


@router.get("/portfolios/{portfolio_id}/positions")
def list_positions(portfolio_id: str, status: PositionStatus | None = None):
    try:
        positions = _service().list_positions(portfolio_id, status=status)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_position_payload(position) for position in positions]
