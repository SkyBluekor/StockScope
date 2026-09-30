from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from app.macro.calibration_candidate import (
    RATE_SPIKE_FEATURE_IDS,
    RATE_SPIKE_METHODS,
)
from app.macro.calibration_research import (
    validate_development_artifact,
    validate_distribution_research_artifact,
    validate_research_protocol,
)
from app.macro.candidate_compression import (
    build_compressed_candidate_frontier,
    validate_compressed_frontier_artifact,
)
from app.macro.frontier_admissibility import (
    validate_frontier_admissibility_diagnostic,
)
from app.macro.identity import content_hash


RATE_SPIKE_ADMISSIBILITY_EVIDENCE_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B_ADMISSIBILITY_EVIDENCE_V1"
)
RATE_SPIKE_EVIDENCE_ROW_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B_EVIDENCE_ROW_V1"
)
RATE_SPIKE_EVIDENCE_FAMILY_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B_EVIDENCE_FAMILY_V1"
)
OBSERVED_ORDER_STATISTIC_METHOD = "OBSERVED_ORDER_STATISTIC_FLOOR_V1"

_FEATURE_ORDER = {feature_id: index for index, feature_id in enumerate(RATE_SPIKE_FEATURE_IDS)}
_METHOD_ORDER = {method: index for index, method in enumerate(RATE_SPIKE_METHODS)}
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

_MAXIMUM_STYLE_AXES = (
    "signal_fraction",
    "positive_capture_fraction",
    "episode_starts_per_year",
    "episode_start_fraction_of_eligible",
)
_MINIMUM_STYLE_AXES = (
    "year_coverage_count",
    "eligible_count",
    "signal_count",
    "episode_count",
)
_DECIMAL_AXES = set(_MAXIMUM_STYLE_AXES)
_INTEGER_AXES = set(_MINIMUM_STYLE_AXES)


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Evidence metric must be finite.")
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


