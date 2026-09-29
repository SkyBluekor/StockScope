from __future__ import annotations

import pytest

from app.macro.candidate_compression import pareto_prune_behavior_groups
from tools.data.compress_macro_calibration_candidates_next6b_s4_1 import (
    build_parser,
)


def _group(
    name: str,
    *,
    feature: str = "delta_bp_1obs",
    fraction: str,
    coverage: int,
    separation: str,
    max_year: str,
) -> dict[str, object]:
    return {
        "behavior_group_id": f"RATEBG-{name}",
        "behavior_group_hash": name,
        "feature_id": feature,
        "signal_count": 1,
        "signal_fraction": fraction,
        "year_coverage_count": coverage,
        "episode_count": 1,
        "episode_separation_ratio": separation,
        "max_year_signal_share": max_year,
        "source_candidate_count": 1,
        "source_methods": ["EMPIRICAL_POSITIVE_TAIL"],
    }


def test_cross_method_pareto_has_no_weighted_score_or_method_partition():
    strong = _group(
        "strong",
        fraction="0.05",
        coverage=4,
        separation="1",
        max_year="0.4",
    )
    dominated = _group(
        "dominated",
        fraction="0.10",
        coverage=3,
        separation="0.8",
        max_year="0.5",
    )
    tradeoff = _group(
        "tradeoff",
        fraction="0.02",
        coverage=2,
        separation="1",
        max_year="0.5",
    )

    frontier, removed = pareto_prune_behavior_groups(
        [strong, dominated, tradeoff]
    )

    assert [item["behavior_group_hash"] for item in frontier] == [
        "strong",
        "tradeoff",
    ]
    assert removed == [
        {
            "behavior_group_id": "RATEBG-dominated",
            "behavior_group_hash": "dominated",
            "feature_id": "delta_bp_1obs",
            "signal_count": 1,
            "signal_fraction": "0.10",
            "year_coverage_count": 3,
            "episode_count": 1,
            "episode_separation_ratio": "0.8",
            "max_year_signal_share": "0.5",
            "source_candidate_count": 1,
            "source_methods": ["EMPIRICAL_POSITIVE_TAIL"],
            "dominated_by_group_hash": "strong",
            "dominance_contract_version": (
                "VN_NEXT6B_S4_1_CROSS_METHOD_PARETO_V1"
            ),
        }
    ]


def test_cross_method_pareto_never_compares_different_features():
    with pytest.raises(ValueError, match="different features"):
        pareto_prune_behavior_groups(
            [
                _group(
                    "one",
                    feature="delta_bp_1obs",
                    fraction="0.1",
                    coverage=2,
                    separation="1",
                    max_year="0.5",
                ),
                _group(
                    "five",
                    feature="delta_bp_5obs",
                    fraction="0.2",
                    coverage=2,
                    separation="1",
                    max_year="0.5",
                ),
            ]
        )


def test_s4_1_cli_intentionally_has_no_holdout_or_target_count_argument():
    parser = build_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--development-artifact" in option_strings
    assert "--protocol-artifact" in option_strings
    assert "--research-artifact" in option_strings
    assert "--write-artifact" in option_strings
    assert "--holdout-artifact" not in option_strings
    assert "--target-count" not in option_strings
