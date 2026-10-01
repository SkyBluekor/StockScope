from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from app.core.config import PROJECT_ROOT
from app.macro import (
    LocalMacroReader,
    LocalMarketImpactReader,
    build_macro_context,
    build_market_stock_impact,
    build_sector_route,
)


router = APIRouter(prefix="/macro", tags=["macro"])
MACRO_REFERENCE_DIAGNOSTIC_API_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B16_REFERENCE_DIAGNOSTIC_API_V1"
)
MACRO_MARKET_STOCK_IMPACT_API_CONTRACT_VERSION = (
    "VN_NEXT6C_S32_MARKET_STOCK_IMPACT_API_V1"
)


def _macro_db_path() -> Path:
    raw = str(os.getenv("STOCKSCOPE_MACRO_DB") or "").strip()
    if raw:
        return Path(raw)
    return PROJECT_ROOT / "backend" / "runtime" / "macro" / "macro.db"


def _market_db_path() -> Path:
    raw = str(os.getenv("STOCKSCOPE_MARKET_STORE_DB") or "").strip()
    if raw:
        return Path(raw)
    return (
        PROJECT_ROOT
        / "backend"
        / "runtime"
        / "market_history"
        / "market_history.db"
    )


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


def _macro_impact_unavailable_detail(
    context: dict[str, Any],
) -> dict[str, Any]:
    availability = context.get("availability") or {}
    reason = (
        context.get("reason")
        or availability.get("reader_reason")
        or "MACRO_CONTEXT_UNAVAILABLE"
    )
    return {
        "code": "MACRO_IMPACT_CONTEXT_UNAVAILABLE",
        "reason": str(reason),
        "message": "Macro context for Market/Stock impact is not available.",
    }


def _market_impact_store_unavailable_detail(
    reason: str | None,
) -> dict[str, Any]:
    return {
        "code": "MARKET_IMPACT_STORE_UNAVAILABLE",
        "reason": str(reason or "MARKET_STORE_UNAVAILABLE"),
        "message": "Market history store for Market/Stock impact is not available.",
    }


@router.get("/market-stock-impact")
def market_stock_impact(
    response: Response,
    market: str = Query(..., description="KOSPI or KOSDAQ."),
    ticker: str = Query(..., min_length=1, description="Stock code."),
    end_date: str = Query(
        ...,
        description="Required confirmed-EOD boundary in YYYY-MM-DD or YYYYMMDD.",
    ),
    cutoff: str | None = Query(
        default=None,
        description=(
            "Timezone-aware ISO-8601 MacroContext cutoff. "
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
                "code": "MACRO_IMPACT_INVALID_REQUEST",
                "message": str(exc),
            },
            headers={"Cache-Control": "no-store"},
        ) from exc

    if context.get("status") == "UNAVAILABLE":
        raise HTTPException(
            status_code=503,
            detail=_macro_impact_unavailable_detail(context),
            headers={"Cache-Control": "no-store"},
        )

    try:
        market_input = LocalMarketImpactReader(
            _market_db_path()
        ).read_pair_as_of(
            market=market,
            ticker=ticker,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MACRO_IMPACT_INVALID_REQUEST",
                "message": str(exc),
            },
            headers={"Cache-Control": "no-store"},
        ) from exc

    if market_input.get("reason") in {
        "STORE_NOT_FOUND",
        "SCHEMA_UNAVAILABLE",
        "READ_FAILED",
    }:
        raise HTTPException(
            status_code=503,
            detail=_market_impact_store_unavailable_detail(
                market_input.get("reason")
            ),
            headers={"Cache-Control": "no-store"},
        )

    try:
        impact = build_market_stock_impact(
            stock_rows=market_input.get("stock_rows") or [],
            market_rows=market_input.get("market_rows") or [],
            market=market,
            ticker=ticker,
            end_date=end_date,
            macro_context_id=context["context_id"],
            macro_context_hash=context["context_hash"],
            decision_cutoff=context["decision_cutoff"],
            sector_temporal_status=None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MACRO_IMPACT_INVALID_REQUEST",
                "message": str(exc),
            },
            headers={"Cache-Control": "no-store"},
        ) from exc

    return {
        "contract_version": MACRO_MARKET_STOCK_IMPACT_API_CONTRACT_VERSION,
        "status": impact["status"],
        "macro_context": {
            "contract_version": context["contract_version"],
            "context_id": context["context_id"],
            "context_hash": context["context_hash"],
            "decision_cutoff": context["decision_cutoff"],
            "status": context["status"],
            "limitations": context["limitations"],
        },
        "impact": impact,
        "sector_route": build_sector_route(),
        "production_decision_approved": False,
    }
