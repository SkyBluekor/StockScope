"""S5 synthetic System One typed-choice Canary; no real network or charges.

The approval records here are FAKE TEST FIXTURES; production user consent and
account pricing are NOT established by this test. All HTTP is MockTransport.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from copy import deepcopy
from decimal import Decimal
import json
import sqlite3

import httpx
import pytest

from app.jev.decision_reviewer_micro_canary import (
    ActualTrialApproval, FrozenMicroProtocol, MicroCanaryRunner, MicroJournal,
    SystemOneMicroProvider, CASES, CASE_SET_HASH, CHOICE_NAME, CHOICES,
    MICRO_VERSION, QUESTION_HASH, summarize_micro_canary,
    synthetic_case_ids, synthetic_projection, micro_packet,
)
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.typesafe_provider import TYPESAFE_SYSTEM_ONE_URL


def _protocol(**kwargs):
    base = dict(
        protocol_id="S5-SYNTHETIC-TEST-ONLY",
        model_requested="jev-latest",
        model_returned="jev-pinned-fixture-2026",
        verified_input_usd_per_million="0.042",
        verified_output_usd_per_million="0",
    )
    base.update(kwargs)
    return FrozenMicroProtocol(**base)


def _fake_approval(protocol):
    return ActualTrialApproval(
        approved_protocol_hash=protocol.identity_hash,
        approved_case_set_hash=CASE_SET_HASH,
        approved_model=protocol.model_returned,
        approved_budget_usd=protocol.total_budget_usd,
        owner_approved=True, provider_terms_confirmed=True,
        account_pricing_confirmed=True, model_catalog_confirmed=True,
        explicit_trial_scope="S5_APPROVED_SYNTHETIC_MICRO_CANARY",
    )


def _response(decision, *, model="jev-pinned-fixture-2026", usage=None):
    probs = {d: (1.0 if d == decision else 0.0) for d in CHOICES}
    return {
        "model": model,
        "answers": {
            CHOICE_NAME: {
                "type": "choice", "choice": decision,
                "confidence": 1.0, "probabilities": probs,
            }
        },
        "usage": usage or {"input_tokens": 123, "output_tokens": 17},
    }


def _journal(tmp_path):
    db = tmp_path / "jev_s5_micro_isolated.db"
    conn = sqlite3.connect(db)
    journal = MicroJournal(conn)
    journal.initialize()
    return conn, journal, db


def _runner(tmp_path, handler):
    conn, journal, db = _journal(tmp_path)
    provider = SystemOneMicroProvider(transport=httpx.MockTransport(handler))
    return conn, journal, MicroCanaryRunner(journal, provider), db


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_all_authored_cases_real_schema_mock_http(tmp_path, case):
    seen = []
    protocol = _protocol()
    approval = _fake_approval(protocol)

    def handler(request):
        seen.append(request)
        assert request.method == "POST"
        assert str(request.url) == TYPESAFE_SYSTEM_ONE_URL
        assert request.headers["authorization"] == "Bearer only-mock"
        payload = json.loads(request.content)
        assert set(payload) == {"state", "model", "questions"}
        assert payload["state"]["synthetic_only"] is True
        assert "gold" not in json.dumps(payload)
        assert "ticker" not in json.dumps(payload)
        assert "source_capture" not in json.dumps(payload)
        assert payload["questions"][CHOICE_NAME]["type"] == "choice"
        return httpx.Response(200, json=_response(case["gold"]))

    conn, journal, runner, path = _runner(tmp_path, handler)
    row = asyncio.run(runner.run_case(
        case["id"], protocol, approval, api_key="only-mock"
    ))
    assert row["state"] == "VALID"
    assert row["decision"] == case["gold"]
    assert row["output"]["decision"] == case["gold"]
    assert row["typed_response"]["model"] == protocol.model_returned
    assert row["typed_response"]["usage"]["input_tokens"] == 123
    assert row["cost_status"] == "ESTIMATED_FROM_VERIFIED_ACCOUNT_RATE"
    assert Decimal(row["computed_cost_usd"]) == Decimal("123") * Decimal("0.042") / 1000000
    assert row["investment_outcome"] == "NOT_EVALUATED"
    if row["decision"] == "PASS_THROUGH":
        assert "개별 근거를 인용하지 않았습니다" in row["output"]["supporting_reasons"][0]["explanation"]
    assert len(seen) == 1
    repeat = asyncio.run(runner.run_case(
        case["id"], protocol, approval, api_key="only-mock"
    ))
    assert repeat["reused"] is True
    assert len(seen) == 1
    assert len(journal.list_records()) == 1
    conn.close()


def test_approval_absence_blocks_before_any_http_or_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "should-never-read")
    seen = []
    def handler(request):
        seen.append(1)
        return httpx.Response(200, json=_response("PASS_THROUGH"))

    conn, journal, runner, _ = _runner(tmp_path, handler)
    with pytest.raises(DecisionReviewContractError, match="S5_ACTUAL_TRIAL_NOT_APPROVED"):
        asyncio.run(runner.run_case("s5-consistent", _protocol(), None))
    assert journal.list_records() == []
    assert seen == []
    conn.close()


@pytest.mark.parametrize("field", [
    "owner_approved", "provider_terms_confirmed", "account_pricing_confirmed",
    "model_catalog_confirmed", "synthetic_only",
])
def test_incomplete_consent_prevents_network(tmp_path, field):
    called = []
    conn, journal, runner, _ = _runner(
        tmp_path, lambda req: (called.append(True), httpx.Response(200, json=_response("ABSTAIN")))[1]
    )
    protocol = _protocol()
    permit = replace(_fake_approval(protocol), **{field: False})
    with pytest.raises(DecisionReviewContractError, match="S5_ACTUAL_TRIAL_NOT_APPROVED"):
        asyncio.run(runner.run_case("s5-consistent", protocol, permit, api_key="mock"))
    assert called == []
    assert journal.list_records() == []
    conn.close()


def test_provider_direct_input_spoofing_denied_without_network(tmp_path):
    calls = []
    proto = _protocol()
    permit = _fake_approval(proto)
    provider = SystemOneMicroProvider(transport=httpx.MockTransport(
        lambda req: (calls.append(req), httpx.Response(200, json=_response("ABSTAIN")))[1]
    ))
    forged = deepcopy(micro_packet(synthetic_projection("s5-consistent"), proto))
    forged["state"]["evidence"].append({"id": "new", "statement": "REAL STOCK DATA"})
    with pytest.raises(DecisionReviewContractError, match="S5_SYNTHETIC_PACKET_FORGED"):
        asyncio.run(provider.ask(forged, proto, permit, api_key="mock"))
    assert calls == []


def test_only_registered_cases_may_be_sent():
    with pytest.raises(DecisionReviewContractError, match="S5_SYNTHETIC_CASE_NOT_REGISTERED"):
        synthetic_projection("live-capture-id")
    with pytest.raises(DecisionReviewContractError, match="S5_REAL_MARKET_INPUT_FORBIDDEN"):
        micro_packet({"status": "OFFLINE_INSPECTABLE_ONLY"},
                     _protocol())


@pytest.mark.parametrize("broken,expected", [
    (lambda x: x.update(model="unexpected-revision"), "S5_RETURNED_MODEL_MISMATCH"),
    (lambda x: x["answers"][CHOICE_NAME].update(choice="BUY"), "S5_CHOICE_INVALID"),
    (lambda x: x["answers"][CHOICE_NAME].update(probabilities={"ABSTAIN": 1.0}),
     "S5_CHOICE_PROBABILITIES_INVALID"),
    (lambda x: x["answers"][CHOICE_NAME].update(confidence=float("nan")),
     "S5_PROVIDER_RESPONSE_INVALID"),
    (lambda x: x["usage"].update(input_tokens=-1), "S5_USAGE_INVALID"),
    (lambda x: x["answers"].update(unrequested={"type": "noul", "noul": 0.9}),
     "S5_ANSWER_SET_INVALID"),
])
def test_invalid_actual_type_safe_response_fails_closed(tmp_path, broken, expected):
    data = _response("PASS_THROUGH")
    broken(data)
    conn, journal, runner, _ = _runner(
        tmp_path, lambda req: httpx.Response(200, json=data)
    )
    proto = _protocol()
    row = asyncio.run(runner.run_case(
        "s5-consistent", proto, _fake_approval(proto), api_key="mock"
    ))
    assert row["state"] == "ERROR"
    assert row["reason_code"] == expected
    assert row["output"] is None
    assert row["decision"] == "ABSTAIN"
    assert row["cost_status"] == "UNKNOWN"
    conn.close()


def test_http_auth_failure_stores_error_and_never_retries(tmp_path):
    seen = []
    def handler(req):
        seen.append(1)
        return httpx.Response(401)
    conn, journal, runner, _ = _runner(tmp_path, handler)
    proto = _protocol()
    row = asyncio.run(runner.run_case(
        "s5-consistent", proto, _fake_approval(proto), api_key="mock"
    ))
    assert row["reason_code"] == "S5_PROVIDER_HTTP_ERROR"
    assert row["state"] == "ERROR"
    assert len(seen) == 1
    conn.close()


def test_journal_budget_atomic_and_persisted(tmp_path):
    count = []
    def handler(req):
        count.append(1)
        return httpx.Response(200, json=_response("PASS_THROUGH"))
    conn, journal, runner, db = _runner(tmp_path, handler)
    proto = _protocol(max_attempts=1, total_budget_usd="0.01")
    permit = _fake_approval(proto)
    a = asyncio.run(runner.run_case("s5-consistent", proto, permit, api_key="mock"))
    assert a["state"] == "VALID"
    with pytest.raises(DecisionReviewContractError, match="S5_TRIAL_BUDGET_EXHAUSTED"):
        asyncio.run(runner.run_case("s5-risk-contradiction", proto, permit, api_key="mock"))
    assert len(count) == 1
    conn.close()
    conn2 = sqlite3.connect(db)
    j2 = MicroJournal(conn2)
    assert len(j2.list_records()) == 1
    conn2.close()


def test_terminal_history_immutable_and_pending_interrupt(tmp_path):
    conn, journal, runner, db = _runner(
        tmp_path, lambda req: httpx.Response(200, json=_response("ABSTAIN"))
    )
    proto = _protocol()
    permit = _fake_approval(proto)
    row = asyncio.run(runner.run_case("s5-unresolved-ambiguity", proto, permit, api_key="mock"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE jev_s5_synthetic SET state='ERROR'")
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM jev_s5_synthetic")
    conn.rollback()
    proj = synthetic_projection("s5-consistent")
    packet = micro_packet(proj, proto)
    pending, reused = journal.reserve(proj, packet, proto)
    assert pending["state"] == "PENDING" and not reused
    assert journal.interrupt_pending() == 1
    assert journal._one(pending["review_id"])["state"] == "INTERRUPTED"
    conn.close()


def test_journal_report_no_financial_uplift_claim(tmp_path):
    conn, journal, runner, _ = _runner(
        tmp_path, lambda req: httpx.Response(200, json=_response("REVIEW_REQUIRED"))
    )
    proto = _protocol()
    permit = _fake_approval(proto)
    asyncio.run(runner.run_case("s5-consistent", proto, permit, api_key="mock"))
    report = summarize_micro_canary(journal)
    assert report["version"] == MICRO_VERSION
    assert report["attempts"] == 1
    assert report["incorrect_against_synthetic_gold"] == 1
    assert report["investment_uplift_established"] is False
    assert report["outcome"] == "NOT_EVALUATED"
    assert len(report["unattempted_cases"]) == len(CASES) - 1
    conn.close()


@pytest.mark.parametrize("overrides", [
    {"model_returned": "jev-latest"},
    {"model_returned": "UNFROZEN"},
    {"retry_count": 1},
    {"max_attempts": 99},
    {"total_budget_usd": "NaN"},
    {"per_attempt_reservation_usd": "-1"},
    {"protocol_case_set_hash": "stale"},
    {"question_hash": "stale"},
])
def test_protocol_fail_closed(overrides):
    with pytest.raises(DecisionReviewContractError, match="S5_PROTOCOL_LIMIT_INVALID"):
        _protocol(**overrides).validate()


def test_missing_account_price_blocks_trial_preflight():
    proto = _protocol(verified_input_usd_per_million=None)
    with pytest.raises(DecisionReviewContractError, match="S5_ACCOUNT_PRICE_UNVERIFIED"):
        _fake_approval(proto).validate(proto)


def test_s5_does_not_replace_v4_contract_or_enable_feature():
    from app.jev.review_models import JEV_USER_FEATURE_DISABLED
    from app.jev.typesafe_canary_v4 import validate_canary_v4_contract
    assert JEV_USER_FEATURE_DISABLED != ""
    assert validate_canary_v4_contract()["spec"]["partition_contract"]["provider_reachable_positive_residual_count"] == 0
    assert set(CHOICES) == {"PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN"}
    assert len(synthetic_case_ids()) >= 5
    assert len(CASE_SET_HASH) == len(QUESTION_HASH) == 64
