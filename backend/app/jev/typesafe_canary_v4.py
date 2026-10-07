from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from app.strategy.condition_assertions import (
    CONDITION_SEMANTIC_ASSERTION_MAPPING_HASH,
    CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION,
)
from app.strategy.semantic_composition import (
    LOCAL_AMBIGUOUS,
    LOCAL_CONFLICT,
    LOCAL_INCOMPLETE,
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
    compose_semantics,
)
from app.strategy.semantic_relations import (
    STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION,
    semantic_relation_contract_hash,
)
from app.strategy.semantic_source import (
    JEV_SEMANTIC_SOURCE_CONTRACT_HASH,
    JEV_SEMANTIC_SOURCE_VERSION,
)
from app.strategy.semantic_source_v2 import (
    JEV_SEMANTIC_SOURCE_CONTRACT_HASH_V2,
    JEV_SEMANTIC_SOURCE_VERSION_V2,
)
from .models import canonical_json, digest_json
from .protocol_canonical import (
    JEV_PROTOCOL_CANONICALIZATION_VERSION,
    JEV_PROTOCOL_HASH_ALGORITHM,
    canonical_protocol_bytes_v2,
    digest_protocol_json_v2,
    validate_protocol_identity_v2,
)
from .typesafe_canary_v4_fixtures import FIXTURE_SPECS
from .typesafe_models import (
    JEV_TYPESAFE_ADAPTER_VERSION,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
    JEV_TYPESAFE_PROJECTOR_VERSION_V4,
    JEV_TYPESAFE_PROVIDER_ID,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
    JEV_TYPESAFE_STATE_CONTRACT_VERSION_V4,
)
from .typesafe_policy_v4 import (
    JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V4,
    decide_typesafe_disposition_v4,
)
from .typesafe_questions_v4 import (
    JEV_TYPESAFE_QUESTION_IDS_V4,
    JEV_TYPESAFE_QUESTION_SET_HASH_V4,
    build_typesafe_questions_v4,
)
from .typesafe_state import TypeSafeStateProjectionError
from .typesafe_state_v4 import (
    JEV_TYPESAFE_PROJECTOR_HASH_V4,
    JEV_TYPESAFE_STATE_CONTRACT_HASH_V4,
    project_typesafe_state_v4,
    route_typesafe_state_v4,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]

CANARY_V4_ARTIFACT_VERSION = "JEV_TYPESAFE_CANARY_PROTOCOL_ARTIFACT_V4"
CANARY_V4_PROTOCOL_ID = "JEV-TYPESAFE-CANARY-V4"
CANARY_V4_PROTOCOL_PATH = (
    PROJECT_ROOT / "docs" / "contracts" / "JEV_TYPESAFE_CANARY_PROTOCOL_V4.json"
)
CANARY_V4_REPETITIONS = 5
CANARY_V4_MODEL_DISCOVERY_ATTEMPTS_MAX = 1
CANARY_V4_SYSTEM_ONE_ATTEMPTS = 40
CANARY_V4_TOTAL_API_ATTEMPTS_MAX = 41
CANARY_V4_RETRY_COUNT = 0
CANARY_V4_CONCURRENCY_CAP = 1
CANARY_V4_DEADLINE_SECONDS = 10.0
CANARY_V4_PER_CALL_RESERVATION_USD = 0.001
CANARY_V4_RESERVED_EXPOSURE_USD = 0.04
CANARY_V4_RESERVED_EXPOSURE_CEILING_USD = 0.05
CANARY_V4_PROJECT_ABSOLUTE_CEILING_USD = 0.25
CANARY_V4_PUBLIC_INPUT_PRICE_USD_PER_BILLION_TOKENS = 42.0
CANARY_V4_PUBLIC_PRICING_URL = "https://typesafe.ai/"
CANARY_V4_PUBLIC_PRICING_CHECKED_AT = "2026-10-07"
THRESHOLD_STRATEGY_CANDIDATES_V4 = (0.50, 0.70, 0.90)
MIN_CLASS_MARGIN_V4 = 0.10

PROVIDER_CALL = "PROVIDER_CALL"
LOCAL_ONLY = "LOCAL_ONLY"


