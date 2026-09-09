from app.market.investor_style import InvestorStyleAnalyzer
from app.strategy.analysis_hub import AnalysisHubBuilder


def base_fundamental():
    return {
        "available": True,
        "latest_metrics": {
            "roe_pct": 17.0,
            "operating_margin_pct": 14.0,
            "debt_ratio_pct": 55.0,
            "current_ratio_pct": 180.0,
            "operating_cash_flow": 170.0,
            "free_cash_flow": 90.0,
            "net_income": 150.0,
        },
        "recent_performance": {
            "revenue_yoy_pct": 14.0,
            "operating_profit_yoy_pct": 28.0,
            "net_income_yoy_pct": 30.0,
        },
        "years": [
            {"year": 2025, "revenue": 1500.0, "net_income": 150.0},
            {"year": 2024, "revenue": 1300.0, "net_income": 125.0},
            {"year": 2023, "revenue": 1120.0, "net_income": 100.0},
        ],
        "axes": {
            "stability": {"status": "GOOD"},
            "cashflow": {"status": "GOOD"},
        },
        "valuation": {
            "eod": {"per": 18.0, "pbr": 1.8},
            "preview": None,
        },
        "data_basis": {"financial": "OpenDART 2026 반기보고서"},
    }


def test_investor_style_returns_ranked_playbooks_and_coverage():
    result = InvestorStyleAnalyzer().analyze(
        fundamental=base_fundamental(),
        relative_strength={"primary_excess_pct": 6.0},
        sector_relative_strength={"available": True, "primary_excess_pct": 3.0},
        event_analysis={"events": []},
        effective={"volume_ratio_20": 1.5, "distance_to_20d_high_pct": -1.0},
        market_context={"regime": "TREND_UP"},
        position_mode="NOT_HELD",
    )
    assert result["available"] is True
    assert len(result["styles"]) == 4
    assert result["top_style"] is not None
    assert result["top_style"]["score"] is not None
    assert all("action_plan" in style for style in result["styles"])
    assert all(style["coverage"]["percent"] <= 100 for style in result["styles"])


def test_unknown_can_slim_institution_does_not_become_zero_score():
    result = InvestorStyleAnalyzer().analyze(
        fundamental=base_fundamental(),
        relative_strength={"primary_excess_pct": 6.0},
        sector_relative_strength={"available": True, "primary_excess_pct": 3.0},
        event_analysis={"events": []},
        effective={"volume_ratio_20": 1.5, "distance_to_20d_high_pct": -1.0},
        market_context={"regime": "TREND_UP"},
        position_mode="NOT_HELD",
    )
    can_slim = next(style for style in result["styles"] if style["code"] == "CAN_SLIM")
    institution = next(cond for cond in can_slim["conditions"] if cond["key"] == "I")
    assert institution["status"] == "UNKNOWN"
    assert can_slim["coverage"]["percent"] < 100
    assert can_slim["score"] is not None


def test_graham_can_be_low_while_buffett_is_higher_for_quality_expensive_company():
    fundamental = base_fundamental()
    fundamental["valuation"] = {"eod": {"per": 32.0, "pbr": 4.0}, "preview": None}
    result = InvestorStyleAnalyzer().analyze(
        fundamental=fundamental,
        relative_strength={"primary_excess_pct": 0.0},
        sector_relative_strength={"available": False},
        event_analysis={"events": []},
        effective={"volume_ratio_20": 1.0, "distance_to_20d_high_pct": -5.0},
        market_context={"regime": "RANGE"},
        position_mode="NOT_HELD",
    )
    by_code = {style["code"]: style for style in result["styles"]}
    assert by_code["BUFFETT"]["score"] > by_code["GRAHAM"]["score"]
    assert any(cond["key"] == "per" and cond["status"] == "FAIL" for cond in by_code["GRAHAM"]["conditions"])


def test_analysis_hub_has_investor_style_navigation_and_signal():
    hub = AnalysisHubBuilder.build(
        position_mode="NOT_HELD",
        risk_gate={"active": False, "message": "정상"},
        risk_analysis={"status": "READY", "summary": "구조 양호"},
        best_regular=type("B", (), {"strategy": type("S", (), {"value": "breakout"})(), "score": 75})(),
        position_action={"available": False},
        relative_strength={"decision": {"archetype": "MARKET_LEADER", "label": "시장 주도형", "summary": "시장보다 강함", "watch_points": []}},
        sector_relative_strength={"available": False, "decision": {}},
        event_analysis={"risk_gate": False, "positive_count": 0, "negative_count": 0, "message": "큰 이벤트 없음"},
        pullback_confirmation={"state": "NOT_PULLBACK", "label": "눌림 아님", "summary": "눌림 아님", "auto_check": {"progress_label": "0/0 조건 확인", "passed": 0, "failed": 0, "pending": 0, "total": 0, "progress_pct": 0, "pending_checks": [], "failed_checks": []}},
        strategy_payloads=[{"strategy": "breakout", "score": 75, "suitability": "높음"}],
        fundamental_analysis={"available": True, "overall": {"status": "GOOD", "label": "양호", "summary": "재무 양호"}, "watch_points": []},
        investor_style_analysis={
            "available": True,
            "top_style": {"fit": "HIGH", "label": "Buffett 스타일", "fit_label": "높음", "summary": "장기 품질 조건이 잘 맞음"},
        },
    )
    assert any(item["key"] == "investor_style" for item in hub["navigation"])
    signal = next(item for item in hub["signals"] if item["key"] == "investor_style")
    assert signal["status"] == "POSITIVE"
    assert "Buffett" in signal["value"]
