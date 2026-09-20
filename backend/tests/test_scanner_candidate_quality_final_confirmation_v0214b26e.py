from __future__ import annotations

import copy
from datetime import date, timedelta

import pytest

from app.backtest.scanner_quality.candidate_quality_final_confirmation import (
    CURRENT,
    EXPECTED_FROZEN_RULE_FINGERPRINT,
    FROZEN_REFINED,
    FROZEN_RULE_SPEC,
    VERDICT_INSUFFICIENT,
    VERDICT_PROMOTE,
    _verdict,
    annotate_and_rank_frozen,
    ensure_frozen_rule,
    frozen_rule_fingerprint,
    select_holdout_from_calendar,
)
from app.backtest.scanner_quality.candidate_quality_validation import ensure_scanner_version


def _row(
    rank: int,
    code: str,
    *,
    state: str = "READY",
    strategy: str = "pullback",
    rs: float = 0.0,
    p20: float = 0.0,
    m2060: float = 0.0,
) -> dict:
    return {
        "analysis_date": "2026-01-01",
        "market": "KOSPI",
        "code": code,
        "current_rank": rank,
        "candidate_state": state,
        "strategy": strategy,
        "relative_strength_market_pct": rs,
        "price_vs_ma20_pct": p20,
        "ma20_vs_ma60_pct": m2060,
    }


def test_frozen_rule_fingerprint_is_locked():
    assert ensure_frozen_rule() == EXPECTED_FROZEN_RULE_FINGERPRINT
    assert frozen_rule_fingerprint() == EXPECTED_FROZEN_RULE_FINGERPRINT
    changed = copy.deepcopy(FROZEN_RULE_SPEC)
    changed["threshold"] = "same-date READY Q80"
    assert frozen_rule_fingerprint(changed) != EXPECTED_FROZEN_RULE_FINGERPRINT


def test_exact_two_of_three_trend_recovery_is_exempt_but_three_of_three_is_demoted():
    rows = [
        _row(1, "A", rs=1, p20=1, m2060=1),
        _row(2, "B", rs=2, p20=2, m2060=2),
        _row(3, "C", rs=3, p20=3, m2060=3),
        _row(4, "TR2", strategy="trend_recovery", rs=10, p20=10, m2060=0),
        _row(5, "TR3", strategy="trend_recovery", rs=11, p20=11, m2060=11),
        _row(6, "SAFE", rs=0, p20=0, m2060=0),
    ]
    current, frozen, meta = annotate_and_rank_frozen(rows)
    by_code = {row["code"]: row for row in current}
    assert by_code["TR2"]["extreme_feature_count"] == 2
    assert by_code["TR2"]["refined_exception"] is True
    assert by_code["TR2"]["frozen_demoted"] is False
    assert by_code["TR3"]["extreme_feature_count"] == 3
    assert by_code["TR3"]["refined_exception"] is False
    assert by_code["TR3"]["frozen_demoted"] is True
    assert meta["refined_exception_opportunities"] == 1
    assert [row["code"] for row in frozen].index("TR2") < [row["code"] for row in frozen].index("TR3")


def test_non_ready_slot_is_immutable():
    rows = [
        _row(1, "HOT", rs=10, p20=10, m2060=10),
        _row(2, "WATCH", state="WATCH"),
        _row(3, "SAFE", rs=0, p20=0, m2060=0),
        _row(4, "MID", rs=1, p20=1, m2060=1),
    ]
    _current, frozen, _meta = annotate_and_rank_frozen(rows)
    assert frozen[1]["code"] == "WATCH"
    assert frozen[1]["candidate_state"] == "WATCH"


