from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.core.config import PROJECT_ROOT
from app.strategy.condition_semantics import (
    CONDITION_SEMANTIC_MAPPING_HASH,
    CONDITION_SEMANTIC_MAPPING_VERSION,
)
from app.strategy.entry_semantics import (
    ENTRY_RULE_REPRESENTATION_HASH,
    ENTRY_RULE_REPRESENTATION_VERSION,
    EntryRuleRepresentation,
    evaluate_entry_semantics,
    normalize_q2_status,
)
from app.strategy.semantic_contract import (
    ROLE_CONFIRMATION_ONLY,
    ROLE_EXECUTABLE_ENTRY,
    STRATEGY_SEMANTIC_CONTRACT_VERSION,
)
from app.strategy.semantic_source import (
    JEV_SEMANTIC_SOURCE_CONTRACT_HASH,
    JEV_SEMANTIC_SOURCE_VERSION,
)

from .models import canonical_json, digest_json
from .typesafe_models import (
    JEV_TYPESAFE_ADAPTER_VERSION,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V3,
    JEV_TYPESAFE_PROJECTOR_VERSION_V3,
    JEV_TYPESAFE_PROVIDER_ID,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3,
    JEV_TYPESAFE_STATE_CONTRACT_VERSION_V3,
)
from .typesafe_policy_v3 import (
    JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V3,
    decide_typesafe_disposition_v3,
)
from .typesafe_provider import (
    TypeSafeJevProviderError,
    TypeSafeSystemOneProvider,
    discover_typesafe_models,
    validate_system_one_response,
)
from .typesafe_questions_v3 import (
    JEV_TYPESAFE_QUESTION_IDS_V3,
    JEV_TYPESAFE_QUESTION_SET_HASH_V3,
    build_typesafe_questions_v3,
)
from .typesafe_state import TypeSafeStateProjectionError
from .typesafe_state_v3 import (
    JEV_TYPESAFE_PROJECTOR_HASH_V3,
    JEV_TYPESAFE_STATE_CONTRACT_HASH_V3,
    project_typesafe_state_v3,
)


CANARY_V3_ARTIFACT_VERSION = "JEV_TYPESAFE_CANARY_PROTOCOL_ARTIFACT_V3"
CANARY_V3_PROTOCOL_ID = "JEV-TYPESAFE-CANARY-V3"
CANARY_V3_REPORT_VERSION = "JEV_TYPESAFE_CANARY_REPORT_V3"
CANARY_V3_MODEL_BINDING_VERSION = "JEV_TYPESAFE_MODEL_BINDING_ARTIFACT_V3"

MAX_MODEL_DISCOVERY_ATTEMPTS = 1
MAX_SYSTEM_ONE_ATTEMPTS = 72
MAX_TOTAL_API_ATTEMPTS = 73
CANARY_V3_REPETITIONS = 3
CANARY_V3_API_BUDGET_USD = 0.25
CANARY_V3_DEADLINE_SECONDS = 10.0
THRESHOLD_STRATEGY_CANDIDATES = (0.50, 0.70, 0.90)

CANARY_V3_PROTOCOL_PATH = (
    PROJECT_ROOT / "docs" / "contracts" / "JEV_TYPESAFE_CANARY_PROTOCOL_V3.json"
)
CANARY_V3_MODEL_BINDING_PATH = (
    PROJECT_ROOT / "docs" / "contracts" / "JEV_TYPESAFE_MODEL_BINDING_V3.json"
)
CANARY_V3_VALIDATION_DIR = PROJECT_ROOT / "docs" / "validation"

STABLE_ALIAS = "STABLE_ALIAS"
PREVIEW_ALIAS = "PREVIEW_ALIAS"
IMMUTABLE_VERSION_VERIFIED = "IMMUTABLE_VERSION_VERIFIED"
UNKNOWN_CHANNEL = "UNKNOWN"

from .typesafe_canary_v3_fixtures import FIXTURE_SPECS as _FIXTURE_SPECS


