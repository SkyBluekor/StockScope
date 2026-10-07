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
    semantic_contract_body = {        "contract_version": STRATEGY_SEMANTIC_CONTRACT_VERSION,
        "strategy_version_id": "SYNTHETIC-V3",
        "strategy_definition_hash": strategy_definition_hash,
        "strategy_key": "synthetic_canary_v3",
        "q1": {
            "intent_text": spec["intent_text"],
            "required_definition_ids": required_ids,
            "definitions": definitions,
            "review_mode": "SEMANTIC_COMPOSITION",
        },
        "entry_rules": rules,
    }
    semantic_contract_hash = digest_json(semantic_contract_body)
    condition_items = [
        {
            "condition_id": f"synthetic-{index:02d}",
            "source_condition": "synthetic",
            "status": "PASS",
            "observed_meaning": meaning,
        }
        for index, meaning in enumerate(list(spec["meanings"]), start=1)
    ]

    body = {
        "source_contract_version": spec["source_version"],
        "source_contract_hash": JEV_SEMANTIC_SOURCE_CONTRACT_HASH,
        "strategy": {
            "strategy_version_id": "SYNTHETIC-V3",
            "strategy_definition_hash": strategy_definition_hash,
            "semantic_contract_version": STRATEGY_SEMANTIC_CONTRACT_VERSION,
            "semantic_contract_hash": semantic_contract_hash,
            "intent_text": spec["intent_text"],
            "required_definition_ids": required_ids,
            "definitions": definitions,
        },
        "conditions": {
            "mapping_version": CONDITION_SEMANTIC_MAPPING_VERSION,
            "mapping_hash": CONDITION_SEMANTIC_MAPPING_HASH,
            "items": condition_items,
        },
        "entry_rule": _entry_payload(rules, representation),
        "readiness": {
            "q1_status": spec["q1_status"],
            "q1_reasons": [spec["q1_reason"]] if spec.get("q1_reason") else [],
            "q2_status": q2_status,
            "q2_reasons": q2_reasons,
        },
        "local_entry_semantic_result": {
            "status": q2_data["local_status"],
            "reason_code": q2_data["local_reason"],
        },
    }
    source = {**body, "source_snapshot_hash": digest_json(body)}
    sample = _synthetic_sample(source, str(spec["partition"]))

    provider_callable = (
        isinstance(spec.get("expected_q1_gold"), bool)
        or spec["family"] == "SOFT"
    )
    projected_state = None
    projected_state_hash = None
    state_bytes = 0
    preflight_error = None
    if provider_callable:
        projection = project_typesafe_state_v3(sample)
        projected_state = projection.state
        projected_state_hash = projection.state_hash
        state_bytes = projection.state_bytes
    else:
        try:
            project_typesafe_state_v3(sample)
        except TypeSafeStateProjectionError as exc:
            preflight_error = exc.code
        else:
            raise TypeSafeCanaryV3Error(
                "CANARY_V3_LOCAL_ONLY_UNEXPECTEDLY_CALLABLE",
                str(spec["fixture_id"]),
            )

    q1_gold = spec.get("expected_q1_gold")
    if q1_gold is True:
        expected_disposition = "REVIEW_REQUIRED"
        expected_reasons = ["STRATEGY_CONTEXT_CONFLICT"]
    elif q1_gold is False:
        expected_disposition = "PASS_THROUGH"
        expected_reasons = ["NO_ADDITIONAL_CONTEXT_CONFLICT"]
    else:
        expected_disposition = None
        expected_reasons = []

    return {
        "fixture_id": spec["fixture_id"],
        "partition": spec["partition"],
        "family": spec["family"],
        "hard_expectation": bool(spec["hard_expectation"]),
        "route": "PROVIDER_CALL" if provider_callable else "LOCAL_ONLY",
        "synthetic_source": source,
        "projected_state": projected_state,
        "projected_state_hash": projected_state_hash,
        "state_bytes": state_bytes,
        "expected_preflight_error": preflight_error,
        "expected_q1_gold": q1_gold,
        "expected_q2_status": q2_status,
        "expected_q2_reason": q2_data["local_reason"],
        "expected_local_entry_result": {
            "status": q2_data["local_status"],
            "reason_code": q2_data["local_reason"],
        },
        "expected_jev_status": "VALID" if provider_callable else "SKIPPED",
        "expected_disposition": expected_disposition,
        "expected_reason_codes": expected_reasons,
        "isolation_family_id": spec.get("isolation_family_id"),
        "gold_rationale": spec["gold_rationale"],
    }


def synthetic_canary_v3_fixtures() -> list[dict[str, Any]]:
    return [_materialize_fixture(spec) for spec in _FIXTURE_SPECS]


def threshold_candidate_grid() -> list[float]:
    return list(THRESHOLD_STRATEGY_CANDIDATES)


