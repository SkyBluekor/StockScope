from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.macro.calibration_candidate import RATE_SPIKE_FEATURE_IDS, RATE_SPIKE_METHODS
from app.macro.frontier_admissibility import (
    validate_frontier_admissibility_diagnostic,
)
from app.macro.identity import content_hash


RATE_SPIKE_ADMISSIBILITY_REVIEW_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2A_ADMISSIBILITY_REVIEW_V1"
)

_METHOD_LABELS = {
    "EMPIRICAL_POSITIVE_TAIL": "EPT",
    "EXPANDING_POSITIVE_TAIL_FRACTION": "TAIL",
    "EXPANDING_ROBUST_MAD": "MAD",
}
_FEATURE_LABELS = {
    "delta_bp_1obs": "1obs",
    "delta_bp_5obs": "5obs",
    "delta_bp_10obs": "10obs",
}


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Review metric must be finite.")
    return result


def _percent_display(value: Any) -> str:
    percent = (_decimal(value) * Decimal("100")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    text = format(percent, "f").rstrip("0").rstrip(".")
    return f"{text or '0'}%"


def _range_display(
    value_range: dict[str, Any],
    *,
    percent: bool = False,
) -> str:
    minimum = value_range.get("min")
    maximum = value_range.get("max")
    if minimum is None or maximum is None:
        return "N/A"
    if percent:
        left = _percent_display(minimum)
        right = _percent_display(maximum)
    else:
        left = str(minimum)
        right = str(maximum)
    return left if left == right else f"{left}..{right}"


def _family_review_row(family: dict[str, Any]) -> dict[str, Any]:
    return {
        "feature_id": family["feature_id"],
        "method": family["method"],
        "family_id": family["family_id"],
        "family_hash": family["family_hash"],
        "candidate_count": int(family["candidate_count"]),
        "unique_behavior_count": int(family["unique_behavior_count"]),
        "threshold_unit": family["threshold_unit"],
        "threshold_value_range": dict(family["threshold_value_range"]),
        "signal_fraction_range": dict(family["signal_fraction_range"]),
        "signal_fraction_display": _range_display(
            family["signal_fraction_range"],
            percent=True,
        ),
        "positive_capture_fraction_range": dict(
            family["positive_capture_fraction_range"]
        ),
        "positive_capture_display": _range_display(
            family["positive_capture_fraction_range"],
            percent=True,
        ),
        "signal_row_count_range": dict(family["signal_row_count_range"]),
        "episode_count_range": dict(family["episode_count_range"]),
        "episode_start_count_range": dict(
            family["episode_start_count_range"]
        ),
        "yearly_episode_count_range": dict(
            family["yearly_episode_count_range"]
        ),
        "nested_behavior": dict(family["nested_behavior"]),
        "positive_capture_classification_counts": dict(
            family["positive_capture_classification_counts"]
        ),
        "observation_status": "OBSERVED",
        "admissibility_decision": "NOT_DEFINED",
        "automatic_rejection_count": 0,
    }


def build_admissibility_review(
    diagnostic: dict[str, Any],
) -> dict[str, Any]:
    state = validate_frontier_admissibility_diagnostic(diagnostic)
    if state["ready_for_holdout"] is not False:
        raise ValueError("S4.2-A review requires Holdout readiness to remain false.")
    if diagnostic["admissibility_status"] != "ADMISSIBILITY_POLICY_UNDEFINED":
        raise ValueError("S4.2-A requires undefined admissibility policy.")

    source_families = list(diagnostic["families"])
    family_rows = [_family_review_row(family) for family in source_families]
    family_rows.sort(key=lambda item: (item["feature_id"], item["method"]))

    expected_pairs = {
        (feature_id, method)
        for feature_id in RATE_SPIKE_FEATURE_IDS
        for method in RATE_SPIKE_METHODS
    }
    actual_pairs = {
        (str(row["feature_id"]), str(row["method"]))
        for row in family_rows
    }
    if actual_pairs != expected_pairs or len(family_rows) != 9:
        raise ValueError("S4.2-A requires exactly 9 feature/method families.")

    source_family_hashes = sorted(
        str(family["family_hash"]) for family in source_families
    )
    review_family_hashes = sorted(
        str(row["family_hash"]) for row in family_rows
    )
    if review_family_hashes != source_family_hashes:
        raise ValueError("Family provenance changed during review projection.")

    event_units = {
        "selection_status": "NOT_SELECTED",
        "selected_event_unit": "UNSET",
        "signal_row_count_range": dict(
            diagnostic["event_unit_diagnostics"]["signal_row_count_range"]
        ),
        "episode_count_range": dict(
            diagnostic["event_unit_diagnostics"]["episode_count_range"]
        ),
        "episode_start_count_range": dict(
            diagnostic["event_unit_diagnostics"][
                "episode_start_count_range"
            ]
        ),
        "available_views": [
            "SIGNAL_ROW",
            "EPISODE",
            "EPISODE_START",
        ],
    }

    source = {
        "diagnostic_id": diagnostic["diagnostic_id"],
        "diagnostic_hash": diagnostic["diagnostic_hash"],
        "source_frontier_id": diagnostic["source_frontier_id"],
        "source_frontier_hash": diagnostic["source_frontier_hash"],
        "development_dataset_hash": diagnostic[
            "development_dataset_hash"
        ],
        "protocol_hash": diagnostic["protocol_hash"],
        "research_hash": diagnostic["research_hash"],
    }

    counts = {
        "family_count": len(family_rows),
        "raw_candidate_count": int(
            diagnostic["compression_manifest"]["raw_candidate_count"]
        ),
        "method_local_pareto_count": int(
            diagnostic["compression_manifest"][
                "method_local_pareto_count"
            ]
        ),
        "compressed_frontier_count": int(
            diagnostic["compression_manifest"][
                "compressed_frontier_count"
            ]
        ),
    }

    policy_state = {
        "admissibility_policy": "UNDEFINED",
        "event_unit": "UNSET",
        "evaluation_rule": "UNSET",
        "final_threshold_selected": False,
        "minimum_sample_selected": False,
        "event_unit_selected": False,
        "policy_approved": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }

    identity_payload = {
        "contract_version": RATE_SPIKE_ADMISSIBILITY_REVIEW_CONTRACT_VERSION,
        "source": source,
        "counts": counts,
        "family_review_payload_hash": content_hash(family_rows),
        "event_unit_diagnostics": event_units,
        "policy_state": policy_state,
        "holdout_locked": True,
        "holdout_accessed": False,
        "network_requests": 0,
        "macro_db_writes": 0,
        "production_impact": "NONE",
    }
    review_hash = content_hash(identity_payload)

    return {
        **identity_payload,
        "review_id": f"RATEADMISSREVIEW-{review_hash[:16]}",
        "review_hash": review_hash,
        "review_status": "REVIEW_REQUIRED",
        "families": family_rows,
    }


def validate_admissibility_review(review: dict[str, Any]) -> dict[str, Any]:
    if (
        review.get("contract_version")
        != RATE_SPIKE_ADMISSIBILITY_REVIEW_CONTRACT_VERSION
    ):
        raise ValueError("Unsupported S4.2-A review contract.")
    if review.get("review_status") != "REVIEW_REQUIRED":
        raise ValueError("S4.2-A must remain a review-only stage.")
    if review.get("holdout_locked") is not True:
        raise ValueError("S4.2-A must keep Holdout locked.")
    if review.get("holdout_accessed") is not False:
        raise ValueError("S4.2-A must not access Holdout.")
    if int(review.get("network_requests") or 0) != 0:
        raise ValueError("S4.2-A must not use network.")
    if int(review.get("macro_db_writes") or 0) != 0:
        raise ValueError("S4.2-A must not write Macro DB.")
    if review.get("production_impact") != "NONE":
        raise ValueError("S4.2-A must have no Production impact.")

    policy = review.get("policy_state") or {}
    if policy.get("admissibility_policy") != "UNDEFINED":
        raise ValueError("Admissibility policy must remain undefined.")
    if policy.get("event_unit") != "UNSET":
        raise ValueError("Event unit must remain UNSET.")
    if policy.get("evaluation_rule") != "UNSET":
        raise ValueError("Evaluation rule must remain UNSET.")
    if policy.get("final_threshold_selected") is not False:
        raise ValueError("S4.2-A must not select a threshold.")
    if policy.get("minimum_sample_selected") is not False:
        raise ValueError("S4.2-A must not select minimum sample.")
    if policy.get("event_unit_selected") is not False:
        raise ValueError("S4.2-A must not select an event unit.")
    if policy.get("policy_approved") is not False:
        raise ValueError("S4.2-A must not approve policy.")
    if policy.get("ready_for_holdout") is not False:
        raise ValueError("S4.2-A must not become Holdout-ready.")
    if policy.get("rate_spike_state") != "UNCALIBRATED":
        raise ValueError("RATE_SPIKE must remain UNCALIBRATED.")

    families = list(review.get("families") or [])
    expected_pairs = {
        (feature_id, method)
        for feature_id in RATE_SPIKE_FEATURE_IDS
        for method in RATE_SPIKE_METHODS
    }
    actual_pairs = {
        (str(item["feature_id"]), str(item["method"]))
        for item in families
    }
    if len(families) != 9 or actual_pairs != expected_pairs:
        raise ValueError("S4.2-A review must contain exactly 9 families.")
    if review.get("family_review_payload_hash") != content_hash(families):
        raise ValueError("Family review payload hash mismatch.")
    if int(review["counts"]["family_count"]) != 9:
        raise ValueError("Family count summary mismatch.")

    for family in families:
        if family.get("observation_status") != "OBSERVED":
            raise ValueError("Family output must remain descriptive.")
        if family.get("admissibility_decision") != "NOT_DEFINED":
            raise ValueError("S4.2-A must not make an admissibility decision.")
        if int(family.get("automatic_rejection_count") or 0) != 0:
            raise ValueError("S4.2-A must not reject candidates.")

    identity_payload = {
        key: review[key]
        for key in (
            "contract_version",
            "source",
            "counts",
            "family_review_payload_hash",
            "event_unit_diagnostics",
            "policy_state",
            "holdout_locked",
            "holdout_accessed",
            "network_requests",
            "macro_db_writes",
            "production_impact",
        )
    }
    expected_hash = content_hash(identity_payload)
    if review.get("review_hash") != expected_hash:
        raise ValueError("S4.2-A review hash mismatch.")
    if review.get("review_id") != f"RATEADMISSREVIEW-{expected_hash[:16]}":
        raise ValueError("S4.2-A review id mismatch.")

    return {
        "review_hash": expected_hash,
        "family_count": 9,
        "holdout_accessed": False,
        "ready_for_holdout": False,
    }


def _threshold_display(family: dict[str, Any]) -> str:
    base = _range_display(family["threshold_value_range"])
    unit = str(family.get("threshold_unit") or "")
    if base == "N/A" or not unit:
        return base
    units = {
        "BASIS_POINT": "bp",
        "FRACTION": "frac",
        "MAD_MULTIPLE": "MAD",
    }
    return f"{base} {units.get(unit, unit)}"


def _nested_display(family: dict[str, Any]) -> str:
    status = str(family["nested_behavior"]["status"])
    if status == "FULLY_NESTED":
        return "FULLY"
    if status == "NOT_FULLY_NESTED":
        return "MIXED"
    return status


def render_admissibility_review_text(review: dict[str, Any]) -> str:
    validate_admissibility_review(review)

    rows = []
    for family in review["families"]:
        rows.append(
            (
                _FEATURE_LABELS[str(family["feature_id"])],
                _METHOD_LABELS[str(family["method"])],
                str(family["candidate_count"]),
                str(family["unique_behavior_count"]),
                _threshold_display(family),
                family["signal_fraction_display"],
                family["positive_capture_display"],
                _range_display(family["signal_row_count_range"]),
                _range_display(family["episode_count_range"]),
                _range_display(family["yearly_episode_count_range"]),
                _nested_display(family),
            )
        )

    headers = (
        "Feat",
        "Meth",
        "Cand",
        "Beh",
        "Threshold",
        "Signal%",
        "Capture%",
        "Rows",
        "Episodes",
        "YearEp",
        "Nested",
    )
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    def format_row(row: tuple[str, ...]) -> str:
        return "  ".join(
            value.ljust(widths[index])
            for index, value in enumerate(row)
        )

    counts = review["counts"]
    policy = review["policy_state"]
    event = review["event_unit_diagnostics"]
    lines = [
        "NEXT-6B-S4.2-A ADMISSIBILITY REVIEW",
        "",
        (
            f"Source diagnostic : {review['source']['diagnostic_id']} "
            f"({review['source']['diagnostic_hash']})"
        ),
        (
            "Families / Raw / Method Pareto / Frontier : "
            f"{counts['family_count']} / "
            f"{counts['raw_candidate_count']} / "
            f"{counts['method_local_pareto_count']} / "
            f"{counts['compressed_frontier_count']}"
        ),
        "",
        format_row(headers),
        format_row(tuple("-" * width for width in widths)),
    ]
    lines.extend(format_row(row) for row in rows)
    lines.extend(
        [
            "",
            (
                "Method legend: "
                "EPT=EMPIRICAL_POSITIVE_TAIL, "
                "TAIL=EXPANDING_POSITIVE_TAIL_FRACTION, "
                "MAD=EXPANDING_ROBUST_MAD"
            ),
            (
                "Event-unit views : "
                f"SIGNAL_ROW={_range_display(event['signal_row_count_range'])}, "
                f"EPISODE={_range_display(event['episode_count_range'])}, "
                "EPISODE_START="
                f"{_range_display(event['episode_start_count_range'])}"
            ),
            (
                "Policy / Event unit / Evaluation rule : "
                f"{policy['admissibility_policy']} / "
                f"{policy['event_unit']} / "
                f"{policy['evaluation_rule']}"
            ),
            (
                "Threshold / Minimum sample / Event unit selected : "
                f"{policy['final_threshold_selected']} / "
                f"{policy['minimum_sample_selected']} / "
                f"{policy['event_unit_selected']}"
            ),
            (
                "Holdout locked / accessed / ready : "
                f"{review['holdout_locked']} / "
                f"{review['holdout_accessed']} / "
                f"{policy['ready_for_holdout']}"
            ),
            (
                "RATE_SPIKE / Network / Macro DB writes / Production : "
                f"{policy['rate_spike_state']} / "
                f"{review['network_requests']} / "
                f"{review['macro_db_writes']} / "
                f"{review['production_impact']}"
            ),
            "",
            "Review status: REVIEW_REQUIRED (no admissibility decision made)",
        ]
    )
    return "\n".join(lines)
