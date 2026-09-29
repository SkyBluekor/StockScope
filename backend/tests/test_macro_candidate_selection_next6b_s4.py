from __future__ import annotations

from app.macro.candidate_selection import pareto_prune_candidates


def _candidate(
    name: str,
    *,
    fraction: str,
    coverage: int,
    separation: str,
    max_year: str,
    threshold: str,
) -> dict[str, object]:
    return {
        "candidate_hash": name,
        "candidate_id": name,
        "feature_id": "delta_bp_1obs",
        "method": "EMPIRICAL_POSITIVE_TAIL",
        "threshold_definition": "RAW_BP_GE_OBSERVED_DEVELOPMENT_VALUE",
        "threshold_value": threshold,
        "threshold_unit": "BASIS_POINT",
        "threshold_source": "OBSERVED_DEVELOPMENT_VALUE",
        "direction": "UP",
        "required_condition": "FEATURE_AVAILABLE",
        "development_signal_count": 1,
        "development_signal_fraction": fraction,
        "year_coverage_count": coverage,
        "episode_separation_ratio": separation,
        "max_year_signal_share": max_year,
    }


def test_pareto_pruning_uses_no_weighted_score_and_is_deterministic():
    strong = _candidate(
        "strong",
        fraction="0.05",
        coverage=4,
        separation="1",
        max_year="0.4",
        threshold="10",
    )
    dominated = _candidate(
        "dominated",
        fraction="0.10",
        coverage=3,
        separation="0.8",
        max_year="0.5",
        threshold="5",
    )
    tradeoff = _candidate(
        "tradeoff",
        fraction="0.02",
        coverage=2,
        separation="1",
        max_year="0.5",
        threshold="15",
    )

    frozen, removed = pareto_prune_candidates(
        [strong, dominated, tradeoff]
    )

    assert [item["candidate_hash"] for item in frozen] == [
        "strong",
        "tradeoff",
    ]
    assert len(removed) == 1
    assert removed[0]["candidate_hash"] == "dominated"
    assert removed[0]["dominated_by"] == "strong"
