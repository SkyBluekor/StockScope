from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.strategy.condition_assertions import (
    ALLOWED_ASSERTION_STANCES,
    STANCE_CONTRADICTS,
    STANCE_NEUTRAL,
    STANCE_SUPPORTS,
    STANCE_UNRESOLVED,
    STANCE_WEAKENS,
)
from app.strategy.semantic_relations import (
    ALLOWED_MATERIALITIES,
    ALLOWED_RELATION_KINDS,
    MATERIALITY_SOFT,
    RELATION_ALLOWS_IF,
    RELATION_EXCLUDES,
    RELATION_REQUIRES_ALL,
    RELATION_REQUIRES_ANY,
)


LOCAL_MATCH = "LOCAL_MATCH"
LOCAL_CONFLICT = "LOCAL_CONFLICT"
LOCAL_INCOMPLETE = "LOCAL_INCOMPLETE"
LOCAL_AMBIGUOUS = "LOCAL_AMBIGUOUS"
RESIDUAL_SEMANTIC_REVIEW = "RESIDUAL_SEMANTIC_REVIEW"

RELATION_MATCH = "MATCH"
RELATION_CONFLICT = "CONFLICT"
RELATION_INCOMPLETE = "INCOMPLETE"
RELATION_AMBIGUOUS = "AMBIGUOUS"
RELATION_RESIDUAL = "RESIDUAL"


@dataclass(frozen=True, slots=True)
class SemanticCompositionResult:
    status: str
    reason_codes: tuple[str, ...]
    relation_results: tuple[dict[str, str], ...]


def _result(
    status: str,
    reasons: list[str] | tuple[str, ...],
    relation_results: list[dict[str, str]] | tuple[dict[str, str], ...] = (),
) -> SemanticCompositionResult:
    return SemanticCompositionResult(
        status,
        tuple(sorted(set(str(item) for item in reasons if item))),
        tuple(dict(item) for item in relation_results),
    )


def incomplete_semantic_composition(
    *reason_codes: str,
) -> SemanticCompositionResult:
    return _result(
        LOCAL_INCOMPLETE,
        list(reason_codes) or ["SEMANTIC_COMPOSITION_INPUT_INCOMPLETE"],
    )


def _concept_state(stances: set[str]) -> str:
    if STANCE_CONTRADICTS in stances:
        return STANCE_CONTRADICTS
    if STANCE_UNRESOLVED in stances or STANCE_WEAKENS in stances:
        return "RESIDUAL"
    if STANCE_SUPPORTS in stances:
        return STANCE_SUPPORTS
    if STANCE_NEUTRAL in stances:
        return STANCE_NEUTRAL
    return "MISSING"


def _relation_result(
    relation_id: str,
    status: str,
    reason: str,
) -> dict[str, str]:
    return {
        "relation_id": relation_id,
        "status": status,
        "reason_code": reason,
    }


