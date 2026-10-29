"""LIVE-02 immutable candidate readiness HTTP contract; never call providers."""
from __future__ import annotations

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
        "capture_id": preview["capture_id"], "sample_index": 0,
    })
    assert missing_capture.status_code == 422
    assert missing_capture.json()["detail"]["code"] == "S7_CAPTURE_NOT_COMPLETE"
    assert missing_sample.status_code == 404
    assert missing_sample.json()["detail"]["code"] == "JEV_LIVE02_SAMPLE_NOT_FOUND"
    assert invalid.status_code == 422
