from app.market.investor_style import InvestorStyleAnalyzer


def fundamental():
    return {
        "available": True,
        "latest_metrics": {
            "roe_pct": 14.0,
            "operating_margin_pct": 12.0,
            "debt_ratio_pct": 30.0,
            "current_ratio_pct": 220.0,
            "operating_cash_flow": 180.0,
            "free_cash_flow": 100.0,
            "net_income": 150.0,
        },
        "recent_performance": {
            "revenue_yoy_pct": 18.0,
            "operating_profit_yoy_pct": 25.0,
            "net_income_yoy_pct": 25.0,
        },
        "years": [
            {"year": 2025, "revenue": 1500.0, "net_income": 150.0},
            {"year": 2024, "revenue": 1300.0, "net_income": 120.0},
            {"year": 2023, "revenue": 1100.0, "net_income": 95.0},
        ],
        "axes": {"stability": {"status": "GOOD"}, "cashflow": {"status": "GOOD"}},
        "valuation": {"eod": {"per": 20.0, "pbr": 1.8}, "preview": None},
        "data_basis": {"financial": "OpenDART 최신 공식 실적"},
    }


def analyze(*, pull_state="REBOUND_WAITING", risk=False, volume_ratio=1.5):
    return InvestorStyleAnalyzer().analyze(
        fundamental=fundamental(),
        relative_strength={"primary_excess_pct": 6.0},
        sector_relative_strength={"available": True, "primary_excess_pct": 3.0},
        event_analysis={"events": []},
        effective={"volume_ratio_20": volume_ratio, "distance_to_20d_high_pct": -1.0},
        market_context={"regime": "TREND_UP"},
        position_mode="NOT_HELD",
        pullback_confirmation={"state": pull_state, "label": "반등 신호 대기", "summary": "앱 자동 확인 중"},
        risk_gate={"active": risk, "message": "위험 조건 우선"},
    )


def test_lynch_action_is_app_judgment_not_homework_list():
    result = analyze()
    lynch = next(style for style in result["styles"] if style["code"] == "LYNCH")
    action = lynch["action_plan"]
    assert action["judgments"]
    assert any(item["label"] == "성장 대비 가격" for item in action["judgments"])
    assert "신규 추격은 대기" in action["current_action"]
    assert action["auto_monitor"]
    assert "자동" in action["automation_note"]


def test_rebound_confirmed_changes_entry_stage_to_review():
    result = analyze(pull_state="REBOUND_CONFIRMED")
    lynch = next(style for style in result["styles"] if style["code"] == "LYNCH")
    assert lynch["action_plan"]["entry_judgment"]["value"] == "검토 가능"
    assert lynch["action_plan"]["decision_code"] == "REVIEW"


def test_risk_gate_overrides_high_style_fit():
    result = analyze(risk=True)
    top = result["styles"][0]
    assert top["action_plan"]["decision_code"] == "RISK_FIRST"
    assert "위험 우선" in top["action_plan"]["current_action"]


def test_top_style_exposes_action_summary_for_analysis_hub():
    result = analyze()
    assert result["top_style"]["current_action"]
    assert result["top_style"]["action_summary"]
    assert result["version"] == "0.18.2"


def test_long_horizon_styles_do_not_use_pullback_wait_as_primary_gate():
    result = analyze(pull_state="REBOUND_WAITING")
    for code in ("BUFFETT", "GRAHAM"):
        style = next(item for item in result["styles"] if item["code"] == code)
        entry = style["action_plan"]["entry_judgment"]
        assert entry["timing_importance"] == "보조"
        assert entry["status"] != "WAIT"
        assert "기업 적합도 판단을 이 조건만으로 막지 않습니다" in entry["summary"]


def test_can_slim_uses_its_own_demand_leadership_market_timing():
    ready = analyze(pull_state="REBOUND_WAITING", volume_ratio=1.5)
    can_slim = next(item for item in ready["styles"] if item["code"] == "CAN_SLIM")
    assert can_slim["action_plan"]["entry_judgment"]["progress_label"] == "4/4 핵심 타이밍 확인"
    assert can_slim["action_plan"]["entry_judgment"]["status"] == "REVIEW"

    weak_demand = analyze(pull_state="REBOUND_CONFIRMED", volume_ratio=0.5)
    can_slim = next(item for item in weak_demand["styles"] if item["code"] == "CAN_SLIM")
    entry = can_slim["action_plan"]["entry_judgment"]
    assert entry["status"] == "WAIT"
    assert "거래량·수요" in entry["missing"]
    # A pullback rebound alone cannot override CAN SLIM's own demand timing.
    assert entry["value"] == "핵심 타이밍 대기"
