"""JEV P6-A authored tests: reference visibility is not an AI model verdict."""
from __future__ import annotations

import sqlite3

import pytest

from app.jev import independent_event_reference_p6 as p6


CUTOFF = "2026-10-28T01:00:00+00:00"


def _projection(
    *, event_status="REFERENCE_AVAILABLE", code="068270",
    market="KOSPI", cutoff=CUTOFF, source="OPENDART_DISCLOSURE",
    available_at="2026-10-28T00:30:00+00:00",
):
    item = {
        "event_type": "AUTHORED_EVENT_NO_SENTIMENT",
        "relation_type": "AUTHORED_RELATED",
        "relevance_state": "AUTHORED",
        "quality_state": "USABLE",
        "revision_state": "ORIGINAL",
        "source_kinds": [source],
        "available_at": available_at,
        "assessment_as_of": available_at,
    }
    return {
        "code": code, "market": market, "decision_cutoff": cutoff,
        "projection_hash": "a" * 64,
        "temporal_projection": {
            "mode": "SYSTEM_OBSERVED_AS_OF",
            "decision_cutoff": cutoff,
        },
        "event_evidence": {
            "status": event_status,
            "items": [item] if event_status == "REFERENCE_AVAILABLE" else [],
        },
        "governance": {"claim_scope": "REFERENCE_CONTEXT_AS_OF_ONLY"},
    }


def _read(projection):
    return p6.classify_event_reference(
        projection, code="068270", market="KOSPI",
        cutoff=CUTOFF, naver_provider_kind="developer_center",
    )


def _sample(action="ENTRY_CANDIDATE"):
    return {
        "sample_index": 0, "snapshot_hash": "b" * 64, "market": "KOSPI",
        "ticker": "068270", "action": action,
    }


def _capture(created_at=CUTOFF):
    return {"id": "authored-capture", "created_at": created_at}


def test_observed_reference_is_uncertain_not_inferred_strategy_conflict():
    result = _read(_projection())
    assert result["status"] == "EVIDENCE_UNCERTAIN"
    assert result["reference_count"] == 1
    assert result["source_kinds"] == ["OPENDART_DISCLOSURE"]
    assert result["independent_conflict_proven"] is False
    assert result["review_needed"] is False
    assert result["ai_input_rights"] == "NOT_APPROVED"
    assert "P6_SOURCE_AI_USE_NOT_APPROVED" in result["reason_codes"]


def test_no_observed_reference_never_claims_no_real_world_events():
    result = _read(_projection(event_status="NO_VALIDATED_EVIDENCE"))
    assert result["status"] == "NO_INDEPENDENT_EVIDENCE"
    assert result["reference_count"] == 0
    assert "P6_NO_OBSERVED_REFERENCE_BY_CUTOFF" in result["reason_codes"]


@pytest.mark.parametrize("projection", [
    _projection(code="373220"),
    _projection(market="KOSDAQ"),
    _projection(cutoff="2026-10-28T02:00:00+00:00"),
    _projection(available_at="2026-10-29T00:00:00+00:00"),
    _projection(event_status="EVIDENCE_BLOCKED"),
])
def test_invalid_identity_future_data_or_integrity_fails_closed(projection):
    result = _read(projection)
    assert result["status"] == "EVIDENCE_NOT_USABLE"
    assert result["reference_count"] == 0
    assert result["projection_hash"] is None


def test_news_search_display_permission_does_not_grant_model_ai_use():
    result = _read(_projection(source="NAVER_NEWS"))
    assert result["status"] == "EVIDENCE_UNCERTAIN"
    assert result["ai_input_rights"] == "NOT_APPROVED"
    assert "P6_SOURCE_AI_USE_NOT_APPROVED" in result["reason_codes"]


def test_unknown_source_is_not_implicitly_approved():
    result = _read(_projection(source="UNKNOWN_VENDOR"))
    assert result["ai_input_rights"] == "NOT_APPROVED"
    assert "P6_SOURCE_POLICY_UNVERIFIED" in result["reason_codes"]


def test_non_entry_candidate_does_not_access_event_store(monkeypatch, tmp_path):
    monkeypatch.setattr(p6, "load_frozen_candidates", lambda *a, **k: [
        (_capture(), _sample(action="REFERENCE_ONLY")),
    ])
    result = p6.inspect_frozen_event_reference(
        tmp_path / "does-not-exist.db",
        capture_id="authored-capture", sample_index=0,
    )
    assert result["status"] == "EVIDENCE_NOT_USABLE"
    assert result["reason_codes"] == ["P6_NOT_ENTRY_CANDIDATE"]
    assert result["actual_provider_calls"] == result["db_writes"] == 0


def test_missing_event_tables_fail_closed_and_do_not_modify_db(monkeypatch, tmp_path):
    db = tmp_path / "existing.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE preserved (v INTEGER)")
        conn.execute("INSERT INTO preserved VALUES (123)")
    before = db.read_bytes()
    monkeypatch.setattr(p6, "load_frozen_candidates", lambda *a, **k: [
        (_capture(), _sample()),
    ])
    result = p6.inspect_frozen_event_reference(
        db, capture_id="authored-capture", sample_index=0,
    )
    assert result["status"] == "EVIDENCE_NOT_USABLE"
    assert result["reason_codes"] == ["EVENT_EVIDENCE_SCHEMA_NOT_READY"]
    assert result["decision_cutoff"] == CUTOFF
    assert db.read_bytes() == before
    assert result["actual_provider_calls"] == result["db_writes"] == 0


def test_unverifiable_capture_time_never_borrows_signal_date(monkeypatch, tmp_path):
    monkeypatch.setattr(p6, "load_frozen_candidates", lambda *a, **k: [
        (_capture("2026-10-28 01:00:00"), _sample()),
    ])
    result = p6.inspect_frozen_event_reference(
        tmp_path / "missing.db", capture_id="authored-capture", sample_index=0,
    )
    assert result["status"] == "EVIDENCE_NOT_USABLE"
    assert result["reason_codes"] == ["P6_CAPTURE_CUTOFF_UNVERIFIED"]


def test_missing_sample_does_not_substitute_another_captured_stock(monkeypatch, tmp_path):
    monkeypatch.setattr(p6, "load_frozen_candidates", lambda *a, **k: [
        (_capture(), _sample()),
    ])
    with pytest.raises(ValueError, match="P6_SAMPLE_NOT_FOUND"):
        p6.inspect_frozen_event_reference(
            tmp_path / "missing.db", capture_id="authored-capture", sample_index=1,
        )


def test_actual_endpoint_never_sends_provider_requests(monkeypatch, tmp_path):
    import app.api.jev as api
    monkeypatch.setattr(api, "_db", lambda: tmp_path / "unused.db")
    monkeypatch.setattr(p6, "load_frozen_candidates", lambda *a, **k: [
        (_capture(), _sample()),
    ])
    response = api.jev_independent_event_reference("authored-capture", 0)
    assert response["capture_id"] == "authored-capture"
    assert response["status"] == "EVIDENCE_NOT_USABLE"
    assert response["external_model_call_allowed"] is False
    assert response["model_review_executed"] is False
    assert response["actual_provider_calls"] == response["db_writes"] == 0
