from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.strategy.models import StrategyName
from app.strategy.semantic_contract import (
    SEMANTIC_STATUS_COMPLETE,
    SEMANTIC_STATUS_INVALID_BINDING,
    SEMANTIC_STATUS_UNSUPPORTED,
    resolve_strategy_semantic_contract,
)


STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION = (
    "STRATEGY_SEMANTIC_RELATION_CONTRACT_V1"
)

RELATION_REQUIRES_ALL = "REQUIRES_ALL"
RELATION_REQUIRES_ANY = "REQUIRES_ANY"
RELATION_ALLOWS_IF = "ALLOWS_IF"
RELATION_EXCLUDES = "EXCLUDES"
ALLOWED_RELATION_KINDS = frozenset(
    {
        RELATION_REQUIRES_ALL,
        RELATION_REQUIRES_ANY,
        RELATION_ALLOWS_IF,
        RELATION_EXCLUDES,
    }
)

MATERIALITY_HARD = "HARD"
MATERIALITY_SOFT = "SOFT"
ALLOWED_MATERIALITIES = frozenset({MATERIALITY_HARD, MATERIALITY_SOFT})


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


# V4 does not invent a new semantic concept merely to create work for Jev.
# The relation members below are constrained to the definition ids already
# authored in semantic_contract.py.
_AUTHORED_RELATIONS: dict[str, tuple[dict[str, Any], ...]] = {
    StrategyName.TREND_FOLLOWING.value: (
        {
            "relation_id": "trend-following-required-structure",
            "kind": RELATION_REQUIRES_ALL,
            "members": ["trend_structure", "relative_strength"],
            "guards": [],
            "materiality": MATERIALITY_HARD,
        },
    ),
    StrategyName.PULLBACK.value: (
        {
            "relation_id": "pullback-required-structure",
            "kind": RELATION_REQUIRES_ALL,
            "members": ["trend_structure", "support_integrity"],
            "guards": [],
            "materiality": MATERIALITY_HARD,
        },
    ),
    StrategyName.BREAKOUT.value: (
        {
            "relation_id": "breakout-required-structure",
            "kind": RELATION_REQUIRES_ALL,
            "members": ["participation", "trend_structure"],
            "guards": [],
            "materiality": MATERIALITY_HARD,
        },
    ),
    StrategyName.SUPPORT_BOUNCE.value: (
        {
            "relation_id": "support-bounce-required-structure",
            "kind": RELATION_REQUIRES_ALL,
            "members": ["support_integrity", "mean_reversion_scope"],
            "guards": [],
            "materiality": MATERIALITY_HARD,
        },
    ),
    StrategyName.OVERSOLD_BOUNCE.value: (
        {
            "relation_id": "oversold-bounce-required-structure",
            "kind": RELATION_REQUIRES_ALL,
            "members": ["mean_reversion_scope", "support_integrity"],
            "guards": [],
            "materiality": MATERIALITY_HARD,
        },
    ),
    StrategyName.RANGE_TRADING.value: (
        {
            "relation_id": "range-trading-required-structure",
            "kind": RELATION_REQUIRES_ALL,
            "members": ["range_structure", "support_integrity"],
            "guards": [],
            "materiality": MATERIALITY_HARD,
        },
    ),
    StrategyName.MOMENTUM_CONTINUATION.value: (
        {
            "relation_id": "momentum-continuation-required-structure",
            "kind": RELATION_REQUIRES_ALL,
            "members": [
                "trend_structure",
                "participation",
                "relative_strength",
            ],
            "guards": [],
            "materiality": MATERIALITY_HARD,
        },
    ),
    StrategyName.VOLATILITY_SQUEEZE.value: (
        {
            "relation_id": "volatility-squeeze-required-structure",
            "kind": RELATION_REQUIRES_ALL,
            "members": ["compression", "trend_structure"],
            "guards": [],
            "materiality": MATERIALITY_HARD,
        },
    ),
    StrategyName.MA20_REBOUND.value: (
        {
            "relation_id": "ma20-rebound-required-structure",
            "kind": RELATION_REQUIRES_ALL,
            "members": ["trend_structure", "support_integrity"],
            "guards": [],
            "materiality": MATERIALITY_HARD,
        },
    ),
    StrategyName.TREND_RECOVERY.value: (
        {
            "relation_id": "trend-recovery-required-structure",
            "kind": RELATION_REQUIRES_ALL,
            "members": ["recovery_structure", "support_integrity"],
            "guards": [],
            "materiality": MATERIALITY_HARD,
        },
    ),
}


