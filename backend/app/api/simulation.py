from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.simulation.sim1_api import create_portfolio, get_portfolio, list_positions
from app.simulation.sim1_models import money_text
from app.simulation.sim1_service import default_paths
from app.simulation.sim1_store import SimulationRepository
from app.simulation.sim2_api import buy, sell
from app.simulation.sim3_api import advance, create_session, get_session, next_day
from app.simulation.sim3_market_provider import HistoricalMarketStoreProvider
from app.simulation.sim3_store import SimulationPlaybackStore
from app.simulation.validation_period import HistoricalValidationPeriodResolver, ValidationPeriodError
from app.simulation.validation_catalog import HistoricalValidationCatalog, ValidationCatalogError

router = APIRouter()

# Legacy SIM.1~SIM.3 HTTP contract remains available for compatibility and
# preserved data. The new UI no longer auto-resumes one of these portfolios.
router.add_api_route("/simulation/portfolios", create_portfolio, methods=["POST"], status_code=201, tags=["simulation"])
router.add_api_route("/simulation/portfolios/{portfolio_id}", get_portfolio, methods=["GET"], tags=["simulation"])
router.add_api_route("/simulation/portfolios/{portfolio_id}/positions", list_positions, methods=["GET"], tags=["simulation"])
router.add_api_route("/simulation/portfolios/{portfolio_id}/buy", buy, methods=["POST"], tags=["simulation-trading"])
router.add_api_route("/simulation/portfolios/{portfolio_id}/sell", sell, methods=["POST"], tags=["simulation-trading"])
router.add_api_route("/simulation/portfolios/{portfolio_id}/sessions", create_session, methods=["POST"], tags=["simulation-playback"])
router.add_api_route("/simulation/portfolios/{portfolio_id}/session", get_session, methods=["GET"], tags=["simulation-playback"])
router.add_api_route("/simulation/portfolios/{portfolio_id}/next-day", next_day, methods=["POST"], tags=["simulation-playback"])
router.add_api_route("/simulation/portfolios/{portfolio_id}/advance", advance, methods=["POST"], tags=["simulation-playback"])


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
        raise HTTPException(status_code=404, detail={"code": "SIM_PORTFOLIO_NOT_FOUND", "message": f"Portfolio not found: {portfolio_id}"})
    playback_store = SimulationPlaybackStore(repository)
    rows = []
    for position in repository.list_positions(portfolio_id):
        mark = playback_store.get_mark(position.id)
        rows.append({
            "position_id": position.id,
            "price_status": mark.price_status.value if mark else None,
            "valuation_stale": mark.valuation_stale if mark else False,
            "mark_date": mark.mark_date if mark else None,
            "source_bar_date": mark.source_bar_date if mark else None,
        })
    return rows


@router.get("/simulation/portfolios/{portfolio_id}/quote/{stock_code}", tags=["simulation-playback"])
def simulation_quote(portfolio_id: str, stock_code: str, market: str = Query(default="KRX", min_length=1, max_length=24)):
    repository = _repository()
    if repository.get_portfolio(portfolio_id) is None:
        raise HTTPException(status_code=404, detail={"code": "SIM_PORTFOLIO_NOT_FOUND", "message": f"Portfolio not found: {portfolio_id}"})
    session = SimulationPlaybackStore(repository).active_session(portfolio_id)
    if session is None:
        raise HTTPException(status_code=409, detail={"code": "SIM_SESSION_NOT_FOUND", "message": "Historical session is not active"})
    code = stock_code.strip()
    if not code:
        raise HTTPException(status_code=400, detail={"code": "SIM_STOCK_CODE_REQUIRED", "message": "stock_code is required"})
    bar = HistoricalMarketStoreProvider().get_bar(market.strip().upper(), code, session.current_date)
    if bar is None:
        raise HTTPException(status_code=404, detail={"code": "SIM_MARKET_DATA_MISSING", "message": f"No stored market bar for {code} on {session.current_date.isoformat()}"})
    return {"stock_code": code, "market": bar.market, "trading_date": bar.trading_date.isoformat(), "close": money_text(bar.close)}


# --- SIM.VAL.0: period preview / legacy visibility -------------------------

def _validation_resolver() -> HistoricalValidationPeriodResolver:
    provider = HistoricalMarketStoreProvider()
    return HistoricalValidationPeriodResolver(provider.store)


def _validation_catalog() -> HistoricalValidationCatalog:
    catalog = HistoricalValidationCatalog(_repository().db_path)
    catalog.initialize()
    return catalog


def _validation_catalog_error(error: ValidationCatalogError) -> None:
    status = 409 if error.code == "SIM_VALIDATION_RUNNING" else 422
    raise HTTPException(status_code=status, detail={"code": error.code, "message": error.message})


