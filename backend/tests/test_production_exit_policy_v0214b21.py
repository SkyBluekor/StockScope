from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestConfig
from app.backtest.production_exit_policy import (
    HOLDING_HARD_MAX,
    HOLDING_TRAILING_HORIZON,
    PRODUCTION_EXIT_POLICY_VERSION,
    ProductionExitPolicyEngine,
    ProductionExitPolicyRegistry,
    ProductionExitPolicyResolution,
)
from app.strategy.models import StrategyName


def _report() -> dict:
    return {
        "status": "COMPLETED",
        "signature": "sample-signature",
        "runner_version": "0.21.4-B.1.1",
        "version": "0.21.4-B.1",
        "period": {"start": "2023-09-01", "end": "2026-09-01"},
        "validation_config": {"post_target2_research_days": 60},
        "strategies": [
            {
                "strategy": "BREAKOUT",
                "status": "SELECTED",
                "selected_policy_id": "ATR_TRAIL_2_0",
                "reason": "validated",
                "max_hold_validation": {
                    "status": "SELECTED",
                    "selected": HOLDING_TRAILING_HORIZON,
                },
            },
            {
                "strategy": "RANGE_TRADING",
                "status": "BASELINE_BETTER",
                "selected_policy_id": "TARGET1_FULL_EXIT",
                "reason": "baseline wins",
                "max_hold_validation": {"status": "NOT_APPLICABLE", "selected": None},
            },
            {
                "strategy": "PULLBACK",
                "status": "UNRESOLVED",
                "selected_policy_id": "TARGET1_FULL_EXIT",
                "reason": "tradeoff",
                "max_hold_validation": {"status": "UNRESOLVED", "selected": None},
            },
            {
                "strategy": "TREND_FOLLOWING",
                "status": "SELECTED",
                "selected_policy_id": "MA20_TRAIL",
                "reason": "validated",
                "max_hold_validation": {"status": "UNRESOLVED", "selected": None},
            },
        ],
    }


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
        "strategy_input": SimpleNamespace(current_price=100.0, atr_pct=None, support_price=95.0, ma20=100.0),
        "technical": {},
        "risk_gate_active": False,
        "risk_gate_reasons": [],
        "audit_context": {},
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


def _base(monkeypatch: pytest.MonkeyPatch, *, target2: float | None = 120.0) -> BacktestEngine:
    base = BacktestEngine()
    plan = SimpleNamespace(
        reference_only=False,
        invalidation_price=90.0,
        target1_price=110.0,
        target2_price=target2,
        status=SimpleNamespace(value="NORMAL"),
        structural_anchor=95.0,
        structural_anchor_label="support",
        structure_rating="양호",
        summary="ok",
        warnings=[],
        reasons=[],
    )
    monkeypatch.setattr(base, "_build_risk_plan_for_policy", lambda **kwargs: (plan, {}))
    return base


def test_registry_activates_only_selected_and_uses_safe_hold_fallback(tmp_path: Path) -> None:
    (tmp_path / "exit_policy_validation_report.json").write_text(
        json.dumps(_report(), ensure_ascii=False), encoding="utf-8"
    )
    registry = ProductionExitPolicyRegistry(tmp_path)
    mapping = registry.activate_from_latest_validation()
    assert mapping["policy_version"] == PRODUCTION_EXIT_POLICY_VERSION
    assert mapping["strategies"]["BREAKOUT"]["policy_id"] == "ATR_TRAIL_2_0"
    assert mapping["strategies"]["BREAKOUT"]["holding_policy"] == HOLDING_TRAILING_HORIZON
    assert mapping["strategies"]["RANGE_TRADING"]["policy_id"] == "TARGET1_FULL_EXIT"
    assert mapping["strategies"]["PULLBACK"]["policy_id"] == "TARGET1_FULL_EXIT"
    assert mapping["strategies"]["TREND_FOLLOWING"]["policy_id"] == "MA20_TRAIL"
    assert mapping["strategies"]["TREND_FOLLOWING"]["holding_policy"] == HOLDING_HARD_MAX