@dataclass(frozen=True, slots=True)
class StrategySemanticRelationResolution:
    status: str
    reason_code: str | None
    contract: dict[str, Any] | None


def authored_relation_strategy_keys() -> tuple[str, ...]:
    return tuple(sorted(_AUTHORED_RELATIONS))


def _validate_relations(
    *,
    concept_ids: set[str],
    relations: list[dict[str, Any]],
) -> bool:
    relation_ids: set[str] = set()
    for relation in relations:
        relation_id = str(relation.get("relation_id") or "").strip()
        kind = str(relation.get("kind") or "").strip()
        materiality = str(relation.get("materiality") or "").strip()
        members = [str(item) for item in list(relation.get("members") or [])]
        guards = [str(item) for item in list(relation.get("guards") or [])]

        if not relation_id or relation_id in relation_ids:
            return False
        relation_ids.add(relation_id)
        if kind not in ALLOWED_RELATION_KINDS:
            return False
        if materiality not in ALLOWED_MATERIALITIES:
            return False
        if not members or not set(members) <= concept_ids:
            return False
        if not set(guards) <= concept_ids:
            return False
        if kind == RELATION_ALLOWS_IF and not guards:
            return False
        if kind != RELATION_ALLOWS_IF and guards:
            return False
    return True


def resolve_strategy_semantic_relation_contract(
    *,
    strategy_key: str,
    strategy_version_id: str | None,
    strategy_definition_hash: str | None,
) -> StrategySemanticRelationResolution:
    key = str(strategy_key or "").strip().lower()
    authored_relations = _AUTHORED_RELATIONS.get(key)
    if authored_relations is None:
        return StrategySemanticRelationResolution(
            SEMANTIC_STATUS_UNSUPPORTED,
            "SEMANTIC_RELATION_STRATEGY_UNSUPPORTED",
            None,
        )

    base = resolve_strategy_semantic_contract(
        strategy_key=key,
        strategy_version_id=strategy_version_id,
        strategy_definition_hash=strategy_definition_hash,
    )
    if base.status != SEMANTIC_STATUS_COMPLETE or not isinstance(base.contract, dict):
        return StrategySemanticRelationResolution(
            base.status,
            base.reason_code or "SEMANTIC_RELATION_BASE_CONTRACT_UNAVAILABLE",
            None,
        )

    q1 = base.contract.get("q1")
    if not isinstance(q1, dict):
        return StrategySemanticRelationResolution(
            SEMANTIC_STATUS_INVALID_BINDING,
            "SEMANTIC_RELATION_BASE_Q1_INVALID",
            None,
        )

    definitions = list(q1.get("definitions") or [])
    concept_ids = {
        str(item.get("id") or "")
        for item in definitions
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    required_ids = {
        str(item) for item in list(q1.get("required_definition_ids") or [])
    }
    if not concept_ids or concept_ids != required_ids:
        return StrategySemanticRelationResolution(
            SEMANTIC_STATUS_INVALID_BINDING,
            "SEMANTIC_RELATION_CONCEPT_BINDING_INVALID",
            None,
        )

    relations = [dict(item) for item in authored_relations]
    if not _validate_relations(concept_ids=concept_ids, relations=relations):
        return StrategySemanticRelationResolution(
            SEMANTIC_STATUS_INVALID_BINDING,
            "SEMANTIC_RELATION_DEFINITION_INVALID",
            None,
        )

    concepts = [
        {
            "concept_id": str(item["id"]),
            "definition_id": str(item["id"]),
            "text": str(item["text"]),
        }
        for item in definitions
    ]
    payload = {
        "contract_version": STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION,
        "strategy_key": key,
        "strategy_version_id": base.contract.get("strategy_version_id"),
        "strategy_definition_hash": base.contract.get("strategy_definition_hash"),
        "strategy_semantic_contract_version": base.contract.get("contract_version"),
        "strategy_semantic_contract_hash": base.contract.get(
            "semantic_contract_hash"
        ),
        "concepts": concepts,
        "relations": relations,
    }
    return StrategySemanticRelationResolution(
        SEMANTIC_STATUS_COMPLETE,
        None,
        {**payload, "relation_contract_hash": _digest(payload)},
    )


def semantic_relation_contract_hash(contract: dict[str, Any]) -> str:
    body = dict(contract)
    body.pop("relation_contract_hash", None)
    return _digest(body)
