from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.backtest.exit_policy_selection import ExitPolicySelectionConfig
from app.backtest.exit_policy_validation_runner import (
    ExitPolicyValidationCheckpoint,
    ExitPolicyValidationRunnerConfig,
    interleave_market_candidates,
    validation_sample_signature,
)
from app.backtest.history_store import HistorySeries
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.service import BacktestService


def test_interleave_market_candidates_balances_markets() -> None:
    groups = {
        "KOSPI": [{"code": "1", "market": "KOSPI"}, {"code": "2", "market": "KOSPI"}],
        "KOSDAQ": [{"code": "3", "market": "KOSDAQ"}, {"code": "4", "market": "KOSDAQ"}],
    }
    rows = interleave_market_candidates(groups, ("KOSPI", "KOSDAQ"), 4)
    assert [(row["market"], row["code"]) for row in rows] == [
        ("KOSPI", "1"), ("KOSDAQ", "3"), ("KOSPI", "2"), ("KOSDAQ", "4")
    ]


def test_checkpoint_signature_changes_when_sample_changes(tmp_path: Path) -> None:
    config = ExitPolicyValidationRunnerConfig(start_date="2024-01-01", end_date="2026-09-01")
    a = validation_sample_signature(config, [{"market": "KOSPI", "code": "000001"}])
    b = validation_sample_signature(config, [{"market": "KOSPI", "code": "000002"}])
    assert a != b

    store = ExitPolicyValidationCheckpoint(tmp_path)
    store.save(a, config, [{"market": "KOSPI", "code": "000001"}])
    assert store.load(a) is not None
    assert store.load(b) is None


def test_market_store_research_candidates_uses_local_trading_days(tmp_path: Path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    for day in ["20260102", "20260105", "20260106", "20260107"]:
        store.put_stock_day("KOSPI", day, [
            {"code": "000001", "date": day, "close": 100},
            {"code": "000002", "date": day, "close": 100},
        ], stable=True)
        store.put_index_day("KOSPI", day, {"date": day, "close": 3000}, stable=True)
    # Remove one symbol-day so its local coverage becomes 75%.
    with store._connect() as conn:  # noqa: SLF001 - focused storage regression test
        conn.execute("DELETE FROM stock_daily WHERE market='KOSPI' AND stock_code='000002' AND bas_dd='20260107'")

    result = store.research_candidates("KOSPI", "20260101", "20260131", minimum_coverage_pct=90, limit=10)
    assert result["trading_days"] == 4
    assert result["index_coverage_pct"] == 100.0
    assert [row["code"] for row in result["candidates"]] == ["000001"]


def _policy(policy_id: str, avg: float, pf: float, mdd: float, trades: int = 12) -> dict:
    negative = 10.0
    positive = pf * negative
    net_sum = avg * trades
    # Keep additive primitives internally consistent enough for aggregation tests.
    scale = 1.0 if abs(positive - negative) < 1e-9 else net_sum / (positive - negative)
    positive *= scale
    negative *= scale
    return {
        "policy_id": policy_id,
        "metrics": {
            "trades": trades,
            "average_net_return_pct": avg,
            "profit_factor": pf,
            "max_drawdown_pct": mdd,
            "average_holding_days": 10,
            "win_rate_pct": 55.0,
        },
        "profit_protection_metrics": {"average_profit_giveback_pct_points": 5.0},
        "aggregation_primitives": {
            "trades": trades,
            "wins": 7,
            "net_return_sum_pct": net_sum,
            "positive_net_sum_pct": positive,
            "negative_net_abs_sum_pct": negative,
            "holding_days_sum": trades * 10,
            "giveback_sum_pct_points": trades * 5,
            "giveback_observations": trades,
        },
        "regime_aggregation_primitives": {},
    }


def _audit(code: str, market: str) -> dict:
    baseline = _policy("TARGET1_FULL_EXIT", 1.0, 1.2, -12.0)
    atr = _policy("ATR_TRAIL_2_0", 2.0, 1.5, -10.0)
    return {
        "code": code,
        "market": market,
        "strategies": [{
            "strategy": "BREAKOUT",
            "policies": [baseline, atr],
            "holding_policy_variants": [atr],
        }],
    }


@pytest.mark.asyncio
async def test_runner_is_local_only_and_reuses_checkpoint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class DummyKrx:
        def request_stats(self): return {"network_requests": 0}

    class DummyMarketStore:
        def research_candidates(self, market, start_dd, end_dd, *, minimum_coverage_pct, limit):
            codes = ["000001", "000003"] if market == "KOSPI" else ["000002"]
            return {
                "market": market,
                "trading_days": 500,
                "index_days": 500,
                "index_coverage_pct": 100.0,
                "candidates": [
                    {"code": code, "market": market, "coverage_pct": 100.0, "row_count": 500}
                    for code in codes[:limit]
                ],
            }

        def stock_series(self, market, code, start_dd, end_dd):
            start = date(2023, 1, 1)
            rows = {}
            for i in range(900):
                day = start + timedelta(days=i)
                if day.weekday() >= 5:
                    continue
                key = day.strftime("%Y%m%d")
                rows[key] = {"date": key, "open": 100, "high": 102, "low": 98, "close": 100, "volume": 1000, "code": code}
            return HistorySeries(rows=rows, checked_dates=set(rows))

        def index_series(self, market, start_dd, end_dd):
            series = self.stock_series(market, "INDEX", start_dd, end_dd)
            return series

    class DummyAuditEngine:
        calls: list[str] = []
        def run(self, *, config, **kwargs):
            self.calls.append(config.code)
            return _audit(config.code, config.market)

    DummyAuditEngine.calls.clear()
    monkeypatch.setattr("app.backtest.service.ExitPolicyResearchEngine", DummyAuditEngine)
    service = BacktestService(DummyKrx(), market_store=DummyMarketStore())  # type: ignore[arg-type]
    dummy = DummyAuditEngine()
    checkpoint = ExitPolicyValidationCheckpoint(tmp_path)
    cfg = ExitPolicyValidationRunnerConfig(
        start_date="2024-01-01",
        end_date="2025-06-01",
        max_stocks=3,
        minimum_stock_count=3,
        minimum_total_trades=30,
    )

    first = await service.run_exit_policy_validation_runner(cfg, checkpoint_store=checkpoint)
    assert first["status"] == "COMPLETED"
    assert first["performance"]["network_requests"] == 0
    assert first["production_policy_changed"] is False
    assert sorted(dummy.calls) == ["000001", "000002", "000003"]

    dummy.calls.clear()
    second = await service.run_exit_policy_validation_runner(cfg, checkpoint_store=checkpoint)
    assert second["status"] == "COMPLETED"
    assert second["checkpoint"]["reused_stocks"] == 3
    assert dummy.calls == []


def test_runner_config_guardrails() -> None:
    with pytest.raises(ValueError):
        ExitPolicyValidationRunnerConfig(start_date="2024-01-01", end_date="2025-01-01", max_stocks=1).validate()
    with pytest.raises(ValueError):
        ExitPolicyValidationRunnerConfig(start_date="2024-01-01", end_date="2025-01-01", minimum_coverage_pct=40).validate()
