"""JEV-ACT2-S1: isolated fake-only V4 request/storage/monitor lifecycle.

Every database lives in tmp_path. No real provider, activation of user-facing
routes, network requests, holdout or existing runtime DB modifications.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import sqlite3

import pytest

from app.jev.review_models import JEV_USER_FEATURE_ACTIVE
from app.jev.review_service import JevManualReviewService
from app.jev.typesafe_canary_v4 import _sample_from_spec
from app.jev.typesafe_canary_v4_fixtures import FIXTURE_SPECS
from app.jev.typesafe_catalog import TypeSafeJevCatalog
from app.jev.typesafe_models import (
    JEV_TYPESAFE_ALLOWED_PAYLOAD_CLASS_V4,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
    JEV_TYPESAFE_PROJECTOR_VERSION_V4,
    JEV_TYPESAFE_STATE_CONTRACT_VERSION_V4,
    JEV_TYPESAFE_ADAPTER_VERSION,
    TypeSafeJevTrialProtocolSpec,
)
from app.jev.typesafe_policy_v4 import JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V4
from app.jev.typesafe_provider import FakeTypeSafeJevProvider
from app.jev.typesafe_questions_v4 import JEV_TYPESAFE_QUESTION_SET_HASH_V4, STRATEGY_RELATION_CONFLICT
from app.jev.typesafe_state_v4 import (
    JEV_TYPESAFE_PROJECTOR_HASH_V4,
    JEV_TYPESAFE_STATE_CONTRACT_HASH_V4,
    route_typesafe_state_v4,
)
from app.prospective.models import digest_json
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.data.migrate_jev_typesafe_v2 import migrate_jev_typesafe


def _db(tmp_path):
    db = tmp_path / "fake_only.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE synthetic_placeholder(id INTEGER PRIMARY KEY)")
    migrate_prospective_store(db)
    migrate_jev_typesafe(db)
    return db


def _synthetic_residual():
    spec = next(x for x in FIXTURE_SPECS if x["expected_local_status"] == "RESIDUAL_SEMANTIC_REVIEW")
    sample = _sample_from_spec(spec)
    assert route_typesafe_state_v4(sample).provider_eligible
    return sample


def _insert_capture(db, *, sample, capture_id="fake-capture", horizon="SHORT"):
    # A complete, isolated synthetic data source with real Prospective tables.
    snap = dict(sample["snapshot"])
    raw = json.dumps(snap, ensure_ascii=False, sort_keys=True)
    digest = digest_json(snap)
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """INSERT INTO prospective_capture_run(
                id,capture_version,source_job_id,status,request_json,
                market_scope,horizon_intent,horizon_policy_version,
                candidate_limit,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (capture_id, "SYNTHETIC_ACT2_FIXTURE", capture_id + "-job",
             "COMPLETE", "{}", "ALL", horizon, "VN_P1_S2_HORIZON_CONTEXT_V1",
             5, "2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z"),
        )
        conn.execute(
            """INSERT INTO prospective_recommendation_sample(
                capture_run_id,sample_index,market,ticker,name,rank,
                strategy,decision_status,candidate_state,action,signal_date,
                snapshot_json,snapshot_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (capture_id, 0, "KOSPI", "000001", "synthetic-only", 1,
             "synthetic", "READY", "READY", "ENTRY_CANDIDATE", "2026-10-01",
             raw, digest, "2026-10-01T00:00:00Z"),
        )
    return capture_id


def _spec(*, budget=0.08):
    return TypeSafeJevTrialProtocolSpec(
        name="isolated fake V4 ACT2 S1",
        provider_id="FAKE",
        model_requested="FAKE-ACT2-S1",
        expected_model_returned="FAKE-ACT2-S1",
        state_contract_version=JEV_TYPESAFE_STATE_CONTRACT_VERSION_V4,
        state_contract_hash=JEV_TYPESAFE_STATE_CONTRACT_HASH_V4,
        projector_version=JEV_TYPESAFE_PROJECTOR_VERSION_V4,
        projector_hash=JEV_TYPESAFE_PROJECTOR_HASH_V4,
        question_contract_version="JEV_TYPESAFE_QUESTIONS_V4",
        question_set_hash=JEV_TYPESAFE_QUESTION_SET_HASH_V4,
        disposition_policy_version=JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
        disposition_policy_hash=JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V4,
        threshold_strategy=0.5,
        horizon_intents=("SHORT", "MEDIUM"),
        recruitment_duration_calendar_days=1,
        max_recruited_candidates=2,
        deadline_seconds=12.0,
        concurrency_cap=1,
        queue_cap=2,
        retry_count=0,
        budget_limit_usd=budget,
        per_call_reservation_usd=0.04,
        source_transmission_approved=False,
        allowed_payload_class=JEV_TYPESAFE_ALLOWED_PAYLOAD_CLASS_V4,
        adapter_version=JEV_TYPESAFE_ADAPTER_VERSION,
    )


def _service(db, *, provider, spec=None, feature=JEV_USER_FEATURE_ACTIVE):
    catalog = TypeSafeJevCatalog(db)
    setting = spec or _spec()
    assert setting.status() == "FROZEN", setting.freeze_gaps()
    protocol = catalog.create_protocol(
        client_request_id="ACT2-S1-SYNTHETIC-ONLY",
        spec=setting,
    )
    catalog.set_activation(protocol["id"], enabled=True, allow_network=False)
    return JevManualReviewService(
        db, feature_status=feature, protocol=protocol,
        provider_override=provider,
    )


@pytest.mark.parametrize(("probability", "expected"), [
    (0.05, "PASS_THROUGH"),
    (0.95, "REVIEW_REQUIRED"),
])
def test_real_fake_provider_request_storage_monitor_and_idempotency(
    tmp_path, probability, expected,
):
    db = _db(tmp_path)
    sample = _synthetic_residual()
    capture = _insert_capture(db, sample=sample)
    before = {
        row[0]: row[1] for row in sqlite3.connect(db).execute(
            "SELECT sample_index,snapshot_hash FROM prospective_recommendation_sample"
        ).fetchall()
    }
    provider = FakeTypeSafeJevProvider(
        probabilities={STRATEGY_RELATION_CONFLICT: probability},
        returned_model="FAKE-ACT2-S1",
    )
    calls = []
    original_review = provider.review
    async def counted(request, *, deadline_seconds):
        calls.append(request)
        return await original_review(request, deadline_seconds=deadline_seconds)
    provider.review = counted
    service = _service(db, provider=provider)
    first = asyncio.run(service.request_review(capture_id=capture))
    assert first["status"] == expected, first
    assert first["reused"] is False
    assert first["review_id"]
    assert len(calls) == 1
    review = service.typesafe.get_review(first["review_id"])
    assert review["status"] == "VALID"
    assert review["disposition"] == expected
    assert review["model_returned"] == "FAKE-ACT2-S1"
    assert review["cost_usd"] == 0.0
    assert review["model_identity_status"] == "MATCHED"
    assert service.typesafe.list_monitor_items(capture)
    again = asyncio.run(service.request_review(capture_id=capture))
    assert again["status"] == expected
    assert again["reused"] is True
    assert again["review_id"] == first["review_id"]
    assert len(calls) == 1
    with sqlite3.connect(db) as conn:
        assert {
            row[0]: row[1] for row in conn.execute(
                "SELECT sample_index,snapshot_hash FROM prospective_recommendation_sample"
            )
        } == before
        assert conn.execute("SELECT COUNT(*) FROM jev_typesafe_review").fetchone()[0] == 1


@pytest.mark.parametrize("mode", ["ERROR", "MALFORMED"])
def test_fake_provider_error_fails_closed_and_never_changes_scanner(tmp_path, mode):
    db = _db(tmp_path)
    capture = _insert_capture(db, sample=_synthetic_residual())
    provider = FakeTypeSafeJevProvider(returned_model="FAKE-ACT2-S1", mode=mode)
    service = _service(db, provider=provider)
    value = asyncio.run(service.request_review(capture_id=capture))
    assert value["status"] == "ERROR", value
    assert value["review_id"]
    assert service.typesafe.get_review(value["review_id"])["status"] == "ERROR"
    assert service.prospective.get_capture(capture)["status"] == "COMPLETE"


def test_fake_provider_not_called_for_legacy_or_disabled_feature(tmp_path):
    db = _db(tmp_path)
    capture = _insert_capture(db, sample=_synthetic_residual(), horizon="LEGACY_UNSPECIFIED")
    class Forbidden:
        async def review(self, *args, **kwargs):
            raise AssertionError("JEV provider must not be called")
    service = _service(db, provider=Forbidden())
    outcome = asyncio.run(service.request_review(capture_id=capture))
    assert outcome["status"] == "NOT_READY"
    assert outcome["reason"] == "SEMANTIC_SOURCE_NOT_READY"
    disabled = JevManualReviewService(
        db, feature_status="DISABLED_VALIDATION_PENDING",
        protocol=service.protocol, provider_override=Forbidden(),
    )
    unavailable = asyncio.run(disabled.request_review(capture_id=capture))
    assert unavailable["status"] == "UNAVAILABLE"
    assert unavailable["reason"] == "FEATURE_NOT_ACTIVATED"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM jev_typesafe_review").fetchone()[0] == 0


def test_abstain_from_valid_existing_storage_is_never_pass_through(tmp_path):
    db = _db(tmp_path)
    service = _service(db, provider=FakeTypeSafeJevProvider(returned_model="FAKE-ACT2-S1"))
    # A real V4 Q1 success returns PASS_THROUGH or REVIEW_REQUIRED; the
    # storage contract additionally permits a provider ABSTAIN disposition.
    service.typesafe.get_review = lambda review_id: {
        "id": review_id, "status": "VALID", "disposition": "ABSTAIN",
    }
    result = service._existing_result(
        recruitment={"review_id": "synthetic-review"},
        baseline_reference=service._baseline_reference(
            requested_capture_id="synthetic", effective_capture_id="synthetic",
            sample_index=0,
        ),
        review_identity="synthetic-identity",
    )
    assert result["status"] == "ABSTAIN"
    assert result["status"] != "PASS_THROUGH"



def test_abstain_post_review_mapping_remains_abstain_in_storage_and_response(
    tmp_path, monkeypatch,
):
    """Synthetic core outcome injection tests the ABSTAIN response boundary.

    The current V4 Q1 threshold policy itself emits PASS_THROUGH/REVIEW_REQUIRED;
    this tests the independent storage contract for an eligible VALID ABSTAIN.
    """
    from types import SimpleNamespace
    from app.jev import review_service as module

    db = _db(tmp_path)
    capture = _insert_capture(db, sample=_synthetic_residual())
    service = _service(db, provider=FakeTypeSafeJevProvider(returned_model="FAKE-ACT2-S1"))

    async def synthetic_abstain(sample, spec, provider):
        return SimpleNamespace(
            disposition="ABSTAIN",
            uncertainty_reason="INSUFFICIENT_EVIDENCE",
            reason_codes=("INSUFFICIENT_EVIDENCE",),
            normalized_response={
                "model": "FAKE-ACT2-S1", "answers": {},
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
            cost_usd=0.0,
            cost_unknown=False,
        )

    monkeypatch.setattr(module, "review_once", synthetic_abstain)
    first = asyncio.run(service.request_review(capture_id=capture))
    assert first["status"] == "ABSTAIN", first
    stored = service.typesafe.get_review(first["review_id"])
    assert stored["status"] == "VALID"
    assert stored["disposition"] == "ABSTAIN"
    repeat = asyncio.run(service.request_review(capture_id=capture))
    assert repeat["status"] == "ABSTAIN"
    assert repeat["reused"] is True
