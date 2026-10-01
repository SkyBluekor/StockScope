from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.macro.identity import content_hash


MACRO_EVENT_REFERENCE_COMPOSITION_CONTRACT_VERSION = (
    "VN_NEXT6D_S1_MACRO_EVENT_REFERENCE_COMPOSITION_V1"
)

_ALLOWED_EVENT_QUALITY = {"USABLE", "LIMITED"}
_ACTIVE_EVENT_REVISIONS = {"ORIGINAL", "CORRECTED"}
_ALLOWED_PRODUCT_SCOPES = {"RESEARCH_ONLY", "REFERENCE_CONTEXT"}


def _aware_utc(value: str, field: str) -> tuple[datetime, str]:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"{field} must be a timezone-aware ISO-8601 datetime."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"{field} must be a timezone-aware ISO-8601 datetime."
        )
    utc = parsed.astimezone(timezone.utc)
    return utc, utc.isoformat()


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = str(payload.get(field) or "").strip()
    if not value:
        raise ValueError(f"{field} is required.")
    return value


def _hash_text(payload: dict[str, Any], field: str) -> str:
    value = _required_text(payload, field).lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{field} must be a 64-character hexadecimal hash.")
    return value


def _bounded_sector_route(sector_route: dict[str, Any] | None) -> dict[str, Any]:
    route = sector_route or {}
    return {
        "contract_version": str(route.get("contract_version") or "").strip()
        or None,
        "historical_sector_status": str(
            route.get("historical_sector_status") or "UNAVAILABLE"
        ),
        "historical_impact_mode": str(
            route.get("historical_impact_mode") or "MARKET_STOCK_ONLY"
        ),
        "prospective_sector_status": str(
            route.get("prospective_sector_status") or "NOT_STARTED"
        ),
        "production_decision_approved": False,
    }


def _bounded_value_validation(event_product: dict[str, Any] | None) -> dict[str, Any]:
    raw = (event_product or {}).get("value_validation") or {}
    status = str(raw.get("status") or "NOT_EVALUATED")
    product_scope = str(raw.get("product_scope") or "RESEARCH_ONLY")
    if product_scope not in _ALLOWED_PRODUCT_SCOPES:
        raise ValueError(
            "Event Evidence product_scope must remain RESEARCH_ONLY or "
            "REFERENCE_CONTEXT."
        )
    return {
        "status": status,
        "product_scope": product_scope,
    }


def _bounded_prediction(event_product: dict[str, Any] | None) -> dict[str, Any]:
    raw = (event_product or {}).get("prediction") or {}
    status = str(raw.get("status") or "NOT_VALIDATED")
    if status != "NOT_VALIDATED":
        raise ValueError(
            "NEXT-6D-S1 does not compose validated prediction output."
        )
    if any(
        raw.get(field) is not None
        for field in ("direction", "horizon_sessions", "probability")
    ):
        raise ValueError(
            "NEXT-6D-S1 prediction fields must remain empty."
        )
    return {
        "status": "NOT_VALIDATED",
        "direction": None,
        "horizon_sessions": None,
        "probability": None,
    }


