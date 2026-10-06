from __future__ import annotations

import itertools
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

from .models import canonical_json, digest_json
from .typesafe_models import (
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
    JEV_TYPESAFE_PROVIDER_ID,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
)
from .typesafe_policy_v2 import (
    JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V2,
    decide_typesafe_disposition_v2,
)
from .typesafe_provider import (
    TypeSafeJevProviderError,
    TypeSafeSystemOneProvider,
    discover_typesafe_models,
    validate_system_one_response,
)
from .typesafe_questions_v2 import (
    ENTRY_CONTEXT_CONFLICT,
    JEV_TYPESAFE_QUESTION_IDS_V2,
    JEV_TYPESAFE_QUESTION_SET_HASH_V2,
    OVERALL_SEMANTIC_REVIEW_INSUFFICIENT,
    STRATEGY_CONTEXT_CONFLICT,
    build_typesafe_questions_v2,
)
from .typesafe_state import project_typesafe_state


CANARY_V2_ARTIFACT_VERSION = "JEV_TYPESAFE_CANARY_PROTOCOL_ARTIFACT_V2"
CANARY_V2_PROTOCOL_ID = "JEV-TYPESAFE-CANARY-V2"
CANARY_V2_REPORT_VERSION = "JEV_TYPESAFE_CANARY_REPORT_V2"
CANARY_V2_MODEL_BINDING_VERSION = "JEV_TYPESAFE_MODEL_BINDING_ARTIFACT_V2"

MAX_MODEL_DISCOVERY_ATTEMPTS = 1
MAX_SYSTEM_ONE_ATTEMPTS = 72
MAX_TOTAL_API_ATTEMPTS = 73
CANARY_V2_REPETITIONS = 3
CANARY_V2_API_BUDGET_USD = 0.25

THRESHOLD_STRATEGY_CANDIDATES = (0.50, 0.65, 0.80)
THRESHOLD_ENTRY_CANDIDATES = (0.50, 0.65, 0.80)
THRESHOLD_EVIDENCE_CANDIDATES = (0.60, 0.75, 0.90)

CANARY_V2_PROTOCOL_PATH = (
    PROJECT_ROOT / "docs" / "contracts" / "JEV_TYPESAFE_CANARY_PROTOCOL_V2.json"
)
CANARY_V2_MODEL_BINDING_PATH = (
    PROJECT_ROOT / "docs" / "contracts" / "JEV_TYPESAFE_MODEL_BINDING_V2.json"
)
CANARY_V2_VALIDATION_DIR = PROJECT_ROOT / "docs" / "validation"

STABLE_ALIAS = "STABLE_ALIAS"
PREVIEW_ALIAS = "PREVIEW_ALIAS"
IMMUTABLE_VERSION_VERIFIED = "IMMUTABLE_VERSION_VERIFIED"
UNKNOWN_CHANNEL = "UNKNOWN"


class TypeSafeCanaryV2Error(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _condition(
    metric_key: str,
    semantic_label: str,
    current_value: Any,
    required_value: Any,
) -> dict[str, Any]:
    return {
        "metric_key": metric_key,
        "status": "PASS",
        "current_value": current_value,
        "required_value": required_value,
        "semantic_label": semantic_label,
    }


SEMANTIC_LABELS = {
    "ma20_slope": "20-day moving-average slope condition",
    "ma20_vs_ma60": "20-day versus 60-day moving-average relation",
    "ma60_vs_ma120": "60-day versus 120-day moving-average relation",
    "relative_strength_sector": "relative strength versus the sector",
    "relative_strength_market": "relative strength versus the broad market",
}

CONDITION_SETS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "R": (
        ("ma20_slope", "rising", "rising"),
        ("ma20_vs_ma60", "above", "above"),
    ),
    "F": (
        ("ma20_slope", "falling", "falling"),
        ("ma20_vs_ma60", "below", "below"),
    ),
    "SP": (
        ("relative_strength_sector", "positive", "positive"),
        ("ma20_slope", "rising", "rising"),
    ),
    "SN": (
        ("relative_strength_sector", "negative", "negative"),
        ("ma20_slope", "falling", "falling"),
    ),
    "L": (
        ("ma60_vs_ma120", "above", "above"),
        ("relative_strength_market", "positive", "positive"),
    ),
    "D": (
        ("ma60_vs_ma120", "below", "below"),
        ("relative_strength_market", "negative", "negative"),
    ),
    "M": (
        ("ma20_slope", "slightly rising", "nondecreasing"),
        ("ma20_vs_ma60", "above", "above"),
    ),
}


def _conditions(key: str) -> list[dict[str, Any]]:
    return [
        _condition(metric, SEMANTIC_LABELS[metric], current, required)
        for metric, current, required in CONDITION_SETS[key]
    ]


def _state(
    description: str,
    condition_key: str,
    entry_kind: str,
    horizon: str,
) -> dict[str, Any]:
    if entry_kind == "X":
        semantic_role = "EXECUTABLE_ENTRY_RANGE"
        executable = True
        classification = "ALIGNED"
    elif entry_kind == "C":
        semantic_role = "STRATEGY_CONDITION_THRESHOLD"
        executable = False
        classification = "SEPARATED"
    else:
        raise ValueError("CANARY_V2_ENTRY_KIND_INVALID")
    return {
        "context": {
            "market": "SYNTHETIC",
            "as_of_date": "2026-10-06",
            "horizon_intent": horizon,
        },
        "strategy_context": {
            "strategy_key": "SYNTHETIC_CANARY_V2",
            "strategy_description": description,
        },
        "condition_context": _conditions(condition_key),
        "entry_context": {
            "price_rule": {
                "kind": "RANGE",
                "status": "MET",
                "semantic_role": semantic_role,
                "executable_entry_range": executable,
            },
            "action": {"status": "ENTRY_CANDIDATE"},
            "price_consistency": {
                "classification": classification,
                "semantic_overlap": False,
            },
        },
        "baseline": {
            "action": "ENTRY_CANDIDATE",
            "candidate_state": "READY",
        },
    }


