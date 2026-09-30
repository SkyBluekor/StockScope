from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.macro.calibration_candidate import (
    RATE_SPIKE_FEATURE_IDS,
    RATE_SPIKE_METHODS,
    build_rate_spike_candidate_set,
    evaluate_candidate_behavior,
    validate_candidate_set_artifact,
)
from app.macro.candidate_behavior import build_method_overlap_matrix
from app.macro.candidate_compression import (
    build_compressed_candidate_frontier,
    validate_compressed_frontier_artifact,
)
from app.macro.identity import content_hash


RATE_SPIKE_ADMISSIBILITY_POLICY_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_1_RATE_SPIKE_ADMISSIBILITY_POLICY_V1"
)
RATE_SPIKE_FRONTIER_DIAGNOSTIC_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_1R_RATE_SPIKE_FRONTIER_DIAGNOSTIC_V1"
)
RATE_SPIKE_FAMILY_DIAGNOSTIC_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_1R_RATE_SPIKE_FAMILY_DIAGNOSTIC_V1"
)


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Admissibility diagnostic metric must be finite.")
    return result


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _decimal_range(values: list[Any]) -> dict[str, str | None]:
    if not values:
        return {"min": None, "max": None}
    decimals = [_decimal(value) for value in values]
    return {
        "min": _decimal_text(min(decimals)),
        "max": _decimal_text(max(decimals)),
    }


def _int_range(values: list[int]) -> dict[str, int | None]:
    if not values:
        return {"min": None, "max": None}
    return {"min": min(values), "max": max(values)}


def classify_positive_capture_for_admissibility(value: Any) -> str:
    """Describe capture without inventing a sub-100% admissibility cutoff."""
    capture = _decimal(value)
    if capture < 0 or capture > 1:
        raise ValueError("Positive capture fraction must be between 0 and 1.")
    if capture == 1:
        return "TRIVIAL_DIRECTION_RULE"
    return "DIAGNOSTIC_ONLY"


def build_unset_rate_spike_admissibility_policy() -> dict[str, Any]:
    return {
        "contract_version": RATE_SPIKE_ADMISSIBILITY_POLICY_CONTRACT_VERSION,
        "policy_id": "RATE_SPIKE_ADMISSIBILITY_UNSET",
        "policy_version": "UNSET",
        "shock_type": "RATE_SPIKE",
        "direction": "UP",
        "event_unit": "UNSET",
        "maximum_signal_fraction": None,
        "maximum_positive_capture": None,
        "maximum_episode_rate": None,
        "minimum_year_coverage": None,
        "minimum_sample": None,
        "evaluation_rule": "UNSET",
        "status": "UNDEFINED",
        "approved": False,
        "production_decision_approved": False,
    }


def _candidate_signal_set(
    *,
    feature_result: dict[str, Any],
    candidate: dict[str, Any],
) -> frozenset[str]:
    rows = evaluate_candidate_behavior(
        feature_result=feature_result,
        candidate=candidate,
    )
    return frozenset(
        str(row["row_hash"]) for row in rows if bool(row["signal"])
    )


