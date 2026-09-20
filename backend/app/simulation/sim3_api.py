from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .sim1_models import money_text
from .sim1_service import SimulationPortfolioService, default_paths
from .sim1_store import BaselineRegistry, SimulationRepository
from .sim3_market_provider import HistoricalMarketStoreProvider
from .sim3_playback_service import MarketPlaybackService, SimulationPlaybackError

router = APIRouter(prefix="/simulation", tags=["simulation-playback"])


class CreateSessionRequest(BaseModel):
    start_date: date
    end_date: date | None = None


class AdvanceRequest(BaseModel):
    trading_days: int = Field(gt=0, le=1000)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _service() -> MarketPlaybackService:
    root = _project_root()
    default_db, baseline_dir = default_paths(root)
    repository = SimulationRepository(Path(os.getenv("STOCKSCOPE_SIM_DB", str(default_db))))
    portfolio_service = SimulationPortfolioService(repository, BaselineRegistry(baseline_dir))
    service = MarketPlaybackService(repository, portfolio_service, HistoricalMarketStoreProvider())
    service.initialize()
    return service


def _error(exc: SimulationPlaybackError) -> None:
    status = 404 if exc.code in {"SIM_PORTFOLIO_NOT_FOUND", "SIM_SESSION_NOT_FOUND"} else 409
    if exc.code in {"SIM_INVALID_TRADING_DATE", "SIM_INVALID_DATE_RANGE", "SIM_INVALID_MODE_FOR_DATE_ENGINE", "SIM_INVALID_ADVANCE_DAYS"}:
        status = 400
    raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc


def _result(result):
    return {
        "session_id": result.session.id,
        "previous_date": result.previous_date,
        "current_date": result.current_date,
        "updated_positions": result.updated_positions,
        "missing_positions": result.missing_positions,
        "cash_balance": money_text(result.summary.portfolio.cash_balance),
        "positions_market_value": money_text(result.summary.positions_market_value),
        "total_equity": money_text(result.summary.total_equity),
        "unrealized_pnl": money_text(result.summary.unrealized_pnl),
        "realized_pnl": money_text(result.summary.portfolio.realized_pnl),
    }


@router.post("/portfolios/{portfolio_id}/sessions")
def create_session(portfolio_id: str, request: CreateSessionRequest):
    try:
        session = _service().create_session(portfolio_id, start_date=request.start_date, end_date=request.end_date)
    except SimulationPlaybackError as exc:
        _error(exc)
    return {
        "session_id": session.id,
        "portfolio_id": session.portfolio_id,
        "start_date": session.start_date,
        "end_date": session.end_date,
        "current_date": session.current_date,
        "status": session.status.value,
    }


@router.get("/portfolios/{portfolio_id}/session")
def get_session(portfolio_id: str):
    try:
        session = _service().get_active_session(portfolio_id)
    except SimulationPlaybackError as exc:
        _error(exc)
    return {
        "session_id": session.id,
        "portfolio_id": session.portfolio_id,
        "start_date": session.start_date,
        "end_date": session.end_date,
        "current_date": session.current_date,
        "status": session.status.value,
    }


@router.post("/portfolios/{portfolio_id}/next-day")
def next_day(portfolio_id: str):
    try:
        return _result(_service().next_day(portfolio_id))
    except SimulationPlaybackError as exc:
        _error(exc)


@router.post("/portfolios/{portfolio_id}/advance")
def advance(portfolio_id: str, request: AdvanceRequest):
    try:
        results = _service().advance(portfolio_id, request.trading_days)
    except SimulationPlaybackError as exc:
        _error(exc)
    return {"steps": [_result(result) for result in results]}
