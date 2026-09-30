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
PROTOCOL_STATUS = "BLOCKED_UNRESOLVED_ADEQUACY_CRITERIA"
REFERENCE_MODE = "EXPANDING_STRICTLY_PRIOR"
COMMON_N_POLICY = "COMMON_N_FIRST"
FAMILY_COMBINATION_RULE = "ALL_FAMILIES_AND"
NO_MATCH_RESULT = "NO_SUPPORTED_BOUNDARY"

TAIL_FORWARD_ENVELOPE_BLOCKER = "TAIL_FORWARD_ENVELOPE_TOLERANCE_UNJUSTIFIED"
MAD_FORWARD_ENVELOPE_BLOCKER = "MAD_FORWARD_ENVELOPE_TOLERANCES_UNJUSTIFIED"
VALIDATION_SUFFIX_BLOCKER = "VALIDATION_SUFFIX_SUFFICIENCY_UNRESOLVED"


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


def _diagnostic_temporal_perturbation(*, metric_scope: str) -> dict[str, Any]:
    return {
        "metric_scope": metric_scope,
        "perturbation_rule": (
            "TIME_ORDER_PRESERVING_CONTIGUOUS_STRICTLY_PRIOR_SEGMENT"
        ),
        "role": "OPTIONAL_DIAGNOSTIC_ONLY",
        "adequacy_gate": False,
        "segment_length_required": False,
        "segment_length": None,
        "tolerance_required": False,
        "tolerance": None,
        "selection_input": False,
        "status": "DEFINED_OPTIONAL_DIAGNOSTIC_ONLY",
    }


def _tail_validation_contract() -> dict[str, Any]:
    return {
        "local_append": {
            "metric": "ECDF_SUP_DRIFT",
            "comparison": "N_MINUS_1_TO_N",
            "reference_support": "OBSERVED_VALUES_UNION_ONLY",
            "invented_x_grid_points": 0,
            "role": "DIAGNOSTIC_ONLY",
            "adequacy_gate": False,
            "tolerance_required": False,
            "tolerance": None,
            "selection_input": False,
            "rationale": (
                "Single-append ECDF drift is descriptive only because expanding "
                "sample growth mechanically reduces one-observation influence."
            ),
            "status": "DEFINED_DIAGNOSTIC_ONLY",
        },
        "forward_envelope": {
            "metric": "ECDF_SUP_DISTANCE",
            "comparison": "BOUNDARY_ANCHOR_TO_EVERY_LATER_REFERENCE",
            "reference_support": "OBSERVED_VALUES_UNION_ONLY",
            "invented_x_grid_points": 0,
            "path_rule": "PRESERVE_EVERY_LATER_COMPARISON",
            "aggregation": "MAX_OVER_VALIDATION_SUFFIX",
            "tolerance": _unjustified_tolerance(
                "ABSOLUTE_PROBABILITY_DIFFERENCE"
            ),
            "status": "DEFINED_METRIC_UNJUSTIFIED_TOLERANCE",
        },
        "temporal_perturbation": _diagnostic_temporal_perturbation(
            metric_scope="ECDF_SUP_DISTANCE"
        ),
        "weighted_stability_score": None,
    }


