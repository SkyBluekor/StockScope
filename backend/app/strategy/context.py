from __future__ import annotations

from typing import Any

from app.strategy.models import MarketRegime, StrategyInput


def regime_from_index(change_rate: float | None) -> MarketRegime:
    """Classify the market regime from the KRX representative-index daily change.

    This is shared by the live strategy analysis and historical backtests so the
    same market-regime rule is applied in both paths.
    """
    if change_rate is None:
        return MarketRegime.UNKNOWN
    if change_rate >= 1.0:
        return MarketRegime.TREND_UP
    if change_rate <= -1.0:
        return MarketRegime.TREND_DOWN
    return MarketRegime.RANGE


def build_strategy_input(
    *,
    code: str,
    market: str,
    technical: dict[str, Any],
    regime: MarketRegime,
    liquidity_ok: bool,
    price: float,
    ma20: float | None,
    rsi14: float | None,
    atr_pct: float | None,
    volume_ratio_20: float | None,
    distance_to_high: float | None,
    support_distance: float | None,
    resistance_distance: float | None,
    extreme_move: bool,
    data_stale: bool,
    source: str,
    index_rate: float | None,
    history_points: int,
    event_risk: bool = False,
    relative_strength_market_pct: float | None = None,
    relative_strength_sector_pct: float | None = None,
    relative_strength_context: dict[str, Any] | None = None,
    sector_relative_strength_context: dict[str, Any] | None = None,
) -> StrategyInput:
    """Build the canonical StrategyInput used by both live analysis and backtest."""
    return StrategyInput(
        code=code,
        market=market.upper(),
        current_price=price,
        ma20=ma20,
        ma60=technical.get("ma60"),
        ma120=technical.get("ma120"),
        ma20_slope_pct=technical.get("ma20_slope_pct"),
        rsi14=rsi14,
        atr_pct=atr_pct,
        volume_ratio_20=volume_ratio_20,
        distance_to_20d_high_pct=distance_to_high,
        support_distance_pct=support_distance,
        resistance_distance_pct=resistance_distance,
        support_price=technical.get("support"),
        resistance_price=technical.get("resistance"),
        higher_high=technical.get("higher_high"),
        higher_low=technical.get("higher_low"),
        relative_strength_market_pct=relative_strength_market_pct,
        relative_strength_sector_pct=relative_strength_sector_pct,
        market_regime=regime,
        event_risk=event_risk,
        liquidity_ok=liquidity_ok,
        tradable=True,
        extreme_move=extreme_move,
        data_stale=data_stale,
        metadata={
            "market_index_change_rate": index_rate,
            "history_points": history_points,
            "price_source": source,
            "relative_strength": relative_strength_context,
            "sector_relative_strength": sector_relative_strength_context,
        },
    )
