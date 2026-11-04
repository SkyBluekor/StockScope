"""B3: actual immutable candidate identity -> trusted Choice -> persisted single request.

Network is exclusively a local httpx.MockTransport. No real TypeSafe call,
market provider request or buy/sell operation can occur in these tests.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.jev import _stock_choice_service
from app.jev.stock_choice_catalog import (
    StockChoiceCatalog, StockChoiceStorageError, migrate_stock_choice,
)
from app.jev.stock_choice_execution import (
    StockChoiceService, TrustedChoiceInput,
)
from app.jev.synthetic_live_01 import prepare_synthetic_service
from app.jev.scanner_shadow_s7 import load_frozen_candidates
from app.jev.stock_review_contract_v1 import DEFAULT_MODEL


EVIDENCE = {
    "provider_policy_checked_at": "MOCK_ONLY",
    "retention_status": "MOCK_ONLY",
    "model_discovery_ref": "MOCK_ONLY",
    "model_discovery_hash": "MOCK_ONLY",
}


def _db(tmp_path):
    db = tmp_path / "jev-b3-local.db"
    _svc, preview = prepare_synthetic_service(
        db, model_requested="jev-latest",
        expected_model_returned="jev-mock-returned", evidence=EVIDENCE,
    )
    return db, preview


def _trusted_input(db, preview):
    pairs = load_frozen_candidates(db, capture_id=preview["capture_id"], limit=500)
    capture, sample = next(
        (c, s) for c, s in pairs if s["sample_index"] == preview["sample_index"]
    )
    return TrustedChoiceInput(
        scope="VERIFIED_STOCK_CHOICE_AI_TRANSFER_V1",
        source_policy_ref="INTERNAL_TEST_AUTHORED_FIELDS_ONLY",
        observed_at_utc="2026-10-30T00:00:00+00:00",
        authored_for_capture=capture["id"],
        authored_for_sample=sample["sample_index"],
        authored_for_snapshot=sample["snapshot_hash"],
        fields={
            "horizon_intent": capture["horizon_intent"],
            "strategy_intent": "Hypothetical strategy note authored by StockScope tests.",
            "review_notes": "A distinct test-only observation is stated as unconfirmed.",
            "internal_risk_rule_description": "Unconfirmed signals require review.",
        },
    )


def _response():
    return {
        "model": DEFAULT_MODEL,
        "answers": {"review_priority": {
            "type": "choice",
            "choice": "CHECK_MISSING_EVIDENCE",
            "confidence": 0.7,
            "probabilities": {
                "CHECK_MISSING_EVIDENCE": 0.7,
                "CHECK_CONFLICTING_SIGNALS": 0.15,
                "CHECK_RISK_CONTEXT": 0.1,
                "NO_DISTINCT_REVIEW_PRIORITY": 0.05,
            },
        }},
        "usage": {"input_tokens": 100, "output_tokens": 22},
    }


def _service(db, preview, *, calls, status=200, evidence=True):
    trusted = _trusted_input(db, preview)
    def resolver(_capture, _sample):
        return trusted if evidence else None
    def handler(req: httpx.Request):
        calls.append(req)
        if status == "timeout":
            raise httpx.ConnectTimeout("fixture only")
        return httpx.Response(status, json=_response())
    return StockChoiceService(
        db, resolver=resolver,
        transport=httpx.MockTransport(handler),
    )


def test_migration_only_creates_choice_objects_and_idempotently(tmp_path):
    db, preview = _db(tmp_path)
    with sqlite3.connect(db) as conn:
        before = {x[0] for x in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    first = migrate_stock_choice(db)
    second = migrate_stock_choice(db)
    assert first == second
    assert first["status"] == "READY"
    with sqlite3.connect(db) as conn:
        after = {x[0] for x in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert after - before == {
            "jev_stock_choice_schema_meta", "jev_stock_choice_review",
        }
    assert preview["capture_id"]


def test_live_readonly_preview_default_blocks_without_rights_and_does_not_write(tmp_path):
    db, preview = _db(tmp_path)
    migrate_stock_choice(db)
    before = db.read_bytes()
    svc = StockChoiceService(db)
    result = svc.preflight(preview["capture_id"], preview["sample_index"])
    assert result["status"] == "NOT_READY"
    assert result["reason_code"] == "CHOICE_SOURCE_RIGHTS_UNVERIFIED"
    assert result["preview"] is None
    assert result["approval_token"] is None
    assert result["real_model_calls"] == 0
    assert result["latest_review"] is None
    assert db.read_bytes() == before


def test_missing_migration_is_blocker_not_implicit_write(tmp_path):
    db, preview = _db(tmp_path)
    before = db.read_bytes()
    output = StockChoiceService(db).preflight(preview["capture_id"],
                                               preview["sample_index"])
    assert output["reason_code"] == "CHOICE_MIGRATION_REQUIRED"
    assert db.read_bytes() == before


def test_real_capture_full_route_fake_transport_one_call_persisted_reloaded(tmp_path, monkeypatch):
    db, preview = _db(tmp_path)
    migrate_stock_choice(db)
    monkeypatch.setenv("JEV_API_KEY", "test-not-a-real-key")
    calls = []
    service = _service(db, preview, calls=calls)
    app.dependency_overrides[_stock_choice_service] = lambda: service
    try:
        client = TestClient(app)
        params = {"capture_id": preview["capture_id"],
                  "sample_index": preview["sample_index"]}
        preflight = client.get("/api/simulation/jev/stock-choice/preview",
                               params=params)
        assert preflight.status_code == 200
        data = preflight.json()
        assert data["status"] == "PREVIEW_READY"
        assert data["candidate"]["snapshot_hash"] == preview["snapshot_hash"]
        assert data["preview"]["model"] == DEFAULT_MODEL
        assert data["approved_for_paid_call"] is False
        assert data["preview"]["state"]["review_scope"] == "AUTHORIZED_CURRENT_REVIEW_PRIORITY_V1"
        assert "999991" not in json.dumps(data["preview"]["state"])
        assert not calls
        post_body = {
            **params, "approval_token": data["approval_token"],
            "request_body_sha256": data["preview"]["request_body_sha256"],
            "explicit_approval": True,
        }
        disapproved = client.post("/api/simulation/jev/stock-choice/reviews",
                                  json={**post_body, "explicit_approval": False})
        assert disapproved.status_code == 409
        assert not calls

        actual = client.post("/api/simulation/jev/stock-choice/reviews",
                             json=post_body)
        assert actual.status_code == 200, actual.text
        output = actual.json()
        assert output["status"] == "VALID" and output["reused"] is False
        assert len(calls) == 1
        assert calls[0].url.host == "api.typesafe.ai"
        assert calls[0].method == "POST"
        assert "Bearer" in calls[0].headers["authorization"]
        assert "999991" not in calls[0].content.decode()
        assert output["review"]["priority_choice"] == "CHECK_MISSING_EVIDENCE"
        assert output["review"]["cost_unknown"] is True
        assert output["review"]["model_returned"] == DEFAULT_MODEL
        assert output["review"]["usage"] == {"input_tokens": 100, "output_tokens": 22}
        assert "approval_token" not in output["review"]
        assert "source_policy_ref" not in json.dumps(output["review"])

        repeat = client.post("/api/simulation/jev/stock-choice/reviews", json=post_body)
        assert repeat.status_code == 200
        assert repeat.json()["reused"] is True
        assert len(calls) == 1
        saved = client.get("/api/simulation/jev/stock-choice/preview",
                           params=params).json()["latest_review"]
        assert saved["id"] == output["review"]["id"]
        assert saved["canonical_capture_id"] == data["candidate"]["capture_id"]
        assert saved["snapshot_hash"] == preview["snapshot_hash"]
        assert saved["status"] == "VALID"
        assert saved["priority_choice"] == "CHECK_MISSING_EVIDENCE"
    finally:
        app.dependency_overrides.pop(_stock_choice_service, None)


def test_wrong_hash_tampered_token_and_unapproved_source_do_not_call(tmp_path, monkeypatch):
    db, preview = _db(tmp_path)
    migrate_stock_choice(db)
    monkeypatch.setenv("JEV_API_KEY", "test-not-a-real-key")
    calls = []
    svc = _service(db, preview, calls=calls)
    ready = svc.preflight(preview["capture_id"], preview["sample_index"])
    kwargs = dict(
        capture_id=preview["capture_id"], sample_index=preview["sample_index"],
        approval_token=ready["approval_token"],
        request_body_sha256=ready["preview"]["request_body_sha256"],
        explicit_approval=True,
    )
    from app.jev.stock_choice_execution import StockChoiceExecutionError
    with pytest.raises(StockChoiceExecutionError) as e1:
        asyncio.run(svc.execute_once(**{**kwargs, "request_body_sha256": "0" * 64}))
    assert e1.value.code == "CHOICE_BODY_CHANGED_SINCE_PREVIEW"
    with pytest.raises(StockChoiceExecutionError) as e2:
        asyncio.run(svc.execute_once(**{**kwargs, "approval_token": "untrusted"}))
    assert e2.value.code == "CHOICE_APPROVAL_REQUIRED"
    not_approved = _service(db, preview, calls=calls, evidence=False)
    with pytest.raises(StockChoiceExecutionError) as e3:
        asyncio.run(not_approved.execute_once(**kwargs))
    assert e3.value.code == "CHOICE_SOURCE_RIGHTS_UNVERIFIED"
    assert calls == []


@pytest.mark.parametrize("status", ["timeout", 429, 529, 422])
def test_unknown_billing_is_terminal_and_never_automatically_retried(
    tmp_path, monkeypatch, status,
):
    db, preview = _db(tmp_path)
    migrate_stock_choice(db)
    monkeypatch.setenv("JEV_API_KEY", "test-not-a-real-key")
    calls = []
    svc = _service(db, preview, calls=calls, status=status)
    ready = svc.preflight(preview["capture_id"], preview["sample_index"])
    kwargs = dict(capture_id=preview["capture_id"], sample_index=preview["sample_index"],
                  approval_token=ready["approval_token"],
                  request_body_sha256=ready["preview"]["request_body_sha256"],
                  explicit_approval=True)
    result = asyncio.run(svc.execute_once(**kwargs))
    assert result["status"] == "UNKNOWN_BILLING"
    assert result["review"]["priority_choice"] is None
    assert result["review"]["error_code"] is not None
    retry = asyncio.run(svc.execute_once(**kwargs))
    assert retry["reused"] is True
    assert retry["status"] == "UNKNOWN_BILLING"
    assert len(calls) == 1


def test_concurrent_approved_clicks_create_at_most_one_model_transport(tmp_path, monkeypatch):
    db, preview = _db(tmp_path)
    migrate_stock_choice(db)
    monkeypatch.setenv("JEV_API_KEY", "test-not-a-real-key")
    calls = []
    svc = _service(db, preview, calls=calls)
    ready = svc.preflight(preview["capture_id"], preview["sample_index"])
    kwargs = dict(capture_id=preview["capture_id"], sample_index=preview["sample_index"],
                  approval_token=ready["approval_token"],
                  request_body_sha256=ready["preview"]["request_body_sha256"],
                  explicit_approval=True)
    async def go():
        return await asyncio.gather(svc.execute_once(**kwargs),
                                    svc.execute_once(**kwargs))
    results = asyncio.run(go())
    assert sorted(x["reused"] for x in results) == [False, True]
    assert len(calls) == 1
    stored = StockChoiceCatalog(db).get_for_candidate(
        capture_id=ready["candidate"]["capture_id"],
        sample_index=ready["candidate"]["sample_index"],
        snapshot_hash=ready["candidate"]["snapshot_hash"],
        market=ready["candidate"]["market"],
        ticker=ready["candidate"]["ticker"])
    assert len(stored) == 1
