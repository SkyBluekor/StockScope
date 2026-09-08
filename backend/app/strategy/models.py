from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MarketRegime(StrEnum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    PANIC = "PANIC"
    UNKNOWN = "UNKNOWN"


class StrategyName(StrEnum):
    TREND_FOLLOWING = "trend_following"
    PULLBACK = "pullback"
    BREAKOUT = "breakout"
    SUPPORT_BOUNCE = "support_bounce"
    OVERSOLD_BOUNCE = "oversold_bounce"
    RANGE_TRADING = "range_trading"
    MOMENTUM_CONTINUATION = "momentum_continuation"
    VOLATILITY_SQUEEZE = "volatility_squeeze"
    MA20_REBOUND = "ma20_rebound"
    TREND_RECOVERY = "trend_recovery"
    NO_TRADE = "no_trade"


@dataclass(slots=True)
class StrategyInput:
    code: str
    market: str

    current_price: float

    ma20: float | None = None
    ma60: float | None = None
    ma120: float | None = None
    ma20_slope_pct: float | None = None

    rsi14: float | None = None
    atr_pct: float | None = None

    volume_ratio_20: float | None = None
    distance_to_20d_high_pct: float | None = None

    support_distance_pct: float | None = None
    resistance_distance_pct: float | None = None
    support_price: float | None = None
    resistance_price: float | None = None

    higher_high: bool | None = None
    higher_low: bool | None = None

    relative_strength_market_pct: float | None = None
    relative_strength_sector_pct: float | None = None

    market_regime: MarketRegime = MarketRegime.UNKNOWN

    event_risk: bool = False
    liquidity_ok: bool = True
    tradable: bool = True
    extreme_move: bool = False
    data_stale: bool = False

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StrategyEvaluation:
    strategy: StrategyName
    score: int | None
    eligible: bool
    passed: int
    total: int
    reasons: list[str]
    unmet: list[str]
    blockers: list[str]
    note: str
    action_plan: dict[str, Any] = field(default_factory=dict)

    @property
    def suitability(self) -> str:
        if self.strategy == StrategyName.NO_TRADE or self.score is None:
            return "보류"
        if not self.eligible:
            return "부적합"
        if self.score >= 85:
            return "매우 높음"
        if self.score >= 70:
            return "높음"
        if self.score >= 55:
            return "보통"
        return "낮음"

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "score": self.score,
            "suitability": self.suitability,
            "eligible": self.eligible,
            "passed": self.passed,
            "total": self.total,
            "reasons": self.reasons,
            "unmet": self.unmet,
            "blockers": self.blockers,
            "note": self.note,
            "action_plan": self.action_plan,
        }
