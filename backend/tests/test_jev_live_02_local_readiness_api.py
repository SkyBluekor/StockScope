"""LIVE-02 immutable candidate readiness HTTP contract; never call providers."""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient
from app.main import app
from app.jev.synthetic_live_01 import prepare_synthetic_service

EVIDENCE = {
    "provider_policy_checked_at": "MOCK_ONLY",
    "retention_status": "MOCK_ONLY",
    "model_discovery_ref": "MOCK_ONLY",
    "model_discovery_hash": "MOCK_ONLY",
}


def _fixture(tmp_path, monkeypatch):
    db = tmp_path / "synthetic-readiness-only.db"
    _, preview = prepare_synthetic_service(
        db,
        model_requested="jev-latest",
        expected_model_returned="jev-mock-returned",
        evidence=EVIDENCE,
    )
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(db))
    return db, preview


def test_local_readiness_is_readonly_and_never_grants_model_call(tmp_path, monkeypatch):
    db, preview = _fixture(tmp_path, monkeypatch)
    before = db.read_bytes()
    # No ASGI startup: application lifespan legitimately manages other runtime
    # stores; isolate this test to the pure GET endpoint's read-only behavior.
    client = TestClient(app)
    response = client.get("/api/simulation/jev/local-readiness", params={
        "capture_id": preview["capture_id"],
        "sample_index": preview["sample_index"],
    })
    feature = client.get("/api/simulation/jev/review-feature")
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["version"] == "JEV_LIVE_02_LOCAL_READINESS_V1"
    assert record["capture_id"] == preview["capture_id"]
    assert record["identity"]["snapshot_hash"] == preview["snapshot_hash"]
    assert record["identity"]["ticker"] == "999991"
    assert record["sample_index"] == 1
    assert record["status"] in {
        "SOURCE_RIGHTS_HOLD", "LOCAL_ONLY", "NEEDS_EVIDENCE",
        "NOT_ENTRY_CANDIDATE",
    }
    assert record["local_readiness"] in {
        "LOCAL_READY", "LOCAL_ONLY", "NEEDS_EVIDENCE", "NOT_APPLICABLE",
    }
    assert record["provider_eligible"] is False
    assert record["actual_provider_calls"] == 0
    assert record["db_writes"] == 0
    assert record["model_review_executed"] is False
    assert record["transmission_decision"] != "ALLOW"
    assert feature.status_code == 200
    assert feature.json()["available"] is False
    assert db.read_bytes() == before


def test_local_readiness_fails_closed_for_missing_capture_and_sample(tmp_path, monkeypatch):
    db, preview = _fixture(tmp_path, monkeypatch)
    client = TestClient(app)
    missing_capture = client.get("/api/simulation/jev/local-readiness", params={
        "capture_id": "not-a-capture", "sample_index": 1,
    })
    missing_sample = client.get("/api/simulation/jev/local-readiness", params={
        "capture_id": preview["capture_id"], "sample_index": 99,
    })
    invalid = client.get("/api/simulation/jev/local-readiness", params={
        "capture_id": preview["capture_id"], "sample_index": -1,
    })
    assert missing_capture.status_code == 422
    assert missing_capture.json()["detail"]["code"] == "S7_CAPTURE_NOT_COMPLETE"
    assert missing_sample.status_code == 404
    assert missing_sample.json()["detail"]["code"] == "JEV_LIVE02_SAMPLE_NOT_FOUND"
    assert invalid.status_code == 422


