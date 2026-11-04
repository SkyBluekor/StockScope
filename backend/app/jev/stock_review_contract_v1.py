"""JEV-B2: isolated, offline-only Choice contract for stock-review routing.

This is NOT a production input authorization mechanism. The ONLY accepted
request preview is an exact, repository-authored *synthetic* fixture. No real
market data, caller-supplied rights flags, HTTP requests, DB writes or model
decisions are supported. A future separate trusted server-side source resolver
and one-use approval boundary are required before any real stock is sent.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Mapping

import httpx

from .models import digest_json
from .typesafe_provider import TYPESAFE_SYSTEM_ONE_URL

VERSION = "JEV_STOCK_REVIEW_ROUTING_V1"
QUESTION_ID = "review_priority"
DEFAULT_MODEL = "jev-1.14.0"  # Candidate only; NOT approved or discovered here.
SOURCE_FIXTURE = "PROJECT_AUTHORED_SYNTHETIC_FIXTURE"
SYNTHETIC_CAPTURE_ID = "JEV-B2-SYNTHETIC-NOT-A-REAL-CAPTURE"
SYNTHETIC_TICKER = "SYNTH-NOT-TRADED"
MAX_WIRE_BYTES = 8192

OPTIONS = (
    "CHECK_MISSING_EVIDENCE",
    "CHECK_CONFLICTING_SIGNALS",
    "CHECK_RISK_CONTEXT",
    "NO_DISTINCT_REVIEW_PRIORITY",
)

QUESTION = {
    "type": "choice",
    "instructions": (
        "Using only the supplied, explicitly authored review notes and "
        "strategy intent for this hypothetical example, choose the single "
        "most useful follow-up check BEFORE relying on the stated decision. "
        "Do not invent market facts, prices, news, causal explanations, "
        "forecast returns, issue trade advice, or override StockScope's "
        "Scanner and Risk results. Choose no distinct priority if none is "
        "grounded in the supplied text."
    ),
    "criteria": {
        "CHECK_MISSING_EVIDENCE": (
            "A necessary source, timestamp, explanation or specifically "
            "mentioned supporting fact is missing from the authored notes."
        ),
        "CHECK_CONFLICTING_SIGNALS": (
            "Two of the supplied authored observations or assumptions are "
            "mutually inconsistent or cannot both support the intended action."
        ),
        "CHECK_RISK_CONTEXT": (
            "The supplied authored risk rule or risk assumption needs "
            "rechecking against the authored strategy or observation."
        ),
        "NO_DISTINCT_REVIEW_PRIORITY": (
            "No one distinct missing, conflicting or risk-focused check is "
            "supported by the given text; NOT an investment safety approval."
        ),
    },
}
QUESTION_SET = {QUESTION_ID: QUESTION}
QUESTION_HASH = digest_json({"version": VERSION, "questions": QUESTION_SET})

# Precisely authored, hypothetical text. None of these statements describes
# any identifiable traded stock, real market outcome or third-party source.
_FIXTURE_TEXT = {
    "strategy_intent": (
        "For an invented scenario, use the stated conditions consistently "
        "before considering a hypothetical entry."
    ),
    "review_notes": (
        "The hypothetical observation supports entry, but the author's "
        "separate rule states that unconfirmed conditions require another check."
    ),
    "internal_risk_rule_description": (
        "In this fictional rulebook, ambiguous observations must be reviewed "
        "rather than counted as confirmed."
    ),
}


class StockReviewContractError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def build_choice_question() -> dict[str, dict[str, Any]]:
    """Immutable contract to callers; never return a mutable global reference."""
    return deepcopy(QUESTION_SET)


def synthetic_fixture() -> dict[str, Any]:
    """A visibly fake, immutable-content fixture, NOT an authorization token."""
    snapshot = {"synthetic_fixture": VERSION, "market_data": "NONE"}
    return {
        "candidate": {
            "capture_id": SYNTHETIC_CAPTURE_ID,
            "sample_index": 0,
            "market": "SYNTHETIC",
            "ticker": SYNTHETIC_TICKER,
            "horizon_intent": "SHORT",
            "signal_date": "2026-01-02",
            "snapshot": snapshot,
            "snapshot_hash": digest_json(snapshot),
        },
        "evidence": {
            "origin": SOURCE_FIXTURE,
            "rights_basis": "IN_REPOSITORY_AUTHORED_SYNTHETIC_TEST_ONLY",
            "observed_at_utc": "2026-01-03T09:00:00+00:00",
            "content_hash": digest_json(_FIXTURE_TEXT),
            "authored_text": deepcopy(_FIXTURE_TEXT),
        },
        "review_at_utc": "2026-01-04T09:00:00+00:00",
    }


def _utc(raw: Any) -> datetime:
    if not isinstance(raw, str) or len(raw) > 40 or "T" not in raw:
        raise StockReviewContractError("TIME_UTC_REQUIRED")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StockReviewContractError("TIME_UTC_REQUIRED") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise StockReviewContractError("TIME_UTC_REQUIRED")
    if value.utcoffset().total_seconds() != 0:
        raise StockReviewContractError("TIME_UTC_REQUIRED")
    return value.astimezone(timezone.utc)


def _deny(reason: str) -> dict[str, Any]:
    """Never echo untrusted texts, client rights receipts or source identifiers."""
    return {
        "contract_version": VERSION,
        "status": "INPUT_NOT_ELIGIBLE",
        "reason_code": reason,
        "question_hash": QUESTION_HASH,
        "request_preview": None,
        "review_identity": None,
        "real_source_transmission_approved": False,
        "historical_decision_eligible": False,
        "provider_eligible": False,
        "provider_calls": 0,
        "db_writes": 0,
    }


def _validate_fixture(case: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = synthetic_fixture()
    if not isinstance(case, dict) or set(case) != set(expected):
        raise StockReviewContractError("NON_ALLOWLIST_FIELD")
    candidate = case.get("candidate")
    evidence = case.get("evidence")
    if not isinstance(candidate, dict) or not isinstance(evidence, dict):
        raise StockReviewContractError("INPUT_NOT_ELIGIBLE")
    if set(candidate) != set(expected["candidate"]) or set(evidence) != set(expected["evidence"]):
        raise StockReviewContractError("NON_ALLOWLIST_FIELD")
    snapshot = candidate["snapshot"]
    if not isinstance(snapshot, dict) or digest_json(snapshot) != candidate["snapshot_hash"]:
        raise StockReviewContractError("SNAPSHOT_HASH_MISMATCH")
    if candidate != expected["candidate"]:
        raise StockReviewContractError("REAL_CANDIDATE_NOT_APPROVED")
    if evidence.get("origin") != SOURCE_FIXTURE or evidence.get("rights_basis") != expected["evidence"]["rights_basis"]:
        raise StockReviewContractError("SOURCE_RIGHTS_UNVERIFIED")
    authored = evidence.get("authored_text")
    if not isinstance(authored, dict) or set(authored) != set(_FIXTURE_TEXT):
        raise StockReviewContractError("NON_ALLOWLIST_FIELD")
    if not isinstance(authored.get("review_notes"), str) or not authored["review_notes"].strip():
        raise StockReviewContractError("REVIEW_NOTE_REQUIRED")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 640 for v in authored.values()):
        raise StockReviewContractError("INPUT_TEXT_INVALID")
    if digest_json(authored) != evidence.get("content_hash"):
        raise StockReviewContractError("INPUT_PROVENANCE_MISMATCH")
    # Even matching data with user-relabelled provenance is never source proof.
    if authored != _FIXTURE_TEXT or evidence["content_hash"] != expected["evidence"]["content_hash"]:
        raise StockReviewContractError("AUTHORING_EVIDENCE_UNVERIFIED")
    seen = _utc(evidence.get("observed_at_utc"))
    reviewed = _utc(case.get("review_at_utc"))
    try:
        signal_date = date.fromisoformat(candidate["signal_date"])
    except (TypeError, ValueError) as exc:
        raise StockReviewContractError("TIME_UTC_REQUIRED") from exc
    if seen > reviewed or reviewed.date() < signal_date:
        raise StockReviewContractError("TIME_NOT_AVAILABLE_ASOF")
    if (seen != _utc(expected["evidence"]["observed_at_utc"])
            or reviewed != _utc(expected["review_at_utc"])):
        raise StockReviewContractError("AUTHORING_TIME_UNVERIFIED")
    return candidate, authored


def prepare_offline_preview(case: Any, *, model_id: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Prepare one test-only request shape. It is never permission to send."""
    try:
        if (not isinstance(model_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", model_id)
                or model_id.upper() == "UNFROZEN"):
            raise StockReviewContractError("MODEL_NOT_PINNED")
        candidate, authored = _validate_fixture(case)
        state = {
            "review_scope": "SYNTHETIC_REVIEW_PRIORITY_CONTRACT_TEST_ONLY",
            "strategy_intent": authored["strategy_intent"],
            "review_notes": authored["review_notes"],
            "horizon_intent": candidate["horizon_intent"],
            "internal_risk_rule_description": authored["internal_risk_rule_description"],
        }
        request_body = {
            "state": state,
            "questions": build_choice_question(),
            "model": model_id,
        }
        request = httpx.Request("POST", TYPESAFE_SYSTEM_ONE_URL, json=request_body)
        if len(request.content) > MAX_WIRE_BYTES or json.loads(request.content) != request_body:
            raise StockReviewContractError("WIRE_SHAPE_INVALID")
        input_hash = digest_json(state)
        identity = digest_json({
            "contract_version": VERSION,
            "capture_id": candidate["capture_id"],
            "sample_index": candidate["sample_index"],
            "market": candidate["market"],
            "ticker": candidate["ticker"],
            "snapshot_hash": candidate["snapshot_hash"],
            "input_hash": input_hash,
            "question_hash": QUESTION_HASH,
            "model_requested": model_id,
        })
        return {
            "contract_version": VERSION,
            "status": "SYNTHETIC_REQUEST_SHAPE_VALIDATED_NO_SEND",
            "reason_code": "OFFLINE_SYNTHETIC_ONLY",
            "question_hash": QUESTION_HASH,
            "request_preview": request_body,
            "http_body_sha256": hashlib.sha256(request.content).hexdigest(),
            "http_body_bytes": len(request.content),
            "input_hash": input_hash,
            "review_identity": identity,
            "local_candidate_identity": {
                "capture_id": candidate["capture_id"],
                "sample_index": candidate["sample_index"],
                "market": candidate["market"],
                "ticker": candidate["ticker"],
                "snapshot_hash": candidate["snapshot_hash"],
            },
            "real_source_transmission_approved": False,
            "historical_decision_eligible": False,
            "provider_eligible": False,
            "provider_calls": 0,
            "db_writes": 0,
        }
    except StockReviewContractError as exc:
        return _deny(exc.code)
    except (TypeError, ValueError, OverflowError):
        return _deny("INPUT_NOT_ELIGIBLE")


def _probability(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StockReviewContractError("CHOICE_PROBABILITY_INVALID")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise StockReviewContractError("CHOICE_PROBABILITY_INVALID")
    return result


def validate_choice_response(payload: Any, *, expected_model: str) -> dict[str, Any]:
    """Validate official Choice envelope, not V4's Noul. Never interpret as returns."""
    if not isinstance(payload, dict):
        raise StockReviewContractError("CHOICE_RESPONSE_INVALID")
    if not isinstance(expected_model, str) or not expected_model.strip():
        raise StockReviewContractError("MODEL_IDENTITY_UNVERIFIED")
    if payload.get("model") != expected_model:
        raise StockReviewContractError("MODEL_IDENTITY_CHANGED")
    answers = payload.get("answers")
    if not isinstance(answers, dict) or set(answers) != {QUESTION_ID}:
        raise StockReviewContractError("CHOICE_ANSWER_SET_MISMATCH")
    answer = answers.get(QUESTION_ID)
    if not isinstance(answer, dict) or set(answer) != {
        "type", "choice", "confidence", "probabilities",
    } or answer.get("type") != "choice":
        raise StockReviewContractError("CHOICE_RESPONSE_SHAPE_INVALID")
    choice = answer.get("choice")
    if not isinstance(choice, str) or choice not in OPTIONS:
        raise StockReviewContractError("CHOICE_OPTION_INVALID")
    confidence = _probability(answer.get("confidence"))
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(OPTIONS):
        raise StockReviewContractError("CHOICE_OPTION_SET_MISMATCH")
    values = {k: _probability(probabilities[k]) for k in OPTIONS}
    if not math.isclose(sum(values.values()), 1.0, abs_tol=0.001, rel_tol=0.0):
        raise StockReviewContractError("CHOICE_PROBABILITIES_NOT_NORMALIZED")
    if values[choice] + 0.000000001 < max(values.values()):
        raise StockReviewContractError("CHOICE_NOT_MAXIMUM")
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise StockReviewContractError("CHOICE_USAGE_INVALID")
    counts = {}
    for key in ("input_tokens", "output_tokens"):
        value = usage.get(key)
        if type(value) is not int or value < 0:
            raise StockReviewContractError("CHOICE_USAGE_INVALID")
        counts[key] = value
    return {
        "contract_version": VERSION,
        "model": expected_model,
        "question_id": QUESTION_ID,
        "choice": choice,
        "probabilities": values,
        "confidence": confidence,
        "usage": counts,
        "display_scope": "REVIEW_PRIORITY_ONLY_NOT_STOCK_RETURN_PROBABILITY",
        "provider_calls": 0,  # Pure parser; no actual model execution here.
    }