def _fixture(
    fixture_id: str,
    partition: str,
    purpose: str,
    description: str,
    condition_key: str,
    entry_kind: str,
    horizon: str,
    *,
    q1: bool | None,
    q2: bool | None,
    q3: bool | None,
    disposition: str | None,
    reason_codes: tuple[str, ...] = (),
    uncertainty_reason: str | None = None,
    metric_group: str,
    hard: bool = True,
    cross_question: bool = False,
    gold_rationale: str,
) -> dict[str, Any]:
    state = _state(description, condition_key, entry_kind, horizon)
    return {
        "fixture_id": fixture_id,
        "partition": partition,
        "purpose": purpose,
        "state": state,
        "state_hash": digest_json(state),
        "expected_propositions": {
            STRATEGY_CONTEXT_CONFLICT: q1,
            ENTRY_CONTEXT_CONFLICT: q2,
            OVERALL_SEMANTIC_REVIEW_INSUFFICIENT: q3,
        },
        "expected_disposition": disposition,
        "expected_reason_codes": list(reason_codes),
        "expected_uncertainty_reason": uncertainty_reason,
        "metric_group": metric_group,
        "hard_expectation": hard,
        "cross_question": cross_question,
        "gold_rationale": gold_rationale,
    }


def synthetic_canary_v2_fixtures() -> list[dict[str, Any]]:
    s = "selection"
    v = "validation"
    fixtures = [
        _fixture(
            "v2-s01", s, "clear normal",
            "This strategy accepts a rising 20-day average above the 60-day average. "
            "The single rule in entry_context is an executable entry range.",
            "R", "X", "SHORT", q1=False, q2=False, q3=False,
            disposition="PASS_THROUGH",
            reason_codes=("NO_ADDITIONAL_CONTEXT_CONFLICT",),
            metric_group="NEGATIVE",
            gold_rationale="Condition direction and executable-rule meaning agree.",
        ),
        _fixture(
            "v2-s02", s, "future uncertainty negative control",
            "Falling averages with the 20-day below the 60-day are intentional here. "
            "The entry_context rule is executable. Later price performance is outside "
            "this review.",
            "F", "X", "SHORT", q1=False, q2=False, q3=False,
            disposition="PASS_THROUGH",
            reason_codes=("NO_ADDITIONAL_CONTEXT_CONFLICT",),
            metric_group="NEGATIVE",
            gold_rationale="Current semantics are complete; future outcome is irrelevant.",
        ),
        _fixture(
            "v2-s03", s, "false-positive trap: confirmation band",
            "Rising averages above the slower average fit this setup. The only rule "
            "in entry_context is a confirmation band, never an executable range. "
            "Candidate status does not change that role.",
            "R", "C", "SHORT", q1=False, q2=False, q3=False,
            disposition="PASS_THROUGH",
            reason_codes=("NO_ADDITIONAL_CONTEXT_CONFLICT",),
            metric_group="NEGATIVE",
            gold_rationale="Non-executable confirmation meaning agrees with state.",
        ),
        _fixture(
            "v2-s04", s, "false-abstain trap: excluded information",
            "Positive sector-relative strength with a rising average is the intended "
            "context. The entry_context rule is executable. Company identity, news "
            "and target prices play no role in these meaning comparisons.",
            "SP", "X", "SHORT", q1=False, q2=False, q3=False,
            disposition="PASS_THROUGH",
            reason_codes=("NO_ADDITIONAL_CONTEXT_CONFLICT",),
            metric_group="NEGATIVE",
            gold_rationale="All semantics needed for the limited review are present.",
        ),
        _fixture(
            "v2-s05", s, "clear strategy conflict",
            "Only falling averages with the 20-day below the 60-day fit this strategy; "
            "the opposite rising arrangement is excluded. The entry_context rule is "
            "executable.",
            "R", "X", "SHORT", q1=True, q2=False, q3=False,
            disposition="REVIEW_REQUIRED",
            reason_codes=("STRATEGY_CONTEXT_CONFLICT",),
            metric_group="CONFLICT",
            gold_rationale="Provided conditions are explicitly excluded by strategy intent.",
        ),
        _fixture(
            "v2-s06", s, "clear Q1 conflict plus Q2 insufficient",
            "Sector underperformance with a falling average is required; sector "
            "outperformance with a rising average contradicts that intent. Band Alpha "
            "is confirmation-only and band Beta is executable. The entry_context rule "
            "represents the selected band.",
            "SP", "X", "SHORT", q1=True, q2=False, q3=False,
            disposition="REVIEW_REQUIRED",
            reason_codes=("STRATEGY_CONTEXT_CONFLICT",),
            metric_group="CONFLICT", cross_question=True,
            gold_rationale="Q1 is explicit; missing selected-band link cannot suppress Q1.",
        ),
        _fixture(
            "v2-s07", s, "clear entry conflict",
            "Rising averages above the slower average fit the strategy. The sole rule "
            "represented in entry_context is confirmation-only and must not denote an "
            "executable entry range.",
            "R", "X", "SHORT", q1=False, q2=True, q3=False,
            disposition="REVIEW_REQUIRED",
            reason_codes=("ENTRY_CONTEXT_CONFLICT",),
            metric_group="CONFLICT",
            gold_rationale="Same rule is confirmation-only in description but executable in state.",
        ),
        _fixture(
            "v2-s08", s, "clear Q2 conflict plus Q1 insufficient",
            "Context class K alone defines which directional condition combination "
            "fits this strategy. The single entry_context rule specifically denotes "
            "an executable range, not a strategy confirmation threshold.",
            "F", "C", "SHORT", q1=False, q2=True, q3=False,
            disposition="REVIEW_REQUIRED",
            reason_codes=("ENTRY_CONTEXT_CONFLICT",),
            metric_group="CONFLICT", cross_question=True,
            gold_rationale="Q2 is explicit; missing K definition cannot suppress Q2.",
        ),
        _fixture(
            "v2-s09", s, "no conflict plus Q1 definition missing",
            "Conditions are interpreted according to context class K. Only that class "
            "defines the intended directional combination. The entry_context rule is "
            "an executable range.",
            "R", "X", "SHORT", q1=False, q2=False, q3=True,
            disposition="ABSTAIN", uncertainty_reason="EVIDENCE_INSUFFICIENT",
            metric_group="INSUFFICIENT",
            gold_rationale="K is required for Q1 and absent; Q2 is consistent.",
        ),
        _fixture(
            "v2-s10", s, "no conflict plus Q2 rule link missing",
            "Rising averages above the slower average fit this setup. Band Alpha is "
            "confirmation-only and band Beta is executable. The rule in entry_context "
            "represents the selected band.",
            "R", "X", "SHORT", q1=False, q2=False, q3=True,
            disposition="ABSTAIN", uncertainty_reason="EVIDENCE_INSUFFICIENT",
            metric_group="INSUFFICIENT",
            gold_rationale="Selected band is unspecified, so Q2 cannot be completed.",
        ),
        _fixture(
            "v2-s11", s, "compound conflict",
            "Only falling averages with the 20-day below the 60-day are compatible. "
            "The sole rule in entry_context is confirmation-only and is never executable.",
            "R", "X", "SHORT", q1=True, q2=True, q3=False,
            disposition="REVIEW_REQUIRED",
            reason_codes=("STRATEGY_CONTEXT_CONFLICT", "ENTRY_CONTEXT_CONFLICT"),
            metric_group="CONFLICT",
            gold_rationale="Both independent conflicts are fully evidenced.",
        ),
        _fixture(
            "v2-s12", s, "semantic ambiguity",
            "This strategy prefers vigorous upward movement but can accept modest "
            "progress. A slightly rising average is a borderline fit. The entry_context "
            "rule is executable.",
            "M", "X", "SHORT", q1=None, q2=None, q3=None,
            disposition=None, metric_group="SOFT", hard=False,
            gold_rationale="Degree wording is intentionally soft; no single hard result.",
        ),
        _fixture(
            "v2-v01", v, "clear normal",
            "A 60-day average above its 120-day counterpart and positive market-relative "
            "strength express the intended structure. The rule in entry_context defines "
            "executable entries.",
            "L", "X", "MEDIUM", q1=False, q2=False, q3=False,
            disposition="PASS_THROUGH",
            reason_codes=("NO_ADDITIONAL_CONTEXT_CONFLICT",),
            metric_group="NEGATIVE",
            gold_rationale="Long-horizon condition and execution meanings agree.",
        ),
        _fixture(
            "v2-v02", v, "future uncertainty negative control",
            "The intended context is a 60-day average below the 120-day average with "
            "negative market-relative strength. The entry_context rule is executable. "
            "Nothing here asserts what prices will do next.",
            "D", "X", "MEDIUM", q1=False, q2=False, q3=False,
            disposition="PASS_THROUGH",
            reason_codes=("NO_ADDITIONAL_CONTEXT_CONFLICT",),
            metric_group="NEGATIVE",
            gold_rationale="Future outcome is not needed for current semantic comparison.",
        ),
        _fixture(
            "v2-v03", v, "false-positive trap: proximity wording",
            "The 60-day average above the 120-day and market outperformance fit this "
            "setup. The sole entry_context rule is a confirmation band. Its proximity "
            "to an execution area does not make it executable.",
            "L", "C", "MEDIUM", q1=False, q2=False, q3=False,
            disposition="PASS_THROUGH",
            reason_codes=("NO_ADDITIONAL_CONTEXT_CONFLICT",),
            metric_group="NEGATIVE",
            gold_rationale="Proximity does not change the confirmation-only role.",
        ),
        _fixture(
            "v2-v04", v, "false-abstain trap: complete bearish context",
            "Negative sector-relative strength together with a falling average is "
            "deliberately accepted by this strategy. The sole rule in entry_context "
            "is an executable range; no external event narrative is needed.",
            "SN", "X", "MEDIUM", q1=False, q2=False, q3=False,
            disposition="PASS_THROUGH",
            reason_codes=("NO_ADDITIONAL_CONTEXT_CONFLICT",),
            metric_group="NEGATIVE",
            gold_rationale="A bearish-looking context can still be semantically complete.",
        ),
        _fixture(
            "v2-v05", v, "clear strategy conflict",
            "The strategy excludes a 60-day average above the 120-day accompanied by "
            "market outperformance; it requires the reverse arrangement. The "
            "entry_context rule defines executable entries.",
            "L", "X", "MEDIUM", q1=True, q2=False, q3=False,
            disposition="REVIEW_REQUIRED",
            reason_codes=("STRATEGY_CONTEXT_CONFLICT",),
            metric_group="CONFLICT",
            gold_rationale="Observed long-horizon arrangement is directly excluded.",
        ),
        _fixture(
            "v2-v06", v, "clear Q1 conflict plus Q2 insufficient",
            "Sector leadership and a rising average are essential. Sector "
            "underperformance combined with a falling average is incompatible. One "
            "strategy band is executable and the other only confirms conditions. The "
            "entry_context rule names the chosen band.",
            "SN", "X", "MEDIUM", q1=True, q2=False, q3=False,
            disposition="REVIEW_REQUIRED",
            reason_codes=("STRATEGY_CONTEXT_CONFLICT",),
            metric_group="CONFLICT", cross_question=True,
            gold_rationale="Q1 is explicit while the chosen-band link is missing for Q2.",
        ),
        _fixture(
            "v2-v07", v, "clear entry conflict",
            "A 60-day average above the 120-day and market outperformance match the "
            "intent. The only rule supplied in entry_context marks confirmation, and "
            "granting execution meaning to that rule contradicts its purpose.",
            "L", "X", "MEDIUM", q1=False, q2=True, q3=False,
            disposition="REVIEW_REQUIRED",
            reason_codes=("ENTRY_CONTEXT_CONFLICT",),
            metric_group="CONFLICT",
            gold_rationale="Same rule is confirmation in description but executable in state.",
        ),
        _fixture(
            "v2-v08", v, "clear Q2 conflict plus Q1 insufficient",
            "Profile P determines whether the sector-relative strength and average "
            "slope match the strategy. The single rule in entry_context is the "
            "executable entry range itself, rather than a non-executable confirmation marker.",
            "SN", "C", "MEDIUM", q1=False, q2=True, q3=False,
            disposition="REVIEW_REQUIRED",
            reason_codes=("ENTRY_CONTEXT_CONFLICT",),
            metric_group="CONFLICT", cross_question=True,
            gold_rationale="Q2 is explicit while Profile P is missing for Q1.",
        ),
        _fixture(
            "v2-v09", v, "no conflict plus Q1 definition missing",
            "The relationship of the two long averages is evaluated using profile P, "
            "which determines whether the observed arrangement matches the strategy. "
            "The entry_context rule is executable.",
            "L", "X", "MEDIUM", q1=False, q2=False, q3=True,
            disposition="ABSTAIN", uncertainty_reason="EVIDENCE_INSUFFICIENT",
            metric_group="INSUFFICIENT",
            gold_rationale="Profile P is required for Q1 and absent; Q2 is consistent.",
        ),
        _fixture(
            "v2-v10", v, "no conflict plus Q2 rule link missing",
            "The supplied negative sector-relative strength and falling average are "
            "intentional. One strategy band is executable and the other only confirms "
            "conditions. The entry_context rule names the chosen band.",
            "SN", "C", "MEDIUM", q1=False, q2=False, q3=True,
            disposition="ABSTAIN", uncertainty_reason="EVIDENCE_INSUFFICIENT",
            metric_group="INSUFFICIENT",
            gold_rationale="Chosen-band link is missing, leaving Q2 incomplete.",
        ),
        _fixture(
            "v2-v11", v, "compound conflict",
            "Only sector leadership with a rising average fits this strategy. The "
            "single rule in entry_context is an executable entry range and must not "
            "be classified as a confirmation-only threshold.",
            "SN", "C", "MEDIUM", q1=True, q2=True, q3=False,
            disposition="REVIEW_REQUIRED",
            reason_codes=("STRATEGY_CONTEXT_CONFLICT", "ENTRY_CONTEXT_CONFLICT"),
            metric_group="CONFLICT",
            gold_rationale="Both strategy and entry meanings explicitly conflict.",
        ),
        _fixture(
            "v2-v12", v, "semantic ambiguity",
            "The intended structure favors the 60-day above the 120-day with market "
            "outperformance. The entry_context band is normally confirmation-only, "
            "though its practical entry meaning can vary with context.",
            "L", "C", "MEDIUM", q1=None, q2=None, q3=None,
            disposition=None, metric_group="SOFT", hard=False,
            gold_rationale="Normally/can-vary wording is intentionally soft.",
        ),
    ]
    return fixtures


