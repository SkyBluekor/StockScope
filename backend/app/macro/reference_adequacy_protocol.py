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
    "VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V1"
)
POLICY_ORIGIN = "DEVELOPMENT_INFORMED"
PROTOCOL_STATUS = "BLOCKED_UNJUSTIFIED_TOLERANCE"
REFERENCE_MODE = "EXPANDING_STRICTLY_PRIOR"
COMMON_N_POLICY = "COMMON_N_FIRST"
FAMILY_COMBINATION_RULE = "ALL_FAMILIES_AND"
NO_MATCH_RESULT = "NO_SUPPORTED_BOUNDARY"


def _unjustified_tolerance(unit: str) -> dict[str, Any]:
    return {
        "value": None,
        "unit": unit,
        "basis": "UNRESOLVED",
        "rationale": None,
        "origin": POLICY_ORIGIN,
        "status": "UNJUSTIFIED",
    }


def _unresolved_parameter(
    *,
    name: str,
    unit: str,
    purpose: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": None,
        "unit": unit,
        "purpose": purpose,
        "origin": POLICY_ORIGIN,
        "status": "UNRESOLVED_PARAMETER",
    }


def _tail_validation_contract() -> dict[str, Any]:
    return {
        "local_append": {
            "metric": "ECDF_SUP_DRIFT",
            "comparison": "N_MINUS_1_TO_N",
            "reference_support": "OBSERVED_VALUES_UNION_ONLY",
            "invented_x_grid_points": 0,
            "role": "DIAGNOSTIC_ONLY",
            "tolerance": _unjustified_tolerance(
                "ABSOLUTE_PROBABILITY_DIFFERENCE"
            ),
            "status": "DEFINED_METRIC_UNJUSTIFIED_TOLERANCE",
        },
        "cumulative": {
            "metric": "ECDF_SUP_DRIFT",
            "comparison": "N_MINUS_K_TO_N",
            "comparison_interval": _unresolved_parameter(
                name="comparison_interval_observations",
                unit="OBSERVATION_COUNT",
                purpose=(
                    "Measure cumulative reference movement beyond one-observation "
                    "append sensitivity."
                ),
            ),
            "tolerance": _unjustified_tolerance(
                "ABSOLUTE_PROBABILITY_DIFFERENCE"
            ),
            "status": "UNRESOLVED_PARAMETER",
        },
        "temporal_perturbation": {
            "metric": "ECDF_SUP_DRIFT",
            "perturbation_rule": (
                "TIME_ORDER_PRESERVING_CONTIGUOUS_STRICTLY_PRIOR_SEGMENT"
            ),
            "segment_length": _unresolved_parameter(
                name="segment_length_observations",
                unit="OBSERVATION_COUNT",
                purpose=(
                    "Test dependence on a contiguous historical reference segment "
                    "without shuffling time order."
                ),
            ),
            "tolerance": _unjustified_tolerance(
                "ABSOLUTE_PROBABILITY_DIFFERENCE"
            ),
            "status": "UNRESOLVED_PARAMETER",
        },
        "weighted_stability_score": None,
    }


def _mad_validation_contract() -> dict[str, Any]:
    local_tolerances = {
        "absolute_median_change": _unjustified_tolerance("BASIS_POINT"),
        "absolute_mad_change": _unjustified_tolerance("BASIS_POINT"),
        "relative_mad_change": _unjustified_tolerance("RATIO"),
    }
    cumulative_tolerances = {
        "absolute_median_change": _unjustified_tolerance("BASIS_POINT"),
        "absolute_mad_change": _unjustified_tolerance("BASIS_POINT"),
        "relative_mad_change": _unjustified_tolerance("RATIO"),
    }
    perturbation_tolerances = {
        "absolute_median_change": _unjustified_tolerance("BASIS_POINT"),
        "absolute_mad_change": _unjustified_tolerance("BASIS_POINT"),
        "relative_mad_change": _unjustified_tolerance("RATIO"),
    }
    return {
        "method_specific_computability_required": True,
        "zero_scale_rule": {
            "previous_mad_zero": "NON_COMPUTABLE_ZERO_SCALE",
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
            "combination_rule": "ALL_AND",
            "tolerances": local_tolerances,
            "status": "DEFINED_METRICS_UNJUSTIFIED_TOLERANCES",
        },
        "cumulative": {
            "metrics": [
                "ABSOLUTE_MEDIAN_CHANGE",
                "ABSOLUTE_MAD_CHANGE",
                "RELATIVE_MAD_CHANGE",
            ],
            "comparison": "N_MINUS_K_TO_N",
            "comparison_interval": _unresolved_parameter(
                name="comparison_interval_observations",
                unit="OBSERVATION_COUNT",
                purpose=(
                    "Measure cumulative location and scale movement beyond a "
                    "single append."
                ),
            ),
            "combination_rule": "ALL_AND",
            "tolerances": cumulative_tolerances,
            "status": "UNRESOLVED_PARAMETER",
        },
        "temporal_perturbation": {
            "metrics": [
                "ABSOLUTE_MEDIAN_CHANGE",
                "ABSOLUTE_MAD_CHANGE",
                "RELATIVE_MAD_CHANGE",
            ],
            "perturbation_rule": (
                "TIME_ORDER_PRESERVING_CONTIGUOUS_STRICTLY_PRIOR_SEGMENT"
            ),
            "segment_length": _unresolved_parameter(
                name="segment_length_observations",
                unit="OBSERVATION_COUNT",
                purpose=(
                    "Test median/MAD dependence on a contiguous historical "
                    "reference segment without shuffling time order."
                ),
            ),
            "combination_rule": "ALL_AND",
            "tolerances": perturbation_tolerances,
            "status": "UNRESOLVED_PARAMETER",
        },
        "weighted_stability_score": None,
    }


