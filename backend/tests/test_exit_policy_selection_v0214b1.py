from __future__ import annotations

from copy import deepcopy

from app.backtest.exit_policy_selection import (
    EXIT_POLICY_SELECTION_VERSION,
    ExitPolicySelectionConfig,
    ExitPolicySelector,
)

BASE = "TARGET1_FULL_EXIT"
ATR = "ATR_TRAIL_2_0"
MA = "MA20_TRAIL"


def _primitive(*, trades: int, avg: float, pf: float, hold: float = 10.0, giveback: float = 5.0) -> dict:
    net_sum = avg * trades
    if abs(pf - 1.0) < 1e-9:
        positive = max(net_sum, 0.0)
        negative = max(-net_sum, 0.0)
    else:
        negative = net_sum / (pf - 1.0)
        if negative < 0:
            negative = abs(negative)
        positive = pf * negative
        # Floating arithmetic from the PF construction is the intended exact aggregate relation.
        if avg < 0 and positive - negative > 0:
            positive, negative = negative / max(pf, 0.01), negative
    wins = round(trades * (0.55 if avg > 0 else 0.40))
    return {
        "trades": trades,
        "wins": wins,
        "net_return_sum_pct": net_sum,
        "positive_net_sum_pct": positive,
        "negative_net_abs_sum_pct": negative,
        "holding_days_sum": hold * trades,
        "giveback_sum_pct_points": giveback * trades,
        "giveback_observations": trades,
    }


def _policy(policy_id: str, *, trades: int, avg: float, pf: float, mdd: float, hold: float = 10.0, giveback: float = 5.0) -> dict:
    return {
        "policy_id": policy_id,
        "metrics": {
            "trades": trades,
            "average_net_return_pct": avg,
            "profit_factor": pf,
            "max_drawdown_pct": mdd,
            "average_holding_days": hold,
            "win_rate_pct": 55.0 if avg > 0 else 40.0,
        },
        "profit_protection_metrics": {
            "average_profit_giveback_pct_points": giveback,
        },
        "aggregation_primitives": _primitive(trades=trades, avg=avg, pf=pf, hold=hold, giveback=giveback),
        "regime_aggregation_primitives": {
            "TREND_UP": {
                "trades": trades,
                "wins": round(trades * 0.6),
                "net_return_sum_pct": avg * trades,
                "positive_net_sum_pct": _primitive(trades=trades, avg=avg, pf=pf)["positive_net_sum_pct"],
                "negative_net_abs_sum_pct": _primitive(trades=trades, avg=avg, pf=pf)["negative_net_abs_sum_pct"],
            }
        },
    }


def _audit(code: str, market: str, *, base_avg: float = 1.0, atr_avg: float = 2.0, ma_avg: float = 1.3,
           base_pf: float = 1.2, atr_pf: float = 1.5, ma_pf: float = 1.3,
           base_mdd: float = -12.0, atr_mdd: float = -10.0, ma_mdd: float = -11.0,
           trades: int = 12, hard_atr_avg: float = 1.5) -> dict:
    policies = [
        _policy(BASE, trades=trades, avg=base_avg, pf=base_pf, mdd=base_mdd, hold=8, giveback=1),
        _policy(ATR, trades=trades, avg=atr_avg, pf=atr_pf, mdd=atr_mdd, hold=14, giveback=5),
        _policy(MA, trades=trades, avg=ma_avg, pf=ma_pf, mdd=ma_mdd, hold=12, giveback=7),
    ]
    hard = [
        _policy(ATR, trades=trades, avg=hard_atr_avg, pf=1.35, mdd=-11.0, hold=10, giveback=6),
        _policy(MA, trades=trades, avg=1.1, pf=1.2, mdd=-12.0, hold=10, giveback=8),
    ]
    return {
        "version": "0.21.4-A",
        "code": code,
        "market": market,
        "strategies": [{
            "strategy": "BREAKOUT",
            "policies": policies,
            "holding_policy_variants": hard,
        }],
    }


def _selector() -> ExitPolicySelector:
    return ExitPolicySelector(ExitPolicySelectionConfig(minimum_stock_count=3, minimum_total_trades=30))


def test_selects_unique_pareto_policy_without_weighted_score() -> None:
    result = _selector().run([
        _audit("000001", "KOSPI"),
        _audit("000002", "KOSDAQ"),
        _audit("000003", "KOSPI"),
    ])
    row = result["strategies"][0]
    assert result["version"] == EXIT_POLICY_SELECTION_VERSION
    assert result["selection_basis"] == "PARETO_NO_WEIGHTING"
    assert result["production_policy_changed"] is False
    assert row["status"] == "SELECTED"
    assert row["selected_policy_id"] == ATR
    assert row["max_hold_validation"]["status"] == "SELECTED"
    assert row["max_hold_validation"]["selected"] == "TRAILING_HORIZON_AFTER_TARGET2"
    assert row["regime_metrics"]["TREND_UP"]["trades"] == 36


def test_baseline_better_keeps_target1_full_exit() -> None:
    audits = [
        _audit(f"00000{i}", "KOSPI" if i % 2 else "KOSDAQ", atr_avg=0.5, ma_avg=0.7,
               atr_pf=1.0, ma_pf=1.05, atr_mdd=-15, ma_mdd=-14)
        for i in range(1, 4)
    ]
    row = _selector().run(audits)["strategies"][0]
    assert row["status"] == "BASELINE_BETTER"
    assert row["selected_policy_id"] == BASE
    assert row["max_hold_validation"]["status"] == "NOT_APPLICABLE"