def threshold_candidate_grid() -> list[dict[str, float]]:
    return [
        {
            "threshold_strategy": strategy,
            "threshold_entry": entry,
            "threshold_evidence": evidence,
        }
        for strategy, entry, evidence in itertools.product(
            THRESHOLD_STRATEGY_CANDIDATES,
            THRESHOLD_ENTRY_CANDIDATES,
            THRESHOLD_EVIDENCE_CANDIDATES,
        )
    ]


def build_canary_v2_protocol_artifact() -> dict[str, Any]:
    spec = {
        "provider_id": JEV_TYPESAFE_PROVIDER_ID,
        "models_endpoint": "https://api.typesafe.ai/v1/models",
        "systemone_endpoint": "https://api.typesafe.ai/v1/systemone",
        "model_discovery_attempts_max": MAX_MODEL_DISCOVERY_ATTEMPTS,
        "systemone_attempts_max": MAX_SYSTEM_ONE_ATTEMPTS,
        "total_api_attempts_max": MAX_TOTAL_API_ATTEMPTS,
        "repetitions": CANARY_V2_REPETITIONS,
        "api_budget_usd": CANARY_V2_API_BUDGET_USD,
        "per_call_reservation_required": True,
        "threshold_candidates": threshold_candidate_grid(),
        "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
        "question_set_hash": JEV_TYPESAFE_QUESTION_SET_HASH_V2,
        "disposition_policy_version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
        "disposition_policy_hash": JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V2,
        "fixtures": synthetic_canary_v2_fixtures(),
        "selection_rule": {
            "selection_partition": "selection",
            "validation_partition": "validation",
            "lock_one_tuple_before_validation": True,
            "validation_fallback_forbidden": True,
            "tie_break": [
                "soft_intervention_count_asc",
                "soft_abstain_count_asc",
                "threshold_strategy_desc",
                "threshold_entry_desc",
                "threshold_evidence_desc",
            ],
        },
        "real_stock_data_allowed": False,
        "actual_trial_activation_allowed": False,
        "retry_count": 0,
        "concurrency_cap": 1,
    }
    return {
        "artifact_version": CANARY_V2_ARTIFACT_VERSION,
        "protocol_id": CANARY_V2_PROTOCOL_ID,
        "status": "FROZEN_BEFORE_REAL_CALLS",
        "frozen_at": "2026-10-06",
        "protocol_hash": digest_json(spec),
        "spec": spec,
    }


