from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.macro.calibration_candidate import (
    RATE_SPIKE_FEATURE_IDS,
    RATE_SPIKE_METHODS,
    build_rate_spike_candidate_set,
    validate_candidate_set_artifact,
)
from app.macro.candidate_behavior import (
    MACRO_CANDIDATE_BEHAVIOR_GROUP_CONTRACT_VERSION,
    build_behavior_groups,
    build_method_overlap_matrix,
)
from app.macro.identity import content_hash


MACRO_COMPRESSED_CANDIDATE_SET_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_1_COMPRESSED_CANDIDATE_SET_V2"
)
MACRO_CROSS_METHOD_DOMINANCE_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_1_CROSS_METHOD_PARETO_V1"
)
MACRO_COMPRESSION_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_1_FRONTIER_COMPRESSION_V1"
)


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Compression metric must be finite.")
    return result


def _group_dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_fraction = _decimal(left["signal_fraction"])
    right_fraction = _decimal(right["signal_fraction"])
    left_coverage = int(left["year_coverage_count"])
    right_coverage = int(right["year_coverage_count"])
    left_separation = _decimal(left["episode_separation_ratio"])
    right_separation = _decimal(right["episode_separation_ratio"])
    left_max_year = _decimal(left["max_year_signal_share"])
    right_max_year = _decimal(right["max_year_signal_share"])

    no_worse = (
        left_fraction <= right_fraction
        and left_coverage >= right_coverage
        and left_separation >= right_separation
        and left_max_year <= right_max_year
    )
    strictly_better = (
        left_fraction < right_fraction
        or left_coverage > right_coverage
        or left_separation > right_separation
        or left_max_year < right_max_year
    )
    return no_worse and strictly_better


def pareto_prune_behavior_groups(
    groups: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not groups:
        return [], []

    feature_ids = {str(group["feature_id"]) for group in groups}
    if len(feature_ids) != 1:
        raise ValueError("Cross-method Pareto cannot compare different features.")

    frontier: list[dict[str, Any]] = []
    dominated: list[dict[str, Any]] = []
    ordered = sorted(
        groups,
        key=lambda item: str(item["behavior_group_hash"]),
    )

    for index, group in enumerate(ordered):
        dominator_hash: str | None = None
        for other_index, other in enumerate(ordered):
            if index == other_index:
                continue
            if _group_dominates(other, group):
                dominator_hash = str(other["behavior_group_hash"])
                break

        if dominator_hash is None:
            frontier.append(group)
        else:
            dominated.append(
                {
                    "behavior_group_id": group["behavior_group_id"],
                    "behavior_group_hash": group["behavior_group_hash"],
                    "feature_id": group["feature_id"],
                    "signal_count": group["signal_count"],
                    "signal_fraction": group["signal_fraction"],
                    "year_coverage_count": group["year_coverage_count"],
                    "episode_count": group["episode_count"],
                    "episode_separation_ratio": group[
                        "episode_separation_ratio"
                    ],
                    "max_year_signal_share": group[
                        "max_year_signal_share"
                    ],
                    "source_candidate_count": group[
                        "source_candidate_count"
                    ],
                    "source_methods": list(group["source_methods"]),
                    "dominated_by_group_hash": dominator_hash,
                    "dominance_contract_version": (
                        MACRO_CROSS_METHOD_DOMINANCE_CONTRACT_VERSION
                    ),
                }
            )

    frontier.sort(key=lambda item: str(item["behavior_group_hash"]))
    dominated.sort(key=lambda item: str(item["behavior_group_hash"]))
    return frontier, dominated


def _trivial_source_refs(
    *,
    candidate_set: dict[str, Any],
    trivial_hashes: set[str],
) -> list[dict[str, Any]]:
    by_hash = {
        str(candidate["candidate_hash"]): candidate
        for candidate in candidate_set["frozen_candidates"]
    }
    refs: list[dict[str, Any]] = []
    for candidate_hash in sorted(trivial_hashes):
        candidate = by_hash[candidate_hash]
        refs.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_hash": candidate_hash,
                "feature_id": candidate["feature_id"],
                "method": candidate["method"],
                "threshold_definition": candidate[
                    "threshold_definition"
                ],
                "threshold_value": candidate["threshold_value"],
                "threshold_unit": candidate["threshold_unit"],
                "removal_reason": "TRIVIAL_DIRECTION_RULE",
            }
        )
    return refs


