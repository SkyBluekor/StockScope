"""S4 closed-network Canary tests. Only tmp_path SQLite and httpx.MockTransport."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import sqlite3

import httpx
import pytest

from app.jev.decision_reviewer_canary import (
    CANARY_PREP_VERSION, MOCK_URL, MockCanaryRunner,
    MockHttpReviewer, MockShadowJournal, TrialLimits,
    assess_actual_canary_preflight, build_mock_request,
)
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.prospective.models import digest_json
from test_jev_act2_s3_decision_reviewer import _projection, _response, _stored


def _setup(tmp_path, handler, *, max_attempts=2):
    source_db, capture = _stored(tmp_path)
    projection = _projection(source_db, capture)
    journal_path = tmp_path / "isolated_mock_journal.db"
    connection = sqlite3.connect(journal_path)
    journal = MockShadowJournal(connection)
    journal.initialize_test_store()
    provider = MockHttpReviewer(httpx.MockTransport(handler))
    runner = MockCanaryRunner(journal, provider)
    limits = TrialLimits(
        protocol_id="FAKE-ONLY-S3", max_attempts=max_attempts,
        max_reserved_usd=max_attempts * 0.01,
    )
    return projection, journal, runner, limits, connection, source_db


@pytest.mark.parametrize("decision", ["PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN"])
def test_mock_http_review_persistent_and_baseline_untouched(tmp_path, decision):
    seen = []
    def fake_http(request):
        assert str(request.url) == MOCK_URL
        assert request.method == "POST"
        payload = json.loads(request.content)
        seen.append(payload)
        assert payload["model"] == "MOCK-ACT2-S4"
        assert payload["transport"] == "MOCK_ONLY"
        assert "code" not in payload["review"]
        assert "ticker" not in payload["review"]
        assert "entry_risk_guide" not in payload["review"]
        assert "news" not in payload["review"]
        assert payload["review"]["risk"]["status"] == "READY"
        return httpx.Response(200, json=_response(decision))
    projection, journal, runner, limits, conn, source_db = _setup(tmp_path, fake_http)
    with sqlite3.connect(source_db) as source:
        before = "\n".join(source.iterdump())
    first = asyncio.run(runner.run_once(projection, limits))
    second = asyncio.run(runner.run_once(projection, limits))
    assert first["state"] == "VALID"
    assert first["disposition"] == decision
    assert first["output"]["decision"] == decision
    assert first["baseline_action"] == "ENTRY_CANDIDATE"
    assert first["actual_provider_calls"] == 0
    assert first["observed_cost_usd"] == 0
    assert second["reused"] is True
    assert len(seen) == 1
    assert len(journal.list_records()) == 1
    with sqlite3.connect(source_db) as source:
        assert before == "\n".join(source.iterdump())
    conn.close()


def test_real_market_preflight_holds_even_if_all_flags_requested(tmp_path):
    projection, journal, runner, limits, conn, _ = _setup(
        tmp_path, lambda request: httpx.Response(200, json=_response("ABSTAIN"))
    )
    report = assess_actual_canary_preflight(
        projection, model_identity_confirmed=True,
        account_pricing_verified=True, budget_approved=True,
        source_transmission_approved=True,
        explicit_user_execution_approved=True,
    )
    assert report["version"] == CANARY_PREP_VERSION
    assert report["can_call_actual_provider"] is False
    assert report["actual_provider_calls"] == 0
    assert {"MARKET_SCOPE", "HORIZON_POLICY", "SOURCE_AS_OF", "SOURCE_RIGHTS"} <= set(
        report["blocking_reasons"]
    )
    conn.close()


def test_default_preflight_does_not_read_env_or_authorize(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "fake-should-not-be-read")
    projection, journal, runner, limits, conn, _ = _setup(
        tmp_path, lambda request: httpx.Response(200, json=_response("ABSTAIN"))
    )
    report = assess_actual_canary_preflight(projection)
    assert report["status"] == "HOLD"
    assert "USER_EXECUTION" in report["blocking_reasons"]
    assert "BUDGET" in report["blocking_reasons"]
    assert report["db_writes"] == 0
    conn.close()


def test_non_mock_transport_never_accepted():
    with pytest.raises(DecisionReviewContractError, match="S4_REAL_TRANSPORT_FORBIDDEN"):
        MockHttpReviewer(httpx.AsyncHTTPTransport())


@pytest.mark.parametrize("kwargs", [
    {"allow_real_network": True},
    {"retry_count": 1},
    {"concurrency_cap": 2},
    {"deadline_seconds": 100.0},
    {"max_attempts": 11},
    {"per_attempt_reservation_usd": 1.0},
    {"max_reserved_usd": 0.0},
])
def test_trial_limits_fail_closed(kwargs):
    with pytest.raises(DecisionReviewContractError, match="S4_MOCK_LIMITS_INVALID"):
        TrialLimits(protocol_id="test-protocol", **kwargs).validate()


def _another(projection):
    copy = deepcopy(projection)
    copy["input"]["candidate_ref"]["sample_index"] += 1
    body = dict(copy["input"])
    body.pop("input_hash")
    copy["input_hash"] = digest_json(body)
    copy["input"]["input_hash"] = copy["input_hash"]
    return copy


def test_attempt_ceiling_persists_across_runner_instances(tmp_path):
    seen = []
    def handler(request):
        seen.append(1)
        return httpx.Response(200, json=_response("PASS_THROUGH"))
    projection, journal, runner, limits, conn, _ = _setup(
        tmp_path, handler, max_attempts=1,
    )
    first = asyncio.run(runner.run_once(projection, limits))
    assert first["state"] == "VALID"
    runner2 = MockCanaryRunner(journal, MockHttpReviewer(httpx.MockTransport(handler)))
    second = _another(projection)
    with pytest.raises(DecisionReviewContractError, match="S4_MOCK_BUDGET_OR_ATTEMPTS_EXCEEDED"):
        asyncio.run(runner2.run_once(second, limits))
    assert len(seen) == 1
    assert len(journal.list_records()) == 1
    conn.close()


def test_http_schema_error_is_persisted_as_error_not_baseline_change(tmp_path):
    projection, journal, runner, limits, conn, _ = _setup(
        tmp_path, lambda request: httpx.Response(200, json={
            **_response("REVIEW_REQUIRED"),
            "trade_instruction": "BUY",
        })
    )
    record = asyncio.run(runner.run_once(projection, limits))
    assert record["state"] == "ERROR"
    assert record["disposition"] == "ABSTAIN"
    assert record["reason_code"] == "RESPONSE_SCHEMA_INVALID"
    assert record["baseline_action"] == "ENTRY_CANDIDATE"
    assert record["output"] is None
    conn.close()


def test_mock_http_error_does_not_retry_or_fake_success(tmp_path):
    seen = []
    def handler(request):
        seen.append(1)
        return httpx.Response(503)
    projection, journal, runner, limits, conn, _ = _setup(tmp_path, handler)
    record = asyncio.run(runner.run_once(projection, limits))
    assert record["state"] == "ERROR"
    assert record["reason_code"] == "S4_MOCK_HTTP_OR_SCHEMA_ERROR"
    assert len(seen) == 1
    conn.close()


def test_mock_timeout_fails_closed(tmp_path):
    async def slow_handler(request):
        await asyncio.sleep(0.08)
        return httpx.Response(200, json=_response("PASS_THROUGH"))
    projection, journal, runner, limits, conn, _ = _setup(
        tmp_path, slow_handler
    )
    from dataclasses import replace
    limits = replace(limits, deadline_seconds=0.01)
    record = asyncio.run(runner.run_once(projection, limits))
    assert record["state"] == "ERROR"
    assert record["reason_code"] == "S4_MOCK_TIMEOUT"
    assert record["output"] is None
    conn.close()


def test_journal_rejects_terminal_mutation_and_deletion(tmp_path):
    projection, journal, runner, limits, conn, _ = _setup(
        tmp_path, lambda request: httpx.Response(200, json=_response("ABSTAIN"))
    )
    row = asyncio.run(runner.run_once(projection, limits))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE jev_s4_mock_trial SET state='VALID' WHERE identity=?",
            (row["identity"],),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM jev_s4_mock_trial")
    assert journal.get(row["identity"])["state"] == "VALID"
    conn.close()


def test_stale_pending_record_interrupted_not_retried(tmp_path):
    projection, journal, runner, limits, conn, _ = _setup(
        tmp_path, lambda request: httpx.Response(200, json=_response("PASS_THROUGH"))
    )
    packet = build_mock_request(projection, limits)
    pending, reused = journal.reserve(projection, packet, limits)
    assert pending["state"] == "PENDING"
    assert not reused
    assert journal.interrupt_pending() == 1
    result = asyncio.run(runner.run_once(projection, limits))
    assert result["state"] == "INTERRUPTED"
    assert result["reused"] is True
    assert result["output"] is None
    conn.close()


def test_missing_protocol_raises_without_store_write(tmp_path):
    projection, journal, runner, limits, conn, _ = _setup(
        tmp_path, lambda request: httpx.Response(200, json=_response("PASS_THROUGH"))
    )
    from dataclasses import replace
    with pytest.raises(DecisionReviewContractError, match="S4_INPUT_IDENTITY_MISMATCH"):
        asyncio.run(runner.run_once(projection, replace(limits, protocol_id="wrong")))
    assert journal.list_records() == []
    conn.close()


def test_legacy_cannot_run_mock_trial(tmp_path):
    db, capture = _stored(tmp_path, horizon="LEGACY_UNSPECIFIED")
    projection = _projection(db, capture)
    with pytest.raises(DecisionReviewContractError, match="S4_NOT_MOCK_INSPECTABLE"):
        build_mock_request(projection, TrialLimits(protocol_id="FAKE-ONLY-S3"))
