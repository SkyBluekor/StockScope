from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app.macro.identity import canonical_json, content_hash
from app.macro.r5r_evaluator import (
    FEATURE_BY_HORIZON,
    HORIZONS,
    R5R_CANDIDATE_DOMAIN_SHA256,
    R5R_CHRONOLOGY_HASH_CONTRACT,
    R5R_METHOD_CONTRACT_SHA256,
    R5R_METHOD_DESIGN_SHA256,
    R5R_NUMERIC_CONTRACT,
    R5R_POLICY_SHA256,
    R5R_WINDOW_PROFILE_SHA256,
    effective_candidate_mapping,
    window_length,
)


R5R_BINDING_CONTRACT_VERSION = "NEXT6E_R5R_EVALUATION_BINDING_V1"

EXPECTED_DEV_DATASET_ID = "MACROCAL-DEV-7c3f6660b3aae03f"
EXPECTED_DEV_DATASET_HASH = (
    "7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1"
)
EXPECTED_DEV_SOURCE_FILE_SHA256 = (
    "7b1dfe33537bb8855b9441b2aeb24338a13950abf8cdc186b2821898d47313f4"
)
EXPECTED_DATASET_CONTRACT_VERSION = "VN_NEXT6B_S2_CALIBRATION_DATASET_V1"
EXPECTED_FEATURE_CONTRACT_VERSION = "VN_NEXT6B_S1_MACRO_FEATURE_V1"
EXPECTED_SPLIT_ROLE = "DEVELOPMENT"
EXPECTED_USAGE_SCOPE = "REFERENCE_RESEARCH_ONLY"
EXPECTED_PROVIDER = "FRED"
EXPECTED_PROVIDER_SERIES_ID = "DGS10"
EXPECTED_SERIES_ID = "US_10Y_CONSTANT_MATURITY_YIELD"


class R5RBindingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_chronology_hash(dates: list[str]) -> str:
    payload = {
        "schema_id": R5R_CHRONOLOGY_HASH_CONTRACT,
        "horizon_set": list(HORIZONS),
        "n": len(dates),
        "rows": [
            {"i": index, "observation_date": date}
            for index, date in enumerate(dates, start=1)
        ],
    }
    return hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()