def test_existing_production_mapping_is_frozen_from_later_research_rerun(tmp_path: Path) -> None:
    report_path = tmp_path / "exit_policy_validation_report.json"
    report_path.write_text(json.dumps(_report(), ensure_ascii=False), encoding="utf-8")
    registry = ProductionExitPolicyRegistry(tmp_path)
    first = registry.activate_from_latest_validation()

    changed = _report()
    changed["strategies"][0]["selected_policy_id"] = "ATR_TRAIL_2_5"
    report_path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    second = registry.ensure_mapping()
    assert second is not None
    assert second["strategies"]["BREAKOUT"]["policy_id"] == first["strategies"]["BREAKOUT"]["policy_id"] == "ATR_TRAIL_2_0"


def test_missing_report_or_mapping_is_exact_baseline_fallback(tmp_path: Path) -> None:
    resolution = ProductionExitPolicyRegistry(tmp_path).resolve(StrategyName.BREAKOUT)
    assert resolution.policy_id == "TARGET1_FULL_EXIT"
    assert resolution.fallback_used is True
    assert resolution.fallback_reason == "NO_VALIDATED_PRODUCTION_MAPPING"


def test_production_trailing_uses_target2_as_milestone_and_shared_eod_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    base = _base(monkeypatch)

    class Registry:
        def resolve(self, strategy):
            return ProductionExitPolicyResolution(
                strategy=StrategyName.BREAKOUT.value,
                policy_id="MA20_TRAIL",
                holding_policy=HOLDING_TRAILING_HORIZON,
                policy_source="TEST_VALIDATED",
                fallback_used=False,
                fallback_reason=None,
            )

    engine = ProductionExitPolicyEngine(base, Registry())  # type: ignore[arg-type]
    monkeypatch.setattr(engine.simulator, "protection_candidate", lambda **kwargs: 118.0)
    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=112, low=99, close=111),
        _row(3, open_=111, high=121, low=110, close=120),
        _row(4, open_=120, high=124, low=118, close=123),
        _row(5, open_=123, high=124, low=114, close=115),
    ]
    trade, _, resolution = engine.simulate_trade(
        signal=_signal(), stock_rows=rows, config=_config(), strategy=StrategyName.BREAKOUT
    )
    assert trade is not None
    assert resolution.policy_id == "MA20_TRAIL"
    assert trade.research_only is False
    assert trade.exit_reason == "TRAILING_CLOSE_EXIT"
    assert trade.exit_date == "20260105"
    meta = trade.metadata["exit_policy"]
    assert meta["target1_reached"] is True
    assert meta["target2_reached"] is True
    assert meta["trailing_activated"] is True
    assert meta["protection_never_decreases"] is True


def test_selected_policy_without_target2_falls_back_to_exact_baseline_trade(monkeypatch: pytest.MonkeyPatch) -> None:
    base = _base(monkeypatch, target2=None)

    class Registry:
        def resolve(self, strategy):
            return ProductionExitPolicyResolution(
                strategy=StrategyName.TREND_FOLLOWING.value,
                policy_id="ATR_TRAIL_2_0",
                holding_policy=HOLDING_TRAILING_HORIZON,
                policy_source="TEST_VALIDATED",
                fallback_used=False,
                fallback_reason=None,
            )

    engine = ProductionExitPolicyEngine(base, Registry())  # type: ignore[arg-type]
    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=111, low=99, close=110),
    ]
    trade, _, resolution = engine.simulate_trade(
        signal=_signal(), stock_rows=rows, config=_config(), strategy=StrategyName.TREND_FOLLOWING
    )
    assert trade is not None
    assert trade.exit_reason == "TARGET_1"
    assert resolution.policy_id == "TARGET1_FULL_EXIT"
    assert resolution.fallback_used is True
    assert resolution.fallback_reason == "SELECTED_POLICY_UNUSABLE_FOR_TRADE"
    assert trade.metadata["exit_policy"]["policy_id"] == "TARGET1_FULL_EXIT"