def _projector_preflight_state(state: dict[str, Any]) -> dict[str, Any]:
    conditions = list(state["condition_context"])
    entry = state["entry_context"]
    sample = {
        "capture_run_id": "SYNTHETIC-CANARY-V2",
        "sample_index": 0,
        "market": state["context"]["market"],
        "signal_date": state["context"]["as_of_date"],
        "horizon_intent": state["context"]["horizon_intent"],
        "action": "ENTRY_CANDIDATE",
        "candidate_state": "READY",
        "strategy": state["strategy_context"]["strategy_key"],
        "snapshot": {
            "market": state["context"]["market"],
            "data_date": state["context"]["as_of_date"],
            "candidate_state": "READY",
            "strategy": state["strategy_context"]["strategy_key"],
            "strategy_version_id": "SYNTHETIC-V2",
            "strategy_definition_hash": "SYNTHETIC-V2",
            "strategy_description": state["strategy_context"]["strategy_description"],
            "action": "ENTRY_CANDIDATE",
            "conditions": {
                "passed": len(conditions),
                "total": len(conditions),
                "missing": 0,
                "top_missing": [],
            },
            "risk": {"status": "READY", "warning": False, "warnings": []},
            "entry_risk_guide": {
                "price_rule": dict(entry["price_rule"]),
                "action": {"status": "ENTRY_CANDIDATE"},
                "price_consistency": {
                    "status": "OK",
                    **dict(entry["price_consistency"]),
                },
            },
            "_repro_condition_details": [
                {
                    "condition_id": f"synthetic-{index}",
                    "raw": "synthetic",
                    "label": "synthetic",
                    "detail": "synthetic",
                    "status": item["status"],
                    "current_value": item["current_value"],
                    "required_value": item["required_value"],
                    "metric_key": item["metric_key"],
                }
                for index, item in enumerate(conditions)
            ],
        },
    }
    return project_typesafe_state(sample).state