def _required_feature_map(row: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    features = row.get("features")
    if not isinstance(features, list):
        raise R5RBindingError(
            "MISSING_REQUIRED_HORIZON",
            "Calibration row must contain a features list.",
        )
    result: dict[str, Mapping[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        feature_id = str(feature.get("feature_id") or "")
        if feature_id in FEATURE_BY_HORIZON.values():
            result[feature_id] = feature
    return result


def _integer_bp(value: Any, feature_id: str) -> int:
    if isinstance(value, bool):
        raise R5RBindingError(
            "INVALID_FEATURE_LATTICE",
            f"{feature_id} must be an exact integer basis-point value.",
        )
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise R5RBindingError(
            "INVALID_FEATURE_LATTICE",
            f"{feature_id} must be numeric.",
        ) from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise R5RBindingError(
            "INVALID_FEATURE_LATTICE",
            f"{feature_id} must be an exact integer basis-point value.",
        )
    return int(number)


def _verify_dataset_hash(dataset: Mapping[str, Any]) -> None:
    manifest = dataset.get("manifest")
    rows = dataset.get("rows")
    if not isinstance(manifest, Mapping) or not isinstance(rows, list):
        raise R5RBindingError(
            "INVALID_DATA_IDENTITY",
            "Calibration dataset is missing manifest/rows.",
        )
    row_hashes = [str(row.get("row_hash") or "") for row in rows]
    recomputed = content_hash(
        {
            "manifest": dict(manifest),
            "row_hashes": row_hashes,
        }
    )
    if recomputed != str(dataset.get("dataset_hash") or ""):
        raise R5RBindingError(
            "INVALID_DATA_IDENTITY",
            "Calibration dataset_hash does not match its manifest/row hashes.",
        )


def _verify_expected_identity(
    dataset: Mapping[str, Any],
    *,
    source_file_sha256: str,
    expected_identity: Mapping[str, str] | None,
) -> None:
    expected = dict(
        expected_identity
        or {
            "dataset_id": EXPECTED_DEV_DATASET_ID,
            "dataset_hash": EXPECTED_DEV_DATASET_HASH,
            "source_file_sha256": EXPECTED_DEV_SOURCE_FILE_SHA256,
            "contract_version": EXPECTED_DATASET_CONTRACT_VERSION,
            "feature_contract_version": EXPECTED_FEATURE_CONTRACT_VERSION,
            "split_role": EXPECTED_SPLIT_ROLE,
            "usage_scope": EXPECTED_USAGE_SCOPE,
            "provider": EXPECTED_PROVIDER,
            "provider_series_id": EXPECTED_PROVIDER_SERIES_ID,
            "series_id": EXPECTED_SERIES_ID,
        }
    )
    manifest = dataset.get("manifest")
    if not isinstance(manifest, Mapping):
        raise R5RBindingError(
            "INVALID_DATA_IDENTITY",
            "Calibration dataset manifest is missing.",
        )

    actual = {
        "dataset_id": str(dataset.get("dataset_id") or ""),
        "dataset_hash": str(dataset.get("dataset_hash") or ""),
        "source_file_sha256": source_file_sha256,
        "contract_version": str(dataset.get("contract_version") or ""),
        "feature_contract_version": str(
            manifest.get("feature_contract_version") or ""
        ),
        "split_role": str(dataset.get("split_role") or ""),
        "usage_scope": str(manifest.get("usage_scope") or ""),
        "provider": str(manifest.get("provider") or ""),
        "provider_series_id": str(manifest.get("provider_series_id") or ""),
        "series_id": str(manifest.get("series_id") or ""),
    }
    for field, required in expected.items():
        if actual.get(field) != required:
            raise R5RBindingError(
                "INVALID_DATA_IDENTITY",
                f"{field} does not match the expected frozen DEV identity.",
            )


def bind_r5r_evaluation_dataset(
    dataset: Mapping[str, Any],
    *,
    source_file_sha256: str,
    expected_identity: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    _verify_dataset_hash(dataset)
    _verify_expected_identity(
        dataset,
        source_file_sha256=source_file_sha256,
        expected_identity=expected_identity,
    )

    source_rows = dataset.get("rows")
    if not isinstance(source_rows, list):
        raise R5RBindingError(
            "INVALID_DATA_IDENTITY",
            "Calibration dataset rows must be a list.",
        )

    excluded_reason_counts: dict[str, int] = {}
    eligible: list[dict[str, Any]] = []

    for row in source_rows:
        if not isinstance(row, Mapping):
            raise R5RBindingError(
                "INVALID_DATA_IDENTITY",
                "Calibration dataset row must be an object.",
            )
        feature_map = _required_feature_map(row)
        if any(
            feature_id not in feature_map
            or str(feature_map[feature_id].get("status") or "") != "AVAILABLE"
            or feature_map[feature_id].get("value") is None
            for feature_id in FEATURE_BY_HORIZON.values()
        ):
            excluded_reason_counts["REQUIRED_HORIZON_UNAVAILABLE"] = (
                excluded_reason_counts.get("REQUIRED_HORIZON_UNAVAILABLE", 0)
                + 1
            )
            continue

        features = {
            feature_id: _integer_bp(feature_map[feature_id]["value"], feature_id)
            for feature_id in FEATURE_BY_HORIZON.values()
        }
        date = str(row.get("observation_date") or "")
        if len(date) != 10 or date[4:5] != "-" or date[7:8] != "-":
            raise R5RBindingError(
                "INVALID_CHRONOLOGY",
                "Observation date must use YYYY-MM-DD.",
            )
        eligible.append(
            {
                "observation_date": date,
                "features": features,
                "source_row_hash": str(row.get("row_hash") or ""),
            }
        )

    eligible.sort(key=lambda item: item["observation_date"])
    dates = [row["observation_date"] for row in eligible]
    if len(dates) != len(set(dates)):
        raise R5RBindingError(
            "INVALID_CHRONOLOGY",
            "Joint chronology contains duplicate observation dates.",
        )
    if dates != sorted(dates):
        raise R5RBindingError(
            "INVALID_CHRONOLOGY",
            "Joint chronology must be strictly ascending.",
        )

    n = len(eligible)
    width = window_length(n)
    candidate_mapping = effective_candidate_mapping(n)
    if not candidate_mapping:
        raise R5RBindingError(
            "NO_ELIGIBLE_GRID_ANCHOR",
            "No structural R5R candidate is eligible after binding.",
        )

    joint_rows = [
        {
            "i": index,
            "observation_date": row["observation_date"],
            "features": row["features"],
            "source_row_hash": row["source_row_hash"],
        }
        for index, row in enumerate(eligible, start=1)
    ]

    manifest = dataset["manifest"]
    limitations = sorted(
        set(str(value) for value in list(manifest.get("limitations") or []))
    )
    chronology_hash = canonical_chronology_hash(dates)

    artifact_payload = {
        "binding_version": R5R_BINDING_CONTRACT_VERSION,
        "dataset_id": str(dataset["dataset_id"]),
        "dataset_hash": str(dataset["dataset_hash"]),
        "source_file_sha256": source_file_sha256,
        "provider": str(manifest["provider"]),
        "provider_series_id": str(manifest["provider_series_id"]),
        "series_id": str(manifest["series_id"]),
        "vintage_id": str(manifest["vintage_id"]),
        "feature_contract_version": str(manifest["feature_contract_version"]),
        "split_role": str(dataset["split_role"]),
        "usage_scope": str(manifest["usage_scope"]),
        "source_row_count": len(source_rows),
        "joint_row_count": n,
        "excluded_before_binding_count": len(source_rows) - n,
        "joint_eligibility_rule": (
            "ALL_REQUIRED_HORIZONS_AVAILABLE_AND_EXACT_INTEGER_BP_BEFORE_BINDING"
        ),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items())),
        "first_observation_date": dates[0],
        "last_observation_date": dates[-1],
        "joint_chronology_hash": chronology_hash,
        "chronology_hash_contract_id": R5R_CHRONOLOGY_HASH_CONTRACT,
        "numeric_contract_id": R5R_NUMERIC_CONTRACT,
        "window_length": width,
        "effective_candidate_mapping": candidate_mapping,
        "limitations": limitations,
        "method_contract_sha256": R5R_METHOD_CONTRACT_SHA256,
        "method_design_sha256": R5R_METHOD_DESIGN_SHA256,
        "candidate_domain_sha256": R5R_CANDIDATE_DOMAIN_SHA256,
        "window_profile_sha256": R5R_WINDOW_PROFILE_SHA256,
        "policy_contract_sha256": R5R_POLICY_SHA256,
        "metrics_computed": False,
        "reference_adequacy_evaluated": False,
        "holdout_accessed": False,
        "runtime_db_accessed": False,
        "network_accessed": False,
    }
    binding_hash = content_hash(artifact_payload)
    artifact = {
        **artifact_payload,
        "binding_id": f"R5RBIND-{binding_hash[:16]}",
        "binding_hash": binding_hash,
    }

    bound_payload = {
        **artifact,
        "joint_rows": joint_rows,
    }
    return {
        "artifact": artifact,
        "bound_payload": bound_payload,
    }