def _evidence_sufficiency_contract() -> dict[str, Any]:
    return {
        "single_zero_transition_sufficient": False,
        "descriptive_median_zero_sufficient": False,
        "validation_suffix_required": True,
        "minimum_validation_suffix_transitions": _unresolved_parameter(
            name="minimum_validation_suffix_transitions",
            unit="TRANSITION_COUNT",
            purpose=(
                "Prevent a boundary near the end of Development from passing "
                "because only a short quiet suffix remains."
            ),
        ),
        "violation_policy": {
            "value": "UNSET",
            "allowed_values": [
                "ZERO_VIOLATIONS",
                "BOUNDED_VIOLATIONS",
            ],
            "status": "UNRESOLVED_PARAMETER",
        },
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
            "MINIMUM_N_PASSING_ALL_TAIL_MAD_HORIZON_CRITERIA"
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
    if stability_source["reconstruction_id"] != reconstruction[
        "reconstruction_id"
    ]:
        raise ValueError("B.1.5 stability reconstruction id mismatch.")
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
        "raw_candidate_count": int(
            reconstruction["counts"]["raw_candidate_count"]
        ),
        "source_main_sha": source_main_sha or "UNSPECIFIED",
    }

    validation_contract = {
        "reference_mode": REFERENCE_MODE,
        "current_observation_excluded": True,
        "adequacy_dimensions": [
            "COMPUTABILITY",
            "SENSITIVITY",
            "EVIDENCE_SUFFICIENCY",
        ],
        "tail": _tail_validation_contract(),
        "mad": _mad_validation_contract(),
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
    research_history = {
        "policy_origin": POLICY_ORIGIN,
        "development_evidence_already_observed": True,
        "claim_data_blind_forbidden": True,
        "holdout_used_for_protocol_design": False,
        "notes": [
            (
                "The protocol is Development-informed and must not be described "
                "as ex-ante to Development."
            ),
            (
                "Candidate/signal/episode survival may explain policy impact but "
                "must not choose or relax adequacy tolerances."
            ),
        ],
    }
    blockers = [
        "TAIL_LOCAL_TOLERANCE_UNJUSTIFIED",
        "TAIL_CUMULATIVE_INTERVAL_UNRESOLVED",
        "TAIL_CUMULATIVE_TOLERANCE_UNJUSTIFIED",
        "TAIL_PERTURBATION_SEGMENT_LENGTH_UNRESOLVED",
        "TAIL_PERTURBATION_TOLERANCE_UNJUSTIFIED",
        "MAD_LOCAL_TOLERANCES_UNJUSTIFIED",
        "MAD_CUMULATIVE_INTERVAL_UNRESOLVED",
        "MAD_CUMULATIVE_TOLERANCES_UNJUSTIFIED",
        "MAD_PERTURBATION_SEGMENT_LENGTH_UNRESOLVED",
        "MAD_PERTURBATION_TOLERANCES_UNJUSTIFIED",
        "VALIDATION_SUFFIX_LENGTH_UNRESOLVED",
        "VIOLATION_POLICY_UNRESOLVED",
    ]
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
        "ready_for_evidence_generation": False,
        "ready_for_b17": False,
        "ready_for_b2": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }

    identity_payload = {
        "contract_version": REFERENCE_ADEQUACY_PROTOCOL_CONTRACT_VERSION,
        "policy_origin": POLICY_ORIGIN,
        "source": source,
        "scope": scope,
        "research_history": research_history,
        "validation_contract": validation_contract,
        "blockers": blockers,
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


def _assert_unjustified_tolerance(item: dict[str, Any]) -> None:
    if item.get("value") is not None:
        raise ValueError("B.1.6 cannot preregister an unjustified tolerance value.")
    if item.get("status") != "UNJUSTIFIED":
        raise ValueError("B.1.6 unresolved tolerance status changed unexpectedly.")
    if item.get("origin") != POLICY_ORIGIN:
        raise ValueError("B.1.6 tolerance origin must be Development-informed.")


def _assert_unresolved_parameter(item: dict[str, Any]) -> None:
    if item.get("value") is not None:
        raise ValueError("B.1.6 unresolved protocol parameter must stay null.")
    if item.get("status") != "UNRESOLVED_PARAMETER":
        raise ValueError("B.1.6 unresolved protocol parameter status mismatch.")
    if item.get("origin") != POLICY_ORIGIN:
        raise ValueError("B.1.6 unresolved parameter origin mismatch.")


def validate_reference_adequacy_protocol(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    if artifact.get("contract_version") != (
        REFERENCE_ADEQUACY_PROTOCOL_CONTRACT_VERSION
    ):
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
    if scope.get("ept_method") != EPT_METHOD:
        raise ValueError("Reference adequacy EPT method mismatch.")
    if scope.get("ept_reference_support_applicable") is not False:
        raise ValueError("EPT must remain excluded from reference support.")
    if scope.get("common_method_n_required") is not True:
        raise ValueError("B.1.6 must keep a common method N requirement.")
    if scope.get("common_horizon_n_required") is not True:
        raise ValueError("B.1.6 must keep a common horizon N requirement.")

    history = artifact.get("research_history") or {}
    if history.get("development_evidence_already_observed") is not True:
        raise ValueError("B.1.6 must record prior Development observation.")
    if history.get("claim_data_blind_forbidden") is not True:
        raise ValueError("B.1.6 cannot claim data-blind Development design.")
    if history.get("holdout_used_for_protocol_design") is not False:
        raise ValueError("B.1.6 cannot use Holdout for protocol design.")

    contract = artifact.get("validation_contract") or {}
    if contract.get("reference_mode") != REFERENCE_MODE:
        raise ValueError("Reference mode changed unexpectedly.")
    if contract.get("current_observation_excluded") is not True:
        raise ValueError("Current observation must remain excluded.")
    if contract.get("adequacy_dimensions") != [
        "COMPUTABILITY",
        "SENSITIVITY",
        "EVIDENCE_SUFFICIENCY",
    ]:
        raise ValueError("Reference adequacy dimensions changed.")

    tail = contract.get("tail") or {}
    if tail.get("weighted_stability_score") is not None:
        raise ValueError("TAIL weighted stability score is forbidden.")
    _assert_unjustified_tolerance(tail["local_append"]["tolerance"])
    _assert_unresolved_parameter(
        tail["cumulative"]["comparison_interval"]
    )
    _assert_unjustified_tolerance(tail["cumulative"]["tolerance"])
    _assert_unresolved_parameter(
        tail["temporal_perturbation"]["segment_length"]
    )
    _assert_unjustified_tolerance(
        tail["temporal_perturbation"]["tolerance"]
    )

    mad = contract.get("mad") or {}
    if mad.get("weighted_stability_score") is not None:
        raise ValueError("MAD weighted stability score is forbidden.")
    if mad.get("method_specific_computability_required") is not True:
        raise ValueError("MAD computability condition must remain explicit.")
    zero_scale = mad.get("zero_scale_rule") or {}
    if zero_scale.get("relative_change") is not None:
        raise ValueError("MAD zero-scale relative change must remain null.")
    if zero_scale.get("null_to_zero_forbidden") is not True:
        raise ValueError("MAD null-to-zero conversion must remain forbidden.")

    for section_name in ("local", "cumulative", "temporal_perturbation"):
        section = mad[section_name]
        if section.get("combination_rule") != "ALL_AND":
            raise ValueError("MAD adequacy metrics must use logical AND.")
        for tolerance in section["tolerances"].values():
            _assert_unjustified_tolerance(tolerance)
    _assert_unresolved_parameter(mad["cumulative"]["comparison_interval"])
    _assert_unresolved_parameter(
        mad["temporal_perturbation"]["segment_length"]
    )

    sufficiency = contract.get("evidence_sufficiency") or {}
    if sufficiency.get("single_zero_transition_sufficient") is not False:
        raise ValueError("Single zero transition cannot establish adequacy.")
    if sufficiency.get("descriptive_median_zero_sufficient") is not False:
        raise ValueError("Median zero cannot establish adequacy.")
    if sufficiency.get("validation_suffix_required") is not True:
        raise ValueError("Validation suffix must remain required.")
    _assert_unresolved_parameter(
        sufficiency["minimum_validation_suffix_transitions"]
    )
    violation_policy = sufficiency.get("violation_policy") or {}
    if violation_policy.get("value") != "UNSET":
        raise ValueError("Violation policy must remain unset in B.1.6.")
    if violation_policy.get("status") != "UNRESOLVED_PARAMETER":
        raise ValueError("Violation policy status mismatch.")

    selection = contract.get("selection_rule") or {}
    expected_boolean_false = (
        "candidate_survival_is_selection_input",
        "signal_survival_is_selection_input",
        "episode_survival_is_selection_input",
        "covered_years_is_selection_input",
        "automatic_tolerance_relaxation",
        "automatic_method_specific_n",
        "automatic_horizon_specific_n",
    )
    if any(selection.get(key) is not False for key in expected_boolean_false):
        raise ValueError("B.1.6 selection guardrail was relaxed.")
    if selection.get("family_combination_rule") != FAMILY_COMBINATION_RULE:
        raise ValueError("Family combination rule changed.")
    if selection.get("no_match_result") != NO_MATCH_RESULT:
        raise ValueError("No-match result must remain NO_SUPPORTED_BOUNDARY.")
    if selection.get("method_policy") != COMMON_N_POLICY:
        raise ValueError("Method N policy changed.")
    if selection.get("horizon_policy") != COMMON_N_POLICY:
        raise ValueError("Horizon N policy changed.")

    policy = artifact.get("policy_state") or {}
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
        "ready_for_evidence_generation": False,
        "ready_for_b17": False,
        "ready_for_b2": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    if policy != expected_policy:
        raise ValueError("Reference adequacy protocol policy state changed.")

    blockers = list(artifact.get("blockers") or [])
    if not blockers:
        raise ValueError("Blocked B.1.6 protocol must preserve blockers.")

    protocol_hash = content_hash(_identity_payload(artifact))
    if artifact.get("adequacy_protocol_hash") != protocol_hash:
        raise ValueError("Reference adequacy protocol hash mismatch.")
    if artifact.get("adequacy_protocol_id") != (
        f"RATEADEQPROTO-{protocol_hash[:16]}"
    ):
        raise ValueError("Reference adequacy protocol id mismatch.")

    return {
        "adequacy_protocol_id": artifact["adequacy_protocol_id"],
        "adequacy_protocol_hash": protocol_hash,
        "protocol_status": policy["protocol_status"],
        "blocker_count": len(blockers),
        "ready_for_evidence_generation": False,
        "ready_for_holdout": False,
    }


def render_reference_adequacy_protocol_text(
    artifact: dict[str, Any],
) -> str:
    validate_reference_adequacy_protocol(artifact)
    contract = artifact["validation_contract"]
    policy = artifact["policy_state"]

    lines = [
        "NEXT-6B-S4.2-B.1.6 REFERENCE ADEQUACY VALIDATION PROTOCOL",
        "",
        (
            "Source Stability      : "
            f"{artifact['source']['reference_stability_id']}"
        ),
        f"Policy Origin         : {artifact['policy_origin']}",
        "",
        "TAIL Validation:",
        (
            "  Local Append          "
            f"{contract['tail']['local_append']['status']}"
        ),
        (
            "  Cumulative            "
            f"{contract['tail']['cumulative']['status']}"
        ),
        (
            "  Temporal Perturbation "
            f"{contract['tail']['temporal_perturbation']['status']}"
        ),
        "",
        "MAD Validation:",
        f"  Local                 {contract['mad']['local']['status']}",
        f"  Cumulative            {contract['mad']['cumulative']['status']}",
        (
            "  Temporal Perturbation "
            f"{contract['mad']['temporal_perturbation']['status']}"
        ),
        "",
        (
            "Evidence Sufficiency : "
            f"{contract['evidence_sufficiency']['status']}"
        ),
        "Common Method N       : REQUIRED",
        "Common Horizon N      : REQUIRED",
        "EPT Reference Gate    : EXCLUDED",
        "",
        (
            "Reference Adequacy / Minimum Prior Observations / "
            "Recommended Support : "
            f"{policy['reference_adequacy']} / "
            f"{policy['minimum_prior_observations']} / "
            f"{policy['recommended_support']}"
        ),
        (
            "Holdout locked / accessed / ready : "
            f"{artifact['holdout_locked']} / "
            f"{artifact['holdout_accessed']} / "
            f"{policy['ready_for_holdout']}"
        ),
        (
            "RATE_SPIKE / Network / Macro DB writes / Production : "
            f"{policy['rate_spike_state']} / "
            f"{artifact['network_requests']} / "
            f"{artifact['macro_db_writes']} / "
            f"{artifact['production_impact']}"
        ),
        "",
        f"Protocol status: {policy['protocol_status']}",
        (
            "B.1.7 readiness: BLOCKED "
            f"({len(artifact['blockers'])} unresolved protocol blockers)"
        ),
    ]
    return "\n".join(lines)
