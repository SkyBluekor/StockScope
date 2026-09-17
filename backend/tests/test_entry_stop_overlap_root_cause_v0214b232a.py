from __future__ import annotations

import pytest

from app.backtest.entry_risk_guide import _display_price_rule, _price_plan_consistency, _price_rule_semantics


def _audit_case(*, condition_low, condition_high, current, stop_low, stop_high, target1):
    rule = _price_rule_semantics(_display_price_rule({
        "kind": "RANGE",
        "label": "전략 조건 가격대",
        "basis": "실제 Scanner 화면 회귀 fixture",
        "range_low": condition_low,
        "range_high": condition_high,
        "trigger_price": None,
        "reference_price": condition_low,
    }))
    invalidation = (stop_low + stop_high) / 2.0
    risk = {
        "entry_reference_price": current,
        "invalidation_price": invalidation,
        "stop_zone_low": stop_low,
        "stop_zone_high": stop_high,
        "target1_price": target1,
        "target2_price": max(target1 + (current - invalidation), target1 * 1.02),
        "structural_anchor_label": "RiskEngine 구조적 기준",
    }
    return _price_plan_consistency(rule, risk)


@pytest.mark.parametrize(
    ("name", "condition_low", "condition_high", "current", "stop_low", "stop_high", "target1", "overlap_low", "overlap_high"),
    [
        ("코스맥스", 272_000, 286_000, 280_500, 268_767, 273_513, 306_500, 272_000, 273_513),
        ("비에이치아이", 61_500, 64_700, 63_200, 60_363, 61_610, 66_800, 61_500, 61_610),
        ("삼성SDI", 527_000, 554_000, 544_000, 522_888, 531_075, 574_000, 527_000, 531_075),
        ("포스코인터내셔널", 53_100, 55_800, 54_800, 52_727, 53_517, 56_700, 53_100, 53_517),
        ("한국콜마", 134_500, 141_600, 150_000, 141_215, 143_827, 165_900, 141_215, 141_600),
    ],
)
def test_observed_scanner_overlaps_are_strategy_condition_context_not_stop_entry_conflicts(
    name, condition_low, condition_high, current, stop_low, stop_high, target1, overlap_low, overlap_high
):
    audit = _audit_case(
        condition_low=condition_low,
        condition_high=condition_high,
        current=current,
        stop_low=stop_low,
        stop_high=stop_high,
        target1=target1,
    )
    assert audit["status"] == "OK", name
    assert audit["classification"] == "STRATEGY_CONDITION_BAND_OVERLAP", name
    assert audit["has_conflict"] is False, name
    assert audit["semantic_overlap"] is True, name
    assert audit["overlap"]["low"] == overlap_low, name
    assert audit["overlap"]["high"] == overlap_high, name
    assert audit["raw"]["risk_entry_reference"] == current, name
    assert audit["raw"]["stop_zone_high"] < current, name
    assert "매수 가능 범위" in (audit["relation_message"] or ""), name


def test_strategy_range_metadata_explicitly_says_it_is_not_an_executable_entry_range():
    rule = _price_rule_semantics(_display_price_rule({
        "kind": "RANGE",
        "label": "20일 평균 가격 근처 구간",
        "basis": "현재가가 20일선과 2.5% 이내",
        "range_low": 97_500,
        "range_high": 102_500,
        "trigger_price": None,
        "reference_price": 100_000,
    }))
    assert rule["semantic_role"] == "STRATEGY_CONDITION_BAND"
    assert rule["user_label"] == "전략 조건 가격대"
    assert rule["executable_entry_range"] is False
    assert "매수 가능한 가격 범위" in rule["semantic_note"]


def test_actual_execution_risk_relationship_remains_invalid_when_stop_reaches_risk_entry():
    rule = _price_rule_semantics(_display_price_rule({
        "kind": "RANGE",
        "label": "전략 조건 가격대",
        "basis": "test",
        "range_low": 90_000,
        "range_high": 110_000,
        "trigger_price": None,
        "reference_price": 100_000,
    }))
    risk = {
        "entry_reference_price": 100_000,
        "invalidation_price": 98_000,
        "stop_zone_low": 99_000,
        "stop_zone_high": 100_500,
        "target1_price": 108_000,
        "target2_price": 112_000,
        "structural_anchor_label": "test",
    }
    audit = _price_plan_consistency(rule, risk)
    assert audit["status"] == "INVALID"
    assert audit["classification"] == "RISK_PLAN_INVALID"
    assert audit["has_conflict"] is True
    assert "STOP_AT_OR_ABOVE_RISK_ENTRY" in audit["issue_codes"]