def validate_canary_v2_contract() -> dict[str, Any]:
    artifact = build_canary_v2_protocol_artifact()
    fixtures = artifact["spec"]["fixtures"]
    if len(fixtures) != 24:
        raise TypeSafeCanaryV2Error("CANARY_V2_FIXTURE_COUNT_INVALID")
    selection = [f for f in fixtures if f["partition"] == "selection"]
    validation = [f for f in fixtures if f["partition"] == "validation"]
    if len(selection) != 12 or len(validation) != 12:
        raise TypeSafeCanaryV2Error("CANARY_V2_PARTITION_COUNT_INVALID")
    if len(fixtures) * CANARY_V2_REPETITIONS != MAX_SYSTEM_ONE_ATTEMPTS:
        raise TypeSafeCanaryV2Error("CANARY_V2_CALL_CAP_INVALID")
    if len(threshold_candidate_grid()) != 27:
        raise TypeSafeCanaryV2Error("CANARY_V2_THRESHOLD_GRID_INVALID")

    forbidden_tokens = (
        '"ticker"',
        '"name"',
        '"rank"',
        '"holdings"',
        '"account"',
        '"user_id"',
        '"portfolio"',
        '"future_outcome"',
        '"news"',
    )
    for partition in (selection, validation):
        if sum(1 for f in partition if f["hard_expectation"]) != 11:
            raise TypeSafeCanaryV2Error("CANARY_V2_HARD_COUNT_INVALID")
        if sum(1 for f in partition if not f["hard_expectation"]) != 1:
            raise TypeSafeCanaryV2Error("CANARY_V2_SOFT_COUNT_INVALID")
        if sum(1 for f in partition if f["metric_group"] == "NEGATIVE") != 4:
            raise TypeSafeCanaryV2Error("CANARY_V2_NEGATIVE_COUNT_INVALID")
        if sum(1 for f in partition if f["metric_group"] == "CONFLICT") != 5:
            raise TypeSafeCanaryV2Error("CANARY_V2_CONFLICT_COUNT_INVALID")
        if sum(1 for f in partition if f["metric_group"] == "INSUFFICIENT") != 2:
            raise TypeSafeCanaryV2Error("CANARY_V2_INSUFFICIENT_COUNT_INVALID")
        if sum(1 for f in partition if f["cross_question"]) != 2:
            raise TypeSafeCanaryV2Error("CANARY_V2_CROSS_QUESTION_COUNT_INVALID")

    for fixture in fixtures:
        encoded = canonical_json(fixture["state"]).lower()
        if any(token in encoded for token in forbidden_tokens):
            raise TypeSafeCanaryV2Error(
                "CANARY_V2_REAL_DATA_FIELD_FORBIDDEN",
                fixture["fixture_id"],
            )
        if fixture["state_hash"] != digest_json(fixture["state"]):
            raise TypeSafeCanaryV2Error("CANARY_V2_STATE_HASH_INVALID")
        if _projector_preflight_state(fixture["state"]) != fixture["state"]:
            raise TypeSafeCanaryV2Error(
                "CANARY_V2_PROJECTOR_PREFLIGHT_MISMATCH",
                fixture["fixture_id"],
            )
        expected = fixture["expected_propositions"]
        if set(expected) != set(JEV_TYPESAFE_QUESTION_IDS_V2):
            raise TypeSafeCanaryV2Error("CANARY_V2_EXPECTATION_SHAPE_INVALID")
        if fixture["hard_expectation"]:
            if not all(isinstance(expected[q], bool) for q in JEV_TYPESAFE_QUESTION_IDS_V2):
                raise TypeSafeCanaryV2Error("CANARY_V2_HARD_GOLD_INVALID")
            if fixture["expected_disposition"] not in {
                "PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN"
            }:
                raise TypeSafeCanaryV2Error("CANARY_V2_DISPOSITION_GOLD_INVALID")
    return artifact