class TypeSafeCanaryV3Error(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _q2_materialization(case: str) -> tuple[
    dict[str, Any],
    EntryRuleRepresentation,
    str,
    list[str],
]:
    if case == "MATCH":
        rules = [{"rule_id": "synthetic-rule", "intent_role": ROLE_CONFIRMATION_ONLY}]
        representation = EntryRuleRepresentation(
            "COMPLETE",
            None,
            {
                "represented_rule_id": "synthetic-rule",
                "represented_role": ROLE_CONFIRMATION_ONLY,
                "executable_entry_range": False,
                "representation_contract_version": ENTRY_RULE_REPRESENTATION_VERSION,
                "representation_contract_hash": ENTRY_RULE_REPRESENTATION_HASH,
            },
        )
    elif case == "CONFLICT_C2E":
        rules = [{"rule_id": "synthetic-rule", "intent_role": ROLE_CONFIRMATION_ONLY}]
        representation = EntryRuleRepresentation(
            "COMPLETE",
            None,
            {
                "represented_rule_id": "synthetic-rule",
                "represented_role": ROLE_EXECUTABLE_ENTRY,
                "executable_entry_range": True,
                "representation_contract_version": ENTRY_RULE_REPRESENTATION_VERSION,
                "representation_contract_hash": ENTRY_RULE_REPRESENTATION_HASH,
            },
        )
    elif case == "CONFLICT_E2C":
        rules = [{"rule_id": "synthetic-rule", "intent_role": ROLE_EXECUTABLE_ENTRY}]
        representation = EntryRuleRepresentation(
            "COMPLETE",
            None,
            {
                "represented_rule_id": "synthetic-rule",
                "represented_role": ROLE_CONFIRMATION_ONLY,
                "executable_entry_range": False,
                "representation_contract_version": ENTRY_RULE_REPRESENTATION_VERSION,
                "representation_contract_hash": ENTRY_RULE_REPRESENTATION_HASH,
            },
        )
    elif case == "MISSING":
        rules = [{"rule_id": "synthetic-rule", "intent_role": ROLE_CONFIRMATION_ONLY}]
        representation = EntryRuleRepresentation(
            "MISSING",
            "Q2_RULE_REFERENCE_MISSING",
            None,
        )
    elif case == "AMBIGUOUS":
        rules = [
            {"rule_id": "synthetic-rule", "intent_role": ROLE_CONFIRMATION_ONLY},
            {"rule_id": "synthetic-rule", "intent_role": ROLE_EXECUTABLE_ENTRY},
        ]
        representation = EntryRuleRepresentation(
            "COMPLETE",
            None,
            {
                "represented_rule_id": "synthetic-rule",
                "represented_role": ROLE_CONFIRMATION_ONLY,
                "executable_entry_range": False,
                "representation_contract_version": ENTRY_RULE_REPRESENTATION_VERSION,
                "representation_contract_hash": ENTRY_RULE_REPRESENTATION_HASH,
            },
        )
    else:
        raise TypeSafeCanaryV3Error("CANARY_V3_Q2_CASE_INVALID", case)

    contract = {"entry_rules": rules}
    local_result = evaluate_entry_semantics(
        strategy_contract=contract,
        representation=representation,
    )
    q2_status, q2_reasons = normalize_q2_status(representation, local_result)
    return (
        {
            "rules": rules,
            "representation": representation.value,
            "local_status": local_result.status,
            "local_reason": local_result.reason_code,
        },
        representation,
        q2_status,
        list(q2_reasons),
    )


def _entry_payload(
    rules: list[dict[str, str]],
    representation: EntryRuleRepresentation,
) -> dict[str, Any]:
    value = dict(representation.value or {})
    rule_id = str(value.get("represented_rule_id") or "")
    intended = [
        item for item in rules
        if str(item.get("rule_id") or "") == rule_id
    ]
    exact = intended[0] if len(intended) == 1 else None
    return {
        "intended_rule_id": exact.get("rule_id") if exact else None,
        "intent_role": exact.get("intent_role") if exact else None,
        "represented_rule_id": value.get("represented_rule_id"),
        "represented_role": value.get("represented_role"),
        "executable_entry_range": value.get("executable_entry_range"),
        "representation_contract_version": value.get("representation_contract_version"),
        "representation_contract_hash": value.get("representation_contract_hash"),
    }


def _synthetic_sample(source: dict[str, Any], partition: str) -> dict[str, Any]:
    return {
        "capture_run_id": "SYNTHETIC-CANARY-V3",
        "sample_index": 0,
        "action": "ENTRY_CANDIDATE",
        "candidate_state": "READY",
        "strategy": "synthetic_canary_v3",
        "signal_date": "2026-10-07",
        "horizon_intent": "SHORT" if partition == "selection" else "MEDIUM",
        "horizon_policy_version": "SYNTHETIC-V3-HORIZON",
        "snapshot": {
            "action": "ENTRY_CANDIDATE",
            "candidate_state": "READY",
            "semantic_source": source,
        },
    }


def _materialize_fixture(spec: dict[str, Any]) -> dict[str, Any]:
    q2_data, representation, q2_status, q2_reasons = _q2_materialization(
        str(spec["q2_case"])
    )
    rules = q2_data["rules"]
    definitions = [
        {"id": key, "text": value}
        for key, value in sorted(dict(spec["definitions"]).items())
    ]
    required_ids = [item["id"] for item in definitions]
    strategy_definition_hash = digest_json(
        {
            "fixture_family": spec["family"],
            "q1_intent": spec["intent_text"],
        }
    )
    semantic_contract_body = {
