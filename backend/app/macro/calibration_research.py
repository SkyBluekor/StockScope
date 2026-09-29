from __future__ import annotations

from typing import Any

from app.macro.calibration_dataset import (
    MACRO_CALIBRATION_DATASET_CONTRACT_VERSION,
)
from app.macro.calibration_protocol import (
    MACRO_CALIBRATION_PROTOCOL_CONTRACT_VERSION,
)
from app.macro.distribution import (
    MACRO_DISTRIBUTION_CONTRACT_VERSION,
    RESEARCH_FEATURE_IDS,
    analyze_feature_distribution,
)
from app.macro.features import MACRO_FEATURE_CONTRACT_VERSION
from app.macro.identity import content_hash


MACRO_DISTRIBUTION_RESEARCH_CONTRACT_VERSION = (
    "VN_NEXT6B_S3_DISTRIBUTION_RESEARCH_V1"
)


def _recompute_row_hash(row: dict[str, Any]) -> str:
    identity = {
        "split_role": row["split_role"],
        "series_id": row["series_id"],
        "vintage_id": row["vintage_id"],
        "observation_key": row["observation_key"],
        "observation_date": row["observation_date"],
        "normalized_hash": row["normalized_hash"],
        "feature_contract_version": row["feature_contract_version"],
        "feature_set_hash": row["feature_set_hash"],
    }
    return content_hash(identity)


def _recompute_feature_set_hash(row: dict[str, Any]) -> str:
    payload = {
        "contract_version": row["feature_contract_version"],
        "series_id": row["series_id"],
        "features": row["features"],
    }
    return content_hash(payload)


def validate_development_artifact(dataset: dict[str, Any]) -> dict[str, Any]:
    if dataset.get("contract_version") != MACRO_CALIBRATION_DATASET_CONTRACT_VERSION:
        raise ValueError("Unsupported Development dataset contract.")
    if dataset.get("split_role") != "DEVELOPMENT":
        raise ValueError("S3 accepts DEVELOPMENT dataset only.")
    if dataset.get("status") not in {
        "READY_REFERENCE_RESEARCH",
        "PARTIAL_REFERENCE_RESEARCH",
    }:
        raise ValueError("Development dataset is not research-ready.")
    if dataset.get("production_decision_approved") is not False:
        raise ValueError("Development dataset must not be Production-approved.")

    manifest = dataset.get("manifest") or {}
    if manifest.get("split_role") != "DEVELOPMENT":
        raise ValueError("Development manifest split_role mismatch.")
    if manifest.get("feature_contract_version") != MACRO_FEATURE_CONTRACT_VERSION:
        raise ValueError("Development feature contract mismatch.")
    if manifest.get("usage_scope") != "REFERENCE_RESEARCH_ONLY":
        raise ValueError("Development usage scope must be REFERENCE_RESEARCH_ONLY.")
    if manifest.get("production_decision_approved") is not False:
        raise ValueError("Development manifest must not be Production-approved.")

    rows = list(dataset.get("rows") or [])
    if int(manifest.get("analysis_row_count") or 0) != len(rows):
        raise ValueError("Development row count does not match manifest.")
    if not rows:
        raise ValueError("Development dataset has no rows.")

    dates = [str(row.get("observation_date") or "") for row in rows]
    if dates != sorted(dates):
        raise ValueError("Development rows must be ordered by observation_date.")
    if len(set(dates)) != len(dates):
        raise ValueError("Development observation_date must be unique.")

    row_hashes: list[str] = []
    for row in rows:
        if row.get("split_role") != "DEVELOPMENT":
            raise ValueError("Development row split_role mismatch.")
        if row.get("feature_contract_version") != MACRO_FEATURE_CONTRACT_VERSION:
            raise ValueError("Development row feature contract mismatch.")
        expected_feature_hash = _recompute_feature_set_hash(row)
        if row.get("feature_set_hash") != expected_feature_hash:
            raise ValueError("Development feature_set_hash mismatch.")
        expected_row_hash = _recompute_row_hash(row)
        if row.get("row_hash") != expected_row_hash:
            raise ValueError("Development row_hash mismatch.")
        row_hashes.append(expected_row_hash)

    expected_dataset_hash = content_hash(
        {
            "manifest": manifest,
            "row_hashes": row_hashes,
        }
    )
    if dataset.get("dataset_hash") != expected_dataset_hash:
        raise ValueError("Development dataset_hash mismatch.")

    return {
        "dataset_hash": expected_dataset_hash,
        "row_count": len(rows),
        "observation_start": dates[0],
        "observation_end": dates[-1],
    }


def _base_protocol_hash(protocol: dict[str, Any]) -> str:
    base = protocol.get("base_protocol") or {}
    return content_hash(base)