def compose_semantics(
    *,
    relation_contract: dict[str, Any],
    assertions: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> SemanticCompositionResult:
    if not isinstance(relation_contract, dict):
        return incomplete_semantic_composition(
            "SEMANTIC_COMPOSITION_RELATION_CONTRACT_MISSING"
        )

    concepts = list(relation_contract.get("concepts") or [])
    relations = list(relation_contract.get("relations") or [])
    if not concepts or not relations:
        return incomplete_semantic_composition(
            "SEMANTIC_COMPOSITION_RELATION_CONTRACT_INVALID"
        )

    concept_ids: set[str] = set()
    for item in concepts:
        if not isinstance(item, dict):
            return incomplete_semantic_composition(
                "SEMANTIC_COMPOSITION_CONCEPT_INVALID"
            )
        concept_id = str(item.get("concept_id") or "")
        if not concept_id or concept_id in concept_ids:
            return incomplete_semantic_composition(
                "SEMANTIC_COMPOSITION_CONCEPT_INVALID"
            )
        concept_ids.add(concept_id)

    stances_by_concept: dict[str, set[str]] = {
        concept_id: set() for concept_id in concept_ids
    }
    if not assertions:
        return incomplete_semantic_composition(
            "SEMANTIC_COMPOSITION_ASSERTIONS_MISSING"
        )

    for assertion in assertions:
        if not isinstance(assertion, dict):
            return incomplete_semantic_composition(
                "SEMANTIC_COMPOSITION_ASSERTION_INVALID"
            )
        stance = str(assertion.get("stance") or "")
        refs = [str(item) for item in list(assertion.get("concept_refs") or [])]
        if stance not in ALLOWED_ASSERTION_STANCES or not refs:
            return incomplete_semantic_composition(
                "SEMANTIC_COMPOSITION_ASSERTION_INVALID"
            )
        if not set(refs) <= concept_ids:
            return incomplete_semantic_composition(
                "SEMANTIC_COMPOSITION_ASSERTION_CONCEPT_UNKNOWN"
            )
        for ref in refs:
            stances_by_concept[ref].add(stance)

    ambiguous = [
        concept_id
        for concept_id, stances in stances_by_concept.items()
        if STANCE_SUPPORTS in stances and STANCE_CONTRADICTS in stances
    ]
    if ambiguous:
        return _result(
            LOCAL_AMBIGUOUS,
            [
                f"SEMANTIC_COMPOSITION_CONCEPT_AMBIGUOUS:{concept_id}"
                for concept_id in ambiguous
            ],
        )

    relation_results: list[dict[str, str]] = []
    for relation in relations:
        if not isinstance(relation, dict):
            return incomplete_semantic_composition(
                "SEMANTIC_COMPOSITION_RELATION_INVALID"
            )
        relation_id = str(relation.get("relation_id") or "")
        kind = str(relation.get("kind") or "")
        materiality = str(relation.get("materiality") or "")
        members = [str(item) for item in list(relation.get("members") or [])]
        guards = [str(item) for item in list(relation.get("guards") or [])]
        if (
            not relation_id
            or kind not in ALLOWED_RELATION_KINDS
            or materiality not in ALLOWED_MATERIALITIES
            or not members
            or not set(members) <= concept_ids
            or not set(guards) <= concept_ids
            or (kind == RELATION_ALLOWS_IF and not guards)
            or (kind != RELATION_ALLOWS_IF and guards)
        ):
            return incomplete_semantic_composition(
                "SEMANTIC_COMPOSITION_RELATION_INVALID"
            )

        member_states = [
            _concept_state(stances_by_concept[concept_id])
            for concept_id in members
        ]
        guard_states = [
            _concept_state(stances_by_concept[concept_id])
            for concept_id in guards
        ]

        status = RELATION_MATCH
        reason = "SEMANTIC_RELATION_MATCH"

        if kind == RELATION_REQUIRES_ALL:
            if STANCE_CONTRADICTS in member_states:
                status = RELATION_CONFLICT
                reason = "SEMANTIC_RELATION_REQUIRED_CONTRADICTED"
            elif "MISSING" in member_states or STANCE_NEUTRAL in member_states:
                status = RELATION_INCOMPLETE
                reason = "SEMANTIC_RELATION_REQUIRED_MISSING"
            elif "RESIDUAL" in member_states:
                status = RELATION_RESIDUAL
                reason = "SEMANTIC_RELATION_REQUIRED_UNRESOLVED"

        elif kind == RELATION_REQUIRES_ANY:
            if STANCE_SUPPORTS in member_states:
                status = RELATION_MATCH
            elif all(state == STANCE_CONTRADICTS for state in member_states):
                status = RELATION_CONFLICT
                reason = "SEMANTIC_RELATION_ANY_CONTRADICTED"
            elif "RESIDUAL" in member_states:
                status = RELATION_RESIDUAL
                reason = "SEMANTIC_RELATION_ANY_UNRESOLVED"
            else:
                status = RELATION_INCOMPLETE
                reason = "SEMANTIC_RELATION_ANY_MISSING"

        elif kind == RELATION_ALLOWS_IF:
            if STANCE_CONTRADICTS in member_states:
                status = RELATION_CONFLICT
                reason = "SEMANTIC_RELATION_EXCEPTION_CONTRADICTED"
            elif "MISSING" in member_states or STANCE_NEUTRAL in member_states:
                status = RELATION_INCOMPLETE
                reason = "SEMANTIC_RELATION_EXCEPTION_MISSING"
            elif "RESIDUAL" in member_states:
                if STANCE_CONTRADICTS in guard_states:
                    status = RELATION_CONFLICT
                    reason = "SEMANTIC_RELATION_EXCEPTION_GUARD_CONTRADICTED"
                elif "MISSING" in guard_states or STANCE_NEUTRAL in guard_states:
                    status = RELATION_INCOMPLETE
                    reason = "SEMANTIC_RELATION_EXCEPTION_GUARD_MISSING"
                elif "RESIDUAL" in guard_states:
                    status = RELATION_RESIDUAL
                    reason = "SEMANTIC_RELATION_EXCEPTION_GUARD_UNRESOLVED"
                else:
                    member_raw = set().union(
                        *(stances_by_concept[item] for item in members)
                    )
                    if STANCE_UNRESOLVED in member_raw:
                        status = RELATION_RESIDUAL
                        reason = "SEMANTIC_RELATION_EXCEPTION_UNRESOLVED"
                    else:
                        status = RELATION_MATCH
                        reason = "SEMANTIC_RELATION_EXCEPTION_ALLOWED"

        elif kind == RELATION_EXCLUDES:
            if STANCE_SUPPORTS in member_states:
                status = RELATION_CONFLICT
                reason = "SEMANTIC_RELATION_EXCLUDED_PRESENT"
            elif "RESIDUAL" in member_states:
                status = RELATION_RESIDUAL
                reason = "SEMANTIC_RELATION_EXCLUDED_UNRESOLVED"
            elif all(state == STANCE_CONTRADICTS for state in member_states):
                status = RELATION_MATCH
            else:
                status = RELATION_INCOMPLETE
                reason = "SEMANTIC_RELATION_EXCLUDED_MISSING"

        if status == RELATION_CONFLICT and materiality == MATERIALITY_SOFT:
            status = RELATION_RESIDUAL
            reason = "SEMANTIC_RELATION_SOFT_CONFLICT_REVIEW"

        relation_results.append(_relation_result(relation_id, status, reason))

    statuses = {item["status"] for item in relation_results}
    if RELATION_AMBIGUOUS in statuses:
        overall = LOCAL_AMBIGUOUS
    elif RELATION_CONFLICT in statuses:
        overall = LOCAL_CONFLICT
    elif RELATION_INCOMPLETE in statuses:
        overall = LOCAL_INCOMPLETE
    elif RELATION_RESIDUAL in statuses:
        overall = RESIDUAL_SEMANTIC_REVIEW
    else:
        overall = LOCAL_MATCH

    reasons = [
        item["reason_code"]
        for item in relation_results
        if item["status"] != RELATION_MATCH
    ]
    if not reasons:
        reasons = ["SEMANTIC_COMPOSITION_MATCH"]

    return _result(overall, reasons, relation_results)
