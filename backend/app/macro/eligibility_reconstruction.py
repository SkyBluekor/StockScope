from __future__ import annotations

from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.macro.admissibility_evidence import (
    validate_admissibility_evidence,
)
from app.macro.calibration_candidate import (
    MACRO_CANDIDATE_GENERATION_CONTRACT_VERSION,
    RATE_SPIKE_FEATURE_IDS,
    RATE_SPIKE_METHODS,
    build_rate_spike_candidate_set,
    evaluate_candidate_behavior,
    generate_raw_feature_candidates,
    validate_candidate_set_artifact,
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
from app.macro.shock_episode import (
    RATE_SPIKE_EPISODE_POLICY_VERSION,
    build_consecutive_true_episodes,
)


RATE_SPIKE_ELIGIBILITY_POLICY_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B1_ELIGIBILITY_POLICY_V1"
)
RATE_SPIKE_ELIGIBILITY_RECONSTRUCTION_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B1_ELIGIBILITY_RECONSTRUCTION_V1"
)
RATE_SPIKE_RAW_LINEAGE_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B1_RAW_LINEAGE_V1"
)
RATE_SPIKE_PRIOR_SUPPORT_AUDIT_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B1_PRIOR_SUPPORT_AUDIT_V1"
)
RATE_SPIKE_SUPPORT_CURVE_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B1_SUPPORT_COUNTERFACTUAL_V1"
)

