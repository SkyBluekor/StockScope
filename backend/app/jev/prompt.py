from __future__ import annotations

import hashlib
import json
from typing import Any


JEV_PROMPT_VERSION = "JEV_DECISION_REVIEWER_PROMPT_V1"

JEV_SYSTEM_PROMPT = """You are StockScope's JEV Decision Reviewer.

Review exactly one existing StockScope ENTRY_CANDIDATE using only the quantitative evidence included in the request.

Rules:
- Do not discover or recommend other stocks.
- Do not change candidate rank, entry price, stop/invalidation level, target, strategy, horizon, or Risk decision.
- Do not infer or use news, events, macro data, holdings, account data, user data, future outcomes, or historical execution outcomes.
- Do not invent missing evidence.
- Treat StockScope as the baseline decision owner. Your output is a shadow review only.
- Return PASS_THROUGH when the supplied evidence has no material conflict with the baseline decision.
- Return REVIEW_REQUIRED only when the supplied evidence contains a material conflict or caution that warrants human re-checking.
- Return ABSTAIN when the supplied evidence is insufficient, stale, conflicting beyond resolution, or outside scope.
- Every reason must cite only evidence_id values that exist in the request.
- Keep explanations short, factual, and tied to the cited evidence.

Return only the structured output required by the response schema."""

JEV_PROMPT_HASH = hashlib.sha256(
    JEV_SYSTEM_PROMPT.encode("utf-8")
).hexdigest()

_REASON_CODES = [
    "CONDITION_ALIGNMENT",
    "CONDITION_CONFLICT",
    "ENTRY_CONTEXT_CONFLICT",
    "RISK_CAUTION",
    "EVIDENCE_LIMITATION",
]

_ABSTAIN_REASONS = [
    "INSUFFICIENT_EVIDENCE",
    "CONFLICT_UNRESOLVED",
    "OUT_OF_SCOPE",
    "STALE_INPUT",
]

_REASON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "enum": _REASON_CODES,
        },
        "evidence_refs": {
            "type": "array",
            "items": {"type": "string"},
        },
        "explanation": {"type": "string"},
    },
    "required": [
        "code",
        "evidence_refs",
        "explanation",
    ],
    "additionalProperties": False,
}

JEV_OUTPUT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": [
                "PASS_THROUGH",
                "REVIEW_REQUIRED",
                "ABSTAIN",
            ],
        },
        "abstain_reason": {
            "type": ["string", "null"],
            "enum": [*_ABSTAIN_REASONS, None],
        },
        "supporting_reasons": {
            "type": "array",
            "items": _REASON_SCHEMA,
        },
        "opposing_reasons": {
            "type": "array",
            "items": _REASON_SCHEMA,
        },
    },
    "required": [
        "decision",
        "abstain_reason",
        "supporting_reasons",
        "opposing_reasons",
    ],
    "additionalProperties": False,
}

JEV_OUTPUT_SCHEMA_HASH = hashlib.sha256(
    json.dumps(
        JEV_OUTPUT_JSON_SCHEMA,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def prompt_identity() -> dict[str, str]:
    return {
        "prompt_version": JEV_PROMPT_VERSION,
        "prompt_hash": JEV_PROMPT_HASH,
        "output_schema_hash": JEV_OUTPUT_SCHEMA_HASH,
    }
