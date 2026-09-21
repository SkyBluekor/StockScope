from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.simulation.sim1_api import create_portfolio, get_portfolio, list_positions
from app.simulation.sim1_models import money_text
from app.simulation.sim1_service import default_paths
from app.simulation.sim1_store import SimulationRepository
from app.simulation.sim2_api import buy, sell
from app.simulation.sim3_api import advance, create_session, get_session, next_day
from app.simulation.sim3_market_provider import HistoricalMarketStoreProvider
from app.simulation.sim3_store import SimulationPlaybackStore

# Keep the public Simulation HTTP contract explicit and stable.  SIM.1/SIM.2/
# SIM.3 routers are intentionally not nested here because combined test/import
# ordering can reload those module-level routers.
router = APIRouter()

router.add_api_route(
    "/simulation/portfolios",
    create_portfolio,
    methods=["POST"],
    status_code=201,
    tags=["simulation"],
)
router.add_api_route(
    "/simulation/portfolios/{portfolio_id}",
    get_portfolio,
    methods=["GET"],
    tags=["simulation"],
)
router.add_api_route(
    "/simulation/portfolios/{portfolio_id}/positions",
    list_positions,
    methods=["GET"],
    tags=["simulation"],
)
router.add_api_route(
    "/simulation/portfolios/{portfolio_id}/buy",
    buy,
    methods=["POST"],
    tags=["simulation-trading"],
)
router.add_api_route(
    "/simulation/portfolios/{portfolio_id}/sell",
    sell,
    methods=["POST"],
    tags=["simulation-trading"],
)
router.add_api_route(
    "/simulation/portfolios/{portfolio_id}/sessions",
    create_session,
    methods=["POST"],
    tags=["simulation-playback"],
)
router.add_api_route(
    "/simulation/portfolios/{portfolio_id}/session",
    get_session,
    methods=["GET"],
    tags=["simulation-playback"],
)
router.add_api_route(
    "/simulation/portfolios/{portfolio_id}/next-day",
    next_day,
    methods=["POST"],
    tags=["simulation-playback"],
)
router.add_api_route(
    "/simulation/portfolios/{portfolio_id}/advance",
    advance,
    methods=["POST"],
    tags=["simulation-playback"],
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _repository() -> SimulationRepository:
    root = _project_root()
    default_db, _ = default_paths(root)
    repository = SimulationRepository(Path(os.getenv("STOCKSCOPE_SIM_DB", str(default_db))))
    repository.initialize()
    return repository


@router.get("/simulation/portfolios/{portfolio_id}/position-marks", tags=["simulation-playback"])
def position_marks(portfolio_id: str):
    repository = _repository()
    if repository.get_portfolio(portfolio_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SIM_PORTFOLIO_NOT_FOUND", "message": f"Portfolio not found: {portfolio_id}"},
        )

    playback_store = SimulationPlaybackStore(repository)
    rows = []
    for position in repository.list_positions(portfolio_id):
        mark = playback_store.get_mark(position.id)
        rows.append(
            {
                "position_id": position.id,
                "price_status": mark.price_status.value if mark else None,
                "valuation_stale": mark.valuation_stale if mark else False,
                "mark_date": mark.mark_date if mark else None,
                "source_bar_date": mark.source_bar_date if mark else None,
            }
        )
    return rows


@router.get("/simulation/portfolios/{portfolio_id}/quote/{stock_code}", tags=["simulation-playback"])
def simulation_quote(
    portfolio_id: str,
    stock_code: str,
    market: str = Query(default="KRX", min_length=1, max_length=24),
):
    """Return the confirmed close for the portfolio's current simulation day.

    This endpoint is deliberately local/offline: it reads HistoricalMarketStore
    through the SIM.3 provider and never performs a KRX/KIS network request.
    """
    repository = _repository()
    if repository.get_portfolio(portfolio_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SIM_PORTFOLIO_NOT_FOUND", "message": f"Portfolio not found: {portfolio_id}"},
        )

    session = SimulationPlaybackStore(repository).active_session(portfolio_id)
    if session is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "SIM_SESSION_NOT_FOUND", "message": "Historical session is not active"},
        )

    code = stock_code.strip()
    if not code:
        raise HTTPException(
            status_code=400,
            detail={"code": "SIM_STOCK_CODE_REQUIRED", "message": "stock_code is required"},
        )

    bar = HistoricalMarketStoreProvider().get_bar(market.strip().upper(), code, session.current_date)
    if bar is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SIM_MARKET_DATA_MISSING",
                "message": f"No stored market bar for {code} on {session.current_date.isoformat()}",
            },
        )

    return {
        "stock_code": code,
        "market": bar.market,
        "trading_date": bar.trading_date.isoformat(),
        "close": money_text(bar.close),
    }

# TRACK.1: recommendation tracking lives in its own domain/DB, but is registered
# through this already-mounted API router so the hotfix does not need to modify
# app.main or other Scanner production wiring.
from app.tracking.api import (  # noqa: E402
    close_tracked_recommendation,
    create_tracked_recommendation,
    list_tracked_recommendations,
)

router.add_api_route(
    "/tracking/recommendations",
    create_tracked_recommendation,
    methods=["POST"],
    status_code=201,
    tags=["tracking"],
)
router.add_api_route(
    "/tracking/recommendations",
    list_tracked_recommendations,
    methods=["GET"],
    tags=["tracking"],
)
router.add_api_route(
    "/tracking/recommendations/{recommendation_id}/close",
    close_tracked_recommendation,
    methods=["POST"],
    tags=["tracking"],
)