def _validation_error(error: ValidationPeriodError) -> None:
    raise HTTPException(status_code=422, detail={"code": error.code, "message": error.message})


@router.get("/simulation/validation-periods/preview", tags=["simulation-validation"])
def validation_period_preview(
    preset: str | None = Query(default=None),
    start_month: str | None = Query(default=None),
    end_month: str | None = Query(default=None),
    market_scope: str = Query(default="ALL"),
):
    try:
        return _validation_resolver().preview(
            preset=preset, start_month=start_month, end_month=end_month, market_scope=market_scope
        )
    except ValidationPeriodError as error:
        _validation_error(error)


class ValidationPeriodRequest(BaseModel):
    preset: str | None = None
    start_month: str | None = None
    end_month: str | None = None
    market_scope: str = "ALL"


@router.post("/simulation/validation-periods/validate", tags=["simulation-validation"])
def validate_validation_period(request: ValidationPeriodRequest):
    payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
    try:
        return _validation_resolver().require_valid(**payload)
    except ValidationPeriodError as error:
        _validation_error(error)


class ValidationDraftRequest(BaseModel):
    name: str
    preset: str | None = None
    start_month: str | None = None
    end_month: str | None = None
    market_scope: str = "ALL"


@router.post("/simulation/validations", status_code=201, tags=["simulation-validation"])
def create_validation_draft(request: ValidationDraftRequest):
    payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
    period_input = {
        "preset": payload.get("preset"),
        "start_month": payload.get("start_month"),
        "end_month": payload.get("end_month"),
        "market_scope": payload.get("market_scope") or "ALL",
    }
    try:
        resolved = _validation_resolver().require_valid(**period_input)
        draft = _validation_catalog().create_draft(
            name=payload.get("name") or "",
            market_scope=resolved["market_scope"],
            requested_period_type=(resolved.get("preset") or "custom"),
            requested_start_month=resolved["requested_start_month"],
            requested_end_month=resolved["requested_end_month"],
            resolved_start_date=resolved["resolved_start_date"],
            resolved_end_date=resolved["resolved_end_date"],
            trading_day_count=resolved["trading_days"],
        )
        return draft.to_dict()
    except ValidationPeriodError as error:
        _validation_error(error)
    except ValidationCatalogError as error:
        _validation_catalog_error(error)


@router.get("/simulation/validations", tags=["simulation-validation"])
def list_validation_drafts():
    return [item.to_dict() for item in _validation_catalog().list()]


@router.get("/simulation/validations/{validation_id}", tags=["simulation-validation"])
def get_validation_draft(validation_id: str):
    item = _validation_catalog().get(validation_id)
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "SIM_VALIDATION_NOT_FOUND", "message": "저장된 검증을 찾을 수 없습니다."})
    return item.to_dict()


@router.delete("/simulation/validations/{validation_id}", tags=["simulation-validation"])
def delete_validation_draft(validation_id: str):
    try:
        deleted = _validation_catalog().delete(validation_id)
    except ValidationCatalogError as error:
        _validation_catalog_error(error)
    if not deleted:
        raise HTTPException(status_code=404, detail={"code": "SIM_VALIDATION_NOT_FOUND", "message": "저장된 검증을 찾을 수 없습니다."})
    return {"deleted": True, "id": validation_id}