def write_canary_v2_protocol(
    path: Path = CANARY_V2_PROTOCOL_PATH,
) -> Path:
    artifact = validate_canary_v2_contract()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_frozen_canary_v2_protocol(
    path: Path = CANARY_V2_PROTOCOL_PATH,
) -> dict[str, Any]:
    expected = validate_canary_v2_contract()
    if not path.is_file():
        raise TypeSafeCanaryV2Error("CANARY_V2_PROTOCOL_NOT_FROZEN")
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TypeSafeCanaryV2Error("CANARY_V2_PROTOCOL_INVALID") from exc
    if stored != expected:
        raise TypeSafeCanaryV2Error("CANARY_V2_PROTOCOL_MISMATCH")
    return stored


def classify_model_channel(model: dict[str, Any]) -> str:
    name = str(model.get("name") or "").strip().lower()
    if "preview" in name:
        return PREVIEW_ALIAS
    if name == "jev-latest" or name.endswith("-latest"):
        return STABLE_ALIAS

    # A version-looking name is not proof of immutability. Public discovery
    # currently exposes name/description/release_date only, so immutable
    # classification requires separate verified metadata bound later.
    if (
        re.fullmatch(r"jev-\\d+(?:\\.\\d+)+", name)
        and model.get("immutable_verified") is True
    ):
        return IMMUTABLE_VERSION_VERIFIED
    return UNKNOWN_CHANNEL


def select_canary_v2_model(
    models: list[dict[str, str]],
    *,
    override: str | None = None,
) -> dict[str, Any]:
    by_name = {item["name"]: item for item in models}
    if override:
        if override not in by_name:
            raise TypeSafeCanaryV2Error("CANARY_V2_MODEL_OVERRIDE_NOT_AVAILABLE")
        selected = by_name[override]
        channel = classify_model_channel(selected)
        if channel == PREVIEW_ALIAS:
            raise TypeSafeCanaryV2Error("CANARY_V2_PREVIEW_MODEL_FORBIDDEN")
        if channel not in {STABLE_ALIAS, IMMUTABLE_VERSION_VERIFIED}:
            raise TypeSafeCanaryV2Error("CANARY_V2_MODEL_CHANNEL_UNVERIFIED")
        return {**selected, "request_channel_class": channel}

    immutable = [
        item for item in models
        if classify_model_channel(item) == IMMUTABLE_VERSION_VERIFIED
    ]
    immutable.sort(
        key=lambda item: (item.get("release_date", ""), item.get("name", "")),
        reverse=True,
    )
    if immutable:
        return {
            **immutable[0],
            "request_channel_class": IMMUTABLE_VERSION_VERIFIED,
        }
    if "jev-latest" in by_name:
        return {
            **by_name["jev-latest"],
            "request_channel_class": STABLE_ALIAS,
        }
    raise TypeSafeCanaryV2Error("CANARY_V2_STABLE_MODEL_UNAVAILABLE")


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
    raise ValueError("CANARY_V2_REPETITION_INVALID")