def build_compressed_candidate_frontier(
    *,
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
    research: dict[str, Any],
) -> dict[str, Any]:
    v1 = build_rate_spike_candidate_set(
        development_dataset=development_dataset,
        protocol=protocol,
        research=research,
    )
    validate_candidate_set_artifact(v1)

    if v1["holdout_locked"] is not True or v1["holdout_accessed"] is not False:
        raise ValueError("S4.1 requires a locked, unread Holdout.")

    per_feature: dict[str, Any] = {}
    all_groups: list[dict[str, Any]] = []
    all_frontier: list[dict[str, Any]] = []
    all_cross_dominated: list[dict[str, Any]] = []
    all_trivial_hashes: set[str] = set()

    for feature_id in RATE_SPIKE_FEATURE_IDS:
        feature_candidates = [
            candidate
            for candidate in v1["frozen_candidates"]
            if candidate["feature_id"] == feature_id
        ]
        grouping = build_behavior_groups(
            feature_id=feature_id,
            feature_result=research["feature_results"][feature_id],
            candidates=feature_candidates,
        )
        groups = grouping["behavior_groups"]
        frontier, cross_dominated = pareto_prune_behavior_groups(groups)
        overlap = build_method_overlap_matrix(groups, RATE_SPIKE_METHODS)

        frontier_hashes = [
            str(group["behavior_group_hash"]) for group in frontier
        ]
        cross_dominated_hashes = [
            str(group["behavior_group_hash"]) for group in cross_dominated
        ]
        if len(set(frontier_hashes)) != len(frontier_hashes):
            raise ValueError("Compressed frontier contains duplicate groups.")

        per_feature[feature_id] = {
            "method_local_pareto_count": len(feature_candidates),
            "trivial_direction_removed_count": grouping[
                "trivial_direction_removed_count"
            ],
            "nontrivial_candidate_count": grouping[
                "nontrivial_candidate_count"
            ],
            "unique_behavior_group_count": grouping[
                "unique_behavior_group_count"
            ],
            "behavior_duplicate_removed_count": grouping[
                "behavior_duplicate_removed_count"
            ],
            "cross_method_dominated_count": len(cross_dominated),
            "compressed_frontier_count": len(frontier),
            "method_overlap_matrix": overlap,
            "frontier_group_hashes": frontier_hashes,
            "cross_method_dominated_group_hashes": cross_dominated_hashes,
        }

        all_groups.extend(groups)
        all_frontier.extend(frontier)
        all_cross_dominated.extend(cross_dominated)
        all_trivial_hashes.update(
            grouping["trivial_direction_candidate_hashes"]
        )

    all_groups.sort(
        key=lambda item: (
            str(item["feature_id"]),
            str(item["behavior_group_hash"]),
        )
    )
    all_frontier.sort(
        key=lambda item: (
            str(item["feature_id"]),
            str(item["behavior_group_hash"]),
        )
    )
    all_cross_dominated.sort(
        key=lambda item: (
            str(item["feature_id"]),
            str(item["behavior_group_hash"]),
        )
    )

    raw_count = int(
        v1["exploration_manifest"]["generated_candidate_count"]
    )
    method_pareto_count = int(
        v1["exploration_manifest"]["frozen_candidate_count"]
    )
    trivial_removed_count = len(all_trivial_hashes)
    nontrivial_count = method_pareto_count - trivial_removed_count
    unique_behavior_count = len(all_groups)
    duplicate_removed_count = nontrivial_count - unique_behavior_count
    cross_dominated_count = len(all_cross_dominated)
    compressed_count = len(all_frontier)

    if duplicate_removed_count < 0:
        raise ValueError("Behavior grouping accounting is invalid.")
    if unique_behavior_count - cross_dominated_count != compressed_count:
        raise ValueError("Cross-method Pareto accounting is invalid.")

    trivial_refs = _trivial_source_refs(
        candidate_set=v1,
        trivial_hashes=all_trivial_hashes,
    )

    stage_manifest = {
        "compression_contract_version": MACRO_COMPRESSION_CONTRACT_VERSION,
        "behavior_group_contract_version": (
            MACRO_CANDIDATE_BEHAVIOR_GROUP_CONTRACT_VERSION
        ),
        "cross_method_dominance_contract_version": (
            MACRO_CROSS_METHOD_DOMINANCE_CONTRACT_VERSION
        ),
        "v1_candidate_set_hash": v1["candidate_set_hash"],
        "raw_candidate_count": raw_count,
        "v1_method_local_dominated_count": int(
            v1["exploration_manifest"]["dominated_candidate_count"]
        ),
        "method_local_pareto_count": method_pareto_count,
        "trivial_direction_removed_count": trivial_removed_count,
        "nontrivial_candidate_count": nontrivial_count,
        "behavior_duplicate_removed_count": duplicate_removed_count,
        "unique_behavior_group_count": unique_behavior_count,
        "cross_method_dominated_count": cross_dominated_count,
        "compressed_frontier_count": compressed_count,
        "trivial_direction_candidate_hashes": sorted(all_trivial_hashes),
        "behavior_group_hashes": sorted(
            str(group["behavior_group_hash"]) for group in all_groups
        ),
        "frontier_group_hashes": sorted(
            str(group["behavior_group_hash"]) for group in all_frontier
        ),
        "cross_method_dominated_group_hashes": sorted(
            str(group["behavior_group_hash"])
            for group in all_cross_dominated
        ),
        "behavior_group_payload_hash": content_hash(all_groups),
        "frontier_group_payload_hash": content_hash(all_frontier),
        "cross_method_dominated_summary_hash": content_hash(
            all_cross_dominated
        ),
        "trivial_direction_summary_hash": content_hash(trivial_refs),
        "per_feature_payload_hash": content_hash(per_feature),
    }

    status = (
        "FRONTIER_COMPRESSED"
        if compressed_count < method_pareto_count
        else "FRONTIER_STRUCTURALLY_LARGE"
    )
    identity_payload = {
        "contract_version": MACRO_COMPRESSED_CANDIDATE_SET_CONTRACT_VERSION,
        "development_dataset_hash": v1["development_dataset_hash"],
        "protocol_hash": v1["protocol_hash"],
        "research_hash": v1["research_hash"],
        "holdout_dataset_hash_reference": v1[
            "holdout_dataset_hash_reference"
        ],
        "stage_manifest": stage_manifest,
        "frontier_status": status,
        "holdout_locked": True,
        "holdout_accessed": False,
        "final_candidate_selected": False,
        "rate_spike_state": "UNCALIBRATED",
        "production_decision_approved": False,
    }
    frontier_hash = content_hash(identity_payload)

    return {
        "contract_version": MACRO_COMPRESSED_CANDIDATE_SET_CONTRACT_VERSION,
        "frontier_id": f"RATEFRONT-{frontier_hash[:16]}",
        "frontier_hash": frontier_hash,
        "frontier_status": status,
        "development_dataset_hash": v1["development_dataset_hash"],
        "protocol_hash": v1["protocol_hash"],
        "research_hash": v1["research_hash"],
        "holdout_dataset_hash_reference": v1[
            "holdout_dataset_hash_reference"
        ],
        "holdout_locked": True,
        "holdout_accessed": False,
        "stage_manifest": stage_manifest,
        "per_feature": per_feature,
        "trivial_direction_candidates": trivial_refs,
        "behavior_groups": all_groups,
        "frontier_groups": all_frontier,
        "cross_method_dominated_groups": all_cross_dominated,
        "final_candidate_selected": False,
        "selected_behavior_group_id": None,
        "selected_behavior_group_hash": None,
        "minimum_sample_selected": False,
        "rate_spike_state": "UNCALIBRATED",
        "normal_labels_created": 0,
        "detected_labels_created": 0,
        "network_requests": 0,
        "macro_db_writes": 0,
        "production_decision_approved": False,
    }


