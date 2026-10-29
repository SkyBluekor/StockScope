from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import PROJECT_ROOT
from app.jev.review_models import (
    BASELINE_WITH_JEV,
    JEV_USER_FEATURE_DISABLED,
)
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_shadow_s7 import load_frozen_candidates
from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
from app.jev.scanner_v4_readiness_s7_5 import diagnose_candidate as diagnose_v4_candidate
from app.jev.scanner_eligibility_s8 import diagnose_candidate as diagnose_s8_candidate
from app.jev.scanner_outbound_gate_live_03 import diagnose_outbound_candidate
from app.horizon import HorizonPolicyError, resolve_horizon_context
from app.jev.review_service import JevManualReviewService
from app.jev import synthetic_live_04_demo as live04_demo
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


@router.get("/local-readiness")
def jev_local_readiness(
    capture_id: str = Query(min_length=1, max_length=200),
    sample_index: int = Query(ge=0, le=499),
) -> dict[str, object]:
    """LIVE-02 read-only diagnostics of one immutable Scanner sample.

    Never authorizes TypeSafe transmission, initializes a provider, or changes
    the canonical Scanner capture. User-facing review POST stays disabled.
    """
    try:
        pairs = load_frozen_candidates(
            _db(), capture_id=capture_id, limit=500,
        )
        match = next(
            ((capture, sample) for capture, sample in pairs
             if sample["sample_index"] == sample_index),
            None,
        )
        if match is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "JEV_LIVE02_SAMPLE_NOT_FOUND",
                        "message": "저장된 COMPLETE 캡처에서 해당 후보를 찾지 못했습니다."},
            )
        capture, sample = match
        v4 = diagnose_v4_candidate(capture, sample)
        s8 = diagnose_s8_candidate(capture, sample)
        integrity = assess_frozen_candidate(capture, sample)
        try:
            horizon_context = resolve_horizon_context(
                capture["horizon_intent"], policy_version=capture["horizon_policy_version"],
            )
            horizon_status = horizon_context.support_status
            horizon_reason = horizon_context.reason_code
        except HorizonPolicyError:
            # A malformed historical record cannot create review eligibility.
            horizon_status = "UNSUPPORTED"
            horizon_reason = "HORIZON_INTENT_INVALID"
    except DecisionReviewContractError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": "저장된 후보의 검토 준비도 확인 불가"},
        ) from exc

    local = v4["local_v4_status"]
    if v4["category"] == "REFERENCE_ONLY":
        status = "NOT_ENTRY_CANDIDATE"
        local_readiness = "NOT_APPLICABLE"
    elif local == "LOCAL_V4_PROJECTABLE":
        status = "SOURCE_RIGHTS_HOLD"
        local_readiness = "LOCAL_READY"
    elif local == "SKIPPED_LOCAL":
        status = "LOCAL_ONLY"
        local_readiness = "LOCAL_ONLY"
    else:
        status = "NEEDS_EVIDENCE"
        local_readiness = "NEEDS_EVIDENCE"

    return {
        "version": "JEV_LIVE_02_LOCAL_READINESS_V1",
        "capture_id": capture["id"],
        "sample_index": int(sample["sample_index"]),
        "identity": {
            "snapshot_hash": sample["snapshot_hash"],
            "signal_date": sample["signal_date"],
            "market": sample["market"],
            "ticker": sample["ticker"],
            "rank": sample["rank"],
            "strategy": sample["strategy"],
            "action": sample["action"],
        },
        "status": status,
        "local_readiness": local_readiness,
        "local_v4_status": local,
        "v4_semantic_status": v4["v4_local_semantic_status"],
        "input_contract": {
            "horizon_intent": capture["horizon_intent"],
            "horizon_policy_version": capture["horizon_policy_version"],
            "horizon_support_status": horizon_status,
            "horizon_reason_code": horizon_reason,
            "strategy_identity_status": integrity["strategy"]["status"],
            "original_strategy_identity": (
                "CAPTURED_ORIGINAL"
                if (
                    integrity["strategy"]["status"] == "PASS"
                    and integrity["policy"]["status"] == "PASS"
                    and integrity["engine"]["status"] == "PASS"
                )
                else "LEGACY_DERIVED_NOT_ORIGINAL"
                if integrity["strategy"]["status"] == "LEGACY_DERIVED"
                else "NOT_VERIFIED"
            ),
            "capture_created_at": capture["created_at"],
            "capture_started_at": capture["started_at"],
            "capture_completed_at": capture["completed_at"],
            "source_first_published_at": None,
            "source_publication_evidence": "UNVERIFIED",
        },
        "integrity_reason_codes": v4["integrity_reason_codes"],
        "baseline_checks": {
            name: {
                "status": integrity[name]["status"],
                "code": integrity[name]["code"],
            }
            for name in ("rank", "strategy", "policy", "engine", "risk", "dates")
        },
        "lineage_analysis_status": v4["lineage_analysis_status"],
        "v4_outbound_lineage_status": s8["v4_outbound_lineage_status"],
        "source_origin_status": s8["source_origin_status"],
        "source_revision_status": s8["source_revision_status"],
        "publication_time_status": s8["publication_time_status"],
        "rights_status": s8["rights_status"],
        "transmission_decision": s8["transmission_decision"],
        "reason_codes": s8["reason_codes"],
        "model_review_executed": False,
        "provider_eligible": False,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


@router.get("/outbound-preflight")
def jev_outbound_preflight(
    capture_id: str = Query(min_length=1, max_length=200),
    sample_index: int = Query(ge=0, le=499),
) -> dict[str, object]:
    """LIVE-03: read-only external disclosure gate, always HOLD for real data.

    No caller-provided rights or approval fields.  No provider or market
    store can be instantiated from this route.
    """
    try:
        pairs = load_frozen_candidates(_db(), capture_id=capture_id, limit=500)
        match = next(
            ((capture, sample) for capture, sample in pairs
             if sample["sample_index"] == sample_index),
            None,
        )
        if match is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "JEV_LIVE03_SAMPLE_NOT_FOUND",
                        "message": "동결된 COMPLETE 후보를 찾지 못했습니다."},
            )
        capture, sample = match
        diagnostic = diagnose_outbound_candidate(capture, sample)
    except DecisionReviewContractError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": "실제 시장 자료의 전송 자격 검사 불가"},
        ) from exc
    return {
        "capture_id": capture["id"],
        "sample_index": int(sample["sample_index"]),
        "snapshot_hash": sample["snapshot_hash"],
        "market": sample["market"],
        "ticker": sample["ticker"],
        **diagnostic,
    }


