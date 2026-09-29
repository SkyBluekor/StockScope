from __future__ import annotations

from copy import deepcopy

import pytest

from app.macro.calibration_candidate import (
    RATE_SPIKE_FEATURE_IDS,
    build_rate_spike_candidate_set,
    generate_feature_candidates,
)
from app.macro.calibration_protocol import build_calibration_research_protocol
from app.macro.calibration_research import build_distribution_research
from app.macro.features import MACRO_FEATURE_CONTRACT_VERSION
from app.macro.identity import content_hash
from tools.data.freeze_macro_calibration_candidates_next6b_s4 import (
    build_parser,
)


SERIES = "US_10Y_CONSTANT_MATURITY_YIELD"
DELTA_VALUES = (-3, -1, 0, 1, 2, 3, -2, 4, 5, -4, 6, 7)


def _feature(
    feature_id: str,
    value: str,
    unit: str,
    date: str,
) -> dict[str, object]:
    return {
        "feature_id": feature_id,
        "status": "AVAILABLE",
        "value": value,
        "unit": unit,
        "current_observation_ref": "ref",
        "baseline_observation_ref": None,
        "current_observation_date": date,
        "baseline_observation_date": None,
        "observation_distance": None,
        "calendar_distance_days": None,
        "reason": None,
        "contract_version": MACRO_FEATURE_CONTRACT_VERSION,
    }


def _row(index: int, date: str) -> dict[str, object]:
    delta = DELTA_VALUES[index]
    features = [
        _feature(
            "rate_level_pct",
            f"{2 + index / 10:.1f}",
            "PERCENT",
            date,
        ),
        _feature("delta_bp_1obs", str(delta), "BASIS_POINT", date),
        _feature("delta_bp_5obs", str(delta * 2), "BASIS_POINT", date),
        _feature("delta_bp_10obs", str(delta * 3), "BASIS_POINT", date),
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
    dates = [
        "2020-01-02",
        "2020-02-03",
        "2020-03-02",
        "2021-01-04",
        "2021-02-01",
        "2021-03-01",
        "2022-01-03",
        "2022-02-01",
        "2022-03-01",
        "2023-01-03",
        "2023-02-01",
        "2023-03-01",
    ]
    rows = [_row(index, date) for index, date in enumerate(dates)]
    manifest = {
        "contract_version": "VN_NEXT6B_S2_CALIBRATION_DATASET_V1",
        "series_id": SERIES,
        "provider": "FRED",
        "provider_series_id": "DGS10",
        "split_role": "DEVELOPMENT",
        "observation_start": dates[0],
        "observation_end": dates[-1],
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
    return build_calibration_research_protocol(
        development_dataset=development,
        holdout_dataset=holdout,
    ).to_dict()


def _inputs():
    development = _development_dataset()
    protocol = _protocol(development)
    research = build_distribution_research(
        development_dataset=development,
        protocol=protocol,
    )
    return development, protocol, research


def test_candidate_thresholds_are_observed_development_breakpoints():
    development, protocol, research = _inputs()
    feature_result = research["feature_results"]["delta_bp_1obs"]

    generated = generate_feature_candidates(
        feature_id="delta_bp_1obs",
        feature_result=feature_result,
        development_dataset_hash=development["dataset_hash"],
        protocol_hash=protocol["protocol_hash"],
        research_hash=research["research_hash"],
    )
    empirical = generated["methods"]["EMPIRICAL_POSITIVE_TAIL"]
    empirical_hashes = set(empirical["generated_candidate_hashes"])
    frozen_and_removed = (
        generated["frozen_candidates"] + generated["dominated_candidates"]
    )
    empirical_candidates = [
        item
        for item in frozen_and_removed
        if item["method"] == "EMPIRICAL_POSITIVE_TAIL"
    ]

    observed_positive = {
        str(value)
        for value in DELTA_VALUES
        if value > 0
    }
    assert empirical["generated_count"] == len(observed_positive)
    assert {
        str(item["candidate_hash"]) for item in empirical_candidates
    } == empirical_hashes
    assert {
        str(item["threshold_value"]) for item in empirical_candidates
    } == observed_positive


def test_candidate_set_excludes_rate_level_and_keeps_holdout_locked():
    development, protocol, research = _inputs()

    candidate_set = build_rate_spike_candidate_set(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )

    assert set(candidate_set["per_feature"]) == set(RATE_SPIKE_FEATURE_IDS)
    assert all(
        candidate["feature_id"] != "rate_level_pct"
        for candidate in candidate_set["frozen_candidates"]
    )
    assert candidate_set["candidate_set_status"] == "FROZEN"
    assert candidate_set["holdout_locked"] is True
    assert candidate_set["holdout_accessed"] is False
    assert candidate_set["final_candidate_selected"] is False
    assert candidate_set["selected_candidate_id"] is None
    assert candidate_set["rate_spike_state"] == "UNCALIBRATED"
    assert candidate_set["normal_labels_created"] == 0
    assert candidate_set["detected_labels_created"] == 0
    assert candidate_set["network_requests"] == 0
    assert candidate_set["macro_db_writes"] == 0
    assert candidate_set["production_decision_approved"] is False
    assert candidate_set["exploration_manifest"][
        "generated_candidate_count"
    ] == (
        candidate_set["exploration_manifest"]["frozen_candidate_count"]
        + candidate_set["exploration_manifest"]["dominated_candidate_count"]
    )


def test_candidate_set_hash_is_deterministic():
    development, protocol, research = _inputs()

    first = build_rate_spike_candidate_set(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    second = build_rate_spike_candidate_set(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )

    assert first["candidate_set_hash"] == second["candidate_set_hash"]
    assert first["candidate_set_id"] == second["candidate_set_id"]


def test_tampered_research_is_rejected_before_candidate_generation():
    development, protocol, research = _inputs()
    tampered = deepcopy(research)
    tampered["feature_results"]["delta_bp_1obs"]["summary"]["max"] = "999"

    with pytest.raises(ValueError, match="research_hash"):
        build_rate_spike_candidate_set(
            development_dataset=development,
            protocol=protocol,
            research=tampered,
        )


def test_robust_candidates_require_positive_rate_move_and_nonzero_prior_mad():
    development, protocol, research = _inputs()
    generated = generate_feature_candidates(
        feature_id="delta_bp_1obs",
        feature_result=research["feature_results"]["delta_bp_1obs"],
        development_dataset_hash=development["dataset_hash"],
        protocol_hash=protocol["protocol_hash"],
        research_hash=research["research_hash"],
    )
    candidates = [
        item
        for item in (
            generated["frozen_candidates"]
            + generated["dominated_candidates"]
        )
        if item["method"] == "EXPANDING_ROBUST_MAD"
    ]

    assert candidates
    assert all(
        item["required_condition"] == "PRIOR_MAD_NON_ZERO"
        for item in candidates
    )
    assert all(
        item["direction"] == "UP"
        for item in candidates
    )
    assert all(
        float(item["threshold_value"]) > 0
        for item in candidates
    )


def test_s4_cli_intentionally_has_no_holdout_argument():
    parser = build_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--development-artifact" in option_strings
    assert "--protocol-artifact" in option_strings
    assert "--research-artifact" in option_strings
    assert "--holdout-artifact" not in option_strings
