from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.backtest.entry_risk_guide import build_entry_risk_guide


def _data(**overrides):
    values = dict(
        current_price=100_000,
        ma20=98_000,
        ma20_slope_pct=0.7,
        volume_ratio_20=0.9,
        support_price=96_000,
        resistance_price=110_000,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


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
        summary="현재 전략 기준으로 손절 폭과 목표 여유가 비교 가능한 구조입니다.",
        warnings=[],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _state(raw: str, *, status: str = "FAIL", metric_key: str | None = None):
    return {
        "conditions": [
            {
                "raw": raw,
                "status": status,
                "metric_key": metric_key,
                "detail": "실제 전략 조건을 확인합니다.",
            }
        ]
    }


def _guide(strategy: str, state, *, data=None, technical=None, risk=None, current_reason="ENTRY_CONDITIONS_MISSING", historical_verified=True, historical_status="GOOD", as_of_date=None, entry_timing=None):
    return build_entry_risk_guide(
        strategy=strategy,
        data=data or _data(),
        technical=technical or {},
        condition_state=state,
        risk_plan=risk or _risk(),
        current_state={"decision_reason": current_reason},
        historical_verified=historical_verified,
        historical_status=historical_status,
        as_of_date=as_of_date,
        entry_timing=entry_timing,
    )


def test_support_condition_is_converted_to_exact_price_range_without_new_threshold():
    guide = _guide(
        "pullback",
        _state("주요 지지선과 4% 이내", metric_key="support_distance"),
        data=_data(current_price=101_000, support_price=96_000),
        technical={"support": 96_000},
    )
    assert guide["price_rule"]["kind"] == "RANGE"
    assert guide["price_rule"]["range_low"] == 96_000
    assert round(guide["price_rule"]["range_high"], 2) == 100_000.00
    assert guide["price_rule"]["gap_pct"] < 0


def test_breakout_uses_the_existing_20_day_high_as_single_reference_price():
    guide = _guide(
        "breakout",
        _state("20일 고점과 2% 이내", metric_key="distance_to_20d_high"),
        data=_data(current_price=96_000),
        technical={"high20": 102_000},
    )
    rule = guide["price_rule"]
    assert rule["kind"] == "ABOVE"
    assert rule["trigger_price"] == 102_000
    assert rule["reference_price"] == 102_000
    assert round(rule["gap_pct"], 2) == 6.25
    assert "2%" in rule["message"]


@pytest.mark.parametrize(
    ("strategy", "raw", "technical", "expected_kind"),
    [
        ("trend_following", "현재가가 20일선 위", {}, "ABOVE"),
        ("pullback", "주요 지지선과 4% 이내", {}, "RANGE"),
        ("breakout", "20일 고점과 2% 이내", {"high20": 102_000}, "ABOVE"),
        ("support_bounce", "지지선과 2.5% 이내", {}, "RANGE"),
        ("oversold_bounce", "지지선과 4% 이내", {}, "RANGE"),
        ("range_trading", "지지선과 3% 이내", {}, "RANGE"),
        ("momentum_continuation", "20일 고점과 5% 이내", {"high20": 102_000}, "RANGE"),
        ("volatility_squeeze", "20일 고점과 4% 이내", {"high20": 102_000}, "ABOVE"),
        ("ma20_rebound", "현재가가 20일선과 2.5% 이내", {}, "RANGE"),
        ("trend_recovery", "현재가가 20일선 위로 회복", {}, "ABOVE"),
    ],
)
def test_all_ten_strategies_map_their_real_price_condition(strategy, raw, technical, expected_kind):
    guide = _guide(strategy, _state(raw), technical=technical)
    assert guide["price_rule"]["kind"] == expected_kind
    assert guide["price_rule"]["basis"] == raw


def test_no_price_condition_does_not_invent_support_as_an_entry_reference():
    guide = _guide(
        "trend_following",
        _state("20일선 기울기가 0% 초과", metric_key="ma20_slope"),
        data=_data(support_price=96_000),
        technical={"support": 96_000},
    )
    assert guide["price_rule"]["kind"] == "UNAVAILABLE"
    assert guide["price_rule"]["reference_price"] is None
    assert guide["price_rule"]["trigger_price"] is None
    assert "임의" in guide["price_rule"]["message"]


def test_volume_and_risk_expose_stop_zone_invalidation_and_targets_separately():
    guide = _guide(
        "breakout",
        _state("거래량이 20일 평균의 1.5배 이상", metric_key="volume_ratio_20"),
        data=_data(volume_ratio_20=0.75),
        historical_verified=False,
        historical_status="NOT_RUN",
    )
    assert guide["volume_rule"]["required_ratio"] == 1.5
    assert guide["volume_rule"]["gap_pct"] == 100.0
    assert guide["risk"]["stop_zone_low"] == 94_000
    assert guide["risk"]["stop_zone_high"] == 95_000
    assert guide["risk"]["invalidation_price"] == 94_500
    assert guide["risk"]["target1_price"] == 108_000
    assert guide["risk"]["target2_price"] == 112_000
    assert guide["risk"]["needs_recheck"] is True


@pytest.mark.parametrize(
    ("reason", "risk_status", "expected_action"),
    [
        ("ENTRY_CANDIDATE", "READY", "ENTRY_CANDIDATE"),
        ("RISK_BLOCKED", "CAUTION", "RISK_BLOCKED"),
        ("ENTRY_CONDITIONS_MISSING", "READY", "WAIT"),
        ("ENTRY_CONDITIONS_MISSING", "CAUTION", "WAIT"),
    ],
)
def test_risk_decision_consistency_keeps_strategy_failure_as_primary_judgement(reason, risk_status, expected_action):
    risk = _risk(status=SimpleNamespace(value=risk_status))
    guide = _guide(
        "trend_following",
        _state("현재가가 20일선 위", status="PASS" if reason != "ENTRY_CONDITIONS_MISSING" else "FAIL"),
        risk=risk,
        current_reason=reason,
    )
    assert guide["action"]["status"] == expected_action
    if reason == "ENTRY_CONDITIONS_MISSING" and risk_status == "CAUTION":
        assert "부족한 전략 조건" in guide["action"]["detail"]


def test_current_candidate_remains_candidate_when_history_is_not_verified():
    guide = _guide(
        "trend_following",
        {"conditions": []},
        current_reason="ENTRY_CANDIDATE",
        historical_verified=False,
        historical_status="NOT_RUN",
    )
    assert guide["action"]["status"] == "ENTRY_CANDIDATE"
    assert "과거" in guide["action"]["detail"]
    assert guide["historical_verification"]["verified"] is False
    assert "검증 전" in guide["historical_verification"]["message"]


def test_historical_insufficient_is_not_rewritten_as_current_condition_failure():
    guide = _guide(
        "trend_following",
        _state("현재가가 20일선 위", status="PASS"),
        current_reason="ENTRY_CANDIDATE",
        historical_verified=True,
        historical_status="INSUFFICIENT",
    )
    assert guide["action"]["status"] == "ENTRY_CANDIDATE"
    assert "표본이 부족" in guide["action"]["detail"]
    assert "표본이 부족" in guide["historical_verification"]["message"]


def test_as_of_date_is_returned_without_frontend_inference():
    guide = _guide(
        "trend_following",
        _state("현재가가 20일선 위", status="PASS"),
        as_of_date="20260914",
    )
    assert guide["as_of_date"] == "20260914"


def test_pullback_reuses_entry_timing_rebound_confirmation_price_without_inventing_threshold():
    entry_timing = {
        "levels": {"rebound_confirmation": 99_000},
        "rules": {"price_rebound": "종가가 시가보다 높고 지지 기준 이상에서 마감"},
        "pending_checks": [
            {
                "key": "rebound_candle",
                "status": "WARN",
                "explanation": "가격 반등 신호가 아직 충분하지 않습니다.",
            }
        ],
    }
    guide = _guide(
        "pullback",
        _state("주요 지지선과 4% 이내"),
        data=_data(current_price=98_000),
        entry_timing=entry_timing,
    )
    rebound = guide["rebound_rule"]
    assert rebound["available"] is True
    assert rebound["trigger_price"] == 99_000
    assert round(rebound["gap_pct"], 2) == 1.02
    assert rebound["status"] == "WARN"
    assert "종가가 시가보다 높고" in rebound["basis"]


def test_non_pullback_strategy_does_not_reuse_pullback_rebound_level():
    guide = _guide(
        "breakout",
        _state("20일 고점과 2% 이내"),
        technical={"high20": 102_000},
        entry_timing={"levels": {"rebound_confirmation": 99_000}},
    )
    assert guide["rebound_rule"]["available"] is False
    assert guide["rebound_rule"]["trigger_price"] is None
