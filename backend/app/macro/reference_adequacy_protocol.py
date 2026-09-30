from __future__ import annotations

from typing import Any

from app.macro.calibration_candidate import RATE_SPIKE_FEATURE_IDS
from app.macro.calibration_research import (
    validate_development_artifact,
    validate_distribution_research_artifact,
    validate_research_protocol,
)
from app.macro.eligibility_reconstruction import validate_eligibility_reconstruction
from app.macro.identity import content_hash
from app.macro.reference_stability import (
    EPT_METHOD,
    MAD_METHOD,
    TAIL_METHOD,
    validate_reference_stability_evidence,
)

REFERENCE_ADEQUACY_PROTOCOL_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3"
)
POLICY_ORIGIN = "DEVELOPMENT_INFORMED"
PROTOCOL_STATUS = "BLOCKED_UNJUSTIFIED_TOLERANCE"
REFERENCE_MODE = "EXPANDING_STRICTLY_PRIOR"
FORWARD_RULE = "BOUNDARY_ANCHORED_FORWARD_ENVELOPE"
COMMON_N_POLICY = "COMMON_N_FIRST"
FAMILY_COMBINATION_RULE = "ALL_FAMILIES_AND"
NO_MATCH_RESULT = "NO_SUPPORTED_BOUNDARY"

BLOCKERS = [
    "TAIL_FORWARD_ENVELOPE_TOLERANCE_UNJUSTIFIED",
    "MAD_FORWARD_ENVELOPE_TOLERANCES_UNJUSTIFIED",
    "VALIDATION_SUFFIX_SUFFICIENCY_UNRESOLVED",
]


def _unjustified_tolerance(unit: str) -> dict[str, Any]:
    return {
        "value": None,
        "unit": unit,
        "basis": "UNRESOLVED",
        "origin": POLICY_ORIGIN,
        "status": "UNJUSTIFIED",
    }


def _tail_contract() -> dict[str, Any]:
    return {
        "local_append": {
            "metric": "ECDF_SUP_DRIFT",
            "comparison": "N_MINUS_1_TO_N",
            "role": "DIAGNOSTIC_ONLY",
            "adequacy_gate": False,
            "tolerance_required": False,
            "tolerance": None,
            "status": "DEFINED_DIAGNOSTIC_ONLY",
        },
        "forward_envelope": {
            "rule": FORWARD_RULE,
            "metric": "ECDF_SUP_DISTANCE",
            "comparison": "ANCHOR_N_TO_EVERY_LATER_REFERENCE_STATE",
            "reference_support": "OBSERVED_VALUES_UNION_ONLY",
            "invented_x_grid_points": 0,
            "aggregation": "MAX_OVER_VALIDATION_SUFFIX",
            "tolerance": _unjustified_tolerance(
                "ABSOLUTE_PROBABILITY_DIFFERENCE"
            ),
            "status": "DEFINED_METRIC_UNJUSTIFIED_TOLERANCE",
        },
        "temporal_perturbation": {
            "role": "OPTIONAL_DIAGNOSTIC_ONLY",
            "adequacy_gate": False,
            "segment_length_required": False,
            "tolerance_required": False,
            "segment_length": None,
            "tolerance": None,
            "status": "OPTIONAL_DIAGNOSTIC_ONLY",
        },
        "weighted_stability_score": None,
    }


def _mad_contract() -> dict[str, Any]:
    return {
        "method_specific_computability_required": True,
        "zero_scale_rule": {
            "anchor_mad_zero": "NON_COMPUTABLE_ZERO_SCALE",
            "relative_change": None,
            "null_to_zero_forbidden": True,
        },
        "local": {
            "metrics": [
                "ABSOLUTE_MEDIAN_CHANGE",
                "ABSOLUTE_MAD_CHANGE",
                "RELATIVE_MAD_CHANGE",
            ],
            "comparison": "N_MINUS_1_TO_N",
            "role": "DIAGNOSTIC_ONLY",
            "adequacy_gate": False,
            "tolerance_required": False,
            "tolerances": None,
            "status": "DEFINED_DIAGNOSTIC_ONLY",
        },
        "forward_envelope": {
            "rule": FORWARD_RULE,
            "metrics": [
                "ABSOLUTE_MEDIAN_SHIFT",
                "ABSOLUTE_MAD_SHIFT",
                "RELATIVE_MAD_SHIFT",
            ],
            "comparison": "ANCHOR_N_TO_EVERY_LATER_REFERENCE_STATE",
            "aggregation": "PER_METRIC_MAX_OVER_VALIDATION_SUFFIX",
            "combination_rule": "ALL_AND",
            "tolerances": {
                "absolute_median_shift": _unjustified_tolerance("BASIS_POINT"),
                "absolute_mad_shift": _unjustified_tolerance("BASIS_POINT"),
                "relative_mad_shift": _unjustified_tolerance("RATIO"),
            },
            "status": "DEFINED_METRICS_UNJUSTIFIED_TOLERANCES",
        },
        "temporal_perturbation": {
            "role": "OPTIONAL_DIAGNOSTIC_ONLY",
            "adequacy_gate": False,
            "segment_length_required": False,
            "tolerance_required": False,
            "segment_length": None,
            "tolerances": None,
            "status": "OPTIONAL_DIAGNOSTIC_ONLY",
        },
        "weighted_stability_score": None,
    }