def test_tradeoff_is_unresolved_instead_of_forcing_a_winner() -> None:
    audits = [
        _audit(f"00000{i}", "KOSPI", atr_avg=3.0, atr_pf=1.6, atr_mdd=-20.0,
               ma_avg=0.8, ma_pf=1.1, ma_mdd=-13.0)
        for i in range(1, 4)
    ]
    row = _selector().run(audits)["strategies"][0]
    assert row["status"] == "UNRESOLVED"
    assert row["selected_policy_id"] == BASE


def test_insufficient_sample_falls_back_to_baseline() -> None:
    audits = [_audit("000001", "KOSPI", trades=3), _audit("000002", "KOSDAQ", trades=3)]
    selector = ExitPolicySelector(ExitPolicySelectionConfig(minimum_stock_count=3, minimum_total_trades=30))
    row = selector.run(audits)["strategies"][0]
    assert row["status"] == "INSUFFICIENT_SAMPLE"
    assert row["selected_policy_id"] == BASE


def test_single_stock_dominance_blocks_auto_selection() -> None:
    audits = [
        _audit("000001", "KOSPI", base_avg=0.5, atr_avg=8.0),
        _audit("000002", "KOSDAQ", base_avg=1.0, atr_avg=1.1),
        _audit("000003", "KOSPI", base_avg=1.0, atr_avg=1.1),
    ]
    row = _selector().run(audits)["strategies"][0]
    assert row["status"] == "UNRESOLVED"
    assert row["stock_concentration"]["single_stock_dominant"] is True
    assert row["stock_concentration"]["dominant_code"] == "000001"


def test_single_market_is_reported_as_warning_not_silently_treated_as_diverse() -> None:
    result = _selector().run([_audit(f"00000{i}", "KOSPI") for i in range(1, 4)])
    assert result["sample"]["markets"] == ["KOSPI"]
    assert result["sample"]["market_diversity_warning"] is True


def test_hard_max_hold_can_win_its_separate_validation() -> None:
    audits = [
        _audit(f"00000{i}", "KOSPI" if i % 2 else "KOSDAQ", hard_atr_avg=3.0)
        for i in range(1, 4)
    ]
    # Make hard hold truly dominate on PF/MDD as well, not just return.
    for audit in audits:
        hard = audit["strategies"][0]["holding_policy_variants"][0]
        hard.update(_policy(ATR, trades=12, avg=3.0, pf=1.8, mdd=-8.0, hold=10, giveback=3))
    row = _selector().run(audits)["strategies"][0]
    assert row["status"] == "SELECTED"
    assert row["selected_policy_id"] == ATR
    assert row["max_hold_validation"]["selected"] == "HARD_MAX_HOLD"


def test_selection_does_not_mutate_input_audits() -> None:
    audits = [_audit(f"00000{i}", "KOSPI") for i in range(1, 4)]
    before = deepcopy(audits)
    _selector().run(audits)
    assert audits == before


def test_selection_config_rejects_invalid_guardrails() -> None:
    import pytest
    with pytest.raises(ValueError):
        ExitPolicySelectionConfig(minimum_stock_count=1, minimum_total_trades=30).validate()
    with pytest.raises(ValueError):
        ExitPolicySelectionConfig(minimum_stock_count=3, minimum_total_trades=5).validate()


def test_report_guardrails_explicitly_defer_production_change() -> None:
    result = _selector().run([_audit(f"00000{i}", "KOSPI") for i in range(1, 4)])
    assert result["guardrails"]["no_weighted_score"] is True
    assert result["guardrails"]["production_integration_deferred_to"] == "v0.21.4-B.2"
    assert result["production_policy_changed"] is False


import pytest


@pytest.mark.asyncio
async def test_service_reuses_one_provider_session_for_multi_stock_selection(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from datetime import date
    from pathlib import Path

    from app.backtest.models import BacktestConfig
    from app.backtest.service import BacktestService
    import app.backtest.service as service_module

    class DummyKrx:
        opened = 0
        closed = 0
        async def open_session(self) -> None:
            self.opened += 1
        async def close_session(self) -> None:
            self.closed += 1

    krx = DummyKrx()
    service = BacktestService(krx)  # type: ignore[arg-type]
    prepared: list[str] = []

    async def fake_prepare_history(*, config, start, end, progress):
        prepared.append(config.code)
        rows = [{"date": "20260101", "open": 100, "high": 101, "low": 99, "close": 100}]
        return rows, rows, [], date(2025, 10, 1), {"network_requests": 0}

    class DummyAudit:
        def run(self, **kwargs):
            config = kwargs["config"]
            assert kwargs["include_holding_policy_variants"] is True
            return _audit(config.code, config.market)

    monkeypatch.setattr(service, "_prepare_history", fake_prepare_history)
    service.exit_policy_research = DummyAudit()  # type: ignore[assignment]
    saved = tmp_path / "selection.json"
    monkeypatch.setattr(service_module, "save_selection_report", lambda report: Path(saved))

    configs = [
        BacktestConfig(code=f"00000{i}", market="KOSPI" if i % 2 else "KOSDAQ", start_date="2026-01-01", end_date="2026-09-01")
        for i in range(1, 4)
    ]
    result = await service.run_exit_policy_selection(
        configs,
        selection_config=ExitPolicySelectionConfig(minimum_stock_count=3, minimum_total_trades=30),
    )
    assert prepared == ["000001", "000002", "000003"]
    assert krx.opened == 1 and krx.closed == 1
    assert result["research_only"] is True
    assert result["production_policy_changed"] is False
    assert result["strategies"][0]["selected_policy_id"] == ATR
    assert result["performance"]["network_requests"] == 0