def validate_compressed_frontier_artifact(
    frontier: dict[str, Any],
) -> dict[str, Any]:
    if (
        frontier.get("contract_version")
        != MACRO_COMPRESSED_CANDIDATE_SET_CONTRACT_VERSION
    ):
        raise ValueError("Unsupported compressed frontier contract.")
    if frontier.get("holdout_locked") is not True:
        raise ValueError("Compressed frontier must keep Holdout locked.")
    if frontier.get("holdout_accessed") is not False:
        raise ValueError("Compressed frontier must not access Holdout.")
    if frontier.get("final_candidate_selected") is not False:
        raise ValueError("S4.1 must not select a final candidate.")
    if frontier.get("selected_behavior_group_id") is not None:
        raise ValueError("S4.1 selected behavior group id must be null.")
    if frontier.get("selected_behavior_group_hash") is not None:
        raise ValueError("S4.1 selected behavior group hash must be null.")
    if frontier.get("minimum_sample_selected") is not False:
        raise ValueError("S4.1 must not select minimum sample.")
    if frontier.get("rate_spike_state") != "UNCALIBRATED":
        raise ValueError("S4.1 RATE_SPIKE must remain UNCALIBRATED.")
    if int(frontier.get("normal_labels_created") or 0) != 0:
        raise ValueError("S4.1 must not create NORMAL labels.")
    if int(frontier.get("detected_labels_created") or 0) != 0:
        raise ValueError("S4.1 must not create DETECTED labels.")
    if frontier.get("production_decision_approved") is not False:
        raise ValueError("S4.1 must not be Production-approved.")

    manifest = frontier.get("stage_manifest") or {}
    groups = list(frontier.get("behavior_groups") or [])
    frontier_groups = list(frontier.get("frontier_groups") or [])
    dominated = list(frontier.get("cross_method_dominated_groups") or [])
    trivial_refs = list(frontier.get("trivial_direction_candidates") or [])
    per_feature = frontier.get("per_feature") or {}

    if manifest.get("behavior_group_payload_hash") != content_hash(groups):
        raise ValueError("Behavior group payload hash mismatch.")
    if manifest.get("frontier_group_payload_hash") != content_hash(
        frontier_groups
    ):
        raise ValueError("Frontier group payload hash mismatch.")
    if manifest.get("cross_method_dominated_summary_hash") != content_hash(
        dominated
    ):
        raise ValueError("Cross-method dominated summary hash mismatch.")
    if manifest.get("trivial_direction_summary_hash") != content_hash(
        trivial_refs
    ):
        raise ValueError("Trivial-direction summary hash mismatch.")
    if manifest.get("per_feature_payload_hash") != content_hash(per_feature):
        raise ValueError("Per-feature compression payload hash mismatch.")

    raw_count = int(manifest.get("raw_candidate_count") or 0)
    method_dominated = int(
        manifest.get("v1_method_local_dominated_count") or 0
    )
    method_pareto = int(manifest.get("method_local_pareto_count") or 0)
    trivial_count = int(
        manifest.get("trivial_direction_removed_count") or 0
    )
    nontrivial_count = int(manifest.get("nontrivial_candidate_count") or 0)
    duplicate_count = int(
        manifest.get("behavior_duplicate_removed_count") or 0
    )
    unique_count = int(manifest.get("unique_behavior_group_count") or 0)
    cross_dominated_count = int(
        manifest.get("cross_method_dominated_count") or 0
    )
    compressed_count = int(
        manifest.get("compressed_frontier_count") or 0
    )
    if raw_count != method_dominated + method_pareto:
        raise ValueError("Raw candidate accounting mismatch.")
    if method_pareto != trivial_count + nontrivial_count:
        raise ValueError("Trivial-direction accounting mismatch.")
    if nontrivial_count != duplicate_count + unique_count:
        raise ValueError("Behavior grouping accounting mismatch.")
    if unique_count != cross_dominated_count + compressed_count:
        raise ValueError("Cross-method frontier accounting mismatch.")
    if trivial_count != len(trivial_refs):
        raise ValueError("Trivial-direction count mismatch.")
    if unique_count != len(groups):
        raise ValueError("Behavior group count mismatch.")
    if cross_dominated_count != len(dominated):
        raise ValueError("Cross-method dominated count mismatch.")
    if compressed_count != len(frontier_groups):
        raise ValueError("Compressed frontier count mismatch.")

    for group in groups:
        payload = {
            key: value
            for key, value in group.items()
            if key not in {"behavior_group_id", "behavior_group_hash"}
        }
        expected_group_hash = content_hash(payload)
        if group.get("behavior_group_hash") != expected_group_hash:
            raise ValueError("Behavior group hash mismatch.")
        if group.get("behavior_group_id") != (
            f"RATEBG-{expected_group_hash[:16]}"
        ):
            raise ValueError("Behavior group id mismatch.")

    behavior_hashes = [
        str(group["behavior_signature_hash"]) for group in groups
    ]
    if len(behavior_hashes) != len(set(behavior_hashes)):
        raise ValueError("Behavior groups contain duplicate signatures.")

    frontier_behavior_hashes = [
        str(group["behavior_signature_hash"]) for group in frontier_groups
    ]
    if len(frontier_behavior_hashes) != len(
        set(frontier_behavior_hashes)
    ):
        raise ValueError("Frontier contains duplicate behavior signatures.")

    for feature_id in RATE_SPIKE_FEATURE_IDS:
        feature_frontier = [
            group
            for group in frontier_groups
            if group["feature_id"] == feature_id
        ]
        for index, group in enumerate(feature_frontier):
            for other_index, other in enumerate(feature_frontier):
                if index == other_index:
                    continue
                if _group_dominates(other, group):
                    raise ValueError(
                        "Compressed frontier still contains a dominated group."
                    )

    identity_payload = {
        "contract_version": frontier["contract_version"],
        "development_dataset_hash": frontier["development_dataset_hash"],
        "protocol_hash": frontier["protocol_hash"],
        "research_hash": frontier["research_hash"],
        "holdout_dataset_hash_reference": frontier[
            "holdout_dataset_hash_reference"
        ],
        "stage_manifest": manifest,
        "frontier_status": frontier["frontier_status"],
        "holdout_locked": frontier["holdout_locked"],
        "holdout_accessed": frontier["holdout_accessed"],
        "final_candidate_selected": frontier[
            "final_candidate_selected"
        ],
        "rate_spike_state": frontier["rate_spike_state"],
        "production_decision_approved": frontier[
            "production_decision_approved"
        ],
    }
    expected_hash = content_hash(identity_payload)
    if frontier.get("frontier_hash") != expected_hash:
        raise ValueError("Compressed frontier hash mismatch.")
    if frontier.get("frontier_id") != f"RATEFRONT-{expected_hash[:16]}":
        raise ValueError("Compressed frontier id mismatch.")

    return {
        "frontier_hash": expected_hash,
        "raw_candidate_count": int(manifest["raw_candidate_count"]),
        "method_local_pareto_count": int(
            manifest["method_local_pareto_count"]
        ),
        "compressed_frontier_count": int(
            manifest["compressed_frontier_count"]
        ),
        "holdout_accessed": False,
    }


