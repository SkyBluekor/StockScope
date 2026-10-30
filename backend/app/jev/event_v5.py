"""P6-C: distinct TypeSafe event-review V5, synthetic-only execution boundary.

Operational Scanner/event data may be classified by route_event_v5, but never
passed to build_event_v5_request. The latter requires the fixed authored fake
fixture and is only used by a locally enabled demo/test via injected provider.
No KRX/Naver/OpenDART content, real tickers, real network, or production writes.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .models import canonical_json, digest_json
from .typesafe_provider import (
    TypeSafeJevProvider, TypeSafeJevProviderError, validate_system_one_response,
)

STATE_VERSION = "JEV_EVENT_REVIEW_STATE_V5"
QUESTION_VERSION = "JEV_EVENT_QUESTIONS_V5"
POLICY_VERSION = "JEV_EVENT_DISPOSITION_POLICY_V5_SYNTHETIC_TEST"
QUESTION_ID = "independent_event_material_review"
TEST_MODEL_ID = "FAKE-JEV-EVENT-V5"
TEST_THRESHOLD = 0.70
MAX_STATE_BYTES = 4096

QUESTION = {
    QUESTION_ID: {
        "type": "noul",
        "instructions": (
            "Using only the explicitly authored synthetic strategy concept and "
            "unresolved independent event assertion provided in this state, "
            "judge if their unresolved semantic relationship warrants material "
            "additional user review. Do not recalculate prices, infer trading "
            "direction, forecast returns, invent facts, search news, or alter "
            "the local Scanner's existing verdict. A missing relationship "
            "cannot be converted into a confirmed contradiction."
        ),
        "criteria": {
            "true": "The unresolved event relationship materially deserves an additional user re-check.",
            "false": "The given evidence does not establish a material need for an additional re-check.",
        },
    },
}
QUESTION_HASH = digest_json({"version": QUESTION_VERSION, "questions": QUESTION})
POLICY_HASH = digest_json({
    "version": POLICY_VERSION,
    "test_only": True,
    "threshold": TEST_THRESHOLD,
    "question_hash": QUESTION_HASH,
    "dispositions": ["REVIEW_REQUIRED", "PASS_THROUGH", "ABSTAIN"],
})
STATE_HASH = digest_json({
    "version": STATE_VERSION,
    "sections": [
        "strategy_concept", "unresolved_event_assertion", "review_scope",
    ],
    "fixture_kind": "AUTHOR_SYNTHETIC_ONLY",
    "max_bytes": MAX_STATE_BYTES,
})


def route_event_v5(assessment: dict[str, Any]) -> dict[str, Any]:
    """Strict local eligibility classification; cannot authorize any transport."""
    status = assessment.get("status")
    candidate = assessment.get("independent_review_candidate") is True
    if status == "NO_INDEPENDENT_EVIDENCE":
        route = "SKIPPED_NO_EVIDENCE"
    elif status == "EVIDENCE_COMPATIBLE":
        route = "SKIPPED_LOCALLY_RESOLVED"
    elif status == "EVIDENCE_CONFLICT":
        route = "LOCAL_REVIEW_REQUIRED"
    elif status == "EVIDENCE_NOT_USABLE":
        route = "BLOCKED_EVIDENCE"
    elif status == "EVIDENCE_UNCERTAIN" and candidate:
        route = "REVIEW_CANDIDATE_PROVIDER_HOLD"
    else:
        route = "BLOCKED_NOT_REVIEW_CANDIDATE"
    return {
        "version": STATE_VERSION,
        "capture_id": assessment.get("capture_id"),
        "sample_index": assessment.get("sample_index"),
        "snapshot_hash": assessment.get("snapshot_hash"),
        "market": assessment.get("market"),
        "ticker": assessment.get("ticker"),
        "event_reference_hash": assessment.get("projection_hash"),
        "assertion_identity_hash": digest_json(
            assessment.get("reviewed_assertion_refs") or [],
        ),
        "event_assessment_status": status,
        "routing": route,
        "semantic_review_candidate": candidate,
        "external_model_call_allowed": False,
        "transmission_status": "PROVIDER_HOLD",
        "model_review_executed": False,
        "model_result": None,
        "reason_codes": sorted(set(
            assessment.get("reason_codes") or []
        ) | {"P6C_REAL_EVENT_AI_RIGHTS_NOT_APPROVED"}),
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def authored_synthetic_fixture() -> dict[str, Any]:
    """One safe fake example not derived from a real Scanner/corporate event."""
    return {
        "contract_version": STATE_VERSION,
        "synthetic_only": True,
        "fixture_id": "JEV_EVENT_V5_AUTHOR_SYNTHETIC_999992",
        "capture_id": "FAKE-EVENT-CAPTURE-999992",
        "sample_index": 0,
        "snapshot_hash": "a" * 64,
        "event_projection_hash": "b" * 64,
        "assertion_identity_hash": "c" * 64,
        "strategy_concept": {
            "concept_id": "support_integrity",
            "definition": "A fictional strategy requires an intact support structure.",
        },
        "unresolved_event_assertion": {
            "event_id": "FAKE-EVENT-1",
            "event_revision": 1,
            "relation": "UNRESOLVED",
            "fact": "A synthetic announcement describes an unresolved operational disruption.",
            "uncertainty": "Its relevance to the hypothetical support concept is unproven.",
            "source_kind": "TEST_SYNTHETIC",
        },
        "review_scope": {
            "mode": "MATERIAL_ADDITIONAL_REVIEW_ONLY",
            "no_trading_advice": True,
            "no_numeric_recomputation": True,
        },
    }


class EventV5ContractError(ValueError):
    pass


def build_event_v5_request(packet: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Only the exact authored synthetic fixture can reach the fake executor.

    Real market data must use a separate future rights-verified adapter; no
    caller can turn one on by setting an env var or a boolean approval flag.
    """
    if packet != authored_synthetic_fixture():
        raise EventV5ContractError("P6C_SYNTHETIC_FIXTURE_IDENTITY_REQUIRED")
    state = {
        "strategy_concept": packet["strategy_concept"],
        "unresolved_event_assertion": packet["unresolved_event_assertion"],
        "review_scope": packet["review_scope"],
    }
    if len(canonical_json(state).encode("utf-8")) > MAX_STATE_BYTES:
        raise EventV5ContractError("P6C_STATE_LIMIT_EXCEEDED")
    request = {
        "state": state,
        "questions": QUESTION,
        "model": TEST_MODEL_ID,
    }
    return request, digest_json({
        "state_contract": STATE_VERSION,
        "state_hash": STATE_HASH,
        "question_contract": QUESTION_VERSION,
        "question_hash": QUESTION_HASH,
        "policy_hash": POLICY_HASH,
        "packet_identity": {
            "capture_id": packet["capture_id"],
            "sample_index": packet["sample_index"],
            "snapshot_hash": packet["snapshot_hash"],
            "event_projection_hash": packet["event_projection_hash"],
            "assertion_identity_hash": packet["assertion_identity_hash"],
        },
        "wire_request": request,
    })


