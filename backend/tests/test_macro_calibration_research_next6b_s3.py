from __future__ import annotations

from copy import deepcopy

import pytest

from app.macro.calibration_protocol import build_calibration_research_protocol
from app.macro.calibration_research import (
    build_distribution_research,
    summarize_distribution_research,
    validate_development_artifact,
)
from app.macro.features import MACRO_FEATURE_CONTRACT_VERSION
from app.macro.identity import content_hash


SERIES = "US_10Y_CONSTANT_MATURITY_YIELD"


def _feature(feature_id: str, value: str, unit: str) -> dict[str, object]:
    return {
        "feature_id": feature_id,
        "status": "AVAILABLE",
        "value": value,
        "unit": unit,
        "current_observation_ref": "ref",
        "baseline_observation_ref": None,
        "current_observation_date": None,
        "baseline_observation_date": None,
        "observation_distance": None,
        "calendar_distance_days": None,
        "reason": None,
        "contract_version": MACRO_FEATURE_CONTRACT_VERSION,
    }


def _row(index: int, date: str) -> dict[str, object]:
    features = [
        _feature("rate_level_pct", f"{4 + index / 100:.2f}", "PERCENT"),
        _feature("delta_bp_1obs", str(index - 2), "BASIS_POINT"),
        _feature("delta_bp_5obs", str((index - 2) * 3), "BASIS_POINT"),
        _feature("delta_bp_10obs", str((index - 2) * 5), "BASIS_POINT"),
    ]
    feature_set_hash = content_hash(
        {
            "contract_version": MACRO_FEATURE_CONTRACT_VERSION,
            "series_id": SERIES,
            "features": features,
        }
    )
    identity = {
        "split_role": "DEVELOPMENT",
        "series_id": SERIES,
        "vintage_id": "2023-12-29",
        "observation_key": f"KEY-{index}",
        "observation_date": date,
        "normalized_hash": f"{index + 1:064x}",
        "feature_contract_version": MACRO_FEATURE_CONTRACT_VERSION,
        "feature_set_hash": feature_set_hash,
    }
    return {
        **identity,
        "revision_no": 1,
        "time_quality": "DATE_ONLY",
        "historical_pit_eligible": False,
        "features": features,
        "row_hash": content_hash(identity),
    }


def _development_dataset() -> dict[str, object]:
    rows = [
        _row(0, "2020-01-02"),
        _row(1, "2020-01-03"),
        _row(2, "2021-01-04"),
        _row(3, "2022-01-04"),
        _row(4, "2023-01-03"),
    ]
    manifest = {
        "contract_version": "VN_NEXT6B_S2_CALIBRATION_DATASET_V1",
        "series_id": SERIES,
        "provider": "FRED",
        "provider_series_id": "DGS10",
        "split_role": "DEVELOPMENT",
        "observation_start": "2020-01-02",
        "observation_end": "2023-01-03",
        "vintage_id": "2023-12-29",
        "source_archive_hash": "a" * 64,
        "source_revision_policy": "LATEST_PUBLISHED_REVISION_WITHIN_FIXED_VINTAGE",
        "feature_contract_version": MACRO_FEATURE_CONTRACT_VERSION,
        "warmup_rule": "MAX_FEATURE_OBSERVATION_DISTANCE",
        "warmup_required": 10,
        "warmup_count": 10,
        "analysis_row_count": len(rows),
        "feature_status_counts": {},
        "time_quality_counts": {"DATE_ONLY": len(rows)},
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
        "status": "READY_REFERENCE_RESEARCH",
        "reason": None,
        "split_role": "DEVELOPMENT",
        "manifest": manifest,
        "rows": rows,
        "historical_evaluation_eligible": False,
        "production_decision_approved": False,
    }


