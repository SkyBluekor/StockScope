from __future__ import annotations

from typing import Any

from app.strategy.semantic_source import verify_semantic_source

from .models import canonical_json, digest_json
from .typesafe_models import (
    JEV_TYPESAFE_PROJECTOR_VERSION_V3,
    JEV_TYPESAFE_STATE_CONTRACT_VERSION_V3,
)
from .typesafe_state import (
    MAX_CONDITIONS,
    MAX_STATE_BYTES,
    MAX_SEMANTIC_TEXT,
    TypeSafeStateProjection,
    TypeSafeStateProjectionError,
)


MAX_INTENT_TEXT = 640
MAX_DEFINITION_TEXT = 360

PROJECTOR_DEFINITION_V3 = {
    "version": JEV_TYPESAFE_PROJECTOR_VERSION_V3,
    "state_contract": JEV_TYPESAFE_STATE_CONTRACT_VERSION_V3,
    "top_level": [
        "strategy_intent",
        "term_definitions",
        "passed_condition_meanings",
    ],
    "max_state_bytes": MAX_STATE_BYTES,
    "max_conditions": MAX_CONDITIONS,
    "semantic_source_required": True,
    "q1_readiness_required": "COMPLETE",
    "raw_numeric_condition_values": False,
}
JEV_TYPESAFE_PROJECTOR_HASH_V3 = digest_json(PROJECTOR_DEFINITION_V3)
JEV_TYPESAFE_STATE_CONTRACT_HASH_V3 = digest_json(
    {
        "version": JEV_TYPESAFE_STATE_CONTRACT_VERSION_V3,
        "projector_hash": JEV_TYPESAFE_PROJECTOR_HASH_V3,
        "top_level": PROJECTOR_DEFINITION_V3["top_level"],
    }
)


def _bounded_text(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise TypeSafeStateProjectionError("SEMANTIC_TEXT_MISSING")
    if len(text) > limit:
        raise TypeSafeStateProjectionError("STATE_LIMIT_EXCEEDED")
    return text


def project_typesafe_state_v3(sample: dict[str, Any]) -> TypeSafeStateProjection:
    if str(sample.get("action") or "") != "ENTRY_CANDIDATE":
        raise TypeSafeStateProjectionError("OUT_OF_SCOPE_ACTION")
    horizon = str(sample.get("horizon_intent") or "")
    if horizon not in {"SHORT", "MEDIUM"}:
        raise TypeSafeStateProjectionError("OUT_OF_SCOPE_HORIZON")

    snapshot = sample.get("snapshot")
    if not isinstance(snapshot, dict):
        raise TypeSafeStateProjectionError("CANONICAL_SNAPSHOT_MISSING")
    source = snapshot.get("semantic_source")
    valid, reason = verify_semantic_source(source)
    if not valid:
        raise TypeSafeStateProjectionError(reason or "SEMANTIC_SOURCE_INVALID")
    assert isinstance(source, dict)

    readiness = source.get("readiness")
    if not isinstance(readiness, dict):
        raise TypeSafeStateProjectionError("SEMANTIC_READINESS_MISSING")
    if str(readiness.get("q1_status") or "") != "COMPLETE":
        raise TypeSafeStateProjectionError("Q1_SEMANTIC_NOT_COMPLETE")

    strategy = source.get("strategy")
    conditions = source.get("conditions")
    if not isinstance(strategy, dict) or not isinstance(conditions, dict):
        raise TypeSafeStateProjectionError("SEMANTIC_SOURCE_INCOMPLETE")

    intent = _bounded_text(strategy.get("intent_text"), limit=MAX_INTENT_TEXT)
    required_ids = [str(item) for item in list(strategy.get("required_definition_ids") or [])]
    definitions = list(strategy.get("definitions") or [])
    if not required_ids or not definitions:
        raise TypeSafeStateProjectionError("Q1_DEFINITIONS_MISSING")

    definition_by_id: dict[str, str] = {}
    for item in definitions:
        if not isinstance(item, dict):
            raise TypeSafeStateProjectionError("Q1_DEFINITION_INVALID")
        definition_id = str(item.get("id") or "").strip()
        if not definition_id or definition_id in definition_by_id:
            raise TypeSafeStateProjectionError("Q1_DEFINITION_INVALID")
        definition_by_id[definition_id] = _bounded_text(
            item.get("text"),
            limit=MAX_DEFINITION_TEXT,
        )
    if set(required_ids) != set(definition_by_id):
        raise TypeSafeStateProjectionError("Q1_DEFINITION_BINDING_MISMATCH")

    items = list(conditions.get("items") or [])
    if not items or len(items) > MAX_CONDITIONS:
        raise TypeSafeStateProjectionError("CONDITION_DETAILS_MISSING")
    passed_meanings: list[dict[str, str]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or str(item.get("status") or "") != "PASS":
            raise TypeSafeStateProjectionError("SEMANTIC_MAPPING_INCOMPLETE")
        meaning = _bounded_text(
            item.get("observed_meaning"),
            limit=MAX_SEMANTIC_TEXT,
        )
        passed_meanings.append(
            {
                "ref": f"condition-{index:02d}",
                "meaning": meaning,
            }
        )

    term_definitions = [
        {
            "ref": f"term-{index:02d}",
            "text": definition_by_id[definition_id],
        }
        for index, definition_id in enumerate(sorted(required_ids), start=1)
    ]
    state = {
        "strategy_intent": {"text": intent},
        "term_definitions": term_definitions,
        "passed_condition_meanings": passed_meanings,
    }
    encoded = canonical_json(state).encode("utf-8")
    if len(encoded) > MAX_STATE_BYTES:
        raise TypeSafeStateProjectionError("STATE_LIMIT_EXCEEDED")

    audit = {
        "capture_run_id": sample.get("capture_run_id"),
        "sample_index": sample.get("sample_index"),
        "snapshot_hash": sample.get("snapshot_hash"),
        "scanner_version": sample.get("scanner_version"),
        "scanner_baseline": sample.get("scanner_baseline"),
        "input_fingerprint": sample.get("input_fingerprint"),
        "semantic_source_contract_version": source.get("source_contract_version"),
        "semantic_source_contract_hash": source.get("source_contract_hash"),
        "semantic_source_snapshot_hash": source.get("source_snapshot_hash"),
        "strategy_semantic_contract_version": strategy.get(
            "semantic_contract_version"
        ),
        "strategy_semantic_contract_hash": strategy.get("semantic_contract_hash"),
        "condition_semantic_mapping_version": conditions.get("mapping_version"),
        "condition_semantic_mapping_hash": conditions.get("mapping_hash"),
        "horizon_policy_version": sample.get("horizon_policy_version"),
    }
    return TypeSafeStateProjection(
        state=state,
        audit=audit,
        state_hash=digest_json(state),
        state_bytes=len(encoded),
        projector_hash=JEV_TYPESAFE_PROJECTOR_HASH_V3,
    )
