from __future__ import annotations

from decimal import Decimal
from typing import Any


MACRO_CANDIDATE_DOMINANCE_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_PARETO_DOMINANCE_V1"
)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return True when left is no worse on all declared objectives.

    S4 deliberately uses no weighted score. Objectives are:
    - lower signal fraction (rarer),
    - higher year coverage,
    - higher episode separation ratio,
    - lower maximum single-year share.
    """

    left_fraction = _decimal(left["development_signal_fraction"])
    right_fraction = _decimal(right["development_signal_fraction"])
    left_coverage = int(left["year_coverage_count"])
    right_coverage = int(right["year_coverage_count"])
    left_separation = _decimal(left["episode_separation_ratio"])
    right_separation = _decimal(right["episode_separation_ratio"])
    left_max_year = _decimal(left["max_year_signal_share"])
    right_max_year = _decimal(right["max_year_signal_share"])

    no_worse = (
        left_fraction <= right_fraction
        and left_coverage >= right_coverage
        and left_separation >= right_separation
        and left_max_year <= right_max_year
    )
    strictly_better = (
        left_fraction < right_fraction
        or left_coverage > right_coverage
        or left_separation > right_separation
        or left_max_year < right_max_year
    )
    return no_worse and strictly_better


def pareto_prune_candidates(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frozen: list[dict[str, Any]] = []
    dominated: list[dict[str, Any]] = []

    for index, candidate in enumerate(candidates):
        dominators: list[str] = []
        for other_index, other in enumerate(candidates):
            if index == other_index:
                continue
            if _dominates(other, candidate):
                dominators.append(str(other["candidate_hash"]))
        if dominators:
            dominated.append(
                {
                    "candidate_hash": candidate["candidate_hash"],
                    "candidate_id": candidate["candidate_id"],
                    "feature_id": candidate["feature_id"],
                    "method": candidate["method"],
                    "threshold_definition": candidate["threshold_definition"],
                    "threshold_value": candidate["threshold_value"],
                    "development_signal_count": candidate[
                        "development_signal_count"
                    ],
                    "development_signal_fraction": candidate[
                        "development_signal_fraction"
                    ],
                    "year_coverage_count": candidate["year_coverage_count"],
                    "episode_separation_ratio": candidate[
                        "episode_separation_ratio"
                    ],
                    "max_year_signal_share": candidate[
                        "max_year_signal_share"
                    ],
                    "dominated_by": sorted(dominators),
                }
            )
        else:
            frozen.append(candidate)

    key = lambda item: (
        str(item["feature_id"]),
        str(item["method"]),
        _decimal(item["threshold_value"]),
        str(item["candidate_hash"]),
    )
    frozen.sort(key=key)
    dominated.sort(key=key)
    return frozen, dominated