def test_first_displayed_candidate_resolves_persisted_zero_index(tmp_path, monkeypatch):
    """Regression: UI rank 1 must resolve sample_index 0, never next stock."""
    db, preview = _fixture(tmp_path, monkeypatch)
    with sqlite3.connect(db) as conn:
        first = conn.execute(
            "SELECT snapshot_hash, ticker FROM prospective_recommendation_sample "
            "WHERE capture_run_id=? AND sample_index=0",
            (preview["capture_id"],),
        ).fetchone()
        second = conn.execute(
            "SELECT snapshot_hash FROM prospective_recommendation_sample "
            "WHERE capture_run_id=? AND sample_index=1",
            (preview["capture_id"],),
        ).fetchone()
    assert first is not None and second is not None
    assert first[0] != second[0]
    before = db.read_bytes()
    client = TestClient(app)
    response = client.get("/api/simulation/jev/local-readiness", params={
        "capture_id": preview["capture_id"], "sample_index": 0,
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["sample_index"] == 0
    assert result["identity"]["snapshot_hash"] == first[0]
    assert result["identity"]["ticker"] == first[1]
    assert result["identity"]["snapshot_hash"] != second[0]
    assert result["actual_provider_calls"] == 0
    assert result["db_writes"] == 0
    assert db.read_bytes() == before


def test_live04r_reports_captured_horizon_original_identity_and_event_provenance(
    tmp_path, monkeypatch,
):
    """Immutable real-capture contract fields are labels, never made-up licenses."""
    db, preview = _fixture(tmp_path, monkeypatch)
    before = db.read_bytes()
    client = TestClient(app)
    response = client.get("/api/simulation/jev/local-readiness", params={
        "capture_id": preview["capture_id"],
        "sample_index": preview["sample_index"],
    })
    assert response.status_code == 200, response.text
    data = response.json()
    contract = data["input_contract"]
    assert contract["horizon_intent"] in ("SHORT", "MEDIUM", "LONG", "LEGACY_UNSPECIFIED")
    assert contract["horizon_support_status"] in (
        "LEGACY_UNSPECIFIED", "EVALUATION_PENDING", "UNSUPPORTED", "SUPPORTED",
    )
    assert contract["original_strategy_identity"] in (
        "CAPTURED_ORIGINAL", "LEGACY_DERIVED_NOT_ORIGINAL", "NOT_VERIFIED",
    )
    if data["baseline_checks"]["strategy"]["status"] == "LEGACY_DERIVED":
        assert contract["original_strategy_identity"] == "LEGACY_DERIVED_NOT_ORIGINAL"
    if data["baseline_checks"]["strategy"]["status"] != "PASS":
        assert contract["original_strategy_identity"] != "CAPTURED_ORIGINAL"
    assert contract["source_first_published_at"] is None
    assert contract["source_publication_evidence"] == "UNVERIFIED"
    assert contract["capture_completed_at"] is not None
    assert data["provider_eligible"] is False
    assert data["model_review_executed"] is False
    assert db.read_bytes() == before


def test_live04r_horizon_is_read_from_capture_not_inferred_from_strategy(
    tmp_path, monkeypatch,
):
    """Switching a controlled fixture to LEGACY only affects local diagnostics."""
    db, preview = _fixture(tmp_path, monkeypatch)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE prospective_capture_run "
            "SET horizon_intent='LEGACY_UNSPECIFIED', horizon_policy_version=NULL "
            "WHERE id=?",
            (preview["capture_id"],),
        )
    before = db.read_bytes()
    result = TestClient(app).get("/api/simulation/jev/local-readiness", params={
        "capture_id": preview["capture_id"],
        "sample_index": preview["sample_index"],
    })
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["input_contract"]["horizon_intent"] == "LEGACY_UNSPECIFIED"
    assert body["input_contract"]["horizon_policy_version"] is None
    assert body["input_contract"]["horizon_support_status"] == "LEGACY_UNSPECIFIED"
    assert body["input_contract"]["horizon_reason_code"] == "HORIZON_NOT_RECORDED"
    assert body["local_v4_status"] != "LOCAL_V4_PROJECTABLE"
    assert body["provider_eligible"] is False
    assert db.read_bytes() == before


def test_live04r_invalid_historical_horizon_is_diagnostic_not_server_error(
    tmp_path, monkeypatch,
):
    db, preview = _fixture(tmp_path, monkeypatch)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE prospective_capture_run SET horizon_intent='NOT_A_REAL_HORIZON' "
            "WHERE id=?",
            (preview["capture_id"],),
        )
    before = db.read_bytes()
    result = TestClient(app).get("/api/simulation/jev/local-readiness", params={
        "capture_id": preview["capture_id"],
        "sample_index": preview["sample_index"],
    })
    assert result.status_code == 200, result.text
    contract = result.json()["input_contract"]
    assert contract["horizon_intent"] == "NOT_A_REAL_HORIZON"
    assert contract["horizon_support_status"] == "UNSUPPORTED"
    assert contract["horizon_reason_code"] == "HORIZON_INTENT_INVALID"
    assert result.json()["provider_eligible"] is False
    assert db.read_bytes() == before
