from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.exit_policy_research import (
    ExitPolicyResearchEngine,
    POLICY_ATR_15,
    POLICY_ATR_20,
    POLICY_ATR_25,
    POLICY_MA20,
    POLICY_SWING_LOW,
    POLICY_TARGET1_FULL_EXIT,
    RESEARCH_POLICIES,
)
from app.backtest.models import BacktestConfig
from app.strategy.models import StrategyName


def _row(day: int, *, open_: float, high: float, low: float, close: float) -> dict:
    return {
        "date": f"202601{day:02d}",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1_000_000,
        "trade_value": 2_000_000_000,
    }


def _config(max_holding_days: int = 4) -> BacktestConfig:
    return BacktestConfig(
        code="005930",
        market="KOSPI",
        start_date="2026-01-01",
        end_date="2026-01-31",
        max_holding_days=max_holding_days,
        round_trip_cost_pct=0.0,
    )


def _signal() -> dict:
    return {
        "signal_index": 0,
        "signal_date": "20260101",
        "strategy_score": 80,
        "strategy_eligible": True,
        "entry_timing_state": "STRATEGY_SIGNAL",
        "entry_timing_passed": 6,
        "entry_timing_total": 6,
        "market_regime": "TREND_UP",
        "relative_strength_market_pct": 2.0,
        "strategy_input": SimpleNamespace(current_price=100.0),
        "technical": {},
        "risk_gate_active": False,
        "risk_gate_reasons": [],
    }


def _engine(monkeypatch: pytest.MonkeyPatch, *, stop: float = 90, target1: float = 110, target2: float = 120) -> ExitPolicyResearchEngine:
    base = BacktestEngine()
    plan = SimpleNamespace(
        reference_only=False,
        invalidation_price=stop,
        target1_price=target1,
        target2_price=target2,
        status=SimpleNamespace(value="NORMAL"),
    )
    monkeypatch.setattr(
        base,
        "_build_risk_plan_for_policy",
        lambda **kwargs: (plan, {}),
    )
    return ExitPolicyResearchEngine(base)


def test_policy_catalog_keeps_atr_as_grid_not_one_arbitrary_value() -> None:
    ids = [policy.id for policy in RESEARCH_POLICIES]
    assert ids == [
        POLICY_TARGET1_FULL_EXIT.id,
        POLICY_ATR_15.id,
        POLICY_ATR_20.id,
        POLICY_ATR_25.id,
        POLICY_MA20.id,
        POLICY_SWING_LOW.id,
    ]
    assert [POLICY_ATR_15.atr_multiplier, POLICY_ATR_20.atr_multiplier, POLICY_ATR_25.atr_multiplier] == [1.5, 2.0, 2.5]


def test_target2_is_milestone_not_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch)
    rows = [
        _row(1, open_=100, high=101, low=99, close=100),  # signal day
        _row(2, open_=100, high=112, low=99, close=111),  # target1 only
        _row(3, open_=111, high=121, low=110, close=120),  # target2 reached
        _row(4, open_=120, high=124, low=118, close=123),
        _row(5, open_=123, high=124, low=114, close=115),
    ]
    monkeypatch.setattr(engine, "_protection_candidate", lambda **kwargs: 118.0)
    trade, _ = engine._simulate_profit_protection_trade(
        signal=_signal(), stock_rows=rows, config=_config(), strategy=StrategyName.TREND_FOLLOWING,
        policy=POLICY_MA20, post_target2_research_days=20,
    )
    assert trade is not None
    assert trade.exit_date == "20260105"
    assert trade.exit_reason == "TRAILING_CLOSE_EXIT"
    research = trade.metadata["exit_policy_research"]
    assert research["target1_reached"] is True
    assert research["target2_reached"] is True
    assert research["trailing_activated"] is True


def test_same_day_stop_and_target2_keeps_conservative_stop_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch)
    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=121, low=89, close=118),
    ]
    trade, _ = engine._simulate_profit_protection_trade(
        signal=_signal(), stock_rows=rows, config=_config(), strategy=StrategyName.BREAKOUT,
        policy=POLICY_ATR_20, post_target2_research_days=20,
    )
    assert trade is not None
    assert trade.exit_reason == "STOP_SAME_DAY_PRIORITY"
    assert trade.exit_price == 90


