from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import PROJECT_ROOT
from app.jev.review_models import (
    BASELINE_WITH_JEV,
    JEV_USER_FEATURE_DISABLED,
)
from app.jev.review_service import JevManualReviewService
from app.jev.typesafe_catalog import (
    TypeSafeJevCatalog,
    TypeSafeJevCatalogError,
)
from app.jev.typesafe_evaluation_catalog import (
    TypeSafeJevEvaluationCatalog,
    TypeSafeJevEvaluationCatalogError,
)


router = APIRouter(
    prefix="/simulation/jev",
    tags=["simulation-jev"],
)

DEFAULT_SIMULATION_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "simulation" / "simulation.db"
)


def _db() -> Path:
    return Path(os.getenv("STOCKSCOPE_SIM_DB") or DEFAULT_SIMULATION_DB)


def _catalog() -> TypeSafeJevCatalog:
    return TypeSafeJevCatalog(_db())


def _evaluation_catalog() -> TypeSafeJevEvaluationCatalog:
    return TypeSafeJevEvaluationCatalog(_db())


@router.get("/status")
def jev_status():
    try:
        return _catalog().monitor_status()
    except TypeSafeJevCatalogError as error:
        if error.code in {
            "JEV_TYPESAFE_MIGRATION_REQUIRED",
            "JEV_TYPESAFE_SCHEMA_UNSUPPORTED",
        }:
            return {
                "available": False,
                "engine": "TYPESAFE_V2",
                "core_status": "NOT_READY",
                "trial_status": "TRIAL_NOT_FROZEN",
                "enabled": False,
                "network_enabled": False,
                "protocol_id": None,
                "protocol_status": None,
                "recruitment": {"total": 0, "callable": 0, "skipped": 0},
                "review_status": {
                    "pending": 0,
                    "valid": 0,
                    "error": 0,
                    "late": 0,
                    "interrupted": 0,
                },
                "disposition": {
                    "pass_through": 0,
                    "review_required": 0,
                    "abstain": 0,
                },
                "cost": {
                    "known_cost_usd": 0.0,
                    "unknown_cost_count": 0,
                    "reserved_exposure_usd": 0.0,
                },
                "code": error.code,
            }
        raise HTTPException(
            status_code=422,
            detail={"code": error.code, "message": error.message},
        ) from error


@router.get("/reviews")
def jev_reviews(
    capture_id: str = Query(min_length=1, max_length=200),
):
    try:
        items = _catalog().list_monitor_items(capture_id)
        statuses = {
            key: sum(
                1 for item in items
                if item["operational_status"] == key
            )
            for key in ("PENDING", "VALID", "ERROR", "LATE", "SKIPPED", "INTERRUPTED")
        }
        dispositions = {
            key: sum(
                1 for item in items
                if item["operational_status"] == "VALID"
                and item["disposition"] == key
            )
            for key in ("PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN")
        }
        return {
            "available": True,
            "engine": "TYPESAFE_V2",
            "capture_id": capture_id,
            "summary": {
                "total": len(items),
                "pending": statuses["PENDING"],
                "complete": statuses["VALID"],
                "review_required": dispositions["REVIEW_REQUIRED"],
                "abstain": dispositions["ABSTAIN"],
                "error": statuses["ERROR"],
                "late": statuses["LATE"],
                "skipped": statuses["SKIPPED"],
                "interrupted": statuses["INTERRUPTED"],
            },
            "items": items,
        }
    except TypeSafeJevCatalogError as error:
        if error.code in {
            "JEV_TYPESAFE_MIGRATION_REQUIRED",
            "JEV_TYPESAFE_SCHEMA_UNSUPPORTED",
        }:
            return {
                "available": False,
                "engine": "TYPESAFE_V2",
                "capture_id": capture_id,
                "summary": {
                    "total": 0,"pending": 0,"complete": 0,
                    "review_required": 0,"abstain": 0,
                    "error": 0,"late": 0,"skipped": 0,"interrupted": 0,
                },
                "items": [],
                "code": error.code,
            }
        raise HTTPException(
            status_code=422,
            detail={"code": error.code, "message": error.message},
        ) from error


@router.get("/evaluation/latest")
def latest_jev_evaluation():
    try:
        return {
            "available": True,
            "engine": "TYPESAFE_V2",
            "evaluation": _evaluation_catalog().latest_completed(),
        }
    except TypeSafeJevEvaluationCatalogError as error:
        if error.code in {
            "JEV_TYPESAFE_EVALUATION_MIGRATION_REQUIRED",
            "JEV_TYPESAFE_EVALUATION_SCHEMA_UNSUPPORTED",
        }:
            return {
                "available": False,
                "engine": "TYPESAFE_V2",
                "evaluation": None,
                "code": error.code,
            }
        raise HTTPException(
            status_code=422,
            detail={"code": error.code, "message": error.message},
        ) from error


@router.get("/evaluation-runs/{run_id}")
def get_jev_evaluation_run(run_id: str):
    try:
        return {
            "available": True,
            "engine": "TYPESAFE_V2",
            "evaluation": _evaluation_catalog().detail(run_id),
        }
    except TypeSafeJevEvaluationCatalogError as error:
        status = (
            404
            if error.code == "JEV_TYPESAFE_EVALUATION_RUN_NOT_FOUND"
            else 422
        )
        raise HTTPException(
            status_code=status,
            detail={"code": error.code, "message": error.message},
        ) from error



class JevManualReviewRequest(BaseModel):
    capture_id: str = Field(..., min_length=1, max_length=200)
    sample_index: int = Field(default=0, ge=0, le=100)
    review_epoch: int = Field(default=0, ge=0, le=1_000_000)


@router.get("/review-feature")
def jev_review_feature_status() -> dict[str, object]:
    return {
        "execution_mode": BASELINE_WITH_JEV,
        "feature_status": JEV_USER_FEATURE_DISABLED,
        "available": False,
        "reason": "FEATURE_NOT_ACTIVATED",
    }


@router.post("/reviews")
async def request_jev_manual_review(
    payload: JevManualReviewRequest,
) -> dict[str, object]:
    service = JevManualReviewService(_db())
    return await service.request_review(
        capture_id=payload.capture_id,
        sample_index=payload.sample_index,
        review_epoch=payload.review_epoch,
    )