def _metrics_for_candidate(
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
    candidate: dict[str, float],
) -> dict[str, Any]:
    fixtures = _fixture_map(artifact)
    proposition_mismatches = 0
    disposition_errors = 0
    false_escalation = 0
    false_abstention = 0
    missed_conflict = 0
    missed_insufficiency = 0
    wrong_reason = 0
    cross_question_errors = 0
    hard_checks = 0
    hard_dispositions = 0
    review_count = 0
    abstain_count = 0
    soft_intervention_count = 0
    soft_abstain_count = 0

    by_fixture: dict[str, list[tuple[Any, dict[str, bool]]]] = defaultdict(list)
    for record in records:
        fixture = fixtures[record["fixture_id"]]
        decision = decide_typesafe_disposition_v2(
            record["probabilities"],
            threshold_strategy=candidate["threshold_strategy"],
            threshold_entry=candidate["threshold_entry"],
            threshold_evidence=candidate["threshold_evidence"],
        )
        gates = dict(decision.gate_results)
        by_fixture[record["fixture_id"]].append((decision, gates))
        if decision.disposition == "REVIEW_REQUIRED":
            review_count += 1
        if decision.disposition == "ABSTAIN":
            abstain_count += 1
        if not fixture["hard_expectation"]:
            if decision.disposition in {"REVIEW_REQUIRED", "ABSTAIN"}:
                soft_intervention_count += 1
            if decision.disposition == "ABSTAIN":
                soft_abstain_count += 1
            continue

        hard_dispositions += 1
        expected = fixture["expected_propositions"]
        for question_id in JEV_TYPESAFE_QUESTION_IDS_V2:
            hard_checks += 1
            if gates[question_id] is not expected[question_id]:
                proposition_mismatches += 1

        expected_reasons = tuple(fixture["expected_reason_codes"])
        if (
            decision.disposition != fixture["expected_disposition"]
            or decision.reason_codes != expected_reasons
            or decision.uncertainty_reason != fixture["expected_uncertainty_reason"]
        ):
            disposition_errors += 1

        group = fixture["metric_group"]
        if group == "NEGATIVE" and decision.disposition == "REVIEW_REQUIRED":
            false_escalation += 1
        if group in {"NEGATIVE", "CONFLICT"} and decision.disposition == "ABSTAIN":
            false_abstention += 1
        if group == "CONFLICT":
            if (
                decision.disposition != "REVIEW_REQUIRED"
                or decision.reason_codes != expected_reasons
            ):
                missed_conflict += 1
                wrong_reason += 1
        if group == "INSUFFICIENT" and decision.disposition != "ABSTAIN":
            missed_insufficiency += 1
        if fixture["cross_question"]:
            if (
                decision.disposition != "REVIEW_REQUIRED"
                or decision.reason_codes != expected_reasons
            ):
                cross_question_errors += 1

    d_cross = e_cross = a_cross = reason_cross = 0
    question_cross = {question_id: 0 for question_id in JEV_TYPESAFE_QUESTION_IDS_V2}
    for fixture_id, items in by_fixture.items():
        dispositions = {item[0].disposition for item in items}
        escalations = {item[0].disposition == "REVIEW_REQUIRED" for item in items}
        abstains = {item[0].disposition == "ABSTAIN" for item in items}
        reasons = {item[0].reason_codes for item in items}
        if len(dispositions) > 1:
            d_cross += 1
        if len(escalations) > 1:
            e_cross += 1
        if len(abstains) > 1:
            a_cross += 1
        if len(reasons) > 1:
            reason_cross += 1
        if fixtures[fixture_id]["hard_expectation"]:
            for question_id in JEV_TYPESAFE_QUESTION_IDS_V2:
                if len({item[1][question_id] for item in items}) > 1:
                    question_cross[question_id] += 1

    valid_count = len(records)
    intervention_count = review_count + abstain_count
    gates_pass = (
        valid_count == 36
        and hard_checks == 99
        and hard_dispositions == 33
        and proposition_mismatches == 0
        and disposition_errors == 0
        and false_escalation == 0
        and false_abstention == 0
        and missed_conflict == 0
        and missed_insufficiency == 0
        and wrong_reason == 0
        and cross_question_errors == 0
        and d_cross == 0
        and e_cross == 0
        and a_cross == 0
        and reason_cross == 0
        and all(value == 0 for value in question_cross.values())
        and review_count <= 18
        and abstain_count <= 9
        and intervention_count <= 24
    )
    return {
        **candidate,
        "hard_proposition_checks": hard_checks,
        "hard_proposition_mismatches": proposition_mismatches,
        "hard_disposition_checks": hard_dispositions,
        "hard_disposition_reason_errors": disposition_errors,
        "false_escalation": false_escalation,
        "false_abstention": false_abstention,
        "missed_conflict": missed_conflict,
        "missed_insufficiency": missed_insufficiency,
        "wrong_reason": wrong_reason,
        "cross_question_errors": cross_question_errors,
        "review_count": review_count,
        "abstain_count": abstain_count,
        "intervention_count": intervention_count,
        "soft_intervention_count": soft_intervention_count,
        "soft_abstain_count": soft_abstain_count,
        "d_crossing": d_cross,
        "e_crossing": e_cross,
        "a_crossing": a_cross,
        "reason_crossing": reason_cross,
        "question_crossing": question_cross,
        "eligible": gates_pass,
    }


def select_threshold_from_selection(
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
) -> dict[str, Any]:
    candidates = [
        _metrics_for_candidate(records, artifact, candidate)
        for candidate in artifact["spec"]["threshold_candidates"]
    ]
    eligible = [item for item in candidates if item["eligible"]]
    selected = None
    if eligible:
        selected = sorted(
            eligible,
            key=lambda item: (
                item["soft_intervention_count"],
                item["soft_abstain_count"],
                -item["threshold_strategy"],
                -item["threshold_entry"],
                -item["threshold_evidence"],
            ),
        )[0]
    return {"candidates": candidates, "selected": selected}


def evaluate_locked_threshold(
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
    selected: dict[str, Any],
) -> dict[str, Any]:
    candidate = {
        "threshold_strategy": float(selected["threshold_strategy"]),
        "threshold_entry": float(selected["threshold_entry"]),
        "threshold_evidence": float(selected["threshold_evidence"]),
    }
    return _metrics_for_candidate(records, artifact, candidate)


def _safe_report_path() -> Path:
    return (
        CANARY_V2_VALIDATION_DIR
        / f"JEV_TYPESAFE_CANARY_V2_{date.today().isoformat()}.json"
    )


