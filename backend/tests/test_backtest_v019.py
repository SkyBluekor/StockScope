from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestConfig
from app.risk.models import RiskPlan, RiskPlanStatus
from app.strategy.context import build_strategy_input
from app.strategy.models import MarketRegime, StrategyEvaluation, StrategyInput, StrategyName


def make_rows(count: int = 70, start: date = date(2026, 1, 2)) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current = start
    while len(rows) < count:
        if current.weekday() < 5:
            price = 100.0 + len(rows) * 0.1
            rows.append({
                "date": current.strftime("%Y%m%d"),
                "open": price,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price + 0.2,
                "volume": 1_000_000,
                "trade_value": 2_000_000_000,
            })
        current += timedelta(days=1)
    return rows


def make_index_rows(stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"date": row["date"], "close": 2500 + i, "change_rate": 0.2}
        for i, row in enumerate(stock_rows)
    ]


class FakeTechnical:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    def analyze(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        self.seen.append((history[0]["date"], history[-1]["date"]))
        price = float(history[-1]["close"])
        return {
            "current_price": price,
            "ma20": price - 1,
            "ma60": price - 2,
            "ma120": None,
            "ma20_slope_pct": 0.5,
            "rsi14": 50.0,
            "atr_pct": 2.0,
            "volume_ratio_20": 1.0,
            "distance_to_20d_high_pct": 4.0,
            "support": price - 1,
            "resistance": price + 10,
            "support_distance_pct": 1.0,
            "resistance_distance_pct": 10.0,
            "higher_high": True,
            "higher_low": True,
        }


class FakeRelative:
    def analyze(self, *args, **kwargs) -> dict[str, Any]:
        return {"primary_period": 20, "primary_excess_pct": 2.0}


class FakeStrategy:
    def evaluate_all(self, data: StrategyInput) -> list[StrategyEvaluation]:
        return [
            StrategyEvaluation(
                strategy=StrategyName.PULLBACK,
                score=82,
                eligible=True,
                passed=7,
                total=9,
                reasons=[],
                unmet=[],
                blockers=[],
                note="",
            )
        ]


class FakePullback:
    def __init__(self, passed: int = 5, state: str = "REBOUND_CONFIRMED") -> None:
        self.passed = passed
        self.state = state
        self.max_history_dates: list[str] = []

    def analyze(self, *, history, **kwargs) -> dict[str, Any]:
        self.max_history_dates.append(history[-1]["date"])
        return {
            "state": self.state,
            "passed": self.passed,
            "total_checks": 7,
            "entry_timing": {
                "state": self.state,
                "progress": {"passed": self.passed, "total": 7},
            },
        }


class FakeRisk:
    def build_plan(self, *, data: StrategyInput, **kwargs) -> RiskPlan:
        entry = float(data.current_price)
        return RiskPlan(
            strategy="pullback",
            status=RiskPlanStatus.READY,
            reference_only=False,
            basis="BACKTEST_NEXT_OPEN",
            entry_price=entry,
            structural_anchor=entry * 0.98,
            structural_anchor_label="테스트",
            invalidation_price=entry * 0.95,
            stop_zone_low=entry * 0.94,
            stop_zone_high=entry * 0.96,
            target1_price=entry * 1.05,
            target1_basis="테스트",
            target2_price=entry * 1.10,
            target2_basis="테스트",
            risk_pct=5.0,
            reward1_pct=5.0,
            reward2_pct=10.0,
            rr1=1.0,
            rr2=2.0,
            structure_rating="양호",
            summary="테스트",
        )


def config_for(rows: list[dict[str, Any]], **kwargs) -> BacktestConfig:
    return BacktestConfig(
        code="005930",
        market="KOSPI",
        start_date=date.fromisoformat(f"{rows[59]['date'][:4]}-{rows[59]['date'][4:6]}-{rows[59]['date'][6:]}").isoformat(),
        end_date=date.fromisoformat(f"{rows[-1]['date'][:4]}-{rows[-1]['date'][4:6]}-{rows[-1]['date'][6:]}").isoformat(),
        initial_capital=10_000_000,
        max_holding_days=kwargs.get("max_holding_days", 20),
        round_trip_cost_pct=kwargs.get("round_trip_cost_pct", 0.0),
    )


def make_engine(*, passed: int = 5, state: str = "REBOUND_CONFIRMED") -> tuple[BacktestEngine, FakeTechnical, FakePullback]:
    technical = FakeTechnical()
    pullback = FakePullback(passed=passed, state=state)
    engine = BacktestEngine(
        technical=technical,
        strategy=FakeStrategy(),
        risk=FakeRisk(),
        pullback=pullback,
        relative_strength=FakeRelative(),
    )
    return engine, technical, pullback


def test_signal_calculation_never_receives_future_rows() -> None:
    rows = make_rows(66)
    engine, technical, pullback = make_engine()
    result = engine.run(stock_rows=rows, index_rows=make_index_rows(rows), config=config_for(rows))

    assert result["diagnostics"]["evaluated_signal_days"] > 0
    assert len(technical.seen) == len(pullback.max_history_dates)
    expected_signal_dates = [row["date"] for row in rows[59:]]
    assert [last for _, last in technical.seen] == expected_signal_dates
    assert pullback.max_history_dates == expected_signal_dates
    for (_, technical_last), pullback_last in zip(technical.seen, pullback.max_history_dates, strict=True):
        assert technical_last == pullback_last


def test_next_day_open_is_used_and_cost_is_subtracted() -> None:
    rows = make_rows(66)
    # Make first entry day hit target 1 so the trade closes immediately.
    rows[60]["high"] = rows[60]["open"] * 1.10
    engine, _, _ = make_engine()
    result = engine.run(
        stock_rows=rows,
        index_rows=make_index_rows(rows),
        config=config_for(rows, round_trip_cost_pct=0.4),
    )
    trade = result["trades"][0]
    assert trade["entry_price"] == pytest.approx(rows[60]["open"])
    assert trade["exit_reason"] == "TARGET_1"
    assert trade["net_return_pct"] == pytest.approx(trade["gross_return_pct"] - 0.4)


def test_same_day_stop_and_target_uses_conservative_stop_priority() -> None:
    rows = make_rows(66)
    entry = float(rows[60]["open"])
    rows[60]["low"] = entry * 0.90
    rows[60]["high"] = entry * 1.10
    engine, _, _ = make_engine()
    result = engine.run(stock_rows=rows, index_rows=make_index_rows(rows), config=config_for(rows))
    trade = result["trades"][0]
    assert trade["exit_reason"] == "STOP_SAME_DAY_PRIORITY"
    assert trade["exit_price"] == pytest.approx(entry * 0.95)


def test_user_selected_max_holding_period_controls_time_exit() -> None:
    rows = make_rows(70)
    engine, _, _ = make_engine()
    result = engine.run(
        stock_rows=rows,
        index_rows=make_index_rows(rows),
        config=config_for(rows, max_holding_days=5),
    )
    trade = result["trades"][0]
    assert trade["holding_days"] == 5
    assert trade["exit_reason"] == "TIME_EXIT"


def test_entry_timing_research_is_separate_from_actual_rule() -> None:
    rows = make_rows(66)
    engine, _, _ = make_engine(passed=3, state="SUPPORT_TESTING")
    result = engine.run(stock_rows=rows, index_rows=make_index_rows(rows), config=config_for(rows))
    assert result["summary"]["trades"] == 0
    three_of_seven = next(row for row in result["entry_timing_research"] if row["entry_timing"] == "3/7")
    assert three_of_seven["signals"] > 0


def test_shared_strategy_input_builder_matches_expected_fields() -> None:
    technical = {
        "ma60": 90.0,
        "ma120": 80.0,
        "ma20_slope_pct": 0.4,
        "support": 95.0,
        "resistance": 110.0,
        "higher_high": True,
        "higher_low": True,
    }
    data = build_strategy_input(
        code="005930",
        market="kospi",
        technical=technical,
        regime=MarketRegime.RANGE,
        liquidity_ok=True,
        price=100.0,
        ma20=98.0,
        rsi14=50.0,
        atr_pct=2.0,
        volume_ratio_20=1.0,
        distance_to_high=3.0,
        support_distance=5.0,
        resistance_distance=10.0,
        extreme_move=False,
        data_stale=False,
        source="KRX_EOD",
        index_rate=0.2,
        history_points=60,
    )
    assert data.market == "KOSPI"
    assert data.support_price == 95.0
    assert data.resistance_price == 110.0
    assert data.metadata["history_points"] == 60


def test_overall_mdd_uses_open_position_daily_mark_to_market() -> None:
    rows = make_rows(66)
    entry = float(rows[60]["open"])
    # Keep Stop at 95% untouched, but create a deep close drawdown above Stop.
    rows[60]["low"] = entry * 0.96
    rows[60]["close"] = entry * 0.965
    rows[60]["high"] = entry * 1.01
    rows[61]["high"] = entry * 1.10
    engine, _, _ = make_engine()
    result = engine.run(stock_rows=rows, index_rows=make_index_rows(rows), config=config_for(rows))

    assert result["summary"]["max_drawdown_basis"] == "DAILY_CLOSE_MARK_TO_MARKET"
    assert result["summary"]["max_drawdown_pct"] < 0
    assert result["summary"]["max_drawdown_pct"] <= -3.0


def test_real_stockscope_engines_can_run_historical_pullback_snapshot() -> None:
    rows: list[dict[str, Any]] = []
    current = date(2025, 1, 2)
    i = 0
    while len(rows) < 90:
        if current.weekday() < 5:
            base = 100.0 + i * 0.35
            dip = -2.0 if i % 15 in (10, 11) else (-1.0 if i % 15 == 12 else 0.0)
            close = base + dip
            rows.append({
                "date": current.strftime("%Y%m%d"),
                "open": close - 0.2,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000 + (i % 10) * 20_000,
                "trade_value": 2_000_000_000,
            })
            i += 1
        current += timedelta(days=1)
    index_rows = [
        {"date": row["date"], "close": 2500.0 + j * 2.0, "change_rate": 0.2}
        for j, row in enumerate(rows)
    ]
    cfg = config_for(rows)
    result = BacktestEngine().run(stock_rows=rows, index_rows=index_rows, config=cfg)

    assert result["version"] == "0.19"
    assert result["strategy"] == "pullback"
    assert result["diagnostics"]["evaluated_signal_days"] > 0
    assert len(result["entry_timing_research"]) == 5
