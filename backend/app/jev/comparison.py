from __future__ import annotations

from collections import Counter
from typing import Any

from .models import JEV_COMPARISON_POLICY


def _key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row.get("capture_run_id") or ""), int(row.get("sample_index") or 0)


def _first_review_by_candidate(
    reviews: list[dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    ordered = sorted(
        reviews,
        key=lambda row: (
            str(row.get("requested_at") or ""),
            int(row.get("attempt") or 1),
            str(row.get("id") or ""),
        ),
    )
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for row in ordered:
        result.setdefault(_key(row), row)
    return result


def join_reviews_with_outcomes(
    reviews: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    review_map = _first_review_by_candidate(reviews)
    joined: list[dict[str, Any]] = []
    for outcome in outcomes:
        review = review_map.get(_key(outcome))
        joined.append(
            {
                "capture_run_id": str(outcome.get("capture_run_id") or ""),
                "sample_index": int(outcome.get("sample_index") or 0),
                "execution_status": str(
                    outcome.get("execution_status") or "NOT_EVALUATED"
                ),
                "net_return_pct": outcome.get("net_return_pct"),
                "review_status": (
                    str(review.get("status")) if review is not None else "MISSING"
                ),
                "review_decision": (
                    review.get("decision") if review is not None else None
                ),
                "review_id": review.get("id") if review is not None else None,
            }
        )
    return joined


def build_comparison_report(
    reviews: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    joined = join_reviews_with_outcomes(reviews, outcomes)
    comparable: list[dict[str, Any]] = []
    for row in joined:
        if row["execution_status"] != "CLOSED":
            continue
        value = row.get("net_return_pct")
        if value is None:
            continue
        comparable.append({**row, "net_return_pct": float(value)})

    status_counts = Counter(str(row.get("status") or "MISSING") for row in reviews)
    decision_counts = Counter(
        str(row.get("decision"))
        for row in reviews
        if row.get("decision") is not None
    )

    if not comparable:
        return {
            "comparison_policy": JEV_COMPARISON_POLICY,
            "comparable_closed_count": 0,
            "baseline_mean_return_pct": None,
            "shadow_mean_return_pct": None,
            "incremental_return_per_opportunity_pct": None,
            "avoided_loss_pct_sum": 0.0,
            "missed_profit_pct_sum": 0.0,
            "disagreement_count": 0,
            "disagreement_precision": None,
            "baseline_loss_rate": None,
            "shadow_loss_rate": None,
            "retained_candidate_loss_rate": None,
            "review_status_counts": dict(status_counts),
            "review_decision_counts": dict(decision_counts),
        }

    baseline_sum = 0.0
    shadow_sum = 0.0
    avoided_loss = 0.0
    missed_profit = 0.0
    disagreement_count = 0
    disagreement_losses = 0
    baseline_losses = 0
    shadow_losses = 0
    retained_count = 0
    retained_losses = 0

    for row in comparable:
        value = float(row["net_return_pct"])
        disagreement = (
            row["review_status"] == "VALID"
            and row["review_decision"] == "REVIEW_REQUIRED"
        )
        baseline_sum += value
        if value < 0:
            baseline_losses += 1

        if disagreement:
            disagreement_count += 1
            if value < 0:
                avoided_loss += -value
                disagreement_losses += 1
            elif value > 0:
                missed_profit += value
        else:
            retained_count += 1
            shadow_sum += value
            if value < 0:
                shadow_losses += 1
                retained_losses += 1

    count = len(comparable)
    return {
        "comparison_policy": JEV_COMPARISON_POLICY,
        "comparable_closed_count": count,
        "baseline_mean_return_pct": baseline_sum / count,
        "shadow_mean_return_pct": shadow_sum / count,
        "incremental_return_per_opportunity_pct": (
            shadow_sum - baseline_sum
        ) / count,
        "avoided_loss_pct_sum": avoided_loss,
        "missed_profit_pct_sum": missed_profit,
        "disagreement_count": disagreement_count,
        "disagreement_precision": (
            disagreement_losses / disagreement_count
            if disagreement_count
            else None
        ),
        "baseline_loss_rate": baseline_losses / count,
        "shadow_loss_rate": shadow_losses / count,
        "retained_candidate_loss_rate": (
            retained_losses / retained_count if retained_count else None
        ),
        "review_status_counts": dict(status_counts),
        "review_decision_counts": dict(decision_counts),
    }
