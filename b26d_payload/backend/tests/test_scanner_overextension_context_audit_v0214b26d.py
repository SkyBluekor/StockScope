from __future__ import annotations

import copy

import pytest

from app.backtest.scanner_quality.overextension_context_audit import (
    CURRENT,
    EXPECTED_CURRENT_AUDIT_VERSION,
    EXPECTED_SCANNER_VERSION,
    ORIGINAL_GUARD,
    REFINED_GUARD,
    TRIPLE_ONLY,
    VERDICT_READY,
    _verdict,
    annotate_overextension,
    rank_variant,
    run_context_audit,
    should_demote,
)


def _row(rank: int, code: str, *, state: str = "READY", strategy: str = "pullback", rs: float = 0, p20: float = 0, m2060: float = 0, ret: float = 0):
    return {
        "analysis_date": "2026-01-01",
        "code": code,
        "rank": rank,
        "current_rank": rank,
        "candidate_state": state,
        "strategy": strategy,
        "relative_strength_market_pct": rs,
        "price_vs_ma20_pct": p20,
        "ma20_vs_ma60_pct": m2060,
        "return_20d": ret,
        "mfe_20d": max(ret, 0),
        "mae_20d": min(ret, 0),
        "event_20d": "TARGET1_FIRST" if ret > 0 else "STOP_FIRST",
    }


def test_same_date_q75_marks_two_of_three_overextension():
    rows = [
        _row(1, "A", rs=1, p20=1, m2060=1, ret=1),
        _row(2, "B", rs=2, p20=2, m2060=2, ret=2),
        _row(3, "C", rs=3, p20=3, m2060=3, ret=3),
        _row(4, "D", rs=10, p20=10, m2060=0, ret=4),
    ]
    annotated = annotate_overextension(rows)
    d = next(row for row in annotated if row["code"] == "D")
    assert d["extreme_feature_count"] == 2
    assert d["overextended"] is True


def test_refined_rule_exempts_only_trend_recovery_two_of_three():
    tr2 = {"candidate_state": "READY", "strategy": "trend_recovery", "overextended": True, "extreme_feature_count": 2}
    tr3 = {"candidate_state": "READY", "strategy": "trend_recovery", "overextended": True, "extreme_feature_count": 3}
    pb2 = {"candidate_state": "READY", "strategy": "pullback", "overextended": True, "extreme_feature_count": 2}
    assert should_demote(tr2, REFINED_GUARD) is False
    assert should_demote(tr3, REFINED_GUARD) is True
    assert should_demote(pb2, REFINED_GUARD) is True


def test_triple_only_does_not_demote_two_of_three():
    two = {"candidate_state": "READY", "strategy": "pullback", "overextended": True, "extreme_feature_count": 2}
    three = {"candidate_state": "READY", "strategy": "pullback", "overextended": True, "extreme_feature_count": 3}
    assert should_demote(two, TRIPLE_ONLY) is False
    assert should_demote(three, TRIPLE_ONLY) is True


def test_non_ready_slots_are_preserved():
    rows = [
        {**_row(1, "A"), "overextended": True, "extreme_feature_count": 3},
        {**_row(2, "W", state="WATCH"), "overextended": False, "extreme_feature_count": 0},
        {**_row(3, "B"), "overextended": False, "extreme_feature_count": 0},
    ]
    ranked = rank_variant(rows, ORIGINAL_GUARD)
    assert ranked[1]["code"] == "W"
    assert ranked[1]["candidate_state"] == "WATCH"


def test_future_outcome_mutation_cannot_change_refined_ranking():
    rows = [
        {**_row(1, "A", strategy="pullback"), "overextended": True, "extreme_feature_count": 2},
        {**_row(2, "B", strategy="trend_recovery"), "overextended": True, "extreme_feature_count": 2},
        {**_row(3, "C"), "overextended": False, "extreme_feature_count": 0},
    ]
    before = [row["code"] for row in rank_variant(rows, REFINED_GUARD)]
    mutated = copy.deepcopy(rows)
    for row in mutated:
        row["return_20d"] = 9999 if row["code"] == "A" else -9999
        row["mfe_20d"] = 9999
        row["mae_20d"] = -9999
        row["event_20d"] = "TARGET1_FIRST"
    after = [row["code"] for row in rank_variant(mutated, REFINED_GUARD)]
    assert before == after


def test_verdict_ready_when_refined_restores_event_quality_and_improves_return():
    comparisons = {
        "top3": {
            CURRENT: {
                "return_20d_mean": -1.0,
                "return_20d_trimmed_mean": -2.0,
                "return_20d_mean_without_best": -2.5,
                "mae_20d_mean": -14.0,
                "target1_first_20d_rate": 0.48,
                "stop_first_20d_rate": 0.48,
            },
            REFINED_GUARD: {
                "return_20d_mean": 2.0,
                "return_20d_trimmed_mean": 0.5,
                "return_20d_mean_without_best": 0.2,
                "mae_20d_mean": -12.0,
                "target1_first_20d_rate": 0.48,
                "stop_first_20d_rate": 0.48,
            },
        }
    }
    verdict, _ = _verdict(comparisons)
    assert verdict == VERDICT_READY


def test_current_payload_version_guard():
    development = {
        "source": {},
        "candidates": [
            {**_row(1, f"{i:03d}"), "analysis_date": f"2025-01-{(i % 28) + 1:02d}"}
            for i in range(25)
        ],
    }
    current = {
        "audit_version": EXPECTED_CURRENT_AUDIT_VERSION,
        "scanner_version": "0.21.3.6",
        "valid_date_count": 20,
        "production_changed": False,
        "dates": [],
    }
    with pytest.raises(ValueError, match=EXPECTED_SCANNER_VERSION):
        run_context_audit(development, current)