def _evidence_sufficiency_contract() -> dict[str, Any]:
    return {
        "validation_suffix_required": True,
        "minimum_validation_suffix_transitions": None,
        "minimum_validation_suffix_unit": "TRANSITION_COUNT",
        "minimum_validation_suffix_status": "UNRESOLVED_PARAMETER",
        "violation_policy": None,
        "acceptance_form": "MAX_ENVELOPE_WITHIN_APPROVED_TOLERANCE",
        "exceedance_count_role": "DIAGNOSTIC_ONLY",
        "status": "UNRESOLVED_PARAMETER",
    }


def _selection_rule() -> dict[str, Any]:
    return {
        "reference_support_methods": [TAIL_METHOD, MAD_METHOD],
        "ept_reference_support_applicable": False,
        "ept_exclusion_reason": (
            "METHOD_DOES_NOT_USE_EXPANDING_REFERENCE_DISTRIBUTION"
        ),
        "method_policy": COMMON_N_POLICY,
        "horizon_policy": COMMON_N_POLICY,
        "family_combination_rule": FAMILY_COMBINATION_RULE,
        "candidate_boundary_rule": (
            "MINIMUM_N_PASSING_ALL_APPROVED_FORWARD_ENVELOPE_CRITERIA"
        ),
        "no_match_result": NO_MATCH_RESULT,
        "candidate_survival_is_selection_input": False,
        "signal_survival_is_selection_input": False,
        "episode_survival_is_selection_input": False,
        "covered_years_is_selection_input": False,
        "automatic_tolerance_relaxation": False,
        "automatic_method_specific_n": False,
        "automatic_horizon_specific_n": False,
    }


