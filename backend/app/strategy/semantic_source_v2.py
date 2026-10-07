from __future__ import annotations

import hashlib
import json
from typing import Any

from app.strategy.condition_assertions import (
    CONDITION_SEMANTIC_ASSERTION_MAPPING_HASH,
    CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION,
    project_passed_condition_assertions,
)
from app.strategy.semantic_composition import (
    RESIDUAL_SEMANTIC_REVIEW,
    SemanticCompositionResult,
    compose_semantics,
    incomplete_semantic_composition,
)
from app.strategy.semantic_contract import SEMANTIC_STATUS_COMPLETE
from app.strategy.semantic_relations import (
    STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION,
    resolve_strategy_semantic_relation_contract,
    semantic_relation_contract_hash,
)
from app.strategy.semantic_source import (
    JEV_SEMANTIC_SOURCE_CONTRACT_HASH,
    JEV_SEMANTIC_SOURCE_VERSION,
    build_semantic_source,
)


JEV_SEMANTIC_SOURCE_VERSION_V2 = "JEV_SEMANTIC_SOURCE_V2"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


JEV_SEMANTIC_SOURCE_CONTRACT_HASH_V2 = _digest(
    {
        "version": JEV_SEMANTIC_SOURCE_VERSION_V2,
        "base_source_version": JEV_SEMANTIC_SOURCE_VERSION,
        "relation_contract_version": STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION,
        "assertion_mapping_version": CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION,
        "sections": [
            "base_source",
            "strategy",
            "relations",
            "conditions",
            "entry_rule",
            "readiness",
            "local_semantic_composition",
        ],
    }
)


def _composition_payload(result: SemanticCompositionResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "reason_codes": list(result.reason_codes),
        "relation_results": [dict(item) for item in result.relation_results],
    }


def build_semantic_source_v2(candidate: dict[str, Any]) -> dict[str, Any]:
    base = build_semantic_source(candidate)
    strategy_key = str(candidate.get("strategy") or "").strip().lower()
    strategy = base.get("strategy") if isinstance(base.get("strategy"), dict) else {}
    conditions = (
        base.get("conditions") if isinstance(base.get("conditions"), dict) else {}
    )

    relation_resolution = resolve_strategy_semantic_relation_contract(
        strategy_key=strategy_key,
        strategy_version_id=(
            str(strategy.get("strategy_version_id"))
            if strategy.get("strategy_version_id") is not None
            else None
        ),
        strategy_definition_hash=(
            str(strategy.get("strategy_definition_hash"))
            if strategy.get("strategy_definition_hash") is not None
            else None
        ),
    )
    assertions = project_passed_condition_assertions(
        strategy_key=strategy_key,
        condition_items=list(conditions.get("items") or []),
    )

    relation_contract = relation_resolution.contract
    if (
        relation_resolution.status == SEMANTIC_STATUS_COMPLETE
        and isinstance(relation_contract, dict)
        and assertions.status == SEMANTIC_STATUS_COMPLETE
    ):
        composition = compose_semantics(
            relation_contract=relation_contract,
            assertions=assertions.items,
        )
    else:
        composition = incomplete_semantic_composition(
            *(
                code
                for code in (
                    relation_resolution.reason_code,
                    *assertions.reason_codes,
                )
                if code
            )
        )

    readiness_v1 = (
        base.get("readiness") if isinstance(base.get("readiness"), dict) else {}
    )
    body = {
        "source_contract_version": JEV_SEMANTIC_SOURCE_VERSION_V2,
        "source_contract_hash": JEV_SEMANTIC_SOURCE_CONTRACT_HASH_V2,
        "base_source": {
            "source_contract_version": base.get("source_contract_version"),
            "source_contract_hash": base.get("source_contract_hash"),
            "source_snapshot_hash": base.get("source_snapshot_hash"),
        },
        "strategy": dict(strategy),
        "relations": (
            dict(relation_contract)
            if isinstance(relation_contract, dict)
            else {
                "contract_version": STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION,
                "relation_contract_hash": None,
                "concepts": [],
                "relations": [],
            }
        ),
        "conditions": {
            "mapping_version": conditions.get("mapping_version"),
            "mapping_hash": conditions.get("mapping_hash"),
            "assertion_mapping_version": assertions.mapping_version,
            "assertion_mapping_hash": assertions.mapping_hash,
            "items": [dict(item) for item in assertions.items],
        },
        "entry_rule": dict(base.get("entry_rule") or {}),
        "readiness": {
            "q2_status": readiness_v1.get("q2_status"),
            "q2_reasons": list(readiness_v1.get("q2_reasons") or []),
            "local_semantic_status": composition.status,
            "local_semantic_reasons": list(composition.reason_codes),
            "residual_review_eligible": (
                composition.status == RESIDUAL_SEMANTIC_REVIEW
            ),
        },
        "local_semantic_composition": _composition_payload(composition),
    }
    return {
        **body,
        "source_snapshot_hash": _digest(body),
    }


def attach_semantic_source_v2(candidate: dict[str, Any]) -> dict[str, Any]:
    snapshot = dict(candidate)
    snapshot["semantic_source_v2"] = build_semantic_source_v2(snapshot)
    return snapshot


def verify_semantic_source_v2(source: Any) -> tuple[bool, str | None]:
    if not isinstance(source, dict):
        return False, "SEMANTIC_SOURCE_V2_MISSING"
    if (
        str(source.get("source_contract_version") or "")
        != JEV_SEMANTIC_SOURCE_VERSION_V2
    ):
        return False, "SEMANTIC_SOURCE_V2_VERSION_UNSUPPORTED"
    if (
        str(source.get("source_contract_hash") or "")
        != JEV_SEMANTIC_SOURCE_CONTRACT_HASH_V2
    ):
        return False, "SEMANTIC_SOURCE_V2_CONTRACT_HASH_MISMATCH"

    expected_snapshot_hash = str(source.get("source_snapshot_hash") or "")
    body = dict(source)
    body.pop("source_snapshot_hash", None)
    if not expected_snapshot_hash or _digest(body) != expected_snapshot_hash:
        return False, "SEMANTIC_SOURCE_V2_HASH_MISMATCH"

    base = source.get("base_source")
    if not isinstance(base, dict):
        return False, "SEMANTIC_SOURCE_V2_BASE_MISSING"
    if (
        base.get("source_contract_version") != JEV_SEMANTIC_SOURCE_VERSION
        or base.get("source_contract_hash") != JEV_SEMANTIC_SOURCE_CONTRACT_HASH
    ):
        return False, "SEMANTIC_SOURCE_V2_BASE_IDENTITY_MISMATCH"

    relations = source.get("relations")
    if not isinstance(relations, dict):
        return False, "SEMANTIC_SOURCE_V2_RELATIONS_MISSING"
    relation_hash = str(relations.get("relation_contract_hash") or "")
    if relation_hash:
        if (
            relations.get("contract_version")
            != STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION
            or semantic_relation_contract_hash(relations) != relation_hash
        ):
            return False, "SEMANTIC_SOURCE_V2_RELATION_HASH_MISMATCH"

    conditions = source.get("conditions")
    if not isinstance(conditions, dict):
        return False, "SEMANTIC_SOURCE_V2_CONDITIONS_MISSING"
    if (
        conditions.get("assertion_mapping_version")
        != CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION
        or conditions.get("assertion_mapping_hash")
        != CONDITION_SEMANTIC_ASSERTION_MAPPING_HASH
    ):
        return False, "SEMANTIC_SOURCE_V2_ASSERTION_MAPPING_MISMATCH"

    return True, None
