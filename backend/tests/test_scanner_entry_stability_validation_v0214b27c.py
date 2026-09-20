from __future__ import annotations

import copy

import pytest

from app.backtest.scanner_quality.entry_stability_validation import (
    CURRENT,
    RULE_MA20_GAP_HIGH,
    RULE_RETURN_STD_HIGH,
    RULE_VOLUME_LOW,
    _metrics,
    _rule_verdict,
    apply_entry_stability_rule,
    classify_ready_bands,
    ensure_scanner_version,
)


def _rows() -> list[dict]:
    values = [
        ("A", "READY", 0.4, 1.0, -8.0),
        ("B", "READY", 0.7, 2.0, -4.0),
        ("C", "READY", 1.0, 3.0, 0.0),
        ("D", "READY", 1.3, 4.0, 4.0),
        ("W", "WATCH", 0.1, 9.0, 9.0),
    ]
    rows = []
    for rank, (code, state, volume, std, gap) in enumerate(values, start=1):
        rows.append({
            "code": code,
            "current_rank": rank,
            "candidate_state": state,
            "volume_ratio_prev20": volume,
            "return_std_20d_pct": std,
            "ma20_gap_change_5d_pct": gap,
            "event_20d": "TARGET1_FIRST" if code in {"A", "C"} else "STOP_FIRST",
            "return_20d": rank,
            "mae_20d": -rank,
        })
    return rows


def test_same_date_quartiles_are_ready_only_and_deterministic() -> None:
    rows1 = _rows()
    rows2 = copy.deepcopy(rows1)
    t1 = classify_ready_bands(rows1)
    t2 = classify_ready_bands(rows2)
    assert t1 == t2
    assert rows1[-1]["volume_ratio_prev20_band"] == "MISSING"
    assert rows1[0]["volume_ratio_prev20_band"] == "LOW"
    assert rows1[-2]["volume_ratio_prev20_band"] == "HIGH"


def test_volume_low_demotes_only_ready_and_preserves_watch_slot() -> None:
    rows = _rows()
    classify_ready_bands(rows)
    result, meta = apply_entry_stability_rule(rows, RULE_VOLUME_LOW)
    assert meta["unstable_count"] == 1
    assert [row["code"] for row in result] == ["B", "C", "D", "A", "W"]
    assert result[4]["candidate_state"] == "WATCH"


def test_return_std_high_demotes_high_quartile() -> None:
    rows = _rows()
    classify_ready_bands(rows)
    result, meta = apply_entry_stability_rule(rows, RULE_RETURN_STD_HIGH)
    assert meta["unstable_count"] == 1
    assert result[-2]["code"] == "D"


def test_ma20_gap_high_demotes_high_quartile() -> None:
    rows = _rows()
    classify_ready_bands(rows)
    result, meta = apply_entry_stability_rule(rows, RULE_MA20_GAP_HIGH)
    assert meta["unstable_count"] == 1
    assert result[-2]["code"] == "D"


def test_future_outcome_mutation_does_not_change_rule_ranking() -> None:
    rows = _rows()
    classify_ready_bands(rows)
    first, _ = apply_entry_stability_rule(rows, RULE_VOLUME_LOW)
    mutated = copy.deepcopy(rows)
    for row in mutated:
        row["event_20d"] = "STOP_FIRST" if row["event_20d"] == "TARGET1_FIRST" else "TARGET1_FIRST"
        row["return_20d"] = -9999
        row["mae_20d"] = -9999
    second, _ = apply_entry_stability_rule(mutated, RULE_VOLUME_LOW)
    assert [row["code"] for row in first] == [row["code"] for row in second]


def test_event_metrics_keep_no_event_separate() -> None:
    rows = [
        {"event_20d": "TARGET1_FIRST", "return_20d": 1, "mae_20d": -1},
        {"event_20d": "STOP_FIRST", "return_20d": -1, "mae_20d": -2},
        {"event_20d": "NO_EVENT", "return_20d": 0, "mae_20d": -0.5},
    ]
    metrics = _metrics(rows)
    assert metrics["target1_first_20d_rate"] == pytest.approx(1 / 3)
    assert metrics["stop_first_20d_rate"] == pytest.approx(1 / 3)
    assert metrics["no_event_20d_rate"] == pytest.approx(1 / 3)


def test_rule_pass_requires_both_event_improvements_and_protection() -> None:
    current = {"target1_first_20d_rate": 0.40, "stop_first_20d_rate": 0.55, "return_20d_mean": 1.0, "mae_20d_mean": -8.0}
    good = {"target1_first_20d_rate": 0.45, "stop_first_20d_rate": 0.50, "return_20d_mean": 0.5, "mae_20d_mean": -8.5}
    weak = {"target1_first_20d_rate": 0.45, "stop_first_20d_rate": 0.56, "return_20d_mean": 1.0, "mae_20d_mean": -8.0}
    bad_protection = {"target1_first_20d_rate": 0.45, "stop_first_20d_rate": 0.50, "return_20d_mean": -0.1, "mae_20d_mean": -8.0}
    assert _rule_verdict(current, good)[0] == "PASS"
    assert _rule_verdict(current, weak)[0] == "WEAK"
    assert _rule_verdict(current, bad_protection)[0] == "FAIL"


def test_stale_scanner_is_blocked() -> None:
    ensure_scanner_version("0.21.3.7")
    with pytest.raises(RuntimeError, match="STALE_SOURCE"):
        ensure_scanner_version("0.21.3.6")
