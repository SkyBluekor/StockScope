from __future__ import annotations

from typing import Any

from app.macro.identity import content_hash


NEXT6E_VALIDATION_ENTRY_GATE_CONTRACT_VERSION = (
    "VN_NEXT6E_S1_VALIDATION_ENTRY_GATE_V1"
)

OVERALL_SCOPE_REFERENCE_VALIDATION_ONLY = "REFERENCE_VALIDATION_ONLY"

LANE_ELIGIBLE = "ELIGIBLE"
LANE_READY_TO_IMPLEMENT = "READY_TO_IMPLEMENT"
LANE_BLOCKED = "BLOCKED"
LANE_LOCKED = "LOCKED"

_ALLOWED_MACRO_NUMERIC_POLICIES = {"NONE"}
_ALLOWED_REFERENCE_ADEQUACY = {"UNRESOLVED"}
_ALLOWED_RATE_SPIKE_CALIBRATION = {"UNCALIBRATED"}
_ALLOWED_HISTORICAL_SECTOR_STATUS = {"BLOCKED_EXTERNAL_SOURCE"}
_ALLOWED_HISTORICAL_IMPACT_MODE = {"MARKET_STOCK_ONLY"}
_ALLOWED_PROSPECTIVE_SECTOR_STATUS = {"NOT_STARTED"}
_ALLOWED_P6_ASOF_MODE = {"SYSTEM_OBSERVED_AS_OF"}
_ALLOWED_PREDICTION_STATUS = {"NOT_VALIDATED"}

_BLOCKER_ORDER = (
    "MACRO_NUMERIC_POLICY_UNDEFINED",
    "REFERENCE_ADEQUACY_UNRESOLVED",
    "RATE_SPIKE_UNCALIBRATED",
    "HISTORICAL_SECTOR_BLOCKED",
    "P6_HISTORICAL_COMPLETENESS_UNPROVEN",
    "P6_HISTORICAL_EVALUATION_NOT_APPROVED",
    "PREDICTION_NOT_VALIDATED",
    "ALTERNATIVE_EXECUTION_POLICY_NOT_DEFINED",
    "HOLDOUT_LOCKED",
)