@router.get("/simulation/legacy-validations", tags=["simulation-validation"])
def list_legacy_validations():
    """Expose preserved SIM.1~SIM.3 portfolios as read-only legacy records.

    They are intentionally not auto-resumed because their execution semantics
    differ from the upcoming Historical Validation engine.
    """
    repository = _repository()
    with repository.connect() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.mode, p.status, p.initial_cash, p.created_at, p.updated_at,
                   (SELECT COUNT(*) FROM simulation_position pos WHERE pos.portfolio_id=p.id) AS position_count,
                   (SELECT COUNT(*) FROM simulation_trade tr WHERE tr.portfolio_id=p.id) AS trade_count,
                   (SELECT s.start_date FROM simulation_session s WHERE s.portfolio_id=p.id ORDER BY s.created_at DESC LIMIT 1) AS start_date,
                   (SELECT s.end_date FROM simulation_session s WHERE s.portfolio_id=p.id ORDER BY s.created_at DESC LIMIT 1) AS end_date,
                   (SELECT s.current_date FROM simulation_session s WHERE s.portfolio_id=p.id ORDER BY s.created_at DESC LIMIT 1) AS current_date,
                   (SELECT s.status FROM simulation_session s WHERE s.portfolio_id=p.id ORDER BY s.created_at DESC LIMIT 1) AS session_status
            FROM simulation_portfolio p
            WHERE p.mode='HISTORICAL'
            ORDER BY p.updated_at DESC, p.created_at DESC
            """
        ).fetchall()
    return [
        {
            "portfolio_id": row["id"],
            "name": row["name"],
            "legacy_status": "LEGACY_SAVED",
            "portfolio_status": row["status"],
            "session_status": row["session_status"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "current_date": row["current_date"],
            "initial_cash": row["initial_cash"],
            "position_count": int(row["position_count"] or 0),
            "trade_count": int(row["trade_count"] or 0),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


@router.delete("/simulation/legacy-validations/{portfolio_id}", tags=["simulation-validation"])
def delete_legacy_validation(portfolio_id: str):
    repository = _repository()
    with repository.connect() as conn:
        portfolio = conn.execute(
            "SELECT id,name,mode FROM simulation_portfolio WHERE id=?", (portfolio_id,)
        ).fetchone()
        if portfolio is None or portfolio["mode"] != "HISTORICAL":
            raise HTTPException(status_code=404, detail={"code": "SIM_LEGACY_NOT_FOUND", "message": "이전 Simulation 기록을 찾을 수 없습니다."})
        counts = {
            "session": conn.execute("SELECT COUNT(*) c FROM simulation_session WHERE portfolio_id=?", (portfolio_id,)).fetchone()["c"],
            "position": conn.execute("SELECT COUNT(*) c FROM simulation_position WHERE portfolio_id=?", (portfolio_id,)).fetchone()["c"],
            "order": conn.execute("SELECT COUNT(*) c FROM simulation_order WHERE portfolio_id=?", (portfolio_id,)).fetchone()["c"],
            "trade": conn.execute("SELECT COUNT(*) c FROM simulation_trade WHERE portfolio_id=?", (portfolio_id,)).fetchone()["c"],
        }
        if any(int(value or 0) > 0 for value in counts.values()):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SIM_LEGACY_HAS_DEPENDENCIES",
                    "message": "포지션·주문·거래·세션 기록이 연결된 이전 Simulation은 안전을 위해 바로 삭제할 수 없습니다.",
                    "counts": counts,
                },
            )
        conn.execute("DELETE FROM simulation_portfolio WHERE id=?", (portfolio_id,))
    return {"deleted": True, "portfolio_id": portfolio_id}


# --- TRACK.1.9: provenance-safe item APIs ---------------------------------
from app.tracking.api import (  # noqa: E402
    close_tracked_recommendation,
    delete_tracked_recommendation,
    create_manual_tracked_item,
    create_scanner_tracked_item,
    create_tracked_recommendation,
    list_tracked_recommendations,
    preview_manual_tracked_item,
    refresh_active_recommendations,
    refresh_tracked_recommendation,
)

router.add_api_route("/tracking/items/from-scanner", create_scanner_tracked_item, methods=["POST"], status_code=201, tags=["tracking"])
router.add_api_route("/tracking/items/manual/preview", preview_manual_tracked_item, methods=["GET"], tags=["tracking"])
router.add_api_route("/tracking/items/manual", create_manual_tracked_item, methods=["POST"], status_code=201, tags=["tracking"])
router.add_api_route("/tracking/items", list_tracked_recommendations, methods=["GET"], tags=["tracking"])
router.add_api_route("/tracking/items/refresh-active", refresh_active_recommendations, methods=["POST"], tags=["tracking"])
router.add_api_route("/tracking/items/{recommendation_id}/close", close_tracked_recommendation, methods=["POST"], tags=["tracking"])
router.add_api_route("/tracking/items/{recommendation_id}", delete_tracked_recommendation, methods=["DELETE"], tags=["tracking"])
router.add_api_route("/tracking/items/{recommendation_id}/refresh", refresh_tracked_recommendation, methods=["POST"], tags=["tracking"])

# One-release compatibility aliases for the Phase 1/2 frontend/API contract.
router.add_api_route("/tracking/recommendations", create_tracked_recommendation, methods=["POST"], status_code=201, tags=["tracking-legacy"])
router.add_api_route("/tracking/recommendations", list_tracked_recommendations, methods=["GET"], tags=["tracking-legacy"])
router.add_api_route("/tracking/recommendations/refresh", refresh_active_recommendations, methods=["POST"], tags=["tracking-legacy"])
router.add_api_route("/tracking/recommendations/{recommendation_id}/close", close_tracked_recommendation, methods=["POST"], tags=["tracking-legacy"])
router.add_api_route("/tracking/recommendations/{recommendation_id}/refresh", refresh_tracked_recommendation, methods=["POST"], tags=["tracking-legacy"])
