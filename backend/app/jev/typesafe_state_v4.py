from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.strategy.semantic_composition import (
    LOCAL_AMBIGUOUS,
    LOCAL_CONFLICT,
    LOCAL_INCOMPLETE,
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
    compose_semantics,
)
from app.strategy.semantic_source_v2 import verify_semantic_source_v2

from .models import canonical_json, digest_json
from .typesafe_models import (
    JEV_TYPESAFE_PROJECTOR_VERSION_V4,
    JEV_TYPESAFE_STATE_CONTRACT_VERSION_V4,
)
from .typesafe_state import (
    MAX_CONDITIONS,
    MAX_SEMANTIC_TEXT,
    MAX_STATE_BYTES,
    TypeSafeStateProjection,
    TypeSafeStateProjectionError,
)


MAX_INTENT_TEXT_V4 = 640
MAX_DEFINITION_TEXT_V4 = 360
MAX_RELATIONS_V4 = 16
MAX_RELATION_REFS_V4 = 8

SKIPPED_LOCAL_MATCH = "SKIPPED_LOCAL_MATCH"
SKIPPED_LOCAL_CONFLICT = "SKIPPED_LOCAL_CONFLICT"
SKIPPED_SOURCE_INCOMPLETE = "SKIPPED_SOURCE_INCOMPLETE"
SKIPPED_SOURCE_AMBIGUOUS = "SKIPPED_SOURCE_AMBIGUOUS"
PROVIDER_CALL_ELIGIBLE = "PROVIDER_CALL_ELIGIBLE"

_NO_CALL_REASON_BY_STATUS = {
    LOCAL_MATCH: SKIPPED_LOCAL_MATCH,
    LOCAL_CONFLICT: SKIPPED_LOCAL_CONFLICT,
    LOCAL_INCOMPLETE: SKIPPED_SOURCE_INCOMPLETE,
    LOCAL_AMBIGUOUS: SKIPPED_SOURCE_AMBIGUOUS,
}


PROJECTOR_DEFINITION_V4 = {
    "version": JEV_TYPESAFE_PROJECTOR_VERSION_V4,
    "state_contract": JEV_TYPESAFE_STATE_CONTRACT_VERSION_V4,
    "top_level": [
        "strategy_intent",
        "term_definitions",
        "authored_relations",
        "passed_condition_meanings",
    ],
    "max_state_bytes": MAX_STATE_BYTES,
    "max_conditions": MAX_CONDITIONS,
    "max_relations": MAX_RELATIONS_V4,
    "semantic_source_required": "JEV_SEMANTIC_SOURCE_V2",
    "local_gate_required": RESIDUAL_SEMANTIC_REVIEW,
    "raw_numeric_condition_values": False,
    "local_verdict_in_provider_wire": False,
    "condition_stance_in_provider_wire": False,
}
JEV_TYPESAFE_PROJECTOR_HASH_V4 = digest_json(PROJECTOR_DEFINITION_V4)
JEV_TYPESAFE_STATE_CONTRACT_HASH_V4 = digest_json(
    {
        "version": JEV_TYPESAFE_STATE_CONTRACT_VERSION_V4,
        "projector_hash": JEV_TYPESAFE_PROJECTOR_HASH_V4,
        "top_level": PROJECTOR_DEFINITION_V4["top_level"],
    }
)


@dataclass(frozen=True, slots=True)
class TypeSafeV4Route:
    local_status: str
    provider_eligible: bool
    reason_code: str