@router.get("/synthetic-demo/status")
def jev_synthetic_demo_status(request: Request) -> dict[str, object]:
    """Only a locally enabled, authored-synthetic development demonstration."""
    client = request.client.host if request.client else None
    if not live04_demo.demo_enabled(client, request.url.hostname):
        return {
            "enabled": False, "status": "DISABLED",
            "synthetic_only": True, "actual_provider_calls": 0,
        }
    try:
        return live04_demo.status()
    except (OSError, ValueError):
        raise HTTPException(status_code=409, detail={
            "code": "JEV04_DEMO_STATE_INVALID",
            "message": "격리된 합성 체험 작업 상태를 확인할 수 없습니다.",
        })


@router.post("/synthetic-demo/start", status_code=202)
def jev_synthetic_demo_start(request: Request, tasks: BackgroundTasks) -> dict[str, object]:
    """Explicit click only; no candidate data, credentials or real TypeSafe HTTP."""
    client = request.client.host if request.client else None
    if not live04_demo.demo_enabled(client, request.url.hostname):
        raise HTTPException(status_code=403, detail={
            "code": "JEV04_SYNTHETIC_DEMO_DISABLED",
            "message": "합성 체험은 로컬 개발 서버에서만 사용할 수 있습니다.",
        })
    if request.headers.get("X-StockScope-Synthetic-Demo") != "confirmed":
        raise HTTPException(status_code=403, detail={
            "code": "JEV04_DEMO_EXPLICIT_ACTION_REQUIRED",
            "message": "합성 체험 요청 확인이 필요합니다.",
        })
    try:
        result = live04_demo.start()
    except (OSError, ValueError):
        raise HTTPException(status_code=409, detail={
            "code": "JEV04_DEMO_SINGLE_SHOT_UNAVAILABLE",
            "message": "이전 합성 체험을 다시 실행할 수 없습니다. 자동 재시도하지 않습니다.",
        })
    if not result["reused"]:
        tasks.add_task(live04_demo.run_mock, result["job_id"])
    return result


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
