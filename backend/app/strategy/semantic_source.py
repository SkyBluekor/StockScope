from __future__ import annotations

import hashlib
import json
from typing import Any

from app.strategy.condition_semantics import (
    CONDITION_SEMANTIC_MAPPING_HASH,
    CONDITION_SEMANTIC_MAPPING_VERSION,
    project_passed_condition_meanings,
)
from app.strategy.entry_semantics import (
    ENTRY_RULE_REPRESENTATION_HASH,
    ENTRY_RULE_REPRESENTATION_VERSION,
    build_entry_rule_representation,
    evaluate_entry_semantics,
    normalize_q2_status,
)
from app.strategy.semantic_contract import (
    SEMANTIC_STATUS_COMPLETE,
    SEMANTIC_STATUS_INVALID_BINDING,
    SEMANTIC_STATUS_MISSING,
    semantic_contract_hash,
    resolve_strategy_semantic_contract,
)


JEV_SEMANTIC_SOURCE_VERSION = "JEV_SEMANTIC_SOURCE_V1"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


JEV_SEMANTIC_SOURCE_CONTRACT_HASH = _digest(
    {
        "version": JEV_SEMANTIC_SOURCE_VERSION,
        "strategy_sections": [
            "strategy_version_id",
            "strategy_definition_hash",
            "semantic_contract_version",
            "semantic_contract_hash",
            "intent_text",
            "required_definition_ids",
            "definitions",
        ],
        "condition_sections": [
            "mapping_version",
            "mapping_hash",
            "items",
        ],
        "entry_sections": [
            "intended_rule_id",
            "intent_role",
            "represented_rule_id",
            "represented_role",
            "executable_entry_range",
            "representation_contract_version",
            "representation_contract_hash",
        ],
        "readiness_sections": ["q1_status", "q1_reasons", "q2_status", "q2_reasons"],
        "local_entry_result": ["status", "reason_code"],
    }
)