def _bounded_text(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise TypeSafeStateProjectionError("SEMANTIC_TEXT_MISSING")
    if len(text) > limit:
        raise TypeSafeStateProjectionError("STATE_LIMIT_EXCEEDED")
    return text


def _validated_source(sample: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if str(sample.get("action") or "") != "ENTRY_CANDIDATE":
        raise TypeSafeStateProjectionError("OUT_OF_SCOPE_ACTION")
    horizon = str(sample.get("horizon_intent") or "")
    if horizon not in {"SHORT", "MEDIUM"}:
        raise TypeSafeStateProjectionError("OUT_OF_SCOPE_HORIZON")

    snapshot = sample.get("snapshot")
    if not isinstance(snapshot, dict):
        raise TypeSafeStateProjectionError("CANONICAL_SNAPSHOT_MISSING")

    source = snapshot.get("semantic_source_v2")
    valid, reason = verify_semantic_source_v2(source)
    if not valid:
        raise TypeSafeStateProjectionError(reason or "SEMANTIC_SOURCE_V2_INVALID")
    assert isinstance(source, dict)

    readiness = source.get("readiness")
    relations = source.get("relations")
    conditions = source.get("conditions")
    if (
        not isinstance(readiness, dict)
        or not isinstance(relations, dict)
        or not isinstance(conditions, dict)
    ):
        raise TypeSafeStateProjectionError("SEMANTIC_SOURCE_V2_INCOMPLETE")

    local_status = str(readiness.get("local_semantic_status") or "")
    assertions = list(conditions.get("items") or [])
    composition = compose_semantics(
        relation_contract=relations,
        assertions=assertions,
    )
    if composition.status != local_status:
        raise TypeSafeStateProjectionError("SEMANTIC_LOCAL_STATUS_MISMATCH")

    eligible_flag = readiness.get("residual_review_eligible")
    expected_flag = local_status == RESIDUAL_SEMANTIC_REVIEW
    if not isinstance(eligible_flag, bool) or eligible_flag is not expected_flag:
        raise TypeSafeStateProjectionError("SEMANTIC_RESIDUAL_ELIGIBILITY_MISMATCH")

    if local_status not in {
        LOCAL_MATCH,
        LOCAL_CONFLICT,
        LOCAL_INCOMPLETE,
        LOCAL_AMBIGUOUS,
        RESIDUAL_SEMANTIC_REVIEW,
    }:
        raise TypeSafeStateProjectionError("SEMANTIC_LOCAL_STATUS_INVALID")

    return source, local_status


def route_typesafe_state_v4(sample: dict[str, Any]) -> TypeSafeV4Route:
    _source, local_status = _validated_source(sample)
    if local_status == RESIDUAL_SEMANTIC_REVIEW:
        return TypeSafeV4Route(
            local_status=local_status,
            provider_eligible=True,
            reason_code=PROVIDER_CALL_ELIGIBLE,
        )
    return TypeSafeV4Route(
        local_status=local_status,
        provider_eligible=False,
        reason_code=_NO_CALL_REASON_BY_STATUS[local_status],
    )


def project_typesafe_state_v4(sample: dict[str, Any]) -> TypeSafeStateProjection:
    source, local_status = _validated_source(sample)
    if local_status != RESIDUAL_SEMANTIC_REVIEW:
        raise TypeSafeStateProjectionError(_NO_CALL_REASON_BY_STATUS[local_status])

    strategy = source.get("strategy")
    relation_contract = source.get("relations")
    conditions = source.get("conditions")
    if (
        not isinstance(strategy, dict)
        or not isinstance(relation_contract, dict)
        or not isinstance(conditions, dict)
    ):
        raise TypeSafeStateProjectionError("SEMANTIC_SOURCE_V2_INCOMPLETE")

    intent = _bounded_text(
        strategy.get("intent_text"),
        limit=MAX_INTENT_TEXT_V4,
    )

    concepts = list(relation_contract.get("concepts") or [])
    if not concepts:
        raise TypeSafeStateProjectionError("Q1_DEFINITIONS_MISSING")

    concept_text_by_id: dict[str, str] = {}
    for item in concepts:
        if not isinstance(item, dict):
            raise TypeSafeStateProjectionError("Q1_DEFINITION_INVALID")
        concept_id = str(item.get("concept_id") or "").strip()
        definition_id = str(item.get("definition_id") or "").strip()
        if (
            not concept_id
            or not definition_id
            or concept_id != definition_id
            or concept_id in concept_text_by_id
        ):
            raise TypeSafeStateProjectionError("Q1_DEFINITION_INVALID")
        concept_text_by_id[concept_id] = _bounded_text(
            item.get("text"),
            limit=MAX_DEFINITION_TEXT_V4,
        )

    required_ids = {
        str(item)
        for item in list(strategy.get("required_definition_ids") or [])
    }
    if required_ids != set(concept_text_by_id):
        raise TypeSafeStateProjectionError("Q1_DEFINITION_BINDING_MISMATCH")

    term_ref_by_concept = {
        concept_id: f"term-{index:02d}"
        for index, concept_id in enumerate(sorted(concept_text_by_id), start=1)
    }
    term_definitions = [
        {
            "ref": term_ref_by_concept[concept_id],
            "text": concept_text_by_id[concept_id],
        }
        for concept_id in sorted(concept_text_by_id)
    ]

    relation_rows = list(relation_contract.get("relations") or [])
    if not relation_rows or len(relation_rows) > MAX_RELATIONS_V4:
        raise TypeSafeStateProjectionError("Q1_RELATIONS_INVALID")

    authored_relations: list[dict[str, Any]] = []
    seen_relation_ids: set[str] = set()
    for index, relation in enumerate(
        sorted(
            relation_rows,
            key=lambda item: str(item.get("relation_id") or "")
            if isinstance(item, dict)
            else "",
        ),
        start=1,
    ):
        if not isinstance(relation, dict):
            raise TypeSafeStateProjectionError("Q1_RELATIONS_INVALID")
        relation_id = str(relation.get("relation_id") or "").strip()
        kind = str(relation.get("kind") or "").strip()
        materiality = str(relation.get("materiality") or "").strip()
        members = [str(item) for item in list(relation.get("members") or [])]
        guards = [str(item) for item in list(relation.get("guards") or [])]
        if (
            not relation_id
            or relation_id in seen_relation_ids
            or not kind
            or not materiality
            or not members
            or len(members) > MAX_RELATION_REFS_V4
            or len(guards) > MAX_RELATION_REFS_V4
            or not set(members) <= set(term_ref_by_concept)
            or not set(guards) <= set(term_ref_by_concept)
        ):
            raise TypeSafeStateProjectionError("Q1_RELATIONS_INVALID")
        seen_relation_ids.add(relation_id)
        authored_relations.append(
            {
                "ref": f"relation-{index:02d}",
                "kind": kind,
                "member_refs": [term_ref_by_concept[item] for item in members],
                "guard_refs": [term_ref_by_concept[item] for item in guards],
                "materiality": materiality,
            }
        )

    condition_items = list(conditions.get("items") or [])
    if not condition_items or len(condition_items) > MAX_CONDITIONS:
        raise TypeSafeStateProjectionError("CONDITION_DETAILS_MISSING")

    passed_meanings: list[dict[str, Any]] = []
    for index, item in enumerate(condition_items, start=1):
        if not isinstance(item, dict):
            raise TypeSafeStateProjectionError("SEMANTIC_MAPPING_INCOMPLETE")
        refs = [str(ref) for ref in list(item.get("concept_refs") or [])]
        if not refs or not set(refs) <= set(term_ref_by_concept):
            raise TypeSafeStateProjectionError("SEMANTIC_MAPPING_INCOMPLETE")
        meaning = _bounded_text(
            item.get("observed_meaning"),
            limit=MAX_SEMANTIC_TEXT,
        )
        passed_meanings.append(
            {
                "ref": f"condition-{index:02d}",
                "concept_refs": [term_ref_by_concept[ref] for ref in refs],
                "meaning": meaning,
            }
        )

    state = {
        "strategy_intent": {"text": intent},
        "term_definitions": term_definitions,
        "authored_relations": authored_relations,
        "passed_condition_meanings": passed_meanings,
    }
    encoded = canonical_json(state).encode("utf-8")
    if len(encoded) > MAX_STATE_BYTES:
        raise TypeSafeStateProjectionError("STATE_LIMIT_EXCEEDED")

    readiness = source.get("readiness")
    audit = {
        "capture_run_id": sample.get("capture_run_id"),
        "sample_index": sample.get("sample_index"),
        "snapshot_hash": sample.get("snapshot_hash"),
        "semantic_source_contract_version": source.get("source_contract_version"),
        "semantic_source_contract_hash": source.get("source_contract_hash"),
        "semantic_source_snapshot_hash": source.get("source_snapshot_hash"),
        "relation_contract_version": relation_contract.get("contract_version"),
        "relation_contract_hash": relation_contract.get("relation_contract_hash"),
        "condition_assertion_mapping_version": conditions.get(
            "assertion_mapping_version"
        ),
        "condition_assertion_mapping_hash": conditions.get(
            "assertion_mapping_hash"
        ),
        "local_semantic_status": (
            readiness.get("local_semantic_status")
            if isinstance(readiness, dict)
            else None
        ),
    }
    return TypeSafeStateProjection(
        state=state,
        audit=audit,
        state_hash=digest_json(state),
        state_bytes=len(encoded),
        projector_hash=JEV_TYPESAFE_PROJECTOR_HASH_V4,
    )
