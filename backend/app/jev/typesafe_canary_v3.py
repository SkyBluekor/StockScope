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


def validate_canary_v3_contract() -> dict[str, Any]:    artifact = build_canary_v3_protocol_artifact()
    fixtures = artifact["spec"]["fixtures"]
    if len(fixtures) != 40 or len({item["fixture_id"] for item in fixtures}) != 40:
        raise TypeSafeCanaryV3Error("CANARY_V3_FIXTURE_COUNT_INVALID")
    if threshold_candidate_grid() != [0.5, 0.7, 0.9]:
        raise TypeSafeCanaryV3Error("CANARY_V3_THRESHOLD_GRID_INVALID")
    if len(JEV_TYPESAFE_QUESTION_IDS_V3) != 1:
        raise TypeSafeCanaryV3Error("CANARY_V3_QUESTION_COUNT_INVALID")
    if 24 * CANARY_V3_REPETITIONS != MAX_SYSTEM_ONE_ATTEMPTS:
        raise TypeSafeCanaryV3Error("CANARY_V3_CALL_CAP_INVALID")

    forbidden = tuple(
        str(item).lower() for item in artifact["spec"]["forbidden_wire_tokens"]
    )
    for partition_name in ("selection", "validation"):
        rows = _partition(fixtures, partition_name)
        callable_rows = _callable(rows)
        local_rows = _local_only(rows)
        hard_rows = [item for item in callable_rows if item["hard_expectation"]]
        soft_rows = [item for item in callable_rows if not item["hard_expectation"]]
        if len(rows) != 20 or len(callable_rows) != 12 or len(local_rows) != 8:
            raise TypeSafeCanaryV3Error("CANARY_V3_PARTITION_COUNT_INVALID")
        if len(hard_rows) != 10 or len(soft_rows) != 2:
            raise TypeSafeCanaryV3Error("CANARY_V3_HARD_SOFT_COUNT_INVALID")
        if sum(item["expected_q1_gold"] is False for item in hard_rows) != 6:
            raise TypeSafeCanaryV3Error("CANARY_V3_NEGATIVE_COUNT_INVALID")
        if sum(item["expected_q1_gold"] is True for item in hard_rows) != 4:
            raise TypeSafeCanaryV3Error("CANARY_V3_POSITIVE_COUNT_INVALID")

    for item in fixtures:
        if item["route"] == "PROVIDER_CALL":
            state = item["projected_state"]
            if not isinstance(state, dict):
                raise TypeSafeCanaryV3Error("CANARY_V3_PROJECTED_STATE_MISSING")
            if item["projected_state_hash"] != digest_json(state):
                raise TypeSafeCanaryV3Error("CANARY_V3_PROJECTED_STATE_HASH_INVALID")
            if int(item["state_bytes"]) != len(canonical_json(state).encode("utf-8")):
                raise TypeSafeCanaryV3Error("CANARY_V3_PROJECTED_STATE_BYTES_INVALID")
            encoded = canonical_json(state).lower()
            if any(token in encoded for token in forbidden):
                raise TypeSafeCanaryV3Error(
                    "CANARY_V3_FORBIDDEN_WIRE_FIELD",
                    str(item["fixture_id"]),
                )
            if set(state) != {
                "strategy_intent", "term_definitions", "passed_condition_meanings"
            }:
                raise TypeSafeCanaryV3Error("CANARY_V3_WIRE_SHAPE_INVALID")
        else:
            if item["projected_state"] is not None:
                raise TypeSafeCanaryV3Error("CANARY_V3_LOCAL_ROUTE_STATE_PRESENT")
            if not item["expected_preflight_error"]:
                raise TypeSafeCanaryV3Error("CANARY_V3_LOCAL_ROUTE_REASON_MISSING")

    isolation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in fixtures:
        family = item.get("isolation_family_id")
        if family:
            isolation[str(family)].append(item)
    if set(isolation) != {"S-A", "S-B", "V-A", "V-B"}:
        raise TypeSafeCanaryV3Error("CANARY_V3_ISOLATION_FAMILY_INVALID")
    for family, rows in isolation.items():
        if len(rows) != 2:
            raise TypeSafeCanaryV3Error("CANARY_V3_ISOLATION_PAIR_INVALID", family)
        if rows[0]["projected_state_hash"] != rows[1]["projected_state_hash"]:
            raise TypeSafeCanaryV3Error("CANARY_V3_ISOLATION_HASH_MISMATCH", family)
        if canonical_json(rows[0]["projected_state"]) != canonical_json(rows[1]["projected_state"]):
            raise TypeSafeCanaryV3Error("CANARY_V3_ISOLATION_WIRE_MISMATCH", family)
        if rows[0]["expected_local_entry_result"] == rows[1]["expected_local_entry_result"]:
            raise TypeSafeCanaryV3Error("CANARY_V3_ISOLATION_LOCAL_RESULT_NOT_DIFFERENT", family)

    if artifact["protocol_hash"] != digest_json(artifact["spec"]):
        raise TypeSafeCanaryV3Error("CANARY_V3_PROTOCOL_HASH_INVALID")
    return artifact


