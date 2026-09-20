from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.backtest.scanner_quality.entry_stability_volume_holdout import (
    EXPECTED_FROZEN_RULE_FINGERPRINT,
    RULE_ID,
    VERDICT_KEEP,
    VERDICT_PROMOTE,
    VERDICT_REJECT,
    _verdict,
    annotate_and_rank_frozen_volume,
    frozen_rule_fingerprint,
    ranking_freeze_hash,
    select_fresh_holdout,
    validate_d_source,
)


def _row(code: str, rank: int, volume: float, state: str = "READY") -> dict:
    return {
        "analysis_date": "2026-01-01",
        "market": "KOSPI",
        "code": code,
        "current_rank": rank,
        "candidate_state": state,
        "volume_ratio_prev20": volume,
    }


def test_frozen_rule_fingerprint_is_locked():
    assert frozen_rule_fingerprint() == EXPECTED_FROZEN_RULE_FINGERPRINT


def test_q25_rule_demotes_only_low_ready_and_preserves_group_order():
    rows = [
        _row("A", 1, 0.10),
        _row("B", 2, 0.20),
        _row("C", 3, 0.80),
        _row("D", 4, 0.90),
        _row("E", 5, 1.00),
        _row("F", 6, 1.10),
        _row("G", 7, 0.05, "WATCH"),
    ]
    current, guard, meta = annotate_and_rank_frozen_volume(rows)
    assert [r["code"] for r in current] == list("ABCDEFG")
    assert [r["code"] for r in guard[:6]] == ["C", "D", "E", "F", "A", "B"]
    assert guard[6]["code"] == "G"
    assert meta["ready_count"] == 6
    assert meta["unstable_count"] == 2
    assert [r["code"] for r in guard if r["volume_low"]] == ["A", "B"]


def test_non_ready_slot_is_immutable():
    rows = [_row("A", 1, 0.1), _row("W", 2, 0.01, "WATCH"), _row("B", 3, 1.0), _row("C", 4, 1.1), _row("D", 5, 1.2)]
    _, guard, _ = annotate_and_rank_frozen_volume(rows)
    assert guard[1]["code"] == "W"
    assert guard[1]["candidate_state"] == "WATCH"


def test_future_outcome_mutation_cannot_change_ranking_hash():
    rows = [_row("A", 1, 0.1), _row("B", 2, 0.8), _row("C", 3, 0.9), _row("D", 4, 1.0)]
    current, guard, meta = annotate_and_rank_frozen_volume(rows)
    first = ranking_freeze_hash("2026-01-01", current, guard, meta["q25"])
    for row in current + guard:
        row["event_20d"] = "TARGET1_FIRST"
        row["return_20d"] = 9999
        row["mfe_20d"] = 9999
        row["mae_20d"] = -9999
        row["event_r_20d"] = 9999
    second = ranking_freeze_hash("2026-01-01", current, guard, meta["q25"])
    assert first == second


def _calendar(start: date, count: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(count)]


def test_holdout_selector_is_deterministic_no_overlap_and_has_future_room():
    cal = _calendar(date(2023, 1, 1), 1500)
    excluded = {cal[i] for i in range(30, 1200, 17)}
    a = select_fresh_holdout(cal, excluded, sample_size=20, min_gap=3, future_sessions_required=20)
    b = select_fresh_holdout(cal, excluded, sample_size=20, min_gap=3, future_sessions_required=20)
    assert a == b
    assert len(a) == 20
    assert not (set(a) & excluded)
    positions = [cal.index(day) for day in a]
    assert all(abs(x - y) >= 3 for i, x in enumerate(positions) for y in positions[i + 1 :])
    excluded_pos = [cal.index(day) for day in excluded]
    assert all(min(abs(pos - other) for other in excluded_pos) >= 3 for pos in positions)
    assert max(positions) <= len(cal) - 21


def test_existing_holdout_dates_are_preserved_when_extending():
    cal = _calendar(date(2023, 1, 1), 1500)
    excluded = {cal[i] for i in range(50, 1200, 23)}
    first = select_fresh_holdout(cal, excluded, sample_size=20, min_gap=3, future_sessions_required=20)
    extended = select_fresh_holdout(cal, excluded, sample_size=24, existing_dates=first, min_gap=3, future_sessions_required=20)
    assert set(first).issubset(extended)
    assert len(extended) == 24


def test_existing_holdout_overlap_is_rejected():
    cal = _calendar(date(2023, 1, 1), 500)
    excluded = {cal[50]}
    with pytest.raises(ValueError, match="overlaps excluded"):
        select_fresh_holdout(cal, excluded, sample_size=4, existing_dates=[cal[50]], future_sessions_required=20)


def _metrics(t1: float, stop: float, er: float, ret: float = 0.0, mae: float = -5.0) -> dict:
    return {
        "target1_first_20d_rate": t1,
        "stop_first_20d_rate": stop,
        "event_r_20d_mean": er,
        "return_20d_mean": ret,
        "mae_20d_mean": mae,
    }


def test_promote_requires_t1_up_stop_down_and_event_r_up():
    cur = _metrics(0.40, 0.50, 0.10)
    grd = _metrics(0.45, 0.45, 0.20)
    verdict, _ = _verdict(cur, grd, {"WIN": 4, "LOSS": 2}, {"GOOD_SWAP": 3, "BAD_SWAP": 1}, {"top1_changed_dates": 0, "checked_dates": 20})
    assert verdict == VERDICT_PROMOTE


def test_equal_primary_is_not_promoted():
    cur = _metrics(0.40, 0.50, 0.10)
    grd = _metrics(0.40, 0.50, 0.20)
    verdict, _ = _verdict(cur, grd, {"WIN": 4, "LOSS": 2}, {"GOOD_SWAP": 3, "BAD_SWAP": 1}, {"top1_changed_dates": 0, "checked_dates": 20})
    assert verdict == VERDICT_KEEP


def test_return_or_mae_protection_failure_blocks_promotion():
    cur = _metrics(0.40, 0.50, 0.10, ret=1.0, mae=-5.0)
    grd = _metrics(0.45, 0.45, 0.20, ret=-0.1, mae=-6.1)
    verdict, _ = _verdict(cur, grd, {"WIN": 4, "LOSS": 2}, {"GOOD_SWAP": 3, "BAD_SWAP": 1}, {"top1_changed_dates": 0, "checked_dates": 20})
    assert verdict != VERDICT_PROMOTE


def test_clear_primary_reversal_is_rejected():
    cur = _metrics(0.45, 0.45, 0.20)
    grd = _metrics(0.35, 0.60, 0.00)
    verdict, _ = _verdict(cur, grd, {"WIN": 1, "LOSS": 5}, {"GOOD_SWAP": 1, "BAD_SWAP": 4}, {"top1_changed_dates": 5, "checked_dates": 20})
    assert verdict == VERDICT_REJECT


def test_d_source_must_be_frozen_and_current_scanner():
    good = {
        "audit_version": "v0.21.4-B.2.7-D",
        "verdict": "FREEZE_VOLUME_LOW_GUARD",
        "production_changed": False,
        "rule": {
            "rule_id": RULE_ID,
            "feature": "volume_ratio_prev20",
            "threshold": "same-date READY Q25",
            "tuning_allowed": False,
        },
        "sources": {"validation": {"scanner_version": "0.21.3.7"}},
    }
    assert validate_d_source(good)["scanner_version"] == "0.21.3.7"
    bad = dict(good)
    bad["verdict"] = "VOLUME_SIGNAL_NOT_ROBUST"
    with pytest.raises(ValueError):
        validate_d_source(bad)
