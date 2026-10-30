"""LIVE-04 local-only explicit Mock E2E; never use real network or market stores."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.jev import synthetic_live_04_demo as demo
from app.jev.review_service import JevManualReviewService
from app.jev.review_models import JEV_USER_FEATURE_DISABLED
from app.jev.typesafe_catalog import TypeSafeJevCatalog

URL = "/api/simulation/jev/synthetic-demo"
HEAD = {"X-StockScope-Synthetic-Demo": "confirmed"}


def _enabled(tmp_path, monkeypatch):
    monkeypatch.setenv(demo.FLAG, "1")
    monkeypatch.setattr(demo, "_root", lambda: tmp_path / "mock-only-isolated")
    demo._ACTIVE.clear()
    return TestClient(app)


def test_demo_disabled_and_public_real_review_stays_off(tmp_path, monkeypatch):
    monkeypatch.delenv(demo.FLAG, raising=False)
    client = TestClient(app)
    status = client.get(URL + "/status")
    assert status.status_code == 200 and status.json()["enabled"] is False
    forbidden = client.post(URL + "/start", headers=HEAD)
    assert forbidden.status_code == 403
    assert client.get("/api/simulation/jev/review-feature").json()["available"] is False
    result = client.post(
        "/api/simulation/jev/reviews",
        json={"capture_id": "arbitrary-real-capture", "sample_index": 0},
    )
    assert result.status_code == 200 and result.json()["reason"] == "FEATURE_NOT_ACTIVATED"
    assert not (tmp_path / "mock-only-isolated").exists()


def test_demo_requires_confirmation_and_localhost(tmp_path, monkeypatch):
    client = _enabled(tmp_path, monkeypatch)
    assert demo.demo_enabled("192.0.2.7", "127.0.0.1") is False
    assert demo.demo_enabled("127.0.0.1", "example.org") is False
    assert client.post(URL + "/start").status_code == 403
    assert client.get(URL + "/status").json()["status"] == "NOT_REQUESTED"
    assert not (tmp_path / "mock-only-isolated").exists()


def test_one_mock_review_is_persisted_and_duplicate_click_is_free(tmp_path, monkeypatch):
    client = _enabled(tmp_path, monkeypatch)
    assert client.get(URL + "/status").json()["status"] == "NOT_REQUESTED"

    created = client.post(URL + "/start", headers=HEAD)
    assert created.status_code == 202, created.text
    job = created.json()
    assert job["status"] == "QUEUED" and job["reused"] is False
    assert job["synthetic_only"] is True
    assert job["sample_index"] == 1
    assert job["actual_provider_calls"] == 0
    persisted = client.get(URL + "/status")
    assert persisted.status_code == 200
    data = persisted.json()
    assert data["status"] == "VALID", data
    assert data["result"]["model_identity_status"] == "MATCHED"
    assert data["result"]["model_returned"] == "jev-mock-returned"
    assert data["result"]["disposition"] == "REVIEW_REQUIRED"
    assert data["result"]["failure_code"] is None
    assert data["result"]["review_id"]
    assert data["result"]["cost_usd"] == 0.0
    assert data["mock_provider_requests"] == 1
    assert data["actual_provider_calls"] == 0
    assert data["job_id"] == job["job_id"]

    repeated = client.post(URL + "/start", headers=HEAD)
    assert repeated.status_code == 202
    assert repeated.json()["reused"] is True
    assert repeated.json()["job_id"] == job["job_id"]
    assert repeated.json()["mock_provider_requests"] == 1

    db = tmp_path / "mock-only-isolated" / "synthetic.db"
    catalog = TypeSafeJevCatalog(db)
    saved = catalog.get_review(data["result"]["review_id"])
    assert saved is not None and saved["status"] == "VALID"
    assert saved["disposition"] == "REVIEW_REQUIRED"
    assert saved["model_returned"] == "jev-mock-returned"

    # Reconstruct a new HTTP client, as if the browser refreshed.
    reloaded = TestClient(app).get(URL + "/status").json()
    assert reloaded["status"] == "VALID"
    assert reloaded["result"]["review_id"] == data["result"]["review_id"]

    # Never touch the user's real operational SQLite or Scanner workflow.
    assert "backend/runtime" not in str(db).replace("\\", "/")
    assert JevManualReviewService(db, feature_status=JEV_USER_FEATURE_DISABLED).feature_status == JEV_USER_FEATURE_DISABLED


def test_interrupted_session_is_not_automatically_retried(tmp_path, monkeypatch):
    client = _enabled(tmp_path, monkeypatch)
    with demo._MUTEX:
        demo._root().mkdir(parents=True)
        demo._save_session({
            "version": demo.VERSION,
            "fixture": demo.FIXTURE_ID,
            "synthetic_only": True,
            "job_id": "interrupted-1",
            "capture_id": "synthetic-only",
            "sample_index": 1,
            "snapshot_hash": "no-operational-data",
            "status": "QUEUED",
            "mock_provider_requests": 0,
        })
    # A fully initialized demo SQLite isn't needed for a pre-reservation crash;
    # only mark catalog pending when the database exists.
    monkeypatch.setattr(TypeSafeJevCatalog, "mark_pending_interrupted", lambda self: 0)
    old = client.get(URL + "/status").json()
    assert old["status"] == "INTERRUPTED"
    assert old["result"]["failure_code"] == "PROCESS_RESTARTED_NO_RETRY"
    reused = client.post(URL + "/start", headers=HEAD).json()
    assert reused["reused"] is True and reused["status"] == "INTERRUPTED"
    assert reused["mock_provider_requests"] == 0
