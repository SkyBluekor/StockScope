from __future__ import annotations

from types import SimpleNamespace

from app.strategy.analysis_hub import AnalysisHubBuilder


def test_action_plan_separates_strategy_fit_from_entry_stage():
    hub = AnalysisHubBuilder.build(
        position_mode="NOT_HELD",
        risk_gate={"active": False, "message": "정상"},
        risk_analysis={
            "status": "READY",
            "summary": "구조는 아직 유지됩니다.",
            "selected_plan": {
                "invalidation_price": 264500,
            },
        },
        best_regular=SimpleNamespace(strategy=SimpleNamespace(value="ma20_rebound"), score=100),
        position_action={"available": False},
        relative_strength={
            "decision": {
                "archetype": "MARKET_LAGGARD",
                "label": "시장 소외형",
                "summary": "시장보다 약합니다.",
                "watch_points": [],
            }
        },
        sector_relative_strength={
            "available": True,
            "decision": {
                "archetype": "DOUBLE_LAGGARD",
                "label": "시장·업종 동시 소외형",
                "summary": "시장과 업종보다 모두 약합니다.",
                "watch_points": [],
            },
        },
        event_analysis={
            "risk_gate": False,
            "positive_count": 1,
            "negative_count": 0,
            "message": "긍정 공시가 있습니다.",
        },
        pullback_confirmation={
            "state": "REBOUND_WAITING",
            "label": "반등 신호 대기",
            "summary": "지지는 유지됐지만 반등 신호가 부족합니다.",
            "anchor": {"name": "20일선/주요 지지", "price": 267800, "distance_pct": 1.2},
            "waiting_for": ["RSI 반등", "반등 거래량"],
            "auto_check": {
                "progress_label": "3/7 조건 확인",
                "passed": 3,
                "failed": 0,
                "pending": 4,
                "total": 7,
                "progress_pct": 43,
                "pending_checks": [
                    {"key": "rsi", "label": "RSI 반등", "status": "WARN", "status_label": "대기", "value": "44.8", "explanation": "회복 전", "source": "KRX_EOD"},
                    {"key": "volume", "label": "반등 거래량", "status": "WARN", "status_label": "대기", "value": "0.73배", "explanation": "평균 이하", "source": "KRX_EOD"},
                ],
                "failed_checks": [],
                "input_hints": [],
                "next_data_note": "다음 EOD에서 재판정",
                "policy": "확률 아님",
            },
        },
        strategy_payloads=[
            {"strategy": "ma20_rebound", "score": 100, "suitability": "매우 높음"},
        ],
        fundamental_analysis={
            "available": True,
            "overall": {"status": "CAUTION", "label": "혼합", "summary": "재무 강점과 약점이 섞였습니다."},
            "watch_points": [],
        },
    )

    action = hub["action_plan"]
    assert hub["version"] == "0.18.2"
    assert action["label"] == "반등 신호 대기"
    assert action["status"] == "WAIT"
    assert action["conflict"]["show"] is True
    assert "진입 신호" in action["conflict"]["summary"]
    assert any("반등 확인 전" in item for item in action["avoid_now"])
    assert any(level["key"] == "support" and level["price"] == 267800 for level in action["price_levels"])
    assert any(level["key"] == "invalidation" and level["price"] == 264500 for level in action["price_levels"])
    assert len(hub["priority_signals"]) == 3
    assert len(hub["other_signals"]) >= 1
    assert all(signal.get("action_hint") for signal in hub["signals"])