class TypeSafeCanaryV4Error(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}:{detail}")
        self.code = code
        self.detail = detail


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _source_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    definitions = dict(spec["definitions"])
    concepts = [
        {
            "concept_id": concept_id,
            "definition_id": concept_id,
            "text": text,
        }
        for concept_id, text in sorted(definitions.items())
    ]
    relation = {
        "relation_id": "synthetic-relation-01",
        "kind": str(spec["relation"]["kind"]),
        "members": list(spec["relation"]["members"]),
        "guards": list(spec["relation"].get("guards") or []),
        "materiality": str(spec["relation"]["materiality"]),
    }
    relation_body = {
        "contract_version": STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION,
        "strategy_key": "synthetic-v4-canary",
        "strategy_version_id": "SYNTHETIC_V4_CANARY",
        "strategy_definition_hash": digest_json(
            {
                "fixture": spec["semantic_scenario_id"],
                "intent": spec["strategy_intent"],
            }
        ),
        "strategy_semantic_contract_version": "SYNTHETIC_V4_CANARY",
        "strategy_semantic_contract_hash": digest_json(
            {"scenario": spec["semantic_scenario_id"]}
        ),
        "concepts": concepts,
        "relations": [relation],
    }
    relation_contract = {
        **relation_body,
        "relation_contract_hash": semantic_relation_contract_hash(relation_body),
    }

    assertions = [
        {
            "condition_id": f"synthetic-condition-{index:02d}",
            "source_condition": f"synthetic-source-{index:02d}",
            "concept_refs": list(item["concept_refs"]),
            "stance": str(item["stance"]),
            "observed_meaning": str(item["text"]),
        }
        for index, item in enumerate(spec["meanings"], start=1)
    ]
    composition = compose_semantics(
        relation_contract=relation_contract,
        assertions=assertions,
    )
    if composition.status != spec["expected_local_status"]:
        raise TypeSafeCanaryV4Error(
            "CANARY_V4_LOCAL_STATUS_INVALID",
            str(spec["fixture_id"]),
        )

    body = {
        "source_contract_version": JEV_SEMANTIC_SOURCE_VERSION_V2,
        "source_contract_hash": JEV_SEMANTIC_SOURCE_CONTRACT_HASH_V2,
        "base_source": {
            "source_contract_version": JEV_SEMANTIC_SOURCE_VERSION,
            "source_contract_hash": JEV_SEMANTIC_SOURCE_CONTRACT_HASH,
            "source_snapshot_hash": digest_json(
                {"fixture_id": spec["fixture_id"], "base": "synthetic"}
            ),
        },
        "strategy": {
            "strategy_key": "synthetic-v4-canary",
            "strategy_version_id": "SYNTHETIC_V4_CANARY",
            "strategy_definition_hash": relation_body["strategy_definition_hash"],
            "intent_text": str(spec["strategy_intent"]),
            "required_definition_ids": sorted(definitions),
        },
        "relations": relation_contract,
        "conditions": {
            "mapping_version": "SYNTHETIC_CANARY_V4",
            "mapping_hash": digest_json(
                {
                    "fixture_id": spec["fixture_id"],
                    "mapping": "synthetic-canary-v4",
                }
            ),
            "assertion_mapping_version": CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION,
            "assertion_mapping_hash": CONDITION_SEMANTIC_ASSERTION_MAPPING_HASH,
            "items": assertions,
        },
        "entry_rule": {
            "synthetic_q2_variant": str(spec.get("q2_variant") or "NONE"),
        },
        "readiness": {
            "q2_status": "SYNTHETIC",
            "q2_reasons": [],
            "local_semantic_status": composition.status,
            "local_semantic_reasons": list(composition.reason_codes),
            "residual_review_eligible": (
                composition.status == RESIDUAL_SEMANTIC_REVIEW
            ),
        },
        "local_semantic_composition": {
            "status": composition.status,
            "reason_codes": list(composition.reason_codes),
            "relation_results": [
                dict(item) for item in composition.relation_results
            ],
        },
    }
    return {**body, "source_snapshot_hash": _digest(body)}


def _sample_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    source = _source_from_spec(spec)
    return {
        "action": "ENTRY_CANDIDATE",
        "horizon_intent": "SHORT",
        "capture_run_id": "synthetic-v4-canary",
        "sample_index": int(
            str(spec["fixture_id"]).split("-")[-1].lstrip("sv") or "0"
        ),
        "snapshot_hash": digest_json(
            {"fixture_id": spec["fixture_id"], "snapshot": "synthetic-v4-canary"}
        ),
        "snapshot": {
            "semantic_source_v2": source,
        },
    }


