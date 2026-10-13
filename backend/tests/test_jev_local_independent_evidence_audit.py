"""Local JEV evidence inventory: independent value is never manufactured."""
from __future__ import annotations

from copy import deepcopy

import pytest

from app.jev import local_evidence_audit as audit
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.prospective.models import digest_json


def _pair():
    snapshot = {
        "semantic_source_v2": {
            "conditions": {"items": [
                {"source_condition": "pass-1", "stance": "SUPPORTS"},
            ]},
            "readiness": {"q2_status": "COMPLETE",
                          "local_semantic_status": "LOCAL_MATCH"},
        },
        "risk": {"status": "READY", "warning": False},
        "entry_risk_guide": {"price_rule": {"semantic_role": "STRATEGY_REFERENCE"}},
    }
    capture = {"id": "SYNTHETIC-capture-1", "status": "COMPLETE"}
    sample = {
        "action": "ENTRY_CANDIDATE", "sample_index": 0,
        "snapshot": snapshot, "snapshot_hash": digest_json(snapshot),
    }
    return capture, sample


def test_existing_pass_entry_role_and_risk_never_count_as_new_review(monkeypatch):
    monkeypatch.setattr(
        audit, "assess_frozen_candidate",
        lambda c, s: {"category": "LOCAL_VALIDATED", "codes": []},
    )
    capture, sample = _pair()
    originals = deepcopy((capture, sample))
    result = audit.diagnose_candidate(capture, sample)
    assert result["status"] == "NO_INDEPENDENT_REVIEW_EVIDENCE"
    assert result["new_independent_evidence_count"] == 0
    assert result["review_decision"] is None
    assert result["shadow_evaluation_eligible"] is False
    assert result["provider_status"] == "PROVIDER_HOLD"
    assert result["actual_provider_calls"] == result["db_writes"] == 0
    assert len(result["baseline_evidence_axes"]) == 3
    assert all(not axis["incremental_evidence"]
               for axis in result["baseline_evidence_axes"])
    assert all(axis["frozen_available"] for axis in result["baseline_evidence_axes"])
    assert (capture, sample) == originals
    assert "pass-1" not in str(result)  # never leak market-derived free text


def test_uncontracted_counterevidence_is_not_promoted_to_independent_fact(monkeypatch):
    monkeypatch.setattr(
        audit, "assess_frozen_candidate",
        lambda c, s: {"category": "LEGACY_LIMITED", "codes": []},
    )
    capture, sample = _pair()
    sample["snapshot"]["new_counterevidence"] = {"claim": "BUY", "verified": True}
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    result = audit.diagnose_candidate(capture, sample)
    assert result["status"] == "NO_INDEPENDENT_REVIEW_EVIDENCE"
    assert result["new_independent_evidence_count"] == 0
    assert result["review_decision"] is None
    assert result["shadow_evaluation_eligible"] is False
    assert "BUY" not in str(result)


def test_tampered_snapshot_and_invalid_candidate_fail_closed(monkeypatch):
    capture, sample = _pair()
    sample["snapshot"]["risk"]["warning"] = True
    assert audit.diagnose_candidate(capture, sample)["status"] == "BLOCKED_INTEGRITY"
    assert audit.diagnose_candidate(capture, sample)["reason_code"] == "SNAPSHOT_HASH_MISMATCH"
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    monkeypatch.setattr(
        audit, "assess_frozen_candidate",
        lambda c, s: {"category": "INVALID", "codes": ["POLICY_PIN_MISMATCH"]},
    )
    result = audit.diagnose_candidate(capture, sample)
    assert result["status"] == "BLOCKED_INTEGRITY"
    assert result["review_decision"] is None


def test_reference_and_failed_lookup_never_generate_reviews(monkeypatch, tmp_path):
    capture, sample = _pair()
    sample["action"] = "WAIT"
    assert audit.diagnose_candidate(capture, sample)["status"] == "REFERENCE_ONLY"
    sample["action"] = "ENTRY_CANDIDATE"
    monkeypatch.setattr(
        audit, "assess_frozen_candidate",
        lambda c, s: {"category": "LOCAL_VALIDATED", "codes": []},
    )
    monkeypatch.setattr(audit, "load_frozen_candidates", lambda *a, **kw: [(capture, sample)])
    result = audit.diagnose_capture(tmp_path / "NON_EXISTENT.db", capture_id=capture["id"])
    assert result["total_records"] == 1
    assert result["counts"] == {"NO_INDEPENDENT_REVIEW_EVIDENCE": 1}
    assert result["independent_evidence_ready"] == result["review_opinions_created"] == 0
    assert result["actual_provider_calls"] == result["db_writes"] == 0
    with pytest.raises(DecisionReviewContractError, match="LOCAL_EVIDENCE_SAMPLE_NOT_FOUND"):
        audit.diagnose_capture(tmp_path / "NON_EXISTENT.db", capture_id=capture["id"],
                               sample_index=99)
    with pytest.raises(DecisionReviewContractError, match="LOCAL_EVIDENCE_CAPTURE_ID_REQUIRED"):
        audit.diagnose_capture(tmp_path / "NON_EXISTENT.db", capture_id=None)
