"""JEV-B2 contract: no external traffic, source-rights grants or real stock inputs."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math

import httpx
import pytest

from app.jev.models import digest_json
from app.jev.stock_review_contract_v1 import (
    DEFAULT_MODEL,
    OPTIONS,
    QUESTION,
    QUESTION_HASH,
    QUESTION_ID,
    SOURCE_FIXTURE,
    VERSION,
    StockReviewContractError,
    build_choice_question,
    prepare_offline_preview,
    synthetic_fixture,
    validate_choice_response,
)
from app.jev.typesafe_provider import TYPESAFE_SYSTEM_ONE_URL
from app.jev.typesafe_questions_v4 import (
    JEV_TYPESAFE_QUESTION_IDS_V4, build_typesafe_questions_v4,
)


def _good_response():
    return {
        "model": DEFAULT_MODEL,
        "answers": {
            QUESTION_ID: {
                "type": "choice",
                "choice": "CHECK_MISSING_EVIDENCE",
                "confidence": 0.65,
                "probabilities": {
                    "CHECK_MISSING_EVIDENCE": 0.7,
                    "CHECK_CONFLICTING_SIGNALS": 0.2,
                    "CHECK_RISK_CONTEXT": 0.1,
                    "NO_DISTINCT_REVIEW_PRIORITY": 0.0,
                },
            }
        },
        "usage": {"input_tokens": 52, "output_tokens": 14},
    }


def test_synthetic_only_preview_has_exact_choice_request_and_no_send(tmp_path, monkeypatch):
    # Even if a real provider key exists in the environment, no HTTP client
    # request, DB access or outbound approval is reachable from this contract.
    monkeypatch.setattr(httpx.Client, "send",
                        lambda *a, **kw: pytest.fail("unexpected HTTP send"))
    monkeypatch.setattr(httpx.AsyncClient, "send",
                        lambda *a, **kw: pytest.fail("unexpected async HTTP send"))
    untouched = tmp_path / "original-market.db"
    untouched.write_bytes(b"fixture-db-cannot-change")
    case = synthetic_fixture()
    out = prepare_offline_preview(case)
    assert out["status"] == "SYNTHETIC_REQUEST_SHAPE_VALIDATED_NO_SEND"
    assert out["contract_version"] == VERSION
    assert out["reason_code"] == "OFFLINE_SYNTHETIC_ONLY"
    assert out["provider_calls"] == out["db_writes"] == 0
    assert out["provider_eligible"] is False
    assert out["real_source_transmission_approved"] is False
    assert out["historical_decision_eligible"] is False
    assert case["candidate"]["market"] == "SYNTHETIC"
    assert case["candidate"]["ticker"] == "SYNTH-NOT-TRADED"
    assert case["evidence"]["origin"] == SOURCE_FIXTURE

    body = out["request_preview"]
    assert set(body) == {"state", "model", "questions"}
    assert body["model"] == DEFAULT_MODEL
    assert tuple(body["questions"]) == (QUESTION_ID,)
    question = body["questions"][QUESTION_ID]
    assert question["type"] == "choice"
    assert list(question["criteria"]) == list(OPTIONS)
    assert body["state"]["review_scope"] == "SYNTHETIC_REVIEW_PRIORITY_CONTRACT_TEST_ONLY"
    assert set(body["state"]) == {
        "review_scope", "strategy_intent", "review_notes", "horizon_intent",
        "internal_risk_rule_description",
    }
    for forbidden in ("price", "market_regime", "news", "dart", "unsc",
                      "capture_id", "snapshot_hash", "ticker", "signal_date"):
        assert forbidden not in json.dumps(body["state"])
    actual_wire = httpx.Request("POST", TYPESAFE_SYSTEM_ONE_URL, json=body).content
    assert out["http_body_sha256"] == hashlib.sha256(actual_wire).hexdigest()
    assert out["http_body_bytes"] == len(actual_wire)
    assert out["input_hash"] == digest_json(body["state"])
    assert out["question_hash"] == QUESTION_HASH
    assert untouched.read_bytes() == b"fixture-db-cannot-change"


def test_determinism_and_changed_model_channel_change_review_identity():
    case = synthetic_fixture()
    a = prepare_offline_preview(case)
    b = prepare_offline_preview(deepcopy(case))
    c = prepare_offline_preview(case, model_id="jev-test-future")
    assert a["request_preview"] == b["request_preview"]
    assert a["review_identity"] == b["review_identity"]
    assert a["http_body_sha256"] == b["http_body_sha256"]
    assert a["review_identity"] != c["review_identity"]
    assert a["request_preview"]["model"] != c["request_preview"]["model"]
    assert a["provider_eligible"] is False and c["provider_eligible"] is False


@pytest.mark.parametrize("change, reason", [
    (lambda c: c.update(price=12000), "NON_ALLOWLIST_FIELD"),
    (lambda c: c["candidate"].update(ticker="005930"), "REAL_CANDIDATE_NOT_APPROVED"),
    (lambda c: c["candidate"].update(capture_id="real-capture-id"), "REAL_CANDIDATE_NOT_APPROVED"),
    (lambda c: c["candidate"].update(sample_index=2), "REAL_CANDIDATE_NOT_APPROVED"),
    (lambda c: c["candidate"].update(horizon_intent="LONG"), "REAL_CANDIDATE_NOT_APPROVED"),
    (lambda c: c["candidate"].update(snapshot_hash="0" * 64), "SNAPSHOT_HASH_MISMATCH"),
    (lambda c: c["candidate"]["snapshot"].update(price=999), "SNAPSHOT_HASH_MISMATCH"),
    (lambda c: c["evidence"].update(source_rights_approved=True), "NON_ALLOWLIST_FIELD"),
    (lambda c: c["evidence"].update(rights_basis="CLIENT_CHECKBOX_TRUE"), "SOURCE_RIGHTS_UNVERIFIED"),
    (lambda c: c["evidence"].update(origin="KRX_STOCK_DAILY"), "SOURCE_RIGHTS_UNVERIFIED"),
    (lambda c: c["evidence"]["authored_text"].update(news="quoted story"), "NON_ALLOWLIST_FIELD"),
    (lambda c: c["evidence"]["authored_text"].update(review_notes=""), "REVIEW_NOTE_REQUIRED"),
    (lambda c: c["evidence"]["authored_text"].update(review_notes="quoted from an external article"), "INPUT_PROVENANCE_MISMATCH"),
    (lambda c: c["evidence"].update(observed_at_utc="2026-01-03"), "TIME_UTC_REQUIRED"),
    (lambda c: c["evidence"].update(observed_at_utc="2026-01-03T18:00:00+09:00"), "TIME_UTC_REQUIRED"),
    (lambda c: c["evidence"].update(observed_at_utc="2026-01-05T00:00:00Z"), "TIME_NOT_AVAILABLE_ASOF"),
    (lambda c: c.update(review_at_utc="2026-01-01T09:00:00Z"), "TIME_NOT_AVAILABLE_ASOF"),
    (lambda c: c.update(review_at_utc="2026-01-04T09:00:00"), "TIME_UTC_REQUIRED"),
])
def test_non_fixture_or_false_rights_claim_cannot_create_model_input(change, reason):
    case = synthetic_fixture()
    change(case)
    report = prepare_offline_preview(case)
    assert report["status"] == "INPUT_NOT_ELIGIBLE"
    assert report["reason_code"] == reason
    assert report["request_preview"] is None
    assert report["review_identity"] is None
    assert report["provider_calls"] == report["db_writes"] == 0
    assert report["provider_eligible"] is False
    assert report["real_source_transmission_approved"] is False


def test_user_mutated_text_with_matching_self_hash_cannot_claim_fixture_rights():
    case = synthetic_fixture()
    case["evidence"]["authored_text"]["review_notes"] = "I copied this from a price table"
    case["evidence"]["content_hash"] = digest_json(case["evidence"]["authored_text"])
    report = prepare_offline_preview(case)
    assert report["reason_code"] == "AUTHORING_EVIDENCE_UNVERIFIED"
    assert report["request_preview"] is None


@pytest.mark.parametrize("value", [None, "", "UNFROZEN", "jev model", "JEV/API", "x"*90])
def test_model_identifier_is_bounded_and_never_provider_authorization(value):
    result = prepare_offline_preview(synthetic_fixture(), model_id=value)
    assert result["status"] == "INPUT_NOT_ELIGIBLE"
    assert result["reason_code"] == "MODEL_NOT_PINNED"
    assert result["provider_calls"] == 0


def test_question_is_defensively_copied_and_v4_is_not_mutated():
    before = build_typesafe_questions_v4()
    q = build_choice_question()
    q[QUESTION_ID]["criteria"]["CHECK_MISSING_EVIDENCE"] = "changed"
    assert build_choice_question()[QUESTION_ID]["criteria"]["CHECK_MISSING_EVIDENCE"] != "changed"
    assert build_typesafe_questions_v4() == before
    assert JEV_TYPESAFE_QUESTION_IDS_V4 == ("strategy_relation_conflict",)
    assert before["strategy_relation_conflict"]["type"] == "noul"
    assert QUESTION["type"] == "choice"


def test_official_choice_response_shape_is_validated_without_return_predictions():
    response = _good_response()
    normalized = validate_choice_response(response, expected_model=DEFAULT_MODEL)
    assert normalized["question_id"] == QUESTION_ID
    assert normalized["choice"] == "CHECK_MISSING_EVIDENCE"
    assert normalized["usage"] == {"input_tokens": 52, "output_tokens": 14}
    assert normalized["confidence"] == pytest.approx(0.65)
    assert normalized["display_scope"] == "REVIEW_PRIORITY_ONLY_NOT_STOCK_RETURN_PROBABILITY"
    assert normalized["provider_calls"] == 0


@pytest.mark.parametrize("edit,code", [
    (lambda p: p.update(model="jev-other"), "MODEL_IDENTITY_CHANGED"),
    (lambda p: p.update(answers={}), "CHOICE_ANSWER_SET_MISMATCH"),
    (lambda p: p["answers"][QUESTION_ID].update(type="noul"), "CHOICE_RESPONSE_SHAPE_INVALID"),
    (lambda p: p["answers"][QUESTION_ID].update(choice="BUY_NOW"), "CHOICE_OPTION_INVALID"),
    (lambda p: p["answers"][QUESTION_ID].update(confidence=math.nan), "CHOICE_PROBABILITY_INVALID"),
    (lambda p: p["answers"][QUESTION_ID].update(confidence=True), "CHOICE_PROBABILITY_INVALID"),
    (lambda p: p["answers"][QUESTION_ID]["probabilities"].pop("CHECK_RISK_CONTEXT"), "CHOICE_OPTION_SET_MISMATCH"),
    (lambda p: p["answers"][QUESTION_ID]["probabilities"].update(CHECK_RISK_CONTEXT=1.5), "CHOICE_PROBABILITY_INVALID"),
    (lambda p: p["answers"][QUESTION_ID]["probabilities"].update(CHECK_MISSING_EVIDENCE=0.5), "CHOICE_PROBABILITIES_NOT_NORMALIZED"),
    (lambda p: p["answers"][QUESTION_ID].update(choice="CHECK_RISK_CONTEXT"), "CHOICE_NOT_MAXIMUM"),
    (lambda p: p["usage"].update(input_tokens=-1), "CHOICE_USAGE_INVALID"),
    (lambda p: p["usage"].update(input_tokens=True), "CHOICE_USAGE_INVALID"),
    (lambda p: p.update(usage={}), "CHOICE_USAGE_INVALID"),
])
def test_malformed_choice_model_and_probabilities_are_rejected(edit, code):
    response = _good_response()
    edit(response)
    with pytest.raises(StockReviewContractError) as exc:
        validate_choice_response(response, expected_model=DEFAULT_MODEL)
    assert exc.value.code == code


@pytest.mark.parametrize("bad", [None, {}, [], "text", {"model": "jev-1.14.0"}])
def test_missing_response_is_not_interpreted_as_model_outcome(bad):
    with pytest.raises(StockReviewContractError):
        validate_choice_response(bad, expected_model=DEFAULT_MODEL)
