from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.strategy.semantic_contract import (
    ROLE_CONFIRMATION_ONLY,
    ROLE_EXECUTABLE_ENTRY,
    SEMANTIC_STATUS_AMBIGUOUS,
    SEMANTIC_STATUS_COMPLETE,
    SEMANTIC_STATUS_INVALID_BINDING,
    SEMANTIC_STATUS_MISSING,
    SEMANTIC_STATUS_STALE_VERSION,
    SEMANTIC_STATUS_UNSUPPORTED,
)


ENTRY_RULE_REPRESENTATION_VERSION = "ENTRY_RULE_REPRESENTATION_V1"

_ALLOWED_SOURCE_ROLES = frozenset(
    {
        "STRATEGY_CONDITION_BAND",
        "STRATEGY_CONDITION_THRESHOLD",
        "STRATEGY_REFERENCE",
    }
)

_RULE_ID_BY_BASIS: dict[str, str] = {
    "현재가가 20일 이동평균선 위": "ma20-reference",
    "현재가가 20일선 위": "ma20-reference",
    "현재가가 20일선 위로 회복": "ma20-reference",
    "현재가가 20일선과 2.5% 이내": "ma20-reference",
    "주요 지지선과 2.5% 이내": "support-proximity",
    "주요 지지선과 4% 이내": "support-proximity",
    "지지선과 3% 이내": "support-proximity",
    "지지선과 5% 이내": "support-proximity",
    "20일 고점과 2% 이내": "high-reference",
    "20일 고점과 4% 이내": "high-reference",
    "20일 고점과 5% 이내": "high-reference",
    "저항까지 최소 4% 여유": "resistance-room",
    "저항까지 최소 5% 여유": "resistance-room",
    "저항과 4% 이내": "resistance-room",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


ENTRY_RULE_REPRESENTATION_HASH = _digest(
    {
        "version": ENTRY_RULE_REPRESENTATION_VERSION,
        "basis_to_rule_id": dict(sorted(_RULE_ID_BY_BASIS.items())),
        "source_semantic_roles": sorted(_ALLOWED_SOURCE_ROLES),
        "represented_role_rule": {
            "executable_entry_range_true": ROLE_EXECUTABLE_ENTRY,
            "executable_entry_range_false": ROLE_CONFIRMATION_ONLY,
        },
    }
)


@dataclass(frozen=True, slots=True)
class EntryRuleRepresentation:
    status: str
    reason_code: str | None
    value: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class EntrySemanticResult:
    status: str
    reason_code: str | None


def build_entry_rule_representation(
    *,
    entry_risk_guide: dict[str, Any] | None,
) -> EntryRuleRepresentation:
    if not isinstance(entry_risk_guide, dict):
        return EntryRuleRepresentation(
            SEMANTIC_STATUS_MISSING,
            "Q2_ENTRY_GUIDE_MISSING",
            None,
        )
    price_rule = entry_risk_guide.get("price_rule")
    if not isinstance(price_rule, dict):
        return EntryRuleRepresentation(
            SEMANTIC_STATUS_MISSING,
            "Q2_PRICE_RULE_MISSING",
            None,
        )

    basis = str(price_rule.get("basis") or "").strip()
    rule_id = _RULE_ID_BY_BASIS.get(basis)
    if not basis or rule_id is None:
        return EntryRuleRepresentation(
            SEMANTIC_STATUS_MISSING,
            "Q2_RULE_REFERENCE_MISSING",
            None,
        )

    source_role = str(price_rule.get("semantic_role") or "").strip()
    if source_role not in _ALLOWED_SOURCE_ROLES:
        return EntryRuleRepresentation(
            SEMANTIC_STATUS_UNSUPPORTED,
            "Q2_REPRESENTATION_ROLE_UNSUPPORTED",
            None,
        )

    executable_raw = price_rule.get("executable_entry_range")
    if not isinstance(executable_raw, bool):
        return EntryRuleRepresentation(
            SEMANTIC_STATUS_MISSING,
            "Q2_EXECUTABLE_FLAG_MISSING",
            None,
        )
    represented_role = (
        ROLE_EXECUTABLE_ENTRY if executable_raw else ROLE_CONFIRMATION_ONLY
    )

    return EntryRuleRepresentation(
        SEMANTIC_STATUS_COMPLETE,
        None,
        {
            "represented_rule_id": rule_id,
            "represented_role": represented_role,
            "executable_entry_range": executable_raw,
            "source_semantic_role": source_role,
            "representation_contract_version": ENTRY_RULE_REPRESENTATION_VERSION,
            "representation_contract_hash": ENTRY_RULE_REPRESENTATION_HASH,
        },
    )


def evaluate_entry_semantics(
    *,
    strategy_contract: dict[str, Any] | None,
    representation: EntryRuleRepresentation,
) -> EntrySemanticResult:
    if not isinstance(strategy_contract, dict):
        return EntrySemanticResult(
            SEMANTIC_STATUS_MISSING,
            "Q2_STRATEGY_SEMANTIC_CONTRACT_MISSING",
        )
    if representation.status != SEMANTIC_STATUS_COMPLETE:
        return EntrySemanticResult(
            representation.status,
            representation.reason_code,
        )
    value = representation.value or {}
    rule_id = str(value.get("represented_rule_id") or "")
    rules = [
        item
        for item in list(strategy_contract.get("entry_rules") or [])
        if isinstance(item, dict) and str(item.get("rule_id") or "") == rule_id
    ]
    if not rules:
        return EntrySemanticResult(
            SEMANTIC_STATUS_MISSING,
            "Q2_INTENDED_RULE_MISSING",
        )
    if len(rules) > 1:
        return EntrySemanticResult(
            SEMANTIC_STATUS_AMBIGUOUS,
            "Q2_RULE_REFERENCE_AMBIGUOUS",
        )

    intended_role = str(rules[0].get("intent_role") or "")
    represented_role = str(value.get("represented_role") or "")
    if intended_role not in {ROLE_CONFIRMATION_ONLY, ROLE_EXECUTABLE_ENTRY}:
        return EntrySemanticResult(
            SEMANTIC_STATUS_UNSUPPORTED,
            "Q2_INTENT_ROLE_UNSUPPORTED",
        )
    if represented_role not in {ROLE_CONFIRMATION_ONLY, ROLE_EXECUTABLE_ENTRY}:
        return EntrySemanticResult(
            SEMANTIC_STATUS_UNSUPPORTED,
            "Q2_REPRESENTED_ROLE_UNSUPPORTED",
        )

    if intended_role == represented_role:
        return EntrySemanticResult("MATCH", None)
    if (
        intended_role == ROLE_CONFIRMATION_ONLY
        and represented_role == ROLE_EXECUTABLE_ENTRY
    ):
        return EntrySemanticResult(
            "CONFLICT",
            "CONFLICT_CONFIRMATION_AS_EXECUTION",
        )
    if (
        intended_role == ROLE_EXECUTABLE_ENTRY
        and represented_role == ROLE_CONFIRMATION_ONLY
    ):
        return EntrySemanticResult(
            "CONFLICT",
            "CONFLICT_EXECUTION_AS_CONFIRMATION",
        )
    return EntrySemanticResult(
        SEMANTIC_STATUS_INVALID_BINDING,
        "Q2_ROLE_BINDING_INVALID",
    )


def normalize_q2_status(
    representation: EntryRuleRepresentation,
    local_result: EntrySemanticResult,
) -> tuple[str, tuple[str, ...]]:
    if local_result.status in {"MATCH", "CONFLICT"}:
        return SEMANTIC_STATUS_COMPLETE, ()
    status = local_result.status
    if status not in {
        SEMANTIC_STATUS_MISSING,
        SEMANTIC_STATUS_AMBIGUOUS,
        SEMANTIC_STATUS_UNSUPPORTED,
        SEMANTIC_STATUS_STALE_VERSION,
        SEMANTIC_STATUS_INVALID_BINDING,
    }:
        status = SEMANTIC_STATUS_INVALID_BINDING
    reasons = tuple(
        code
        for code in (representation.reason_code, local_result.reason_code)
        if code
    )
    return status, reasons
