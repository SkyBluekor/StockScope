from __future__ import annotations

from app.backtest.interpreter import build_problem_solver
from app.backtest.models import BacktestConfig


def _config(start: str = "2025-09-10", end: str = "2026-09-10") -> BacktestConfig:
    return BacktestConfig(code="066570", market="KOSPI", start_date=start, end_date=end)


def _summary(*, trades=4, wins=1, expectancy=-2.46, pf=0.44, mdd=-16.64):
    return {
        "trades": trades,
        "wins": wins,
        "losses": max(0, trades - wins),
        "win_rate_pct": None if trades == 0 else wins / trades * 100,
        "expectancy_pct": expectancy,
        "average_net_return_pct": expectancy,
        "profit_factor": pf,
        "max_drawdown_pct": mdd,
        "max_consecutive_losses": 3,
    }


def test_low_sample_prioritizes_more_evidence_instead_of_strategy_failure():
    result = {
        "summary": _summary(),
        "entry_timing_research": [],
        "market_regime_performance": [],
        "trades": [],
    }
    solver = build_problem_solver(result, _config())
    assert solver["status"] == "NEEDS_MORE_EVIDENCE"
    assert solver["label"] == "이 종목에서 전략 근거 부족"
    assert solver["problems"][0]["id"] == "LOW_SAMPLE"
    assert solver["next_actions"][0]["type"] == "RERUN_PERIOD"
    assert solver["next_actions"][0]["years"] == 3
    assert "전략 자체" in solver["summary"]


def test_timing_result_is_only_research_candidate_when_sample_is_small():
    result = {
        "summary": _summary(),
        "entry_timing_research": [
            {"entry_timing": "3/7", "trades": 17, "expectancy_pct": 0.89, "profit_factor": 1.26},
            {"entry_timing": "4/7", "trades": 14, "expectancy_pct": 2.57, "profit_factor": 1.96},
            {"entry_timing": "5/7", "trades": 10, "expectancy_pct": 1.29, "profit_factor": 1.7},
        ],
        "market_regime_performance": [],
        "trades": [],
    }
    solver = build_problem_solver(result, _config())
    timing_problem = next(item for item in solver["problems"] if item["id"] == "TIMING_CANDIDATE")
    assert "4/7" in timing_problem["evidence"]
    assert "규칙 변경이 아니라 추가 검증 후보" in timing_problem["solution"]
    assert solver["strategy_candidate"] is None


def test_regime_difference_explains_what_problem_to_verify_next():
    result = {
        "summary": _summary(),
        "entry_timing_research": [],
        "market_regime_performance": [
            {"key": "RANGE", "trades": 3, "expectancy_pct": -5.83},
            {"key": "TREND_UP", "trades": 1, "expectancy_pct": 7.61},
        ],
        "trades": [],
    }
    solver = build_problem_solver(result, _config())
    problem = next(item for item in solver["problems"] if item["id"] == "REGIME_SENSITIVITY")
    assert "횡보장" in problem["evidence"]
    assert "상승장" in problem["evidence"]
    assert "즉시" in problem["solution"]


def test_stop_dominance_is_detected_but_does_not_auto_change_stop_rule():
    trades = [
        {"exit_reason": "STOP", "entry_price": 100, "stop_price": 95},
        {"exit_reason": "STOP_GAP", "entry_price": 100, "stop_price": 94},
        {"exit_reason": "STOP", "entry_price": 100, "stop_price": 96},
        {"exit_reason": "TARGET_1", "entry_price": 100, "stop_price": 95},
    ]
    result = {
        "summary": _summary(),
        "entry_timing_research": [],
        "market_regime_performance": [],
        "trades": trades,
    }
    solver = build_problem_solver(result, _config())
    problem = next(item for item in solver["problems"] if item["id"] == "STOP_DOMINANCE")
    assert "3건" in problem["evidence"]
    assert "손절 거리별 별도 검증" in problem["solution"]


def test_strategy_candidate_requires_larger_repeated_sample():
    result = {
        "summary": _summary(trades=40, wins=22, expectancy=0.4, pf=1.1, mdd=-8.0),
        "entry_timing_research": [
            {"entry_timing": "4/7", "trades": 24, "expectancy_pct": 2.1, "profit_factor": 1.5},
            {"entry_timing": "5/7", "trades": 23, "expectancy_pct": 1.0, "profit_factor": 1.3},
        ],
        "market_regime_performance": [],
        "trades": [],
    }
    solver = build_problem_solver(result, _config(start="2022-09-10", end="2026-09-10"))
    assert solver["strategy_candidate"] is not None
    assert "4/7" in solver["strategy_candidate"]["title"]
    assert "즉시 바꾸지" in solver["strategy_candidate"]["next_validation"]


def test_three_year_result_still_low_sample_recommends_five_year_rerun():
    result = {
        "summary": _summary(trades=7, wins=3, expectancy=-0.4, pf=0.8, mdd=-10.0),
        "entry_timing_research": [],
        "market_regime_performance": [],
        "trades": [],
    }
    solver = build_problem_solver(result, _config(start="2023-09-10", end="2026-09-10"))
    action = next(item for item in solver["next_actions"] if item["id"] == "EXPAND_PERIOD")
    assert action["years"] == 5
