from __future__ import annotations

from app.backtest.candidate_priority import build_candidate_priority, priority_sort_key, rank_candidates
from app.backtest.scanner_quality.decision_quality_audit import audit_repro_payload


def _candidate(code: str, structural: float | None, *, missing: int = 0, fit: float = 120.0) -> dict:
    risk = {
        "entry_reference_price": 100.0,
        "structural_target1_price": structural,
        "structural_target1_basis": "최근 저항 후보" if structural is not None else None,
    }
    return {
        "code": code,
        "name": code,
        "market": "KOSPI",
        "current_price": 100.0,
        "candidate_state": "READY" if missing == 0 else "WATCH",
        "action": "ENTRY_CANDIDATE" if missing == 0 else "WAIT",
        "conditions": {"passed": 7 - missing, "total": 7, "missing": missing},
        "risk": {"status": "READY", "warning": False, "warnings": []},
        "entry_risk_guide": {
            "action": {"status": "ENTRY_CANDIDATE" if missing == 0 else "WAIT"},
            "price_rule": {"kind": "RANGE", "gap_pct": 0.0, "label": "지지 가격 근처 진입 구간"},
            "risk": risk,
        },
        "_strategy_fit_score": fit,
        "_repro_strategy_trace": {
            "selection_method": "test",
            "selected_strategy": "pullback",
            "evaluations": [
                {
                    "strategy": "pullback",
                    "selected": True,
                    "selector_rank": 1,
                    "selector_eligible": True,
                    "selector_score": 100,
                    "current_evaluated": True,
                    "current_status": "READY" if missing == 0 else "WATCH",
                    "current_internal_score": 100.0 if missing == 0 else 85.0,
                    "missing": missing,
                    "risk_status": "READY",
                    "risk_warning": False,
                }
            ],
        },
        "strategy": "pullback",
    }


def _repro_row(candidate: dict, rank: int) -> dict:
    diagnostic = build_candidate_priority(candidate)
    ranked = candidate.get("priority") or {}
    for key in ("tie_group", "tie_size", "tie_focus_order", "tie_focus", "tie_breaker", "strict_rank"):
        if key in ranked:
            diagnostic[key] = ranked[key]
    temp = dict(candidate)
    temp["priority"] = diagnostic
    return {
        "rank": rank,
        "code": candidate["code"],
        "name": candidate["name"],
        "market": candidate["market"],
        "candidate_state": candidate["candidate_state"],
        "action": candidate["action"],
        "conditions": candidate["conditions"],
        "risk": candidate["risk"],
        "strategy": candidate["strategy"],
        "strategy_fit_score": candidate["_strategy_fit_score"],
        "entry_gap_pct": diagnostic.get("entry_gap_pct"),
        "priority_tier": diagnostic.get("tier"),
        "priority_tie": {
            "group": diagnostic.get("tie_group"),
            "size": diagnostic.get("tie_size"),
            "focus_order": diagnostic.get("tie_focus_order"),
            "focus": diagnostic.get("tie_focus"),
            "breaker": diagnostic.get("tie_breaker"),
            "strict_rank": diagnostic.get("strict_rank"),
            "structural_target_distance_pct": diagnostic.get("structural_target_distance_pct"),
            "structural_target_basis": diagnostic.get("structural_target_basis"),
        },
        "strategy_trace": candidate["_repro_strategy_trace"],
        "final_sort_key": list(priority_sort_key(temp)),
        "price_plan": {},
    }


def test_exact_tie_promotes_one_nearest_structural_target_and_preserves_peer_order() -> None:
    candidates = [
        _candidate("000100", 110.0),
        _candidate("000200", 105.0),
        _candidate("000300", 120.0),
    ]
    ranked, _changes = rank_candidates(candidates)
    assert [item["code"] for item in ranked] == ["000200", "000100", "000300"]
    assert ranked[0]["priority"]["tie_focus"] is True
    assert ranked[0]["priority"]["tie_breaker"] == "STRUCTURAL_TARGET_NEAREST_PROMOTE"
    assert ranked[0]["priority"]["structural_target_distance_pct"] == 5.0
    assert ranked[1]["priority"]["tie_focus_order"] == 1
    assert ranked[2]["priority"]["tie_focus_order"] == 1


def test_missing_structural_target_keeps_legacy_code_order() -> None:
    candidates = [_candidate("000300", None), _candidate("000100", None), _candidate("000200", None)]
    ranked, _changes = rank_candidates(candidates)
    assert [item["code"] for item in ranked] == ["000100", "000200", "000300"]
    assert all(item["priority"]["tie_breaker"] == "CODE_STABLE_ORDER" for item in ranked)


def test_tie_rule_never_crosses_existing_priority_boundary() -> None:
    ready_far = _candidate("000900", 140.0, missing=0)
    near_ready_close = _candidate("000001", 101.0, missing=1)
    ranked, _changes = rank_candidates([near_ready_close, ready_far])
    assert [item["code"] for item in ranked] == ["000900", "000001"]
    assert ranked[0]["priority"]["strict_rank"] is True


def test_effective_sort_key_reproduces_promoted_order_and_decision_audit_passes() -> None:
    candidates = [_candidate("000100", 110.0), _candidate("000200", 105.0), _candidate("000300", 120.0)]
    ranked, _changes = rank_candidates(candidates)
    rows = [_repro_row(item, index) for index, item in enumerate(ranked, start=1)]
    assert [row["code"] for row in sorted(rows, key=lambda row: tuple(row["final_sort_key"]))] == [
        item["code"] for item in ranked
    ]
    report = audit_repro_payload(
        {
            "audit_version": "test",
            "scanner_version": "0.21.3.6",
            "analysis_date": "2026-09-18",
            "market_scope": "ALL",
            "candidate_pool_complete": True,
            "candidates": rows,
        },
        top_n=3,
    )
    assert report["verdict"] == "PASS"
    assert report["summary"]["structural_focus_count"] == 1
    assert report["candidates"][0]["why_above_next"]["component"] == "tie_focus_order"
