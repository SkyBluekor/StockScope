from __future__ import annotations

from app.backtest.policy_lab import (
    POLICY_BLOCK_ALL_CAUTION,
    POLICY_BLOCK_WIDE_STOP,
    POLICY_CURRENT,
    POLICY_NEAREST_VALID_ANCHOR,
    build_risk_policy_comparison,
)


def _metrics(*, trades: int, expectancy: float, total: float, mdd: float) -> dict:
    return {
        "trades": trades,
        "wins": max(0, trades // 2),
        "losses": trades - max(0, trades // 2),
        "win_rate_pct": 50.0 if trades else None,
        "average_gross_return_pct": expectancy,
        "average_net_return_pct": expectancy,
        "median_net_return_pct": expectancy,
        "average_win_pct": 2.0,
        "average_loss_pct": -2.0,
        "expectancy_pct": expectancy,
        "profit_factor": 1.0,
        "average_holding_days": 5.0,
        "max_consecutive_losses": 2,
        "max_drawdown_pct": mdd,
        "initial_capital": 10_000_000.0,
        "final_capital": 10_000_000.0 * (1 + total / 100),
        "total_net_return_pct": total,
    }


def _scenario(
    policy_id: str,
    *,
    trades: int,
    expectancy: float,
    total: float,
    mdd: float,
    blocked: int = 0,
    caution: int = 0,
    wide: int = 0,
    changed: int = 0,
) -> dict:
    return {
        "id": policy_id,
        "metrics": _metrics(trades=trades, expectancy=expectancy, total=total, mdd=mdd),
        "eligible_attempts": trades + blocked,
        "blocked_by_policy": blocked,
        "blocked_reasons": {},
        "unusable_risk_plan": 0,
        "caution_trades": caution,
        "wide_stop_trades": wide,
        "average_initial_stop_distance_pct": 4.0,
        "anchor_changed_signals": changed,
        "anchor_changed_trades": changed,
    }


def test_targeted_wide_stop_policy_is_preferred_over_aggressive_caution_block() -> None:
    result = build_risk_policy_comparison([
        _scenario(POLICY_CURRENT, trades=13, expectancy=-1.67, total=-21.25, mdd=-22.27, caution=9, wide=1),
        # Highest raw result, but it removes most trades and is deliberately too broad.
        _scenario(POLICY_BLOCK_ALL_CAUTION, trades=4, expectancy=3.0, total=12.0, mdd=-5.0, blocked=9),
        _scenario(POLICY_BLOCK_WIDE_STOP, trades=12, expectancy=-0.15, total=-1.8, mdd=-8.0, blocked=1),
        _scenario(POLICY_NEAREST_VALID_ANCHOR, trades=13, expectancy=-0.9, total=-11.0, mdd=-12.0, changed=3),
    ])

    assert result["next_validation_candidate"]["policy_id"] == POLICY_BLOCK_WIDE_STOP
    all_caution = next(row for row in result["scenarios"] if row["id"] == POLICY_BLOCK_ALL_CAUTION)
    assert all_caution["interpretation"]["status"] == "TOO_AGGRESSIVE"
    assert "성과가 가장 높아서" in result["decision"]


def test_wide_stop_filter_is_not_recommended_when_it_does_not_improve_the_problem() -> None:
    result = build_risk_policy_comparison([
        _scenario(POLICY_CURRENT, trades=12, expectancy=0.4, total=4.5, mdd=-7.0, caution=3, wide=1),
        _scenario(POLICY_BLOCK_ALL_CAUTION, trades=9, expectancy=0.2, total=1.8, mdd=-8.0, blocked=3),
        _scenario(POLICY_BLOCK_WIDE_STOP, trades=11, expectancy=0.1, total=1.0, mdd=-9.0, blocked=1),
        _scenario(POLICY_NEAREST_VALID_ANCHOR, trades=12, expectancy=0.2, total=2.0, mdd=-8.0, changed=2),
    ])

    assert result["next_validation_candidate"] is None
    wide = next(row for row in result["scenarios"] if row["id"] == POLICY_BLOCK_WIDE_STOP)
    assert wide["interpretation"]["status"] == "PROBLEM_REMOVED_BUT_NO_GAIN"


def test_nearest_anchor_can_be_next_candidate_when_wide_filter_does_not_help() -> None:
    result = build_risk_policy_comparison([
        _scenario(POLICY_CURRENT, trades=15, expectancy=-0.8, total=-11.0, mdd=-14.0, caution=6, wide=1),
        _scenario(POLICY_BLOCK_ALL_CAUTION, trades=9, expectancy=-0.5, total=-5.0, mdd=-10.0, blocked=6),
        _scenario(POLICY_BLOCK_WIDE_STOP, trades=14, expectancy=-0.9, total=-12.0, mdd=-15.0, blocked=1),
        _scenario(POLICY_NEAREST_VALID_ANCHOR, trades=15, expectancy=0.2, total=3.0, mdd=-7.0, changed=4),
    ])

    assert result["next_validation_candidate"]["policy_id"] == POLICY_NEAREST_VALID_ANCHOR
    nearest = next(row for row in result["scenarios"] if row["id"] == POLICY_NEAREST_VALID_ANCHOR)
    assert nearest["interpretation"]["status"] == "DIRECT_CANDIDATE"

from dataclasses import replace
from typing import Any

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestConfig
from app.risk.engine import RiskEngine
from app.risk.models import RiskPlan, RiskPlanStatus
from app.strategy.context import build_strategy_input
from app.strategy.models import MarketRegime, StrategyInput


class WideCautionRisk:
    def build_plan(self, *, data: StrategyInput, **_: Any) -> RiskPlan:
        entry = float(data.current_price)
        anchor = entry * 0.85
        atr_value = entry * 0.04
        stop = anchor - atr_value * 0.5
        return RiskPlan(
            strategy="pullback",
            status=RiskPlanStatus.CAUTION,
            reference_only=False,
            basis="BACKTEST_NEXT_OPEN",
            entry_price=entry,
            structural_anchor=anchor,
            structural_anchor_label="주요 지지 후보",
            invalidation_price=stop,
            stop_zone_low=stop - 0.5,
            stop_zone_high=stop + 0.5,
            target1_price=entry * 1.05,
            target1_basis="테스트 목표",
            target2_price=entry * 1.10,
            target2_basis="테스트 목표",
            risk_pct=(entry - stop) / entry * 100.0,
            reward1_pct=5.0,
            reward2_pct=10.0,
            rr1=0.29,
            rr2=0.59,
            structure_rating="불리함",
            summary="손절 폭이 넓어 주의가 필요합니다.",
            warnings=["손절 폭이 넓습니다."],
            reasons=["주요 지지 후보를 사용했습니다."],
        )


def _policy_config() -> BacktestConfig:
    return BacktestConfig(
        code="005930",
        market="KOSPI",
        start_date="2026-06-25",
        end_date="2026-07-10",
        round_trip_cost_pct=0.0,
        max_holding_days=5,
        minimum_strategy_score=55,
    )


def _policy_strategy_input() -> StrategyInput:
    technical = {
        "ma60": 96.0,
        "ma120": 90.0,
        "ma20_slope_pct": 0.4,
        "support": 85.0,
        "resistance": 110.0,
        "higher_high": True,
        "higher_low": True,
    }
    return build_strategy_input(
        code="005930",
        market="KOSPI",
        technical=technical,
        regime=MarketRegime.TREND_UP,
        liquidity_ok=True,
        price=100.0,
        ma20=98.0,
        rsi14=55.0,
        atr_pct=4.0,
        volume_ratio_20=1.2,
        distance_to_high=3.0,
        support_distance=15.0,
        resistance_distance=10.0,
        extreme_move=False,
        data_stale=False,
        source="KRX_EOD",
        index_rate=0.5,
        history_points=60,
    )


def _policy_signal() -> dict[str, Any]:
    base = _policy_strategy_input()
    return {
        "signal_index": 0,
        "signal_date": "20260625",
        "technical": {
            "current_price": 100.0,
            "ma20": 98.0,
            "support": 85.0,
            "low20": 84.0,
            "high20": 110.0,
        },
        "strategy_input": base,
        "strategy_score": 95,
        "strategy_eligible": True,
        "risk_gate_active": False,
        "risk_gate_reasons": [],
        "entry_timing_state": "REBOUND_CONFIRMED",
        "entry_timing_passed": 6,
        "entry_timing_total": 7,
        "market_regime": "TREND_UP",
        "relative_strength_market_pct": 1.5,
        "audit_context": {
            "stock_history_start_date": "20260401",
            "stock_history_end_date": "20260625",
            "index_history_end_date": "20260625",
            "market_regime_source_date": "20260625",
            "future_data_used": False,
            "signal_close": 100.0,
            "signal_support": 85.0,
            "signal_ma20": 98.0,
            "signal_atr_pct": 4.0,
            "technical_low20": 84.0,
        },
    }


def _policy_rows() -> list[dict[str, Any]]:
    return [
        {"date": "20260625", "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        {"date": "20260626", "open": 100.0, "high": 103.0, "low": 90.0, "close": 92.0},
        {"date": "20260629", "open": 91.0, "high": 93.0, "low": 82.0, "close": 84.0},
        {"date": "20260630", "open": 84.0, "high": 86.0, "low": 83.0, "close": 85.0},
    ]


def test_policy_filters_are_research_only_and_do_not_change_current_execution() -> None:
    engine = BacktestEngine(risk=WideCautionRisk())
    current_meta: dict[str, Any] = {}
    current_trade, _ = engine._simulate_trade(  # noqa: SLF001
        signal=_policy_signal(),
        stock_rows=_policy_rows(),
        config=_policy_config(),
        research_only=False,
        risk_policy=POLICY_CURRENT,
        policy_meta=current_meta,
    )
    assert current_trade is not None
    assert current_trade.stop_price == pytest.approx(83.0)
    assert current_meta["outcome"] == "EXECUTED"

    caution_meta: dict[str, Any] = {}
    caution_trade, _ = engine._simulate_trade(  # noqa: SLF001
        signal=_policy_signal(),
        stock_rows=_policy_rows(),
        config=_policy_config(),
        research_only=True,
        risk_policy=POLICY_BLOCK_ALL_CAUTION,
        policy_meta=caution_meta,
    )
    assert caution_trade is None
    assert caution_meta["outcome"] == "BLOCKED_POLICY"
    assert caution_meta["blocked_reason"] == "CAUTION"

    wide_meta: dict[str, Any] = {}
    wide_trade, _ = engine._simulate_trade(  # noqa: SLF001
        signal=_policy_signal(),
        stock_rows=_policy_rows(),
        config=_policy_config(),
        research_only=True,
        risk_policy=POLICY_BLOCK_WIDE_STOP,
        policy_meta=wide_meta,
    )
    assert wide_trade is None
    assert wide_meta["blocked_reason"] == "WIDE_STOP"


def test_nearest_anchor_experiment_uses_ma20_when_it_is_closer_than_support() -> None:
    engine = BacktestEngine(risk=RiskEngine())
    meta: dict[str, Any] = {}
    trade, _ = engine._simulate_trade(  # noqa: SLF001
        signal=_policy_signal(),
        stock_rows=_policy_rows(),
        config=_policy_config(),
        research_only=True,
        risk_policy=POLICY_NEAREST_VALID_ANCHOR,
        policy_meta=meta,
    )

    assert trade is not None
    assert meta["anchor_changed"] is True
    assert meta["baseline_anchor"] == pytest.approx(85.0)
    assert meta["selected_anchor"] == pytest.approx(98.0)
    assert meta["selected_anchor_label"] == "20일 이동평균선"
    # Entry 100, ATR 4%, Pullback buffer 0.5 -> MA20 98 - 2 = 96.
    assert trade.stop_price == pytest.approx(96.0)
    assert meta["selected_stop_distance_pct"] == pytest.approx(4.0)


def test_policy_scenario_counts_blocked_wide_stop_instead_of_hiding_it() -> None:
    engine = BacktestEngine(risk=WideCautionRisk())
    current = engine._simulate_risk_policy_scenario(  # noqa: SLF001
        signals=[_policy_signal()],
        stock_rows=_policy_rows(),
        config=_policy_config(),
        risk_policy=POLICY_CURRENT,
    )
    filtered = engine._simulate_risk_policy_scenario(  # noqa: SLF001
        signals=[_policy_signal()],
        stock_rows=_policy_rows(),
        config=_policy_config(),
        risk_policy=POLICY_BLOCK_WIDE_STOP,
    )

    assert current["metrics"]["trades"] == 1
    assert current["wide_stop_trades"] == 1
    assert filtered["metrics"]["trades"] == 0
    assert filtered["blocked_by_policy"] == 1
    assert filtered["blocked_reasons"]["WIDE_STOP"] == 1

from app.backtest.interpreter import build_problem_solver


def test_problem_solver_turns_policy_comparison_into_next_action() -> None:
    comparison = build_risk_policy_comparison([
        _scenario(POLICY_CURRENT, trades=13, expectancy=-1.67, total=-21.25, mdd=-22.27, caution=9, wide=1),
        _scenario(POLICY_BLOCK_ALL_CAUTION, trades=4, expectancy=2.0, total=8.0, mdd=-5.0, blocked=9),
        _scenario(POLICY_BLOCK_WIDE_STOP, trades=12, expectancy=-0.1, total=-1.2, mdd=-8.0, blocked=1),
        _scenario(POLICY_NEAREST_VALID_ANCHOR, trades=13, expectancy=-0.8, total=-10.0, mdd=-12.0, changed=3),
    ])
    result = {
        "summary": _metrics(trades=13, expectancy=-1.67, total=-21.25, mdd=-22.27),
        "entry_timing_research": [],
        "market_regime_performance": [],
        "trades": [
            {"exit_reason": "STOP", "entry_price": 100.0, "stop_price": 95.0},
            {"exit_reason": "STOP", "entry_price": 100.0, "stop_price": 94.0},
            {"exit_reason": "STOP_GAP", "entry_price": 100.0, "stop_price": 93.0},
            {"exit_reason": "STOP", "entry_price": 100.0, "stop_price": 95.0},
            {"exit_reason": "STOP", "entry_price": 100.0, "stop_price": 95.0},
            {"exit_reason": "STOP", "entry_price": 100.0, "stop_price": 95.0},
            {"exit_reason": "STOP", "entry_price": 100.0, "stop_price": 95.0},
            {"exit_reason": "STOP", "entry_price": 100.0, "stop_price": 95.0},
            {"exit_reason": "TARGET_1", "entry_price": 100.0, "stop_price": 95.0},
            {"exit_reason": "TARGET_1", "entry_price": 100.0, "stop_price": 95.0},
            {"exit_reason": "TARGET_1", "entry_price": 100.0, "stop_price": 95.0},
            {"exit_reason": "TARGET_1", "entry_price": 100.0, "stop_price": 95.0},
            {"exit_reason": "TARGET_1", "entry_price": 100.0, "stop_price": 95.0},
        ],
        "risk_policy_comparison": comparison,
    }
    solver = build_problem_solver(result, _policy_config())
    problem = next(item for item in solver["problems"] if item["id"] == "RISK_POLICY_CANDIDATE")
    action = next(item for item in solver["next_actions"] if item["id"] == "VIEW_RISK_POLICY")
    assert "실제 비교" in problem["title"]
    assert "과도한 손절만 제외" in problem["evidence"]
    assert action["section"] == "risk-policy-analysis"