def summarize_compressed_frontier(
    frontier: dict[str, Any],
) -> dict[str, Any]:
    manifest = frontier["stage_manifest"]
    signal_fractions = [
        _decimal(group["signal_fraction"])
        for group in frontier["frontier_groups"]
    ]
    episode_counts = [
        int(group["episode_count"])
        for group in frontier["frontier_groups"]
    ]
    capture_fractions = [
        _decimal(group["positive_move_capture_fraction"])
        for group in frontier["frontier_groups"]
        if group["positive_move_capture_fraction"] is not None
    ]

    return {
        "contract_version": frontier["contract_version"],
        "frontier_id": frontier["frontier_id"],
        "frontier_hash": frontier["frontier_hash"],
        "frontier_status": frontier["frontier_status"],
        "development_dataset_hash": frontier[
            "development_dataset_hash"
        ],
        "protocol_hash": frontier["protocol_hash"],
        "research_hash": frontier["research_hash"],
        "holdout_locked": frontier["holdout_locked"],
        "holdout_accessed": frontier["holdout_accessed"],
        "raw_candidate_count": manifest["raw_candidate_count"],
        "v1_method_local_dominated_count": manifest[
            "v1_method_local_dominated_count"
        ],
        "method_local_pareto_count": manifest[
            "method_local_pareto_count"
        ],
        "trivial_direction_removed_count": manifest[
            "trivial_direction_removed_count"
        ],
        "behavior_duplicate_removed_count": manifest[
            "behavior_duplicate_removed_count"
        ],
        "unique_behavior_group_count": manifest[
            "unique_behavior_group_count"
        ],
        "cross_method_dominated_count": manifest[
            "cross_method_dominated_count"
        ],
        "compressed_frontier_count": manifest[
            "compressed_frontier_count"
        ],
        "features": frontier["per_feature"],
        "frontier_signal_fraction_range": {
            "min": (
                str(min(signal_fractions).normalize())
                if signal_fractions
                else None
            ),
            "max": (
                str(max(signal_fractions).normalize())
                if signal_fractions
                else None
            ),
        },
        "frontier_positive_capture_fraction_range": {
            "min": (
                str(min(capture_fractions).normalize())
                if capture_fractions
                else None
            ),
            "max": (
                str(max(capture_fractions).normalize())
                if capture_fractions
                else None
            ),
        },
        "frontier_episode_count_range": {
            "min": min(episode_counts) if episode_counts else None,
            "max": max(episode_counts) if episode_counts else None,
        },
        "final_candidate_selected": frontier[
            "final_candidate_selected"
        ],
        "minimum_sample_selected": frontier[
            "minimum_sample_selected"
        ],
        "rate_spike_state": frontier["rate_spike_state"],
        "normal_labels_created": frontier["normal_labels_created"],
        "detected_labels_created": frontier["detected_labels_created"],
        "network_requests": frontier["network_requests"],
        "macro_db_writes": frontier["macro_db_writes"],
        "production_decision_approved": frontier[
            "production_decision_approved"
        ],
    }
