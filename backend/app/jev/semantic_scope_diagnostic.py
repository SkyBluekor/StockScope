"""Offline semantic integrity inspection for legacy-horizon Scanner captures.

This is NOT a Jev provider route. It deliberately never overrides the
SHORT/MEDIUM gate in typesafe_state_v4 or builds a provider request.
"""
from __future__ import annotations

from typing import Any

from app.prospective.models import digest_json
from app.strategy.semantic_composition import (
    LOCAL_AMBIGUOUS,
    LOCAL_CONFLICT,
    LOCAL_INCOMPLETE,
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
    compose_semantics,
)
from app.strategy.semantic_source_v2 import verify_semantic_source_v2

SEMANTIC_SOURCE_MISSING = "SEMANTIC_SOURCE_MISSING"
SEMANTIC_SOURCE_INVALID = "SEMANTIC_SOURCE_INVALID"
RESIDUAL_REVIEW_OBSERVED = "RESIDUAL_REVIEW_OBSERVED"

LOCAL_INSPECTION_CATEGORIES = (
    LOCAL_MATCH,
    LOCAL_CONFLICT,
    LOCAL_INCOMPLETE,
    LOCAL_AMBIGUOUS,
    RESIDUAL_REVIEW_OBSERVED,
    SEMANTIC_SOURCE_MISSING,
    SEMANTIC_SOURCE_INVALID,
)
_KNOWN_LOCAL = frozenset({
    LOCAL_MATCH, LOCAL_CONFLICT, LOCAL_INCOMPLETE,
    LOCAL_AMBIGUOUS, RESIDUAL_SEMANTIC_REVIEW,
})


def inspect_stored_semantic_source(
    snapshot: Any,
    *,
    stored_snapshot_hash: str | None = None,
) -> str:
    """Return only a category, without leaking any stock or source content.

    Requires V2 source identity and recomposes *valid* relation assertions.
    For insufficient authored source, preserve the local INCOMPLETE status
    without inventing assertions or a strategy meaning.
    """
    if not isinstance(snapshot, dict):
        return SEMANTIC_SOURCE_INVALID
    if stored_snapshot_hash and digest_json(snapshot) != stored_snapshot_hash:
        return SEMANTIC_SOURCE_INVALID

    source = snapshot.get("semantic_source_v2")
    if not isinstance(source, dict):
        return SEMANTIC_SOURCE_MISSING
    try:
        valid, _ = verify_semantic_source_v2(source)
        if not valid:
            return SEMANTIC_SOURCE_INVALID
        readiness = source.get("readiness")
        relations = source.get("relations")
        conditions = source.get("conditions")
        stored_composition = source.get("local_semantic_composition")
        if not all(isinstance(item, dict) for item in (
            readiness, relations, conditions, stored_composition
        )):
            return SEMANTIC_SOURCE_INVALID
        status = readiness.get("local_semantic_status")
        if status not in _KNOWN_LOCAL:
            return SEMANTIC_SOURCE_INVALID
        if stored_composition.get("status") != status:
            return SEMANTIC_SOURCE_INVALID
        eligible = readiness.get("residual_review_eligible")
        if not isinstance(eligible, bool) or eligible != (
            status == RESIDUAL_SEMANTIC_REVIEW
        ):
            return SEMANTIC_SOURCE_INVALID

        reasons = readiness.get("local_semantic_reasons")
        saved_reasons = stored_composition.get("reason_codes")
        saved_relations = stored_composition.get("relation_results")
        assertion_items = conditions.get("items")
        if (
            not isinstance(reasons, list)
            or not isinstance(saved_reasons, list)
            or not isinstance(saved_relations, list)
            or not isinstance(assertion_items, list)
            or reasons != saved_reasons
            or any(not isinstance(item, dict) for item in saved_relations)
        ):
            return SEMANTIC_SOURCE_INVALID

        # If authored data is incomplete, the production builder uses
        # incomplete_semantic_composition(reasons); the relation composer
        # must NOT replace its authored missing-input reasons.
        complete_relations = bool(
            relations.get("relation_contract_hash")
            and relations.get("concepts")
            and relations.get("relations")
            and assertion_items
        )
        if complete_relations:
            composed = compose_semantics(
                relation_contract=relations,
                assertions=assertion_items,
            )
            if (
                composed.status != status
                or list(composed.reason_codes) != reasons
                or [dict(x) for x in composed.relation_results] != saved_relations
            ):
                return SEMANTIC_SOURCE_INVALID
        elif status != LOCAL_INCOMPLETE or saved_relations:
            return SEMANTIC_SOURCE_INVALID

        if status == RESIDUAL_SEMANTIC_REVIEW:
            return RESIDUAL_REVIEW_OBSERVED
        return str(status)
    except (KeyError, TypeError, ValueError, AttributeError):
        return SEMANTIC_SOURCE_INVALID
