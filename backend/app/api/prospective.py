from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import PROJECT_ROOT
from app.prospective.rank_comparison import compare_capture_candidates
from app.prospective import (
    ProspectiveCatalogError,
    ProspectiveEvaluationError,
    ProspectiveService,
)


router = APIRouter(
    prefix="/simulation/prospective",
    tags=["simulation-prospective"],
)

DEFAULT_SIMULATION_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "simulation" / "simulation.db"
)
DEFAULT_MARKET_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
)


class ProtocolRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=200)
    name: str = Field(default="Prospective 평가", min_length=1, max_length=160)
    market_scope: Literal["ALL", "KOSPI", "KOSDAQ"] = "ALL"
    strategy: str | None = Field(default=None, max_length=100)
    development_start: str | None = None
    development_end: str | None = None
    holdout_start: str | None = None
    holdout_end: str | None = None
    purge_trading_days: int = Field(default=20, ge=1, le=120)
    max_holding_days: int = Field(default=20, ge=1, le=120)
    round_trip_cost_pct: float = Field(default=0.0, ge=0, le=5)
    fee_pct: float = Field(default=0.0, ge=0, le=5)
    tax_pct: float = Field(default=0.0, ge=0, le=5)
    slippage_pct: float = Field(default=0.0, ge=0, le=5)
    execution_mode: Literal["PRODUCTION_POLICY", "OBSERVATION_ONLY"] = (
        "PRODUCTION_POLICY"
    )


class EvaluationRunRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=200)
    protocol_id: str = Field(min_length=1, max_length=200)


def _service() -> ProspectiveService:
    simulation_db = Path(
        os.getenv("STOCKSCOPE_SIM_DB")
        or DEFAULT_SIMULATION_DB
    )
    market_db = Path(
        (os.getenv("STOCKSCOPE_MARKET_STORE_DB") or os.getenv("STOCKSCOPE_MARKET_DB"))
        or DEFAULT_MARKET_DB
    )
    return ProspectiveService(simulation_db, market_db)


def _raise(error: Exception) -> None:
    code = getattr(error, "code", "PROSPECTIVE_ERROR")
    message = getattr(error, "message", str(error))
    if code in {
        "PROSPECTIVE_PROTOCOL_NOT_FOUND",
        "PROSPECTIVE_EVALUATION_RUN_NOT_FOUND",
        "PROSPECTIVE_MARKET_STORE_NOT_FOUND",
    }:
        status = 404
    elif code in {
        "PROSPECTIVE_MIGRATION_REQUIRED",
        "PROSPECTIVE_SCHEMA_UNSUPPORTED",
        "PROSPECTIVE_EVALUATION_ALREADY_RUNNING",
        "PROSPECTIVE_EXIT_POLICY_CHANGED",
    }:
        status = 409
    else:
        status = 422
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
    ) from error


@router.get("/status")
def prospective_status():
    try:
        return _service().catalog.status_summary()
    except ProspectiveCatalogError as error:
        _raise(error)


@router.get("/captures")
def list_prospective_captures(
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return _service().catalog.list_captures(limit=limit)
    except ProspectiveCatalogError as error:
        _raise(error)


@router.get("/captures/{capture_id}/candidate-comparison")
def compare_scanner_candidates(
    capture_id: str,
    left_sample_index: int = Query(ge=0),
    right_sample_index: int = Query(ge=0),
):
    """Explain recorded Scanner order; never modify candidate rankings."""
    result = compare_capture_candidates(
        db_path=_service().catalog.db_path,
        capture_id=capture_id,
        left_sample_index=left_sample_index,
        right_sample_index=right_sample_index,
    )
    if result["status"] in {"INVALID_COMPARISON_PAIR", "SAMPLE_NOT_FOUND"}:
        raise HTTPException(status_code=422, detail={
            "code": result["status"], "message": "유효한 서로 다른 두 후보를 선택하세요.",
        })
    if result["status"] == "CAPTURE_NOT_FOUND":
        raise HTTPException(status_code=404, detail={
            "code": result["status"], "message": "Scanner 캡처를 찾지 못했습니다.",
        })
    return result


@router.get("/protocols")
def list_prospective_protocols():
    try:
        return _service().catalog.list_protocols()
    except ProspectiveCatalogError as error:
        _raise(error)


@router.post("/protocols", status_code=201)
def create_prospective_protocol(request: ProtocolRequest):
    try:
        return _service().create_protocol(
            client_request_id=request.client_request_id,
            name=request.name,
            market_scope=request.market_scope,
            strategy=request.strategy,
            development_start=request.development_start,
            development_end=request.development_end,
            holdout_start=request.holdout_start,
            holdout_end=request.holdout_end,
            purge_trading_days=request.purge_trading_days,
            max_holding_days=request.max_holding_days,
            round_trip_cost_pct=request.round_trip_cost_pct,
            fee_pct=request.fee_pct,
            tax_pct=request.tax_pct,
            slippage_pct=request.slippage_pct,
            execution_mode=request.execution_mode,
        )
    except ProspectiveCatalogError as error:
        _raise(error)


@router.get("/evaluation-runs")
def list_prospective_evaluation_runs(
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        return _service().catalog.list_evaluation_runs(limit=limit)
    except ProspectiveCatalogError as error:
        _raise(error)


@router.post("/evaluation-runs", status_code=201)
def create_prospective_evaluation_run(request: EvaluationRunRequest):
    try:
        return _service().create_evaluation_run(
            protocol_id=request.protocol_id,
            client_request_id=request.client_request_id,
        )
    except ProspectiveCatalogError as error:
        _raise(error)


@router.post("/evaluation-runs/{run_id}/execute")
def execute_prospective_evaluation_run(run_id: str):
    try:
        return _service().execute_evaluation_run(run_id)
    except (ProspectiveCatalogError, ProspectiveEvaluationError) as error:
        _raise(error)


@router.post("/evaluation-runs/{run_id}/cancel")
def cancel_prospective_evaluation_run(run_id: str):
    try:
        return _service().cancel_evaluation_run(run_id)
    except ProspectiveCatalogError as error:
        _raise(error)


@router.get("/evaluation-runs/{run_id}")
def get_prospective_evaluation_run(run_id: str):
    try:
        return _service().evaluation_detail(run_id)
    except ProspectiveCatalogError as error:
        _raise(error)
