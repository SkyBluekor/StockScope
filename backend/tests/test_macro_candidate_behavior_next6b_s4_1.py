from __future__ import annotations

from copy import deepcopy

from app.macro.candidate_behavior import (
    build_behavior_groups,
    build_candidate_behavior,
    build_method_overlap_matrix,
)
from app.macro.calibration_candidate import RATE_SPIKE_METHODS


def _feature_result() -> dict[str, object]:
    return {
        "expanding": {
            "rows": [
                {
                    "observation_date": "2020-01-01",
                    "row_hash": "row-1",
                    "value": "-1",
                    "positive_tail_fraction_ge": "1",
                    "robust_deviation_mad": "-1",
                },
                {
                    "observation_date": "2020-01-02",
                    "row_hash": "row-2",
                    "value": "1",
                    "positive_tail_fraction_ge": "0.75",
                    "robust_deviation_mad": "1",
                },
                {
                    "observation_date": "2020-01-03",
                    "row_hash": "row-3",
                    "value": "2",
                    "positive_tail_fraction_ge": "0.5",
                    "robust_deviation_mad": "2",
                },
                {
                    "observation_date": "2020-01-04",
                    "row_hash": "row-4",
                    "value": "3",
                    "positive_tail_fraction_ge": "0.25",
                    "robust_deviation_mad": "3",
                },
            ]
        }
    }


def _candidate(
    name: str,
    *,
    method: str,
    threshold: str,
    eligible: int = 4,
    signal: int = 2,
) -> dict[str, object]:
    if method == "EMPIRICAL_POSITIVE_TAIL":
        definition = "RAW_BP_GE_OBSERVED_DEVELOPMENT_VALUE"
        unit = "BASIS_POINT"
        condition = "FEATURE_AVAILABLE"
        lookback = "FULL_DEVELOPMENT_REFERENCE"
    elif method == "EXPANDING_POSITIVE_TAIL_FRACTION":
        definition = "PRIOR_POSITIVE_TAIL_FRACTION_LE_OBSERVED_VALUE"
        unit = "FRACTION"
        condition = "PRIOR_OBSERVATION_EXISTS"
        lookback = "EXPANDING_STRICTLY_PRIOR"
    else:
        definition = "PRIOR_MAD_DEVIATION_GE_OBSERVED_VALUE"
        unit = "MAD_MULTIPLE"
        condition = "PRIOR_MAD_NON_ZERO"
        lookback = "EXPANDING_STRICTLY_PRIOR"

    return {
        "candidate_id": f"RATECAND-{name}",
        "candidate_hash": name,
        "feature_id": "delta_bp_1obs",
        "method": method,
        "direction": "UP",
        "threshold_definition": definition,
        "threshold_value": threshold,
        "threshold_unit": unit,
        "threshold_source": "OBSERVED_DEVELOPMENT_VALUE",
        "required_condition": condition,
        "lookback_mode": lookback,
        "selected_rolling_lookback": None,
        "eligible_row_count": eligible,
        "development_signal_count": signal,
        "development_signal_fraction": str(signal / eligible),
        "derived_minimum_prior_support": 2,
        "year_signal_counts": {"2020": signal},
        "year_coverage_count": 1,
        "year_coverage_fraction": "1",
        "max_year_signal_share": "1",
        "episode_summary": {"episode_count": 1},
        "episode_separation_ratio": str(1 / signal),
        "holdout_accessed": False,
        "production_decision_approved": False,
    }


def test_different_methods_with_same_behavior_share_signature():
    feature_result = _feature_result()
    empirical = _candidate(
        "empirical",
        method="EMPIRICAL_POSITIVE_TAIL",
        threshold="2",
    )
    robust = _candidate(
        "robust",
        method="EXPANDING_ROBUST_MAD",
        threshold="2",
    )

    left = build_candidate_behavior(
        feature_result=feature_result,
        candidate=empirical,
    )
    right = build_candidate_behavior(
        feature_result=feature_result,
        candidate=robust,
    )

    assert left["behavior_signature_hash"] == right["behavior_signature_hash"]
    assert left["signal_signature_hash"] == right["signal_signature_hash"]
    assert left["eligibility_signature_hash"] == right[
        "eligibility_signature_hash"
    ]


def test_same_signal_with_different_eligibility_is_different_behavior():
    feature_result = _feature_result()
    empirical = _candidate(
        "empirical",
        method="EMPIRICAL_POSITIVE_TAIL",
        threshold="2",
    )

    tail_result = deepcopy(feature_result)
    tail_result["expanding"]["rows"][0][
        "positive_tail_fraction_ge"
    ] = None
    tail = _candidate(
        "tail",
        method="EXPANDING_POSITIVE_TAIL_FRACTION",
        threshold="0.5",
        eligible=3,
        signal=2,
    )

    left = build_candidate_behavior(
        feature_result=feature_result,
        candidate=empirical,
    )
    right = build_candidate_behavior(
        feature_result=tail_result,
        candidate=tail,
    )

    assert left["signal_signature_hash"] == right["signal_signature_hash"]
    assert left["eligibility_signature_hash"] != right[
        "eligibility_signature_hash"
    ]
    assert left["behavior_signature_hash"] != right[
        "behavior_signature_hash"
    ]


def test_all_positive_capture_is_trivial_direction_rule():
    candidate = _candidate(
        "trivial",
        method="EMPIRICAL_POSITIVE_TAIL",
        threshold="1",
        signal=3,
    )
    candidate["development_signal_fraction"] = "0.75"
    candidate["year_signal_counts"] = {"2020": 3}
    candidate["episode_separation_ratio"] = str(1 / 3)

    behavior = build_candidate_behavior(
        feature_result=_feature_result(),
        candidate=candidate,
    )

    assert behavior["positive_move_count"] == 3
    assert behavior["positive_move_capture_count"] == 3
    assert behavior["positive_move_capture_fraction"] == "1"
    assert behavior["trivial_direction_rule"] is True


def test_behavior_group_preserves_method_aliases_and_source_thresholds():
    feature_result = _feature_result()
    empirical = _candidate(
        "empirical",
        method="EMPIRICAL_POSITIVE_TAIL",
        threshold="2",
    )
    robust = _candidate(
        "robust",
        method="EXPANDING_ROBUST_MAD",
        threshold="2",
    )

    grouped = build_behavior_groups(
        feature_id="delta_bp_1obs",
        feature_result=feature_result,
        candidates=[empirical, robust],
    )

    assert grouped["unique_behavior_group_count"] == 1
    assert grouped["behavior_duplicate_removed_count"] == 1
    group = grouped["behavior_groups"][0]
    assert group["source_candidate_count"] == 2
    assert group["source_methods"] == [
        "EMPIRICAL_POSITIVE_TAIL",
        "EXPANDING_ROBUST_MAD",
    ]
    assert {ref["threshold_value"] for ref in group["source_refs"]} == {"2"}

    overlap = build_method_overlap_matrix(
        grouped["behavior_groups"],
        RATE_SPIKE_METHODS,
    )
    assert overlap["EMPIRICAL_POSITIVE_TAIL"]["EXPANDING_ROBUST_MAD"] == 1
    assert overlap["EXPANDING_ROBUST_MAD"]["EMPIRICAL_POSITIVE_TAIL"] == 1