def _expected_disposition(gold: bool | None) -> tuple[str | None, list[str]]:
    if gold is True:
        return "REVIEW_REQUIRED", ["STRATEGY_RELATION_CONFLICT"]
    if gold is False:
        return "PASS_THROUGH", ["NO_ADDITIONAL_RELATION_CONFLICT"]
    return None, []


def _materialize_fixture(spec: dict[str, Any]) -> dict[str, Any]:
    sample = _sample_from_spec(spec)
    route = route_typesafe_state_v4(sample)
    expected_status = str(spec["expected_local_status"])
    if route.local_status != expected_status:
        raise TypeSafeCanaryV4Error(
            "CANARY_V4_ROUTE_STATUS_INVALID",
            str(spec["fixture_id"]),
        )

    projected_state = None
    projected_state_hash = None
    state_bytes = None
    route_name = LOCAL_ONLY
    if expected_status == RESIDUAL_SEMANTIC_REVIEW:
        route_name = PROVIDER_CALL
        projection = project_typesafe_state_v4(sample)
        projected_state = projection.state
        projected_state_hash = projection.state_hash
        state_bytes = projection.state_bytes
    else:
        if route.provider_eligible:
            raise TypeSafeCanaryV4Error(
                "CANARY_V4_LOCAL_ROUTE_BECAME_PROVIDER",
                str(spec["fixture_id"]),
            )
        try:
            project_typesafe_state_v4(sample)
        except TypeSafeStateProjectionError:
            pass
        else:
            raise TypeSafeCanaryV4Error(
                "CANARY_V4_LOCAL_ROUTE_PROJECTED",
                str(spec["fixture_id"]),
            )

    expected_disposition, expected_reason_codes = _expected_disposition(
        spec.get("expected_q1_gold")
    )
    return {
        "fixture_id": str(spec["fixture_id"]),
        "partition": str(spec["partition"]),
        "failure_mode": str(spec["failure_mode"]),
        "semantic_scenario_id": str(spec["semantic_scenario_id"]),
        "reachability": str(spec["reachability"]),
        "hard_expectation": bool(spec["hard_expectation"]),
        "route": route_name,
        "expected_local_status": expected_status,
        "expected_q1_gold": spec.get("expected_q1_gold"),
        "expected_disposition": expected_disposition,
        "expected_reason_codes": expected_reason_codes,
        "isolation_family_id": spec.get("isolation_family_id"),
        "q2_variant": str(spec.get("q2_variant") or "NONE"),
        "projected_state": projected_state,
        "projected_state_hash": projected_state_hash,
        "state_bytes": state_bytes,
    }


def synthetic_canary_v4_fixtures() -> list[dict[str, Any]]:
    return [_materialize_fixture(deepcopy(spec)) for spec in FIXTURE_SPECS]


def threshold_candidate_grid_v4() -> list[float]:
    return list(THRESHOLD_STRATEGY_CANDIDATES_V4)


def _partition(
    fixtures: list[dict[str, Any]],
    partition: str,
) -> list[dict[str, Any]]:
    return [item for item in fixtures if item["partition"] == partition]


def _provider_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in rows if item["route"] == PROVIDER_CALL]


def _unique_provider_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in _provider_rows(rows):
        state_hash = str(item["projected_state_hash"] or "")
        if not state_hash:
            raise TypeSafeCanaryV4Error("CANARY_V4_PROVIDER_HASH_MISSING")
        existing = unique.get(state_hash)
        if existing is not None:
            if (
                existing["expected_q1_gold"] != item["expected_q1_gold"]
                or existing["hard_expectation"] != item["hard_expectation"]
            ):
                raise TypeSafeCanaryV4Error(
                    "CANARY_V4_DUPLICATE_WIRE_GOLD_MISMATCH",
                    state_hash,
                )
        else:
            unique[state_hash] = item
    return [unique[key] for key in sorted(unique)]


def _max_request_bytes(fixtures: list[dict[str, Any]]) -> int:
    questions = build_typesafe_questions_v4()
    sizes = []
    for item in fixtures:
        if item["route"] != PROVIDER_CALL:
            continue
        request = {
            "state": item["projected_state"],
            "questions": questions,
            "model": "jev-latest",
        }
        sizes.append(len(canonical_protocol_bytes_v2(request)))
    return max(sizes) if sizes else 0