def test_protection_line_never_decreases(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch)
    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=121, low=99, close=120),
        _row(3, open_=120, high=130, low=119, close=129),
        _row(4, open_=129, high=130, low=123, close=124),
    ]
    candidates = {1: 115.0, 2: 122.0, 3: 118.0}
    monkeypatch.setattr(
        engine,
        "_protection_candidate",
        lambda **kwargs: candidates.get(kwargs["end_index"]),
    )
    trade, _ = engine._simulate_profit_protection_trade(
        signal=_signal(), stock_rows=rows, config=_config(), strategy=StrategyName.TREND_FOLLOWING,
        policy=POLICY_SWING_LOW, post_target2_research_days=2,
    )
    assert trade is not None
    research = trade.metadata["exit_policy_research"]
    assert research["final_protection_price"] == 122.0
    assert research["protection_never_decreases"] is True


def test_today_new_candidate_cannot_rescue_today_close_breach(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch)
    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=121, low=99, close=120),  # target2, protection becomes 110
        _row(3, open_=120, high=140, low=108, close=109),  # would produce 130, but closes below OLD 110
    ]
    candidates = {1: 110.0, 2: 130.0}
    monkeypatch.setattr(engine, "_protection_candidate", lambda **kwargs: candidates.get(kwargs["end_index"]))
    trade, _ = engine._simulate_profit_protection_trade(
        signal=_signal(), stock_rows=rows, config=_config(), strategy=StrategyName.BREAKOUT,
        policy=POLICY_ATR_15, post_target2_research_days=20,
    )
    assert trade is not None
    assert trade.exit_reason == "TRAILING_CLOSE_EXIT"
    assert trade.exit_price == 109
    assert trade.metadata["exit_policy_research"]["final_protection_price"] == 110.0


def test_pre_target2_max_hold_remains_existing_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch)
    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=108, low=99, close=106),
        _row(3, open_=106, high=109, low=104, close=108),
        _row(4, open_=108, high=109, low=105, close=107),
        _row(5, open_=107, high=109, low=106, close=108),
    ]
    trade, _ = engine._simulate_profit_protection_trade(
        signal=_signal(), stock_rows=rows, config=_config(max_holding_days=3), strategy=StrategyName.PULLBACK,
        policy=POLICY_MA20, post_target2_research_days=20,
    )
    assert trade is not None
    assert trade.exit_reason == "TIME_EXIT_PRE_TARGET2"
    assert trade.holding_days == 3


def test_target2_extends_research_horizon_beyond_original_max_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch)
    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=121, low=99, close=120),
        _row(3, open_=120, high=125, low=118, close=124),
        _row(4, open_=124, high=128, low=122, close=127),
        _row(5, open_=127, high=130, low=125, close=129),
    ]
    monkeypatch.setattr(engine, "_protection_candidate", lambda **kwargs: 100.0)
    trade, _ = engine._simulate_profit_protection_trade(
        signal=_signal(), stock_rows=rows, config=_config(max_holding_days=1), strategy=StrategyName.MOMENTUM_CONTINUATION,
        policy=POLICY_ATR_25, post_target2_research_days=2,
    )
    assert trade is not None
    assert trade.exit_reason == "RESEARCH_HORIZON_EXIT"
    assert trade.holding_days == 3


def test_swing_low_requires_two_right_side_bars_to_be_confirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch)
    rows = [
        _row(1, open_=100, high=105, low=100, close=103),
        _row(2, open_=103, high=104, low=98, close=100),
        _row(3, open_=100, high=102, low=95, close=99),  # pivot candidate
        _row(4, open_=99, high=103, low=97, close=102),
        _row(5, open_=102, high=106, low=99, close=105),  # second right bar confirms day3
    ]
    assert engine._latest_confirmed_swing_low(rows, end_index=3, entry_index=1) is None
    assert engine._latest_confirmed_swing_low(rows, end_index=4, entry_index=1) == 95


def test_ma20_uses_exactly_completed_20_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch)
    rows = [
        _row(i + 1, open_=100 + i, high=101 + i, low=99 + i, close=100 + i)
        for i in range(21)
    ]
    expected = sum(float(100 + i) for i in range(1, 21)) / 20
    assert engine._ma20(rows, 20) == pytest.approx(expected)


