from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.simulation.sim1_api import (
    create_portfolio,
    get_portfolio,
    list_positions,
)
from app.simulation.sim1_service import default_paths
from app.simulation.sim1_store import SimulationRepository
from app.simulation.sim2_api import buy, sell
from app.simulation.sim3_api import advance, create_session, get_session, next_day
from app.simulation.sim3_store import SimulationPlaybackStore

# Register the stable public Simulation HTTP contract explicitly instead of
# nesting the SIM.1/SIM.2/SIM.3 module-level routers.  This avoids route loss
# when test/import ordering reloads those modules during a combined suite.
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