def _strategy_payload(contract: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {
            "strategy_version_id": None,
            "strategy_definition_hash": None,
            "semantic_contract_version": None,
            "semantic_contract_hash": None,
            "intent_text": None,
            "required_definition_ids": [],
            "definitions": [],
        }
    q1 = contract.get("q1") if isinstance(contract.get("q1"), dict) else {}
    return {
        "strategy_version_id": contract.get("strategy_version_id"),
        "strategy_definition_hash": contract.get("strategy_definition_hash"),
        "semantic_contract_version": contract.get("contract_version"),
        "semantic_contract_hash": contract.get("semantic_contract_hash"),
        "intent_text": q1.get("intent_text"),
        "required_definition_ids": list(q1.get("required_definition_ids") or []),
        "definitions": list(q1.get("definitions") or []),
    }


def _entry_payload(
    contract: dict[str, Any] | None,
    representation_value: dict[str, Any] | None,
) -> dict[str, Any]:
    value = dict(representation_value or {})
    rule_id = str(value.get("represented_rule_id") or "")
    intended = None
    if isinstance(contract, dict) and rule_id:
        matches = [
            item
            for item in list(contract.get("entry_rules") or [])
            if isinstance(item, dict) and str(item.get("rule_id") or "") == rule_id
        ]
        if len(matches) == 1:
            intended = matches[0]
    return {
        "intended_rule_id": (
            str(intended.get("rule_id")) if isinstance(intended, dict) else None
        ),
        "intent_role": (
            str(intended.get("intent_role")) if isinstance(intended, dict) else None
        ),
        "represented_rule_id": value.get("represented_rule_id"),
        "represented_role": value.get("represented_role"),
        "executable_entry_range": value.get("executable_entry_range"),
        "representation_contract_version": value.get(
            "representation_contract_version"
        ),
        "representation_contract_hash": value.get(
            "representation_contract_hash"
        ),
    }


def build_semantic_source(candidate: dict[str, Any]) -> dict[str, Any]:
    strategy_key = str(candidate.get("strategy") or "").strip().lower()
    strategy_resolution = resolve_strategy_semantic_contract(
        strategy_key=strategy_key,
        strategy_version_id=(
            str(candidate.get("strategy_version_id"))
            if candidate.get("strategy_version_id") is not None
            else None
        ),
        strategy_definition_hash=(
            str(candidate.get("strategy_definition_hash"))
            if candidate.get("strategy_definition_hash") is not None
            else None
        ),
    )
    contract = strategy_resolution.contract

    q1_reasons: list[str] = []
    if strategy_resolution.status != SEMANTIC_STATUS_COMPLETE:
        q1_status = strategy_resolution.status
        if strategy_resolution.reason_code:
            q1_reasons.append(strategy_resolution.reason_code)
        condition_projection = project_passed_condition_meanings(
            strategy_key=strategy_key,
            conditions_summary=None,
        )
    elif str(candidate.get("action") or "") != "ENTRY_CANDIDATE":
        q1_status = SEMANTIC_STATUS_MISSING
        q1_reasons.append("Q1_OUT_OF_SCOPE_ACTION")
        condition_projection = project_passed_condition_meanings(
            strategy_key=strategy_key,
            conditions_summary=candidate.get("conditions"),
        )
    else:
        condition_projection = project_passed_condition_meanings(
            strategy_key=strategy_key,
            conditions_summary=candidate.get("conditions"),
        )
        q1_status = condition_projection.status
        q1_reasons.extend(condition_projection.reason_codes)

    representation = build_entry_rule_representation(
        entry_risk_guide=(
            candidate.get("entry_risk_guide")
            if isinstance(candidate.get("entry_risk_guide"), dict)
            else None
        )
    )
    if strategy_resolution.status == SEMANTIC_STATUS_COMPLETE:
        local_entry_result = evaluate_entry_semantics(
            strategy_contract=contract,
            representation=representation,
        )
        q2_status, q2_reasons = normalize_q2_status(
            representation,
            local_entry_result,
        )
    else:
        local_entry_result = evaluate_entry_semantics(
            strategy_contract=None,
            representation=representation,
        )
        q2_status = strategy_resolution.status
        q2_reasons = tuple(
            code
            for code in (
                strategy_resolution.reason_code,
                representation.reason_code,
                local_entry_result.reason_code,
            )
            if code
        )

    body = {
        "source_contract_version": JEV_SEMANTIC_SOURCE_VERSION,
        "source_contract_hash": JEV_SEMANTIC_SOURCE_CONTRACT_HASH,
        "strategy": _strategy_payload(contract),
        "conditions": {
            "mapping_version": CONDITION_SEMANTIC_MAPPING_VERSION,
            "mapping_hash": CONDITION_SEMANTIC_MAPPING_HASH,
            "items": [dict(item) for item in condition_projection.items],
        },
        "entry_rule": _entry_payload(contract, representation.value),
        "readiness": {
            "q1_status": q1_status,
            "q1_reasons": sorted(set(q1_reasons)),
            "q2_status": q2_status,
            "q2_reasons": sorted(set(q2_reasons)),
        },
        "local_entry_semantic_result": {
            "status": local_entry_result.status,
            "reason_code": local_entry_result.reason_code,
        },
    }
    return {
        **body,
        "source_snapshot_hash": _digest(body),
    }


def attach_semantic_source(candidate: dict[str, Any]) -> dict[str, Any]:
    snapshot = dict(candidate)
    snapshot["semantic_source"] = build_semantic_source(snapshot)
    return snapshot


def verify_semantic_source(source: Any) -> tuple[bool, str | None]:
    if not isinstance(source, dict):
        return False, "SEMANTIC_SOURCE_MISSING"
    if str(source.get("source_contract_version") or "") != JEV_SEMANTIC_SOURCE_VERSION:
        return False, "SEMANTIC_SOURCE_VERSION_UNSUPPORTED"
    if str(source.get("source_contract_hash") or "") != JEV_SEMANTIC_SOURCE_CONTRACT_HASH:
        return False, "SEMANTIC_SOURCE_CONTRACT_HASH_MISMATCH"

    expected_snapshot_hash = str(source.get("source_snapshot_hash") or "")
    body = dict(source)
    body.pop("source_snapshot_hash", None)
    if not expected_snapshot_hash or _digest(body) != expected_snapshot_hash:
        return False, "SEMANTIC_SOURCE_HASH_MISMATCH"

    strategy = source.get("strategy")
    if not isinstance(strategy, dict):
        return False, "SEMANTIC_SOURCE_STRATEGY_MISSING"
    semantic_hash = str(strategy.get("semantic_contract_hash") or "")
    if semantic_hash:
        reconstructed = {
            "contract_version": strategy.get("semantic_contract_version"),
            "strategy_version_id": strategy.get("strategy_version_id"),
            "strategy_definition_hash": strategy.get("strategy_definition_hash"),
            "strategy_key": None,
            "q1": {
                "intent_text": strategy.get("intent_text"),
                "required_definition_ids": list(
                    strategy.get("required_definition_ids") or []
                ),
                "definitions": list(strategy.get("definitions") or []),
                "review_mode": "SEMANTIC_COMPOSITION",
            },
            "entry_rules": [],
        }
        # The compact snapshot deliberately omits strategy_key and entry_rules;
        # therefore only source-level integrity is verified here. Full strategy
        # contract integrity was verified before capture and its immutable hash is
        # carried forward for audit/cohort identity.
        del reconstructed

    conditions = source.get("conditions")
    if not isinstance(conditions, dict):
        return False, "SEMANTIC_SOURCE_CONDITIONS_MISSING"
    if (
        str(conditions.get("mapping_version") or "")
        != CONDITION_SEMANTIC_MAPPING_VERSION
        or str(conditions.get("mapping_hash") or "")
        != CONDITION_SEMANTIC_MAPPING_HASH
    ):
        return False, "SEMANTIC_SOURCE_CONDITION_MAPPING_MISMATCH"

    entry = source.get("entry_rule")
    if isinstance(entry, dict) and entry.get("represented_rule_id") is not None:
        if (
            str(entry.get("representation_contract_version") or "")
            != ENTRY_RULE_REPRESENTATION_VERSION
            or str(entry.get("representation_contract_hash") or "")
            != ENTRY_RULE_REPRESENTATION_HASH
        ):
            return False, "SEMANTIC_SOURCE_ENTRY_MAPPING_MISMATCH"

    return True, None
