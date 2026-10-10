"""Read-only JEV-ACT1-S1 activation assessment.

This module evaluates frozen *local* contracts and documented evidence gaps.
It never loads provider credentials, constructs an HTTP client or changes activation.
An offline PASS for the protocol is not a Canary PASS.
"""
from __future__ import annotations

from typing import Any, Callable

from app.jev.typesafe_canary_v4 import (
    TypeSafeCanaryV4Error,
    load_frozen_canary_v4_protocol,
)

READINESS_VERSION = "JEV_ACT1_S1_READINESS_V1"


def _check(code: str, status: str, explanation: str) -> dict[str, str]:
    return {"code": code, "status": status, "explanation": explanation}


def assess_jev_act1_readiness(
    *,
    audit: dict[str, Any] | None = None,
    protocol_loader: Callable[[], dict[str, Any]] = load_frozen_canary_v4_protocol,
) -> dict[str, Any]:
    """Pure offline gate. A missing evidence input must fail closed."""
    checks: list[dict[str, str]] = []
    try:
        artifact = protocol_loader()
        spec = artifact["spec"]
        if (
            artifact.get("status") != "FROZEN_BEFORE_REAL_CALLS"
            or spec.get("actual_trial_activation_allowed") is not False
            or spec.get("production_feature_activation_allowed") is not False
            or spec.get("execution_requires_separate_authorization") is not True
        ):
            raise ValueError("V4_OFFLINE_FREEZE_STATUS_INVALID")
    except (TypeSafeCanaryV4Error, ValueError, KeyError, TypeError) as exc:
        spec = None
        reason = (
            exc.code if isinstance(exc, TypeSafeCanaryV4Error)
            else "V4_OFFLINE_PROTOCOL_INVALID"
        )
        checks.append(_check("V4_PROTOCOL", "BLOCK", reason))
    else:
        checks.append(_check(
            "V4_PROTOCOL", "PASS",
            "Frozen protocol canonical hash, fixture/route contract and local identity verified; no external execution.",
        ))
    if spec is not None:
        budget = spec.get("budget")
        if not isinstance(budget, dict):
            checks.append(_check("V4_PLANNED_LIMITS", "BLOCK", "BUDGET_MISSING"))
        else:
            try:
                calls = int(spec["planned_systemone_calls"])
                reservation = float(budget["per_call_reservation_usd"])
                ceiling = float(budget["reserved_exposure_ceiling_usd"])
                project = float(budget["project_absolute_ceiling_usd"])
                configured = float(budget["max_reserved_exposure_usd"])
                retries = int(spec["retry_count"])
                acceptable = (
                    calls > 0 and retries == 0
                    and configured <= ceiling <= 0.05
                    and configured <= project <= 0.25
                    and abs(calls * reservation - configured) < 1e-9
                )
            except (TypeError, ValueError, KeyError):
                acceptable = False
            checks.append(_check(
                "V4_PLANNED_LIMITS", "PASS" if acceptable else "BLOCK",
                "Frozen synthetic Canary attempt/reservation ceilings validated."
                if acceptable else "V4_PLANNED_LIMITS_INVALID",
            ))
    else:
        checks.append(_check("V4_PLANNED_LIMITS", "BLOCK", "V4_PROTOCOL_UNAVAILABLE"))

    # S1 deliberately cannot assert that a future provider experiment passed:
    # no production-approved response evidence is supplied or read here.
    checks.extend([
        _check(
            "V4_ACTUAL_CANARY", "HOLD",
            "No independently validated actual V4 Canary selection/validation PASS evidence is available to S1.",
        ),
        _check(
            "V4_THRESHOLD_MODEL_BINDING", "HOLD",
            "Final validated threshold and concrete provider response model are not bound for product use.",
        ),
        _check(
            "LIVE_PRICING_ACCOUNT_TERMS", "HOLD",
            "Frozen pricing/reservation figures are not a verified current account price or spending authorization.",
        ),
        _check(
            "SOURCE_TRANSMISSION_APPROVAL", "HOLD",
            "Real stock semantic source transmission and user opt-in have not been separately approved.",
        ),
        _check(
            "PRODUCT_REVIEW_ACTIVATION", "HOLD",
            "Backend feature remains DISABLED_VALIDATION_PENDING; no real provider is installed by this diagnostic.",
        ),
    ])

    sample_total = int((audit or {}).get("total_samples") or 0)
    eligible = int((audit or {}).get("provider_eligible") or 0)
    legacy = (audit or {}).get("legacy_local_inspection")
    if not isinstance(legacy, dict):
        legacy = {}
    legacy_total = int(legacy.get("total") or 0)
    legacy_inspected = int(legacy.get("inspectable") or 0)
    legacy_residual = int(legacy.get("residual_observed") or 0)
    if audit is None:
        scope_reason = "RUN_LOCAL_READONLY_AUDIT"
    elif legacy_total:
        scope_reason = "LEGACY_HORIZON_REQUIRES_SEPARATE_POLICY_VALIDATION"
    else:
        scope_reason = "NO_LEGACY_SCOPE_OBSERVED"
    checks.append(_check(
        "HORIZON_SCOPE_COMPATIBILITY", "HOLD", scope_reason,
    ))
    if audit is None:
        utility = "RUN_LOCAL_READONLY_AUDIT"
    elif sample_total == 0:
        utility = "NO_PROSPECTIVE_SAMPLES"
    elif eligible:
        utility = "ELIGIBLE_SAMPLES_OBSERVED_UTILITY_UNPROVEN"
    elif legacy_total and legacy_inspected == 0:
        utility = "LEGACY_LOCAL_INSPECTION_INVALID_OR_MISSING"
    elif legacy_residual:
        utility = "LEGACY_RESIDUAL_OBSERVED_PROVIDER_NOT_AUTHORIZED"
    elif legacy_total:
        utility = "LEGACY_LOCAL_REVIEW_ONLY_NO_PROVIDER_ELIGIBLE"
    else:
        utility = "NO_PROVIDER_ELIGIBLE_SAMPLES_OBSERVED"
    checks.append(_check("PRODUCTION_REACHABILITY", "HOLD", utility))

    verdict = (
        "BLOCK" if any(x["status"] == "BLOCK" for x in checks)
        else "HOLD" if any(x["status"] == "HOLD" for x in checks)
        else "PASS"
    )
    return {
        "version": READINESS_VERSION,
        "activation_verdict": verdict,
        "can_activate_user_feature": False,
        "actual_canary_executed": False,
        "provider_calls": 0,
        "external_network_requests": 0,
        "db_writes": 0,
        "checks": checks,
    }
