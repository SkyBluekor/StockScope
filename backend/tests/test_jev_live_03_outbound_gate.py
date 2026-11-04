"""LIVE-03: no external requests, no rights grant, exact byte contract checks."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.jev.scanner_outbound_gate_live_03 import (
    DEFAULT_MODEL, OutboundGateError, _wire_body, diagnose_outbound_candidate,
    inspect_wire_body, verify_http_request_binding,
)
from app.jev.synthetic_live_01 import prepare_synthetic_service
from app.jev.typesafe_provider import TYPESAFE_SYSTEM_ONE_URL
from app.jev.typesafe_state_v4 import project_typesafe_state_v4

EVIDENCE = {
    "provider_policy_checked_at": "MOCK_ONLY",
    "retention_status": "MOCK_ONLY",
    "model_discovery_ref": "MOCK_ONLY",
    "model_discovery_hash": "MOCK_ONLY",
}


def _prepared(tmp_path, monkeypatch):
    db = tmp_path / "live03-synthetic-only.db"
    service, preview = prepare_synthetic_service(
        db, model_requested="jev-latest",
        expected_model_returned="jev-mock-returned", evidence=EVIDENCE,
    )
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(db))
    return db, service, preview


def _v4_body(service, preview):
    samples = service.prospective.list_samples(capture_run_id=preview["capture_id"])
    assert any(s["sample_index"] == preview["sample_index"] for s in samples)
    sample = next(s for s in samples if s["sample_index"] == preview["sample_index"])
    projection = project_typesafe_state_v4({**sample, "horizon_intent": "SHORT"})
    return _wire_body(projection.state, DEFAULT_MODEL)


def test_readonly_endpoint_returns_hold_not_transmission_permission(tmp_path, monkeypatch):
    db, _service, preview = _prepared(tmp_path, monkeypatch)
    before = db.read_bytes()
    client = TestClient(app)  # no lifespan/operational startup
    response = client.get("/api/simulation/jev/outbound-preflight", params={
        "capture_id": preview["capture_id"], "sample_index": preview["sample_index"],
    })
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["snapshot_hash"] == preview["snapshot_hash"]
    assert report["decision"] in {"HOLD", "NOT_APPLICABLE"}
    assert report["execution_status"] == "NOT_AUTHORIZED"
    assert report["provider_eligible"] is False
    assert report["trusted_rights_resolver"] == "NOT_CONFIGURED"
    assert report["actual_provider_calls"] == 0
    assert report["db_writes"] == 0
    assert report["time_authenticity"] == "UNVERIFIED"
    assert db.read_bytes() == before

    missing = client.get("/api/simulation/jev/outbound-preflight", params={
        "capture_id": preview["capture_id"], "sample_index": 404,
    })
    invalid = client.get("/api/simulation/jev/outbound-preflight", params={
        "capture_id": preview["capture_id"], "sample_index": -1,
    })
    assert missing.status_code == 404
    assert invalid.status_code == 422


def test_httpx_wire_bytes_are_distinctly_hashed_and_binding_rejects_changes(
    tmp_path, monkeypatch,
):
    _db, service, preview = _prepared(tmp_path, monkeypatch)
    body = _v4_body(service, preview)
    audit = inspect_wire_body(body)
    request = httpx.Request("POST", TYPESAFE_SYSTEM_ONE_URL, json=body)
    assert audit["model_id"] == DEFAULT_MODEL
    assert audit["field_count"] >= 8
    assert any(f["path"].startswith("state.passed_condition_meanings[")
               and "KRX_STOCK_DAILY" in f["expected_parents"]
               for f in audit["field_verdicts"])
    assert audit["http_body_sha256"] == hashlib.sha256(request.content).hexdigest()
    assert audit["http_body_bytes"] == len(request.content)
    assert audit["outbound_projection_hash"] != audit["http_body_sha256"]
    assert audit["all_actual_parent_revisions_verified"] is False
    assert audit["body_was_transmitted"] is False
    assert verify_http_request_binding(audit, request, expected_model=DEFAULT_MODEL) is None

    edited = deepcopy(body)
    edited["state"]["strategy_intent"]["text"] += " changed"
    with pytest.raises(OutboundGateError, match="LIVE03_HTTP_BINDING_MISMATCH"):
        verify_http_request_binding(
            audit, httpx.Request("POST", TYPESAFE_SYSTEM_ONE_URL, json=edited),
            expected_model=DEFAULT_MODEL,
        )
    with pytest.raises(OutboundGateError, match="LIVE03_HTTP_BINDING_MISMATCH"):
        verify_http_request_binding(
            audit, httpx.Request("POST", "https://example.org/v1/systemone", json=body),
            expected_model=DEFAULT_MODEL,
        )
    with pytest.raises(OutboundGateError, match="LIVE03_HTTP_BINDING_MISMATCH"):
        verify_http_request_binding(audit, request, expected_model="jev-other")
    with pytest.raises(OutboundGateError, match="LIVE03_HTTP_BINDING_MISMATCH"):
        verify_http_request_binding(
            audit, httpx.Request("GET", TYPESAFE_SYSTEM_ONE_URL),
            expected_model=DEFAULT_MODEL,
        )


def test_invalid_v4_shape_and_sensitive_material_fail_before_any_provider(
    tmp_path, monkeypatch,
):
    _db, service, preview = _prepared(tmp_path, monkeypatch)
    body = _v4_body(service, preview)
    unsafe = deepcopy(body)
    unsafe["state"]["strategy_intent"]["text"] = "Bearer sensitive-token"
    with pytest.raises(OutboundGateError, match="LIVE03_SENSITIVE_OUTBOUND_CONTENT"):
        inspect_wire_body(unsafe)

    unknown = deepcopy(body)
    unknown["extra"] = {"raw_market": "private"}
    with pytest.raises(OutboundGateError, match="LIVE03_V4_WIRE_SHAPE_INVALID"):
        inspect_wire_body(unknown)

    with pytest.raises(OutboundGateError, match="LIVE03_MODEL_NOT_PINNED"):
        _wire_body(body["state"], "UNFROZEN")


def test_real_like_candidate_cannot_be_allowed_by_self_claimed_receipts(
    tmp_path, monkeypatch,
):
    _db, service, preview = _prepared(tmp_path, monkeypatch)
    samples = service.prospective.list_samples(capture_run_id=preview["capture_id"])
    sample = next(s for s in samples if s["sample_index"] == preview["sample_index"])
    capture = {
        "id": preview["capture_id"], "horizon_intent": "SHORT",
        "status": "COMPLETE", "actual_data_date": sample["signal_date"],
        "request_json": json.dumps({"selection_policy_id": "SYNTHETIC-ONLY"}),
    }
    # An untrusted receipt/status string must never be consumed as a grant.
    sample["rights_status"] = "VERIFIED_ALLOWED"
    sample["execution_approval_ref"] = "I_APPROVE"
    result = diagnose_outbound_candidate(capture, sample)
    assert result["decision"] == "HOLD"
    assert result["provider_eligible"] is False
    assert result["actual_provider_calls"] == 0
    assert "EXECUTION_APPROVAL_NOT_GRANTED" in result["reason_codes"]
