from __future__ import annotations

from app.backtest.selector import historical_fit, plain_condition, select_strategy, strategy_guide


def _metrics(*, trades: int, expectancy: float | None, pf: float | None, mdd: float, median: float | None = 0.3):
    return {
        "trades": trades,
        "expectancy_pct": expectancy,
        "profit_factor": pf,
        "max_drawdown_pct": mdd,
        "median_net_return_pct": median,
    }


def _row(strategy: str, label: str, hist_score: float, current_score: float, hist_status: str = "GOOD", current_status: str = "READY"):
    return {
        "strategy": strategy,
        "label": label,
        "historical_fit": {
            "status": hist_status,
            "label": "과거 근거 좋음" if hist_status == "GOOD" else "근거 부족",
            "summary": "test",
            "internal_score": hist_score,
        },
        "historical_metrics": {"trades": 20},
        "current": {
            "status": current_status,
            "label": "진입 후보" if current_status == "READY" else "아직 진입 조건 미완성",
            "summary": "test current",
            "unmet": ["거래량 20일 평균의 1.2배 이상", "20일 고점과 5% 이내"],
            "internal_score": current_score,
        },
    }


def test_historical_fit_does_not_promote_tiny_sample():
    fit = historical_fit(_metrics(trades=2, expectancy=8.0, pf=9.0, mdd=-2.0))
    assert fit["status"] == "INSUFFICIENT"
    assert fit["label"] == "근거 부족"


def test_historical_fit_requires_positive_structure_for_good():
    fit = historical_fit(_metrics(trades=20, expectancy=-0.5, pf=0.8, mdd=-8.0))
    assert fit["status"] == "WEAK"


def test_selector_combines_history_and_current_state_instead_of_return_only():
    rows = [
        _row("breakout", "돌파", hist_score=80, current_score=85),
        _row("pullback", "눌림목", hist_score=88, current_score=55, current_status="WATCH"),
    ]
    result = select_strategy(rows, as_of_date="20260910", market_regime="TREND_UP")
    assert result["strategy"] == "breakout"
    assert result["action"] == "ENTRY_CANDIDATE"
    assert result["strategy_easy_name"] == "막혀 있던 가격을 뚫을 때 노리기"
    assert result["user_action"]["user_task"] == "진입 여부를 결정하세요"
    assert result["recheck_mode"] == "ON_NEXT_ANALYSIS"


def test_selector_does_not_enter_when_best_historical_sample_is_insufficient():
    rows = [
        _row("breakout", "돌파", hist_score=95, current_score=90, hist_status="INSUFFICIENT"),
        _row("pullback", "눌림목", hist_score=40, current_score=40, hist_status="WEAK", current_status="WATCH"),
    ]
    result = select_strategy(rows, as_of_date="20260910", market_regime="RANGE")
    assert result["strategy"] == "breakout"
    assert result["action"] == "NEEDS_VALIDATION"
    assert result["user_action"]["user_task"] == "현재 할 일 없음"
    assert "과거" in result["reason"]


def test_wait_action_makes_user_task_and_recheck_responsibility_explicit():
    rows = [_row("momentum_continuation", "모멘텀 지속", hist_score=80, current_score=65, current_status="WATCH")]
    result = select_strategy(rows, as_of_date="20260910", market_regime="TREND_UP")
    assert result["action"] == "WAIT"
    assert result["user_action"]["user_task"] == "현재 할 일 없음"
    assert "다음 분석" in result["user_action"]["stockscope_detail"]
    assert result["change_condition_details"][0]["label"] == "평소보다 거래가 20% 이상 활발해지기"
    assert "자동 계산" in result["change_condition_details"][0]["detail"]


def test_beginner_guides_exist_for_all_ten_strategies():
    strategies = [
        "trend_following", "pullback", "breakout", "support_bounce", "oversold_bounce",
        "range_trading", "momentum_continuation", "volatility_squeeze", "ma20_rebound", "trend_recovery",
    ]
    for strategy in strategies:
        guide = strategy_guide(strategy)
        assert guide["easy_name"]
        assert guide["professional_name"]
        assert len(guide["description"]) >= 10
        assert len(guide["when_to_use"]) >= 10


def test_professional_condition_is_translated_to_beginner_language():
    detail = plain_condition("ATR 3.5% 이하")
    assert detail["label"] == "가격 움직임이 충분히 조용해지기"
    assert "ATR" not in detail["label"]
    assert "StockScope" in plain_condition("거래량 20일 평균의 1.2배 이상")["detail"]
