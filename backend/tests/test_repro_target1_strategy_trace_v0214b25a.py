from __future__ import annotations

from app.backtest.reproducibility_audit import _candidate_snapshot


def test_repro_snapshot_keeps_target1_cap_metadata_and_strategy_trace() -> None:
    candidate = {
        "code": "008930",
        "name": "한미사이언스",
        "market": "KOSPI",
        "data_date": "2026-09-18",
        "current_price": 48500,
        "candidate_state": "READY",
        "candidate_label": "현재 진입 후보",
        "strategy": "support_bounce",
        "action": "ENTRY_CANDIDATE",
        "conditions": {"passed": 9, "total": 9, "missing": 0},
        "risk": {"status": "READY", "warning": False, "warnings": []},
        "historical_fit": {"status": "WEAK", "verified": True, "trades": 47},
        "entry_risk_guide": {
            "price_rule": {"kind": "RANGE", "label": "전략 조건 가격대", "gap_pct": 0.0},
            "rebound_rule": {"available": False},
            "risk": {
                "entry_reference_price": 48500,
                "invalidation_price": 46050,
                "stop_zone_low": 45450,
                "stop_zone_high": 46600,
                "target1_price": 52212.45,
                "target1_basis": "risk_reward_cap",
                "target1_cap_applied": True,
                "target1_cap_price": 52212.45,
                "structural_target1_price": 61000,
                "structural_target1_basis": "최근 저항 후보",
                "target1_audit": {"policy": "CAP_1_5R", "cap_r": 1.5},
                "target2_price": 62237.48,
                "target2_basis": "extension",
                "rr1": 1.5,
                "rr2": 5.0,
            },
        },
        "_strategy_fit_score": 100.0,
        "_repro_strategy_trace": {
            "selection_method": "test",
            "selected_strategy": "support_bounce",
            "evaluations": [{"strategy": "support_bounce", "selected": True}],
        },
    }

    snapshot = _candidate_snapshot(candidate, 5)
    plan = snapshot["price_plan"]
    assert plan["target1_cap_applied"] is True
    assert plan["target1_cap_price"] == 52212.45
    assert plan["structural_target1_price"] == 61000
    assert plan["structural_target1_basis"] == "최근 저항 후보"
    assert plan["target1_audit"]["policy"] == "CAP_1_5R"
    assert snapshot["strategy_trace"]["selected_strategy"] == "support_bounce"