def _blocked_report(
    artifact: dict[str, Any],
    code: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "report_version": CANARY_V2_REPORT_VERSION,
        "status": "BLOCKED",
        "canary_protocol_id": CANARY_V2_PROTOCOL_ID,
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


async def run_real_canary_v2(
    *,
    per_call_reservation_usd: float | None,
    model_override: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    deadline_seconds: float = 10.0,
) -> dict[str, Any]:
    artifact = validate_canary_v2_contract()
    if (
        per_call_reservation_usd is None
        or isinstance(per_call_reservation_usd, bool)
        or not math.isfinite(float(per_call_reservation_usd))
        or float(per_call_reservation_usd) <= 0.0
    ):
        return _blocked_report(
            artifact, "BLOCKED_COST_RESERVATION_UNVERIFIED"
        )
    reservation = float(per_call_reservation_usd)
    if reservation * MAX_SYSTEM_ONE_ATTEMPTS > CANARY_V2_API_BUDGET_USD:
        return _blocked_report(
            artifact, "BLOCKED_COST_RESERVATION_EXCEEDS_BUDGET"
        )

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
        selected_model = select_canary_v2_model(
            models, override=model_override
        )
    except (TypeSafeJevProviderError, TypeSafeCanaryV2Error) as exc:
        code = exc.code if hasattr(exc, "code") else "CANARY_V2_MODEL_DISCOVERY_FAILED"
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
        fixtures = [
            item for item in artifact["spec"]["fixtures"]
            if item["partition"] == partition
        ]
        for repetition in range(1, CANARY_V2_REPETITIONS + 1):
            for fixture in _partition_order(fixtures, repetition):
                if counts["attempted"] >= MAX_SYSTEM_ONE_ATTEMPTS:
                    errors.append("CANARY_V2_SYSTEMONE_ATTEMPT_CAP_REACHED")
                    return False
                if reserved_exposure + reservation > CANARY_V2_API_BUDGET_USD:
                    errors.append("CANARY_V2_BUDGET_RESERVATION_BLOCKED")
                    return False

                # Reservation and attempt are recorded before the provider call.
                reserved_exposure += reservation
                counts["attempted"] += 1
                attempts["systemone"] += 1
                request = {
                    "state": fixture["state"],
                    "questions": build_typesafe_questions_v2(),
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
                        expected_question_ids=JEV_TYPESAFE_QUESTION_IDS_V2,
                    )
                except TypeSafeJevProviderError as exc:
                    counts["failed"] += 1
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
                        "fixture_hash": fixture["state_hash"],
                        "repetition": repetition,
                        "model_requested": selected_model["name"],
                        "model_returned": normalized["model"],
                        "probabilities": normalized["probabilities"],
                        "usage": normalized["usage"],
                        "latency_ms": latency_ms,
                    }
                )
        return True

    selection_complete = await run_partition("selection")
    selection_analysis = select_threshold_from_selection(
        records_by_partition["selection"], artifact
    )
    selected_threshold = selection_analysis["selected"]
    validation_analysis = None

    if not selection_complete or len(records_by_partition["selection"]) != 36:
        errors.append("CANARY_V2_SELECTION_INCOMPLETE")
    elif selected_threshold is None:
        errors.append("CANARY_V2_NO_ELIGIBLE_THRESHOLD")
    else:
        validation_complete = await run_partition("validation")
        if not validation_complete or len(records_by_partition["validation"]) != 36:
            errors.append("CANARY_V2_VALIDATION_INCOMPLETE")
        else:
            validation_analysis = evaluate_locked_threshold(
                records_by_partition["validation"],
                artifact,
                selected_threshold,
            )
            if not validation_analysis["eligible"]:
                errors.append("CANARY_V2_VALIDATION_FAILED")

    all_records = (
        records_by_partition["selection"]
        + records_by_partition["validation"]
    )
    returned_models = sorted(
        {str(record["model_returned"]) for record in all_records}
    )
    if len(returned_models) > 1:
        errors.append("CANARY_V2_MODEL_IDENTITY_CHANGED")

    input_tokens = sum(
        int(record["usage"]["input_tokens"]) for record in all_records
    )
    output_tokens = sum(
        int(record["usage"]["output_tokens"]) for record in all_records
    )
    status = "PASS" if not errors else "FAIL"
    completed = datetime.now(timezone.utc).isoformat()
    binding = {
        "artifact_version": CANARY_V2_MODEL_BINDING_VERSION,
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
        "report_version": CANARY_V2_REPORT_VERSION,
        "status": status,
        "canary_protocol_id": CANARY_V2_PROTOCOL_ID,
        "canary_protocol_hash": artifact["protocol_hash"],
        "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
        "question_set_hash": JEV_TYPESAFE_QUESTION_SET_HASH_V2,
        "disposition_policy_version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
        "disposition_policy_hash": JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V2,
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
            "hard_budget_usd": CANARY_V2_API_BUDGET_USD,
            "per_call_reservation_usd": reservation,
            "reserved_exposure_usd": reserved_exposure,
            "actual_provider_cost_usd": None,
            "actual_provider_cost_status": "UNKNOWN",
        },
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
        "selection_analysis": selection_analysis,
        "selected_threshold": (
            {
                "threshold_strategy": selected_threshold["threshold_strategy"],
                "threshold_entry": selected_threshold["threshold_entry"],
                "threshold_evidence": selected_threshold["threshold_evidence"],
            }
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


def write_canary_v2_outputs(
    report: dict[str, Any],
    *,
    report_path: Path | None = None,
    binding_path: Path = CANARY_V2_MODEL_BINDING_PATH,
) -> tuple[Path, Path]:
    path = Path(report_path or _safe_report_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    binding_path.write_text(
        json.dumps(
            report.get("model_binding") or {},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path, binding_path
