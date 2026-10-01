from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from app.core.config import PROJECT_ROOT
from app.core.stock_code import normalize_stock_code
from app.event_evidence import (
    EVENT_REFERENCE_AS_OF_MODE,
    EventEvidenceAsOfReader,
    EventEvidenceContractError,
)
from app.macro import (
    LocalMacroReader,
    LocalMarketImpactReader,
    build_macro_context,
    build_market_stock_impact,
    build_macro_event_reference_composition,
    build_sector_route,
)


router = APIRouter(prefix="/macro", tags=["macro"])
MACRO_REFERENCE_DIAGNOSTIC_API_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B16_REFERENCE_DIAGNOSTIC_API_V1"
)
MACRO_MARKET_STOCK_IMPACT_API_CONTRACT_VERSION = (
    "VN_NEXT6C_S32_MARKET_STOCK_IMPACT_API_V1"
)
MACRO_EVENT_REFERENCE_API_CONTRACT_VERSION = (
    "VN_NEXT6D_S3_MACRO_EVENT_REFERENCE_API_V1"
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


def _simulation_db_path() -> Path:
    raw = str(os.getenv("STOCKSCOPE_SIM_DB") or "").strip()
    if raw:
        return Path(raw)
    return (
        PROJECT_ROOT
        / "backend"
        / "runtime"
        / "simulation"
        / "simulation.db"
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


def _macro_event_invalid_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "MACRO_EVENT_REFERENCE_INVALID_REQUEST",
            "message": message,
        },
        headers={"Cache-Control": "no-store"},
    )


def _macro_event_context_unavailable(
    context: dict[str, Any],
) -> HTTPException:
    availability = context.get("availability") or {}
    reason = (
        context.get("reason")
        or availability.get("reader_reason")
        or "MACRO_CONTEXT_UNAVAILABLE"
    )
    return HTTPException(
        status_code=503,
        detail={
            "code": "MACRO_EVENT_CONTEXT_UNAVAILABLE",
            "reason": str(reason),
            "message": "Macro context for Macro/Event reference is not available.",
        },
        headers={"Cache-Control": "no-store"},
    )


def _macro_event_market_unavailable(reason: str | None) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "MACRO_EVENT_MARKET_STORE_UNAVAILABLE",
            "reason": str(reason or "MARKET_STORE_UNAVAILABLE"),
            "message": (
                "Market history store for Macro/Event reference is not available."
            ),
        },
        headers={"Cache-Control": "no-store"},
    )


_EVENT_REQUEST_ERROR_CODES = {
    "EVENT_EVIDENCE_ASOF_TIME_INVALID",
    "EVENT_EVIDENCE_ASOF_TIMEZONE_REQUIRED",
    "STOCK_CODE_INVALID",
    "EVENT_EVIDENCE_MARKET_INVALID",
    "EVENT_EVIDENCE_ASOF_LIMIT_INVALID",
}