def build_canary_v4_protocol_artifact() -> dict[str, Any]:
    fixtures = synthetic_canary_v4_fixtures()
    selection_unique = _unique_provider_rows(_partition(fixtures, "selection"))
    validation_unique = _unique_provider_rows(_partition(fixtures, "validation"))
    planned_calls = (
        len(selection_unique) + len(validation_unique)
    ) * CANARY_V4_REPETITIONS

    spec = {
        "provider_id": JEV_TYPESAFE_PROVIDER_ID,
        "models_endpoint": "https://api.typesafe.ai/v1/models",
        "systemone_endpoint": "https://api.typesafe.ai/v1/systemone",
        "architecture": "LOCAL_RELATION_COMPOSITION_PLUS_RESIDUAL_Q1",
        "canonicalization_version": JEV_PROTOCOL_CANONICALIZATION_VERSION,
        "hash_algorithm": JEV_PROTOCOL_HASH_ALGORITHM,
        "model_request_rule": {
            "default_request_model": "jev-latest",
            "stable_alias_required": True,
            "preview_forbidden": True,
            "first_valid_concrete_response_binds_run": True,
            "subsequent_concrete_response_must_match": True,
        },
        "identities": {
            "semantic_source_version": JEV_SEMANTIC_SOURCE_VERSION_V2,
            "semantic_source_contract_hash": JEV_SEMANTIC_SOURCE_CONTRACT_HASH_V2,
            "relation_contract_version": STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION,
            "assertion_mapping_version": CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION,
            "assertion_mapping_hash": CONDITION_SEMANTIC_ASSERTION_MAPPING_HASH,
            "state_contract_version": JEV_TYPESAFE_STATE_CONTRACT_VERSION_V4,
            "state_contract_hash": JEV_TYPESAFE_STATE_CONTRACT_HASH_V4,
            "projector_version": JEV_TYPESAFE_PROJECTOR_VERSION_V4,
            "projector_hash": JEV_TYPESAFE_PROJECTOR_HASH_V4,
            "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
            "question_set_hash": JEV_TYPESAFE_QUESTION_SET_HASH_V4,
            "disposition_policy_version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
            "disposition_policy_hash": JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V4,
            "adapter_version": JEV_TYPESAFE_ADAPTER_VERSION,
        },
        "questions": build_typesafe_questions_v4(),
        "fixtures": fixtures,
        "partition_contract": {
            "selection_fixture_rows": len(_partition(fixtures, "selection")),
            "validation_fixture_rows": len(_partition(fixtures, "validation")),
            "selection_unique_provider_wires": len(selection_unique),
            "validation_unique_provider_wires": len(validation_unique),
            "provider_reachable_positive_residual_count": sum(
                item["route"] == PROVIDER_CALL
                and item["reachability"] == "PRODUCTION_REACHABLE"
                and item["expected_q1_gold"] is True
                for item in fixtures
            ),
        },
        "threshold_candidates": threshold_candidate_grid_v4(),
        "threshold_rule": {
            "comparison": "raw p >= T_strategy",
            "round_before_compare": False,
            "selection_partition": "selection",
            "validation_partition": "validation",
            "lock_before_validation": True,
            "validation_fallback_forbidden": True,
            "minimum_positive_margin": MIN_CLASS_MARGIN_V4,
            "minimum_negative_margin": MIN_CLASS_MARGIN_V4,
            "minimum_worst_class_margin": MIN_CLASS_MARGIN_V4,
            "tie_break": [
                "worst_class_margin_desc",
                "soft_review_required_count_asc",
                "threshold_strategy_asc",
            ],
        },
        "acceptance_gates": {
            "hard_false_reviews": 0,
            "hard_missed_reviews": 0,
            "hard_disposition_reason_errors": 0,
            "provider_errors": 0,
            "route_errors": 0,
            "isolation_errors": 0,
            "hard_disposition_crossing": 0,
            "positive_margin_min": MIN_CLASS_MARGIN_V4,
            "negative_margin_min": MIN_CLASS_MARGIN_V4,
            "worst_class_margin_min": MIN_CLASS_MARGIN_V4,
            "validation_rescue_allowed": False,
        },
        "forbidden_wire_keys": [
            "local_semantic_status",
            "stance",
            "gold",
            "expected_disposition",
            "ticker",
            "name",
            "rank",
            "price",
            "risk",
            "entry",
            "stop",
            "target",
            "rr",
            "holdings",
            "future_return",
            "q2",
        ],
        "repetitions_per_unique_q1_wire": CANARY_V4_REPETITIONS,
        "duplicate_wire_rule": (
            "SAME_PROJECTED_STATE_HASH_SHARED_RESPONSE_WITHIN_PARTITION_REPETITION"
        ),
        "model_discovery_attempts_max": CANARY_V4_MODEL_DISCOVERY_ATTEMPTS_MAX,
        "planned_systemone_calls": planned_calls,
        "systemone_attempts_hard_cap": CANARY_V4_SYSTEM_ONE_ATTEMPTS,
        "total_api_attempts_hard_cap": CANARY_V4_TOTAL_API_ATTEMPTS_MAX,
        "retry_count": CANARY_V4_RETRY_COUNT,
        "concurrency_cap": CANARY_V4_CONCURRENCY_CAP,
        "deadline_seconds": CANARY_V4_DEADLINE_SECONDS,
        "max_request_bytes": _max_request_bytes(fixtures),
        "budget": {
            "public_pricing_evidence": {
                "input_price_usd_per_billion_tokens": (
                    CANARY_V4_PUBLIC_INPUT_PRICE_USD_PER_BILLION_TOKENS
                ),
                "source_url": CANARY_V4_PUBLIC_PRICING_URL,
                "checked_at": CANARY_V4_PUBLIC_PRICING_CHECKED_AT,
                "account_terms_recheck_required_before_execute": True,
            },
            "per_call_reservation_usd": CANARY_V4_PER_CALL_RESERVATION_USD,
            "max_reserved_exposure_usd": CANARY_V4_RESERVED_EXPOSURE_USD,
            "reserved_exposure_ceiling_usd": (
                CANARY_V4_RESERVED_EXPOSURE_CEILING_USD
            ),
            "project_absolute_ceiling_usd": (
                CANARY_V4_PROJECT_ABSOLUTE_CEILING_USD
            ),
            "actual_cost_before_execution": None,
            "actual_cost_status": "UNKNOWN",
        },
        "real_stock_data_allowed": False,
        "actual_trial_activation_allowed": False,
        "production_feature_activation_allowed": False,
        "holdout_access_allowed": False,
        "execution_requires_separate_authorization": True,
        "selected_threshold": None,
        "final_threshold_frozen": False,
    }
    if planned_calls != CANARY_V4_SYSTEM_ONE_ATTEMPTS:
        raise TypeSafeCanaryV4Error("CANARY_V4_PLANNED_CALL_COUNT_INVALID")
    if (
        planned_calls * CANARY_V4_PER_CALL_RESERVATION_USD
        != CANARY_V4_RESERVED_EXPOSURE_USD
    ):
        raise TypeSafeCanaryV4Error("CANARY_V4_RESERVED_EXPOSURE_INVALID")

    protocol_hash = digest_protocol_json_v2(spec)
    body = {
        "artifact_version": CANARY_V4_ARTIFACT_VERSION,
        "protocol_id": CANARY_V4_PROTOCOL_ID,
        "status": "FROZEN_BEFORE_REAL_CALLS",
        "frozen_at": "2026-10-07",
        "canonicalization_version": JEV_PROTOCOL_CANONICALIZATION_VERSION,
        "hash_algorithm": JEV_PROTOCOL_HASH_ALGORITHM,
        "protocol_hash": protocol_hash,
        "spec": spec,
    }
    return {
        **body,
        "artifact_hash": digest_protocol_json_v2(body),
    }


