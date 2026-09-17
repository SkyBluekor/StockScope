from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.backtest.entry_risk_guide import (
    _display_price_rule,
    _price_plan_consistency,
    build_entry_risk_guide,
)


def _risk(**overrides):
    values = dict(
        status=SimpleNamespace(value="READY"),
        reference_only=False,
        entry_price=100_000,
        structural_anchor=96_000,
        structural_anchor_label="주요 지지선",
        invalidation_price=94_500,
        stop_zone_low=94_000,
        stop_zone_high=95_000,
        target1_price=108_000,
        target2_price=112_000,
        risk_pct=5.5,
        reward1_pct=8.0,
        reward2_pct=12.0,
        rr1=1.45,
        rr2=2.18,
        structure_rating="양호",
        summary="test",
        warnings=[],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _guide(strategy: str, raw: str, *, risk=None, current=100_000, support=96_000, ma20=98_000, high20=102_000):
    data = SimpleNamespace(
        current_price=current,
        ma20=ma20,
        ma20_slope_pct=0.7,
        volume_ratio_20=1.1,
        support_price=support,
        resistance_price=112_000,
    )
    return build_entry_risk_guide(
        strategy=strategy,
        data=data,
        technical={"support": support, "high20": high20, "resistance": 112_000},
        condition_state={"conditions": [{"raw": raw, "status": "PASS", "metric_key": None}]},
        risk_plan=risk or _risk(),
        current_state={"decision_reason": "ENTRY_CANDIDATE"},
        historical_verified=True,
        historical_status="GOOD",
        as_of_date="20260916",
    )


@pytest.mark.parametrize(
    ("strategy", "raw", "expected_kind"),
    [
        ("trend_following", "현재가가 20일선 위", "ABOVE"),
        ("pullback", "주요 지지선과 4% 이내", "RANGE"),
        ("breakout", "20일 고점과 2% 이내", "ABOVE"),
        ("support_bounce", "지지선과 2.5% 이내", "RANGE"),
        ("oversold_bounce", "지지선과 4% 이내", "RANGE"),
        ("range_trading", "지지선과 3% 이내", "RANGE"),
        ("momentum_continuation", "20일 고점과 5% 이내", "RANGE"),
        ("volatility_squeeze", "20일 고점과 4% 이내", "ABOVE"),
        ("ma20_rebound", "현재가가 20일선과 2.5% 이내", "RANGE"),
        ("trend_recovery", "현재가가 20일선 위로 회복", "ABOVE"),
    ],
)
def test_all_ten_strategy_price_rules_are_audited_without_rewriting(strategy, raw, expected_kind):
    guide = _guide(strategy, raw)
    assert guide["price_rule"]["kind"] == expected_kind
    assert guide["price_consistency"]["status"] in {"OK", "WARNING", "INVALID"}
    assert guide["risk"]["entry_reference_price"] == 100_000
    assert guide["risk"]["invalidation_price"] == 94_500
    assert guide["risk"]["stop_zone_low"] == 94_000
    assert guide["risk"]["stop_zone_high"] == 95_000


def _audit(entry_low, entry_high, *, stop_low=94_000, stop_high=95_000, invalidation=94_500, entry_reference=100_000, target1=108_000, target2=112_000):
    rule = _display_price_rule({
        "kind": "RANGE",
        "label": "테스트 진입 구간",
        "basis": "test",
        "range_low": entry_low,
        "range_high": entry_high,
        "trigger_price": None,
        "reference_price": entry_low,
    })
    risk = {
        "entry_reference_price": entry_reference,
        "invalidation_price": invalidation,
        "stop_zone_low": stop_low,
        "stop_zone_high": stop_high,
        "target1_price": target1,
        "target2_price": target2,
        "structural_anchor_label": "테스트 지지선",
    }
    return _price_plan_consistency(rule, risk)


def test_normal_entry_stop_relationship_is_ok_and_reports_gap():
    audit = _audit(96_000, 100_000)
    assert audit["status"] == "OK"
    assert audit["has_conflict"] is False
    assert "아래" in (audit["relation_message"] or "")


def test_stop_equal_to_strategy_condition_low_is_semantic_overlap_not_execution_conflict():
    audit = _audit(96_000, 100_000, stop_low=95_000, stop_high=96_000)
    assert audit["status"] == "OK"
    assert audit["classification"] == "STRATEGY_CONDITION_BAND_OVERLAP"
    assert audit["has_conflict"] is False
    assert "CONDITION_BAND_STOP_OVERLAP" in audit["issue_codes"]


def test_stop_inside_strategy_condition_band_is_explained_without_rewriting_prices():
    audit = _audit(96_000, 100_000, stop_low=96_500, stop_high=97_500)
    assert audit["status"] == "OK"
    assert audit["raw_overlap"] is True
    assert audit["semantic_overlap"] is True
    assert audit["overlap"]["low"] == 96_500
    assert audit["overlap"]["high"] == 97_500


def test_stop_above_risk_entry_is_still_invalid_even_if_condition_band_is_separate():
    audit = _audit(96_000, 100_000, stop_low=101_000, stop_high=102_000)
    assert audit["status"] == "INVALID"
    assert "STOP_AT_OR_ABOVE_RISK_ENTRY" in audit["issue_codes"]


def test_invalidation_inside_strategy_condition_band_is_context_not_execution_conflict():
    audit = _audit(96_000, 100_000, stop_low=94_000, stop_high=95_000, invalidation=97_000)
    assert audit["status"] == "OK"
    assert audit["semantic_overlap"] is True
    assert "CONDITION_BAND_INVALIDATION_OVERLAP" in audit["issue_codes"]


def test_target1_at_or_below_risk_entry_is_invalid():
    audit = _audit(96_000, 100_000, target1=99_000, target2=112_000)
    assert audit["status"] == "INVALID"
    assert "TARGET1_AT_OR_BELOW_RISK_ENTRY" in audit["issue_codes"]


def test_target2_below_target1_is_invalid():
    audit = _audit(96_000, 100_000, target1=108_000, target2=107_000)
    assert audit["status"] == "INVALID"
    assert "TARGET2_BELOW_TARGET1" in audit["issue_codes"]


def test_reversed_ranges_are_invalid_even_though_comparison_uses_sorted_pair():
    audit = _audit(100_000, 96_000, stop_low=95_000, stop_high=94_000)
    assert audit["status"] == "INVALID"
    assert "CONDITION_RANGE_REVERSED" in audit["issue_codes"]
    assert "STOP_ZONE_REVERSED" in audit["issue_codes"]


def test_display_rounding_touch_is_distinguished_from_raw_overlap():
    audit = _audit(
        50_040,
        52_000,
        stop_low=49_900,
        stop_high=50_030,
        invalidation=49_950,
        entry_reference=51_000,
        target1=55_000,
        target2=58_000,
    )
    assert audit["raw_overlap"] is False
    assert audit["display_overlap_only"] is True
    assert audit["status"] == "OK"
    assert audit["classification"] == "DISPLAY_ROUNDING_TOUCH"
    assert "DISPLAY_ROUNDING_TOUCH" in audit["issue_codes"]


def test_breakout_current_price_below_trigger_is_not_an_error_by_itself():
    guide = _guide(
        "breakout",
        "20일 고점과 2% 이내",
        current=98_000,
        high20=102_000,
        risk=_risk(entry_price=100_000, invalidation_price=94_500, stop_zone_low=94_000, stop_zone_high=95_000),
    )
    assert guide["price_rule"]["kind"] == "ABOVE"
    assert guide["price_rule"]["trigger_price"] == 102_000
    assert "ENTRY_STOP_OVERLAP" not in guide["price_consistency"]["issue_codes"]


def test_consistency_diagnostic_does_not_change_action_or_risk_values():
    risk = _risk(stop_zone_low=96_500, stop_zone_high=97_500)
    guide = _guide("pullback", "주요 지지선과 4% 이내", risk=risk)
    assert guide["price_consistency"]["status"] == "OK"
    assert guide["price_consistency"]["classification"] == "STRATEGY_CONDITION_BAND_OVERLAP"
    assert guide["action"]["status"] == "ENTRY_CANDIDATE"
    assert guide["risk"]["stop_zone_low"] == 96_500
    assert guide["risk"]["stop_zone_high"] == 97_500