def _protocol(development: dict[str, object]) -> dict[str, object]:
    holdout = {
        "status": "READY_REFERENCE_RESEARCH",
        "split_role": "HOLDOUT",
        "dataset_hash": "b" * 64,
        "manifest": {
            "series_id": SERIES,
            "feature_contract_version": MACRO_FEATURE_CONTRACT_VERSION,
            "observation_start": "2024-01-02",
            "observation_end": "2025-12-31",
            "vintage_id": "2025-12-31",
        },
    }
    protocol = build_calibration_research_protocol(
        development_dataset=development,
        holdout_dataset=holdout,
    )
    return protocol.to_dict()


def test_development_artifact_validates_hashes_and_order():
    dataset = _development_dataset()
    state = validate_development_artifact(dataset)

    assert state["dataset_hash"] == dataset["dataset_hash"]
    assert state["row_count"] == 5

    shuffled = deepcopy(dataset)
    shuffled["rows"][0], shuffled["rows"][1] = (
        shuffled["rows"][1],
        shuffled["rows"][0],
    )
    with pytest.raises(ValueError, match="ordered"):
        validate_development_artifact(shuffled)


def test_s3_rejects_holdout_or_tampered_development_artifact():
    dataset = _development_dataset()

    holdout = deepcopy(dataset)
    holdout["split_role"] = "HOLDOUT"
    with pytest.raises(ValueError, match="DEVELOPMENT"):
        validate_development_artifact(holdout)

    tampered = deepcopy(dataset)
    tampered["rows"][0]["features"][0]["value"] = "99"
    with pytest.raises(ValueError, match="feature_set_hash"):
        validate_development_artifact(tampered)


def test_distribution_research_keeps_holdout_locked_and_selects_nothing():
    development = _development_dataset()
    protocol = _protocol(development)

    research = build_distribution_research(
        development_dataset=development,
        protocol=protocol,
    )
    summary = summarize_distribution_research(research)

    assert research["development_row_count"] == 5
    assert research["holdout_accessed"] is False
    assert research["candidate_selection_status"] == "NOT_SELECTED"
    assert research["selected_feature"] is None
    assert research["selected_method"] is None
    assert research["selected_threshold"] is None
    assert research["selected_minimum_sample"] is None
    assert research["selected_rolling_lookback"] is None
    assert research["episode_policy_selected"] is False
    assert research["rate_spike_state"] == "UNCALIBRATED"
    assert research["normal_labels_created"] == 0
    assert research["detected_labels_created"] == 0
    assert research["network_requests"] == 0
    assert research["macro_db_writes"] == 0
    assert research["production_decision_approved"] is False
    assert summary["threshold_selected"] is False
    assert summary["minimum_sample_selected"] is False
    assert summary["rolling_lookback_selected"] is False


def test_future_rows_do_not_change_prior_expanding_results():
    development = _development_dataset()
    protocol = _protocol(development)
    first = build_distribution_research(
        development_dataset=development,
        protocol=protocol,
    )
    original_rows = first["feature_results"]["delta_bp_1obs"]["expanding"]["rows"]

    extended = deepcopy(development)
    future = _row(5, "2023-12-29")
    extended["rows"].append(future)
    extended["manifest"]["analysis_row_count"] = len(extended["rows"])
    extended["dataset_hash"] = content_hash(
        {
            "manifest": extended["manifest"],
            "row_hashes": [row["row_hash"] for row in extended["rows"]],
        }
    )
    extended["dataset_id"] = f"MACROCAL-DEV-{extended['dataset_hash'][:16]}"
    extended_protocol = _protocol(extended)

    second = build_distribution_research(
        development_dataset=extended,
        protocol=extended_protocol,
    )
    extended_rows = second["feature_results"]["delta_bp_1obs"]["expanding"]["rows"]

    assert original_rows == extended_rows[: len(original_rows)]


def test_yearly_summary_uses_same_rule_for_all_years():
    development = _development_dataset()
    protocol = _protocol(development)
    research = build_distribution_research(
        development_dataset=development,
        protocol=protocol,
    )

    years = research["feature_results"]["delta_bp_1obs"]["yearly_summary"]
    assert list(years) == ["2020", "2021", "2022", "2023"]
    assert years["2020"]["count"] == 2
    assert years["2021"]["count"] == 1
