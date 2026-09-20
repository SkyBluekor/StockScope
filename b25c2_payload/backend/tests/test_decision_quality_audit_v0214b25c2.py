from __future__ import annotations

from backend.app.backtest.scanner_quality.decision_quality_audit import audit_repro_payload


def _candidate(*, code: str, key: list[object], tie: dict[str, object] | None) -> dict[str, object]:
    row: dict[str, object] = {
        "rank": 1,
        "code": code,
        "name": "TEST",
        "strategy": "pullback",
        "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE",
        "conditions": {"passed": 1, "total": 1, "missing": 0},
        "risk": {"status": "READY", "warning": False},
        "priority_tier": "READY",
        "entry_gap_pct": 0.0,
        "strategy_fit_score": 120.0,
        "final_sort_key": key,
        "strategy_trace": {
            "selected_strategy": "pullback",
            "selection_method": "test",
            "evaluations": [
                {
                    "strategy": "pullback",
                    "selected": True,
                    "selector_rank": 1,
                    "selector_eligible": True,
                    "selector_score": 100,
                    "current_evaluated": True,
                    "current_status": "READY",
                    "current_internal_score": 100.0,
                    "missing": 0,
                    "risk_status": "READY",
                    "risk_warning": False,
                }
            ],
        },
    }
    if tie is not None:
        row["priority_tie"] = tie
    return row


def test_stale_scanner_source_is_not_pass() -> None:
    payload = {
        "audit_version": "v0.21.4-B.2.3.4b",
        "scanner_version": "0.21.3.6",
        "analysis_date": "2026-09-18",
        "candidates": [
            _candidate(code="000810", key=[0, 0, 0, 0, 0.0, -120.0, "000810"], tie=None)
        ],
    }
    report = audit_repro_payload(payload, top_n=1)
    assert report["verdict"] == "ERROR"
    assert report["summary"]["b25c_source_ready"] is False
    assert any(issue["kind"] == "STALE_SCANNER_SOURCE" for issue in report["issues"])


def test_b25c_source_with_tie_metadata_can_pass() -> None:
    payload = {
        "audit_version": "v0.21.4-B.2.3.4b",
        "scanner_version": "0.21.3.7",
        "analysis_date": "2026-09-18",
        "candidates": [
            _candidate(
                code="005490",
                key=[0, 0, 0, 0, 0.0, -120.0, 0, "005490"],
                tie={
                    "group": 1,
                    "size": 1,
                    "focus_order": 0,
                    "focus": False,
                    "breaker": "NONE",
                    "structural_target_distance_pct": 3.87,
                },
            )
        ],
    }
    report = audit_repro_payload(payload, top_n=1)
    assert report["verdict"] == "PASS"
    assert report["summary"]["b25c_source_ready"] is True
