from types import SimpleNamespace

from app.strategy.analysis_hub import AnalysisHubBuilder


def best(strategy="pullback", score=78):
    return SimpleNamespace(strategy=SimpleNamespace(value=strategy), score=score)


def build(**overrides):
    kwargs = dict(
        position_mode="NOT_HELD",
        risk_gate={"active": False, "message": "정상"},
        risk_analysis={"status": "READY", "summary": "손익 구조 양호"},
        best_regular=best(),
        position_action={"available": False},
        relative_strength={"decision": {"archetype": "OUTPERFORMING", "label": "완만한 시장 우위", "summary": "시장보다 강함", "watch_points": []}},
        sector_relative_strength={"available": True, "decision": {"archetype": "DUAL_LEADER", "label": "시장·업종 동시 주도형", "summary": "업종보다 강함", "watch_points": []}},
        event_analysis={"risk_gate": False, "positive_count": 1, "negative_count": 0, "message": "긍정 이벤트"},
        pullback_confirmation={"state": "REBOUND_CONFIRMED", "label": "반등 확인", "summary": "지지 후 반등", "waiting_for": []},
        strategy_payloads=[{"strategy": "pullback", "score": 78, "suitability": "높음"}],
    )
    kwargs.update(overrides)
    return AnalysisHubBuilder.build(**kwargs)


def test_summary_is_action_first_not_raw_data():
    result = build()
    assert result["primary_action"] == "눌림목 후보 우선 검토"
    assert result["signals"]
    assert result["navigation"][0]["key"] == "summary"


def test_risk_gate_overrides_positive_signals():
    result = build(
        risk_gate={"active": True, "message": "중요 위험"},
        risk_analysis={"status": "HOLD", "summary": "위험 확인"},
    )
    assert result["primary_action"] == "신규 진입 보류"
    assert result["verdict_code"] == "RISK_FIRST"