async def review_synthetic_once(
    packet: dict[str, Any],
    provider: TypeSafeJevProvider,
    *,
    timeout_seconds: float = 3.0,
) -> dict[str, Any]:
    """Injected Fake provider only; never construct a network-capable provider."""
    if provider.__class__.__name__ != "FakeTypeSafeJevProvider":
        raise EventV5ContractError("P6C_FAKE_PROVIDER_ONLY")
    request, review_id = build_event_v5_request(packet)
    try:
        result = await asyncio.wait_for(
            provider.review(request, deadline_seconds=timeout_seconds),
            timeout=timeout_seconds,
        )
        normalized = validate_system_one_response(
            result.raw_response,
            expected_model_returned=TEST_MODEL_ID,
            expected_question_ids=(QUESTION_ID,),
        )
        p = normalized["probabilities"][QUESTION_ID]
        verdict = "REVIEW_REQUIRED" if p >= TEST_THRESHOLD else "PASS_THROUGH"
        return {
            "status": "VALID", "disposition": verdict,
            "review_id": review_id,
            "reason_codes": [
                "P6C_SYNTHETIC_MATERIAL_REVIEW" if verdict == "REVIEW_REQUIRED"
                else "P6C_SYNTHETIC_LOW_REVIEW_PRIORITY"
            ],
            "question_contract": QUESTION_VERSION,
            "question_hash": QUESTION_HASH,
            "state_contract": STATE_VERSION,
            "state_hash": STATE_HASH,
            "policy_version": POLICY_VERSION,
            "policy_hash": POLICY_HASH,
            "model_returned": normalized["model"],
            "usage": normalized["usage"],
            "cost_usd": result.cost_usd,
            "cost_unknown": result.cost_unknown,
            "synthetic_only": True,
            "mock_provider_calls": 1,
            "actual_provider_calls": 0,
        }
    except (TypeSafeJevProviderError, asyncio.TimeoutError, ValueError, TypeError, KeyError):
        return {
            "status": "ERROR", "disposition": "ABSTAIN",
            "failure_code": "P6C_SYNTHETIC_MODEL_RESPONSE_REJECTED",
            "review_id": review_id,
            "synthetic_only": True,
            "mock_provider_calls": 1,
            "actual_provider_calls": 0,
        }
