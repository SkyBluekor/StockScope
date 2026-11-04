"""B4: local originally-authored notes on immutable saved candidates.

No actual provider connection. The sole Choice call is httpx.MockTransport.
This does NOT prove legal originality of a user's note or profitability.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.api.jev as jev_api
from app.jev.stock_choice_execution import (
    StockChoiceExecutionError, StockChoiceService,
)
from app.jev.stock_choice_catalog import migrate_stock_choice
from app.jev.stock_choice_authored_b4 import (
    AuthoredEvidenceStore, ChoiceCostPolicy, LocalModelRegistry,
    migrate_authored_b4, RATE_USD_PER_MILLION_INPUT,
)
from app.jev.synthetic_live_01 import prepare_synthetic_service
from app.jev.stock_review_contract_v1 import DEFAULT_MODEL


EVIDENCE = {
    "provider_policy_checked_at": "MOCK_ONLY",
    "retention_status": "MOCK_ONLY",
    "model_discovery_ref": "MOCK_ONLY",
    "model_discovery_hash": "MOCK_ONLY",
}
NOTE = (
    "I independently wonder whether my entry assumptions are clear enough "
    "for this selected candidate, and want to verify my own reasoning."
)
OTHER_NOTE = (
    "My hypothesis about this particular candidate needs a separate "
    "check of uncertain conditions before I act on my own interpretation."
)


def fixture(tmp_path, monkeypatch):
    db = tmp_path / "actual-schema-synthetic-record.db"
    _, p = prepare_synthetic_service(
        db, model_requested="jev-latest",
        expected_model_returned="jev-mock-returned", evidence=EVIDENCE,
    )
    migrate_stock_choice(db)
    migrate_authored_b4(db)
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(db))
    monkeypatch.setenv("STOCKSCOPE_JEV_B4_LOCAL_AUTHORED", "1")
    monkeypatch.setenv("JEV_API_KEY", "fake-in-memory-mocktransport-only")
    svc = StockChoiceService(db)
    cap, sample = svc._candidate(p["capture_id"], p["sample_index"])
    identity = svc._identity(cap, sample)
    return db, p, identity


def save(store, identity, note=NOTE):
    return store.save(identity, note, original_authorship_attested=True,
                      no_third_party_material_attested=True,
                      external_ai_transfer_attested=True)


def registry():
    r = LocalModelRegistry()
    r.confirm_from_provider([{
        "name": DEFAULT_MODEL, "description": "test-only",
        "release_date": "2026-01-01",
    }])
    return r


def _response():
    return {
        "model": DEFAULT_MODEL,
        "answers": {"review_priority": {
            "type": "choice", "choice": "CHECK_MISSING_EVIDENCE",
            "confidence": 0.7,
            "probabilities": {
                "CHECK_MISSING_EVIDENCE": 0.7,
                "CHECK_CONFLICTING_SIGNALS": 0.15,
                "CHECK_RISK_CONTEXT": 0.1,
                "NO_DISTINCT_REVIEW_PRIORITY": 0.05,
            }
        }},
        "usage": {"input_tokens": 252, "output_tokens": 12},
    }


def test_b4_migration_is_explicit_idempotent_and_b3_schema_compatible(tmp_path, monkeypatch):
    db, p, identity = fixture(tmp_path, monkeypatch)
    with sqlite3.connect(db) as cx:
        before = {row[0] for row in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    outcome = migrate_authored_b4(db)
    assert outcome["status"] == "READY"
    assert outcome["writes_to_scanner"] == outcome["external_model_calls"] == 0
    with sqlite3.connect(db) as cx:
        after = {row[0] for row in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert after == before
        cols = {row[1] for row in cx.execute("PRAGMA table_info(jev_stock_choice_review)")}
        assert "cost_basis_ref" in cols
        assert cx.execute(
            "SELECT COUNT(*) FROM prospective_recommendation_sample"
        ).fetchone()[0] > 0


def test_real_capture_authored_note_to_verified_choice_preview_then_one_mock_call(
    tmp_path, monkeypatch,
):
    db, p, identity = fixture(tmp_path, monkeypatch)
    store = AuthoredEvidenceStore(db)
    start = StockChoiceService(db)
    before = start.preflight(p["capture_id"], p["sample_index"])
    assert before["reason_code"] == "CHOICE_SOURCE_RIGHTS_UNVERIFIED"
    registered = save(store, identity)
    assert registered["note_version"] == 1
    assert store.latest(identity)["authored_note"] == NOTE
    r = registry()
    seen = []
    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=_response())
    svc = StockChoiceService(
        db, resolver=store.resolver, model_id=r.active(),
        cost_policy=ChoiceCostPolicy(r), transport=httpx.MockTransport(handler),
    )
    preview = svc.preflight(p["capture_id"], p["sample_index"])
    assert preview["status"] == "PREVIEW_READY", preview
    assert preview["preview"]["cost_status"] == "ESTIMATED"
    assert preview["preview"]["cost_policy"]["provider_hard_billing_limit"] is False
    assert preview["preview"]["cost_policy"]["user_single_call_limit_usd"] == 0.001
    assert NOTE in json.dumps(preview["preview"]["state"])
    assert "999991" not in json.dumps(preview["preview"]["state"])
    assert preview["real_model_calls"] == 0
    assert seen == []
    kwargs = {
        "capture_id": p["capture_id"], "sample_index": p["sample_index"],
        "approval_token": preview["approval_token"],
        "request_body_sha256": preview["preview"]["request_body_sha256"],
        "explicit_approval": True,
    }
    done = asyncio.run(svc.execute_once(**kwargs))
    assert done["status"] == "VALID"
    assert done["review"]["cost_usd"] == pytest.approx(
        252 * RATE_USD_PER_MILLION_INPUT / 1_000_000
    )
    assert done["review"]["cost_unknown"] is False
    assert "ESTIMATE" in done["review"]["cost_basis_ref"]
    assert len(seen) == 1
    assert seen[0].method == "POST"
    wire = seen[0].content.decode("utf-8")
    assert NOTE in wire
    assert "999991" not in wire
    assert "STOCKSCOPE_SIM_DB" not in wire
    dupe = asyncio.run(svc.execute_once(**kwargs))
    assert dupe["reused"] is True
    assert len(seen) == 1
    reload = svc.preflight(p["capture_id"], p["sample_index"])
    assert reload["latest_review"]["id"] == done["review"]["id"]
    assert reload["latest_review"]["priority_choice"] == "CHECK_MISSING_EVIDENCE"


def test_new_note_does_not_reuse_old_note_result_or_duplicate_version(
    tmp_path, monkeypatch,
):
    db, p, identity = fixture(tmp_path, monkeypatch)
    store = AuthoredEvidenceStore(db)
    first = save(store, identity)
    assert save(store, identity)["status"] == "UNCHANGED"
    second = save(store, identity, OTHER_NOTE)
    assert second["note_version"] == 2
    assert first["note_version"] == 1
    assert store.latest(identity)["authored_note"] == OTHER_NOTE
    r = registry()
    policy = ChoiceCostPolicy(r)
    svc = StockChoiceService(db, resolver=store.resolver, model_id=r.active(),
                             cost_policy=policy)
    p2 = svc.preflight(p["capture_id"], p["sample_index"])
    assert p2["status"] == "PREVIEW_READY"
    assert OTHER_NOTE in p2["preview"]["state"]["review_notes"]


@pytest.mark.parametrize("note", [
    "short",
    "I copied the article from https://example.org and want to know the result",
    "I think the price today is 20000원 and I should use it as JEV input",
    "My original note includes an account number 계좌번호 and a password",
    "I summarize a DART 공시 원문 for this model to inspect",
    "x"*381,
])
def test_authored_content_minimal_scope_rejects_obvious_external_material(
    tmp_path, monkeypatch, note,
):
    db,p,identity=fixture(tmp_path, monkeypatch)
    with pytest.raises(StockChoiceExecutionError):
        save(AuthoredEvidenceStore(db), identity, note)
    assert AuthoredEvidenceStore(db).latest(identity) is None


def test_refuse_inferred_authorship_without_all_three_explicit_confirmations(
    tmp_path, monkeypatch,
):
    db,p,identity=fixture(tmp_path, monkeypatch)
    with pytest.raises(StockChoiceExecutionError) as err:
        AuthoredEvidenceStore(db).save(
            identity, NOTE, original_authorship_attested=True,
            no_third_party_material_attested=False,
            external_ai_transfer_attested=True,
        )
    assert err.value.code == "B4_AUTHORED_ATTESTATION_REQUIRED"
    assert AuthoredEvidenceStore(db).latest(identity) is None


def test_no_model_discovery_or_missing_key_cannot_unblock_paid_choice(
    tmp_path, monkeypatch,
):
    db,p,identity=fixture(tmp_path, monkeypatch)
    store=AuthoredEvidenceStore(db)
    save(store, identity)
    r=LocalModelRegistry()
    svc=StockChoiceService(db,resolver=store.resolver,model_id=DEFAULT_MODEL,
                           cost_policy=ChoiceCostPolicy(r))
    assert svc.preflight(p["capture_id"],p["sample_index"])["reason_code"] == "B4_MODEL_NOT_DISCOVERED"
    r.confirm_from_provider([{"name": DEFAULT_MODEL}])
    monkeypatch.delenv("JEV_API_KEY")
    import app.jev.stock_choice_authored_b4 as b4
    monkeypatch.setattr(b4, "load_typesafe_jev_api_key", lambda: None, raising=False)
    from app.jev import typesafe_provider
    monkeypatch.setattr(typesafe_provider, "load_typesafe_jev_api_key", lambda: None)
    assert svc.preflight(p["capture_id"],p["sample_index"])["reason_code"] == "B4_PROVIDER_KEY_MISSING"


def test_b4_authoring_api_is_explicit_and_readonly_verification_never_calls_paid_model(
    tmp_path, monkeypatch,
):
    db,p,identity=fixture(tmp_path, monkeypatch)
    calls=[]
    async def models():
        calls.append("models")
        return [{"name": DEFAULT_MODEL, "description": "test-only",
                 "release_date": "2026-01-01"}]
    monkeypatch.setattr(jev_api, "discover_typesafe_models", models)
    reg=registry()
    # Only the router's dependency is replaced, never TypeSafe's transport.
    service=StockChoiceService(db,resolver=AuthoredEvidenceStore(db).resolver,
                               model_id=DEFAULT_MODEL,cost_policy=ChoiceCostPolicy(reg))
    app.dependency_overrides[jev_api._stock_choice_service]=lambda:service
    try:
        with TestClient(app) as client:
            params={"capture_id":p["capture_id"],"sample_index":p["sample_index"]}
            original_db=db.read_bytes()
            empty=client.get("/api/simulation/jev/stock-choice/authored",params=params)
            assert empty.status_code == 200
            assert empty.json()["status"] == "NOT_REGISTERED"
            assert db.read_bytes() == original_db
            assert calls == []
            bad=client.post("/api/simulation/jev/stock-choice/authored",
                            json={**params,"note":NOTE,
                                  "original_authorship_attested":True,
                                  "no_third_party_material_attested":False,
                                  "external_ai_transfer_attested":True})
            assert bad.status_code == 422
            good=client.post("/api/simulation/jev/stock-choice/authored",
                             json={**params,"note":NOTE,
                                   "original_authorship_attested":True,
                                   "no_third_party_material_attested":True,
                                   "external_ai_transfer_attested":True})
            assert good.status_code == 200,good.text
            assert good.json()["note_version"] == 1
            assert calls == []
            meta=client.get("/api/simulation/jev/stock-choice/authored",params=params).json()
            assert meta["status"] == "STORED"
            assert meta["note"] == NOTE
            assert meta["candidate"]["ticker"] == identity["ticker"]
            before=client.get("/api/simulation/jev/stock-choice/preview",params=params)
            assert before.status_code == 200
            assert before.json()["status"]=="PREVIEW_READY"
            confirmed=client.post("/api/simulation/jev/stock-choice/models/verify")
            assert confirmed.status_code == 200
            assert confirmed.json()["paid_model_calls"] == 0
            assert calls == ["models"]
    finally:
        app.dependency_overrides.pop(jev_api._stock_choice_service,None)


def test_local_feature_disabled_never_records_note_or_calls_models(tmp_path,monkeypatch):
    db,p,identity=fixture(tmp_path,monkeypatch)
    monkeypatch.delenv("STOCKSCOPE_JEV_B4_LOCAL_AUTHORED")
    with TestClient(app) as client:
        q={"capture_id":p["capture_id"],"sample_index":p["sample_index"]}
        old=db.read_bytes()
        response=client.get("/api/simulation/jev/stock-choice/authored",params=q)
        assert response.json()["status"]=="B4_LOCAL_AUTHORING_DISABLED"
        blocked=client.post("/api/simulation/jev/stock-choice/authored",
                            json={**q,"note":NOTE,
                                  "original_authorship_attested":True,
                                  "no_third_party_material_attested":True,
                                  "external_ai_transfer_attested":True})
        assert blocked.status_code==403
        assert client.post("/api/simulation/jev/stock-choice/models/verify").status_code==403
        assert db.read_bytes()==old