def test_baseline_production_path_matches_legacy_backtest_trade_exactly(monkeypatch: pytest.MonkeyPatch) -> None:
    base = _base(monkeypatch)

    class Registry:
        def resolve(self, strategy):
            return ProductionExitPolicyResolution(
                strategy=StrategyName.RANGE_TRADING.value,
                policy_id="TARGET1_FULL_EXIT",
                policy_source="TEST_BASELINE",
                fallback_used=False,
                fallback_reason=None,
            )

    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=111, low=99, close=110),
        _row(3, open_=110, high=112, low=108, close=111),
    ]
    legacy_trade, legacy_index = base._simulate_trade(  # noqa: SLF001 - parity contract
        signal=_signal(),
        stock_rows=rows,
        config=_config(),
        research_only=False,
        strategy=StrategyName.RANGE_TRADING,
    )
    engine = ProductionExitPolicyEngine(base, Registry())  # type: ignore[arg-type]
    production_trade, production_index, resolution = engine.simulate_trade(
        signal=_signal(),
        stock_rows=rows,
        config=_config(),
        strategy=StrategyName.RANGE_TRADING,
    )
    assert legacy_trade is not None and production_trade is not None
    assert production_index == legacy_index
    assert resolution.policy_id == "TARGET1_FULL_EXIT"
    for field in (
        "signal_date",
        "entry_date",
        "entry_price",
        "exit_date",
        "exit_price",
        "exit_reason",
        "holding_days",
        "stop_price",
        "target1_price",
        "target2_price",
        "gross_return_pct",
        "net_return_pct",
    ):
        assert getattr(production_trade, field) == getattr(legacy_trade, field)



def test_backtest_run_accepts_production_actual_trade_hook_without_changing_research_path(monkeypatch: pytest.MonkeyPatch) -> None:
    base = _base(monkeypatch)
    signal = dict(_signal())
    signal["entry_timing_state"] = "REBOUND_CONFIRMED"

    def fake_snapshot(**kwargs):
        return signal if int(kwargs["index"]) == 0 else None

    monkeypatch.setattr(base, "_signal_snapshot", fake_snapshot)
    calls = {"actual": 0}

    def simulate_actual(*, signal, stock_rows, config):
        calls["actual"] += 1
        return base._simulate_trade(  # noqa: SLF001 - test the production hook contract
            signal=signal,
            stock_rows=stock_rows,
            config=config,
            research_only=False,
            strategy=StrategyName.PULLBACK,
        )

    rows = [
        _row(1, open_=100, high=101, low=99, close=100),
        _row(2, open_=100, high=111, low=99, close=110),
        _row(3, open_=110, high=112, low=108, close=111),
    ]
    result = base.run(
        stock_rows=rows,
        index_rows=rows,
        config=_config(),
        actual_trade_simulator=simulate_actual,
    )
    assert calls["actual"] == 1
    assert result["summary"]["trades"] == 1


def test_historical_policy_metadata_distinguishes_baseline_and_profit_protection() -> None:
    baseline = ProductionExitPolicyResolution(strategy="RANGE_TRADING")
    selected = ProductionExitPolicyResolution(
        strategy="BREAKOUT",
        policy_id="ATR_TRAIL_2_0",
        holding_policy=HOLDING_TRAILING_HORIZON,
        fallback_used=False,
        fallback_reason=None,
    )
    base_meta = ProductionExitPolicyEngine.historical_policy_metadata(baseline)
    selected_meta = ProductionExitPolicyEngine.historical_policy_metadata(selected)
    assert base_meta["target1_is_exit"] is True and base_meta["target2_included"] is False
    assert selected_meta["target1_is_exit"] is False and selected_meta["target2_included"] is True
    assert selected_meta["policy_version"] == PRODUCTION_EXIT_POLICY_VERSION