def build_reference_adequacy_protocol(
    *,
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
    research: dict[str, Any],
    reconstruction: dict[str, Any],
    stability: dict[str, Any],
    source_main_sha: str | None = None,
) -> dict[str, Any]:
    development_state = validate_development_artifact(development_dataset)
    protocol_state = validate_research_protocol(
        protocol,
        development_dataset_hash=development_state["dataset_hash"],
    )
    research_state = validate_distribution_research_artifact(
        research,
        development_dataset_hash=development_state["dataset_hash"],
        protocol_hash=protocol_state["protocol_hash"],
    )
    reconstruction_state = validate_eligibility_reconstruction(reconstruction)
    stability_state = validate_reference_stability_evidence(stability)

    reconstruction_source = reconstruction["source"]
    if reconstruction_source["development_dataset_hash"] != development_state[
        "dataset_hash"
    ]:
        raise ValueError("B.1 reconstruction Development hash mismatch.")
    if reconstruction_source["protocol_hash"] != protocol_state["protocol_hash"]:
        raise ValueError("B.1 reconstruction Protocol hash mismatch.")
    if reconstruction_source["research_hash"] != research_state["research_hash"]:
        raise ValueError("B.1 reconstruction Research hash mismatch.")

    stability_source = stability["source"]
    if stability_source["development_dataset_hash"] != development_state[
        "dataset_hash"
    ]:
        raise ValueError("B.1.5 stability Development hash mismatch.")
    if stability_source["protocol_hash"] != protocol_state["protocol_hash"]:
        raise ValueError("B.1.5 stability Protocol hash mismatch.")
    if stability_source["research_hash"] != research_state["research_hash"]:
        raise ValueError("B.1.5 stability Research hash mismatch.")
    if stability_source["reconstruction_hash"] != reconstruction[
        "reconstruction_hash"
    ]:
        raise ValueError("B.1.5 stability reconstruction hash mismatch.")
    if int(stability_source["raw_candidate_count"]) != int(
        reconstruction_state["raw_candidate_count"]
    ):
        raise ValueError("B.1.5 stability raw candidate count mismatch.")

    source = {
        "development_dataset_hash": development_state["dataset_hash"],
        "protocol_hash": protocol_state["protocol_hash"],
        "research_hash": research_state["research_hash"],
        "reconstruction_id": reconstruction["reconstruction_id"],
        "reconstruction_hash": reconstruction["reconstruction_hash"],
        "reference_stability_id": stability["stability_id"],
        "reference_stability_hash": stability_state["stability_hash"],
        "raw_candidate_count": int(reconstruction["counts"]["raw_candidate_count"]),
        "source_main_sha": source_main_sha or "UNSPECIFIED",
    }
    validation_contract = {
        "reference_mode": REFERENCE_MODE,
        "current_observation_excluded": True,
        "adequacy_dimensions": [
            "COMPUTABILITY",
            "FORWARD_SENSITIVITY",
            "EVIDENCE_SUFFICIENCY",
        ],
        "tail": _tail_contract(),
        "mad": _mad_contract(),
        "evidence_sufficiency": _evidence_sufficiency_contract(),
        "selection_rule": _selection_rule(),
    }
    scope = {
        "shock": "RATE_SPIKE",
        "features": list(RATE_SPIKE_FEATURE_IDS),
        "methods": [TAIL_METHOD, MAD_METHOD],
        "ept_method": EPT_METHOD,
        "ept_reference_support_applicable": False,
        "common_method_n_required": True,
        "common_horizon_n_required": True,
    }
    policy_state = {
        "protocol_status": PROTOCOL_STATUS,
        "reference_adequacy": "UNRESOLVED",
        "reference_adequacy_criterion": "UNRESOLVED",
        "minimum_prior_observations": None,
        "recommended_support": None,
        "selection_status": "NOT_SELECTED",
        "eligibility_policy_status": "UNDEFINED",
        "admissibility_policy_status": "UNDEFINED",
        "final_candidate_status": "NOT_SELECTED",
        "ready_for_evidence_generation": True,
        "ready_for_b17": True,
        "ready_for_b2": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    identity_payload = {
        "contract_version": REFERENCE_ADEQUACY_PROTOCOL_CONTRACT_VERSION,
        "policy_origin": POLICY_ORIGIN,
        "source": source,
        "scope": scope,
        "research_history": {
            "policy_origin": POLICY_ORIGIN,
            "development_evidence_already_observed": True,
            "claim_data_blind_forbidden": True,
            "holdout_used_for_protocol_design": False,
            "r2_review": "PARTIAL_STRUCTURAL_REDUCTION",
        },
        "validation_contract": validation_contract,
        "blockers": list(BLOCKERS),
        "policy_state": policy_state,
        "holdout_locked": True,
        "holdout_accessed": False,
        "network_requests": 0,
        "macro_db_writes": 0,
        "production_impact": "NONE",
    }
    protocol_hash = content_hash(identity_payload)
    return {
        **identity_payload,
        "adequacy_protocol_id": f"RATEADEQPROTO-{protocol_hash[:16]}",
        "adequacy_protocol_hash": protocol_hash,
    }


def _identity_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        key: artifact[key]
        for key in (
            "contract_version",
            "policy_origin",
            "source",
            "scope",
            "research_history",
            "validation_contract",
            "blockers",
            "policy_state",
            "holdout_locked",
            "holdout_accessed",
            "network_requests",
            "macro_db_writes",
            "production_impact",
        )
    }


