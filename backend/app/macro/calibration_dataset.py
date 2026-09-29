from __future__ import annotations

from enum import Enum
from typing import Any

from app.macro.features import (
    DGS10_FEATURE_WINDOWS,
    MACRO_FEATURE_CONTRACT_VERSION,
    build_dgs10_features,
)
from app.macro.identity import content_hash


MACRO_CALIBRATION_DATASET_CONTRACT_VERSION = (
    "VN_NEXT6B_S2_CALIBRATION_DATASET_V1"
)


class CalibrationSplitRole(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    HOLDOUT = "HOLDOUT"


def _split_role(value: CalibrationSplitRole | str) -> CalibrationSplitRole:
    return (
        value
        if isinstance(value, CalibrationSplitRole)
        else CalibrationSplitRole(str(value).strip().upper())
    )


def _feature_status_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_feature: dict[str, dict[str, int]] = {}
    for row in rows:
        for feature in row["features"]:
            feature_id = str(feature["feature_id"])
            status = str(feature["status"])
            bucket = by_feature.setdefault(feature_id, {})
            bucket[status] = bucket.get(status, 0) + 1
    return {
        feature_id: dict(sorted(counts.items()))
        for feature_id, counts in sorted(by_feature.items())
    }


def build_calibration_dataset(
    *,
    archive: dict[str, Any],
    split_role: CalibrationSplitRole | str,
) -> dict[str, Any]:
    role = _split_role(split_role)
    if archive.get("usage_scope") != "REFERENCE_RESEARCH_ONLY":
        raise ValueError("Calibration dataset requires REFERENCE_RESEARCH_ONLY archive.")

    warmup = list(archive.get("warmup_observations") or [])
    analysis = list(archive.get("analysis_observations") or [])
    max_window = max(DGS10_FEATURE_WINDOWS)

    if archive.get("status") == "NOT_PREPARED" or not analysis:
        payload = {
            "contract_version": MACRO_CALIBRATION_DATASET_CONTRACT_VERSION,
            "split_role": role.value,
            "status": "NOT_PREPARED",
            "reason": archive.get("reason") or "ARCHIVE_NOT_PREPARED",
            "series_id": archive.get("series_id"),
            "vintage_id": archive.get("vintage_id"),
            "observation_start": archive.get("observation_start"),
            "observation_end": archive.get("observation_end"),
            "usage_scope": "REFERENCE_RESEARCH_ONLY",
            "historical_evaluation_eligible": False,
            "rows": [],
            "production_decision_approved": False,
        }
        dataset_hash = content_hash(payload)
        return {
            **payload,
            "dataset_id": f"MACROCAL-{role.value[:3]}-{dataset_hash[:16]}",
            "dataset_hash": dataset_hash,
        }

    combined = [*warmup, *analysis]
    first_analysis_index = len(warmup)
    dataset_rows: list[dict[str, Any]] = []

    for offset, observation in enumerate(analysis):
        combined_index = first_analysis_index + offset
        start_index = max(0, combined_index - max_window)
        feature_window = list(reversed(combined[start_index : combined_index + 1]))
        feature_set = build_dgs10_features(feature_window)
        window_pit_eligible = bool(feature_window) and all(
            str(item.get("time_quality")) in {"EXACT", "PROVIDER_TIME"}
            for item in feature_window
        )
        row_identity = {
            "split_role": role.value,
            "series_id": archive["series_id"],
            "vintage_id": archive["vintage_id"],
            "observation_key": observation["observation_key"],
            "observation_date": observation["observation_date"],
            "normalized_hash": observation["normalized_hash"],
            "feature_contract_version": feature_set["contract_version"],
            "feature_set_hash": feature_set["feature_set_hash"],
        }
        dataset_rows.append(
            {
                **row_identity,
                "revision_no": observation["revision_no"],
                "time_quality": observation["time_quality"],
                "historical_pit_eligible": window_pit_eligible,
                "features": feature_set["features"],
                "row_hash": content_hash(row_identity),
            }
        )

    feature_summary = _feature_status_summary(dataset_rows)
    unavailable_feature_count = sum(
        count
        for counts in feature_summary.values()
        for status, count in counts.items()
        if status != "AVAILABLE"
    )
    pit_eligible_count = sum(
        bool(row["historical_pit_eligible"]) for row in dataset_rows
    )
    time_quality_counts: dict[str, int] = {}
    for row in dataset_rows:
        quality = str(row["time_quality"])
        time_quality_counts[quality] = time_quality_counts.get(quality, 0) + 1

    status = (
        "READY_REFERENCE_RESEARCH"
        if unavailable_feature_count == 0
        and len(warmup) >= max_window
        else "PARTIAL_REFERENCE_RESEARCH"
    )
    limitations: list[str] = []
    if pit_eligible_count < len(dataset_rows):
        limitations.append("HISTORICAL_TIME_NOT_PROVEN")
    if len(warmup) < max_window:
        limitations.append("WARMUP_INSUFFICIENT")
    if unavailable_feature_count:
        limitations.append("FEATURE_ROWS_INCOMPLETE")

    manifest = {
        "contract_version": MACRO_CALIBRATION_DATASET_CONTRACT_VERSION,
        "series_id": archive["series_id"],
        "provider": "FRED",
        "provider_series_id": "DGS10",
        "split_role": role.value,
        "observation_start": archive["observation_start"],
        "observation_end": archive["observation_end"],
        "vintage_id": archive["vintage_id"],
        "source_archive_hash": archive["archive_hash"],
        "source_revision_policy": archive["revision_policy"],
        "feature_contract_version": MACRO_FEATURE_CONTRACT_VERSION,
        "warmup_rule": "MAX_FEATURE_OBSERVATION_DISTANCE",
        "warmup_required": max_window,
        "warmup_count": len(warmup),
        "analysis_row_count": len(dataset_rows),
        "feature_status_counts": feature_summary,
        "time_quality_counts": dict(sorted(time_quality_counts.items())),
        "historical_pit_eligible_count": pit_eligible_count,
        "usage_scope": "REFERENCE_RESEARCH_ONLY",
        "limitations": sorted(set(limitations)),
        "production_decision_approved": False,
    }
    identity_payload = {
        "manifest": manifest,
        "row_hashes": [row["row_hash"] for row in dataset_rows],
    }
    dataset_hash = content_hash(identity_payload)
    return {
        "contract_version": MACRO_CALIBRATION_DATASET_CONTRACT_VERSION,
        "dataset_id": f"MACROCAL-{role.value[:3]}-{dataset_hash[:16]}",
        "dataset_hash": dataset_hash,
        "status": status,
        "reason": None,
        "split_role": role.value,
        "manifest": manifest,
        "rows": dataset_rows,
        "historical_evaluation_eligible": False,
        "production_decision_approved": False,
    }
