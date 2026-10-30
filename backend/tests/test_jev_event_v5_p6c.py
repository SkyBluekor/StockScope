"""P6-C full synthetic V5 wire/fake execution and live-data HOLD routing."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.jev import event_v5, synthetic_event_v5_demo as demo
from app.jev.typesafe_provider import FakeTypeSafeJevProvider


def _provider(p=0.81, **kw):
    return FakeTypeSafeJevProvider(
        probabilities={event_v5.QUESTION_ID: p},
        returned_model=event_v5.TEST_MODEL_ID,
        **kw,
    )


def _run(provider=None):
    return asyncio.run(event_v5.review_synthetic_once(
        event_v5.authored_synthetic_fixture(),
        provider or _provider(),
    ))


def test_v5_synthetic_fixture_is_frozen_distinct_from_v4():
    fake = event_v5.authored_synthetic_fixture()
    request, review_id = event_v5.build_event_v5_request(fake)
    assert fake["fixture_id"].endswith("999992")
    assert "event_revision" in request["state"]["unresolved_event_assertion"]
    assert list(request["questions"]) == [event_v5.QUESTION_ID]
    assert request["model"] == event_v5.TEST_MODEL_ID
    assert "strategy_relation_conflict" not in request["questions"]
    assert len(review_id) == 64
    assert len(json.dumps(request).encode("utf-8")) < 8192


@pytest.mark.parametrize("change", [
    {"synthetic_only": False},
    {"capture_id": "a-real-capture"},
    {"event_projection_hash": "0" * 64},
    {"sample_index": 1},
])
def test_real_or_modified_data_cannot_enter_synthetic_wire(change):
    fixture = event_v5.authored_synthetic_fixture()
    fixture.update(change)
    with pytest.raises(event_v5.EventV5ContractError, match="P6C_SYNTHETIC_FIXTURE_IDENTITY_REQUIRED"):
        event_v5.build_event_v5_request(fixture)


@pytest.mark.parametrize("probability,expected", [
    (0.81, "REVIEW_REQUIRED"), (0.20, "PASS_THROUGH"),
    (event_v5.TEST_THRESHOLD, "REVIEW_REQUIRED"),
])
def test_fake_provider_roundtrip_valid_response_and_policy(probability, expected):
    result = _run(_provider(probability))
    assert result["status"] == "VALID"
    assert result["disposition"] == expected
    assert result["model_returned"] == event_v5.TEST_MODEL_ID
    assert result["question_hash"] == event_v5.QUESTION_HASH
    assert result["policy_hash"] == event_v5.POLICY_HASH
    assert result["mock_provider_calls"] == 1
    assert result["actual_provider_calls"] == 0


@pytest.mark.parametrize("mode", ["MALFORMED", "ERROR"])
def test_fake_provider_bad_response_abstains(mode):
    result = _run(_provider(mode=mode))
    assert result["status"] == "ERROR"
    assert result["disposition"] == "ABSTAIN"
    assert result["failure_code"] == "P6C_SYNTHETIC_MODEL_RESPONSE_REJECTED"


def test_fake_provider_wrong_model_abstains():
    result = _run(FakeTypeSafeJevProvider(
        probabilities={event_v5.QUESTION_ID: 0.8},
        returned_model="ANOTHER-FAKE-MODEL",
    ))
    assert result["disposition"] == "ABSTAIN"


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), -0.01, 1.01])
def test_fake_provider_bad_probabilities_abstain(probability):
    # Fake provider validates its own payload; invalid test data is rejected.
    result = _run(_provider(probability))
    assert result["status"] == "ERROR"


def test_provider_not_named_fake_cannot_execute(monkeypatch):
    class NotFake:
        async def review(self, request, *, deadline_seconds):
            raise AssertionError("must never call non-fake provider")
    with pytest.raises(event_v5.EventV5ContractError, match="P6C_FAKE_PROVIDER_ONLY"):
        asyncio.run(event_v5.review_synthetic_once(
            event_v5.authored_synthetic_fixture(), NotFake(),
        ))


@pytest.mark.parametrize("event_status,candidate,expected", [
    ("NO_INDEPENDENT_EVIDENCE", False, "SKIPPED_NO_EVIDENCE"),
    ("EVIDENCE_COMPATIBLE", False, "SKIPPED_LOCALLY_RESOLVED"),
    ("EVIDENCE_CONFLICT", False, "LOCAL_REVIEW_REQUIRED"),
    ("EVIDENCE_NOT_USABLE", False, "BLOCKED_EVIDENCE"),
    ("EVIDENCE_UNCERTAIN", True, "REVIEW_CANDIDATE_PROVIDER_HOLD"),
    ("EVIDENCE_UNCERTAIN", False, "BLOCKED_NOT_REVIEW_CANDIDATE"),
])
def test_live_event_routes_never_grant_market_transport(event_status, candidate, expected):
    status = event_v5.route_event_v5({
        "status": event_status, "independent_review_candidate": candidate,
        "capture_id": "CAPTURE", "sample_index": 0,
        "snapshot_hash": "a" * 64, "ticker": "068270",
        "market": "KOSPI", "projection_hash": "b" * 64,
        "reviewed_assertion_refs": [], "reason_codes": [],
    })
    assert status["routing"] == expected
    assert status["external_model_call_allowed"] is False
    assert status["model_review_executed"] is False
    assert status["model_result"] is None
    assert status["actual_provider_calls"] == status["db_writes"] == 0


def test_api_real_v5_routing_still_disallows_provider(monkeypatch, tmp_path):
    import app.api.jev as api
    monkeypatch.setattr(api, "_db", lambda: tmp_path / "missing.db")
    monkeypatch.setattr(api, "inspect_frozen_event_assertions", lambda *a, **k: {
        "status": "EVIDENCE_UNCERTAIN", "independent_review_candidate": True,
        "capture_id": "cap", "sample_index": 0,
        "snapshot_hash": "a" * 64,
        "market": "KOSPI", "ticker": "068270",
        "projection_hash": "b" * 64,
        "reviewed_assertion_refs": [], "reason_codes": [],
    })
    result = api.jev_event_v5_routing("cap", 0)
    assert result["routing"] == "REVIEW_CANDIDATE_PROVIDER_HOLD"
    assert result["external_model_call_allowed"] is False
    assert not (tmp_path / "missing.db").exists()


def test_local_fake_demo_is_one_shot_persistent_and_never_uses_live_db(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "_root", lambda: tmp_path / "v5-fixture-only")
    monkeypatch.setattr(demo, "_ACTIVE", False)
    monkeypatch.delenv(demo.FLAG, raising=False)
    assert demo.demo_enabled("127.0.0.1", "127.0.0.1") is False
    monkeypatch.setenv(demo.FLAG, "1")
    assert demo.demo_enabled("127.0.0.1", "127.0.0.1") is True
    assert demo.demo_enabled("203.0.113.5", "127.0.0.1") is False
    assert demo.status()["status"] == "NOT_REQUESTED"
    first = demo.start()
    assert first["status"] == "QUEUED"
    assert first["reused"] is False
    assert demo.start()["reused"] is True
    asyncio.run(demo.run_mock())
    saved = demo.status()
    assert saved["status"] == "VALID"
    assert saved["result"]["disposition"] == "REVIEW_REQUIRED"
    assert saved["mock_provider_calls"] == 1
    assert saved["actual_provider_calls"] == 0
    assert demo.start()["reused"] is True
    assert (tmp_path / "v5-fixture-only" / "v5-session.json").is_file()


def test_restart_does_not_auto_execute_or_duplicate(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "_root", lambda: tmp_path / "v5-restart")
    monkeypatch.setattr(demo, "_ACTIVE", False)
    demo.start()
    monkeypatch.setattr(demo, "_ACTIVE", False)
    saved = demo.status()
    assert saved["status"] == "INTERRUPTED"
    assert saved["mock_provider_calls"] == 0
    assert demo.start()["reused"] is True
    asyncio.run(demo.run_mock())
    assert demo.status()["mock_provider_calls"] == 0
