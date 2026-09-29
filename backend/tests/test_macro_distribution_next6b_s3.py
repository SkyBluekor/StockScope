from __future__ import annotations

from decimal import Decimal

from app.macro.distribution import (
    analyze_feature_distribution,
    build_expanding_analysis,
    empirical_cdf,
    median_absolute_deviation,
    summarize_values,
    tail_profile,
)


def test_summary_and_mad_are_deterministic():
    values = [
        Decimal("-10"),
        Decimal("0"),
        Decimal("10"),
        Decimal("20"),
    ]
    summary = summarize_values(values)

    assert summary["count"] == 4
    assert summary["min"] == "-10"
    assert summary["max"] == "20"
    assert summary["mean"] == "5"
    assert summary["median"] == "5"
    assert summary["mad"] == "10"
    assert summary["positive_count"] == 2
    assert summary["zero_count"] == 1
    assert summary["negative_count"] == 1
    assert median_absolute_deviation(values) == Decimal("10")


def test_empirical_cdf_and_tail_profiles_do_not_select_thresholds():
    values = [
        Decimal("-10"),
        Decimal("0"),
        Decimal("10"),
        Decimal("10"),
        Decimal("20"),
    ]
    cdf = empirical_cdf(values)
    tails = tail_profile(values)

    assert cdf[-1]["value"] == "20"
    assert cdf[-1]["fraction_le"] == "1"
    assert tails["positive"][0] == {
        "value": "10",
        "count_ge": 3,
        "fraction_ge": "0.6",
    }
    assert tails["negative"][0]["value"] == "-10"
    assert tails["absolute"][-1]["absolute_value"] == "20"


def test_expanding_analysis_uses_strictly_prior_rows_only():
    first_three = [
        {"observation_date": "2020-01-01", "value": Decimal("1"), "row_hash": "a"},
        {"observation_date": "2020-01-02", "value": Decimal("2"), "row_hash": "b"},
        {"observation_date": "2020-01-03", "value": Decimal("4"), "row_hash": "c"},
    ]
    initial = build_expanding_analysis(first_three)
    with_future = build_expanding_analysis(
        first_three
        + [
            {
                "observation_date": "2023-12-29",
                "value": Decimal("999"),
                "row_hash": "future",
            }
        ]
    )

    assert initial["rows"] == with_future["rows"][:3]
    assert initial["rows"][0]["status"] == "INSUFFICIENT_HISTORY"
    assert initial["rows"][1]["prior_count"] == 1
    assert initial["rows"][2]["prior_count"] == 2
    assert initial["selected_rolling_lookback"] is None
    assert initial["minimum_sample_policy_defined"] is False


def test_feature_research_keeps_direction_and_windows_separate():
    rows = [
        {
            "observation_date": "2020-01-01",
            "row_hash": "a",
            "features": [
                {
                    "feature_id": "delta_bp_1obs",
                    "status": "AVAILABLE",
                    "value": "-5",
                }
            ],
        },
        {
            "observation_date": "2020-01-02",
            "row_hash": "b",
            "features": [
                {
                    "feature_id": "delta_bp_1obs",
                    "status": "AVAILABLE",
                    "value": "7",
                }
            ],
        },
        {
            "observation_date": "2020-01-03",
            "row_hash": "c",
            "features": [
                {
                    "feature_id": "delta_bp_1obs",
                    "status": "UNAVAILABLE",
                    "value": None,
                }
            ],
        },
    ]

    result = analyze_feature_distribution(rows, "delta_bp_1obs")

    assert result["available_count"] == 2
    assert result["unavailable_count"] == 1
    assert result["summary"]["positive_count"] == 1
    assert result["summary"]["negative_count"] == 1
    assert result["selected_threshold"] is None
    assert result["selected_minimum_sample"] is None
    assert result["selected_rolling_lookback"] is None