def validate_research_protocol(
    protocol: dict[str, Any],
    *,
    development_dataset_hash: str,
) -> dict[str, Any]:
    if protocol.get("contract_version") != MACRO_CALIBRATION_PROTOCOL_CONTRACT_VERSION:
        raise ValueError("Unsupported calibration protocol contract.")
    if protocol.get("development_dataset_hash") != development_dataset_hash:
        raise ValueError("Protocol Development dataset hash mismatch.")
    if protocol.get("holdout_locked") is not True:
        raise ValueError("Holdout must remain locked during S3.")
    if protocol.get("threshold_defined") is not False:
        raise ValueError("Threshold must remain undefined during S3.")
    if protocol.get("minimum_sample_defined") is not False:
        raise ValueError("Minimum sample must remain undefined during S3.")
    if protocol.get("episode_policy_defined") is not False:
        raise ValueError("Episode policy must remain undefined during S3.")
    if protocol.get("production_decision_approved") is not False:
        raise ValueError("S3 protocol must not be Production-approved.")

    identity_payload = {
        "contract_version": protocol["contract_version"],
        "base_protocol_hash": _base_protocol_hash(protocol),
        "development_dataset_hash": protocol["development_dataset_hash"],
        "holdout_dataset_hash": protocol["holdout_dataset_hash"],
        "development_vintage": protocol["development_vintage"],
        "holdout_vintage": protocol["holdout_vintage"],
        "holdout_locked": protocol["holdout_locked"],
        "threshold_defined": protocol["threshold_defined"],
        "minimum_sample_defined": protocol["minimum_sample_defined"],
        "episode_policy_defined": protocol["episode_policy_defined"],
        "candidate_method_families": protocol["candidate_method_families"],
        "production_decision_approved": protocol["production_decision_approved"],
    }
    expected_hash = content_hash(identity_payload)
    if protocol.get("protocol_hash") != expected_hash:
        raise ValueError("Calibration protocol_hash mismatch.")
    return {
        "protocol_hash": expected_hash,
        "holdout_dataset_hash": protocol["holdout_dataset_hash"],
        "candidate_method_families": list(protocol["candidate_method_families"]),
    }


