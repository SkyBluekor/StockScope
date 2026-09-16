from __future__ import annotations

from pathlib import Path

from app.backtest.expanded_sample_validation import (
    ExpandedSamplePlanner,
    compare_validation_reports,
    comparison_fingerprint,
    validation_config_from_report,
)
from app.backtest.exit_policy_validation_runner import ExitPolicyValidationCheckpoint
from app.backtest.market_store import HistoricalMarketStore


def _report(selected: list[dict], *, signature: str = "base-sig", max_stocks: int = 20) -> dict:
    return {
        "status": "COMPLETED",
        "signature": signature,
        "period": {"start": "2026-09-01", "end": "2026-09-03"},
        "validation_config": {
            "markets": ["KOSPI", "KOSDAQ"],
            "max_stocks": max_stocks,
            "minimum_coverage_pct": 90.0,
            "initial_capital": 10_000_000,
            "max_holding_days": 20,
            "round_trip_cost_pct": 0.0,
            "minimum_stock_count": 3,
            "minimum_total_trades": 30,
            "post_target2_research_days": 60,
        },
        "market_availability": {"KOSPI": {}, "KOSDAQ": {}},
        "selected_stocks": selected,
        "validated_stocks": [{"code": row["code"], "market": row["market"]} for row in selected],
        "summary": {"selected": 0, "baseline_better": 1, "unresolved": 1, "insufficient_sample": 0},
        "strategies": [
            {"strategy": "TREND_FOLLOWING", "status": "BASELINE_BETTER", "selected_policy_id": "TARGET1_FULL_EXIT"},
            {"strategy": "PULLBACK", "status": "UNRESOLVED", "selected_policy_id": "TARGET1_FULL_EXIT"},
        ],
    }


def test_planner_preserves_base_and_balances_expansion(tmp_path: Path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    days = ["20260901", "20260902", "20260903"]
    for market in ("KOSPI", "KOSDAQ"):
        for day in days:
            rows = [
                {"date": day, "code": f"{market[-1]}{index:05d}", "close": 1000 + index}
                for index in range(12)
            ]
            store.put_stock_day(market, day, rows, stable=True)
            store.put_index_day(market, day, {"date": day, "close": 1000}, stable=True)

    base = [
        {"market": "KOSPI", "code": "I00000"},
        {"market": "KOSDAQ", "code": "Q00000"},
    ]
    plan = ExpandedSamplePlanner(store).plan(_report(base), 20)

    assert plan["ready_to_run"] is True
    assert plan["ready_stock_count"] == 20
    assert plan["selected_stocks"][0]["code"] == "I00000"
    assert plan["selected_stocks"][1]["code"] == "Q00000"
    assert plan["target_market_counts"] == {"KOSDAQ": 10, "KOSPI": 10}


def test_comparison_tracks_status_changes_without_changing_conditions() -> None:
    selected = [{"market": "KOSPI", "code": "000001"}, {"market": "KOSDAQ", "code": "000002"}]
    base = _report(selected, signature="base")
    expanded = _report(selected + [{"market": "KOSPI", "code": "000003"}], signature="expanded", max_stocks=40)
    expanded["strategies"][1] = {
        "strategy": "PULLBACK",
        "status": "BASELINE_BETTER",
        "selected_policy_id": "TARGET1_FULL_EXIT",
    }
    audit = {
        "validation_signature": "base",
        "strategies": [
            {"strategy": "PULLBACK", "leave_one_out": {"status": "SENSITIVE"}},
        ],
    }

    comparison = compare_validation_reports(base, expanded, audit)

    assert comparison["conditions_match"] is True
    assert comparison["same_status_count"] == 1
    assert comparison["changed_status_count"] == 1
    assert comparison["previously_sensitive_changed_status"] == 1
    assert comparison_fingerprint(base) == comparison_fingerprint(expanded)


def test_validation_config_and_report_archive_support_60_stocks(tmp_path: Path) -> None:
    selected = [{"market": "KOSPI", "code": "000001"}, {"market": "KOSDAQ", "code": "000002"}]
    report = _report(selected, signature="archive-me")
    config = validation_config_from_report(report, 60)
    config.validate()
    assert config.max_stocks == 60

    checkpoint = ExitPolicyValidationCheckpoint(tmp_path)
    checkpoint.save_report(report)
    assert checkpoint.load_report("archive-me") == report
    assert checkpoint.load_report() == report
