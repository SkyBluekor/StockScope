from app.strategy.engine import StrategyEngine
from app.strategy.models import MarketRegime, StrategyInput, StrategyName


def _breakout_input(sector_relative: float | None) -> StrategyInput:
    return StrategyInput(
        code="005930",
        market="KOSPI",
        current_price=100.0,
        ma20=90.0,
        ma60=80.0,
        ma120=70.0,
        ma20_slope_pct=1.0,
        rsi14=60.0,
        atr_pct=2.0,
        volume_ratio_20=2.0,
        distance_to_20d_high_pct=1.0,
        support_distance_pct=4.0,
        resistance_distance_pct=1.0,
        higher_high=True,
        higher_low=True,
        relative_strength_market_pct=4.0,
        relative_strength_sector_pct=sector_relative,
        market_regime=MarketRegime.TREND_UP,
    )


def _find_breakout(rows):
    return next(row for row in rows if row.strategy == StrategyName.BREAKOUT)


def test_weak_sector_relative_strength_reduces_breakout_suitability():
    engine = StrategyEngine()
    strong = _find_breakout(engine.evaluate_all(_breakout_input(4.0)))
    weak = _find_breakout(engine.evaluate_all(_breakout_input(-4.0)))
    assert strong.score is not None and weak.score is not None
    assert strong.score > weak.score


def test_missing_sector_data_preserves_market_only_baseline_condition():
    engine = StrategyEngine()
    missing = _find_breakout(engine.evaluate_all(_breakout_input(None)))
    strong = _find_breakout(engine.evaluate_all(_breakout_input(4.0)))
    assert missing.score == strong.score
