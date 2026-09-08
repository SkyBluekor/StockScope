from app.strategy import (
    MarketRegime,
    StrategyEngine,
    StrategyInput,
    StrategyName,
)


def test_pullback_ranks_high_for_uptrend_near_support():
    engine = StrategyEngine()
    data = StrategyInput(
        code="005930",
        market="KOSPI",
        current_price=72400,
        ma20=71000,
        ma60=68000,
        ma120=65000,
        ma20_slope_pct=1.2,
        rsi14=52,
        atr_pct=2.4,
        volume_ratio_20=0.95,
        distance_to_20d_high_pct=5.0,
        support_distance_pct=1.8,
        resistance_distance_pct=7.2,
        higher_high=True,
        higher_low=True,
        relative_strength_market_pct=2.0,
        relative_strength_sector_pct=1.0,
        market_regime=MarketRegime.TREND_UP,
    )

    result = engine.evaluate_all(data)

    assert result[0].strategy in {
        StrategyName.PULLBACK,
        StrategyName.TREND_FOLLOWING,
    }
    assert result[0].score >= 70


def test_breakout_ranks_high_near_high_with_volume():
    engine = StrategyEngine()
    data = StrategyInput(
        code="000660",
        market="KOSPI",
        current_price=200000,
        ma20=185000,
        ma60=170000,
        ma120=160000,
        ma20_slope_pct=2.0,
        rsi14=66,
        atr_pct=3.0,
        volume_ratio_20=2.1,
        distance_to_20d_high_pct=0.8,
        support_distance_pct=9,
        resistance_distance_pct=1,
        higher_high=True,
        higher_low=True,
        relative_strength_market_pct=4.5,
        relative_strength_sector_pct=2.1,
        market_regime=MarketRegime.TREND_UP,
    )

    result = engine.evaluate_all(data)

    top_two = {item.strategy for item in result[:2]}
    assert StrategyName.BREAKOUT in top_two
    breakout = next(item for item in result if item.strategy == StrategyName.BREAKOUT)
    assert breakout.score >= 80


def test_risk_gate_returns_no_trade():
    engine = StrategyEngine()
    data = StrategyInput(
        code="TEST",
        market="KOSDAQ",
        current_price=10000,
        event_risk=True,
        market_regime=MarketRegime.TREND_UP,
    )

    result = engine.evaluate_all(data)

    assert result[0].strategy == StrategyName.NO_TRADE
    assert result[0].score is None
    assert result[0].blockers
    assert len([item for item in result if item.strategy != StrategyName.NO_TRADE]) == 10


def test_low_information_can_produce_no_trade():
    engine = StrategyEngine()
    data = StrategyInput(
        code="TEST",
        market="KOSPI",
        current_price=10000,
        market_regime=MarketRegime.UNKNOWN,
    )

    result = engine.evaluate_all(data)

    assert result[0].strategy == StrategyName.NO_TRADE


def test_score_is_not_probability():
    engine = StrategyEngine()
    data = StrategyInput(
        code="TEST",
        market="KOSPI",
        current_price=10000,
        ma20=9000,
        ma60=8000,
        market_regime=MarketRegime.TREND_UP,
    )

    result = engine.evaluate_all(data)

    assert all("probability" not in item.to_dict() for item in result)


def test_evaluation_exposes_unmet_conditions():
    engine = StrategyEngine()
    data = StrategyInput(
        code="TEST",
        market="KOSPI",
        current_price=10000,
        ma20=11000,
        ma60=12000,
        rsi14=80,
        market_regime=MarketRegime.RANGE,
    )

    result = engine.evaluate_all(data)
    regular = next(item for item in result if item.strategy != StrategyName.NO_TRADE)

    assert isinstance(regular.unmet, list)
    assert len(regular.unmet) > 0
    assert "unmet" in regular.to_dict()


def test_strategy_evaluation_contains_response_guide():
    engine = StrategyEngine()
    data = StrategyInput(
        code="005930", market="KOSPI", current_price=10000, ma20=9800,
        ma20_slope_pct=1.0, rsi14=55, atr_pct=2.5, volume_ratio_20=1.1,
        support_distance_pct=2.0, resistance_distance_pct=6.0,
        support_price=9700, resistance_price=10600, higher_low=True,
        market_regime=MarketRegime.TREND_UP,
    )
    result = engine.evaluate_all(data)
    regular = next(item for item in result if item.strategy != StrategyName.NO_TRADE)
    assert regular.action_plan["new_entry"]
    assert regular.action_plan["holding"]
    assert regular.action_plan["avoid"]
    assert regular.action_plan["invalidation"]


def test_strategy_catalog_has_ten_real_strategies():
    engine = StrategyEngine()
    data = StrategyInput(code="TEST", market="KOSPI", current_price=10000, ma20=9900, market_regime=MarketRegime.RANGE)
    result = engine.evaluate_all(data)
    names = {item.strategy for item in result if item.strategy != StrategyName.NO_TRADE}
    assert len(names) == 10
    assert StrategyName.MOMENTUM_CONTINUATION in names
    assert StrategyName.VOLATILITY_SQUEEZE in names
    assert StrategyName.MA20_REBOUND in names
    assert StrategyName.TREND_RECOVERY in names


def test_extreme_manual_move_activates_risk_gate_but_keeps_strategy_reference():
    engine = StrategyEngine()
    data = StrategyInput(
        code="0011A0",
        market="KOSDAQ",
        current_price=11110,
        ma20=9000,
        rsi14=68,
        atr_pct=5.0,
        extreme_move=True,
        market_regime=MarketRegime.TREND_UP,
    )

    result = engine.evaluate_all(data)

    assert result[0].strategy == StrategyName.NO_TRADE
    assert result[0].score is None
    assert any("급격한 가격 변동" in reason for reason in result[0].blockers)
    assert any(item.strategy != StrategyName.NO_TRADE for item in result[1:])
