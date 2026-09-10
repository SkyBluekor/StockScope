from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BacktestConfig:
    code: str
    market: str
    start_date: str
    end_date: str
    initial_capital: float = 10_000_000.0
    max_holding_days: int = 20
    round_trip_cost_pct: float = 0.0
    minimum_strategy_score: int = 55


@dataclass(slots=True)
class BacktestTrade:
    signal_date: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    exit_reason: str
    holding_days: int
    strategy_score: int
    entry_timing_passed: int
    entry_timing_total: int
    entry_timing_state: str
    market_regime: str
    stop_price: float
    target1_price: float
    target2_price: float | None
    gross_return_pct: float
    net_return_pct: float
    risk_plan_status: str
    research_only: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_date": self.signal_date,
            "entry_date": self.entry_date,
            "entry_price": round(self.entry_price, 4),
            "exit_date": self.exit_date,
            "exit_price": round(self.exit_price, 4),
            "exit_reason": self.exit_reason,
            "holding_days": self.holding_days,
            "strategy_score": self.strategy_score,
            "entry_timing_passed": self.entry_timing_passed,
            "entry_timing_total": self.entry_timing_total,
            "entry_timing_state": self.entry_timing_state,
            "market_regime": self.market_regime,
            "stop_price": round(self.stop_price, 4),
            "target1_price": round(self.target1_price, 4),
            "target2_price": None if self.target2_price is None else round(self.target2_price, 4),
            "gross_return_pct": round(self.gross_return_pct, 4),
            "net_return_pct": round(self.net_return_pct, 4),
            "risk_plan_status": self.risk_plan_status,
            "research_only": self.research_only,
            "metadata": self.metadata,
        }