def _mad_validation_contract() -> dict[str, Any]:
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
            "selection_input": False,
            "status": "DEFINED_DIAGNOSTIC_ONLY",
        },
        "forward_envelope": {
            "metrics": [
                "ABSOLUTE_MEDIAN_SHIFT",
                "ABSOLUTE_MAD_SHIFT",
                "RELATIVE_MAD_SHIFT",
            ],
            "comparison": "BOUNDARY_ANCHOR_TO_EVERY_LATER_REFERENCE",
            "path_rule": "PRESERVE_EVERY_LATER_COMPARISON",
            "per_metric_aggregation": "MAX_OVER_VALIDATION_SUFFIX",
            "combination_rule": "ALL_AND",
            "tolerances": {
                "absolute_median_shift": _unjustified_tolerance("BASIS_POINT"),
                "absolute_mad_shift": _unjustified_tolerance("BASIS_POINT"),
                "relative_mad_shift": _unjustified_tolerance("RATIO"),
            },
            "status": "DEFINED_METRICS_UNJUSTIFIED_TOLERANCES",
        },
        "temporal_perturbation": _diagnostic_temporal_perturbation(
            metric_scope="MEDIAN_MAD_SHIFT"
        ),
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
        "acceptance_form": "MAX_ENVELOPE_WITHOUT_SEPARATE_VIOLATION_BUDGET",
        "separate_violation_budget_required": False,
        "exceedance_count_role": "DIAGNOSTIC_ONLY",
        "status": "UNRESOLVED_SUFFIX_SUFFICIENCY",
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
        "candidate_support_universe": "B15_COMMON_SUPPORT_REVIEW_POINTS_ONLY",
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
        "boundary_validation": {
            "rule": "BOUNDARY_ANCHORED_FORWARD_ENVELOPE",
            "candidate_support_universe": "B15_COMMON_SUPPORT_REVIEW_POINTS_ONLY",
            "every_later_reference_required": True,
            "fixed_comparison_interval_required": False,
            "method_specific_interval_forbidden": True,
            "horizon_specific_interval_forbidden": True,
        },
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
        "r2_review": "PARTIAL_STRUCTURAL_REDUCTION",
        "notes": [
            (
                "The protocol is Development-informed and must not be described "
                "as ex-ante to Development."
            ),
            (
                "Candidate/signal/episode survival may explain policy impact but "
                "must not choose or relax adequacy tolerances."
            ),
            (
                "R2 removed fixed cumulative intervals, perturbation gates, a "
                "separate MAD local tolerance gate, and a separate violation "
                "budget from the adequacy decision."
            ),
        ],
    }
    blockers = [
        TAIL_FORWARD_ENVELOPE_BLOCKER,
        MAD_FORWARD_ENVELOPE_BLOCKER,
        VALIDATION_SUFFIX_BLOCKER,
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
        "ready_for_evidence_generation": True,
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


def _assert_diagnostic_only(section: dict[str, Any], label: str) -> None:
    if section.get("adequacy_gate") is not False:
        raise ValueError(f"{label} cannot become an adequacy gate.")
    if section.get("tolerance_required") is not False:
        raise ValueError(f"{label} cannot require a tolerance.")
    if section.get("selection_input") is not False:
        raise ValueError(f"{label} cannot become a selection input.")


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
    if history.get("r2_review") != "PARTIAL_STRUCTURAL_REDUCTION":
        raise ValueError("B.1.6 V3 must record the R2 structural review.")

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

    boundary = contract.get("boundary_validation") or {}
    if boundary.get("rule") != "BOUNDARY_ANCHORED_FORWARD_ENVELOPE":
        raise ValueError("Boundary validation must use the forward envelope.")
    if boundary.get("candidate_support_universe") != (
        "B15_COMMON_SUPPORT_REVIEW_POINTS_ONLY"
    ):
        raise ValueError("Boundary candidate universe changed.")
    if boundary.get("every_later_reference_required") is not True:
        raise ValueError("Every later reference comparison must be preserved.")
    if boundary.get("fixed_comparison_interval_required") is not False:
        raise ValueError("Fixed cumulative K must remain eliminated.")

    tail = contract.get("tail") or {}
    if tail.get("weighted_stability_score") is not None:
        raise ValueError("TAIL weighted stability score is forbidden.")
    local_append = tail.get("local_append") or {}
    if local_append.get("role") != "DIAGNOSTIC_ONLY":
        raise ValueError("TAIL local append must remain diagnostic-only.")
    _assert_diagnostic_only(local_append, "TAIL local append")
    if local_append.get("tolerance") is not None:
        raise ValueError("TAIL local append cannot carry an adequacy tolerance.")
    if local_append.get("status") != "DEFINED_DIAGNOSTIC_ONLY":
        raise ValueError("TAIL local append diagnostic status mismatch.")

    tail_envelope = tail.get("forward_envelope") or {}
    if tail_envelope.get("comparison") != (
        "BOUNDARY_ANCHOR_TO_EVERY_LATER_REFERENCE"
    ):
        raise ValueError("TAIL envelope comparison changed.")
    if tail_envelope.get("reference_support") != "OBSERVED_VALUES_UNION_ONLY":
        raise ValueError("TAIL envelope must use observed support only.")
    if int(tail_envelope.get("invented_x_grid_points") or 0) != 0:
        raise ValueError("TAIL envelope cannot invent x-grid points.")
    if tail_envelope.get("aggregation") != "MAX_OVER_VALIDATION_SUFFIX":
        raise ValueError("TAIL envelope aggregation changed.")
    _assert_unjustified_tolerance(tail_envelope["tolerance"])

    tail_perturbation = tail.get("temporal_perturbation") or {}
    if tail_perturbation.get("role") != "OPTIONAL_DIAGNOSTIC_ONLY":
        raise ValueError("TAIL perturbation must remain optional diagnostic-only.")
    _assert_diagnostic_only(tail_perturbation, "TAIL perturbation")
    if tail_perturbation.get("segment_length_required") is not False:
        raise ValueError("TAIL perturbation segment length cannot be required.")
    if tail_perturbation.get("segment_length") is not None:
        raise ValueError("TAIL perturbation segment length must stay unset.")
    if tail_perturbation.get("tolerance") is not None:
        raise ValueError("TAIL perturbation tolerance must stay unset.")

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

    mad_local = mad.get("local") or {}
    if mad_local.get("role") != "DIAGNOSTIC_ONLY":
        raise ValueError("MAD local transitions must remain diagnostic-only.")
    _assert_diagnostic_only(mad_local, "MAD local transition")
    if mad_local.get("tolerances") is not None:
        raise ValueError("MAD local diagnostic cannot carry tolerances.")

    mad_envelope = mad.get("forward_envelope") or {}
    if mad_envelope.get("comparison") != (
        "BOUNDARY_ANCHOR_TO_EVERY_LATER_REFERENCE"
    ):
        raise ValueError("MAD envelope comparison changed.")
    if mad_envelope.get("per_metric_aggregation") != (
        "MAX_OVER_VALIDATION_SUFFIX"
    ):
        raise ValueError("MAD envelope aggregation changed.")
    if mad_envelope.get("combination_rule") != "ALL_AND":
        raise ValueError("MAD envelope metrics must use logical AND.")
    for tolerance in mad_envelope["tolerances"].values():
        _assert_unjustified_tolerance(tolerance)

    mad_perturbation = mad.get("temporal_perturbation") or {}
    if mad_perturbation.get("role") != "OPTIONAL_DIAGNOSTIC_ONLY":
        raise ValueError("MAD perturbation must remain optional diagnostic-only.")
    _assert_diagnostic_only(mad_perturbation, "MAD perturbation")
    if mad_perturbation.get("segment_length_required") is not False:
        raise ValueError("MAD perturbation segment length cannot be required.")
    if mad_perturbation.get("segment_length") is not None:
        raise ValueError("MAD perturbation segment length must stay unset.")
    if mad_perturbation.get("tolerance") is not None:
        raise ValueError("MAD perturbation tolerance must stay unset.")

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
    if sufficiency.get("acceptance_form") != (
        "MAX_ENVELOPE_WITHOUT_SEPARATE_VIOLATION_BUDGET"
    ):
        raise ValueError("Evidence sufficiency acceptance form changed.")
    if sufficiency.get("separate_violation_budget_required") is not False:
        raise ValueError("Separate violation budget must remain eliminated.")
    if sufficiency.get("exceedance_count_role") != "DIAGNOSTIC_ONLY":
        raise ValueError("Exceedance counts can only be diagnostic.")

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
    if selection.get("candidate_support_universe") != (
        "B15_COMMON_SUPPORT_REVIEW_POINTS_ONLY"
    ):
        raise ValueError("Candidate support universe changed.")

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
        "ready_for_evidence_generation": True,
        "ready_for_b17": False,
        "ready_for_b2": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    if policy != expected_policy:
        raise ValueError("Reference adequacy protocol policy state changed.")

    blockers = list(artifact.get("blockers") or [])
    expected_blockers = [
        TAIL_FORWARD_ENVELOPE_BLOCKER,
        MAD_FORWARD_ENVELOPE_BLOCKER,
        VALIDATION_SUFFIX_BLOCKER,
    ]
    if blockers != expected_blockers:
        raise ValueError("B.1.6 V3 blocker set changed unexpectedly.")

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
        "ready_for_evidence_generation": True,
        "ready_for_holdout": False,
    }