def write_canary_v3_protocol(path: Path = CANARY_V3_PROTOCOL_PATH) -> Path:
    artifact = validate_canary_v3_contract()
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(artifact, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TypeSafeCanaryV3Error("CANARY_V3_PROTOCOL_INVALID") from exc
        if existing != artifact:
            raise TypeSafeCanaryV3Error("CANARY_V3_PROTOCOL_DRIFT")
        return path
    path.write_text(rendered, encoding="utf-8")
    return path


def load_frozen_canary_v3_protocol(
    path: Path = CANARY_V3_PROTOCOL_PATH,
) -> dict[str, Any]:
    expected = validate_canary_v3_contract()
    if not path.is_file():
        raise TypeSafeCanaryV3Error("CANARY_V3_PROTOCOL_NOT_FROZEN")
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TypeSafeCanaryV3Error("CANARY_V3_PROTOCOL_INVALID") from exc
    if stored != expected:
        raise TypeSafeCanaryV3Error("CANARY_V3_PROTOCOL_DRIFT")
    return stored


def classify_model_channel(model: dict[str, Any]) -> str:
    name = str(model.get("name") or "").strip().lower()
    if "preview" in name:
        return PREVIEW_ALIAS
    if name == "jev-latest" or name.endswith("-latest"):
        return STABLE_ALIAS
    if (
        re.fullmatch(r"jev-\d+(?:\.\d+)+", name)
        and model.get("immutable_verified") is True
    ):
        return IMMUTABLE_VERSION_VERIFIED
    return UNKNOWN_CHANNEL


def select_canary_v3_model(
    models: list[dict[str, str]],
    *,
    override: str | None = None,
) -> dict[str, Any]:
    by_name = {item["name"]: item for item in models}
    requested = override or "jev-latest"
    if requested not in by_name:
        raise TypeSafeCanaryV3Error("CANARY_V3_STABLE_MODEL_UNAVAILABLE")
    selected = by_name[requested]
    channel = classify_model_channel(selected)
    if channel == PREVIEW_ALIAS:
        raise TypeSafeCanaryV3Error("CANARY_V3_PREVIEW_MODEL_FORBIDDEN")
    if channel not in {STABLE_ALIAS, IMMUTABLE_VERSION_VERIFIED}:
        raise TypeSafeCanaryV3Error("CANARY_V3_MODEL_CHANNEL_UNVERIFIED")
    return {**selected, "request_channel_class": channel}


def _fixture_map(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["fixture_id"]: item
        for item in artifact["spec"]["fixtures"]
    }


def _partition_order(
    fixtures: list[dict[str, Any]],
    repetition: int,
) -> list[dict[str, Any]]:
    ordered = sorted(fixtures, key=lambda item: item["fixture_id"])
    if repetition == 1:
        return ordered
    if repetition == 2:
        return list(reversed(ordered))
    if repetition == 3:
        return ordered[1:] + ordered[:1]
    raise ValueError("CANARY_V3_REPETITION_INVALID")


def _metrics_for_threshold(
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
    threshold: float,
) -> dict[str, Any]:
    fixtures = _fixture_map(artifact)
    hard_checks = 0
    hard_mismatches = 0
    false_reviews = 0
    missed_reviews = 0
    disposition_reason_errors = 0
    review_count = 0
    soft_review_count = 0
    by_fixture: dict[str, list[tuple[str, tuple[str, ...], bool]]] = defaultdict(list)

    for record in records:
        fixture = fixtures[record["fixture_id"]]
        decision = decide_typesafe_disposition_v3(
            {"strategy_context_conflict": record["probability"]},
            threshold_strategy=threshold,
        )
        gate = bool(decision.gate_results["strategy_context_conflict"])
        by_fixture[record["fixture_id"]].append(
            (decision.disposition, decision.reason_codes, gate)
        )
        if decision.disposition == "REVIEW_REQUIRED":
            review_count += 1
        if not fixture["hard_expectation"]:
            if decision.disposition == "REVIEW_REQUIRED":
                soft_review_count += 1
            continue

        hard_checks += 1
        gold = bool(fixture["expected_q1_gold"])
        if gate != gold:
            hard_mismatches += 1
        if not gold and decision.disposition == "REVIEW_REQUIRED":
            false_reviews += 1
        if gold and decision.disposition != "REVIEW_REQUIRED":
            missed_reviews += 1
        if (
            decision.disposition != fixture["expected_disposition"]
            or list(decision.reason_codes) != fixture["expected_reason_codes"]
        ):
            disposition_reason_errors += 1

    disposition_crossing = 0
    reason_crossing = 0
    hard_gate_crossing = 0
    for fixture_id, items in by_fixture.items():
        if len({row[0] for row in items}) > 1:
            disposition_crossing += 1
        if len({row[1] for row in items}) > 1:
            reason_crossing += 1
        if fixtures[fixture_id]["hard_expectation"] and len({row[2] for row in items}) > 1:
            hard_gate_crossing += 1

    eligible = (
        len(records) == 36
        and hard_checks == 30
        and hard_mismatches == 0
        and false_reviews == 0
        and missed_reviews == 0
        and disposition_reason_errors == 0
        and disposition_crossing == 0
        and reason_crossing == 0
        and hard_gate_crossing == 0
        and review_count <= 18
    )
    return {
        "threshold_strategy": float(threshold),
        "hard_proposition_checks": hard_checks,
        "hard_proposition_mismatches": hard_mismatches,
        "hard_false_reviews": false_reviews,
        "hard_missed_reviews": missed_reviews,
        "hard_disposition_reason_errors": disposition_reason_errors,
        "review_required_count": review_count,
        "soft_review_required_count": soft_review_count,
        "abstain_count": 0,
        "disposition_crossing": disposition_crossing,
        "reason_crossing": reason_crossing,
        "hard_gate_crossing": hard_gate_crossing,
        "eligible": eligible,
    }


def select_threshold_from_selection(
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
) -> dict[str, Any]:
    candidates = [
        _metrics_for_threshold(records, artifact, threshold)
        for threshold in artifact["spec"]["threshold_candidates"]
    ]
    eligible = [item for item in candidates if item["eligible"]]
    selected = None
    if eligible:
        selected = sorted(
            eligible,
            key=lambda item: (                item["soft_review_required_count"],
                -item["threshold_strategy"],
            ),
        )[0]
    return {"candidates": candidates, "selected": selected}


def evaluate_locked_threshold(
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
    selected: dict[str, Any],
) -> dict[str, Any]:
    return _metrics_for_threshold(
        records,
        artifact,
        float(selected["threshold_strategy"]),
    )


def _blocked_report(artifact: dict[str, Any], code: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "report_version": CANARY_V3_REPORT_VERSION,
        "status": "BLOCKED",
        "canary_protocol_id": CANARY_V3_PROTOCOL_ID,
        "canary_protocol_hash": artifact["protocol_hash"],
        "started_at": now,
        "completed_at": now,
        "api_attempts": {
            "model_discovery": 0,
            "systemone": 0,
            "total": 0,
            "hard_cap": MAX_TOTAL_API_ATTEMPTS,
        },
        "systemone_counts": {
            "planned": MAX_SYSTEM_ONE_ATTEMPTS,
            "attempted": 0,
            "completed": 0,
            "valid": 0,
            "failed": 0,
        },
        "errors": [code],
        "real_stock_data_sent": False,
        "actual_trial_activation": False,
        "final_threshold_frozen": False,
        "trial_freeze_readiness": "BLOCKED_PREFLIGHT",
    }


async def run_real_canary_v3(
    *,
    per_call_reservation_usd: float | None,
    model_override: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    deadline_seconds: float = CANARY_V3_DEADLINE_SECONDS,
) -> dict[str, Any]:
    artifact = load_frozen_canary_v3_protocol()
    if (
        per_call_reservation_usd is None
        or isinstance(per_call_reservation_usd, bool)
        or not math.isfinite(float(per_call_reservation_usd))
        or float(per_call_reservation_usd) <= 0.0
    ):
        return _blocked_report(artifact, "BLOCKED_COST_RESERVATION_UNVERIFIED")
    reservation = float(per_call_reservation_usd)
    if reservation * MAX_SYSTEM_ONE_ATTEMPTS > CANARY_V3_API_BUDGET_USD:
        return _blocked_report(artifact, "BLOCKED_COST_RESERVATION_EXCEEDS_BUDGET")

    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    attempts = {"model_discovery": 1, "systemone": 0}
    counts = {
        "planned": MAX_SYSTEM_ONE_ATTEMPTS,
        "attempted": 0,
        "completed": 0,
        "valid": 0,
        "failed": 0,
    }
    reserved_exposure = 0.0
    try:
        models = await discover_typesafe_models(
            deadline_seconds=deadline_seconds,
            transport=transport,
        )
        selected_model = select_canary_v3_model(models, override=model_override)
    except (TypeSafeJevProviderError, TypeSafeCanaryV3Error) as exc:
        code = exc.code if hasattr(exc, "code") else "CANARY_V3_MODEL_DISCOVERY_FAILED"
        completed = datetime.now(timezone.utc).isoformat()
        return {
            **_blocked_report(artifact, code),
            "status": "FAIL",
            "started_at": started,
            "completed_at": completed,
            "api_attempts": {
                "model_discovery": 1,
                "systemone": 0,
                "total": 1,
                "hard_cap": MAX_TOTAL_API_ATTEMPTS,
            },
        }

    provider = TypeSafeSystemOneProvider(
        model_id=selected_model["name"],
        transport=transport,
    )
    observed_model: str | None = None
    records_by_partition: dict[str, list[dict[str, Any]]] = {
        "selection": [],
        "validation": [],
    }

    async def run_partition(partition: str) -> bool:
        nonlocal observed_model, reserved_exposure
        fixtures = _callable(_partition(artifact["spec"]["fixtures"], partition))
        for repetition in range(1, CANARY_V3_REPETITIONS + 1):
            for fixture in _partition_order(fixtures, repetition):
                if counts["attempted"] >= MAX_SYSTEM_ONE_ATTEMPTS:
                    errors.append("CANARY_V3_SYSTEMONE_ATTEMPT_CAP_REACHED")
                    return False
                if reserved_exposure + reservation > CANARY_V3_API_BUDGET_USD:
                    errors.append("CANARY_V3_BUDGET_RESERVATION_BLOCKED")
                    return False

                reserved_exposure += reservation
                counts["attempted"] += 1
                attempts["systemone"] += 1
                request = {
                    "state": fixture["projected_state"],
                    "questions": build_typesafe_questions_v3(),
                    "model": selected_model["name"],
                }
                before = time.perf_counter()
                try:
                    result = await provider.review(
                        request,
                        deadline_seconds=deadline_seconds,
                    )
                    counts["completed"] += 1
                    normalized = validate_system_one_response(
                        result.raw_response,
                        expected_model_returned=observed_model,
                        expected_question_ids=JEV_TYPESAFE_QUESTION_IDS_V3,
                    )
                except TypeSafeJevProviderError as exc:
                    counts["failed"] += 1
                    if exc.code == "TYPESAFE_MODEL_IDENTITY_CHANGED":
                        errors.append("CANARY_V3_MODEL_IDENTITY_CHANGED")
                    else:
                        errors.append(exc.code)
                    return False
                latency_ms = int(round((time.perf_counter() - before) * 1000))
                if observed_model is None:
                    observed_model = str(normalized["model"])
                counts["valid"] += 1
                records_by_partition[partition].append(
                    {
                        "fixture_id": fixture["fixture_id"],
                        "partition": partition,
                        "projected_state_hash": fixture["projected_state_hash"],
                        "repetition": repetition,
                        "model_requested": selected_model["name"],
                        "model_returned": normalized["model"],
                        "probability": normalized["probabilities"]["strategy_context_conflict"],
                        "usage": normalized["usage"],
                        "latency_ms": latency_ms,
                    }
                )
        return True

    selection_complete = await run_partition("selection")
    selection_analysis = select_threshold_from_selection(
        records_by_partition["selection"],
        artifact,
    )
    selected_threshold = selection_analysis["selected"]
    validation_analysis = None

    if not selection_complete or len(records_by_partition["selection"]) != 36:
        errors.append("CANARY_V3_SELECTION_INCOMPLETE")
    elif selected_threshold is None:
        errors.append("CANARY_V3_NO_ELIGIBLE_THRESHOLD")
    else:
        validation_complete = await run_partition("validation")
        if not validation_complete or len(records_by_partition["validation"]) != 36:
            errors.append("CANARY_V3_VALIDATION_INCOMPLETE")
        else:
            validation_analysis = evaluate_locked_threshold(
                records_by_partition["validation"],
                artifact,
                selected_threshold,
            )
            if not validation_analysis["eligible"]:
                errors.append("CANARY_V3_VALIDATION_FAILED")

    all_records = records_by_partition["selection"] + records_by_partition["validation"]
    input_tokens = sum(int(item["usage"]["input_tokens"]) for item in all_records)
    output_tokens = sum(int(item["usage"]["output_tokens"]) for item in all_records)
    status = "PASS" if not errors else "FAIL"
    completed = datetime.now(timezone.utc).isoformat()
    binding = {
        "artifact_version": CANARY_V3_MODEL_BINDING_VERSION,
        "status": "OBSERVED_CANARY_BINDING" if all_records else "DISCOVERY_ONLY",
        "checked_at": completed,
        "provider_id": JEV_TYPESAFE_PROVIDER_ID,
        "available_models": [
            {**item, "request_channel_class": classify_model_channel(item)}
            for item in models
        ],
        "selected_request_model": selected_model["name"],
        "request_channel_class": selected_model["request_channel_class"],
        "selected_release_date": selected_model.get("release_date"),
        "observed_response_model": observed_model,
        "discovery_hash": digest_json(models),
        "canary_protocol_hash": artifact["protocol_hash"],
    }
    return {
        "report_version": CANARY_V3_REPORT_VERSION,
        "status": status,
        "canary_protocol_id": CANARY_V3_PROTOCOL_ID,
        "canary_protocol_hash": artifact["protocol_hash"],
        "started_at": started,
        "completed_at": completed,
        "model_binding": binding,
        "api_attempts": {
            "model_discovery": attempts["model_discovery"],
            "systemone": attempts["systemone"],
            "total": attempts["model_discovery"] + attempts["systemone"],
            "hard_cap": MAX_TOTAL_API_ATTEMPTS,
        },
        "systemone_counts": counts,
        "budget": {
            "hard_budget_usd": CANARY_V3_API_BUDGET_USD,
            "per_call_reservation_usd": reservation,
            "reserved_exposure_usd": reserved_exposure,
            "actual_provider_cost_usd": None,
            "actual_provider_cost_status": "UNKNOWN",
        },
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "selection_analysis": selection_analysis,
        "selected_threshold": (
            {"threshold_strategy": selected_threshold["threshold_strategy"]}
            if selected_threshold is not None
            else None
        ),
        "validation_analysis": validation_analysis,
        "records": records_by_partition,
        "errors": sorted(set(errors)),
        "real_stock_data_sent": False,
        "actual_trial_activation": False,
        "final_threshold_frozen": False,
        "trial_freeze_readiness": (
            "READY_FOR_TRIAL_POLICY_BINDING"
            if status == "PASS"
            else "BLOCKED_CANARY_FAILED"
        ),
        "account_policy_binding": "NOT_VERIFIED_BY_CANARY",
    }


def _safe_report_path() -> Path:
    return (
        CANARY_V3_VALIDATION_DIR
        / f"JEV_TYPESAFE_CANARY_V3_{date.today().isoformat()}.json"
    )


def write_canary_v3_outputs(
    report: dict[str, Any],
    *,
    report_path: Path | None = None,
    binding_path: Path = CANARY_V3_MODEL_BINDING_PATH,
) -> tuple[Path, Path]:
    path = Path(report_path or _safe_report_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    binding_path.write_text(
        json.dumps(report.get("model_binding") or {}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return path, binding_path