def _project_event_reference(
    event_product: dict[str, Any] | None,
    *,
    cutoff_dt: datetime,
    cutoff: str,
) -> dict[str, Any]:
    if event_product is None:
        return {
            "status": "EVENT_SOURCE_UNAVAILABLE",
            "source_status": "UNAVAILABLE",
            "source_reference_count": 0,
            "eligible_reference_count": 0,
            "excluded_after_cutoff_count": 0,
            "excluded_revision_count": 0,
            "excluded_synthetic_count": 0,
            "excluded_quality_count": 0,
            "latest_as_of": None,
            "items": [],
            "historical_completeness_proven": False,
        }

    evidence = event_product.get("event_evidence") or {}
    source_status = str(
        evidence.get("status") or "NO_VALIDATED_EVIDENCE"
    )
    source_count = int(evidence.get("reference_count") or 0)
    raw_items = evidence.get("items") or []
    if not isinstance(raw_items, list):
        raise ValueError("event_evidence.items must be a list.")

    eligible: list[dict[str, Any]] = []
    excluded_after_cutoff = 0
    excluded_revision = 0
    excluded_synthetic = 0
    excluded_quality = 0

    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ValueError(
                f"event_evidence.items[{index}] must be an object."
            )

        quality = str(raw.get("quality_state") or "").strip().upper()
        if quality not in _ALLOWED_EVENT_QUALITY:
            excluded_quality += 1
            continue

        revision = str(raw.get("revision_state") or "").strip().upper()
        if revision not in _ACTIVE_EVENT_REVISIONS:
            excluded_revision += 1
            continue

        source_kinds = sorted(
            {
                str(kind).strip()
                for kind in (raw.get("source_kinds") or [])
                if str(kind).strip()
            }
        )
        if not source_kinds or "TEST_SYNTHETIC" in source_kinds:
            excluded_synthetic += 1
            continue

        available_dt, available_at = _aware_utc(
            str(raw.get("available_at") or ""),
            f"event_evidence.items[{index}].available_at",
        )
        evidence_dt, evidence_as_of = _aware_utc(
            str(raw.get("evidence_as_of") or ""),
            f"event_evidence.items[{index}].evidence_as_of",
        )
        assessment_dt, assessment_as_of = _aware_utc(
            str(raw.get("assessment_as_of") or ""),
            f"event_evidence.items[{index}].assessment_as_of",
        )

        if any(
            value > cutoff_dt
            for value in (available_dt, evidence_dt, assessment_dt)
        ):
            excluded_after_cutoff += 1
            continue

        eligible.append(
            {
                "event_type": str(raw.get("event_type") or "").strip()
                or "UNKNOWN",
                "relation_type": str(raw.get("relation_type") or "").strip()
                or "UNKNOWN",
                "relevance_state": str(
                    raw.get("relevance_state") or ""
                ).strip()
                or "UNKNOWN",
                "quality_state": quality,
                "source_kinds": source_kinds,
                "available_at": available_at,
                "evidence_as_of": evidence_as_of,
                "revision_state": revision,
                "assessment_as_of": assessment_as_of,
            }
        )

    eligible.sort(
        key=lambda item: (
            item["assessment_as_of"],
            item["available_at"],
            item["event_type"],
            item["relation_type"],
            item["source_kinds"],
        )
    )

    if eligible:
        status = (
            "REFERENCE_AVAILABLE"
            if any(item["quality_state"] == "USABLE" for item in eligible)
            else "REFERENCE_LIMITED"
        )
        latest_as_of = max(item["assessment_as_of"] for item in eligible)
    elif source_status == "EVIDENCE_BLOCKED":
        status = "EVIDENCE_BLOCKED"
        latest_as_of = None
    else:
        status = "NO_ELIGIBLE_REFERENCE"
        latest_as_of = None

    return {
        "status": status,
        "source_status": source_status,
        "source_reference_count": source_count,
        "eligible_reference_count": len(eligible),
        "excluded_after_cutoff_count": excluded_after_cutoff,
        "excluded_revision_count": excluded_revision,
        "excluded_synthetic_count": excluded_synthetic,
        "excluded_quality_count": excluded_quality,
        "latest_as_of": latest_as_of,
        "items": eligible,
        "historical_completeness_proven": False,
        "decision_cutoff": cutoff,
    }


