from app.risk import RiskEngine
from app.strategy.models import MarketRegime, StrategyInput, StrategyName


def make_input(**overrides):
    payload = dict(
        code="005930",
        market="KOSPI",
        current_price=100000.0,
        ma20=97000.0,
        rsi14=55.0,
        atr_pct=3.0,
        volume_ratio_20=1.0,
        support_distance_pct=3.0,
        resistance_distance_pct=7.0,
        support_price=97000.0,
        resistance_price=107000.0,
        higher_high=True,
        higher_low=True,
        market_regime=MarketRegime.TREND_UP,
    )
    payload.update(overrides)
    return StrategyInput(**payload)


def test_pullback_risk_plan_has_invalidation_and_rr():
    plan = RiskEngine().build_plan(
        data=make_input(),
        strategy=StrategyName.PULLBACK,
        technical={"low20": 93000.0, "high20": 106000.0},
        risk_gate_active=False,
        risk_gate_reasons=[],
        basis="CONFIRMED_EOD",
    )

    assert plan.invalidation_price is not None
    assert plan.invalidation_price < 97000
    assert plan.stop_zone_low < plan.stop_zone_high < 100000
    assert plan.target1_price > 100000
    assert plan.target2_price > plan.target1_price
    assert plan.rr1 is not None and plan.rr1 > 0
    assert plan.rr2 is not None and plan.rr2 >= 2.0
    assert plan.reference_only is False


def test_risk_gate_turns_plan_into_reference_only_hold():
    plan = RiskEngine().build_plan(
        data=make_input(extreme_move=True, data_stale=True),
        strategy=StrategyName.PULLBACK,
        technical={"low20": 93000.0, "high20": 106000.0},
        risk_gate_active=True,
        risk_gate_reasons=["확정 종가 대비 급격한 가격 변동"],
        basis="MANUAL_REFERENCE",
    )

    assert plan.status.value == "HOLD"
    assert plan.reference_only is True
    assert any("급격" in warning for warning in plan.warnings)


def test_missing_atr_does_not_invent_stop_price():
    plan = RiskEngine().build_plan(
        data=make_input(atr_pct=None),
        strategy=StrategyName.PULLBACK,
        technical={"low20": 93000.0, "high20": 106000.0},
        risk_gate_active=False,
        risk_gate_reasons=[],
        basis="CONFIRMED_EOD",
    )

    assert plan.status.value == "UNAVAILABLE"
    assert plan.invalidation_price is None
    assert plan.target1_price is None