def test_built_guide_exposes_trace_context_without_changing_ranking_inputs():
    from types import SimpleNamespace
    from app.backtest.entry_risk_guide import build_entry_risk_guide

    data = SimpleNamespace(
        current_price=100_000,
        ma20=98_000,
        ma20_slope_pct=0.7,
        volume_ratio_20=1.1,
        support_price=95_000,
        resistance_price=112_000,
    )
    risk = SimpleNamespace(
        status=SimpleNamespace(value="READY"),
        reference_only=False,
        entry_price=100_000,
        structural_anchor=98_000,
        structural_anchor_label="20일 이동평균선",
        invalidation_price=96_500,
        stop_zone_low=96_000,
        stop_zone_high=97_000,
        target1_price=108_000,
        target2_price=112_000,
        risk_pct=3.5, reward1_pct=8.0, reward2_pct=12.0, rr1=2.2, rr2=3.4,
        structure_rating="양호", summary="test", warnings=[],
    )
    guide = build_entry_risk_guide(
        strategy="ma20_rebound", data=data,
        technical={"support": 95_000, "high20": 110_000, "resistance": 112_000},
        condition_state={"conditions": [{"raw": "현재가가 20일선과 2.5% 이내", "status": "PASS", "metric_key": None}]},
        risk_plan=risk,
        current_state={"decision_reason": "ENTRY_CANDIDATE"},
        as_of_date="20260916",
    )
    trace = guide["price_consistency"]["trace_context"]
    assert trace["strategy"] == "ma20_rebound"
    assert trace["analysis_date"] == "20260916"
    assert trace["risk_entry_reference"] == 100_000
    assert trace["risk_structural_anchor_label"] == "20일 이동평균선"
    assert trace["strategy_rule_role"] == "STRATEGY_CONDITION_BAND"


def test_failed_strategy_price_condition_is_explanation_band_not_buy_range():
    """A failed price condition may be selected first to explain what must change.

    This is the important semantic case behind candidates such as 한국콜마: the
    shown band can sit well below current price while RiskEngine still references
    current price for stop/target construction.
    """
    from types import SimpleNamespace
    from app.backtest.entry_risk_guide import build_entry_risk_guide

    data = SimpleNamespace(
        current_price=150_000,
        ma20=138_000,
        ma20_slope_pct=0.8,
        volume_ratio_20=1.1,
        support_price=136_000,
        resistance_price=168_000,
    )
    risk = SimpleNamespace(
        status=SimpleNamespace(value="READY"),
        reference_only=False,
        entry_price=150_000,
        structural_anchor=142_500,
        structural_anchor_label="구조적 지지 기준",
        invalidation_price=142_500,
        stop_zone_low=141_215,
        stop_zone_high=143_827,
        target1_price=165_900,
        target2_price=175_000,
        risk_pct=5.0, reward1_pct=10.6, reward2_pct=16.7, rr1=2.1, rr2=3.3,
        structure_rating="보통", summary="test", warnings=[],
    )
    condition_state = {
        "conditions": [
            {"raw": "현재가가 20일선과 2.5% 이내", "status": "FAIL", "metric_key": None},
            {"raw": "현재가가 20일선 위로 회복", "status": "PASS", "metric_key": None},
        ]
    }
    guide = build_entry_risk_guide(
        strategy="trend_recovery", data=data,
        technical={"support": 136_000, "high20": 155_000, "resistance": 168_000},
        condition_state=condition_state,
        risk_plan=risk,
        current_state={"decision_reason": "WAIT_FOR_CONDITION"},
        as_of_date="20260916",
    )

    rule = guide["price_rule"]
    audit = guide["price_consistency"]
    assert rule["status"] == "FAIL"
    assert rule["semantic_role"] == "STRATEGY_CONDITION_BAND"
    assert rule["executable_entry_range"] is False
    assert rule["range_high"] < data.current_price
    assert audit["classification"] == "STRATEGY_CONDITION_BAND_OVERLAP"
    assert audit["status"] == "OK"
    assert audit["trace_context"]["strategy_rule_status"] == "FAIL"
    assert audit["trace_context"]["risk_entry_reference"] == 150_000
    assert audit["trace_context"]["decision_reason"] == "WAIT_FOR_CONDITION"
    assert "RiskEngine entry_price" in audit["sources"]["entry"]
    assert audit["sources"]["strategy_price"] == "현재가가 20일선과 2.5% 이내"
