from __future__ import annotations

import copy

import pytest

from app.backtest.scanner_quality.entry_stability_volume_robustness import (
    EXPECTED_DEVELOPMENT_VERSION,
    EXPECTED_SCANNER_VERSION,
    EXPECTED_VALIDATION_VERSION,
    RULE_ID,
    VERDICT_FREEZE,
    _apply_development_volume_guard,
    _date_outcome,
    _metrics,
    _swap_category,
    _verdict,
    _validate_inputs,
)


def row(code: str, rank: int, band: str, event: str, event_r: float) -> dict:
    return {"code": code, "rank": rank, "candidate_state": "READY", "volume_ratio_prev20_band": band, "event_20d": event, "event_r_20d": event_r, "return_20d": event_r, "mae_20d": -1.0}


def test_volume_low_demotes_only_low_ready_preserving_groups():
    rows = [row("A",1,"MID","TARGET1_FIRST",1.0), row("B",2,"LOW","STOP_FIRST",-1.0), row("C",3,"MID","TARGET1_FIRST",1.0), row("D",4,"LOW","STOP_FIRST",-1.0)]
    out = _apply_development_volume_guard(rows)
    assert [x["code"] for x in out] == ["A","C","B","D"]


def test_policy_metrics_use_event_r_not_terminal_return_only():
    rows = [row("A",1,"MID","STOP_FIRST",-1.0), row("B",2,"MID","TARGET1_FIRST",1.5)]
    rows[0]["return_20d"] = 30.0
    m = _metrics(rows)
    assert m["event_r_20d_mean"] == pytest.approx(0.25)
    assert m["return_20d_mean"] > 10


def test_date_outcome_win_loss_tie():
    assert _date_outcome([row("A",1,"MID","STOP_FIRST",-1)], [row("B",1,"MID","TARGET1_FIRST",1.5)])["status"] == "WIN"
    assert _date_outcome([row("A",1,"MID","TARGET1_FIRST",1.5)], [row("B",1,"MID","STOP_FIRST",-1)])["status"] == "LOSS"
    assert _date_outcome([row("A",1,"MID","STOP_FIRST",-1)], [row("B",1,"MID","STOP_FIRST",-1)])["status"] == "TIE"


def test_swap_categories():
    assert _swap_category(row("A",1,"LOW","STOP_FIRST",-1), row("B",2,"MID","TARGET1_FIRST",1.5)) == "GOOD_SWAP"
    assert _swap_category(row("A",1,"LOW","TARGET1_FIRST",1.5), row("B",2,"MID","STOP_FIRST",-1)) == "BAD_SWAP"


def test_input_guards_require_promoted_volume_signal():
    dev = {"audit_version": EXPECTED_DEVELOPMENT_VERSION}
    val = {"audit_version": EXPECTED_VALIDATION_VERSION, "scanner_version": EXPECTED_SCANNER_VERSION, "verdict": "PROMOTE_VOLUME_SIGNAL", "surviving_rules": [RULE_ID]}
    _validate_inputs(dev, val)
    bad = copy.deepcopy(val); bad["scanner_version"] = "0.21.3.6"
    with pytest.raises(RuntimeError): _validate_inputs(dev, bad)


def test_freeze_verdict_requires_primary_event_r_mae_and_side_effects():
    base = {"target1_first_20d_rate":0.4,"stop_first_20d_rate":0.55,"event_r_20d_mean":0.0,"event_r_20d_trimmed_mean":-0.1,"mae_20d_mean":-10.0}
    good = {"target1_first_20d_rate":0.45,"stop_first_20d_rate":0.5,"event_r_20d_mean":0.2,"event_r_20d_trimmed_mean":0.0,"mae_20d_mean":-9.0}
    dev={"date_count":53,"current_top3":base,"guard_top3":good}
    val={"date_count":20,"current_top3":base,"guard_top3":good,"swaps":{"GOOD_SWAP":4,"BAD_SWAP":1},"date_outcomes":{"WIN":4,"LOSS":2},"aggressiveness":{"top1_changed_dates":0}}
    verdict,_ = _verdict(dev,val)
    assert verdict == VERDICT_FREEZE


def test_future_terminal_return_mutation_does_not_change_guard_order():
    rows = [row("A",1,"LOW","STOP_FIRST",-1), row("B",2,"MID","TARGET1_FIRST",1.5), row("C",3,"MID","TARGET1_FIRST",1.5)]
    before = [x["code"] for x in _apply_development_volume_guard(rows)]
    mutated = copy.deepcopy(rows)
    for item in mutated:
        item["return_20d"] = 9999.0
        item["event_20d"] = "TARGET1_FIRST"
        item["event_r_20d"] = 99.0
    after = [x["code"] for x in _apply_development_volume_guard(mutated)]
    assert before == after