def validate_reference_adequacy_protocol(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    if artifact.get("contract_version") != REFERENCE_ADEQUACY_PROTOCOL_CONTRACT_VERSION:
        raise ValueError("Unsupported reference adequacy protocol contract.")
    if artifact.get("policy_origin") != POLICY_ORIGIN:
        raise ValueError("Reference adequacy protocol must be Development-informed.")
    if artifact.get("holdout_locked") is not True:
        raise ValueError("Reference adequacy protocol must keep Holdout locked.")
    if artifact.get("holdout_accessed") is not False:
        raise ValueError("Reference adequacy protocol must not access Holdout.")
    if int(artifact.get("network_requests") or 0) != 0:
        raise ValueError("Reference adequacy protocol must not use network.")
    if int(artifact.get("macro_db_writes") or 0) != 0:
        raise ValueError("Reference adequacy protocol must not write Macro DB.")
    if artifact.get("production_impact") != "NONE":
        raise ValueError("Reference adequacy protocol must have no Production impact.")

    scope = artifact.get("scope") or {}
    if scope.get("features") != list(RATE_SPIKE_FEATURE_IDS):
        raise ValueError("Reference adequacy feature scope changed.")
    if scope.get("methods") != [TAIL_METHOD, MAD_METHOD]:
        raise ValueError("Reference adequacy method scope changed.")
    if scope.get("ept_reference_support_applicable") is not False:
        raise ValueError("EPT must remain excluded from reference support.")
    if scope.get("common_method_n_required") is not True:
        raise ValueError("Common method N requirement changed.")
    if scope.get("common_horizon_n_required") is not True:
        raise ValueError("Common horizon N requirement changed.")

    contract = artifact.get("validation_contract") or {}
    if contract.get("reference_mode") != REFERENCE_MODE:
        raise ValueError("Reference mode changed unexpectedly.")
    if contract.get("current_observation_excluded") is not True:
        raise ValueError("Current observation must remain excluded.")

    tail = contract.get("tail") or {}
    local_tail = tail.get("local_append") or {}
    if (
        local_tail.get("role") != "DIAGNOSTIC_ONLY"
        or local_tail.get("adequacy_gate") is not False
        or local_tail.get("tolerance_required") is not False
        or local_tail.get("tolerance") is not None
    ):
        raise ValueError("TAIL local append must remain diagnostic-only.")
    tail_forward = tail.get("forward_envelope") or {}
    if tail_forward.get("rule") != FORWARD_RULE:
        raise ValueError("TAIL forward envelope rule mismatch.")
    if tail_forward.get("invented_x_grid_points") != 0:
        raise ValueError("TAIL forward envelope cannot invent x-grid points.")
    tail_tolerance = tail_forward.get("tolerance") or {}
    if tail_tolerance.get("value") is not None or tail_tolerance.get("status") != "UNJUSTIFIED":
        raise ValueError("TAIL forward envelope tolerance must remain unresolved.")
    tail_perturbation = tail.get("temporal_perturbation") or {}
    if (
        tail_perturbation.get("role") != "OPTIONAL_DIAGNOSTIC_ONLY"
        or tail_perturbation.get("adequacy_gate") is not False
        or tail_perturbation.get("segment_length") is not None
        or tail_perturbation.get("tolerance") is not None
    ):
        raise ValueError("TAIL temporal perturbation must remain optional diagnostic-only.")
    if tail.get("weighted_stability_score") is not None:
        raise ValueError("TAIL weighted stability score is forbidden.")

    mad = contract.get("mad") or {}
    local_mad = mad.get("local") or {}
    if (
        local_mad.get("role") != "DIAGNOSTIC_ONLY"
        or local_mad.get("adequacy_gate") is not False
        or local_mad.get("tolerance_required") is not False
        or local_mad.get("tolerances") is not None
    ):
        raise ValueError("MAD local metrics must remain diagnostic-only.")
    mad_forward = mad.get("forward_envelope") or {}
    if mad_forward.get("rule") != FORWARD_RULE:
        raise ValueError("MAD forward envelope rule mismatch.")
    if mad_forward.get("combination_rule") != "ALL_AND":
        raise ValueError("MAD forward envelope metrics must use logical AND.")
    for tolerance in (mad_forward.get("tolerances") or {}).values():
        if tolerance.get("value") is not None or tolerance.get("status") != "UNJUSTIFIED":
            raise ValueError("MAD forward envelope tolerances must remain unresolved.")
    mad_perturbation = mad.get("temporal_perturbation") or {}
    if (
        mad_perturbation.get("role") != "OPTIONAL_DIAGNOSTIC_ONLY"
        or mad_perturbation.get("adequacy_gate") is not False
        or mad_perturbation.get("segment_length") is not None
        or mad_perturbation.get("tolerances") is not None
    ):
        raise ValueError("MAD temporal perturbation must remain optional diagnostic-only.")
    if mad.get("weighted_stability_score") is not None:
        raise ValueError("MAD weighted stability score is forbidden.")

    sufficiency = contract.get("evidence_sufficiency") or {}
    if sufficiency.get("minimum_validation_suffix_transitions") is not None:
        raise ValueError("Validation suffix minimum must remain unresolved.")
    if sufficiency.get("violation_policy") is not None:
        raise ValueError("Separate violation-budget policy is forbidden in V3.")
    if sufficiency.get("acceptance_form") != "MAX_ENVELOPE_WITHIN_APPROVED_TOLERANCE":
        raise ValueError("Evidence-sufficiency acceptance form changed.")

    selection = contract.get("selection_rule") or {}
    forbidden_true = (
        "candidate_survival_is_selection_input",
        "signal_survival_is_selection_input",
        "episode_survival_is_selection_input",
        "covered_years_is_selection_input",
        "automatic_tolerance_relaxation",
        "automatic_method_specific_n",
        "automatic_horizon_specific_n",
    )
    if any(selection.get(key) is not False for key in forbidden_true):
        raise ValueError("Reference adequacy selection guardrail was relaxed.")

    if list(artifact.get("blockers") or []) != BLOCKERS:
        raise ValueError("Reference adequacy V3 blocker set changed.")

    expected_policy = {
        "protocol_status": PROTOCOL_STATUS,
        "reference_adequacy": "UNRESOLVED",
        "reference_adequacy_criterion": "UNRESOLVED",
        "minimum_prior_observations": None,
        "recommended_support": None,
        "selection_status": "NOT_SELECTED",
        "eligibility_policy_status": "UNDEFINED",
        "admissibility_policy_status": "UNDEFINED",
        "final_candidate_status": "NOT_SELECTED",
        "ready_for_evidence_generation": True,
        "ready_for_b17": True,
        "ready_for_b2": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    if artifact.get("policy_state") != expected_policy:
        raise ValueError("Reference adequacy protocol policy state changed.")

    protocol_hash = content_hash(_identity_payload(artifact))
    if artifact.get("adequacy_protocol_hash") != protocol_hash:
        raise ValueError("Reference adequacy protocol hash mismatch.")
    if artifact.get("adequacy_protocol_id") != f"RATEADEQPROTO-{protocol_hash[:16]}":
        raise ValueError("Reference adequacy protocol id mismatch.")

    return {
        "adequacy_protocol_id": artifact["adequacy_protocol_id"],
        "adequacy_protocol_hash": protocol_hash,
        "protocol_status": PROTOCOL_STATUS,
        "blocker_count": len(BLOCKERS),
        "ready_for_evidence_generation": True,
        "ready_for_holdout": False,
    }


def render_reference_adequacy_protocol_text(artifact: dict[str, Any]) -> str:
    state = validate_reference_adequacy_protocol(artifact)
    policy = artifact["policy_state"]
    return "\n".join(
        [
            "NEXT-6B-S4.2-B.1.6 REFERENCE ADEQUACY VALIDATION PROTOCOL V3",
            "",
            f"Source Stability      : {artifact['source']['reference_stability_id']}",
            f"Policy Origin         : {artifact['policy_origin']}",
            "Validation Rule       : BOUNDARY_ANCHORED_FORWARD_ENVELOPE",
            "TAIL Local            : DIAGNOSTIC_ONLY",
            "MAD Local             : DIAGNOSTIC_ONLY",
            "Temporal Perturbation : OPTIONAL_DIAGNOSTIC_ONLY",
            "EPT Reference Gate    : EXCLUDED",
            "",
            (
                "Reference Adequacy / Minimum Prior Observations / "
                f"Recommended Support : {policy['reference_adequacy']} / "
                f"{policy['minimum_prior_observations']} / {policy['recommended_support']}"
            ),
            (
                "Holdout locked / accessed / ready : "
                f"{artifact['holdout_locked']} / {artifact['holdout_accessed']} / "
                f"{policy['ready_for_holdout']}"
            ),
            (
                "RATE_SPIKE / Network / Macro DB writes / Production : "
                f"{policy['rate_spike_state']} / {artifact['network_requests']} / "
                f"{artifact['macro_db_writes']} / {artifact['production_impact']}"
            ),
            "",
            f"Protocol status: {state['protocol_status']}",
            f"Evidence generation readiness: READY ({state['blocker_count']} unresolved policy classes)",
            "B.2 readiness: BLOCKED",
        ]
    )
