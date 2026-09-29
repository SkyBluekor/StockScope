from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.macro.calibration_candidate import evaluate_candidate_behavior
from app.macro.identity import content_hash
from app.macro.shock_episode import (
    RATE_SPIKE_EPISODE_POLICY_VERSION,
    build_consecutive_true_episodes,
)


MACRO_CANDIDATE_BEHAVIOR_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_1_BEHAVIOR_SIGNATURE_V1"
)
MACRO_CANDIDATE_BEHAVIOR_GROUP_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_1_BEHAVIOR_GROUP_V1"
)


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Behavior metric must be finite.")
    return result


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _fraction(numerator: int, denominator: int) -> str | None:
    if denominator <= 0:
        return None
    return _decimal_text(Decimal(numerator) / Decimal(denominator))


def build_candidate_behavior(
    *,
    feature_result: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    rows = evaluate_candidate_behavior(
        feature_result=feature_result,
        candidate=candidate,
    )
    if not rows:
        raise ValueError("Candidate behavior requires Development rows.")

    eligible_rows = [row for row in rows if row["eligible"]]
    signal_rows = [row for row in rows if row["signal"]]
    positive_rows = [row for row in rows if row["positive_move"]]

    if any(row["signal"] and not row["positive_move"] for row in rows):
        raise ValueError("RATE_SPIKE signal must be an eligible positive move.")

    eligible_count = len(eligible_rows)
    signal_count = len(signal_rows)
    positive_move_count = len(positive_rows)
    if signal_count != int(candidate["development_signal_count"]):
        raise ValueError("Candidate signal count differs from behavior replay.")
    if eligible_count != int(candidate["eligible_row_count"]):
        raise ValueError("Candidate eligible count differs from behavior replay.")
    if positive_move_count <= 0:
        raise ValueError("RATE_SPIKE behavior requires positive Development moves.")

    eligibility_sequence = [
        {
            "row_hash": row["row_hash"],
            "eligible": bool(row["eligible"]),
        }
        for row in rows
    ]
    signal_sequence = [
        {
            "row_hash": row["row_hash"],
            "signal": bool(row["signal"]),
        }
        for row in rows
    ]
    eligibility_signature_hash = content_hash(eligibility_sequence)
    signal_signature_hash = content_hash(signal_sequence)

    episode_summary = build_consecutive_true_episodes(rows)
    if int(episode_summary["episode_count"]) != int(
        candidate["episode_summary"]["episode_count"]
    ):
        raise ValueError("Candidate episode count differs from behavior replay.")
    episode_boundaries = [
        {
            "start_date": episode["start_date"],
            "end_date": episode["end_date"],
        }
        for episode in episode_summary["episodes"]
    ]
    episode_boundary_hash = content_hash(episode_boundaries)

    behavior_identity = {
        "contract_version": MACRO_CANDIDATE_BEHAVIOR_CONTRACT_VERSION,
        "feature_id": candidate["feature_id"],
        "eligibility_signature_hash": eligibility_signature_hash,
        "signal_signature_hash": signal_signature_hash,
        "episode_policy_version": RATE_SPIKE_EPISODE_POLICY_VERSION,
        "episode_boundary_hash": episode_boundary_hash,
    }
    behavior_signature_hash = content_hash(behavior_identity)
    capture_count = sum(
        bool(row["signal"] and row["positive_move"]) for row in rows
    )
    capture_fraction = _fraction(capture_count, positive_move_count)
    trivial_direction_rule = (
        positive_move_count > 0
        and capture_count == positive_move_count
    )

    return {
        "contract_version": MACRO_CANDIDATE_BEHAVIOR_CONTRACT_VERSION,
        "candidate_id": candidate["candidate_id"],
        "candidate_hash": candidate["candidate_hash"],
        "feature_id": candidate["feature_id"],
        "method": candidate["method"],
        "threshold_definition": candidate["threshold_definition"],
        "threshold_value": candidate["threshold_value"],
        "threshold_unit": candidate["threshold_unit"],
        "behavior_signature_hash": behavior_signature_hash,
        "eligibility_signature_hash": eligibility_signature_hash,
        "signal_signature_hash": signal_signature_hash,
        "episode_boundary_hash": episode_boundary_hash,
        "eligible_count": eligible_count,
        "signal_count": signal_count,
        "signal_fraction": candidate["development_signal_fraction"],
        "positive_move_count": positive_move_count,
        "positive_move_capture_count": capture_count,
        "positive_move_capture_fraction": capture_fraction,
        "year_signal_counts": dict(candidate["year_signal_counts"]),
        "year_coverage_count": int(candidate["year_coverage_count"]),
        "year_coverage_fraction": candidate["year_coverage_fraction"],
        "max_year_signal_share": candidate["max_year_signal_share"],
        "episode_count": int(episode_summary["episode_count"]),
        "episode_separation_ratio": candidate["episode_separation_ratio"],
        "trivial_direction_rule": trivial_direction_rule,
        "holdout_accessed": False,
        "production_decision_approved": False,
    }


def _source_ref(
    candidate: dict[str, Any],
    behavior: dict[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate["candidate_id"],
        "candidate_hash": candidate["candidate_hash"],
        "method": candidate["method"],
        "threshold_definition": candidate["threshold_definition"],
        "threshold_value": candidate["threshold_value"],
        "threshold_unit": candidate["threshold_unit"],
        "required_condition": candidate["required_condition"],
        "lookback_mode": candidate["lookback_mode"],
        "derived_minimum_prior_support": candidate[
            "derived_minimum_prior_support"
        ],
        "behavior_signature_hash": behavior["behavior_signature_hash"],
    }


def build_behavior_groups(
    *,
    feature_id: str,
    feature_result: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    behavior_by_hash: dict[str, dict[str, Any]] = {}
    candidate_by_hash = {
        str(candidate["candidate_hash"]): candidate for candidate in candidates
    }

    for candidate in candidates:
        if candidate["feature_id"] != feature_id:
            raise ValueError("Behavior grouping cannot mix features.")
        behavior = build_candidate_behavior(
            feature_result=feature_result,
            candidate=candidate,
        )
        behavior_by_hash[str(candidate["candidate_hash"])] = behavior

    trivial_candidate_hashes = sorted(
        candidate_hash
        for candidate_hash, behavior in behavior_by_hash.items()
        if behavior["trivial_direction_rule"]
    )
    nontrivial = [
        candidate
        for candidate in candidates
        if str(candidate["candidate_hash"]) not in set(trivial_candidate_hashes)
    ]

    buckets: dict[str, list[dict[str, Any]]] = {}
    for candidate in nontrivial:
        behavior = behavior_by_hash[str(candidate["candidate_hash"])]
        buckets.setdefault(behavior["behavior_signature_hash"], []).append(
            candidate
        )

    groups: list[dict[str, Any]] = []
    for behavior_hash in sorted(buckets):
        source_candidates = sorted(
            buckets[behavior_hash],
            key=lambda item: str(item["candidate_hash"]),
        )
        representative = source_candidates[0]
        behavior = behavior_by_hash[str(representative["candidate_hash"])]

        for candidate in source_candidates[1:]:
            other = behavior_by_hash[str(candidate["candidate_hash"])]
            equality_fields = (
                "eligible_count",
                "signal_count",
                "signal_fraction",
                "positive_move_count",
                "positive_move_capture_count",
                "positive_move_capture_fraction",
                "year_coverage_count",
                "year_coverage_fraction",
                "max_year_signal_share",
                "episode_count",
                "episode_separation_ratio",
            )
            if any(other[field] != behavior[field] for field in equality_fields):
                raise ValueError(
                    "Equal behavior signatures must have equal behavior metrics."
                )

        source_refs = [
            _source_ref(
                candidate,
                behavior_by_hash[str(candidate["candidate_hash"])],
            )
            for candidate in source_candidates
        ]
        source_methods = sorted(
            {str(candidate["method"]) for candidate in source_candidates}
        )
        group_payload = {
            "contract_version": (
                MACRO_CANDIDATE_BEHAVIOR_GROUP_CONTRACT_VERSION
            ),
            "feature_id": feature_id,
            "behavior_signature_hash": behavior_hash,
            "eligibility_signature_hash": behavior[
                "eligibility_signature_hash"
            ],
            "signal_signature_hash": behavior["signal_signature_hash"],
            "episode_boundary_hash": behavior["episode_boundary_hash"],
            "eligible_count": behavior["eligible_count"],
            "signal_count": behavior["signal_count"],
            "signal_fraction": behavior["signal_fraction"],
            "positive_move_count": behavior["positive_move_count"],
            "positive_move_capture_count": behavior[
                "positive_move_capture_count"
            ],
            "positive_move_capture_fraction": behavior[
                "positive_move_capture_fraction"
            ],
            "year_signal_counts": behavior["year_signal_counts"],
            "year_coverage_count": behavior["year_coverage_count"],
            "year_coverage_fraction": behavior["year_coverage_fraction"],
            "max_year_signal_share": behavior["max_year_signal_share"],
            "episode_count": behavior["episode_count"],
            "episode_separation_ratio": behavior[
                "episode_separation_ratio"
            ],
            "episode_policy_version": RATE_SPIKE_EPISODE_POLICY_VERSION,
            "source_candidate_count": len(source_candidates),
            "source_candidate_hashes": [
                str(candidate["candidate_hash"])
                for candidate in source_candidates
            ],
            "source_methods": source_methods,
            "source_refs": source_refs,
            "trivial_direction_rule": False,
            "holdout_accessed": False,
            "production_decision_approved": False,
        }
        group_hash = content_hash(group_payload)
        groups.append(
            {
                **group_payload,
                "behavior_group_id": f"RATEBG-{group_hash[:16]}",
                "behavior_group_hash": group_hash,
            }
        )

    groups.sort(
        key=lambda item: (
            str(item["feature_id"]),
            str(item["behavior_signature_hash"]),
            str(item["behavior_group_hash"]),
        )
    )

    duplicate_removed_count = len(nontrivial) - len(groups)
    return {
        "feature_id": feature_id,
        "input_candidate_count": len(candidates),
        "trivial_direction_removed_count": len(trivial_candidate_hashes),
        "trivial_direction_candidate_hashes": trivial_candidate_hashes,
        "nontrivial_candidate_count": len(nontrivial),
        "unique_behavior_group_count": len(groups),
        "behavior_duplicate_removed_count": duplicate_removed_count,
        "behavior_groups": groups,
        "candidate_behavior_hashes": {
            candidate_hash: behavior["behavior_signature_hash"]
            for candidate_hash, behavior in sorted(behavior_by_hash.items())
        },
    }


def build_method_overlap_matrix(
    groups: list[dict[str, Any]],
    methods: tuple[str, ...],
) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {
        left: {right: 0 for right in methods}
        for left in methods
    }
    for group in groups:
        source_methods = set(str(item) for item in group["source_methods"])
        for left in methods:
            if left not in source_methods:
                continue
            for right in methods:
                if right in source_methods:
                    matrix[left][right] += 1
    return matrix
