from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.backtest.audit import build_accuracy_audit
from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestConfig
from app.risk.models import RiskPlan, RiskPlanStatus
from app.strategy.context import build_strategy_input
from app.strategy.models import MarketRegime, StrategyInput


class WideCautionRisk:
    def build_plan(self, *, data: StrategyInput, **_: Any) -> RiskPlan:
        entry = float(data.current_price)
        # Exact diagnostic shape: structural support is far below the next-open
        # entry and a 0.5 ATR buffer is subtracted from that support.
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
            warnings=["현재 가격에서 무효화 기준까지 거리가 12% 이상으로 넓어 신규 진입 리스크가 큽니다."],
            reasons=["주요 지지 후보를 구조적 기준으로 사용했습니다."],
        )


def _strategy_input() -> StrategyInput:
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


def _config(cost: float = 0.1) -> BacktestConfig:
    return BacktestConfig(
        code="005930",
        market="KOSPI",
        start_date="2026-06-25",
        end_date="2026-07-10",
        round_trip_cost_pct=cost,
        max_holding_days=5,
    )


def _signal() -> dict[str, Any]:
    base = _strategy_input()
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


def _rows() -> list[dict[str, Any]]:
    return [
        {"date": "20260625", "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        {"date": "20260626", "open": 100.0, "high": 103.0, "low": 90.0, "close": 92.0},
        {"date": "20260629", "open": 91.0, "high": 93.0, "low": 82.0, "close": 84.0},
        {"date": "20260630", "open": 84.0, "high": 86.0, "low": 83.0, "close": 85.0},
    ]


def test_trade_trace_explains_wide_stop_formula_and_next_open() -> None:
    engine = BacktestEngine(risk=WideCautionRisk())
    trade, exit_index = engine._simulate_trade(  # noqa: SLF001 - accuracy audit regression test
        signal=_signal(),
        stock_rows=_rows(),
        config=_config(),
        research_only=False,
    )

    assert trade is not None
    assert exit_index == 2
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.stop_price == pytest.approx(83.0)
    assert trade.risk_plan_status == "CAUTION"
    trace = trade.metadata["audit"]
    assert trace["entry"]["next_trading_day_open_verified"] is True
    assert trace["risk"]["structural_anchor"] == pytest.approx(85.0)
    assert trace["risk"]["atr_value_at_entry"] == pytest.approx(4.0)
    assert trace["risk"]["buffer_factor"] == pytest.approx(0.5)
    assert trace["risk"]["initial_stop_distance_pct"] == pytest.approx(17.0)
    assert "WIDE_STOP" in trace["flags"]
    assert "CAUTION_RISK_PLAN" in trace["flags"]


def test_caution_plan_is_currently_executed_and_audit_surfaces_policy_gap() -> None:
    engine = BacktestEngine(risk=WideCautionRisk())
    trade, _ = engine._simulate_trade(  # noqa: SLF001
        signal=_signal(),
        stock_rows=_rows(),
        config=_config(),
        research_only=False,
    )
    assert trade is not None, "v0.19.4 must diagnose, not silently change the approved trade rule"

    result = {"trades": [trade.to_dict()]}
    audit = build_accuracy_audit(result, _config(), signal_boundary_violations=0)
    assert audit["status"] == "REVIEW_REQUIRED"
    check_by_id = {item["id"]: item for item in audit["checks"]}
    assert check_by_id["WIDE_STOP"]["status"] == "WARN"
    assert check_by_id["CAUTION_PLAN_EXECUTION"]["status"] == "WARN"
    assert audit["counts"]["wide_stop_trades"] == 1
    assert audit["counts"]["caution_plan_trades"] == 1
    flagged = audit["flagged_trades"][0]
    assert flagged["stop_distance_pct"] == pytest.approx(17.0)
    assert "CAUTION" in flagged["cause"]


def test_audit_recalculates_return_and_cost_math() -> None:
    engine = BacktestEngine(risk=WideCautionRisk())
    trade, _ = engine._simulate_trade(  # noqa: SLF001
        signal=_signal(),
        stock_rows=_rows(),
        config=_config(cost=0.15),
        research_only=False,
    )
    assert trade is not None
    audit = build_accuracy_audit({"trades": [trade.to_dict()]}, _config(cost=0.15))
    check_by_id = {item["id"]: item for item in audit["checks"]}
    assert check_by_id["RETURN_MATH"]["status"] == "PASS"
    assert audit["counts"]["return_math_mismatches"] == 0


def test_audit_fails_closed_when_future_boundary_violation_is_reported() -> None:
    audit = build_accuracy_audit({"trades": []}, _config(), signal_boundary_violations=1)
    assert audit["status"] == "FAILED"
    future_check = next(item for item in audit["checks"] if item["id"] == "FUTURE_DATA_BOUNDARY")
    assert future_check["status"] == "FAIL"


def test_entry_timing_research_overlap_is_explained_not_pooled() -> None:
    audit = build_accuracy_audit({"trades": []}, _config(), research_overlap_pairs=7)
    check = next(item for item in audit["checks"] if item["id"] == "ENTRY_TIMING_RESEARCH_INDEPENDENCE")
    assert check["status"] == "INFO"
    assert "7쌍" in check["detail"]
    assert "독립 표본" in check["detail"]


def test_real_risk_engine_can_create_very_wide_stop_by_prioritizing_support_over_closer_ma20() -> None:
    from app.risk.engine import RiskEngine
    from app.strategy.models import StrategyName

    data = replace(
        _strategy_input(),
        current_price=331_000.0,
        support_price=278_032.0,
        ma20=320_000.0,
        atr_pct=2.0,
        resistance_price=370_000.0,
    )
    plan = RiskEngine().build_plan(
        data=data,
        strategy=StrategyName.PULLBACK,
        technical={"low20": 276_000.0, "high20": 370_000.0},
        risk_gate_active=False,
        risk_gate_reasons=[],
        basis="BACKTEST_NEXT_OPEN",
    )

    # Pullback currently chooses a valid support candidate before MA20.
    assert plan.structural_anchor == pytest.approx(278_032.0)
    assert plan.structural_anchor_label == "주요 지지 후보"
    # 331,000 * 2% ATR = 6,620; Pullback buffer = 0.5 ATR.
    assert plan.invalidation_price == pytest.approx(274_722.0)
    assert plan.risk_pct == pytest.approx(17.0, abs=0.01)
    assert plan.status == RiskPlanStatus.CAUTION
    assert plan.structure_rating == "불리함"