def test_path_metrics_report_profit_giveback() -> None:
    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=121, low=99, close=120),
        _row(3, open_=120, high=131, low=119, close=130),
        _row(4, open_=130, high=131, low=114, close=115),
    ]
    metrics = ExitPolicyResearchEngine._trade_path_metrics(
        rows=rows, entry_index=0, exit_index=3, entry_price=100, exit_price=115,
    )
    assert metrics["peak_return_pct"] == 30.0
    assert metrics["profit_giveback_pct_points"] == 15.0
    assert metrics["profit_giveback_of_peak_pct"] == 50.0

@pytest.mark.asyncio
async def test_service_exposes_research_only_audit_without_changing_other_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.backtest.service import BacktestService

    class DummyKrx:
        opened = False
        closed = False

        async def open_session(self) -> None:
            self.opened = True

        async def close_session(self) -> None:
            self.closed = True

    krx = DummyKrx()
    service = BacktestService(krx)  # type: ignore[arg-type]
    rows = [_row(1, open_=100, high=101, low=99, close=100)]

    async def fake_prepare_history(**kwargs):
        return rows, rows, [], __import__("datetime").date(2025, 12, 1), {"network_requests": 0}

    class DummyAudit:
        def run(self, **kwargs):
            return {"version": "0.21.4-A", "research_only": True, "strategies": []}

    monkeypatch.setattr(service, "_prepare_history", fake_prepare_history)
    service.exit_policy_research = DummyAudit()  # type: ignore[assignment]

    result = await service.run_exit_policy_audit(_config())
    assert result["research_only"] is True
    assert result["version"] == "0.21.4-A"
    assert result["performance"]["network_requests"] == 0
    assert krx.opened is True and krx.closed is True


def test_v0214b1_additive_primitives_are_exact_for_policy_aggregation() -> None:
    from app.backtest.models import BacktestTrade

    trades = [
        BacktestTrade(
            signal_date="20260101", entry_date="20260102", entry_price=100, exit_date="20260103", exit_price=110,
            exit_reason="TARGET_1", holding_days=2, strategy_score=80, entry_timing_passed=6,
            entry_timing_total=6, entry_timing_state="STRATEGY_SIGNAL", market_regime="TREND_UP",
            stop_price=90, target1_price=110, target2_price=120, gross_return_pct=10, net_return_pct=9,
            risk_plan_status="NORMAL", research_only=True,
            metadata={"exit_policy_research": {"profit_giveback_pct_points": 1.5}},
        ),
        BacktestTrade(
            signal_date="20260104", entry_date="20260105", entry_price=100, exit_date="20260106", exit_price=95,
            exit_reason="STOP", holding_days=2, strategy_score=80, entry_timing_passed=6,
            entry_timing_total=6, entry_timing_state="STRATEGY_SIGNAL", market_regime="TREND_DOWN",
            stop_price=95, target1_price=110, target2_price=120, gross_return_pct=-5, net_return_pct=-6,
            risk_plan_status="NORMAL", research_only=True,
            metadata={"exit_policy_research": {"profit_giveback_pct_points": 0.5}},
        ),
    ]
    primitives = ExitPolicyResearchEngine._aggregation_primitives(trades)
    assert primitives["trades"] == 2
    assert primitives["wins"] == 1
    assert primitives["net_return_sum_pct"] == 3
    assert primitives["positive_net_sum_pct"] == 9
    assert primitives["negative_net_abs_sum_pct"] == 6
    assert primitives["giveback_sum_pct_points"] == 2
    regimes = ExitPolicyResearchEngine._regime_aggregation_primitives(trades)
    assert regimes["TREND_UP"]["trades"] == 1
    assert regimes["TREND_DOWN"]["net_return_sum_pct"] == -6


def test_v0214b1_hard_max_hold_variant_stops_at_original_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch)
    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=121, low=99, close=120),
        _row(3, open_=120, high=125, low=118, close=124),
        _row(4, open_=124, high=128, low=122, close=127),
    ]
    monkeypatch.setattr(engine, "_protection_candidate", lambda **kwargs: 100.0)
    trade, _ = engine._simulate_profit_protection_trade(
        signal=_signal(), stock_rows=rows, config=_config(max_holding_days=2),
        strategy=StrategyName.TREND_FOLLOWING, policy=POLICY_ATR_20,
        post_target2_research_days=20, extend_after_target2=False,
    )
    assert trade is not None
    assert trade.exit_reason == "HARD_MAX_HOLD_EXIT"
    assert trade.holding_days == 2
    assert trade.metadata["exit_policy_research"]["post_target2_holding_policy"] == "HARD_MAX_HOLD"