def _required_text(value: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required.")
    return text


def _enum_text(
    value: str,
    *,
    field: str,
    allowed: set[str],
) -> str:
    text = _required_text(value, field).upper()
    if text not in allowed:
        raise ValueError(
            f"{field} is not supported by NEXT-6E-S1: {text}."
        )
    return text


def _current_blockers(
    *,
    macro_numeric_policy: str,
    reference_adequacy: str,
    rate_spike_calibration_status: str,
    historical_sector_status: str,
    p6_historical_completeness_proven: bool,
    p6_historical_evaluation_approved: bool,
    prediction_status: str,
) -> list[str]:
    present: set[str] = {
        "ALTERNATIVE_EXECUTION_POLICY_NOT_DEFINED",
        "HOLDOUT_LOCKED",
    }
    if macro_numeric_policy == "NONE":
        present.add("MACRO_NUMERIC_POLICY_UNDEFINED")
    if reference_adequacy == "UNRESOLVED":
        present.add("REFERENCE_ADEQUACY_UNRESOLVED")
    if rate_spike_calibration_status == "UNCALIBRATED":
        present.add("RATE_SPIKE_UNCALIBRATED")
    if historical_sector_status == "BLOCKED_EXTERNAL_SOURCE":
        present.add("HISTORICAL_SECTOR_BLOCKED")
    if not p6_historical_completeness_proven:
        present.add("P6_HISTORICAL_COMPLETENESS_UNPROVEN")
    if not p6_historical_evaluation_approved:
        present.add("P6_HISTORICAL_EVALUATION_NOT_APPROVED")
    if prediction_status == "NOT_VALIDATED":
        present.add("PREDICTION_NOT_VALIDATED")
    return [code for code in _BLOCKER_ORDER if code in present]


def build_next6e_validation_entry_gate(
    *,
    scanner_version: str,
    macro_numeric_policy: str,
    reference_adequacy: str,
    rate_spike_calibration_status: str,
    historical_sector_status: str,
    historical_impact_mode: str,
    prospective_sector_status: str,
    p6_asof_mode: str,
    p6_historical_completeness_proven: bool,
    p6_historical_evaluation_approved: bool,
    prediction_status: str,
) -> dict[str, Any]:
    """Freeze the NEXT-6E validation entry boundary.

    The builder is deliberately pure. It performs no database, filesystem,
    provider, network, runtime-clock or validation-run access. It only maps
    explicitly supplied, already-established NEXT-6 states into a deterministic
    validation-scope contract.

    NEXT-6E-S1 is not an effectiveness evaluation and does not authorize any
    Strategy, Scanner, Risk, Holdings, prediction or Production behavior.
    """

    scanner = _required_text(scanner_version, "scanner_version")
    numeric_policy = _enum_text(
        macro_numeric_policy,
        field="macro_numeric_policy",
        allowed=_ALLOWED_MACRO_NUMERIC_POLICIES,
    )
    adequacy = _enum_text(
        reference_adequacy,
        field="reference_adequacy",
        allowed=_ALLOWED_REFERENCE_ADEQUACY,
    )
    rate_spike = _enum_text(
        rate_spike_calibration_status,
        field="rate_spike_calibration_status",
        allowed=_ALLOWED_RATE_SPIKE_CALIBRATION,
    )
    historical_sector = _enum_text(
        historical_sector_status,
        field="historical_sector_status",
        allowed=_ALLOWED_HISTORICAL_SECTOR_STATUS,
    )
    impact_mode = _enum_text(
        historical_impact_mode,
        field="historical_impact_mode",
        allowed=_ALLOWED_HISTORICAL_IMPACT_MODE,
    )
    prospective_sector = _enum_text(
        prospective_sector_status,
        field="prospective_sector_status",
        allowed=_ALLOWED_PROSPECTIVE_SECTOR_STATUS,
    )
    asof_mode = _enum_text(
        p6_asof_mode,
        field="p6_asof_mode",
        allowed=_ALLOWED_P6_ASOF_MODE,
    )
    prediction = _enum_text(
        prediction_status,
        field="prediction_status",
        allowed=_ALLOWED_PREDICTION_STATUS,
    )

    if not isinstance(p6_historical_completeness_proven, bool):
        raise ValueError(
            "p6_historical_completeness_proven must be a boolean."
        )
    if not isinstance(p6_historical_evaluation_approved, bool):
        raise ValueError(
            "p6_historical_evaluation_approved must be a boolean."
        )

    event_incremental_lane = (
        LANE_ELIGIBLE
        if (
            p6_historical_completeness_proven
            and p6_historical_evaluation_approved
        )
        else LANE_BLOCKED
    )

    lanes = {
        "reference_reproducibility": LANE_ELIGIBLE,
        "development_coverage": LANE_ELIGIBLE,
        "prospective_reference_capture": LANE_READY_TO_IMPLEMENT,
        "shock_effectiveness": LANE_BLOCKED,
        "sector_effectiveness": LANE_BLOCKED,
        "event_incremental_value": event_incremental_lane,
        "execution_policy_comparison": LANE_BLOCKED,
        "holdout_evaluation": LANE_LOCKED,
        "production_readiness": LANE_BLOCKED,
    }

    numeric_criteria = {
        "defined": False,
        "minimum_sample": None,
        "minimum_effect_size": None,
        "maximum_allowed_degradation": None,
        "promotion_threshold": None,
    }

    blockers = _current_blockers(
        macro_numeric_policy=numeric_policy,
        reference_adequacy=adequacy,
        rate_spike_calibration_status=rate_spike,
        historical_sector_status=historical_sector,
        p6_historical_completeness_proven=(
            p6_historical_completeness_proven
        ),
        p6_historical_evaluation_approved=(
            p6_historical_evaluation_approved
        ),
        prediction_status=prediction,
    )

    governance = {
        "holdout_access": False,
        "holdout_evaluation_approved": False,
        "historical_effectiveness_approved": False,
        "execution_policy_evaluation_approved": False,
        "prediction_approved": False,
        "strategy_input_approved": False,
        "scanner_input_approved": False,
        "risk_gate_input_approved": False,
        "holdings_plan_input_approved": False,
        "production_decision_approved": False,
        "network_access": False,
        "database_write": False,
    }

    identity_payload = {
        "contract_version": NEXT6E_VALIDATION_ENTRY_GATE_CONTRACT_VERSION,
        "overall_scope": OVERALL_SCOPE_REFERENCE_VALIDATION_ONLY,
        "baseline": {
            "target": "PRODUCTION_SCANNER",
            "scanner_version": scanner,
            "selection_policy_pin_required": True,
        },
        "input_state": {
            "macro_numeric_policy": numeric_policy,
            "reference_adequacy": adequacy,
            "rate_spike_calibration_status": rate_spike,
            "historical_sector_status": historical_sector,
            "historical_impact_mode": impact_mode,
            "prospective_sector_status": prospective_sector,
            "p6_asof_mode": asof_mode,
            "p6_historical_completeness_proven": (
                p6_historical_completeness_proven
            ),
            "p6_historical_evaluation_approved": (
                p6_historical_evaluation_approved
            ),
            "prediction_status": prediction,
        },
        "lanes": lanes,
        "numeric_criteria": numeric_criteria,
        "blockers": blockers,
        "governance": governance,
    }
    gate_hash = content_hash(identity_payload)

    return {
        "contract_version": NEXT6E_VALIDATION_ENTRY_GATE_CONTRACT_VERSION,
        "gate_id": f"NEXT6EGATE-{gate_hash[:16]}",
        "gate_hash": gate_hash,
        "overall_scope": OVERALL_SCOPE_REFERENCE_VALIDATION_ONLY,
        "baseline": identity_payload["baseline"],
        "input_state": identity_payload["input_state"],
        "lanes": lanes,
        "numeric_criteria": numeric_criteria,
        "blockers": blockers,
        "governance": governance,
    }