_FEATURE_ORDER = {
    feature_id: index for index, feature_id in enumerate(RATE_SPIKE_FEATURE_IDS)
}
_METHOD_ORDER = {
    method: index for index, method in enumerate(RATE_SPIKE_METHODS)
}
_FEATURE_LABELS = {
    "delta_bp_1obs": "1obs",
    "delta_bp_5obs": "5obs",
    "delta_bp_10obs": "10obs",
}
_METHOD_LABELS = {
    "EMPIRICAL_POSITIVE_TAIL": "EPT",
    "EXPANDING_POSITIVE_TAIL_FRACTION": "TAIL",
    "EXPANDING_ROBUST_MAD": "MAD",
}


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Eligibility reconstruction metric must be finite.")
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
    if value is None:
        return "N/A"
    percent = (_decimal(value) * Decimal("100")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    text = format(percent, "f").rstrip("0").rstrip(".")
    return f"{text or '0'}%"


def build_unset_eligibility_policy() -> dict[str, Any]:
    payload = {
        "contract_version": RATE_SPIKE_ELIGIBILITY_POLICY_CONTRACT_VERSION,
        "policy_id": "RATE_SPIKE_ELIGIBILITY_UNSET",
        "policy_version": "UNSET",
        "shock_type": "RATE_SPIKE",
        "status": "UNDEFINED",
        "reference_support_rule": "UNSET",
        "minimum_prior_observations": None,
        "insufficient_reference_state": "UNKNOWN",
        "missing_metric_state": "UNKNOWN",
        "approved": False,
        "production_decision_approved": False,
    }
    return payload


def _raw_candidates(
    *,
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
    research: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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

    candidates: list[dict[str, Any]] = []
    per_family: dict[str, Any] = {}
    for feature_id in RATE_SPIKE_FEATURE_IDS:
        generated = generate_raw_feature_candidates(
            feature_id=feature_id,
            feature_result=research["feature_results"][feature_id],
            development_dataset_hash=development_state["dataset_hash"],
            protocol_hash=protocol_state["protocol_hash"],
            research_hash=research_state["research_hash"],
        )
        for method in RATE_SPIKE_METHODS:
            items = list(generated[method])
            items.sort(
                key=lambda item: (
                    _decimal(item["threshold_value"]),
                    str(item["candidate_hash"]),
                )
            )
            candidates.extend(items)
            per_family[f"{feature_id}|{method}"] = {
                "feature_id": feature_id,
                "method": method,
                "raw_candidate_count": len(items),
                "raw_candidate_hashes": [
                    str(item["candidate_hash"]) for item in items
                ],
                "threshold_unit": (
                    str(items[0]["threshold_unit"]) if items else None
                ),
                "threshold_min": (
                    str(items[0]["threshold_value"]) if items else None
                ),
                "threshold_max": (
                    str(items[-1]["threshold_value"]) if items else None
                ),
            }

    candidates.sort(
        key=lambda item: (
            _FEATURE_ORDER[str(item["feature_id"])],
            _METHOD_ORDER[str(item["method"])],
            _decimal(item["threshold_value"]),
            str(item["candidate_hash"]),
        )
    )
    return candidates, per_family


def _validate_raw_replay(
    *,
    raw_candidates: list[dict[str, Any]],
    candidate_set: dict[str, Any],
) -> dict[str, Any]:
    replay_hashes = sorted(
        str(candidate["candidate_hash"]) for candidate in raw_candidates
    )
    manifest = candidate_set["exploration_manifest"]
    source_hashes = sorted(
        str(item) for item in manifest["generated_candidate_hashes"]
    )
    if replay_hashes != source_hashes:
        raise ValueError("Raw candidate replay differs from S4 generation manifest.")
    if len(replay_hashes) != int(manifest["generated_candidate_count"]):
        raise ValueError("Raw candidate replay count mismatch.")
    return {
        "source_generation_contract_version": (
            manifest["generation_contract_version"]
        ),
        "expected_generation_contract_version": (
            MACRO_CANDIDATE_GENERATION_CONTRACT_VERSION
        ),
        "raw_candidate_count": len(replay_hashes),
        "raw_candidate_hashes_hash": content_hash(replay_hashes),
        "raw_replay_status": "PASS",
    }


def _lineage_maps(
    *,
    candidate_set: dict[str, Any],
    frontier: dict[str, Any],
) -> dict[str, Any]:
    method_dominated = {
        str(item["candidate_hash"]): item
        for item in candidate_set["dominated_candidates"]
    }
    method_frontier = {
        str(item["candidate_hash"]): item
        for item in candidate_set["frozen_candidates"]
    }
    trivial = {
        str(item["candidate_hash"]): item
        for item in frontier["trivial_direction_candidates"]
    }

    group_by_candidate: dict[str, dict[str, Any]] = {}
    for group in frontier["behavior_groups"]:
        hashes = sorted(str(item) for item in group["source_candidate_hashes"])
        canonical = hashes[0] if hashes else None
        for candidate_hash in hashes:
            if candidate_hash in group_by_candidate:
                raise ValueError("Candidate appears in multiple behavior groups.")
            group_by_candidate[candidate_hash] = {
                "behavior_group_id": group["behavior_group_id"],
                "behavior_group_hash": group["behavior_group_hash"],
                "source_candidate_count": int(group["source_candidate_count"]),
                "canonical_candidate_hash": canonical,
                "behavior_duplicate_grouped": (
                    len(hashes) > 1 and candidate_hash != canonical
                ),
            }

    final_groups = {
        str(group["behavior_group_hash"])
        for group in frontier["frontier_groups"]
    }
    cross_dominated_groups = {
        str(group["behavior_group_hash"]): group
        for group in frontier["cross_method_dominated_groups"]
    }

    return {
        "method_dominated": method_dominated,
        "method_frontier": method_frontier,
        "trivial": trivial,
        "group_by_candidate": group_by_candidate,
        "final_groups": final_groups,
        "cross_dominated_groups": cross_dominated_groups,
    }


def _lineage_for_candidate(
    candidate: dict[str, Any],
    maps: dict[str, Any],
) -> dict[str, Any]:
    candidate_hash = str(candidate["candidate_hash"])

    if candidate_hash in maps["method_dominated"]:
        source = maps["method_dominated"][candidate_hash]
        return {
            "contract_version": RATE_SPIKE_RAW_LINEAGE_CONTRACT_VERSION,
            "candidate_hash": candidate_hash,
            "method_local_stage": "DOMINATED",
            "trivial_direction_removed": False,
            "behavior_group_id": None,
            "behavior_group_hash": None,
            "behavior_duplicate_grouped": False,
            "group_disposition": "NOT_REACHED",
            "legacy_pipeline_status": "METHOD_LOCAL_DOMINATED",
            "legacy_removal_stage": "S4_METHOD_LOCAL_PARETO",
            "legacy_removal_reason": "METHOD_LOCAL_PARETO_DOMINATED",
            "legacy_dominated_by": source.get("dominated_by"),
        }

    if candidate_hash not in maps["method_frontier"]:
        raise ValueError("Raw candidate is missing from S4 Pareto accounting.")

    if candidate_hash in maps["trivial"]:
        return {
            "contract_version": RATE_SPIKE_RAW_LINEAGE_CONTRACT_VERSION,
            "candidate_hash": candidate_hash,
            "method_local_stage": "FRONTIER",
            "trivial_direction_removed": True,
            "behavior_group_id": None,
            "behavior_group_hash": None,
            "behavior_duplicate_grouped": False,
            "group_disposition": "NOT_REACHED",
            "legacy_pipeline_status": "TRIVIAL_DIRECTION_REMOVED",
            "legacy_removal_stage": "S4_1_TRIVIAL_DIRECTION",
            "legacy_removal_reason": "TRIVIAL_DIRECTION_RULE",
            "legacy_dominated_by": None,
        }

    group = maps["group_by_candidate"].get(candidate_hash)
    if group is None:
        raise ValueError(
            "Non-trivial S4 frontier candidate has no S4.1 behavior group."
        )
    group_hash = str(group["behavior_group_hash"])
    duplicate = bool(group["behavior_duplicate_grouped"])

    if duplicate:
        disposition = (
            "FINAL_FRONTIER"
            if group_hash in maps["final_groups"]
            else "CROSS_METHOD_DOMINATED"
            if group_hash in maps["cross_dominated_groups"]
            else "UNKNOWN"
        )
        if disposition == "UNKNOWN":
            raise ValueError("Duplicate behavior group disposition is unknown.")
        return {
            "contract_version": RATE_SPIKE_RAW_LINEAGE_CONTRACT_VERSION,
            "candidate_hash": candidate_hash,
            "method_local_stage": "FRONTIER",
            "trivial_direction_removed": False,
            "behavior_group_id": group["behavior_group_id"],
            "behavior_group_hash": group_hash,
            "behavior_duplicate_grouped": True,
            "group_disposition": disposition,
            "legacy_pipeline_status": "BEHAVIOR_DUPLICATE_GROUPED",
            "legacy_removal_stage": "S4_1_BEHAVIOR_GROUPING",
            "legacy_removal_reason": "IDENTICAL_BEHAVIOR_GROUP",
            "legacy_dominated_by": None,
        }

    if group_hash in maps["final_groups"]:
        return {
            "contract_version": RATE_SPIKE_RAW_LINEAGE_CONTRACT_VERSION,
            "candidate_hash": candidate_hash,
            "method_local_stage": "FRONTIER",
            "trivial_direction_removed": False,
            "behavior_group_id": group["behavior_group_id"],
            "behavior_group_hash": group_hash,
            "behavior_duplicate_grouped": False,
            "group_disposition": "FINAL_FRONTIER",
            "legacy_pipeline_status": "FINAL_FRONTIER",
            "legacy_removal_stage": None,
            "legacy_removal_reason": None,
            "legacy_dominated_by": None,
        }

    dominated_group = maps["cross_dominated_groups"].get(group_hash)
    if dominated_group is not None:
        return {
            "contract_version": RATE_SPIKE_RAW_LINEAGE_CONTRACT_VERSION,
            "candidate_hash": candidate_hash,
            "method_local_stage": "FRONTIER",
            "trivial_direction_removed": False,
            "behavior_group_id": group["behavior_group_id"],
            "behavior_group_hash": group_hash,
            "behavior_duplicate_grouped": False,
            "group_disposition": "CROSS_METHOD_DOMINATED",
            "legacy_pipeline_status": "CROSS_METHOD_DOMINATED",
            "legacy_removal_stage": "S4_1_CROSS_METHOD_PARETO",
            "legacy_removal_reason": "CROSS_METHOD_PARETO_DOMINATED",
            "legacy_dominated_by": dominated_group.get(
                "dominated_by_group_hash"
            ),
        }

    raise ValueError("S4.1 behavior group is missing a final disposition.")


def _candidate_prior_support_audit(
    *,
    candidate: dict[str, Any],
    feature_result: dict[str, Any],
) -> dict[str, Any]:
    behavior_rows = evaluate_candidate_behavior(
        feature_result=feature_result,
        candidate=candidate,
    )
    expanding_rows = list(feature_result["expanding"]["rows"])
    if len(behavior_rows) != len(expanding_rows):
        raise ValueError("Candidate behavior row count differs from research rows.")

    enriched: list[dict[str, Any]] = []
    for behavior, research_row in zip(behavior_rows, expanding_rows):
        if str(behavior["row_hash"]) != str(research_row["row_hash"]):
            raise ValueError("Candidate/research row ordering mismatch.")
        enriched.append(
            {
                "observation_date": str(behavior["observation_date"]),
                "row_hash": str(behavior["row_hash"]),
                "prior_count": int(research_row["prior_count"]),
                "eligible": bool(behavior["eligible"]),
                "signal": bool(behavior["signal"]),
            }
        )

    eligible_rows = [row for row in enriched if row["eligible"]]
    signal_rows = [row for row in enriched if row["signal"]]
    if not signal_rows:
        raise ValueError("Raw S4 candidate must have at least one signal.")

    method = str(candidate["method"])
    reference_applicable = method != "EMPIRICAL_POSITIVE_TAIL"
    first_computable = (
        min(row["prior_count"] for row in eligible_rows)
        if eligible_rows
        else None
    )
    first_signal = min(row["prior_count"] for row in signal_rows)
    max_signal = max(row["prior_count"] for row in signal_rows)

    episode = build_consecutive_true_episodes(enriched)
    if int(episode["episode_count"]) != int(
        candidate["episode_summary"]["episode_count"]
    ):
        raise ValueError("Prior-support audit changed baseline episode count.")

    payload = {
        "contract_version": RATE_SPIKE_PRIOR_SUPPORT_AUDIT_CONTRACT_VERSION,
        "candidate_id": candidate["candidate_id"],
        "candidate_hash": candidate["candidate_hash"],
        "feature_id": candidate["feature_id"],
        "method": method,
        "threshold_value": candidate["threshold_value"],
        "threshold_unit": candidate["threshold_unit"],
        "baseline_required_condition": candidate["required_condition"],
        "reference_support_applicable": reference_applicable,
        "baseline_computability_min_prior": first_computable,
        "first_signal_prior_count": first_signal,
        "min_signal_prior_count": first_signal,
        "max_signal_prior_count": max_signal,
        "first_signal_observation_date": next(
            row["observation_date"]
            for row in signal_rows
            if row["prior_count"] == first_signal
        ),
        "baseline_eligible_count": len(eligible_rows),
        "baseline_signal_count": len(signal_rows),
        "baseline_episode_count": int(episode["episode_count"]),
        "legacy_derived_minimum_prior_support": int(
            candidate["derived_minimum_prior_support"]
        ),
        "legacy_minimum_prior_support_derivation": candidate[
            "minimum_prior_support_derivation"
        ],
        "legacy_support_is_eligibility_enforced": False,
        "legacy_support_is_statistical_precision_guarantee": False,
        "approved_reference_support": "UNSET",
        "signal_before_reference_policy_count": "NOT_EVALUATED",
        "holdout_accessed": False,
        "production_decision_approved": False,
    }
    audit_hash = content_hash(payload)
    return {
        **payload,
        "audit_id": f"RATEELIGAUD-{audit_hash[:16]}",
        "audit_hash": audit_hash,
    }


def _int_distribution(values: list[int | None]) -> dict[str, Any]:
    concrete = [int(value) for value in values if value is not None]
    if not concrete:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "unique_value_count": 0,
            "histogram": [],
        }
    counts = Counter(concrete)
    return {
        "count": len(concrete),
        "min": min(concrete),
        "max": max(concrete),
        "unique_value_count": len(counts),
        "histogram": [
            {"value": value, "candidate_count": counts[value]}
            for value in sorted(counts)
        ],
    }


def _support_curve(
    *,
    feature_result: dict[str, Any],
    candidate_audits: list[dict[str, Any]],
    raw_candidates_by_hash: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not candidate_audits:
        return {
            "contract_version": RATE_SPIKE_SUPPORT_CURVE_CONTRACT_VERSION,
            "status": "NO_CANDIDATES",
            "source": "OBSERVED_PRIOR_COUNTS_ONLY",
            "invented_grid_points": 0,
            "reference_support_applicable": None,
            "point_count": 0,
            "points": [],
        }

    method = str(candidate_audits[0]["method"])
    if method == "EMPIRICAL_POSITIVE_TAIL":
        return {
            "contract_version": RATE_SPIKE_SUPPORT_CURVE_CONTRACT_VERSION,
            "status": "NOT_APPLICABLE",
            "source": "OBSERVED_PRIOR_COUNTS_ONLY",
            "invented_grid_points": 0,
            "reference_support_applicable": False,
            "point_count": 0,
            "points": [],
        }

    research_rows = list(feature_result["expanding"]["rows"])
    observed_supports = sorted(
        {
            int(row["prior_count"])
            for row in research_rows
            if int(row["prior_count"]) > 0
        }
    )
    if not observed_supports:
        return {
            "contract_version": RATE_SPIKE_SUPPORT_CURVE_CONTRACT_VERSION,
            "status": "NO_OBSERVED_PRIOR_COUNTS",
            "source": "OBSERVED_PRIOR_COUNTS_ONLY",
            "invented_grid_points": 0,
            "reference_support_applicable": True,
            "point_count": 0,
            "points": [],
        }

    # Precompute each candidate's baseline state once. A hypothetical support
    # rule only masks rows with prior_count below the observed support point.
    per_candidate: list[dict[str, Any]] = []
    for audit in candidate_audits:
        candidate = raw_candidates_by_hash[str(audit["candidate_hash"])]
        behavior_rows = evaluate_candidate_behavior(
            feature_result=feature_result,
            candidate=candidate,
        )
        rows: list[dict[str, Any]] = []
        previous_signal = False
        for behavior, research_row in zip(behavior_rows, research_rows):
            signal = bool(behavior["signal"])
            episode_start = bool(signal and not previous_signal)
            rows.append(
                {
                    "prior_count": int(research_row["prior_count"]),
                    "eligible": bool(behavior["eligible"]),
                    "signal": signal,
                    "episode_start": episode_start,
                    "year": str(behavior["observation_date"])[:4],
                }
            )
            previous_signal = signal
        per_candidate.append(
            {
                "candidate_hash": candidate["candidate_hash"],
                "rows": rows,
            }
        )

    points: list[dict[str, Any]] = []
    previous_signature: str | None = None

    for support in observed_supports:
        candidate_metrics: list[dict[str, Any]] = []
        for item in per_candidate:
            rows = [
                row for row in item["rows"]
                if row["prior_count"] >= support
            ]
            eligible_count = sum(row["eligible"] for row in rows)
            signal_count = sum(row["signal"] for row in rows)
            episode_start_rows = [
                row for row in rows if row["episode_start"]
            ]
            episode_start_count = len(episode_start_rows)
            covered_years = len(
                {row["year"] for row in episode_start_rows}
            )
            candidate_metrics.append(
                {
                    "candidate_hash": item["candidate_hash"],
                    "eligible_count": eligible_count,
                    "signal_count": signal_count,
                    "episode_start_count": episode_start_count,
                    "covered_year_count": covered_years,
                }
            )

        active = [
            metric for metric in candidate_metrics
            if metric["signal_count"] > 0
        ]
        signature_payload = [
            (
                metric["candidate_hash"],
                metric["signal_count"],
                metric["episode_start_count"],
                metric["covered_year_count"],
            )
            for metric in candidate_metrics
        ]
        signature = content_hash(signature_payload)

        # Keep only signal/event behavior change points. Eligible counts are
        # reported at those points but do not create a point by themselves.
        if signature == previous_signature:
            continue
        previous_signature = signature

        eligible_values = [
            metric["eligible_count"] for metric in candidate_metrics
        ]
        signal_values = [
            metric["signal_count"] for metric in active
        ]
        episode_values = [
            metric["episode_start_count"] for metric in active
        ]
        coverage_values = [
            metric["covered_year_count"] for metric in active
        ]
        points.append(
            {
                "minimum_prior_observations": support,
                "active_candidate_count": len(active),
                "inactive_candidate_count": (
                    len(candidate_metrics) - len(active)
                ),
                "eligible_count_range": {
                    "min": min(eligible_values) if eligible_values else None,
                    "max": max(eligible_values) if eligible_values else None,
                },
                "signal_count_range": {
                    "min": min(signal_values) if signal_values else None,
                    "max": max(signal_values) if signal_values else None,
                },
                "episode_start_count_range": {
                    "min": min(episode_values) if episode_values else None,
                    "max": max(episode_values) if episode_values else None,
                },
                "covered_year_count_range": {
                    "min": min(coverage_values) if coverage_values else None,
                    "max": max(coverage_values) if coverage_values else None,
                },
                "candidate_behavior_signature_hash": signature,
            }
        )

    return {
        "contract_version": RATE_SPIKE_SUPPORT_CURVE_CONTRACT_VERSION,
        "status": "DIAGNOSTIC_ONLY",
        "source": "OBSERVED_PRIOR_COUNTS_ONLY",
        "compression_rule": "SIGNAL_EVENT_BEHAVIOR_CHANGE_POINTS_ONLY",
        "eligible_only_changes_create_points": False,
        "invented_grid_points": 0,
        "reference_support_applicable": True,
        "point_count": len(points),
        "points": points,
        "selection_status": "NOT_SELECTED",
        "recommended_support": None,
    }


def _family_summary(
    *,
    feature_id: str,
    method: str,
    audits: list[dict[str, Any]],
    feature_result: dict[str, Any],
    raw_candidates_by_hash: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    family_audits = [
        audit
        for audit in audits
        if audit["feature_id"] == feature_id and audit["method"] == method
    ]
    family_audits.sort(
        key=lambda item: (
            _decimal(item["threshold_value"]),
            str(item["candidate_hash"]),
        )
    )
    return {
        "feature_id": feature_id,
        "method": method,
        "raw_candidate_count": len(family_audits),
        "reference_support_applicable": (
            method != "EMPIRICAL_POSITIVE_TAIL"
        ),
        "first_computable_prior_count_distribution": _int_distribution(
            [
                item["baseline_computability_min_prior"]
                for item in family_audits
            ]
        ),
        "first_signal_prior_count_distribution": _int_distribution(
            [item["first_signal_prior_count"] for item in family_audits]
        ),
        "min_signal_prior_count_distribution": _int_distribution(
            [item["min_signal_prior_count"] for item in family_audits]
        ),
        "max_signal_prior_count_distribution": _int_distribution(
            [item["max_signal_prior_count"] for item in family_audits]
        ),
        "observed_support_counterfactual": _support_curve(
            feature_result=feature_result,
            candidate_audits=family_audits,
            raw_candidates_by_hash=raw_candidates_by_hash,
        ),
        "selection_status": "NOT_SELECTED",
    }


def build_eligibility_reconstruction(
    *,
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
    research: dict[str, Any],
    diagnostic: dict[str, Any],
    evidence: dict[str, Any],
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
    validate_frontier_admissibility_diagnostic(diagnostic)
    validate_admissibility_evidence(evidence)

    if diagnostic["development_dataset_hash"] != development_state["dataset_hash"]:
        raise ValueError("Diagnostic Development hash differs from B.1 input.")
    if diagnostic["protocol_hash"] != protocol_state["protocol_hash"]:
        raise ValueError("Diagnostic Protocol hash differs from B.1 input.")
    if diagnostic["research_hash"] != research_state["research_hash"]:
        raise ValueError("Diagnostic Research hash differs from B.1 input.")
    if evidence["source"]["diagnostic_hash"] != diagnostic["diagnostic_hash"]:
        raise ValueError("S4.2-B evidence Diagnostic hash mismatch.")
    if evidence["source"]["development_dataset_hash"] != development_state["dataset_hash"]:
        raise ValueError("S4.2-B evidence Development hash mismatch.")
    if evidence["source"]["protocol_hash"] != protocol_state["protocol_hash"]:
        raise ValueError("S4.2-B evidence Protocol hash mismatch.")
    if evidence["source"]["research_hash"] != research_state["research_hash"]:
        raise ValueError("S4.2-B evidence Research hash mismatch.")

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

    if diagnostic["source_candidate_set_hash"] != candidate_set["candidate_set_hash"]:
        raise ValueError("Replayed S4 candidate set differs from Diagnostic.")
    if diagnostic["source_frontier_hash"] != frontier["frontier_hash"]:
        raise ValueError("Replayed S4.1 frontier differs from Diagnostic.")
    if evidence["source"]["source_frontier_hash"] != frontier["frontier_hash"]:
        raise ValueError("S4.2-B evidence source frontier differs from replay.")

    raw_candidates, raw_family_manifest = _raw_candidates(
        development_dataset=development_dataset,
        protocol=protocol,
        research=research,
    )
    raw_replay = _validate_raw_replay(
        raw_candidates=raw_candidates,
        candidate_set=candidate_set,
    )
    raw_candidates_by_hash = {
        str(candidate["candidate_hash"]): candidate
        for candidate in raw_candidates
    }

    maps = _lineage_maps(
        candidate_set=candidate_set,
        frontier=frontier,
    )
    lineage: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    for candidate in raw_candidates:
        line = _lineage_for_candidate(candidate, maps)
        audit = _candidate_prior_support_audit(
            candidate=candidate,
            feature_result=research["feature_results"][
                str(candidate["feature_id"])
            ],
        )
        lineage.append(line)
        audits.append(audit)

    lineage.sort(key=lambda item: str(item["candidate_hash"]))
    audits.sort(key=lambda item: str(item["candidate_hash"]))

    if len(lineage) != len(raw_candidates):
        raise ValueError("Every raw candidate must have legacy lineage.")
    if len(audits) != len(raw_candidates):
        raise ValueError("Every raw candidate must have prior-support audit.")

    families: list[dict[str, Any]] = []
    for feature_id in RATE_SPIKE_FEATURE_IDS:
        for method in RATE_SPIKE_METHODS:
            families.append(
                _family_summary(
                    feature_id=feature_id,
                    method=method,
                    audits=audits,
                    feature_result=research["feature_results"][feature_id],
                    raw_candidates_by_hash=raw_candidates_by_hash,
                )
            )
    families.sort(
        key=lambda item: (
            _FEATURE_ORDER[str(item["feature_id"])],
            _METHOD_ORDER[str(item["method"])],
        )
    )

    episode_contract = build_consecutive_true_episodes([])
    episode_semantics = {
        "policy_version": episode_contract["policy_version"],
        "start_rule": episode_contract["start_rule"],
        "continue_rule": episode_contract["continue_rule"],
        "end_rule": episode_contract["end_rule"],
        "gap_tolerance_observations": episode_contract[
            "gap_tolerance_observations"
        ],
        "repeat_alert_rule": episode_contract["repeat_alert_rule"],
        "event_count_semantics": "EPISODE_START",
        "episode_count_equals_episode_start_count_under_current_policy": True,
        "left_boundary_episode_state_rule": "REQUIRE_PRIOR_STATE",
        "left_boundary_rule_status": "DEFINED",
        "calendar_day_adjacency": False,
    }
    if episode_semantics["policy_version"] != RATE_SPIKE_EPISODE_POLICY_VERSION:
        raise ValueError("Episode policy version mismatch.")

    lineage_counts = Counter(
        str(item["legacy_pipeline_status"]) for item in lineage
    )
    ordering_contract = {
        "candidate_universe_scope": "FROZEN_RAW_GENERATION",
        "pipeline_order": [
            "RAW_CANDIDATE_GENERATION",
            "ELIGIBILITY",
            "ADMISSIBILITY",
            "BEHAVIOR_GROUPING",
            "POLICY_PRESERVING_COMPRESSION",
        ],
        "admissibility_applied": False,
        "post_admissibility_compression": "NOT_READY",
        "legacy_compression_is_not_policy_preserving_for_future_admissibility": True,
    }
    policy_state = {
        "eligibility_policy": build_unset_eligibility_policy(),
        "eligibility_policy_defined": False,
        "minimum_prior_observations_selected": False,
        "admissibility_policy_defined": False,
        "final_candidate_selected": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }

    source = {
        "development_dataset_hash": development_state["dataset_hash"],
        "protocol_hash": protocol_state["protocol_hash"],
        "research_hash": research_state["research_hash"],
        "candidate_set_id": candidate_set["candidate_set_id"],
        "candidate_set_hash": candidate_set["candidate_set_hash"],
        "diagnostic_id": diagnostic["diagnostic_id"],
        "diagnostic_hash": diagnostic["diagnostic_hash"],
        "frontier_id": frontier["frontier_id"],
        "frontier_hash": frontier["frontier_hash"],
        "evidence_id": evidence["evidence_id"],
        "evidence_hash": evidence["evidence_hash"],
    }
    counts = {
        "raw_candidate_count": len(raw_candidates),
        "method_local_pareto_count": int(
            frontier["stage_manifest"]["method_local_pareto_count"]
        ),
        "legacy_frontier_count": int(
            frontier["stage_manifest"]["compressed_frontier_count"]
        ),
        "family_count": len(families),
        "lineage_status_counts": dict(sorted(lineage_counts.items())),
    }

    identity_payload = {
        "contract_version": RATE_SPIKE_ELIGIBILITY_RECONSTRUCTION_CONTRACT_VERSION,
        "source": source,
        "raw_replay": raw_replay,
        "counts": counts,
        "raw_family_manifest_hash": content_hash(raw_family_manifest),
        "raw_candidate_hashes_hash": content_hash(
            sorted(raw_candidates_by_hash)
        ),
        "lineage_payload_hash": content_hash(lineage),
        "prior_support_audit_payload_hash": content_hash(audits),
        "family_payload_hash": content_hash(families),
        "episode_semantics": episode_semantics,
        "ordering_contract": ordering_contract,
        "policy_state": policy_state,
        "holdout_locked": True,
        "holdout_accessed": False,
        "network_requests": 0,
        "macro_db_writes": 0,
        "production_impact": "NONE",
    }
    reconstruction_hash = content_hash(identity_payload)

    return {
        **identity_payload,
        "reconstruction_id": f"RATEELIGREC-{reconstruction_hash[:16]}",
        "reconstruction_hash": reconstruction_hash,
        "reconstruction_status": "COMPLETE",
        "raw_family_manifest": raw_family_manifest,
        "legacy_lineage": lineage,
        "prior_support_audits": audits,
        "families": families,
    }


def validate_eligibility_reconstruction(
    reconstruction: dict[str, Any],
) -> dict[str, Any]:
    if (
        reconstruction.get("contract_version")
        != RATE_SPIKE_ELIGIBILITY_RECONSTRUCTION_CONTRACT_VERSION
    ):
        raise ValueError("Unsupported S4.2-B.1 reconstruction contract.")
    if reconstruction.get("reconstruction_status") != "COMPLETE":
        raise ValueError("S4.2-B.1 reconstruction must be complete.")
    if reconstruction.get("holdout_locked") is not True:
        raise ValueError("S4.2-B.1 must keep Holdout locked.")
    if reconstruction.get("holdout_accessed") is not False:
        raise ValueError("S4.2-B.1 must not access Holdout.")
    if int(reconstruction.get("network_requests") or 0) != 0:
        raise ValueError("S4.2-B.1 must not use network.")
    if int(reconstruction.get("macro_db_writes") or 0) != 0:
        raise ValueError("S4.2-B.1 must not write Macro DB.")
    if reconstruction.get("production_impact") != "NONE":
        raise ValueError("S4.2-B.1 must have no Production impact.")

    raw_replay = reconstruction.get("raw_replay") or {}
    if raw_replay.get("raw_replay_status") != "PASS":
        raise ValueError("S4.2-B.1 raw replay must pass.")
    if (
        raw_replay.get("source_generation_contract_version")
        != MACRO_CANDIDATE_GENERATION_CONTRACT_VERSION
    ):
        raise ValueError("S4.2-B.1 generation contract mismatch.")
    if (
        raw_replay.get("expected_generation_contract_version")
        != MACRO_CANDIDATE_GENERATION_CONTRACT_VERSION
    ):
        raise ValueError("S4.2-B.1 expected generation contract mismatch.")

    policy = reconstruction.get("policy_state") or {}
    if policy.get("eligibility_policy_defined") is not False:
        raise ValueError("Eligibility policy must remain undefined.")
    if policy.get("minimum_prior_observations_selected") is not False:
        raise ValueError("Minimum prior observations must remain unselected.")
    if policy.get("admissibility_policy_defined") is not False:
        raise ValueError("Admissibility policy must remain undefined.")
    if policy.get("final_candidate_selected") is not False:
        raise ValueError("S4.2-B.1 must not select a final candidate.")
    if policy.get("ready_for_holdout") is not False:
        raise ValueError("S4.2-B.1 must not be Holdout-ready.")
    if policy.get("rate_spike_state") != "UNCALIBRATED":
        raise ValueError("RATE_SPIKE must remain UNCALIBRATED.")

    eligibility = policy.get("eligibility_policy") or {}
    if eligibility != build_unset_eligibility_policy():
        raise ValueError("Eligibility policy placeholder changed unexpectedly.")

    ordering = reconstruction.get("ordering_contract") or {}
    if ordering.get("candidate_universe_scope") != "FROZEN_RAW_GENERATION":
        raise ValueError("Candidate universe must be frozen raw generation.")
    if ordering.get("pipeline_order") != [
        "RAW_CANDIDATE_GENERATION",
        "ELIGIBILITY",
        "ADMISSIBILITY",
        "BEHAVIOR_GROUPING",
        "POLICY_PRESERVING_COMPRESSION",
    ]:
        raise ValueError("S4.2-B.1 pipeline order mismatch.")
    if ordering.get("admissibility_applied") is not False:
        raise ValueError("S4.2-B.1 must not apply admissibility.")
    if ordering.get("post_admissibility_compression") != "NOT_READY":
        raise ValueError("Post-admissibility compression must remain NOT_READY.")

    counts = reconstruction.get("counts") or {}
    lineage = list(reconstruction.get("legacy_lineage") or [])
    audits = list(reconstruction.get("prior_support_audits") or [])
    families = list(reconstruction.get("families") or [])
    raw_manifest = reconstruction.get("raw_family_manifest") or {}

    raw_count = int(counts.get("raw_candidate_count") or 0)
    if raw_count <= 0:
        raise ValueError("S4.2-B.1 requires a non-empty raw universe.")
    if len(lineage) != raw_count or len(audits) != raw_count:
        raise ValueError("S4.2-B.1 raw candidate audit accounting mismatch.")
    if len(families) != 9 or int(counts.get("family_count") or 0) != 9:
        raise ValueError("S4.2-B.1 requires exactly 9 families.")

    lineage_hashes = [str(item["candidate_hash"]) for item in lineage]
    audit_hashes = [str(item["candidate_hash"]) for item in audits]
    if len(set(lineage_hashes)) != raw_count:
        raise ValueError("Legacy lineage contains duplicate candidates.")
    if sorted(lineage_hashes) != sorted(audit_hashes):
        raise ValueError("Lineage and prior-support audit universes differ.")

    raw_manifest_hashes = sorted(
        str(candidate_hash)
        for family in raw_manifest.values()
        for candidate_hash in family["raw_candidate_hashes"]
    )
    if sorted(lineage_hashes) != raw_manifest_hashes:
        raise ValueError("Raw family manifest differs from lineage universe.")
    if reconstruction.get("raw_candidate_hashes_hash") != content_hash(
        sorted(lineage_hashes)
    ):
        raise ValueError("Raw candidate hash manifest mismatch.")

    if reconstruction.get("raw_family_manifest_hash") != content_hash(
        raw_manifest
    ):
        raise ValueError("Raw family manifest hash mismatch.")
    if reconstruction.get("lineage_payload_hash") != content_hash(lineage):
        raise ValueError("Legacy lineage payload hash mismatch.")
    if reconstruction.get("prior_support_audit_payload_hash") != content_hash(
        audits
    ):
        raise ValueError("Prior-support audit payload hash mismatch.")
    if reconstruction.get("family_payload_hash") != content_hash(families):
        raise ValueError("Family payload hash mismatch.")

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
        raise ValueError("S4.2-B.1 family set mismatch.")

    for audit in audits:
        if audit.get("legacy_support_is_eligibility_enforced") is not False:
            raise ValueError(
                "Legacy derived support cannot be treated as eligibility."
            )
        if (
            audit.get("legacy_support_is_statistical_precision_guarantee")
            is not False
        ):
            raise ValueError(
                "Legacy derived support cannot claim statistical precision."
            )
        if audit.get("approved_reference_support") != "UNSET":
            raise ValueError("Reference support must remain UNSET.")

    for family in families:
        curve = family["observed_support_counterfactual"]
        if int(curve.get("invented_grid_points") or 0) != 0:
            raise ValueError("S4.2-B.1 cannot invent support grid points.")
        if curve.get("recommended_support") is not None:
            raise ValueError("S4.2-B.1 must not recommend support.")
        if curve.get("status") == "DIAGNOSTIC_ONLY":
            supports = [
                int(point["minimum_prior_observations"])
                for point in curve["points"]
            ]
            if supports != sorted(set(supports)):
                raise ValueError("Support counterfactual points must be unique.")

    identity_payload = {
        key: reconstruction[key]
        for key in (
            "contract_version",
            "source",
            "raw_replay",
            "counts",
            "raw_family_manifest_hash",
            "raw_candidate_hashes_hash",
            "lineage_payload_hash",
            "prior_support_audit_payload_hash",
            "family_payload_hash",
            "episode_semantics",
            "ordering_contract",
            "policy_state",
            "holdout_locked",
            "holdout_accessed",
            "network_requests",
            "macro_db_writes",
            "production_impact",
        )
    }
    expected_hash = content_hash(identity_payload)
    if reconstruction.get("reconstruction_hash") != expected_hash:
        raise ValueError("S4.2-B.1 reconstruction hash mismatch.")
    if reconstruction.get("reconstruction_id") != (
        f"RATEELIGREC-{expected_hash[:16]}"
    ):
        raise ValueError("S4.2-B.1 reconstruction id mismatch.")

    return {
        "reconstruction_hash": expected_hash,
        "raw_candidate_count": raw_count,
        "family_count": 9,
        "holdout_accessed": False,
        "ready_for_holdout": False,
    }


def render_eligibility_reconstruction_text(
    reconstruction: dict[str, Any],
) -> str:
    validate_eligibility_reconstruction(reconstruction)

    headers = (
        "Feat",
        "Meth",
        "Raw",
        "First computable prior",
        "First signal prior",
        "Support points",
    )
    rows: list[tuple[str, ...]] = []
    for family in reconstruction["families"]:
        computable = family["first_computable_prior_count_distribution"]
        signal = family["first_signal_prior_count_distribution"]
        curve = family["observed_support_counterfactual"]

        def range_text(summary: dict[str, Any]) -> str:
            if summary["count"] <= 0:
                return "N/A"
            if summary["min"] == summary["max"]:
                return str(summary["min"])
            return f"{summary['min']}..{summary['max']}"

        rows.append(
            (
                _FEATURE_LABELS[str(family["feature_id"])],
                _METHOD_LABELS[str(family["method"])],
                str(family["raw_candidate_count"]),
                range_text(computable),
                range_text(signal),
                str(curve["point_count"]),
            )
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

    counts = reconstruction["counts"]
    ordering = reconstruction["ordering_contract"]
    policy = reconstruction["policy_state"]
    eligibility = policy["eligibility_policy"]

    lines = [
        "NEXT-6B-S4.2-B.1 RAW UNIVERSE & ELIGIBILITY AUDIT",
        "",
        (
            "Raw Candidates / Legacy Method Pareto / Legacy Frontier : "
            f"{counts['raw_candidate_count']} / "
            f"{counts['method_local_pareto_count']} / "
            f"{counts['legacy_frontier_count']}"
        ),
        (
            "Raw Replay / Legacy Lineage / Eligibility Audit : "
            f"{reconstruction['raw_replay']['raw_replay_status']} / "
            "COMPLETE / COMPLETE"
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
                "Reference Support Policy / Minimum Prior Observations : "
                f"{eligibility['status']} / "
                f"{eligibility['minimum_prior_observations']}"
            ),
            (
                "Candidate Universe / Admissibility Applied / "
                "Post-Admissibility Compression : "
                f"{ordering['candidate_universe_scope']} / "
                f"{ordering['admissibility_applied']} / "
                f"{ordering['post_admissibility_compression']}"
            ),
            (
                "Episode Policy / Event semantics / Left boundary : "
                f"{reconstruction['episode_semantics']['policy_version']} / "
                f"{reconstruction['episode_semantics']['event_count_semantics']} / "
                f"{reconstruction['episode_semantics']['left_boundary_episode_state_rule']}"
            ),
            (
                "Eligibility / Admissibility / Final candidate selected : "
                f"{policy['eligibility_policy_defined']} / "
                f"{policy['admissibility_policy_defined']} / "
                f"{policy['final_candidate_selected']}"
            ),
            (
                "Holdout locked / accessed / ready : "
                f"{reconstruction['holdout_locked']} / "
                f"{reconstruction['holdout_accessed']} / "
                f"{policy['ready_for_holdout']}"
            ),
            (
                "RATE_SPIKE / Network / Macro DB writes / Production : "
                f"{policy['rate_spike_state']} / "
                f"{reconstruction['network_requests']} / "
                f"{reconstruction['macro_db_writes']} / "
                f"{reconstruction['production_impact']}"
            ),
            "",
            "Reconstruction status: COMPLETE (no support or admissibility policy selected)",
        ]
    )
    return "\n".join(lines)
