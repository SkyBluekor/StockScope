"""JEV-B: one-stock V4 question-fit proof, never paid TypeSafe execution."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.jev import _single_stock_review_fit
from app.jev.synthetic_live_01 import prepare_synthetic_service

EVIDENCE = {
    "provider_policy_checked_at": "MOCK_ONLY",
    "retention_status": "MOCK_ONLY",
    "model_discovery_ref": "MOCK_ONLY",
    "model_discovery_hash": "MOCK_ONLY",
}


def test_v4_scope_does_not_relabel_local_result_as_paid_model_candidate():
    checks = [
        (
            {"category": "ENTRY_CANDIDATE", "local_v4_status": "SKIPPED_LOCAL",
             "v4_local_semantic_status": "LOCAL_MATCH"},
            ("LOCAL_ALREADY_RESOLVED", "NO_RESIDUAL_SEMANTIC_REVIEW"),
        ),
        (
            {"category": "ENTRY_CANDIDATE", "local_v4_status": "SKIPPED_LOCAL",
             "v4_local_semantic_status": "LOCAL_CONFLICT"},
            ("LOCAL_ALREADY_RESOLVED", "LOCAL_CONFLICT_ALREADY_DETERMINED"),
        ),
        (
            {"category": "ENTRY_CANDIDATE", "local_v4_status": "SKIPPED_LOCAL",
             "v4_local_semantic_status": "LOCAL_AMBIGUOUS"},
            ("INPUT_CONTRACT_MISMATCH", "LOCAL_SEMANTIC_STATE_NOT_REVIEWABLE"),
        ),
        (
            {"category": "ENTRY_CANDIDATE", "local_v4_status": "LOCAL_V4_PROJECTABLE",
             "v4_local_semantic_status": "RESIDUAL_SEMANTIC_REVIEW"},
            ("SOURCE_RIGHTS_HOLD", "SOURCE_RIGHTS_AND_TIMING_UNVERIFIED"),
        ),
        (
            {"category": "REFERENCE_ONLY", "local_v4_status": "REFERENCE_ONLY"},
            ("NOT_ENTRY_CANDIDATE", "NOT_ENTRY_CANDIDATE"),
        ),
        (
            {"category": "INVALID", "local_v4_status": "BLOCKED_INTEGRITY"},
            ("INPUT_CONTRACT_MISMATCH", "V4_SEMANTIC_INPUT_NOT_READY"),
        ),
    ]
    for diagnostic, expected in checks:
        assert _single_stock_review_fit(diagnostic) == expected


def _fixture(tmp_path, monkeypatch):
    db = tmp_path / "b-fit-only.db"
    _service, preview = prepare_synthetic_service(
        db, model_requested="jev-latest",
        expected_model_returned="jev-mock-returned", evidence=EVIDENCE,
    )
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(db))
    return db, preview


def test_existing_feature_contract_unchanged_without_explicit_candidate(tmp_path, monkeypatch):
    db, _preview = _fixture(tmp_path, monkeypatch)
    before = db.read_bytes()
    response = TestClient(app).get("/api/simulation/jev/review-feature")
    assert response.status_code == 200
    assert response.json() == {
        "execution_mode": "BASELINE_WITH_JEV",
        "feature_status": "DISABLED_VALIDATION_PENDING",
        "available": False,
        "reason": "FEATURE_NOT_ACTIVATED",
    }
    assert db.read_bytes() == before


def test_selected_real_capture_identity_has_no_rights_or_provider_calls(tmp_path, monkeypatch):
    db, preview = _fixture(tmp_path, monkeypatch)
    before = db.read_bytes()
    response = TestClient(app).get("/api/simulation/jev/review-feature", params={
        "capture_id": preview["capture_id"],
        "sample_index": preview["sample_index"],
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["available"] is False
    record = payload["candidate_review"]
    assert record["capture_id"] == preview["capture_id"]
    assert record["sample_index"] == preview["sample_index"]
    assert record["snapshot_hash"] == preview["snapshot_hash"]
    assert record["market"] == "KOSPI"
    assert record["ticker"] == "999991"
    assert record["status"] in {
        "LOCAL_ALREADY_RESOLVED", "SOURCE_RIGHTS_HOLD",
        "INPUT_CONTRACT_MISMATCH", "NOT_ENTRY_CANDIDATE",
    }
    assert record["question_scope"] == "V4_STRATEGY_RELATION_CONFLICT_ONLY"
    assert record["provider_eligible"] is False
    assert record["external_model_calls"] == record["db_writes"] == 0
    assert record["historical_pit_verified"] is False
    assert record["source_rights_approved"] is False
    assert db.read_bytes() == before


@pytest.mark.parametrize("params", [
    {"capture_id": "only-capture"},
    {"sample_index": 1},
    {"capture_id": "anything", "sample_index": -1},
    {"capture_id": "anything", "sample_index": 500},
])
def test_candidate_fit_requires_complete_bounded_identity(tmp_path, monkeypatch, params):
    db, _preview = _fixture(tmp_path, monkeypatch)
    before = db.read_bytes()
    response = TestClient(app).get("/api/simulation/jev/review-feature", params=params)
    assert response.status_code == 422
    assert db.read_bytes() == before


def test_unknown_sample_rejected_without_fabricated_result(tmp_path, monkeypatch):
    db, preview = _fixture(tmp_path, monkeypatch)
    before = db.read_bytes()
    response = TestClient(app).get("/api/simulation/jev/review-feature", params={
        "capture_id": preview["capture_id"], "sample_index": 499,
    })
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "JEV_B_SAMPLE_NOT_FOUND"
    assert db.read_bytes() == before