def _collect_wire_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key).lower())
            keys.update(_collect_wire_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_collect_wire_keys(child))
    return keys


def validate_canary_v4_contract() -> dict[str, Any]:
    artifact = build_canary_v4_protocol_artifact()
    spec = artifact["spec"]
    fixtures = spec["fixtures"]

    if len(fixtures) != 18 or len({item["fixture_id"] for item in fixtures}) != 18:
        raise TypeSafeCanaryV4Error("CANARY_V4_FIXTURE_COUNT_INVALID")
    if threshold_candidate_grid_v4() != [0.5, 0.7, 0.9]:
        raise TypeSafeCanaryV4Error("CANARY_V4_THRESHOLD_GRID_INVALID")
    if len(JEV_TYPESAFE_QUESTION_IDS_V4) != 1:
        raise TypeSafeCanaryV4Error("CANARY_V4_QUESTION_COUNT_INVALID")

    required_modes = {
        "DIRECT_CONTRADICTION",
        "REQUIRED_CONDITION_COLLAPSE",
        "COMPOSITIONAL_CONFLICT",
        "ALLOWED_EXCEPTION",
        "WEAK_SEMANTIC_PHRASING",
        "NEAR_BOUNDARY_AMBIGUITY",
        "NEGATIVE_TRAP",
        "LOCAL_DETERMINISTIC_CONFLICT",
        "LOCAL_MISSING",
        "LOCAL_AMBIGUOUS",
        "Q1_Q2_ISOLATION",
    }
    if not required_modes <= {item["failure_mode"] for item in fixtures}:
        raise TypeSafeCanaryV4Error("CANARY_V4_FAILURE_MODE_COVERAGE_INVALID")

    scenarios_by_partition: dict[str, set[str]] = {
        "selection": set(),
        "validation": set(),
    }
    for item in fixtures:
        partition = str(item["partition"])
        scenario = str(item["semantic_scenario_id"])
        scenarios_by_partition.setdefault(partition, set()).add(scenario)
    if scenarios_by_partition["selection"] & scenarios_by_partition["validation"]:
        raise TypeSafeCanaryV4Error("CANARY_V4_SCENARIO_LEAKAGE")

    for partition in ("selection", "validation"):
        rows = _partition(fixtures, partition)
        unique = _unique_provider_rows(rows)
        if len(rows) != 9 or len(unique) != 4:
            raise TypeSafeCanaryV4Error(
                "CANARY_V4_PARTITION_WIRE_COUNT_INVALID",
                partition,
            )

    if spec["partition_contract"]["provider_reachable_positive_residual_count"] != 0:
        raise TypeSafeCanaryV4Error(
            "CANARY_V4_FAKE_PRODUCTION_POSITIVE_RESIDUAL"
        )

    forbidden = {str(key).lower() for key in spec["forbidden_wire_keys"]}
    for item in fixtures:
        if item["route"] != PROVIDER_CALL:
            if item["projected_state"] is not None:
                raise TypeSafeCanaryV4Error(
                    "CANARY_V4_LOCAL_STATE_PRESENT",
                    item["fixture_id"],
                )
            continue
        state = item["projected_state"]
        if set(state) != {
            "strategy_intent",
            "term_definitions",
            "authored_relations",
            "passed_condition_meanings",
        }:
            raise TypeSafeCanaryV4Error(
                "CANARY_V4_WIRE_SHAPE_INVALID",
                item["fixture_id"],
            )
        if _collect_wire_keys(state) & forbidden:
            raise TypeSafeCanaryV4Error(
                "CANARY_V4_FORBIDDEN_WIRE_KEY",
                item["fixture_id"],
            )
        if item["projected_state_hash"] != digest_json(state):
            raise TypeSafeCanaryV4Error(
                "CANARY_V4_STATE_HASH_INVALID",
                item["fixture_id"],
            )

    isolation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in fixtures:
        if item.get("isolation_family_id"):
            isolation[str(item["isolation_family_id"])].append(item)
    if set(isolation) != {"SEL-Q2", "VAL-Q2"}:
        raise TypeSafeCanaryV4Error("CANARY_V4_ISOLATION_FAMILY_INVALID")
    for family, rows in isolation.items():
        if len(rows) != 2:
            raise TypeSafeCanaryV4Error("CANARY_V4_ISOLATION_ROW_COUNT", family)
        if rows[0]["projected_state_hash"] != rows[1]["projected_state_hash"]:
            raise TypeSafeCanaryV4Error("CANARY_V4_ISOLATION_WIRE_MISMATCH", family)
        if rows[0]["q2_variant"] == rows[1]["q2_variant"]:
            raise TypeSafeCanaryV4Error("CANARY_V4_ISOLATION_Q2_NOT_DIFFERENT", family)

    if spec["planned_systemone_calls"] != CANARY_V4_SYSTEM_ONE_ATTEMPTS:
        raise TypeSafeCanaryV4Error("CANARY_V4_SYSTEM_ONE_CAP_INVALID")
    if (
        spec["total_api_attempts_hard_cap"]
        != CANARY_V4_SYSTEM_ONE_ATTEMPTS
        + CANARY_V4_MODEL_DISCOVERY_ATTEMPTS_MAX
    ):
        raise TypeSafeCanaryV4Error("CANARY_V4_TOTAL_CAP_INVALID")
    if spec["budget"]["max_reserved_exposure_usd"] > 0.05:
        raise TypeSafeCanaryV4Error("CANARY_V4_RESERVED_BUDGET_INVALID")
    if spec["budget"]["project_absolute_ceiling_usd"] > 0.25:
        raise TypeSafeCanaryV4Error("CANARY_V4_PROJECT_BUDGET_INVALID")

    if artifact["protocol_hash"] != digest_protocol_json_v2(spec):
        raise TypeSafeCanaryV4Error("CANARY_V4_PROTOCOL_HASH_INVALID")
    artifact_body = dict(artifact)
    artifact_hash = str(artifact_body.pop("artifact_hash") or "")
    if artifact_hash != digest_protocol_json_v2(artifact_body):
        raise TypeSafeCanaryV4Error("CANARY_V4_ARTIFACT_HASH_INVALID")
    return artifact