def build_canary_v3_protocol_artifact() -> dict[str, Any]:
    spec = {
        "provider_id": JEV_TYPESAFE_PROVIDER_ID,
        "models_endpoint": "https://api.typesafe.ai/v1/models",
        "systemone_endpoint": "https://api.typesafe.ai/v1/systemone",
        "architecture": "ARCH_C_PLUS_D1_Q1_ONLY",
        "model_request_rule": {
            "default_request_model": "jev-latest",
            "stable_alias_required": True,
            "preview_forbidden": True,
            "version_looking_name_is_not_immutable_without_verified_metadata": True,
            "first_valid_concrete_response_binds_run": True,
            "subsequent_concrete_response_must_match": True,
        },
        "identities": {
            "semantic_source_version": JEV_SEMANTIC_SOURCE_VERSION,
            "semantic_source_contract_hash": JEV_SEMANTIC_SOURCE_CONTRACT_HASH,
            "strategy_semantic_contract_version": STRATEGY_SEMANTIC_CONTRACT_VERSION,
            "condition_semantic_mapping_version": CONDITION_SEMANTIC_MAPPING_VERSION,
            "condition_semantic_mapping_hash": CONDITION_SEMANTIC_MAPPING_HASH,
            "entry_rule_representation_version": ENTRY_RULE_REPRESENTATION_VERSION,
            "entry_rule_representation_hash": ENTRY_RULE_REPRESENTATION_HASH,
            "state_contract_version": JEV_TYPESAFE_STATE_CONTRACT_VERSION_V3,
            "state_contract_hash": JEV_TYPESAFE_STATE_CONTRACT_HASH_V3,
            "projector_version": JEV_TYPESAFE_PROJECTOR_VERSION_V3,
            "projector_hash": JEV_TYPESAFE_PROJECTOR_HASH_V3,
            "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3,
            "question_set_hash": JEV_TYPESAFE_QUESTION_SET_HASH_V3,
            "disposition_policy_version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V3,
            "disposition_policy_hash": JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V3,
            "adapter_version": JEV_TYPESAFE_ADAPTER_VERSION,
        },
        "questions": build_typesafe_questions_v3(),
        "fixtures": synthetic_canary_v3_fixtures(),
        "partition_contract": {
            "selection_contexts": 20,
            "validation_contexts": 20,
            "provider_callable_per_partition": 12,
            "local_only_per_partition": 8,
            "callable_hard_per_partition": 10,
            "callable_soft_per_partition": 2,
            "hard_negative_per_partition": 6,
            "hard_positive_per_partition": 4,
        },
        "threshold_candidates": threshold_candidate_grid(),
        "threshold_rule": {
            "comparison": "p >= T_strategy",
            "round_before_compare": False,
            "selection_partition": "selection",
            "validation_partition": "validation",
            "lock_before_validation": True,
            "validation_fallback_forbidden": True,
            "tie_break": [
                "soft_review_required_count_asc",
                "threshold_strategy_desc",
            ],
        },
        "acceptance_gates": {
            "hard_proposition_mismatches": 0,
            "hard_false_reviews": 0,
            "hard_missed_reviews": 0,
            "hard_disposition_reason_errors": 0,
            "callable_route_errors": 0,
            "local_route_errors": 0,
            "isolation_errors": 0,
            "provider_errors": 0,
            "hard_gate_crossing": 0,
            "disposition_crossing_all_callable": 0,
            "reason_crossing_all_callable": 0,
            "review_required_max_per_partition": 18,
            "abstain_max_per_partition": 0,
        },
        "local_entry_truth_table": [
            {"intended": "CONFIRMATION_ONLY", "represented": "CONFIRMATION_ONLY", "result": "MATCH"},
            {"intended": "CONFIRMATION_ONLY", "represented": "EXECUTABLE_ENTRY", "result": "CONFLICT_CONFIRMATION_AS_EXECUTION"},
            {"intended": "EXECUTABLE_ENTRY", "represented": "EXECUTABLE_ENTRY", "result": "MATCH"},
            {"intended": "EXECUTABLE_ENTRY", "represented": "CONFIRMATION_ONLY", "result": "CONFLICT_EXECUTION_AS_CONFIRMATION"},
            {"reference": "MISSING", "result": "MISSING"},
            {"reference": "AMBIGUOUS", "result": "AMBIGUOUS"},
        ],
        "forbidden_wire_tokens": [
            "ticker", "name", "rank", "capture_id", "current_price",
            "entry_rule", "intent_role", "represented_role",
            "local_entry_semantic_result", "risk", "stop", "target", "rr",
            "fixture_id", "partition", "gold", "expected", "rationale",
            "future_outcome", "news", "holdings", "account", "user_id",
        ],
        "repetitions": CANARY_V3_REPETITIONS,
        "model_discovery_attempts_max": MAX_MODEL_DISCOVERY_ATTEMPTS,
        "systemone_attempts_max": MAX_SYSTEM_ONE_ATTEMPTS,
        "total_api_attempts_max": MAX_TOTAL_API_ATTEMPTS,
        "retry_count": 0,
        "concurrency_cap": 1,
        "deadline_seconds": CANARY_V3_DEADLINE_SECONDS,
        "api_budget_usd": CANARY_V3_API_BUDGET_USD,
        "per_call_reservation_required": True,
        "reservation_must_be_verified_before_execute": True,
        "real_stock_data_allowed": False,
        "actual_trial_activation_allowed": False,
        "execution_requires_separate_authorization": True,
        "selected_threshold": None,
        "final_threshold_frozen": False,
    }
    return {
        "artifact_version": CANARY_V3_ARTIFACT_VERSION,
        "protocol_id": CANARY_V3_PROTOCOL_ID,
        "status": "FROZEN_BEFORE_REAL_CALLS",
        "frozen_at": "2026-10-07",
        "protocol_hash": digest_json(spec),
        "spec": spec,
    }


def _partition(fixtures: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [item for item in fixtures if item["partition"] == name]


def _callable(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in fixtures if item["route"] == "PROVIDER_CALL"]


def _local_only(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in fixtures if item["route"] == "LOCAL_ONLY"]


def validate_canary_v3_contract() -> dict[str, Any]:
