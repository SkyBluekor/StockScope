from __future__ import annotations

from app.backtest.selector import build_condition_state, current_readiness, historical_fit, plain_condition, select_strategy, strategy_guide


def _metrics(*, trades: int, expectancy: float | None, pf: float | None, mdd: float, median: float | None = 0.3):
    return {
        "trades": trades,
        "expectancy_pct": expectancy,
        "profit_factor": pf,
        "max_drawdown_pct": mdd,
        "median_net_return_pct": median,
    }


def _row(strategy: str, label: str, hist_score: float, current_score: float, hist_status: str = "GOOD", current_status: str = "READY"):
    unmet = [] if current_status == "READY" else ["거래량 20일 평균의 1.2배 이상", "20일 고점과 5% 이내"]
    total = 9
    passed = total - len(unmet)
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
            "passed": passed,
            "missing": len(unmet),
            "total": total,
            "unmet": unmet,
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
    assert result["strategy_easy_name"] == "막힌 가격 돌파 노리기"
    assert result["user_action"]["user_task"] == "진입 여부를 결정하세요"
    assert result["recheck_mode"] == "ON_NEXT_ANALYSIS"


def test_selector_separates_current_entry_readiness_from_historical_sample_size():
    rows = [
        _row("breakout", "돌파", hist_score=95, current_score=90, hist_status="INSUFFICIENT"),
        _row("pullback", "눌림목", hist_score=40, current_score=40, hist_status="WEAK", current_status="WATCH"),
    ]
    result = select_strategy(rows, as_of_date="20260910", market_regime="RANGE")
    assert result["strategy"] == "breakout"
    assert result["action"] == "ENTRY_CANDIDATE"
    assert result["user_action"]["user_task"] == "진입 여부를 결정하세요"
    assert result["decision_reason"] == "ENTRY_CANDIDATE"
    assert "과거" in result["reason"]
    assert any("과거" in warning for warning in result["additional_warnings"])


def test_wait_action_makes_user_task_and_recheck_responsibility_explicit():
    rows = [_row("momentum_continuation", "모멘텀 지속", hist_score=80, current_score=65, current_status="WATCH")]
    result = select_strategy(rows, as_of_date="20260910", market_regime="TREND_UP")
    assert result["action"] == "WAIT"
    assert result["user_action"]["user_task"] == "신규 진입하지 않기"
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


def test_condition_detail_includes_current_required_and_status_when_snapshot_is_available():
    from types import SimpleNamespace

    data = SimpleNamespace(
        current_price=56200,
        ma20=55000,
        ma60=53000,
        ma120=50000,
        ma20_slope_pct=0.6,
        rsi14=61.2,
        atr_pct=2.8,
        volume_ratio_20=0.84,
        distance_to_20d_high_pct=3.4,
        support_distance_pct=2.0,
        resistance_distance_pct=4.5,
        support_price=55100,
        resistance_price=57800,
        relative_strength_market_pct=1.2,
        relative_strength_sector_pct=0.4,
        higher_high=True,
        higher_low=True,
        market_regime="TREND_UP",
    )
    detail = plain_condition(
        "거래량 20일 평균의 1.2배 이상",
        data=data,
        technical={"high20": 57800},
        status="FAIL",
    )
    assert detail["status"] == "FAIL"
    assert detail["current_value"] == "0.84배"
    assert detail["required_value"] == "1.20배 이상"


def test_price_condition_uses_actual_close_and_20day_high_when_available():
    from types import SimpleNamespace

    data = SimpleNamespace(
        current_price=56200,
        ma20=None,
        ma60=None,
        ma120=None,
        ma20_slope_pct=None,
        rsi14=None,
        atr_pct=None,
        volume_ratio_20=None,
        distance_to_20d_high_pct=2.77,
        support_distance_pct=None,
        resistance_distance_pct=None,
        support_price=None,
        resistance_price=None,
        relative_strength_market_pct=None,
        relative_strength_sector_pct=None,
        higher_high=None,
        higher_low=None,
        market_regime="RANGE",
    )
    detail = plain_condition(
        "20일 고점과 5% 이내",
        data=data,
        technical={"high20": 57800},
        status="PASS",
    )
    assert "56,200원" in detail["current_value"]
    assert "57,800원" in detail["current_value"]
    assert detail["required_value"] == "20일 고점과 5% 이내"


def test_multi_strategy_current_details_use_latest_snapshot_data_not_undefined_loop_variable():
    """Regression: v0.20.2 raised NameError('data') while building current condition details."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "app" / "backtest" / "multi_strategy.py"
    text = source.read_text(encoding="utf-8")
    assert 'latest_data = latest["strategy_input"]' in text
    assert 'latest_technical = latest["technical"]' in text
    assert 'build_condition_state(' in text
    assert 'data=latest_data' in text
    assert 'technical=latest_technical' in text
    assert 'data=data, technical=snapshot["technical"]' not in text


def test_selector_keeps_all_missing_conditions_for_consistent_counts():
    row = _row("pullback", "눌림목", hist_score=80, current_score=65, current_status="WATCH")
    row["current"]["unmet"] = [
        "거래량 20일 평균의 1.2배 이상",
        "20일 고점과 5% 이내",
        "저점 상승 구조 유지",
        "시장 대비 상대강도 양호",
        "ATR 변동성이 과도하지 않음",
        "현재가가 20일선과 2.5% 이내",
    ]
    result = select_strategy([row], as_of_date="20260910", market_regime="TREND_UP")
    assert len(result["change_conditions"]) == 6
    assert len(result["change_condition_details"]) == 6


def test_short_beginner_strategy_names_are_used_for_results():
    assert strategy_guide("pullback")["easy_name"] == "쉬어간 뒤 다시 오를 때 노리기"
    assert strategy_guide("momentum_continuation")["easy_name"] == "강한 상승 이어가기"
    assert strategy_guide("trend_recovery")["easy_name"] == "상승 흐름 회복 노리기"


def test_abstract_relative_strength_and_low_structure_are_rephrased():
    assert plain_condition("시장 대비 상대강도 양호")["label"] == "시장보다 약하게 움직이지 않기"
    assert plain_condition("저점 상승 구조 유지")["label"] == "가격이 이전보다 더 낮은 곳까지 밀리지 않기"



def test_condition_state_is_single_source_for_pass_missing_and_total_counts():
    from types import SimpleNamespace

    evaluation = SimpleNamespace(
        reasons=["현재가가 20일선 위", "고점 상승 구조"],
        unmet=["거래량 20일 평균의 1.2배 이상"],
        passed=2,
        total=3,
    )
    state = build_condition_state(evaluation)
    assert state["passed"] == 2
    assert state["missing"] == 1
    assert state["total"] == 3
    assert len(state["conditions"]) == 3
    assert len(state["passed_details"]) == 2
    assert len(state["missing_details"]) == 1
    assert state["consistency"]["ok"] is True


def test_condition_state_reports_engine_detail_count_mismatch_without_hiding_it():
    from types import SimpleNamespace

    evaluation = SimpleNamespace(
        reasons=["현재가가 20일선 위"],
        unmet=["거래량 20일 평균의 1.2배 이상"],
        passed=1,
        total=9,
    )
    state = build_condition_state(evaluation)
    assert state["total"] == 2
    assert state["consistency"]["ok"] is False
    assert state["consistency"]["engine_total"] == 9
    assert state["consistency"]["detail_total"] == 2


def test_market_crash_condition_display_matches_trend_down_failure_case():
    from types import SimpleNamespace

    data = SimpleNamespace(
        current_price=100,
        ma20=None,
        ma60=None,
        ma120=None,
        ma20_slope_pct=None,
        rsi14=None,
        atr_pct=None,
        volume_ratio_20=None,
        distance_to_20d_high_pct=None,
        support_distance_pct=None,
        resistance_distance_pct=None,
        support_price=None,
        resistance_price=None,
        relative_strength_market_pct=None,
        relative_strength_sector_pct=None,
        higher_high=None,
        higher_low=None,
        market_regime="TREND_DOWN",
    )
    detail = plain_condition("시장 급락 아님", data=data, technical={}, status="FAIL")
    assert detail["current_value"] == "하락장"
    assert detail["required_value"] == "하락장·패닉이 아님"
    assert detail["status"] == "FAIL"


def test_missing_conditions_remain_primary_reason_when_risk_is_also_caution():
    from types import SimpleNamespace

    evaluation = SimpleNamespace(
        score=78,
        eligible=True,
        passed=7,
        total=9,
        reasons=[f"통과{i}" for i in range(7)],
        unmet=["거래량 20일 평균의 1.2배 이상", "시장 급락 아님"],
        blockers=[],
    )
    state = build_condition_state(evaluation)
    risk_plan = SimpleNamespace(status=SimpleNamespace(value="CAUTION"), reference_only=False)
    current = current_readiness(evaluation=evaluation, risk_plan=risk_plan, condition_state=state)
    assert current["decision_reason"] == "ENTRY_CONDITIONS_MISSING"
    assert current["label"] == "아직 진입 조건 부족"
    assert current["missing"] == 2
    assert current["risk_warning"] is True
    assert any("위험" in warning for warning in current["warnings"])


def test_selector_uses_missing_conditions_as_primary_and_risk_as_secondary_warning():
    row = _row("momentum_continuation", "모멘텀 지속", hist_score=80, current_score=75, current_status="CAUTION")
    row["current"].update({
        "passed": 7,
        "total": 9,
        "missing": 2,
        "risk_warning": True,
        "warnings": ["손절 폭이나 목표 여유 같은 위험 구조에 경고가 있습니다."],
        "unmet": ["거래량 20일 평균의 1.2배 이상", "시장 급락 아님"],
        "unmet_details": [
            plain_condition("거래량 20일 평균의 1.2배 이상", status="FAIL"),
            plain_condition("시장 급락 아님", status="FAIL"),
        ],
    })
    result = select_strategy([row], as_of_date="20260911", market_regime="TREND_DOWN")
    assert result["action"] == "WAIT"
    assert result["action_label"] == "아직 진입 조건 부족"
    assert result["decision_reason"] == "ENTRY_CONDITIONS_MISSING"
    assert result["additional_warnings"]
    assert "2개" in result["headline"]


def test_selector_switches_to_risk_blocked_only_after_strategy_conditions_are_complete():
    row = _row("momentum_continuation", "모멘텀 지속", hist_score=80, current_score=75, current_status="CAUTION")
    row["current"].update({
        "passed": 9,
        "total": 9,
        "missing": 0,
        "risk_warning": True,
        "warnings": ["손절 폭이나 목표 여유 같은 위험 구조에 경고가 있습니다."],
        "unmet": [],
        "unmet_details": [],
        "summary": "전략 조건은 갖춰졌지만 위험 구조에 경고가 있습니다.",
    })
    result = select_strategy([row], as_of_date="20260911", market_regime="TREND_UP")
    assert result["action"] == "WAIT"
    assert result["action_label"] == "위험 때문에 진입 보류"
    assert result["decision_reason"] == "RISK_BLOCKED"
    assert result["additional_warnings"] == []


def test_selector_keeps_current_candidate_when_history_is_weak_but_warns_separately():
    row = _row("trend_following", "추세 추종", hist_score=45, current_score=92, hist_status="WEAK", current_status="READY")
    result = select_strategy([row], as_of_date="20260914", market_regime="TREND_UP")
    assert result["action"] == "ENTRY_CANDIDATE"
    assert result["decision_reason"] == "ENTRY_CANDIDATE"
    assert any("과거" in warning for warning in result["additional_warnings"])
