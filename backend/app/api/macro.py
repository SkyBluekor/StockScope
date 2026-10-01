from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from app.core.config import PROJECT_ROOT
from app.macro import LocalMacroReader, build_macro_context


router = APIRouter(prefix="/macro", tags=["macro"])
MACRO_REFERENCE_DIAGNOSTIC_API_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B16_REFERENCE_DIAGNOSTIC_API_V1"
)


def _macro_db_path() -> Path:
    raw = str(os.getenv("STOCKSCOPE_MACRO_DB") or "").strip()
    if raw:
        return Path(raw)
    return PROJECT_ROOT / "backend" / "runtime" / "macro" / "macro.db"


def _default_cutoff() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rate_spike_summary(context: dict[str, Any]) -> dict[str, Any]:
    assessment = context.get("shock_assessment") or {}
    for component in assessment.get("components") or []:
        if component.get("shock_type") == "RATE_SPIKE":
            return {
                "state": component.get("state"),
                "reason": component.get("reason"),
            }
    return {
        "state": "UNKNOWN",
        "reason": "RATE_SPIKE_COMPONENT_MISSING",
    }


def _unavailable_detail(context: dict[str, Any]) -> dict[str, Any]:
    availability = context.get("availability") or {}
    reason = (
        context.get("reason")
        or availability.get("reader_reason")
        or "MACRO_REFERENCE_UNAVAILABLE"
    )
    return {
        "code": "MACRO_REFERENCE_UNAVAILABLE",
        "reason": str(reason),
        "message": "Macro reference diagnostic is not available.",
    }


@router.get("/reference-diagnostic")
def reference_diagnostic(
    response: Response,
    cutoff: str | None = Query(
        default=None,
        description=(
            "Timezone-aware ISO-8601 cutoff. "
            "When omitted, the current UTC time is used."
        ),
    ),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    decision_cutoff = cutoff or _default_cutoff()

    try:
        context = build_macro_context(
            reader=LocalMacroReader(_macro_db_path()),
            decision_cutoff=decision_cutoff,
            usage="REFERENCE_SHADOW",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MACRO_REFERENCE_INVALID_REQUEST",
                "message": str(exc),
            },
        ) from exc

    if context.get("status") == "UNAVAILABLE":
        raise HTTPException(
            status_code=503,
            detail=_unavailable_detail(context),
            headers={"Cache-Control": "no-store"},
        )

    diagnostic = context["reference_diagnostic"]
    governance = diagnostic["governance"]
    return {
        "contract_version": MACRO_REFERENCE_DIAGNOSTIC_API_CONTRACT_VERSION,
        "status": diagnostic["status"],
        "decision_cutoff": context["decision_cutoff"],
        "macro_context": {
            "contract_version": context["contract_version"],
            "context_id": context["context_id"],
            "context_hash": context["context_hash"],
            "status": context["status"],
            "limitations": context["limitations"],
        },
        "reference_diagnostic": diagnostic,
        "reference_adequacy": {
            "state": governance["reference_adequacy"],
            "numeric_policy_defined": governance["numeric_policy_defined"],
            "minimum_prior_observations": governance[
                "minimum_prior_observations"
            ],
            "recommended_support": governance["recommended_support"],
        },
        "rate_spike": _rate_spike_summary(context),
        "production_decision_approved": bool(
            context["production_decision_approved"]
        ),
    }