def test_future_outcome_mutation_cannot_change_frozen_ranking():
    rows = [
        _row(1, "A", rs=10, p20=10, m2060=10),
        _row(2, "B", strategy="trend_recovery", rs=9, p20=9, m2060=0),
        _row(3, "C", rs=0, p20=0, m2060=0),
        _row(4, "D", rs=1, p20=1, m2060=1),
    ]
    _c1, frozen1, _m1 = annotate_and_rank_frozen(rows)
    mutated = copy.deepcopy(rows)
    for row in mutated:
        row["return_20d"] = 9999 if row["code"] == "A" else -9999
        row["mfe_20d"] = 9999
        row["mae_20d"] = -9999
        row["event_20d"] = "TARGET1_FIRST"
    _c2, frozen2, _m2 = annotate_and_rank_frozen(mutated)
    assert [row["code"] for row in frozen1] == [row["code"] for row in frozen2]


def _weekday_calendar(start: date, end: date) -> list[date]:
    result: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def test_holdout_selector_is_deterministic_and_has_no_overlap():
    calendar = _weekday_calendar(date(2023, 1, 2), date(2026, 8, 18))
    used = set(calendar[10::12][:73])
    first = select_holdout_from_calendar(calendar, used, sample_size=20, min_gap=3)
    second = select_holdout_from_calendar(calendar, used, sample_size=20, min_gap=3)
    assert first == second
    assert len(first) == 20
    assert len(set(first)) == 20
    assert not (set(first) & used)
    assert {day.year for day in first} == {2023, 2024, 2025, 2026}


def test_existing_holdout_is_preserved_when_extending_to_30():
    calendar = _weekday_calendar(date(2023, 1, 2), date(2026, 8, 18))
    used = set(calendar[10::13][:73])
    first20 = select_holdout_from_calendar(calendar, used, sample_size=20, min_gap=3)
    thirty = select_holdout_from_calendar(calendar, used, sample_size=30, existing_dates=first20, min_gap=3)
    assert set(first20).issubset(thirty)
    assert len(thirty) == 30


def test_holdout_selector_rejects_existing_overlap():
    calendar = _weekday_calendar(date(2023, 1, 2), date(2026, 8, 18))
    used = {calendar[50]}
    with pytest.raises(ValueError, match="overlap"):
        select_holdout_from_calendar(calendar, used, sample_size=20, existing_dates=[calendar[50]], min_gap=3)


def _promotion_inputs(*, overextended: int = 20, exceptions: int = 4):
    comparisons = {
        "top3": {
            CURRENT: {
                "return_20d_mean": -1.0,
                "return_20d_trimmed_mean": -2.0,
                "return_20d_mean_without_best": -2.5,
                "return_20d_median": -1.0,
                "return_20d_positive_rate": 0.40,
                "return_10d_mean": -0.5,
                "mae_20d_mean": -14.0,
                "target1_first_10d_rate": 0.45,
                "target1_first_20d_rate": 0.48,
                "stop_first_20d_rate": 0.48,
            },
            FROZEN_REFINED: {
                "return_20d_mean": 1.5,
                "return_20d_trimmed_mean": 0.5,
                "return_20d_mean_without_best": 0.2,
                "return_20d_median": 0.1,
                "return_20d_positive_rate": 0.50,
                "return_10d_mean": 0.2,
                "mae_20d_mean": -11.0,
                "target1_first_10d_rate": 0.47,
                "target1_first_20d_rate": 0.50,
                "stop_first_20d_rate": 0.45,
            },
        }
    }
    impact = {
        "overextended_candidates": overextended,
        "refined_exception_opportunities": exceptions,
    }
    stability = {"stable_block_count": 3, "block_count": 4}
    return comparisons, impact, stability


def test_final_verdict_promotes_only_when_frozen_gates_clear():
    comparisons, impact, stability = _promotion_inputs()
    verdict, reasons = _verdict(comparisons, impact, stability)
    assert verdict == VERDICT_PROMOTE
    assert any("block stability" in reason for reason in reasons)


def test_final_verdict_requires_minimum_exception_sample():
    comparisons, impact, stability = _promotion_inputs(exceptions=2)
    verdict, reasons = _verdict(comparisons, impact, stability)
    assert verdict == VERDICT_INSUFFICIENT
    assert any("exception opportunities" in reason for reason in reasons)


def test_stale_scanner_version_is_rejected():
    with pytest.raises(RuntimeError, match="0.21.3.7"):
        ensure_scanner_version("0.21.3.6")
