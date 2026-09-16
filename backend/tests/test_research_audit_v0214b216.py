from __future__ import annotations

import json
from pathlib import Path

from app.backtest.exit_policy_selection import ExitPolicySelectionConfig, ExitPolicySelector
from app.backtest.exit_policy_validation_runner import ExitPolicyValidationCheckpoint
from app.backtest.research_audit import ExitPolicyResearchAuditStore, ExitPolicyResearchAuditor


def _policy(
    policy_id: str,
    *,
    trades: int,
    net_sum: float,
    positive_sum: float,
    negative_abs_sum: float,
    mdd: float,
    signal_count: int | None = None,
) -> dict:
    return {
        "policy_id": policy_id,
        "signal_count": trades if signal_count is None else signal_count,
        "metrics": {
            "trades": trades,
            "average_net_return_pct": net_sum / trades,
            "win_rate_pct": 50.0,
            "profit_factor": positive_sum / negative_abs_sum if negative_abs_sum else None,
            "max_drawdown_pct": mdd,
            "average_holding_days": 5.0,
        },
        "profit_protection_metrics": {"average_profit_giveback_pct_points": 2.0},
        "aggregation_primitives": {
            "trades": trades,
            "wins": trades // 2,
            "net_return_sum_pct": net_sum,
            "positive_net_sum_pct": positive_sum,
            "negative_net_abs_sum_pct": negative_abs_sum,
            "holding_days_sum": trades * 5,
            "giveback_sum_pct_points": trades * 2,
            "giveback_observations": trades,
        },
        "regime_aggregation_primitives": {
            "TREND_UP": {
                "trades": trades,
                "wins": trades // 2,
                "net_return_sum_pct": net_sum,
                "positive_net_sum_pct": positive_sum,
                "negative_net_abs_sum_pct": negative_abs_sum,
            }
        },
        "recent_trades": [],
    }


def _audit(code: str, market: str, *, candidate_trade_delta: int = 0) -> dict:
    baseline_trades = 12
    candidate_trades = baseline_trades + candidate_trade_delta
    return {
        "code": code,
        "market": market,
        "config": {
            "entry_price_policy": "NEXT_TRADING_DAY_OPEN",
            "same_day_stop_target2_policy": "STOP_FIRST_CONSERVATIVE",
            "trailing_exit_confirmation": "DAILY_CLOSE",
            "protection_update_policy": "AFTER_CLOSE_FOR_NEXT_TRADING_DAY_ONLY",
            "protection_direction": "NON_DECREASING",
        },
        "strategies": [
            {
                "strategy": "trend_following",
                "policies": [
                    _policy(
                        "TARGET1_FULL_EXIT",
                        trades=baseline_trades,
                        net_sum=12,
                        positive_sum=24,
                        negative_abs_sum=12,
                        mdd=-10,
                    ),
                    _policy(
                        "ATR_TRAIL_2_0",
                        trades=candidate_trades,
                        net_sum=6,
                        positive_sum=18,
                        negative_abs_sum=12,
                        mdd=-15,
                        signal_count=candidate_trades,
                    ),
                ],
                "holding_policy_variants": [],
            }
        ],
    }


def _write_fixture(tmp_path: Path, *, candidate_trade_delta: int = 0, stock_count: int = 4) -> ExitPolicyResearchAuditor:
    audits = [
        _audit(f"00000{index}", "KOSPI" if index % 2 else "KOSDAQ", candidate_trade_delta=candidate_trade_delta)
        for index in range(1, stock_count + 1)
    ]
    selection_config = ExitPolicySelectionConfig(minimum_stock_count=3, minimum_total_trades=30)
    result = ExitPolicySelector(selection_config).run(audits)
    signature = "fixture-signature"
    checkpoint_payload = {
        "schema_version": 1,
        "signature": signature,
        "audits": audits,
    }
    (tmp_path / f"exit_policy_validation_checkpoint_{signature}.json").write_text(
        json.dumps(checkpoint_payload), encoding="utf-8"
    )
    report = {
        **result,
        "runner_version": "fixture",
        "status": "COMPLETED",
        "signature": signature,
        "period": {"start": "2023-01-01", "end": "2026-01-01"},
        "validation_config": {
            "minimum_stock_count": 3,
            "minimum_total_trades": 30,
            "minimum_coverage_pct": 90,
        },
        "selected_stocks": [
            {"code": audit["code"], "market": audit["market"], "coverage_pct": 100.0, "row_count": 700}
            for audit in audits
        ],
        "validated_stocks": [{"code": audit["code"], "market": audit["market"]} for audit in audits],
        "excluded_stocks": [],
        "market_availability": {
            "KOSPI": {"trading_days": 700, "index_days": 700, "index_coverage_pct": 100.0},
            "KOSDAQ": {"trading_days": 700, "index_days": 700, "index_coverage_pct": 100.0},
        },
        "summary": {
            "selected": int((result.get("status_counts") or {}).get("SELECTED", 0)),
            "baseline_better": int((result.get("status_counts") or {}).get("BASELINE_BETTER", 0)),
            "unresolved": int((result.get("status_counts") or {}).get("UNRESOLVED", 0)),
            "insufficient_sample": int((result.get("status_counts") or {}).get("INSUFFICIENT_SAMPLE", 0)),
            "production_policy_changed": False,
        },
        "performance": {"total_seconds": 1.0, "network_requests": 0},
    }
    checkpoint_store = ExitPolicyValidationCheckpoint(tmp_path)
    checkpoint_store.save_report(report)
    return ExitPolicyResearchAuditor(checkpoint_store, ExitPolicyResearchAuditStore(tmp_path))


def test_research_audit_replays_aggregates_and_decisions(tmp_path: Path) -> None:
    report = _write_fixture(tmp_path).run()
    assert report["available"] is True
    assert report["checks"]["aggregate_replay"]["status"] == "PASS"
    assert report["checks"]["aggregate_replay"]["mismatch_count"] == 0
    assert report["checks"]["decision_replay"]["status"] == "PASS"
    assert report["checks"]["decision_replay"]["mismatch_count"] == 0
    assert report["checks"]["data_coverage"]["status"] == "PASS"
    assert report["checks"]["guardrails"]["status"] == "PASS"
    strategy = report["strategies"][0]
    assert strategy["baseline_sample"]["participating_stocks"] == 4
    assert strategy["leave_one_out"]["runs"] == 4
    assert strategy["leave_one_out"]["same_status"] == 4


def test_research_audit_marks_policy_dependent_entry_counts_as_information_not_fake_pass(tmp_path: Path) -> None:
    report = _write_fixture(tmp_path, candidate_trade_delta=1).run()
    strategy = report["strategies"][0]
    assert strategy["entry_set"]["status"] == "POLICY_DEPENDENT"
    assert strategy["entry_set"]["matched_entry_equality_proven"] is False
    assert report["summary"]["policy_dependent_entry_strategies"] == 1
    assert report["checks"]["entry_set"]["status"] == "INFORMATIONAL"


def test_research_audit_requires_matching_checkpoint(tmp_path: Path) -> None:
    store = ExitPolicyValidationCheckpoint(tmp_path)
    store.save_report({"status": "COMPLETED", "signature": "missing", "period": {"start": "x", "end": "y"}})
    report = ExitPolicyResearchAuditor(store, ExitPolicyResearchAuditStore(tmp_path)).run()
    assert report["available"] is False
    assert report["status"] == "DATA_REQUIRED"