def build_macro_event_reference_composition(
    *,
    macro_context: dict[str, Any],
    impact: dict[str, Any],
    sector_route: dict[str, Any] | None,
    event_product: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compose bounded Macro, Market/Stock Impact and P6 Event references.

    The function is pure: it performs no database access, provider call, network
    request, evidence mutation, strategy scoring, or policy decision. It validates
    identities and preserves the current P6 product projection as reference-only.
    """

    context_id = _required_text(macro_context, "context_id")
    context_hash = _hash_text(macro_context, "context_hash")
    cutoff_dt, cutoff = _aware_utc(
        _required_text(macro_context, "decision_cutoff"),
        "macro_context.decision_cutoff",
    )
    macro_status = str(macro_context.get("status") or "UNAVAILABLE")

    context_ref = impact.get("context_ref") or {}
    if str(context_ref.get("macro_context_id") or "") != context_id:
        raise ValueError("Impact macro_context_id does not match MacroContext.")
    if str(context_ref.get("macro_context_hash") or "").lower() != context_hash:
        raise ValueError(
            "Impact macro_context_hash does not match MacroContext."
        )
    _, impact_cutoff = _aware_utc(
        str(context_ref.get("decision_cutoff") or ""),
        "impact.context_ref.decision_cutoff",
    )
    if impact_cutoff != cutoff:
        raise ValueError(
            "Impact decision_cutoff does not match MacroContext."
        )

    impact_id = _required_text(impact, "impact_id")
    impact_hash = _hash_text(impact, "impact_hash")
    impact_status = str(impact.get("status") or "UNAVAILABLE")
    scope = impact.get("scope") or {}
    market = str(scope.get("market") or "").strip().upper()
    ticker = str(scope.get("ticker") or "").strip().upper()
    if not market or not ticker:
        raise ValueError("Impact market and ticker scope are required.")

    if event_product is not None:
        event_market = str(event_product.get("market") or "").strip().upper()
        event_code = str(event_product.get("code") or "").strip().upper()
        if event_market != market or event_code != ticker:
            raise ValueError(
                "Event Evidence market/code does not match Impact scope."
            )

    event_reference = _project_event_reference(
        event_product,
        cutoff_dt=cutoff_dt,
        cutoff=cutoff,
    )
    value_validation = _bounded_value_validation(event_product)
    prediction = _bounded_prediction(event_product)
    sector = _bounded_sector_route(sector_route)

    macro_available = macro_status != "UNAVAILABLE"
    impact_available = impact_status != "UNAVAILABLE"
    has_event_reference = event_reference["eligible_reference_count"] > 0

    if not macro_available or not impact_available:
        status = "UNAVAILABLE"
    elif (
        macro_status in {"COMPLETE_REFERENCE", "COMPLETE_HISTORICAL"}
        and impact_status == "AVAILABLE"
        and has_event_reference
    ):
        status = "AVAILABLE"
    else:
        status = "PARTIAL"

    limitations = [
        "REFERENCE_COMPOSITION_ONLY",
        "NO_CAUSAL_ATTRIBUTION",
        "NO_MACRO_EXPOSURE_RELATION_CREATED",
        "NO_PREDICTION",
        "CURRENT_P6_PRODUCT_PROJECTION_NOT_HISTORICALLY_COMPLETE",
    ]
    if not has_event_reference:
        limitations.append("EVENT_REFERENCE_NOT_AVAILABLE_AT_CUTOFF")
    if sector["historical_sector_status"] != "AVAILABLE":
        limitations.append("HISTORICAL_SECTOR_NOT_AVAILABLE")

    bounded_macro = {
        "context_id": context_id,
        "context_hash": context_hash,
        "status": macro_status,
        "usage_mode": macro_context.get("usage_mode"),
    }
    bounded_impact = {
        "impact_id": impact_id,
        "impact_hash": impact_hash,
        "status": impact_status,
        "reason": impact.get("reason"),
        "window": {
            "start_date": (impact.get("window") or {}).get("start_date"),
            "end_date": (impact.get("window") or {}).get("end_date"),
        },
        "market_return_pct": (impact.get("market") or {}).get("return_pct"),
        "stock_return_pct": (impact.get("stock") or {}).get("return_pct"),
        "stock_vs_market_pctp": (impact.get("relative") or {}).get(
            "stock_vs_market_pctp"
        ),
    }

    governance = {
        "claim_scope": "REFERENCE_COMPOSITION_ONLY",
        "causal_attribution": False,
        "macro_exposure_relation_created": False,
        "prediction_approved": False,
        "strategy_input_approved": False,
        "scanner_input_approved": False,
        "risk_gate_input_approved": False,
        "holdings_plan_input_approved": False,
        "production_decision_approved": False,
        "network_access": False,
        "database_write": False,
    }

    # Identity intentionally pins only references eligible at the frozen cutoff.
    # Diagnostic counts about later/current product rows may change as the P6
    # projection evolves, but they cannot rewrite a past composition identity.
    event_identity = {
        "status": event_reference["status"],
        "eligible_reference_count": event_reference[
            "eligible_reference_count"
        ],
        "latest_as_of": event_reference["latest_as_of"],
        "items": event_reference["items"],
        "historical_completeness_proven": False,
        "decision_cutoff": cutoff,
    }
    identity_payload = {
        "contract_version": MACRO_EVENT_REFERENCE_COMPOSITION_CONTRACT_VERSION,
        "status": status,
        "decision_cutoff": cutoff,
        "scope": {
            "market": market,
            "ticker": ticker,
        },
        "macro": bounded_macro,
        "impact": bounded_impact,
        "sector": sector,
        "event_reference": event_identity,
        "value_validation": value_validation,
        "prediction": prediction,
        "limitations": sorted(set(limitations)),
        "governance": governance,
    }
    composition_hash = content_hash(identity_payload)
    return {
        "contract_version": MACRO_EVENT_REFERENCE_COMPOSITION_CONTRACT_VERSION,
        "composition_id": f"MEVCOMP-{composition_hash[:16]}",
        "composition_hash": composition_hash,
        "status": status,
        "decision_cutoff": cutoff,
        "scope": {
            "market": market,
            "ticker": ticker,
        },
        "macro": bounded_macro,
        "impact": bounded_impact,
        "sector": sector,
        "event_reference": event_reference,
        "value_validation": value_validation,
        "prediction": prediction,
        "identity_policy": "CUTOFF_ELIGIBLE_REFERENCES_ONLY",
        "limitations": sorted(set(limitations)),
        "governance": governance,
    }