def _nested_behavior_summary(
    *,
    feature_result: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if not candidates:
        return {
            "status": "NO_CANDIDATES",
            "distinct_signal_set_count": 0,
            "adjacent_comparison_count": 0,
            "non_nested_adjacent_count": 0,
        }

    signal_sets = [
        _candidate_signal_set(
            feature_result=feature_result,
            candidate=candidate,
        )
        for candidate in candidates
    ]
    distinct = sorted(
        set(signal_sets),
        key=lambda item: (len(item), tuple(sorted(item))),
    )
    non_nested = 0
    for left, right in zip(distinct, distinct[1:]):
        if not left.issubset(right):
            non_nested += 1

    return {
        "status": (
            "FULLY_NESTED"
            if non_nested == 0
            else "NOT_FULLY_NESTED"
        ),
        "distinct_signal_set_count": len(distinct),
        "adjacent_comparison_count": max(0, len(distinct) - 1),
        "non_nested_adjacent_count": non_nested,
    }


def _family_diagnostic(
    *,
    feature_id: str,
    method: str,
    frontier_groups: list[dict[str, Any]],
    candidate_by_hash: dict[str, dict[str, Any]],
    feature_result: dict[str, Any],
) -> dict[str, Any]:
    groups = [
        group
        for group in frontier_groups
        if group["feature_id"] == feature_id
        and method in set(str(item) for item in group["source_methods"])
    ]
    candidate_hashes = sorted(
        {
            str(ref["candidate_hash"])
            for group in groups
            for ref in group["source_refs"]
            if str(ref["method"]) == method
        }
    )
    candidates = [candidate_by_hash[item] for item in candidate_hashes]

    threshold_units = sorted(
        {str(candidate["threshold_unit"]) for candidate in candidates}
    )
    if len(threshold_units) > 1:
        raise ValueError("A feature/method family cannot mix threshold units.")

    yearly_episode_counts: list[int] = []
    signal_row_counts: list[int] = []
    episode_counts: list[int] = []
    for candidate in candidates:
        episode_summary = candidate["episode_summary"]
        signal_row_counts.append(int(episode_summary["signal_row_count"]))
        episode_count = int(episode_summary["episode_count"])
        episode_counts.append(episode_count)
        yearly = dict(episode_summary.get("yearly_episode_counts") or {})
        years = sorted(str(year) for year in candidate["year_signal_counts"])
        yearly_episode_counts.extend(int(yearly.get(year, 0)) for year in years)

    captures = [
        group["positive_move_capture_fraction"]
        for group in groups
        if group["positive_move_capture_fraction"] is not None
    ]
    capture_classifications = {
        "TRIVIAL_DIRECTION_RULE": 0,
        "DIAGNOSTIC_ONLY": 0,
    }
    for value in captures:
        capture_classifications[
            classify_positive_capture_for_admissibility(value)
        ] += 1

    if capture_classifications["TRIVIAL_DIRECTION_RULE"]:
        raise ValueError(
            "Exact all-positive behavior must be removed before admissibility diagnostics."
        )

    payload = {
        "contract_version": RATE_SPIKE_FAMILY_DIAGNOSTIC_CONTRACT_VERSION,
        "feature_id": feature_id,
        "method": method,
        "candidate_count": len(candidates),
        "unique_behavior_count": len(groups),
        "candidate_hashes": candidate_hashes,
        "behavior_group_hashes": sorted(
            str(group["behavior_group_hash"]) for group in groups
        ),
        "threshold_unit": threshold_units[0] if threshold_units else None,
        "threshold_value_range": _decimal_range(
            [candidate["threshold_value"] for candidate in candidates]
        ),
        "signal_fraction_range": _decimal_range(
            [group["signal_fraction"] for group in groups]
        ),
        "positive_capture_fraction_range": _decimal_range(captures),
        "signal_row_count_range": _int_range(signal_row_counts),
        "episode_count_range": _int_range(episode_counts),
        "episode_start_count_range": _int_range(episode_counts),
        "yearly_episode_count_range": _int_range(yearly_episode_counts),
        "positive_capture_classification_counts": capture_classifications,
        "nested_behavior": _nested_behavior_summary(
            feature_result=feature_result,
            candidates=candidates,
        ),
        "admissibility_decision": "NOT_DEFINED",
        "automatic_rejection_count": 0,
        "holdout_accessed": False,
        "production_decision_approved": False,
    }
    family_hash = content_hash(payload)
    return {
        **payload,
        "family_id": f"RATEFAM-{family_hash[:16]}",
        "family_hash": family_hash,
    }


def build_frontier_admissibility_diagnostic(
    *,
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
    research: dict[str, Any],
) -> dict[str, Any]:
    candidate_set = build_rate_spike_candidate_set(
        development_dataset=development_dataset,
        protocol=protocol,
        research=research,
    )
    validate_candidate_set_artifact(candidate_set)

    frontier = build_compressed_candidate_frontier(
        development_dataset=development_dataset,
        protocol=protocol,
        research=research,
    )
    validate_compressed_frontier_artifact(frontier)

    if frontier["stage_manifest"]["v1_candidate_set_hash"] != candidate_set[
        "candidate_set_hash"
    ]:
        raise ValueError("S4 and S4.1 replay identities do not match.")
    if frontier["holdout_locked"] is not True or frontier["holdout_accessed"] is not False:
        raise ValueError("S4.1R requires locked and unread Holdout.")

    candidate_by_hash = {
        str(candidate["candidate_hash"]): candidate
        for candidate in candidate_set["frozen_candidates"]
    }
    families: list[dict[str, Any]] = []
    feature_diagnostics: dict[str, Any] = {}

    for feature_id in RATE_SPIKE_FEATURE_IDS:
        feature_groups = [
            group
            for group in frontier["frontier_groups"]
            if group["feature_id"] == feature_id
        ]
        feature_families = []
        for method in RATE_SPIKE_METHODS:
            family = _family_diagnostic(
                feature_id=feature_id,
                method=method,
                frontier_groups=frontier["frontier_groups"],
                candidate_by_hash=candidate_by_hash,
                feature_result=research["feature_results"][feature_id],
            )
            families.append(family)
            feature_families.append(family["family_hash"])

        feature_diagnostics[feature_id] = {
            "family_hashes": feature_families,
            "structural_method_overlap_matrix": frontier["per_feature"][
                feature_id
            ]["method_overlap_matrix"],
            "frontier_method_overlap_matrix": build_method_overlap_matrix(
                feature_groups,
                RATE_SPIKE_METHODS,
            ),
            "compressed_frontier_count": len(feature_groups),
        }

    families.sort(key=lambda item: (item["feature_id"], item["method"]))
    family_payload_hash = content_hash(families)
    feature_payload_hash = content_hash(feature_diagnostics)

    policy = build_unset_rate_spike_admissibility_policy()
    readiness = {
        "candidate_generation": "COMPLETE",
        "structural_compression": "COMPLETE",
        "behavior_rarity_diagnostics": "COMPLETE",
        "admissibility_policy": "UNDEFINED",
        "event_unit_defined": False,
        "evaluation_rule_defined": False,
        "ready_for_holdout": False,
        "blockers": [
            "ADMISSIBILITY_POLICY_UNDEFINED",
            "EVENT_UNIT_UNSET",
            "EVALUATION_RULE_UNDEFINED",
        ],
    }

    frontier_candidate_hashes = sorted(
        {
            str(ref["candidate_hash"])
            for group in frontier["frontier_groups"]
            for ref in group["source_refs"]
        }
    )
    frontier_candidates = [
        candidate_by_hash[item] for item in frontier_candidate_hashes
    ]
    event_unit_diagnostics = {
        "event_unit": "UNSET",
        "signal_row_count_range": _int_range(
            [
                int(candidate["episode_summary"]["signal_row_count"])
                for candidate in frontier_candidates
            ]
        ),
        "episode_count_range": _int_range(
            [
                int(candidate["episode_summary"]["episode_count"])
                for candidate in frontier_candidates
            ]
        ),
        "episode_start_count_range": _int_range(
            [
                int(candidate["episode_summary"]["episode_count"])
                for candidate in frontier_candidates
            ]
        ),
        "selection_status": "NOT_SELECTED",
    }

    identity_payload = {
        "contract_version": RATE_SPIKE_FRONTIER_DIAGNOSTIC_CONTRACT_VERSION,
        "development_dataset_hash": frontier["development_dataset_hash"],
        "protocol_hash": frontier["protocol_hash"],
        "research_hash": frontier["research_hash"],
        "holdout_dataset_hash_reference": frontier[
            "holdout_dataset_hash_reference"
        ],
        "source_candidate_set_hash": candidate_set["candidate_set_hash"],
        "source_frontier_hash": frontier["frontier_hash"],
        "family_payload_hash": family_payload_hash,
        "feature_payload_hash": feature_payload_hash,
        "admissibility_policy": policy,
        "readiness": readiness,
        "event_unit_diagnostics": event_unit_diagnostics,
        "diagnostic_status": "ADMISSIBILITY_POLICY_UNDEFINED",
        "holdout_locked": True,
        "holdout_accessed": False,
        "final_candidate_selected": False,
        "rate_spike_state": "UNCALIBRATED",
        "production_decision_approved": False,
    }
    diagnostic_hash = content_hash(identity_payload)

    return {
        **identity_payload,
        "diagnostic_id": f"RATEFRONTDIAG-{diagnostic_hash[:16]}",
        "diagnostic_hash": diagnostic_hash,
        "source_frontier_id": frontier["frontier_id"],
        "compression_manifest": frontier["stage_manifest"],
        "families": families,
        "feature_diagnostics": feature_diagnostics,
        "final_threshold_selected": False,
        "minimum_sample_selected": False,
        "event_unit_selected": False,
        "normal_labels_created": 0,
        "detected_labels_created": 0,
        "network_requests": 0,
        "macro_db_writes": 0,
    }


def validate_frontier_admissibility_diagnostic(
    diagnostic: dict[str, Any],
) -> dict[str, Any]:
    if diagnostic.get("contract_version") != RATE_SPIKE_FRONTIER_DIAGNOSTIC_CONTRACT_VERSION:
        raise ValueError("Unsupported frontier diagnostic contract.")
    if diagnostic.get("holdout_locked") is not True:
        raise ValueError("S4.1R must keep Holdout locked.")
    if diagnostic.get("holdout_accessed") is not False:
        raise ValueError("S4.1R must not access Holdout.")
    if diagnostic.get("diagnostic_status") != "ADMISSIBILITY_POLICY_UNDEFINED":
        raise ValueError("S4.1R must leave admissibility policy undefined.")
    if diagnostic.get("final_candidate_selected") is not False:
        raise ValueError("S4.1R must not select a final candidate.")
    if diagnostic.get("final_threshold_selected") is not False:
        raise ValueError("S4.1R must not select a threshold.")
    if diagnostic.get("minimum_sample_selected") is not False:
        raise ValueError("S4.1R must not select minimum sample.")
    if diagnostic.get("event_unit_selected") is not False:
        raise ValueError("S4.1R must not silently select an event unit.")
    if diagnostic.get("rate_spike_state") != "UNCALIBRATED":
        raise ValueError("S4.1R RATE_SPIKE must remain UNCALIBRATED.")
    if diagnostic.get("production_decision_approved") is not False:
        raise ValueError("S4.1R must not be Production-approved.")
    if int(diagnostic.get("normal_labels_created") or 0) != 0:
        raise ValueError("S4.1R must not create NORMAL labels.")
    if int(diagnostic.get("detected_labels_created") or 0) != 0:
        raise ValueError("S4.1R must not create DETECTED labels.")
    if int(diagnostic.get("network_requests") or 0) != 0:
        raise ValueError("S4.1R diagnostics must be local-only.")
    if int(diagnostic.get("macro_db_writes") or 0) != 0:
        raise ValueError("S4.1R diagnostics must not write Macro DB.")

    policy = diagnostic.get("admissibility_policy") or {}
    expected_policy = build_unset_rate_spike_admissibility_policy()
    if policy != expected_policy:
        raise ValueError("S4.1R admissibility policy must remain explicitly UNSET.")

    readiness = diagnostic.get("readiness") or {}
    if readiness.get("ready_for_holdout") is not False:
        raise ValueError("Undefined admissibility policy cannot be ready for Holdout.")
    if readiness.get("candidate_generation") != "COMPLETE":
        raise ValueError("Candidate generation must be complete.")
    if readiness.get("structural_compression") != "COMPLETE":
        raise ValueError("Structural compression must be complete.")
    if readiness.get("behavior_rarity_diagnostics") != "COMPLETE":
        raise ValueError("Frontier diagnostics must be complete.")
    if readiness.get("admissibility_policy") != "UNDEFINED":
        raise ValueError("Admissibility policy state mismatch.")
    if readiness.get("event_unit_defined") is not False:
        raise ValueError("Event unit must remain undefined.")
    if readiness.get("evaluation_rule_defined") is not False:
        raise ValueError("Evaluation rule must remain undefined.")

    families = list(diagnostic.get("families") or [])
    expected_pairs = {
        (feature_id, method)
        for feature_id in RATE_SPIKE_FEATURE_IDS
        for method in RATE_SPIKE_METHODS
    }
    actual_pairs = {
        (str(item["feature_id"]), str(item["method"])) for item in families
    }
    if actual_pairs != expected_pairs or len(families) != len(expected_pairs):
        raise ValueError("S4.1R must report all feature/method families.")
    for family in families:
        payload = {
            key: value
            for key, value in family.items()
            if key not in {"family_id", "family_hash"}
        }
        expected_hash = content_hash(payload)
        if family.get("family_hash") != expected_hash:
            raise ValueError("Family diagnostic hash mismatch.")
        if family.get("family_id") != f"RATEFAM-{expected_hash[:16]}":
            raise ValueError("Family diagnostic id mismatch.")
        if int(family.get("automatic_rejection_count") or 0) != 0:
            raise ValueError("S4.1R must not add an admissibility rejection cutoff.")

    if diagnostic.get("family_payload_hash") != content_hash(families):
        raise ValueError("Family diagnostic payload hash mismatch.")
    feature_diagnostics = diagnostic.get("feature_diagnostics") or {}
    if diagnostic.get("feature_payload_hash") != content_hash(feature_diagnostics):
        raise ValueError("Feature diagnostic payload hash mismatch.")

    identity_payload = {
        key: diagnostic[key]
        for key in (
            "contract_version",
            "development_dataset_hash",
            "protocol_hash",
            "research_hash",
            "holdout_dataset_hash_reference",
            "source_candidate_set_hash",
            "source_frontier_hash",
            "family_payload_hash",
            "feature_payload_hash",
            "admissibility_policy",
            "readiness",
            "event_unit_diagnostics",
            "diagnostic_status",
            "holdout_locked",
            "holdout_accessed",
            "final_candidate_selected",
            "rate_spike_state",
            "production_decision_approved",
        )
    }
    expected_hash = content_hash(identity_payload)
    if diagnostic.get("diagnostic_hash") != expected_hash:
        raise ValueError("Frontier diagnostic hash mismatch.")
    if diagnostic.get("diagnostic_id") != f"RATEFRONTDIAG-{expected_hash[:16]}":
        raise ValueError("Frontier diagnostic id mismatch.")

    return {
        "diagnostic_hash": expected_hash,
        "family_count": len(families),
        "ready_for_holdout": False,
        "holdout_accessed": False,
    }


def summarize_frontier_admissibility_diagnostic(
    diagnostic: dict[str, Any],
) -> dict[str, Any]:
    manifest = diagnostic["compression_manifest"]
    return {
        "contract_version": diagnostic["contract_version"],
        "diagnostic_id": diagnostic["diagnostic_id"],
        "diagnostic_hash": diagnostic["diagnostic_hash"],
        "diagnostic_status": diagnostic["diagnostic_status"],
        "source_frontier_id": diagnostic["source_frontier_id"],
        "source_frontier_hash": diagnostic["source_frontier_hash"],
        "development_dataset_hash": diagnostic["development_dataset_hash"],
        "protocol_hash": diagnostic["protocol_hash"],
        "research_hash": diagnostic["research_hash"],
        "raw_candidate_count": manifest["raw_candidate_count"],
        "method_local_pareto_count": manifest["method_local_pareto_count"],
        "trivial_direction_removed_count": manifest[
            "trivial_direction_removed_count"
        ],
        "behavior_duplicate_removed_count": manifest[
            "behavior_duplicate_removed_count"
        ],
        "cross_method_dominated_count": manifest[
            "cross_method_dominated_count"
        ],
        "compressed_frontier_count": manifest["compressed_frontier_count"],
        "family_count": len(diagnostic["families"]),
        "admissibility_policy": diagnostic["admissibility_policy"],
        "event_unit_diagnostics": diagnostic["event_unit_diagnostics"],
        "readiness": diagnostic["readiness"],
        "holdout_locked": diagnostic["holdout_locked"],
        "holdout_accessed": diagnostic["holdout_accessed"],
        "final_threshold_selected": diagnostic["final_threshold_selected"],
        "minimum_sample_selected": diagnostic["minimum_sample_selected"],
        "event_unit_selected": diagnostic["event_unit_selected"],
        "rate_spike_state": diagnostic["rate_spike_state"],
        "normal_labels_created": diagnostic["normal_labels_created"],
        "detected_labels_created": diagnostic["detected_labels_created"],
        "network_requests": diagnostic["network_requests"],
        "macro_db_writes": diagnostic["macro_db_writes"],
        "production_decision_approved": diagnostic[
            "production_decision_approved"
        ],
    }