def build_distribution_research(
    *,
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    development_state = validate_development_artifact(development_dataset)
    protocol_state = validate_research_protocol(
        protocol,
        development_dataset_hash=development_state["dataset_hash"],
    )
    rows = list(development_dataset["rows"])

    feature_results = {
        feature_id: analyze_feature_distribution(rows, feature_id)
        for feature_id in RESEARCH_FEATURE_IDS
    }
    feature_hashes = {
        feature_id: content_hash(result)
        for feature_id, result in feature_results.items()
    }

    identity_payload = {
        "contract_version": MACRO_DISTRIBUTION_RESEARCH_CONTRACT_VERSION,
        "distribution_contract_version": MACRO_DISTRIBUTION_CONTRACT_VERSION,
        "development_dataset_hash": development_state["dataset_hash"],
        "protocol_hash": protocol_state["protocol_hash"],
        "feature_hashes": feature_hashes,
        "holdout_accessed": False,
        "candidate_selection_status": "NOT_SELECTED",
        "threshold_selected": False,
        "minimum_sample_selected": False,
        "rolling_lookback_selected": False,
        "episode_policy_selected": False,
        "rate_spike_state": "UNCALIBRATED",
        "production_decision_approved": False,
    }
    research_hash = content_hash(identity_payload)
    return {
        "contract_version": MACRO_DISTRIBUTION_RESEARCH_CONTRACT_VERSION,
        "research_id": f"MACRODIST-{research_hash[:16]}",
        "research_hash": research_hash,
        "development_dataset_hash": development_state["dataset_hash"],
        "protocol_hash": protocol_state["protocol_hash"],
        "development_row_count": development_state["row_count"],
        "development_observation_start": development_state["observation_start"],
        "development_observation_end": development_state["observation_end"],
        "holdout_dataset_hash_reference": protocol_state["holdout_dataset_hash"],
        "holdout_accessed": False,
        "methods_studied": [
            "EMPIRICAL_DISTRIBUTION",
            "EMPIRICAL_TAIL_PROFILE",
            "EXPANDING_EMPIRICAL_PERCENTILE",
            "EXPANDING_ROBUST_DEVIATION_MAD",
            "YEARLY_STABILITY_SUMMARY",
        ],
        "candidate_method_families": protocol_state["candidate_method_families"],
        "feature_results": feature_results,
        "candidate_selection_status": "NOT_SELECTED",
        "selected_feature": None,
        "selected_method": None,
        "selected_threshold": None,
        "selected_minimum_sample": None,
        "selected_rolling_lookback": None,
        "episode_policy_selected": False,
        "rate_spike_state": "UNCALIBRATED",
        "normal_labels_created": 0,
        "detected_labels_created": 0,
        "network_requests": 0,
        "macro_db_writes": 0,
        "production_decision_approved": False,
    }


def validate_distribution_research_artifact(
    research: dict[str, Any],
    *,
    development_dataset_hash: str,
    protocol_hash: str,
) -> dict[str, Any]:
    if (
        research.get("contract_version")
        != MACRO_DISTRIBUTION_RESEARCH_CONTRACT_VERSION
    ):
        raise ValueError("Unsupported distribution research contract.")
    if research.get("development_dataset_hash") != development_dataset_hash:
        raise ValueError("Research Development dataset hash mismatch.")
    if research.get("protocol_hash") != protocol_hash:
        raise ValueError("Research protocol hash mismatch.")
    if research.get("holdout_accessed") is not False:
        raise ValueError("S4 requires research with holdout_accessed=false.")
    if research.get("candidate_selection_status") != "NOT_SELECTED":
        raise ValueError("S4 requires unselected S3 research.")
    if research.get("selected_feature") is not None:
        raise ValueError("S3 research must not select a feature.")
    if research.get("selected_method") is not None:
        raise ValueError("S3 research must not select a method.")
    if research.get("selected_threshold") is not None:
        raise ValueError("S3 research must not select a threshold.")
    if research.get("selected_minimum_sample") is not None:
        raise ValueError("S3 research must not select minimum sample.")
    if research.get("selected_rolling_lookback") is not None:
        raise ValueError("S3 research must not select rolling lookback.")
    if research.get("episode_policy_selected") is not False:
        raise ValueError("S3 research must not select an episode policy.")
    if research.get("rate_spike_state") != "UNCALIBRATED":
        raise ValueError("S3 RATE_SPIKE state must remain UNCALIBRATED.")
    if int(research.get("normal_labels_created") or 0) != 0:
        raise ValueError("S3 research must not create NORMAL labels.")
    if int(research.get("detected_labels_created") or 0) != 0:
        raise ValueError("S3 research must not create DETECTED labels.")
    if research.get("production_decision_approved") is not False:
        raise ValueError("S3 research must not be Production-approved.")

    feature_results = research.get("feature_results") or {}
    if set(feature_results) != set(RESEARCH_FEATURE_IDS):
        raise ValueError("Research feature set mismatch.")
    feature_hashes = {
        feature_id: content_hash(feature_results[feature_id])
        for feature_id in RESEARCH_FEATURE_IDS
    }
    distribution_versions = {
        result.get("contract_version") for result in feature_results.values()
    }
    if distribution_versions != {MACRO_DISTRIBUTION_CONTRACT_VERSION}:
        raise ValueError("Research distribution contract mismatch.")

    identity_payload = {
        "contract_version": research["contract_version"],
        "distribution_contract_version": MACRO_DISTRIBUTION_CONTRACT_VERSION,
        "development_dataset_hash": research["development_dataset_hash"],
        "protocol_hash": research["protocol_hash"],
        "feature_hashes": feature_hashes,
        "holdout_accessed": research["holdout_accessed"],
        "candidate_selection_status": research["candidate_selection_status"],
        "threshold_selected": research["selected_threshold"] is not None,
        "minimum_sample_selected": (
            research["selected_minimum_sample"] is not None
        ),
        "rolling_lookback_selected": (
            research["selected_rolling_lookback"] is not None
        ),
        "episode_policy_selected": research["episode_policy_selected"],
        "rate_spike_state": research["rate_spike_state"],
        "production_decision_approved": research[
            "production_decision_approved"
        ],
    }
    expected_hash = content_hash(identity_payload)
    if research.get("research_hash") != expected_hash:
        raise ValueError("Distribution research_hash mismatch.")

    return {
        "research_hash": expected_hash,
        "development_row_count": int(research["development_row_count"]),
        "holdout_dataset_hash_reference": research[
            "holdout_dataset_hash_reference"
        ],
        "methods_studied": list(research["methods_studied"]),
    }


def summarize_distribution_research(research: dict[str, Any]) -> dict[str, Any]:
    features: dict[str, Any] = {}
    for feature_id, result in research["feature_results"].items():
        features[feature_id] = {
            "available_count": result["available_count"],
            "unavailable_count": result["unavailable_count"],
            "summary": result["summary"],
            "empirical_cdf_points": len(result["empirical_cdf"]),
            "positive_tail_points": len(result["tail_profile"]["positive"]),
            "negative_tail_points": len(result["tail_profile"]["negative"]),
            "absolute_tail_points": len(result["tail_profile"]["absolute"]),
            "expanding_percentile_available_count": result["expanding"][
                "percentile_available_count"
            ],
            "expanding_robust_available_count": result["expanding"][
                "robust_deviation_available_count"
            ],
            "years": list(result["yearly_summary"].keys()),
            "selected_threshold": None,
        }
    return {
        "contract_version": research["contract_version"],
        "research_id": research["research_id"],
        "research_hash": research["research_hash"],
        "development_dataset_hash": research["development_dataset_hash"],
        "protocol_hash": research["protocol_hash"],
        "development_row_count": research["development_row_count"],
        "holdout_accessed": research["holdout_accessed"],
        "methods_studied": research["methods_studied"],
        "features": features,
        "candidate_selection_status": research["candidate_selection_status"],
        "threshold_selected": False,
        "minimum_sample_selected": False,
        "rolling_lookback_selected": False,
        "episode_policy_selected": False,
        "rate_spike_state": research["rate_spike_state"],
        "normal_labels_created": research["normal_labels_created"],
        "detected_labels_created": research["detected_labels_created"],
        "network_requests": research["network_requests"],
        "macro_db_writes": research["macro_db_writes"],
        "production_decision_approved": research[
            "production_decision_approved"
        ],
    }