def _percent_display(value: Any) -> str:
    percent = (_decimal(value) * Decimal("100")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    text = format(percent, "f").rstrip("0").rstrip(".")
    return f"{text or '0'}%"


def _decimal_display(value: Any) -> str:
    number = _decimal(value).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    text = format(number, "f").rstrip("0").rstrip(".")
    return text or "0"


def _actual_development_years(
    development_dataset: dict[str, Any],
) -> list[str]:
    years = sorted(
        {
            str(row["observation_date"])[:4]
            for row in development_dataset["rows"]
            if str(row.get("observation_date") or "")[:4]
        }
    )
    if not years:
        raise ValueError("Development evidence requires at least one observation year.")
    return years


def _threshold_refs_by_method(
    source_refs: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for ref in source_refs:
        method = str(ref["method"])
        result.setdefault(method, []).append(
            {
                "candidate_id": ref["candidate_id"],
                "candidate_hash": ref["candidate_hash"],
                "threshold_definition": ref["threshold_definition"],
                "threshold_value": ref["threshold_value"],
                "threshold_unit": ref["threshold_unit"],
                "required_condition": ref["required_condition"],
                "lookback_mode": ref["lookback_mode"],
                "derived_minimum_prior_support": ref[
                    "derived_minimum_prior_support"
                ],
            }
        )
    for method in result:
        result[method].sort(
            key=lambda item: (
                str(item["threshold_unit"]),
                _decimal(item["threshold_value"]),
                str(item["candidate_hash"]),
            )
        )
    return dict(sorted(result.items()))


def _build_evidence_row(
    *,
    group: dict[str, Any],
    development_years: list[str],
) -> dict[str, Any]:
    eligible_count = int(group["eligible_count"])
    signal_count = int(group["signal_count"])
    episode_count = int(group["episode_count"])
    episode_start_count = episode_count
    development_year_count = len(development_years)

    episode_starts_per_year = _fraction(
        episode_start_count,
        development_year_count,
    )
    episode_start_fraction = _fraction(
        episode_start_count,
        eligible_count,
    )
    if episode_starts_per_year is None or episode_start_fraction is None:
        raise ValueError("Evidence row requires positive year and eligible counts.")

    source_refs = sorted(
        [dict(ref) for ref in group["source_refs"]],
        key=lambda ref: (
            str(ref["method"]),
            str(ref["threshold_unit"]),
            _decimal(ref["threshold_value"]),
            str(ref["candidate_hash"]),
        ),
    )
    row_payload = {
        "contract_version": RATE_SPIKE_EVIDENCE_ROW_CONTRACT_VERSION,
        "feature_id": group["feature_id"],
        "behavior_group_id": group["behavior_group_id"],
        "behavior_group_hash": group["behavior_group_hash"],
        "behavior_signature_hash": group["behavior_signature_hash"],
        "episode_boundary_hash": group["episode_boundary_hash"],
        "episode_start_hash": group["episode_start_hash"],
        "source_methods": list(group["source_methods"]),
        "source_candidate_count": int(group["source_candidate_count"]),
        "source_candidate_hashes": list(group["source_candidate_hashes"]),
        "source_refs": source_refs,
        "thresholds_by_method": _threshold_refs_by_method(source_refs),
        "eligible_count": eligible_count,
        "signal_count": signal_count,
        "signal_fraction": group["signal_fraction"],
        "positive_move_count": int(group["positive_move_count"]),
        "positive_move_capture_count": int(
            group["positive_move_capture_count"]
        ),
        "positive_capture_fraction": group[
            "positive_move_capture_fraction"
        ],
        "episode_count": episode_count,
        "episode_start_count": episode_start_count,
        "development_year_count": development_year_count,
        "development_years": development_years,
        "episode_starts_per_year": episode_starts_per_year,
        "episode_start_fraction_of_eligible": episode_start_fraction,
        "year_coverage_count": int(group["year_coverage_count"]),
        "year_coverage_fraction": group["year_coverage_fraction"],
        "max_year_signal_share": group["max_year_signal_share"],
        "episode_separation_ratio": group["episode_separation_ratio"],
        "holdout_accessed": False,
        "production_decision_approved": False,
    }
    row_hash = content_hash(row_payload)
    return {
        **row_payload,
        "evidence_row_id": f"RATEEVIDROW-{row_hash[:16]}",
        "evidence_row_hash": row_hash,
    }


def _axis_value(row: dict[str, Any], axis: str) -> Decimal | int:
    value = row[axis]
    if axis in _DECIMAL_AXES:
        return _decimal(value)
    if axis in _INTEGER_AXES:
        return int(value)
    raise ValueError(f"Unsupported evidence axis: {axis}")


def _serialize_axis_value(axis: str, value: Decimal | int) -> str | int:
    if axis in _DECIMAL_AXES:
        return _decimal_text(Decimal(value))
    return int(value)


def _observed_summary(
    rows: list[dict[str, Any]],
    axis: str,
) -> dict[str, Any]:
    if not rows:
        return {
            "status": "NO_VALUES",
            "quantile_method": OBSERVED_ORDER_STATISTIC_METHOD,
            "count": 0,
            "unique_value_count": 0,
            "min": None,
            "q1": None,
            "median": None,
            "q3": None,
            "max": None,
        }
    values = sorted(_axis_value(row, axis) for row in rows)
    last = len(values) - 1

    def observed(percentile: Decimal) -> Decimal | int:
        index = int((Decimal(last) * percentile).to_integral_value(rounding=ROUND_FLOOR))
        return values[index]

    return {
        "status": "DESCRIPTIVE_ONLY",
        "quantile_method": OBSERVED_ORDER_STATISTIC_METHOD,
        "count": len(values),
        "unique_value_count": len(set(values)),
        "min": _serialize_axis_value(axis, values[0]),
        "q1": _serialize_axis_value(axis, observed(Decimal("0.25"))),
        "median": _serialize_axis_value(axis, observed(Decimal("0.50"))),
        "q3": _serialize_axis_value(axis, observed(Decimal("0.75"))),
        "max": _serialize_axis_value(axis, values[-1]),
    }


def _observed_breakpoint_curve(
    rows: list[dict[str, Any]],
    axis: str,
) -> dict[str, Any]:
    values = [_axis_value(row, axis) for row in rows]
    unique_values = sorted(set(values))
    total = len(values)
    comparison = (
        "AT_OR_BELOW"
        if axis in _MAXIMUM_STYLE_AXES
        else "AT_OR_ABOVE"
    )
    points: list[dict[str, Any]] = []
    for value in unique_values:
        if comparison == "AT_OR_BELOW":
            count = sum(item <= value for item in values)
        else:
            count = sum(item >= value for item in values)
        points.append(
            {
                "value": _serialize_axis_value(axis, value),
                "frontier_group_count": count,
                "frontier_group_fraction": _fraction(count, total),
            }
        )
    return {
        "axis": axis,
        "comparison": comparison,
        "source": "OBSERVED_FRONTIER_VALUES_ONLY",
        "invented_grid_points": 0,
        "point_count": len(points),
        "points": points,
    }


def _joint_profile_key(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "signal_fraction": row["signal_fraction"],
        "positive_capture_fraction": row["positive_capture_fraction"],
        "episode_starts_per_year": row["episode_starts_per_year"],
        "episode_start_fraction_of_eligible": row[
            "episode_start_fraction_of_eligible"
        ],
        "year_coverage_count": row["year_coverage_count"],
        "eligible_count": row["eligible_count"],
        "signal_count": row["signal_count"],
        "episode_count": row["episode_count"],
    }


def _build_joint_profiles(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        profile = _joint_profile_key(row)
        profile_hash = content_hash(profile)
        bucket = buckets.setdefault(
            profile_hash,
            {
                "profile_hash": profile_hash,
                "profile": profile,
                "behavior_group_hashes": [],
                "source_candidate_count": 0,
            },
        )
        bucket["behavior_group_hashes"].append(
            str(row["behavior_group_hash"])
        )
        bucket["source_candidate_count"] += int(
            row["source_candidate_count"]
        )

    result: list[dict[str, Any]] = []
    for profile_hash in sorted(buckets):
        bucket = buckets[profile_hash]
        hashes = sorted(bucket["behavior_group_hashes"])
        result.append(
            {
                "profile_id": f"RATEEVIDPROF-{profile_hash[:16]}",
                "profile_hash": profile_hash,
                "profile": bucket["profile"],
                "profile_count": len(hashes),
                "behavior_group_hashes": hashes,
                "source_candidate_count": int(
                    bucket["source_candidate_count"]
                ),
                "rank": None,
                "score": None,
                "recommended": False,
            }
        )
    return result


def _family_members(
    rows: list[dict[str, Any]],
    *,
    feature_id: str,
    method: str,
) -> list[dict[str, Any]]:
    members = [
        row
        for row in rows
        if row["feature_id"] == feature_id
        and method in set(str(item) for item in row["source_methods"])
    ]
    members.sort(key=lambda row: str(row["behavior_group_hash"]))
    return members


def _build_family_evidence(
    *,
    rows: list[dict[str, Any]],
    feature_id: str,
    method: str,
    diagnostic_family: dict[str, Any],
) -> dict[str, Any]:
    members = _family_members(
        rows,
        feature_id=feature_id,
        method=method,
    )
    if len(members) != int(diagnostic_family["unique_behavior_count"]):
        raise ValueError("Replay family behavior count differs from S4.1R diagnostic.")

    source_candidate_hashes = sorted(
        {
            str(ref["candidate_hash"])
            for row in members
            for ref in row["source_refs"]
            if str(ref["method"]) == method
        }
    )
    if len(source_candidate_hashes) != int(diagnostic_family["candidate_count"]):
        raise ValueError("Replay family candidate count differs from S4.1R diagnostic.")

    axis_order = (*_MAXIMUM_STYLE_AXES, *_MINIMUM_STYLE_AXES)
    descriptive = {
        axis: _observed_summary(members, axis)
        for axis in axis_order
    }
    curves = {
        axis: _observed_breakpoint_curve(members, axis)
        for axis in axis_order
    }
    joint_profiles = _build_joint_profiles(members)

    family_payload = {
        "contract_version": RATE_SPIKE_EVIDENCE_FAMILY_CONTRACT_VERSION,
        "feature_id": feature_id,
        "method": method,
        "source_family_id": diagnostic_family["family_id"],
        "source_family_hash": diagnostic_family["family_hash"],
        "frontier_group_count": len(members),
        "source_candidate_count": len(source_candidate_hashes),
        "source_candidate_hashes": source_candidate_hashes,
        "behavior_group_hashes": [
            str(row["behavior_group_hash"]) for row in members
        ],
        "descriptive_summaries": descriptive,
        "observed_breakpoint_curves": curves,
        "exact_joint_profiles": joint_profiles,
        "joint_profile_count": len(joint_profiles),
        "nested_behavior": dict(diagnostic_family["nested_behavior"]),
        "evidence_status": "COMPLETE",
        "interpretation": "DESCRIPTIVE_ONLY",
        "admissibility_decision": "NOT_DEFINED",
        "automatic_rejection_count": 0,
        "holdout_accessed": False,
        "production_decision_approved": False,
    }
    family_hash = content_hash(family_payload)
    return {
        **family_payload,
        "evidence_family_id": f"RATEEVIDFAM-{family_hash[:16]}",
        "evidence_family_hash": family_hash,
    }


def build_admissibility_evidence(
    *,
    diagnostic: dict[str, Any],
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
    research: dict[str, Any],
) -> dict[str, Any]:
    validate_frontier_admissibility_diagnostic(diagnostic)
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

    if diagnostic["development_dataset_hash"] != development_state["dataset_hash"]:
        raise ValueError("Diagnostic Development hash differs from evidence input.")
    if diagnostic["protocol_hash"] != protocol_state["protocol_hash"]:
        raise ValueError("Diagnostic Protocol hash differs from evidence input.")
    if diagnostic["research_hash"] != research_state["research_hash"]:
        raise ValueError("Diagnostic Research hash differs from evidence input.")

    frontier = build_compressed_candidate_frontier(
        development_dataset=development_dataset,
        protocol=protocol,
        research=research,
    )
    validate_compressed_frontier_artifact(frontier)

    if frontier["frontier_hash"] != diagnostic["source_frontier_hash"]:
        raise ValueError("Replayed frontier hash differs from S4.1R diagnostic.")
    if frontier["frontier_id"] != diagnostic["source_frontier_id"]:
        raise ValueError("Replayed frontier id differs from S4.1R diagnostic.")
    if frontier["holdout_accessed"] is not False:
        raise ValueError("S4.2-B must not access Holdout.")

    years = _actual_development_years(development_dataset)
    evidence_rows = [
        _build_evidence_row(
            group=group,
            development_years=years,
        )
        for group in frontier["frontier_groups"]
    ]
    evidence_rows.sort(
        key=lambda row: (
            _FEATURE_ORDER[str(row["feature_id"])],
            str(row["behavior_group_hash"]),
        )
    )

    expected_frontier_count = int(
        frontier["stage_manifest"]["compressed_frontier_count"]
    )
    if len(evidence_rows) != expected_frontier_count:
        raise ValueError("Evidence row count differs from compressed frontier.")

    diagnostic_families = {
        (str(item["feature_id"]), str(item["method"])): item
        for item in diagnostic["families"]
    }
    family_evidence: list[dict[str, Any]] = []
    for feature_id in RATE_SPIKE_FEATURE_IDS:
        for method in RATE_SPIKE_METHODS:
            key = (feature_id, method)
            if key not in diagnostic_families:
                raise ValueError("S4.2-B diagnostic is missing a required family.")
            family_evidence.append(
                _build_family_evidence(
                    rows=evidence_rows,
                    feature_id=feature_id,
                    method=method,
                    diagnostic_family=diagnostic_families[key],
                )
            )

    family_evidence.sort(
        key=lambda item: (
            _FEATURE_ORDER[str(item["feature_id"])],
            _METHOD_ORDER[str(item["method"])],
        )
    )
    if len(family_evidence) != 9:
        raise ValueError("S4.2-B requires exactly 9 evidence families.")

    source = {
        "diagnostic_id": diagnostic["diagnostic_id"],
        "diagnostic_hash": diagnostic["diagnostic_hash"],
        "source_frontier_id": diagnostic["source_frontier_id"],
        "source_frontier_hash": diagnostic["source_frontier_hash"],
        "replayed_frontier_id": frontier["frontier_id"],
        "replayed_frontier_hash": frontier["frontier_hash"],
        "frontier_replay_verified": True,
        "development_dataset_hash": development_state["dataset_hash"],
        "protocol_hash": protocol_state["protocol_hash"],
        "research_hash": research_state["research_hash"],
    }
    counts = {
        "development_row_count": int(development_state["row_count"]),
        "development_year_count": len(years),
        "frontier_group_count": len(evidence_rows),
        "family_count": len(family_evidence),
        "raw_candidate_count": int(
            frontier["stage_manifest"]["raw_candidate_count"]
        ),
        "method_local_pareto_count": int(
            frontier["stage_manifest"]["method_local_pareto_count"]
        ),
        "compressed_frontier_count": expected_frontier_count,
    }
    evidence_state = {
        "frontier_replay": "VERIFIED",
        "evidence_rows": "COMPLETE",
        "observed_breakpoint_curves": "COMPLETE",
        "exact_joint_profiles": "COMPLETE",
        "descriptive_summaries": "COMPLETE",
    }
    policy_state = {
        "admissibility_policy": "UNDEFINED",
        "policy_defined": False,
        "policy_approved": False,
        "event_unit": "UNSET",
        "episode_rate_unit": "UNSET",
        "minimum_sample_unit": "UNSET",
        "evaluation_rule": "UNSET",
        "final_threshold_selected": False,
        "minimum_sample_selected": False,
        "event_unit_selected": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }

    identity_payload = {
        "contract_version": RATE_SPIKE_ADMISSIBILITY_EVIDENCE_CONTRACT_VERSION,
        "source": source,
        "counts": counts,
        "development_years": years,
        "evidence_rows_payload_hash": content_hash(evidence_rows),
        "family_evidence_payload_hash": content_hash(family_evidence),
        "evidence_state": evidence_state,
        "policy_state": policy_state,
        "holdout_locked": True,
        "holdout_accessed": False,
        "network_requests": 0,
        "macro_db_writes": 0,
        "production_impact": "NONE",
    }
    evidence_hash = content_hash(identity_payload)

    return {
        **identity_payload,
        "evidence_id": f"RATEEVID-{evidence_hash[:16]}",
        "evidence_hash": evidence_hash,
        "evidence_rows": evidence_rows,
        "families": family_evidence,
    }


def validate_admissibility_evidence(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    if (
        evidence.get("contract_version")
        != RATE_SPIKE_ADMISSIBILITY_EVIDENCE_CONTRACT_VERSION
    ):
        raise ValueError("Unsupported S4.2-B evidence contract.")
    if evidence.get("holdout_locked") is not True:
        raise ValueError("S4.2-B must keep Holdout locked.")
    if evidence.get("holdout_accessed") is not False:
        raise ValueError("S4.2-B must not access Holdout.")
    if int(evidence.get("network_requests") or 0) != 0:
        raise ValueError("S4.2-B must not use network.")
    if int(evidence.get("macro_db_writes") or 0) != 0:
        raise ValueError("S4.2-B must not write Macro DB.")
    if evidence.get("production_impact") != "NONE":
        raise ValueError("S4.2-B must have no Production impact.")

    source = evidence.get("source") or {}
    if source.get("frontier_replay_verified") is not True:
        raise ValueError("S4.2-B requires verified frontier replay.")
    if source.get("source_frontier_hash") != source.get("replayed_frontier_hash"):
        raise ValueError("S4.2-B source/replay frontier hashes differ.")
    if source.get("source_frontier_id") != source.get("replayed_frontier_id"):
        raise ValueError("S4.2-B source/replay frontier ids differ.")

    policy = evidence.get("policy_state") or {}
    expected_policy = {
        "admissibility_policy": "UNDEFINED",
        "policy_defined": False,
        "policy_approved": False,
        "event_unit": "UNSET",
        "episode_rate_unit": "UNSET",
        "minimum_sample_unit": "UNSET",
        "evaluation_rule": "UNSET",
        "final_threshold_selected": False,
        "minimum_sample_selected": False,
        "event_unit_selected": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    if policy != expected_policy:
        raise ValueError("S4.2-B policy state must remain fully unselected.")

    state = evidence.get("evidence_state") or {}
    if state != {
        "frontier_replay": "VERIFIED",
        "evidence_rows": "COMPLETE",
        "observed_breakpoint_curves": "COMPLETE",
        "exact_joint_profiles": "COMPLETE",
        "descriptive_summaries": "COMPLETE",
    }:
        raise ValueError("S4.2-B evidence completion state mismatch.")

    rows = list(evidence.get("evidence_rows") or [])
    families = list(evidence.get("families") or [])
    counts = evidence.get("counts") or {}
    if len(rows) != int(counts.get("frontier_group_count") or 0):
        raise ValueError("S4.2-B evidence row accounting mismatch.")
    if len(rows) != int(counts.get("compressed_frontier_count") or 0):
        raise ValueError("S4.2-B compressed frontier accounting mismatch.")
    if len(families) != 9 or int(counts.get("family_count") or 0) != 9:
        raise ValueError("S4.2-B requires exactly 9 evidence families.")

    for row in rows:
        payload = {
            key: value
            for key, value in row.items()
            if key not in {"evidence_row_id", "evidence_row_hash"}
        }
        expected_hash = content_hash(payload)
        if row.get("evidence_row_hash") != expected_hash:
            raise ValueError("Evidence row hash mismatch.")
        if row.get("evidence_row_id") != f"RATEEVIDROW-{expected_hash[:16]}":
            raise ValueError("Evidence row id mismatch.")
        if int(row["episode_start_count"]) != int(row["episode_count"]):
            raise ValueError("S4.2-B episode start count must match episode count.")
        if row.get("holdout_accessed") is not False:
            raise ValueError("Evidence row cannot access Holdout.")

    expected_pairs = {
        (feature_id, method)
        for feature_id in RATE_SPIKE_FEATURE_IDS
        for method in RATE_SPIKE_METHODS
    }
    actual_pairs = {
        (str(item["feature_id"]), str(item["method"]))
        for item in families
    }
    if actual_pairs != expected_pairs:
        raise ValueError("S4.2-B family set mismatch.")

    for family in families:
        payload = {
            key: value
            for key, value in family.items()
            if key not in {"evidence_family_id", "evidence_family_hash"}
        }
        expected_hash = content_hash(payload)
        if family.get("evidence_family_hash") != expected_hash:
            raise ValueError("Evidence family hash mismatch.")
        if family.get("evidence_family_id") != f"RATEEVIDFAM-{expected_hash[:16]}":
            raise ValueError("Evidence family id mismatch.")
        if family.get("evidence_status") != "COMPLETE":
            raise ValueError("Evidence family must be complete.")
        if family.get("interpretation") != "DESCRIPTIVE_ONLY":
            raise ValueError("Evidence family must remain descriptive.")
        if family.get("admissibility_decision") != "NOT_DEFINED":
            raise ValueError("S4.2-B must not define admissibility.")
        if int(family.get("automatic_rejection_count") or 0) != 0:
            raise ValueError("S4.2-B must not reject candidates.")

        for axis, curve in family["observed_breakpoint_curves"].items():
            if curve.get("source") != "OBSERVED_FRONTIER_VALUES_ONLY":
                raise ValueError("Breakpoint curve contains non-observed source.")
            if int(curve.get("invented_grid_points") or 0) != 0:
                raise ValueError("S4.2-B cannot invent breakpoint grid values.")
            points = list(curve.get("points") or [])
            if int(curve.get("point_count") or 0) != len(points):
                raise ValueError("Breakpoint curve point count mismatch.")
            observed_values = [
                item["value"] for item in points
            ]
            if len(observed_values) != len(set(str(item) for item in observed_values)):
                raise ValueError("Breakpoint curve values must be unique.")

        for summary in family["descriptive_summaries"].values():
            if summary.get("status") == "DESCRIPTIVE_ONLY":
                if summary.get("quantile_method") != OBSERVED_ORDER_STATISTIC_METHOD:
                    raise ValueError("Unsupported observed quantile method.")

        for profile in family["exact_joint_profiles"]:
            if profile.get("rank") is not None:
                raise ValueError("S4.2-B must not rank evidence profiles.")
            if profile.get("score") is not None:
                raise ValueError("S4.2-B must not score evidence profiles.")
            if profile.get("recommended") is not False:
                raise ValueError("S4.2-B must not recommend evidence profiles.")

    if evidence.get("evidence_rows_payload_hash") != content_hash(rows):
        raise ValueError("Evidence rows payload hash mismatch.")
    if evidence.get("family_evidence_payload_hash") != content_hash(families):
        raise ValueError("Evidence family payload hash mismatch.")

    identity_payload = {
        key: evidence[key]
        for key in (
            "contract_version",
            "source",
            "counts",
            "development_years",
            "evidence_rows_payload_hash",
            "family_evidence_payload_hash",
            "evidence_state",
            "policy_state",
            "holdout_locked",
            "holdout_accessed",
            "network_requests",
            "macro_db_writes",
            "production_impact",
        )
    }
    expected_hash = content_hash(identity_payload)
    if evidence.get("evidence_hash") != expected_hash:
        raise ValueError("S4.2-B evidence hash mismatch.")
    if evidence.get("evidence_id") != f"RATEEVID-{expected_hash[:16]}":
        raise ValueError("S4.2-B evidence id mismatch.")

    return {
        "evidence_hash": expected_hash,
        "frontier_group_count": len(rows),
        "family_count": 9,
        "holdout_accessed": False,
        "ready_for_holdout": False,
    }


def _summary_triplet(
    family: dict[str, Any],
    axis: str,
    *,
    percent: bool = False,
) -> str:
    summary = family["descriptive_summaries"][axis]
    if summary["status"] != "DESCRIPTIVE_ONLY":
        return "N/A"
    values = (summary["min"], summary["median"], summary["max"])
    if percent:
        return "/".join(_percent_display(value) for value in values)
    return "/".join(_decimal_display(value) for value in values)


def render_admissibility_evidence_text(
    evidence: dict[str, Any],
) -> str:
    validate_admissibility_evidence(evidence)

    headers = (
        "Feat",
        "Meth",
        "Groups",
        "Signal% min/med/max",
        "Capture% min/med/max",
        "Ep/yr min/med/max",
        "YearCov min/med/max",
    )
    table_rows: list[tuple[str, ...]] = []
    for family in evidence["families"]:
        table_rows.append(
            (
                _FEATURE_LABELS[str(family["feature_id"])],
                _METHOD_LABELS[str(family["method"])],
                str(family["frontier_group_count"]),
                _summary_triplet(
                    family,
                    "signal_fraction",
                    percent=True,
                ),
                _summary_triplet(
                    family,
                    "positive_capture_fraction",
                    percent=True,
                ),
                _summary_triplet(
                    family,
                    "episode_starts_per_year",
                ),
                _summary_triplet(
                    family,
                    "year_coverage_count",
                ),
            )
        )

    widths = [
        max(len(headers[index]), *(len(row[index]) for row in table_rows))
        for index in range(len(headers))
    ]

    def format_row(row: tuple[str, ...]) -> str:
        return "  ".join(
            value.ljust(widths[index])
            for index, value in enumerate(row)
        )

    source = evidence["source"]
    counts = evidence["counts"]
    policy = evidence["policy_state"]
    lines = [
        "NEXT-6B-S4.2-B ADMISSIBILITY EVIDENCE MATRIX",
        "",
        f"Source Diagnostic : {source['diagnostic_id']} ({source['diagnostic_hash']})",
        f"Source Frontier   : {source['source_frontier_id']} ({source['source_frontier_hash']})",
        f"Replay Frontier   : {source['replayed_frontier_id']} ({source['replayed_frontier_hash']}) PASS",
        (
            "Frontier Groups / Families / Dev Years : "
            f"{counts['frontier_group_count']} / "
            f"{counts['family_count']} / "
            f"{counts['development_year_count']}"
        ),
        "",
        format_row(headers),
        format_row(tuple("-" * width for width in widths)),
    ]
    lines.extend(format_row(row) for row in table_rows)
    lines.extend(
        [
            "",
            (
                "Observed breakpoint curves / Exact joint profiles : "
                f"{evidence['evidence_state']['observed_breakpoint_curves']} / "
                f"{evidence['evidence_state']['exact_joint_profiles']}"
            ),
            (
                "Quantile display : "
                f"{OBSERVED_ORDER_STATISTIC_METHOD} (DESCRIPTIVE_ONLY)"
            ),
            (
                "Policy / Event unit / Episode rate unit / Minimum sample unit : "
                f"{policy['admissibility_policy']} / "
                f"{policy['event_unit']} / "
                f"{policy['episode_rate_unit']} / "
                f"{policy['minimum_sample_unit']}"
            ),
            f"Evaluation rule   : {policy['evaluation_rule']}",
            (
                "Threshold / Minimum sample / Event unit selected : "
                f"{policy['final_threshold_selected']} / "
                f"{policy['minimum_sample_selected']} / "
                f"{policy['event_unit_selected']}"
            ),
            (
                "Holdout locked / accessed / ready : "
                f"{evidence['holdout_locked']} / "
                f"{evidence['holdout_accessed']} / "
                f"{policy['ready_for_holdout']}"
            ),
            (
                "RATE_SPIKE / Network / Macro DB writes / Production : "
                f"{policy['rate_spike_state']} / "
                f"{evidence['network_requests']} / "
                f"{evidence['macro_db_writes']} / "
                f"{evidence['production_impact']}"
            ),
            "",
            "Evidence status: COMPLETE (no admissibility policy selected)",
        ]
    )
    return "\n".join(lines)
