from __future__ import annotations

from app.backtest.candidate_priority import build_candidate_priority, rank_candidates


def _candidate(
    code: str,
    *,
    passed: int = 6,
    total: int = 6,
    risk_warning: bool = False,
    risk_status: str = "READY",
    evidence: str = "GOOD",
    gap: float | None = 1.0,
    strategy_fit: float = 80.0,
) -> dict:
    missing = max(0, total - passed)
    guide = {
        "action": {"status": "RISK_BLOCKED" if missing == 0 and risk_warning else ("ENTRY_CANDIDATE" if missing == 0 else "WAIT")},
        "price_rule": {
            "kind": "ABOVE" if gap is not None else "UNAVAILABLE",
            "label": "돌파 확인 가격",
            "gap_pct": gap,
        },
        "rebound_rule": {"available": False, "gap_pct": None},
    }
    return {
        "code": code,
        "name": code,
        "candidate_state": "READY",
        "candidate_label": "old",
        "conditions": {"passed": passed, "total": total, "missing": missing, "top_missing": []},
        "risk": {"status": risk_status, "warning": risk_warning, "warnings": []},
        "historical_fit": {"status": "FAIR", "verified": True},
        "historical_evidence": {
            "status": evidence,
            "verified": evidence != "DATA_UNAVAILABLE",
            "sample_sufficient": evidence in {"GOOD", "FAIR", "WEAK"},
        },
        "entry_risk_guide": guide,
        "_strategy_fit_score": strategy_fit,
    }


def test_v0213_strategy_pass_risk_pass_is_ready() -> None:
    priority = build_candidate_priority(_candidate("A"))
    assert priority["tier"] == "READY"
    assert any(item.startswith("진입 조건 6/6") for item in priority["strengths"])
    assert "Risk 구조 양호" in priority["strengths"]


def test_v0213_history_sample_shortage_does_not_turn_current_ready_into_fail() -> None:
    priority = build_candidate_priority(_candidate("A", evidence="INSUFFICIENT"))
    assert priority["tier"] == "READY"
    assert "3년 과거 표본 부족" in priority["penalties"]


def test_v0213_one_missing_condition_is_near_ready_even_when_history_is_good() -> None:
    priority = build_candidate_priority(_candidate("A", passed=5, total=6, evidence="GOOD"))
    assert priority["tier"] == "NEAR_READY"


def test_v0213_all_conditions_pass_but_risk_block_is_risk_hold() -> None:
    priority = build_candidate_priority(_candidate("A", risk_warning=True, risk_status="CAUTION"))
    assert priority["tier"] == "RISK_HOLD"


def test_v0213_history_good_never_promotes_condition_fail_above_current_ready() -> None:
    ready = _candidate("READY", evidence="FAIR", gap=2.0)
    near = _candidate("NEAR", passed=5, total=6, evidence="GOOD", gap=0.1)
    ranked, _ = rank_candidates([near, ready])
    assert ranked[0]["code"] == "READY"
    assert ranked[1]["priority"]["tier"] == "NEAR_READY"


def test_v0213_risk_hold_never_beats_near_ready_only_because_all_conditions_pass() -> None:
    risk_hold = _candidate("RISK", risk_warning=True, evidence="GOOD", gap=0.0)
    near = _candidate("NEAR", passed=5, total=6, evidence="INSUFFICIENT", gap=2.0)
    ranked, _ = rank_candidates([risk_hold, near])
    assert [row["code"] for row in ranked] == ["NEAR", "RISK"]


def test_v0213_entry_proximity_precedes_history_inside_same_tier() -> None:
    closer_weak = _candidate("CLOSE", evidence="WEAK", gap=0.5)
    farther_good = _candidate("FAR", evidence="GOOD", gap=3.0)
    ranked, _ = rank_candidates([farther_good, closer_weak])
    assert ranked[0]["code"] == "CLOSE"


def test_v0213_history_breaks_tie_after_current_risk_and_entry_proximity() -> None:
    good = _candidate("GOOD", evidence="GOOD", gap=1.0)
    weak = _candidate("WEAK", evidence="WEAK", gap=1.0)
    ranked, _ = rank_candidates([weak, good])
    assert ranked[0]["code"] == "GOOD"


def test_v0213_missing_concrete_entry_reference_is_not_fabricated() -> None:
    priority = build_candidate_priority(_candidate("A", gap=None))
    assert priority["entry_gap_pct"] is None
    assert priority["entry_gap_basis"] is None


def test_v0213_ranking_keeps_previous_rank_for_diagnostics() -> None:
    weak = _candidate("WEAK", evidence="WEAK", gap=1.0)
    good = _candidate("GOOD", evidence="GOOD", gap=1.0)
    ranked, changes = rank_candidates([weak, good])
    assert ranked[0]["code"] == "GOOD"
    assert ranked[0]["priority"]["previous_rank"] == 2
    assert ranked[0]["priority"]["rank_change"] == 1
    assert changes[0]["new_rank"] == 1
    assert changes[0]["previous_rank"] == 2
