from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from typing import Any

from app.macro.calibration_research import (
    validate_development_artifact,
    validate_distribution_research_artifact,
    validate_research_protocol,
)
from app.macro.candidate_selection import (
    MACRO_CANDIDATE_DOMINANCE_CONTRACT_VERSION,
    pareto_prune_candidates,
)
from app.macro.identity import content_hash
from app.macro.shock_episode import (
    RATE_SPIKE_EPISODE_POLICY_VERSION,
    build_consecutive_true_episodes,
)


MACRO_RATE_SPIKE_CANDIDATE_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_RATE_SPIKE_CANDIDATE_V1"
)
MACRO_CANDIDATE_SET_CONTRACT_VERSION = "VN_NEXT6B_S4_CANDIDATE_SET_V1"
MACRO_CANDIDATE_GENERATION_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_DATA_DERIVED_CANDIDATE_GENERATION_V1"
)

RATE_SPIKE_FEATURE_IDS = (
    "delta_bp_1obs",
    "delta_bp_5obs",
    "delta_bp_10obs",
)
RATE_SPIKE_METHODS = (
    "EMPIRICAL_POSITIVE_TAIL",
    "EXPANDING_POSITIVE_TAIL_FRACTION",
    "EXPANDING_ROBUST_MAD",
)


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Candidate metric must be finite.")
    return result


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _fraction(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        raise ValueError("fraction denominator must be positive.")
    return _decimal_text(Decimal(numerator) / Decimal(denominator))


def _threshold_values(
    rows: list[dict[str, Any]],
    method: str,
) -> list[Decimal]:
    values: set[Decimal] = set()
    for row in rows:
        raw_value = _decimal(row["value"])
        if raw_value <= 0:
            continue
        if method == "EMPIRICAL_POSITIVE_TAIL":
            values.add(raw_value)
        elif method == "EXPANDING_POSITIVE_TAIL_FRACTION":
            metric = row.get("positive_tail_fraction_ge")
            if metric is not None:
                values.add(_decimal(metric))
        elif method == "EXPANDING_ROBUST_MAD":
            metric = row.get("robust_deviation_mad")
            if metric is not None:
                score = _decimal(metric)
                if score > 0:
                    values.add(score)
        else:
            raise ValueError(f"Unsupported RATE_SPIKE method: {method}")
    return sorted(values)


def _threshold_definition(method: str) -> tuple[str, str, str]:
    if method == "EMPIRICAL_POSITIVE_TAIL":
        return (
            "RAW_BP_GE_OBSERVED_DEVELOPMENT_VALUE",
            "BASIS_POINT",
            "FEATURE_AVAILABLE",
        )
    if method == "EXPANDING_POSITIVE_TAIL_FRACTION":
        return (
            "PRIOR_POSITIVE_TAIL_FRACTION_LE_OBSERVED_VALUE",
            "FRACTION",
            "PRIOR_OBSERVATION_EXISTS",
        )
    if method == "EXPANDING_ROBUST_MAD":
        return (
            "PRIOR_MAD_DEVIATION_GE_OBSERVED_VALUE",
            "MAD_MULTIPLE",
            "PRIOR_MAD_NON_ZERO",
        )
    raise ValueError(f"Unsupported RATE_SPIKE method: {method}")


def _signal_for_row(
    row: dict[str, Any],
    *,
    method: str,
    threshold: Decimal,
) -> tuple[bool, bool]:
    raw_value = _decimal(row["value"])

    if method == "EMPIRICAL_POSITIVE_TAIL":
        return True, raw_value > 0 and raw_value >= threshold

    if method == "EXPANDING_POSITIVE_TAIL_FRACTION":
        metric = row.get("positive_tail_fraction_ge")
        if metric is None:
            return False, False
        return True, raw_value > 0 and _decimal(metric) <= threshold

    if method == "EXPANDING_ROBUST_MAD":
        metric = row.get("robust_deviation_mad")
        if metric is None:
            return False, False
        return True, raw_value > 0 and _decimal(metric) >= threshold

    raise ValueError(f"Unsupported RATE_SPIKE method: {method}")


def _minimum_prior_support(
    *,
    eligible_count: int,
    signal_count: int,
) -> int:
    if eligible_count <= 0 or signal_count <= 0:
        raise ValueError("Candidate support requires positive counts.")
    ratio = Decimal(eligible_count) / Decimal(signal_count)
    return int(ratio.to_integral_value(rounding=ROUND_CEILING))


def _candidate_from_threshold(
    *,
    feature_id: str,
    feature_result: dict[str, Any],
    method: str,
    threshold: Decimal,
    development_dataset_hash: str,
    protocol_hash: str,
    research_hash: str,
) -> dict[str, Any]:
    expanding_rows = list(feature_result["expanding"]["rows"])
    signal_rows: list[dict[str, Any]] = []
    eligible_count = 0
    signal_count = 0
    yearly_signal_counts: dict[str, int] = {}
    all_years = sorted(
        {str(row["observation_date"])[:4] for row in expanding_rows}
    )

    for row in expanding_rows:
        eligible, signal = _signal_for_row(
            row,
            method=method,
            threshold=threshold,
        )
        if eligible:
            eligible_count += 1
        if signal:
            signal_count += 1
            year = str(row["observation_date"])[:4]
            yearly_signal_counts[year] = yearly_signal_counts.get(year, 0) + 1
        signal_rows.append(
            {
                "observation_date": row["observation_date"],
                "row_hash": row["row_hash"],
                "eligible": eligible,
                "signal": signal,
            }
        )

    if signal_count <= 0:
        raise ValueError("Observed candidate threshold must produce a signal.")

    year_counts = {
        year: yearly_signal_counts.get(year, 0)
        for year in all_years
    }
    year_coverage_count = sum(count > 0 for count in year_counts.values())
    year_coverage_fraction = _fraction(
        year_coverage_count,
        len(all_years),
    )
    max_year_count = max(year_counts.values()) if year_counts else 0
    max_year_signal_share = _fraction(max_year_count, signal_count)

    episode_summary = build_consecutive_true_episodes(signal_rows)
    episode_count = int(episode_summary["episode_count"])
    episode_separation_ratio = _fraction(episode_count, signal_count)

    definition, threshold_unit, required_condition = _threshold_definition(method)
    support_fraction = _fraction(signal_count, eligible_count)
    derived_minimum_support = _minimum_prior_support(
        eligible_count=eligible_count,
        signal_count=signal_count,
    )

    payload = {
        "contract_version": MACRO_RATE_SPIKE_CANDIDATE_CONTRACT_VERSION,
        "shock_type": "RATE_SPIKE",
        "feature_id": feature_id,
        "method": method,
        "direction": "UP",
        "threshold_definition": definition,
        "threshold_value": _decimal_text(threshold),
        "threshold_unit": threshold_unit,
        "threshold_source": "OBSERVED_DEVELOPMENT_VALUE",
        "required_condition": required_condition,
        "lookback_mode": (
            "FULL_DEVELOPMENT_REFERENCE"
            if method == "EMPIRICAL_POSITIVE_TAIL"
            else "EXPANDING_STRICTLY_PRIOR"
        ),
        "selected_rolling_lookback": None,
        "eligible_row_count": eligible_count,
        "development_signal_count": signal_count,
        "development_signal_fraction": support_fraction,
        "derived_minimum_prior_support": derived_minimum_support,
        "minimum_prior_support_derivation": (
            "CEIL(ELIGIBLE_ROW_COUNT/DEVELOPMENT_SIGNAL_COUNT)"
        ),
        "year_signal_counts": year_counts,
        "year_coverage_count": year_coverage_count,
        "year_coverage_fraction": year_coverage_fraction,
        "max_year_signal_share": max_year_signal_share,
        "episode_policy_version": RATE_SPIKE_EPISODE_POLICY_VERSION,
        "episode_summary": episode_summary,
        "episode_separation_ratio": episode_separation_ratio,
        "development_dataset_hash": development_dataset_hash,
        "protocol_hash": protocol_hash,
        "research_hash": research_hash,
        "holdout_accessed": False,
        "production_decision_approved": False,
    }
    candidate_hash = content_hash(payload)
    return {
        **payload,
        "candidate_id": f"RATECAND-{candidate_hash[:16]}",
        "candidate_hash": candidate_hash,
    }


def generate_raw_feature_candidates(
    *,
    feature_id: str,
    feature_result: dict[str, Any],
    development_dataset_hash: str,
    protocol_hash: str,
    research_hash: str,
) -> dict[str, list[dict[str, Any]]]:
    if feature_id not in RATE_SPIKE_FEATURE_IDS:
        raise ValueError(f"Unsupported RATE_SPIKE feature: {feature_id}")

    generated_by_method: dict[str, list[dict[str, Any]]] = {}
    rows = list(feature_result["expanding"]["rows"])
    for method in RATE_SPIKE_METHODS:
        thresholds = _threshold_values(rows, method)
        generated_by_method[method] = [
            _candidate_from_threshold(
                feature_id=feature_id,
                feature_result=feature_result,
                method=method,
                threshold=threshold,
                development_dataset_hash=development_dataset_hash,
                protocol_hash=protocol_hash,
                research_hash=research_hash,
            )
            for threshold in thresholds
        ]
    return generated_by_method


def evaluate_candidate_behavior(
    *,
    feature_result: dict[str, Any],
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    method = str(candidate["method"])
    threshold = _decimal(candidate["threshold_value"])
    behavior_rows: list[dict[str, Any]] = []

    for row in feature_result["expanding"]["rows"]:
        eligible, signal = _signal_for_row(
            row,
            method=method,
            threshold=threshold,
        )
        raw_value = _decimal(row["value"])
        behavior_rows.append(
            {
                "observation_date": str(row["observation_date"]),
                "row_hash": str(row["row_hash"]),
                "eligible": eligible,
                "signal": signal,
                "positive_move": bool(eligible and raw_value > 0),
            }
        )
    return behavior_rows


def generate_feature_candidates(
    *,
    feature_id: str,
    feature_result: dict[str, Any],
    development_dataset_hash: str,
    protocol_hash: str,
    research_hash: str,
) -> dict[str, Any]:
    if feature_id not in RATE_SPIKE_FEATURE_IDS:
        raise ValueError(f"Unsupported RATE_SPIKE feature: {feature_id}")

    methods: dict[str, Any] = {}
    all_frozen: list[dict[str, Any]] = []
    all_dominated: list[dict[str, Any]] = []

    generated_by_method = generate_raw_feature_candidates(
        feature_id=feature_id,
        feature_result=feature_result,
        development_dataset_hash=development_dataset_hash,
        protocol_hash=protocol_hash,
        research_hash=research_hash,
    )

    for method in RATE_SPIKE_METHODS:
        generated = generated_by_method[method]
        frozen, dominated = pareto_prune_candidates(generated)
        generated_hashes = sorted(
            str(candidate["candidate_hash"]) for candidate in generated
        )
        dominated_hashes = sorted(
            str(candidate["candidate_hash"]) for candidate in dominated
        )
        frozen_hashes = sorted(
            str(candidate["candidate_hash"]) for candidate in frozen
        )
        methods[method] = {
            "generation_rule": "ALL_UNIQUE_OBSERVED_POSITIVE_BREAKPOINTS",
            "generated_count": len(generated),
            "dominated_count": len(dominated),
            "frozen_count": len(frozen),
            "generated_candidate_hashes": generated_hashes,
            "dominated_candidate_hashes": dominated_hashes,
            "frozen_candidate_hashes": frozen_hashes,
        }
        all_frozen.extend(frozen)
        all_dominated.extend(dominated)

    return {
        "feature_id": feature_id,
        "methods": methods,
        "frozen_candidates": sorted(
            all_frozen,
            key=lambda item: (
                item["method"],
                _decimal(item["threshold_value"]),
                item["candidate_hash"],
            ),
        ),
        "dominated_candidates": sorted(
            all_dominated,
            key=lambda item: (
                item["method"],
                _decimal(item["threshold_value"]),
                item["candidate_hash"],
            ),
        ),
    }


def build_rate_spike_candidate_set(
    *,
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
    research: dict[str, Any],
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
    if protocol.get("holdout_locked") is not True:
        raise ValueError("Holdout must remain locked during S4.")

    feature_results = research["feature_results"]
    per_feature: dict[str, Any] = {}
    frozen_candidates: list[dict[str, Any]] = []
    dominated_candidates: list[dict[str, Any]] = []
    generated_hashes: list[str] = []

    for feature_id in RATE_SPIKE_FEATURE_IDS:
        generated = generate_feature_candidates(
            feature_id=feature_id,
            feature_result=feature_results[feature_id],
            development_dataset_hash=development_state["dataset_hash"],
            protocol_hash=protocol_state["protocol_hash"],
            research_hash=research_state["research_hash"],
        )
        per_feature[feature_id] = {
            "methods": generated["methods"],
            "frozen_count": len(generated["frozen_candidates"]),
            "dominated_count": len(generated["dominated_candidates"]),
        }
        frozen_candidates.extend(generated["frozen_candidates"])
        dominated_candidates.extend(generated["dominated_candidates"])
        for method_state in generated["methods"].values():
            generated_hashes.extend(method_state["generated_candidate_hashes"])

    frozen_candidates.sort(
        key=lambda item: (
            item["feature_id"],
            item["method"],
            _decimal(item["threshold_value"]),
            item["candidate_hash"],
        )
    )
    dominated_candidates.sort(
        key=lambda item: (
            item["feature_id"],
            item["method"],
            _decimal(item["threshold_value"]),
            item["candidate_hash"],
        )
    )

    total_generated = len(generated_hashes)
    total_frozen = len(frozen_candidates)
    total_dominated = len(dominated_candidates)
    if total_generated != total_frozen + total_dominated:
        raise ValueError("Candidate accounting mismatch.")

    exploration_manifest = {
        "generation_contract_version": (
            MACRO_CANDIDATE_GENERATION_CONTRACT_VERSION
        ),
        "dominance_contract_version": (
            MACRO_CANDIDATE_DOMINANCE_CONTRACT_VERSION
        ),
        "episode_policy_version": RATE_SPIKE_EPISODE_POLICY_VERSION,
        "features_considered": list(RATE_SPIKE_FEATURE_IDS),
        "methods_considered": list(RATE_SPIKE_METHODS),
        "generated_candidate_count": total_generated,
        "dominated_candidate_count": total_dominated,
        "frozen_candidate_count": total_frozen,
        "generated_candidate_hashes": sorted(generated_hashes),
        "frozen_candidate_hashes": sorted(
            str(item["candidate_hash"]) for item in frozen_candidates
        ),
        "dominated_candidate_hashes": sorted(
            str(item["candidate_hash"]) for item in dominated_candidates
        ),
        "frozen_candidate_payload_hash": content_hash(frozen_candidates),
        "dominated_candidate_summary_hash": content_hash(
            dominated_candidates
        ),
    }

    identity_payload = {
        "contract_version": MACRO_CANDIDATE_SET_CONTRACT_VERSION,
        "development_dataset_hash": development_state["dataset_hash"],
        "protocol_hash": protocol_state["protocol_hash"],
        "research_hash": research_state["research_hash"],
        "holdout_dataset_hash_reference": protocol_state[
            "holdout_dataset_hash"
        ],
        "exploration_manifest": exploration_manifest,
        "candidate_set_status": "FROZEN",
        "holdout_locked": True,
        "holdout_accessed": False,
        "final_candidate_selected": False,
        "rate_spike_state": "UNCALIBRATED",
        "production_decision_approved": False,
    }
    candidate_set_hash = content_hash(identity_payload)
    return {
        "contract_version": MACRO_CANDIDATE_SET_CONTRACT_VERSION,
        "candidate_set_id": f"RATECANDSET-{candidate_set_hash[:16]}",
        "candidate_set_hash": candidate_set_hash,
        "candidate_set_status": "FROZEN",
        "development_dataset_hash": development_state["dataset_hash"],
        "protocol_hash": protocol_state["protocol_hash"],
        "research_hash": research_state["research_hash"],
        "holdout_dataset_hash_reference": protocol_state[
            "holdout_dataset_hash"
        ],
        "holdout_locked": True,
        "holdout_accessed": False,
        "exploration_manifest": exploration_manifest,
        "per_feature": per_feature,
        "frozen_candidates": frozen_candidates,
        "dominated_candidates": dominated_candidates,
        "final_candidate_selected": False,
        "selected_candidate_id": None,
        "selected_candidate_hash": None,
        "rate_spike_state": "UNCALIBRATED",
        "normal_labels_created": 0,
        "detected_labels_created": 0,
        "network_requests": 0,
        "macro_db_writes": 0,
        "production_decision_approved": False,
    }


def validate_candidate_set_artifact(
    candidate_set: dict[str, Any],
) -> dict[str, Any]:
    if candidate_set.get("contract_version") != MACRO_CANDIDATE_SET_CONTRACT_VERSION:
        raise ValueError("Unsupported candidate set contract.")
    if candidate_set.get("candidate_set_status") != "FROZEN":
        raise ValueError("Candidate set must be FROZEN.")
    if candidate_set.get("holdout_locked") is not True:
        raise ValueError("Candidate set must keep Holdout locked.")
    if candidate_set.get("holdout_accessed") is not False:
        raise ValueError("Candidate set must not access Holdout.")
    if candidate_set.get("final_candidate_selected") is not False:
        raise ValueError("S4 must not select a final candidate.")
    if candidate_set.get("selected_candidate_id") is not None:
        raise ValueError("S4 selected_candidate_id must be null.")
    if candidate_set.get("selected_candidate_hash") is not None:
        raise ValueError("S4 selected_candidate_hash must be null.")
    if candidate_set.get("rate_spike_state") != "UNCALIBRATED":
        raise ValueError("S4 RATE_SPIKE must remain UNCALIBRATED.")
    if int(candidate_set.get("normal_labels_created") or 0) != 0:
        raise ValueError("S4 must not create NORMAL labels.")
    if int(candidate_set.get("detected_labels_created") or 0) != 0:
        raise ValueError("S4 must not create DETECTED labels.")
    if candidate_set.get("production_decision_approved") is not False:
        raise ValueError("S4 must not be Production-approved.")

    manifest = candidate_set.get("exploration_manifest") or {}
    frozen_candidates = list(candidate_set.get("frozen_candidates") or [])
    dominated_candidates = list(candidate_set.get("dominated_candidates") or [])

    recomputed_frozen_hashes: list[str] = []
    for candidate in frozen_candidates:
        payload = {
            key: value
            for key, value in candidate.items()
            if key not in {"candidate_id", "candidate_hash"}
        }
        expected = content_hash(payload)
        if expected != candidate.get("candidate_hash"):
            raise ValueError("Frozen candidate_hash mismatch.")
        if candidate.get("candidate_id") != f"RATECAND-{expected[:16]}":
            raise ValueError("Frozen candidate_id mismatch.")
        recomputed_frozen_hashes.append(expected)

    frozen_hashes = sorted(recomputed_frozen_hashes)
    dominated_hashes = sorted(
        str(candidate["candidate_hash"])
        for candidate in dominated_candidates
    )
    generated_hashes = sorted(
        [*frozen_hashes, *dominated_hashes]
    )

    if frozen_hashes != sorted(manifest.get("frozen_candidate_hashes") or []):
        raise ValueError("Frozen candidate manifest mismatch.")
    if dominated_hashes != sorted(
        manifest.get("dominated_candidate_hashes") or []
    ):
        raise ValueError("Dominated candidate manifest mismatch.")
    if generated_hashes != sorted(
        manifest.get("generated_candidate_hashes") or []
    ):
        raise ValueError("Generated candidate manifest mismatch.")
    if int(manifest.get("frozen_candidate_count") or 0) != len(frozen_hashes):
        raise ValueError("Frozen candidate count mismatch.")
    if int(manifest.get("dominated_candidate_count") or 0) != len(
        dominated_hashes
    ):
        raise ValueError("Dominated candidate count mismatch.")
    if int(manifest.get("generated_candidate_count") or 0) != len(
        generated_hashes
    ):
        raise ValueError("Generated candidate count mismatch.")
    if manifest.get("frozen_candidate_payload_hash") != content_hash(
        frozen_candidates
    ):
        raise ValueError("Frozen candidate payload hash mismatch.")
    if manifest.get("dominated_candidate_summary_hash") != content_hash(
        dominated_candidates
    ):
        raise ValueError("Dominated candidate summary hash mismatch.")

    identity_payload = {
        "contract_version": candidate_set["contract_version"],
        "development_dataset_hash": candidate_set[
            "development_dataset_hash"
        ],
        "protocol_hash": candidate_set["protocol_hash"],
        "research_hash": candidate_set["research_hash"],
        "holdout_dataset_hash_reference": candidate_set[
            "holdout_dataset_hash_reference"
        ],
        "exploration_manifest": manifest,
        "candidate_set_status": candidate_set["candidate_set_status"],
        "holdout_locked": candidate_set["holdout_locked"],
        "holdout_accessed": candidate_set["holdout_accessed"],
        "final_candidate_selected": candidate_set[
            "final_candidate_selected"
        ],
        "rate_spike_state": candidate_set["rate_spike_state"],
        "production_decision_approved": candidate_set[
            "production_decision_approved"
        ],
    }
    expected_set_hash = content_hash(identity_payload)
    if expected_set_hash != candidate_set.get("candidate_set_hash"):
        raise ValueError("Candidate set hash mismatch.")
    if candidate_set.get("candidate_set_id") != (
        f"RATECANDSET-{expected_set_hash[:16]}"
    ):
        raise ValueError("Candidate set id mismatch.")

    return {
        "candidate_set_hash": expected_set_hash,
        "generated_candidate_count": len(generated_hashes),
        "frozen_candidate_count": len(frozen_hashes),
        "dominated_candidate_count": len(dominated_hashes),
        "holdout_accessed": False,
    }


def summarize_candidate_set(candidate_set: dict[str, Any]) -> dict[str, Any]:
    features: dict[str, Any] = {}
    for feature_id in RATE_SPIKE_FEATURE_IDS:
        feature = candidate_set["per_feature"][feature_id]
        features[feature_id] = {
            "generated_count": sum(
                int(method["generated_count"])
                for method in feature["methods"].values()
            ),
            "dominated_count": feature["dominated_count"],
            "frozen_count": feature["frozen_count"],
            "methods": {
                method: {
                    "generated_count": state["generated_count"],
                    "dominated_count": state["dominated_count"],
                    "frozen_count": state["frozen_count"],
                }
                for method, state in feature["methods"].items()
            },
        }

    manifest = candidate_set["exploration_manifest"]
    frozen = candidate_set["frozen_candidates"]
    rarity = [
        _decimal(candidate["development_signal_fraction"])
        for candidate in frozen
    ]
    episode_counts = [
        int(candidate["episode_summary"]["episode_count"])
        for candidate in frozen
    ]

    return {
        "contract_version": candidate_set["contract_version"],
        "candidate_set_id": candidate_set["candidate_set_id"],
        "candidate_set_hash": candidate_set["candidate_set_hash"],
        "candidate_set_status": candidate_set["candidate_set_status"],
        "development_dataset_hash": candidate_set[
            "development_dataset_hash"
        ],
        "protocol_hash": candidate_set["protocol_hash"],
        "research_hash": candidate_set["research_hash"],
        "holdout_locked": candidate_set["holdout_locked"],
        "holdout_accessed": candidate_set["holdout_accessed"],
        "generation_contract_version": manifest[
            "generation_contract_version"
        ],
        "dominance_contract_version": manifest[
            "dominance_contract_version"
        ],
        "episode_policy_version": manifest["episode_policy_version"],
        "generated_candidate_count": manifest[
            "generated_candidate_count"
        ],
        "dominated_candidate_count": manifest[
            "dominated_candidate_count"
        ],
        "frozen_candidate_count": manifest["frozen_candidate_count"],
        "features": features,
        "frozen_signal_fraction_range": {
            "min": _decimal_text(min(rarity)) if rarity else None,
            "max": _decimal_text(max(rarity)) if rarity else None,
        },
        "frozen_episode_count_range": {
            "min": min(episode_counts) if episode_counts else None,
            "max": max(episode_counts) if episode_counts else None,
        },
        "final_candidate_selected": candidate_set[
            "final_candidate_selected"
        ],
        "rate_spike_state": candidate_set["rate_spike_state"],
        "normal_labels_created": candidate_set["normal_labels_created"],
        "detected_labels_created": candidate_set[
            "detected_labels_created"
        ],
        "network_requests": candidate_set["network_requests"],
        "macro_db_writes": candidate_set["macro_db_writes"],
        "production_decision_approved": candidate_set[
            "production_decision_approved"
        ],
    }