def render_reference_adequacy_protocol_text(
    artifact: dict[str, Any],
) -> str:
    validate_reference_adequacy_protocol(artifact)
    contract = artifact["validation_contract"]
    policy = artifact["policy_state"]

    lines = [
        "NEXT-6B-S4.2-B.1.6 REFERENCE ADEQUACY VALIDATION PROTOCOL V3",
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
            "  Forward Envelope      "
            f"{contract['tail']['forward_envelope']['status']}"
        ),
        (
            "  Temporal Perturbation "
            f"{contract['tail']['temporal_perturbation']['status']}"
        ),
        "",
        "MAD Validation:",
        f"  Local                 {contract['mad']['local']['status']}",
        (
            "  Forward Envelope      "
            f"{contract['mad']['forward_envelope']['status']}"
        ),
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
            "Evidence generation / B.2 / Holdout ready : "
            f"{policy['ready_for_evidence_generation']} / "
            f"{policy['ready_for_b2']} / "
            f"{policy['ready_for_holdout']}"
        ),
        (
            "Holdout locked / accessed : "
            f"{artifact['holdout_locked']} / "
            f"{artifact['holdout_accessed']}"
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
            "Unresolved adequacy classes: "
            f"{len(artifact['blockers'])}"
        ),
    ]
    return "\n".join(lines)
