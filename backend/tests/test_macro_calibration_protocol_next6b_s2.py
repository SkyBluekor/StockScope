from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.macro.calibration_protocol import (
    build_calibration_research_protocol,
    validate_split_ranges,
)
from tools.data.prepare_macro_calibration_next6b_s2 import write_immutable_json


def _dataset(
    *,
    role: str,
    dataset_hash: str,
    start: str,
    end: str,
    vintage: str,
):
    return {
        "status": "READY_REFERENCE_RESEARCH",
        "split_role": role,
        "dataset_hash": dataset_hash,
        "manifest": {
            "series_id": "US_10Y_CONSTANT_MATURITY_YIELD",
            "feature_contract_version": "VN_NEXT6B_S1_MACRO_FEATURE_V1",
            "observation_start": start,
            "observation_end": end,
            "vintage_id": vintage,
        },
    }


def test_split_ranges_must_be_chronological_and_non_overlapping():
    with pytest.raises(ValueError, match="non-overlapping"):
        validate_split_ranges(
            development_start="2026-01-01",
            development_end="2026-06-30",
            holdout_start="2026-06-30",
            holdout_end="2026-09-30",
        )

    with pytest.raises(ValueError, match="development_start"):
        validate_split_ranges(
            development_start="2026-06-30",
            development_end="2026-01-01",
            holdout_start="2026-07-01",
            holdout_end="2026-09-30",
        )


def test_protocol_freezes_split_structure_without_numeric_policy():
    development = _dataset(
        role="DEVELOPMENT",
        dataset_hash="a" * 64,
        start="2024-01-01",
        end="2024-12-31",
        vintage="2024-12-31",
    )
    holdout = _dataset(
        role="HOLDOUT",
        dataset_hash="b" * 64,
        start="2025-01-01",
        end="2025-12-31",
        vintage="2025-12-31",
    )

    protocol = build_calibration_research_protocol(
        development_dataset=development,
        holdout_dataset=holdout,
    )
    payload = protocol.to_dict()

    assert payload["holdout_locked"] is True
    assert payload["threshold_defined"] is False
    assert payload["minimum_sample_defined"] is False
    assert payload["episode_policy_defined"] is False
    assert payload["production_decision_approved"] is False
    assert payload["base_protocol"]["numeric_thresholds_defined"] is False
    assert payload["candidate_method_families"] == [
        "ROLLING_QUANTILE",
        "ROBUST_STANDARDIZED_DEVIATION",
    ]


def test_protocol_hash_is_deterministic():
    development = _dataset(
        role="DEVELOPMENT",
        dataset_hash="a" * 64,
        start="2024-01-01",
        end="2024-12-31",
        vintage="2024-12-31",
    )
    holdout = _dataset(
        role="HOLDOUT",
        dataset_hash="b" * 64,
        start="2025-01-01",
        end="2025-12-31",
        vintage="2025-12-31",
    )
    first = build_calibration_research_protocol(
        development_dataset=development,
        holdout_dataset=holdout,
    )
    second = build_calibration_research_protocol(
        development_dataset=development,
        holdout_dataset=holdout,
    )
    assert first.protocol_hash == second.protocol_hash
    assert first.protocol_id == second.protocol_id


def test_immutable_artifact_writer_is_idempotent_and_collision_safe(tmp_path: Path):
    payload = {"dataset_hash": "a" * 64, "value": 1}
    first = write_immutable_json(
        directory=tmp_path,
        prefix="DEV",
        identity="a" * 16,
        payload=payload,
    )
    second = write_immutable_json(
        directory=tmp_path,
        prefix="DEV",
        identity="a" * 16,
        payload=payload,
    )
    assert second == first
    assert json.loads(first.read_text(encoding="utf-8")) == payload

    with pytest.raises(RuntimeError, match="collision"):
        write_immutable_json(
            directory=tmp_path,
            prefix="DEV",
            identity="a" * 16,
            payload={"dataset_hash": "a" * 64, "value": 2},
        )
