from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.macro.identity import content_hash
from app.macro.r5r_binding import (
    R5RBindingError,
    bind_r5r_evaluation_dataset,
    canonical_chronology_hash,
)
from app.macro.r5r_evaluator import (
    R5R_CANDIDATE_DOMAIN_SHA256,
    R5R_METHOD_CONTRACT_SHA256,
    R5R_METHOD_DESIGN_SHA256,
    R5R_POLICY_SHA256,
    R5R_WINDOW_PROFILE_SHA256,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "docs" / "fixtures"


def _feature(feature_id: str, value: int | str, status: str = "AVAILABLE") -> dict:
    return {
        "feature_id": feature_id,
        "status": status,
        "value": value if status == "AVAILABLE" else None,
    }


def _dataset(count: int = 12, *, missing_index: int | None = 0) -> dict:
    rows: list[dict] = []
    for index in range(count):
        date = f"2026-01-{index + 1:02d}"
        features = [
            _feature("rate_level_pct", "4.00"),
            _feature("delta_bp_1obs", index),
            _feature("delta_bp_5obs", index * 2),
            _feature("delta_bp_10obs", index * 3),
        ]
        if missing_index == index:
            features[-1] = _feature("delta_bp_10obs", 0, "UNAVAILABLE")
        row_identity = {
            "split_role": "DEVELOPMENT",
            "series_id": "US_10Y_CONSTANT_MATURITY_YIELD",
            "vintage_id": "SYNTHETIC",
            "observation_key": f"K{index}",
            "observation_date": date,
            "normalized_hash": f"{index:064x}",
            "feature_contract_version": "VN_NEXT6B_S1_MACRO_FEATURE_V1",
            "feature_set_hash": f"{index + 100:064x}",
        }
        rows.append(
            {
                **row_identity,
                "revision_no": 1,
                "time_quality": "DATE_ONLY",
                "historical_pit_eligible": False,
                "features": features,
                "row_hash": content_hash(row_identity),
            }
        )

    feature_counts = {
        "delta_bp_1obs": {"AVAILABLE": count},
        "delta_bp_5obs": {"AVAILABLE": count},
        "delta_bp_10obs": (
            {"AVAILABLE": count}
            if missing_index is None
            else {"AVAILABLE": count - 1, "UNAVAILABLE": 1}
        ),
        "rate_level_pct": {"AVAILABLE": count},
    }
    manifest = {
        "contract_version": "VN_NEXT6B_S2_CALIBRATION_DATASET_V1",
        "series_id": "US_10Y_CONSTANT_MATURITY_YIELD",
        "provider": "FRED",
        "provider_series_id": "DGS10",
        "split_role": "DEVELOPMENT",
        "observation_start": rows[0]["observation_date"],
        "observation_end": rows[-1]["observation_date"],
        "vintage_id": "SYNTHETIC",
        "source_archive_hash": "c" * 64,
        "source_revision_policy": "SYNTHETIC",
        "feature_contract_version": "VN_NEXT6B_S1_MACRO_FEATURE_V1",
        "warmup_rule": "MAX_FEATURE_OBSERVATION_DISTANCE",
        "warmup_required": 10,
        "warmup_count": 10,
        "analysis_row_count": count,
        "feature_status_counts": feature_counts,
        "time_quality_counts": {"DATE_ONLY": count},
        "historical_pit_eligible_count": 0,
        "usage_scope": "REFERENCE_RESEARCH_ONLY",
        "limitations": ["HISTORICAL_TIME_NOT_PROVEN"],
        "production_decision_approved": False,
    }
    dataset_hash = content_hash(
        {
            "manifest": manifest,
            "row_hashes": [row["row_hash"] for row in rows],
        }
    )
    return {
        "contract_version": "VN_NEXT6B_S2_CALIBRATION_DATASET_V1",
        "dataset_id": f"MACROCAL-DEV-{dataset_hash[:16]}",
        "dataset_hash": dataset_hash,
        "status": "PARTIAL_REFERENCE_RESEARCH",
        "reason": None,
        "split_role": "DEVELOPMENT",
        "manifest": manifest,
        "rows": rows,
        "historical_evaluation_eligible": False,
        "production_decision_approved": False,
    }


def _expected(dataset: dict, source_hash: str) -> dict[str, str]:
    manifest = dataset["manifest"]
    return {
        "dataset_id": dataset["dataset_id"],
        "dataset_hash": dataset["dataset_hash"],
        "source_file_sha256": source_hash,
        "contract_version": dataset["contract_version"],
        "feature_contract_version": manifest["feature_contract_version"],
        "split_role": dataset["split_role"],
        "usage_scope": manifest["usage_scope"],
        "provider": manifest["provider"],
        "provider_series_id": manifest["provider_series_id"],
        "series_id": manifest["series_id"],
    }


def test_prebinding_excludes_unavailable_horizon_with_provenance() -> None:
    dataset = _dataset(count=12, missing_index=0)
    source_hash = "d" * 64
    result = bind_r5r_evaluation_dataset(
        dataset,
        source_file_sha256=source_hash,
        expected_identity=_expected(dataset, source_hash),
    )

    artifact = result["artifact"]
    assert artifact["source_row_count"] == 12
    assert artifact["joint_row_count"] == 11
    assert artifact["excluded_before_binding_count"] == 1
    assert artifact["excluded_reason_counts"] == {
        "REQUIRED_HORIZON_UNAVAILABLE": 1
    }
    assert artifact["metrics_computed"] is False
    assert artifact["reference_adequacy_evaluated"] is False
    assert artifact["holdout_accessed"] is False
    assert "HISTORICAL_TIME_NOT_PROVEN" in artifact["limitations"]
    assert len(result["bound_payload"]["joint_rows"]) == 11


def test_invalid_available_fractional_bp_fails_instead_of_rounding() -> None:
    dataset = _dataset(count=12, missing_index=None)
    dataset["rows"][0]["features"][1]["value"] = "1.5"
    source_hash = "d" * 64

    # dataset_hash binds row hashes rather than mutable row payload, so this test
    # targets the independent R5R lattice validation directly.
    with pytest.raises(R5RBindingError) as exc:
        bind_r5r_evaluation_dataset(
            dataset,
            source_file_sha256=source_hash,
            expected_identity=_expected(dataset, source_hash),
        )
    assert exc.value.code == "INVALID_FEATURE_LATTICE"


def test_duplicate_joint_date_fails_closed() -> None:
    dataset = _dataset(count=12, missing_index=None)
    dataset["rows"][1]["observation_date"] = dataset["rows"][0]["observation_date"]
    source_hash = "d" * 64

    with pytest.raises(R5RBindingError) as exc:
        bind_r5r_evaluation_dataset(
            dataset,
            source_file_sha256=source_hash,
            expected_identity=_expected(dataset, source_hash),
        )
    assert exc.value.code == "INVALID_CHRONOLOGY"


def test_chronology_hash_matches_br1_targeted_fixture() -> None:
    targeted = json.loads(
        (
            FIXTURES / "NEXT6E_S6A_R5R_MUR3_BR1_TARGETED_FIXTURES_V1.json"
        ).read_text(encoding="utf-8")
    )
    fixture = next(
        item
        for item in targeted["fixtures"]
        if item["fixture_id"] == "BR1-F02-A_CANONICAL_CHRONOLOGY_HASH"
    )
    dates = [row["observation_date"] for row in fixture["input"]["rows"]]
    assert canonical_chronology_hash(dates) == fixture["expected"]["sha256"]


def test_binding_contains_frozen_contract_identities_without_metrics() -> None:
    dataset = _dataset(count=12, missing_index=0)
    source_hash = "d" * 64
    artifact = bind_r5r_evaluation_dataset(
        dataset,
        source_file_sha256=source_hash,
        expected_identity=_expected(dataset, source_hash),
    )["artifact"]

    assert artifact["method_contract_sha256"] == R5R_METHOD_CONTRACT_SHA256
    assert artifact["method_design_sha256"] == R5R_METHOD_DESIGN_SHA256
    assert artifact["candidate_domain_sha256"] == R5R_CANDIDATE_DOMAIN_SHA256
    assert artifact["window_profile_sha256"] == R5R_WINDOW_PROFILE_SHA256
    assert artifact["policy_contract_sha256"] == R5R_POLICY_SHA256
    assert artifact["window_length"] == 2
    assert artifact["effective_candidate_mapping"]
    assert artifact["metrics_computed"] is False
    assert "OBSERVED_PATH_COMMON_N" not in artifact
    assert "candidates" not in artifact


def test_wrong_source_identity_fails_closed() -> None:
    dataset = _dataset(count=12, missing_index=0)
    source_hash = "d" * 64
    expected = _expected(dataset, source_hash)
    expected["source_file_sha256"] = "e" * 64

    with pytest.raises(R5RBindingError) as exc:
        bind_r5r_evaluation_dataset(
            dataset,
            source_file_sha256=source_hash,
            expected_identity=expected,
        )
    assert exc.value.code == "INVALID_DATA_IDENTITY"
