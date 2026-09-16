from pathlib import Path

from app.backtest.expanded_sample_validation import compare_validation_reports
from app.backtest.exit_policy_validation_runner import (
    ExitPolicyValidationCheckpoint,
    ExitPolicyValidationRunnerConfig,
)


def _config(max_stocks: int) -> ExitPolicyValidationRunnerConfig:
    return ExitPolicyValidationRunnerConfig(
        start_date="2023-09-16",
        end_date="2026-09-16",
        max_stocks=max_stocks,
        initial_capital=10_000_000,
        max_holding_days=20,
        round_trip_cost_pct=0.0,
    )


def test_research_fingerprint_ignores_only_sample_size() -> None:
    base = _config(20)
    expanded = _config(40)
    assert base.signature() != expanded.signature()
    assert base.research_fingerprint() == expanded.research_fingerprint()

    changed = ExitPolicyValidationRunnerConfig(
        start_date=base.start_date,
        end_date=base.end_date,
        max_stocks=40,
        initial_capital=base.initial_capital,
        max_holding_days=40,
        round_trip_cost_pct=base.round_trip_cost_pct,
    )
    assert base.research_fingerprint() != changed.research_fingerprint()


def test_cross_sample_checkpoint_reuses_matching_stock_audits(tmp_path: Path) -> None:
    store = ExitPolicyValidationCheckpoint(tmp_path)
    base = _config(20)
    expanded = _config(40)
    audits = [
        {"market": "KOSPI", "code": "005930", "strategies": []},
        {"market": "KOSDAQ", "code": "035760", "strategies": []},
    ]
    store.save("a" * 20, base, audits)

    rows = store.load_reusable_audits(
        expanded,
        [
            {"market": "KOSPI", "code": "005930"},
            {"market": "KOSDAQ", "code": "035760"},
            {"market": "KOSPI", "code": "000660"},
        ],
    )
    assert [(row["market"], row["code"]) for row in rows] == [
        ("KOSPI", "005930"),
        ("KOSDAQ", "035760"),
    ]


def test_expanded_result_interprets_unresolved_to_baseline_as_strengthened() -> None:
    common = {
        "validation_config": {
            "markets": ["KOSPI", "KOSDAQ"],
            "minimum_coverage_pct": 90,
            "initial_capital": 10_000_000,
            "max_holding_days": 20,
            "round_trip_cost_pct": 0,
            "minimum_stock_count": 3,
            "minimum_total_trades": 30,
            "post_target2_research_days": 60,
        },
        "period": {"start": "2023-09-16", "end": "2026-09-16"},
    }
    base = {
        **common,
        "signature": "b" * 20,
        "validated_stocks": [{}] * 20,
        "summary": {"selected": 0, "baseline_better": 5, "unresolved": 5},
        "strategies": [
            {"strategy": "PULLBACK", "status": "UNRESOLVED", "selected_policy_id": ""},
            {"strategy": "TREND_FOLLOWING", "status": "BASELINE_BETTER", "selected_policy_id": ""},
        ],
    }
    expanded = {
        **common,
        "signature": "c" * 20,
        "validated_stocks": [{}] * 40,
        "summary": {"selected": 0, "baseline_better": 6, "unresolved": 4},
        "strategies": [
            {"strategy": "PULLBACK", "status": "BASELINE_BETTER", "selected_policy_id": ""},
            {"strategy": "TREND_FOLLOWING", "status": "BASELINE_BETTER", "selected_policy_id": ""},
        ],
    }
    comparison = compare_validation_reports(base, expanded)
    assert comparison["outcome"] == "BASELINE_STRENGTHENED"
    assert comparison["transitions"]["UNRESOLVED->BASELINE_BETTER"] == 1
