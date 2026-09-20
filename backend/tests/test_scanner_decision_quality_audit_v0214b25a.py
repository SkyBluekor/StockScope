from __future__ import annotations

from app.backtest.scanner_quality.decision_quality_audit import audit_repro_payload


def _candidate(rank: int, code: str, *, gap: float, fit: float) -> dict:
    strategy = "support_bounce"
    return {
        "rank": rank,
        "code": code,
        "name": f"N{code}",
        "market": "KOSPI",
        "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE",
        "strategy": strategy,
        "conditions": {"passed": 7, "total": 7, "missing": 0},
        "risk": {"status": "READY", "warning": False, "warnings": []},
        "priority_tier": "READY",
        "entry_gap_pct": gap,
        "strategy_fit_score": fit,
        "final_sort_key": [0, 0, 0, 0, gap, -fit, code],
        "strategy_trace": {
            "selection_method": "test",
            "selected_strategy": strategy,
            "evaluations": [
                {
                    "strategy": strategy,
                    "selector_rank": 1,
                    "selector_eligible": True,
                    "selector_score": 90,
                    "current_evaluated": True,
                    "current_status": "READY",
                    "current_internal_score": 110.0,
                    "passed": 7,
                    "total": 7,
                    "missing": 0,
                    "risk_status": "READY",
                    "risk_warning": False,
                    "selected": True,
                },
                {
                    "strategy": "breakout",
                    "selector_rank": 2,
                    "selector_eligible": True,
                    "selector_score": 80,
                    "current_evaluated": True,
                    "current_status": "WAIT",
                    "current_internal_score": 95.0,
                    "passed": 6,
                    "total": 7,
                    "missing": 1,
                    "risk_status": "READY",
                    "risk_warning": False,
                    "selected": False,
                },
            ],
        },
    }


def test_passes_consistent_top5_style_payload() -> None:
    payload = {
        "audit_version": "repro",
        "scanner_version": "0.21.3.6",
        "analysis_date": "2026-09-18",
        "market_scope": "ALL",
        "candidate_pool_complete": True,
        "candidates": [
            _candidate(1, "000001", gap=0.1, fit=90),
            _candidate(2, "000002", gap=0.3, fit=95),
        ],
    }
    report = audit_repro_payload(payload, top_n=5)
    assert report["verdict"] == "PASS"
    assert report["summary"]["ranking_order_consistent"] is True
    assert report["summary"]["strategy_trace_available_count"] == 2
    assert report["candidates"][0]["why_above_next"]["component"] == "entry_gap_pct"


def test_detects_ready_risk_and_sort_mismatch() -> None:
    first = _candidate(1, "000001", gap=2.0, fit=90)
    second = _candidate(2, "000002", gap=0.1, fit=80)
    first["risk"] = {"status": "CAUTION", "warning": True, "warnings": ["risk"]}
    payload = {
        "scanner_version": "0.21.3.6",
        "analysis_date": "2026-09-18",
        "candidates": [first, second],
    }
    report = audit_repro_payload(payload, top_n=2)
    kinds = {issue["kind"] for issue in report["issues"]}
    assert report["verdict"] == "ERROR"
    assert "READY_WITH_BAD_RISK" in kinds
    assert "FINAL_SORT_ORDER_MISMATCH" in kinds


def test_old_repro_without_strategy_trace_is_review_not_false_error() -> None:
    candidate = _candidate(1, "000001", gap=0.1, fit=90)
    candidate.pop("strategy_trace")
    report = audit_repro_payload({"candidates": [candidate]}, top_n=1)
    assert report["verdict"] == "REVIEW"
    assert any(issue["kind"] == "STRATEGY_TRACE_MISSING" for issue in report["issues"])