def write_canary_v4_protocol(
    path: Path = CANARY_V4_PROTOCOL_PATH,
) -> Path:
    artifact = validate_canary_v4_contract()
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(artifact, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != artifact:
            raise TypeSafeCanaryV4Error("CANARY_V4_PROTOCOL_DRIFT")
        return path
    path.write_text(rendered, encoding="utf-8")
    return path


def load_frozen_canary_v4_protocol(
    path: Path = CANARY_V4_PROTOCOL_PATH,
) -> dict[str, Any]:
    if not path.is_file():
        raise TypeSafeCanaryV4Error("CANARY_V4_PROTOCOL_MISSING")
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TypeSafeCanaryV4Error("CANARY_V4_PROTOCOL_INVALID") from exc

    runtime = validate_canary_v4_contract()
    try:
        validate_protocol_identity_v2(
            stored_artifact=stored,
            runtime_artifact=runtime,
        )
    except ValueError as exc:
        raise TypeSafeCanaryV4Error(
            "CANARY_V4_PROTOCOL_IDENTITY_INVALID",
            str(exc),
        ) from exc

    stored_body = dict(stored)
    stored_artifact_hash = str(stored_body.pop("artifact_hash", "") or "")
    if stored_artifact_hash != digest_protocol_json_v2(stored_body):
        raise TypeSafeCanaryV4Error("CANARY_V4_ARTIFACT_HASH_INVALID")
    if stored != runtime:
        raise TypeSafeCanaryV4Error("CANARY_V4_PROTOCOL_DRIFT")
    return stored


def _wire_expectations(
    artifact: dict[str, Any],
    partition: str,
) -> dict[str, dict[str, Any]]:
    rows = _unique_provider_rows(
        _partition(artifact["spec"]["fixtures"], partition)
    )
    return {
        str(item["projected_state_hash"]): item
        for item in rows
    }


def _metrics_for_threshold_v4(
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
    partition: str,
    threshold: float,
    *,
    provider_errors: int = 0,
    route_errors: int = 0,
    isolation_errors: int = 0,
) -> dict[str, Any]:
    expected = _wire_expectations(artifact, partition)
    expected_records = len(expected) * CANARY_V4_REPETITIONS
    by_wire: dict[str, list[tuple[str, tuple[str, ...], bool, float]]] = defaultdict(list)

    hard_checks = 0
    false_reviews = 0
    missed_reviews = 0
    disposition_reason_errors = 0
    soft_review_count = 0
    positive_probabilities: list[float] = []
    negative_probabilities: list[float] = []

    for record in records:
        state_hash = str(record.get("projected_state_hash") or "")
        fixture = expected.get(state_hash)
        if fixture is None:
            route_errors += 1
            continue
        probability = float(record["probability"])
        decision = decide_typesafe_disposition_v4(
            {"strategy_relation_conflict": probability},
            threshold_strategy=threshold,
        )
        gate = bool(decision.gate_results["strategy_relation_conflict"])
        by_wire[state_hash].append(
            (
                decision.disposition,
                decision.reason_codes,
                gate,
                probability,
            )
        )

        if not fixture["hard_expectation"]:
            if decision.disposition == "REVIEW_REQUIRED":
                soft_review_count += 1
            continue

        hard_checks += 1
        gold = bool(fixture["expected_q1_gold"])
        if gold:
            positive_probabilities.append(probability)
        else:
            negative_probabilities.append(probability)
        if not gold and decision.disposition == "REVIEW_REQUIRED":
            false_reviews += 1
        if gold and decision.disposition != "REVIEW_REQUIRED":
            missed_reviews += 1
        if (
            decision.disposition != fixture["expected_disposition"]
            or list(decision.reason_codes) != fixture["expected_reason_codes"]
        ):
            disposition_reason_errors += 1

    hard_disposition_crossing = 0
    for state_hash, items in by_wire.items():
        fixture = expected[state_hash]
        if fixture["hard_expectation"] and len({row[0] for row in items}) > 1:
            hard_disposition_crossing += 1

    positive_margin = (
        round(min(positive_probabilities) - threshold, 12)
        if positive_probabilities
        else None
    )
    negative_margin = (
        round(threshold - max(negative_probabilities), 12)
        if negative_probabilities
        else None
    )
    worst_margin = (
        round(min(positive_margin, negative_margin), 12)
        if positive_margin is not None and negative_margin is not None
        else None
    )
    epsilon = 1e-12
    eligible = (
        len(records) == expected_records
        and all(
            len(by_wire.get(state_hash, ())) == CANARY_V4_REPETITIONS
            for state_hash in expected
        )
        and false_reviews == 0
        and missed_reviews == 0
        and disposition_reason_errors == 0
        and provider_errors == 0
        and route_errors == 0
        and isolation_errors == 0
        and hard_disposition_crossing == 0
        and positive_margin is not None
        and negative_margin is not None
        and positive_margin + epsilon >= MIN_CLASS_MARGIN_V4
        and negative_margin + epsilon >= MIN_CLASS_MARGIN_V4
        and worst_margin is not None
        and worst_margin + epsilon >= MIN_CLASS_MARGIN_V4
    )
    return {
        "partition": partition,
        "threshold_strategy": float(threshold),
        "unique_provider_wires": len(expected),
        "expected_records": expected_records,
        "observed_records": len(records),
        "hard_checks": hard_checks,
        "hard_false_reviews": false_reviews,
        "hard_missed_reviews": missed_reviews,
        "hard_disposition_reason_errors": disposition_reason_errors,
        "provider_errors": int(provider_errors),
        "route_errors": int(route_errors),
        "isolation_errors": int(isolation_errors),
        "hard_disposition_crossing": hard_disposition_crossing,
        "soft_review_required_count": soft_review_count,
        "positive_margin": positive_margin,
        "negative_margin": negative_margin,
        "worst_class_margin": worst_margin,
        "eligible": eligible,
    }


def select_threshold_from_selection_v4(
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
    *,
    provider_errors: int = 0,
    route_errors: int = 0,
    isolation_errors: int = 0,
) -> dict[str, Any]:
    candidates = [
        _metrics_for_threshold_v4(
            records,
            artifact,
            "selection",
            threshold,
            provider_errors=provider_errors,
            route_errors=route_errors,
            isolation_errors=isolation_errors,
        )
        for threshold in artifact["spec"]["threshold_candidates"]
    ]
    eligible = [item for item in candidates if item["eligible"]]
    selected = None
    if eligible:
        selected = sorted(
            eligible,
            key=lambda item: (
                -float(item["worst_class_margin"]),
                int(item["soft_review_required_count"]),
                float(item["threshold_strategy"]),
            ),
        )[0]
    return {
        "candidates": candidates,
        "selected": selected,
    }


def evaluate_locked_threshold_v4(
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
    selected: dict[str, Any],
    *,
    provider_errors: int = 0,
    route_errors: int = 0,
    isolation_errors: int = 0,
) -> dict[str, Any]:
    if not selected or "threshold_strategy" not in selected:
        raise TypeSafeCanaryV4Error("CANARY_V4_SELECTED_THRESHOLD_MISSING")
    return _metrics_for_threshold_v4(
        records,
        artifact,
        "validation",
        float(selected["threshold_strategy"]),
        provider_errors=provider_errors,
        route_errors=route_errors,
        isolation_errors=isolation_errors,
    )