@router.get("/event-reference")
def macro_event_reference(
    response: Response,
    market: str = Query(..., description="KOSPI or KOSDAQ."),
    ticker: str = Query(..., min_length=1, description="Stock code."),
    end_date: str = Query(
        ...,
        description="Required confirmed-EOD boundary in YYYY-MM-DD or YYYYMMDD.",
    ),
    cutoff: str = Query(
        ...,
        description="Required timezone-aware ISO-8601 decision cutoff.",
    ),
) -> dict[str, Any]:
    """Expose the bounded NEXT-6D Macro/Event reference composition.

    This endpoint is read-only and reference-only. Event Evidence degradation
    does not erase otherwise valid Macro/Impact context, while Macro/Market
    infrastructure failures remain fail-closed.
    """

    response.headers["Cache-Control"] = "no-store"

    try:
        market_key = str(market or "").strip().upper()
        if market_key not in {"KOSPI", "KOSDAQ"}:
            raise ValueError("market must be KOSPI or KOSDAQ.")
        normalized_ticker = normalize_stock_code(ticker)
        context = build_macro_context(
            reader=LocalMacroReader(_macro_db_path()),
            decision_cutoff=cutoff,
            usage="REFERENCE_SHADOW",
        )
    except ValueError as exc:
        raise _macro_event_invalid_request(str(exc)) from exc

    if context.get("status") == "UNAVAILABLE":
        raise _macro_event_context_unavailable(context)

    try:
        market_input = LocalMarketImpactReader(
            _market_db_path()
        ).read_pair_as_of(
            market=market_key,
            ticker=normalized_ticker,
            end_date=end_date,
        )
    except ValueError as exc:
        raise _macro_event_invalid_request(str(exc)) from exc

    if market_input.get("reason") in {
        "STORE_NOT_FOUND",
        "SCHEMA_UNAVAILABLE",
        "READ_FAILED",
    }:
        raise _macro_event_market_unavailable(market_input.get("reason"))

    try:
        impact = build_market_stock_impact(
            stock_rows=market_input.get("stock_rows") or [],
            market_rows=market_input.get("market_rows") or [],
            market=market_key,
            ticker=normalized_ticker,
            end_date=end_date,
            macro_context_id=context["context_id"],
            macro_context_hash=context["context_hash"],
            decision_cutoff=context["decision_cutoff"],
            sector_temporal_status=None,
        )
    except ValueError as exc:
        raise _macro_event_invalid_request(str(exc)) from exc

    event_product: dict[str, Any] | None = None
    event_source = {
        "reader_status": "AVAILABLE",
        "reason": None,
        "projection_mode": EVENT_REFERENCE_AS_OF_MODE,
    }
    try:
        event_product = EventEvidenceAsOfReader(
            _simulation_db_path()
        ).stock_reference_as_of(
            normalized_ticker,
            market_key,
            context["decision_cutoff"],
        )
    except EventEvidenceContractError as exc:
        if exc.code in _EVENT_REQUEST_ERROR_CODES:
            raise _macro_event_invalid_request(exc.message) from exc
        event_source = {
            "reader_status": "UNAVAILABLE",
            "reason": exc.code,
            "projection_mode": EVENT_REFERENCE_AS_OF_MODE,
        }

    try:
        composition = build_macro_event_reference_composition(
            macro_context=context,
            impact=impact,
            sector_route=build_sector_route(),
            event_product=event_product,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MACRO_EVENT_REFERENCE_CONTRACT_ERROR",
                "message": str(exc),
            },
            headers={"Cache-Control": "no-store"},
        ) from exc

    impact_projection = composition["impact"]
    sector_projection = composition["sector"]
    event_reference = composition["event_reference"]

    return {
        "contract_version": MACRO_EVENT_REFERENCE_API_CONTRACT_VERSION,
        "status": composition["status"],
        "decision_cutoff": composition["decision_cutoff"],
        "scope": composition["scope"],
        "composition_id": composition["composition_id"],
        "composition_hash": composition["composition_hash"],
        "macro": {
            "status": composition["macro"]["status"],
            "usage_mode": composition["macro"]["usage_mode"],
        },
        "impact": {
            "status": impact_projection["status"],
            "reason": impact_projection["reason"],
            "window": impact_projection["window"],
            "market_return_pct": impact_projection["market_return_pct"],
            "stock_return_pct": impact_projection["stock_return_pct"],
            "stock_vs_market_pctp": impact_projection[
                "stock_vs_market_pctp"
            ],
        },
        "sector": {
            "historical_sector_status": sector_projection[
                "historical_sector_status"
            ],
            "historical_impact_mode": sector_projection[
                "historical_impact_mode"
            ],
            "prospective_sector_status": sector_projection[
                "prospective_sector_status"
            ],
        },
        "event_source": event_source,
        "event_reference": {
            "status": event_reference["status"],
            "source_status": event_reference["source_status"],
            "source_reference_count": event_reference[
                "source_reference_count"
            ],
            "eligible_reference_count": event_reference[
                "eligible_reference_count"
            ],
            "latest_as_of": event_reference["latest_as_of"],
            "historical_completeness_proven": event_reference[
                "historical_completeness_proven"
            ],
            "items": event_reference["items"],
        },
        "value_validation": composition["value_validation"],
        "prediction": composition["prediction"],
        "identity_policy": composition["identity_policy"],
        "limitations": composition["limitations"],
        "governance": composition["governance"],
        "production_decision_approved": False,
    }
