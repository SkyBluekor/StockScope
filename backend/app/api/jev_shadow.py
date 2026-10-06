from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.core.config import PROJECT_ROOT
from app.jev import (
    JevCatalog,
    JevCatalogError,
    JevEvaluationCatalog,
    JevEvaluationCatalogError,
    trial_readiness,
)


router = APIRouter(
    prefix="/simulation/jev-shadow",
    tags=["simulation-jev-shadow"],
)

DEFAULT_SIMULATION_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "simulation" / "simulation.db"
)

_STATUS_KEYS = (
    "PENDING",
    "VALID",
    "ERROR",
    "LATE",
    "SKIPPED",
    "INTERRUPTED",
)
_DECISION_KEYS = (
    "PASS_THROUGH",
    "REVIEW_REQUIRED",
    "ABSTAIN",
)


def _catalog() -> JevCatalog:
    simulation_db = Path(
        os.getenv("STOCKSCOPE_SIM_DB")
        or DEFAULT_SIMULATION_DB
    )
    return JevCatalog(simulation_db)


def _evaluation_catalog() -> JevEvaluationCatalog:
    simulation_db = Path(
        os.getenv("STOCKSCOPE_SIM_DB")
        or DEFAULT_SIMULATION_DB
    )
    return JevEvaluationCatalog(simulation_db)


def _unavailable(error: JevCatalogError) -> dict[str, object]:
    readiness = trial_readiness()
    return {
        "available": False,
        "enabled": False,
        "ready_for_activation": bool(readiness.get("ready")),
        "trial_status": readiness.get("status"),
        "protocol_status": None,
        "network_enabled": False,
        "status_counts": {key: 0 for key in _STATUS_KEYS},
        "decision_counts": {key: 0 for key in _DECISION_KEYS},
        "code": error.code,
    }


def _raise(error: JevCatalogError) -> None:
    raise HTTPException(
        status_code=422,
        detail={
            "code": error.code,
            "message": error.message,
        },
    ) from error


@router.get("/status")
def jev_shadow_status():
    catalog = _catalog()
    try:
        summary = catalog.status_summary()
        activation = summary.get("activation")
        enabled = bool(
            isinstance(activation, dict)
            and activation.get("enabled")
        )
        protocol_status = None
        network_enabled = False
        if isinstance(activation, dict):
            network_enabled = bool(
                enabled and activation.get("allow_network")
            )
            protocol_id = activation.get("protocol_id")
            if protocol_id:
                protocol = catalog.get_protocol(str(protocol_id))
                if protocol is not None:
                    protocol_status = str(protocol.get("status") or "") or None

        status_counts = {
            key: int(summary["status_counts"].get(key, 0))
            for key in _STATUS_KEYS
        }
        decision_counts = {
            key: int(summary["decision_counts"].get(key, 0))
            for key in _DECISION_KEYS
        }
        readiness = trial_readiness()
        return {
            "available": True,
            "enabled": enabled,
            "ready_for_activation": bool(readiness.get("ready")),
            "trial_status": readiness.get("status"),
            "protocol_status": protocol_status,
            "network_enabled": network_enabled,
            "status_counts": status_counts,
            "decision_counts": decision_counts,
        }
    except JevCatalogError as error:
        if error.code in {
            "JEV_MIGRATION_REQUIRED",
            "JEV_SCHEMA_UNSUPPORTED",
        }:
            return _unavailable(error)
        _raise(error)


@router.get("/reviews")
def list_jev_shadow_reviews(
    capture_id: str = Query(min_length=1, max_length=200),
):
    catalog = _catalog()
    try:
        items = catalog.list_monitor_reviews(capture_id)
        status_counts = {
            key: sum(1 for item in items if item["status"] == key)
            for key in _STATUS_KEYS
        }
        decision_counts = {
            key: sum(
                1
                for item in items
                if item["status"] == "VALID"
                and item["decision"] == key
            )
            for key in _DECISION_KEYS
        }
        return {
            "available": True,
            "capture_id": capture_id,
            "summary": {
                "total": len(items),
                "pending": status_counts["PENDING"],
                "complete": status_counts["VALID"],
                "review_required": decision_counts["REVIEW_REQUIRED"],
                "abstain": decision_counts["ABSTAIN"],
                "error": status_counts["ERROR"],
                "late": status_counts["LATE"],
                "skipped": status_counts["SKIPPED"],
                "interrupted": status_counts["INTERRUPTED"],
            },
            "items": items,
        }
    except JevCatalogError as error:
        if error.code in {
            "JEV_MIGRATION_REQUIRED",
            "JEV_SCHEMA_UNSUPPORTED",
        }:
            return {
                "available": False,
                "capture_id": capture_id,
                "summary": {
                    "total": 0,
                    "pending": 0,
                    "complete": 0,
                    "review_required": 0,
                    "abstain": 0,
                    "error": 0,
                    "late": 0,
                    "skipped": 0,
                    "interrupted": 0,
                },
                "items": [],
                "code": error.code,
            }
        _raise(error)



@router.get("/evaluation/latest")
def latest_jev_reviewer_evaluation():
    catalog = _evaluation_catalog()
    try:
        latest = catalog.latest_completed()
        return {
            "available": True,
            "evaluation": latest,
        }
    except JevEvaluationCatalogError as error:
        if error.code in {
            "JEV_EVALUATION_MIGRATION_REQUIRED",
            "JEV_EVALUATION_SCHEMA_UNSUPPORTED",
        }:
            return {
                "available": False,
                "evaluation": None,
                "code": error.code,
            }
        raise HTTPException(
            status_code=422,
            detail={
                "code": error.code,
                "message": error.message,
            },
        ) from error


@router.get("/evaluation-runs/{run_id}")
def get_jev_reviewer_evaluation_run(run_id: str):
    catalog = _evaluation_catalog()
    try:
        return {
            "available": True,
            "evaluation": catalog.detail(run_id),
        }
    except JevEvaluationCatalogError as error:
        status = (
            404
            if error.code == "JEV_EVALUATION_RUN_NOT_FOUND"
            else 422
        )
        raise HTTPException(
            status_code=status,
            detail={
                "code": error.code,
                "message": error.message,
            },
        ) from error
