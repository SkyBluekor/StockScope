from __future__ import annotations

from app.backtest.scanner_quality.no_trade_audit import audit_history_payload


def _candidate(*, state="WATCH", action="WAIT", missing=1, risk_status="READY", warning=False, code="000001"):
    return {
        "code": code,
        "name": "테스트",
        "candidate_state": state,
        "action": action,
        "conditions": {"passed": 5, "total": 6, "missing": missing, "top_missing": []},
        "risk": {"status": risk_status, "warning": warning, "warnings": []},
    }


def _payload(candidates, date="2026-01-02"):
    return {
        "audit_version": "test",
        "scanner_version": "0.21.3.7",
        "valid_date_count": 1,
        "runs": [
            {
                "analysis_date": date,
                "status": "OK",
                "variants": {
                    "BASELINE_TOP3": {
                        "selected_stock_count": len(candidates),
                        "actionable_count": len(candidates),
                        "candidates": candidates,
                    }
                },
            }
        ],
    }


def test_all_watch_day_is_valid_no_trade_behavior():
    report = audit_history_payload(_payload([_candidate(code="000001"), _candidate(code="000002")]))
    assert report["verdict"] == "PASS"
    assert report["summary"]["no_ready_date_count"] == 1
    assert report["summary"]["forced_entry_without_ready_count"] == 0


def test_ready_with_missing_condition_is_error():
    report = audit_history_payload(_payload([_candidate(state="READY", action="ENTRY_CANDIDATE", missing=1)]))
    assert report["verdict"] == "ERROR"
    assert report["summary"]["ready_with_missing_count"] == 1


def test_ready_with_risk_warning_is_error():
    report = audit_history_payload(
        _payload([_candidate(state="READY", action="ENTRY_CANDIDATE", missing=0, risk_status="CAUTION", warning=True)])
    )
    assert report["verdict"] == "ERROR"
    assert report["summary"]["ready_with_bad_risk_count"] == 1


def test_entry_candidate_without_ready_is_error():
    report = audit_history_payload(_payload([_candidate(state="WATCH", action="ENTRY_CANDIDATE", missing=1)]))
    assert report["verdict"] == "ERROR"
    assert report["summary"]["entry_without_ready_count"] == 1


def test_ranking_does_not_promote_missing_condition_watch():
    from app.backtest.candidate_priority import rank_candidates

    candidate = _candidate(state="WATCH", action="WAIT", missing=1, risk_status="READY", warning=False)
    candidate["_strategy_fit_score"] = 120.0
    candidate["entry_risk_guide"] = {}
    ranked, _changes = rank_candidates([candidate])
    assert ranked[0]["candidate_state"] == "WATCH"
    assert ranked[0]["priority"]["tier"] == "NEAR_READY"


def test_ranking_does_not_promote_caution_risk_to_ready():
    from app.backtest.candidate_priority import rank_candidates

    candidate = _candidate(state="WATCH", action="WAIT", missing=0, risk_status="CAUTION", warning=True)
    candidate["_strategy_fit_score"] = 120.0
    candidate["entry_risk_guide"] = {}
    ranked, _changes = rank_candidates([candidate])
    assert ranked[0]["candidate_state"] == "WATCH"
    assert ranked[0]["priority"]["tier"] == "RISK_HOLD"
