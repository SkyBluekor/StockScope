from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.core.config import PROJECT_ROOT

from .models import canonical_json, digest_json
from .typesafe_models import (
    JEV_TYPESAFE_PROVIDER_ID,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION,
)
from .typesafe_provider import (
    TypeSafeJevProviderError,
    TypeSafeSystemOneProvider,
    discover_typesafe_models,
    validate_system_one_response,
)
from .typesafe_questions import (
    JEV_TYPESAFE_QUESTION_IDS,
    JEV_TYPESAFE_QUESTION_SET_HASH,
    build_typesafe_questions,
)


CANARY_ARTIFACT_VERSION = "JEV_TYPESAFE_CANARY_PROTOCOL_ARTIFACT_V1"
CANARY_PROTOCOL_ID = "JEV-TYPESAFE-CANARY-V1"
PUBLIC_API_VERSION = "0.2.0"
PUBLIC_INPUT_PRICE_USD_PER_MILLION = 0.042
PUBLIC_OUTPUT_PRICE_USD_PER_MILLION = 0.0
MAX_MODEL_DISCOVERY_CALLS = 1
MAX_SYSTEM_ONE_CALLS = 24
MAX_TOTAL_API_CALLS = 25
CANARY_REPETITIONS = 2
CANARY_API_BUDGET_USD = 0.25
THRESHOLD_CANDIDATES = (
    (0.10, 0.90),
    (0.15, 0.85),
    (0.20, 0.80),
)
PREFERRED_THRESHOLD = (0.15, 0.85)

CANARY_PROTOCOL_PATH = (
    PROJECT_ROOT / "docs" / "contracts" / "JEV_TYPESAFE_CANARY_PROTOCOL_V1.json"
)
MODEL_BINDING_PATH = (
    PROJECT_ROOT / "docs" / "contracts" / "JEV_TYPESAFE_MODEL_BINDING_V1.json"
)
CANARY_VALIDATION_DIR = PROJECT_ROOT / "docs" / "validation"


class TypeSafeCanaryError(RuntimeError):
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


def _state(
    strategy_description: str,
    conditions: list[dict[str, Any]],
    *,
    semantic_role: str = "EXECUTABLE_ENTRY_RANGE",
    executable_entry_range: bool = True,
    classification: str = "ALIGNED",
) -> dict[str, Any]:
    return {
        "context": {
            "market": "SYNTHETIC",
            "as_of_date": "2026-10-06",
            "horizon_intent": "SHORT",
        },
        "strategy_context": {
            "strategy_key": "SYNTHETIC_PHASE1",
            "strategy_description": strategy_description,
        },
        "condition_context": conditions,
        "entry_context": {
            "price_rule": {
                "kind": "RANGE",
                "status": "MET",
                "semantic_role": semantic_role,
                "executable_entry_range": executable_entry_range,
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


def synthetic_canary_fixtures() -> list[dict[str, Any]]:
    base = [
        _condition(
            "price_vs_ma20",
            "price relation to the 20-day moving average",
            "above",
            "above",
        ),
        _condition(
            "volume_ratio_20",
            "volume versus 20-day average condition",
            "1.3x",
            "at least 1.0x",
        ),
    ]
    low_all = {
        "strategy_context_conflict": "LOW",
        "entry_context_conflict": "LOW",
        "review_evidence_insufficient": "LOW",
    }
    fixtures: list[dict[str, Any]] = []

    def add(
        fixture_id: str,
        category: str,
        state: dict[str, Any],
        expected_bands: dict[str, str],
        *,
        hard: bool = True,
        note: str = "",
    ) -> None:
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "category": category,
                "state": state,
                "expected_bands": expected_bands,
                "hard_expectation": hard,
                "note": note,
            }
        )

    add(
        "normal-01",
        "CLEAR_NORMAL",
        _state(
            "This strategy seeks confirmed trend continuation with price above "
            "its medium-term reference and adequate participation.",
            base,
        ),
        low_all,
    )
    add(
        "normal-02",
        "CLEAR_NORMAL",
        _state(
            "This strategy accepts an executable entry range only after its "
            "already-passed trend and participation conditions are satisfied.",
            [
                _condition(
                    "ma20_slope",
                    "20-day moving-average slope condition",
                    "rising",
                    "rising",
                ),
                _condition(
                    "relative_strength_market",
                    "relative strength versus the broad market",
                    "positive",
                    "positive",
                ),
            ],
        ),
        low_all,
    )
    add(
        "future-uncertainty-control",
        "CLEAR_NORMAL",
        _state(
            "This strategy reviews present trend context only. Future returns "
            "are intentionally unknown and are not required for this review.",
            base,
        ),
        low_all,
        note=(
            "q3 must not confuse ordinary future uncertainty with insufficient "
            "semantic evidence."
        ),
    )
    add(
        "strategy-conflict-01",
        "STRATEGY_CONFLICT",
        _state(
            "This strategy requires price to remain below the 20-day moving "
            "average and explicitly avoids above-average price continuation.",
            [
                _condition(
                    "price_vs_ma20",
                    "price relation to the 20-day moving average",
                    "above",
                    "above",
                ),
                _condition(
                    "ma20_slope",
                    "20-day moving-average slope condition",
                    "rising",
                    "rising",
                ),
            ],
        ),
        {
            "strategy_context_conflict": "HIGH",
            "entry_context_conflict": "LOW",
            "review_evidence_insufficient": "LOW",
        },
    )
    add(
        "strategy-conflict-02",
        "STRATEGY_CONFLICT",
        _state(
            "This strategy only accepts weak participation and explicitly "
            "rejects unusually active volume.",
            [
                _condition(
                    "volume_ratio_20",
                    "volume versus 20-day average condition",
                    "1.6x",
                    "at least 1.0x",
                ),
                _condition(
                    "relative_strength_market",
                    "relative strength versus the broad market",
                    "positive",
                    "positive",
                ),
            ],
        ),
        {
            "strategy_context_conflict": "HIGH",
            "entry_context_conflict": "LOW",
            "review_evidence_insufficient": "LOW",
        },
    )
    add(
        "entry-conflict-01",
        "ENTRY_CONFLICT",
        _state(
            "This strategy uses a condition threshold as confirmation; that "
            "threshold is not itself an executable buy range.",
            base,
            semantic_role="STRATEGY_CONDITION_THRESHOLD",
            executable_entry_range=False,
            classification="SEPARATED",
        ),
        {
            "strategy_context_conflict": "LOW",
            "entry_context_conflict": "HIGH",
            "review_evidence_insufficient": "LOW",
        },
    )
    add(
        "entry-conflict-02",
        "ENTRY_CONFLICT",
        _state(
            "This strategy separates confirmation bands from executable entries; "
            "confirmation bands must not be presented as buy ranges.",
            [
                _condition(
                    "distance_to_ma20",
                    "distance to the 20-day moving average condition",
                    "near",
                    "within condition band",
                ),
                _condition(
                    "rsi14",
                    "14-period RSI condition",
                    "58",
                    "within confirmation band",
                ),
            ],
            semantic_role="STRATEGY_CONDITION_THRESHOLD",
            executable_entry_range=False,
            classification="SEPARATED",
        ),
        {
            "strategy_context_conflict": "LOW",
            "entry_context_conflict": "HIGH",
            "review_evidence_insufficient": "LOW",
        },
    )
    add(
        "evidence-insufficient-01",
        "EVIDENCE_INSUFFICIENT",
        _state(
            "This strategy has a specific semantic intent that cannot be "
            "determined from the supplied abbreviated context.",
            [
                _condition(
                    "price_vs_ma20",
                    "price relation",
                    None,
                    None,
                )
            ],
            semantic_role="UNSPECIFIED",
            executable_entry_range=False,
            classification="UNKNOWN",
        ),
        {
            "strategy_context_conflict": "ANY",
            "entry_context_conflict": "ANY",
            "review_evidence_insufficient": "HIGH",
        },
    )
    add(
        "evidence-insufficient-02",
        "EVIDENCE_INSUFFICIENT",
        _state(
            "The strategy description is intentionally incomplete for this "
            "synthetic evidence-sufficiency control.",
            [
                _condition(
                    "volume_ratio_20",
                    "participation condition",
                    None,
                    None,
                )
            ],
            semantic_role="UNSPECIFIED",
            executable_entry_range=False,
            classification="UNKNOWN",
        ),
        {
            "strategy_context_conflict": "ANY",
            "entry_context_conflict": "ANY",
            "review_evidence_insufficient": "HIGH",
        },
    )
    add(
        "ambiguous-strategy-01",
        "AMBIGUOUS_BOUNDARY",
        _state(
            "This strategy usually prefers continuation but can tolerate mild "
            "pullback characteristics when the broader structure remains "
            "constructive.",
            [
                _condition(
                    "price_vs_ma20",
                    "price relation to the 20-day moving average",
                    "near threshold",
                    "confirmation threshold",
                ),
                _condition(
                    "relative_strength_market",
                    "relative strength versus the broad market",
                    "slightly positive",
                    "positive",
                ),
            ],
        ),
        {
            "strategy_context_conflict": "ANY",
            "entry_context_conflict": "LOW",
            "review_evidence_insufficient": "LOW",
        },
        hard=False,
    )
    add(
        "ambiguous-entry-01",
        "AMBIGUOUS_BOUNDARY",
        _state(
            "This strategy uses a confirmation band near the eventual execution "
            "area, but the two concepts remain distinct.",
            base,
            semantic_role="CONDITION_BAND_NEAR_EXECUTION",
            executable_entry_range=False,
            classification="NEAR",
        ),
        {
            "strategy_context_conflict": "LOW",
            "entry_context_conflict": "ANY",
            "review_evidence_insufficient": "LOW",
        },
        hard=False,
    )
    add(
        "compound-conflict-01",
        "COMPOUND_CONFLICT",
        _state(
            "This strategy requires price below its reference and treats only an "
            "explicitly executable range as an entry.",
            [
                _condition(
                    "price_vs_ma20",
                    "price relation to the 20-day moving average",
                    "above",
                    "above",
                ),
                _condition(
                    "ma20_slope",
                    "20-day moving-average slope condition",
                    "rising",
                    "rising",
                ),
            ],
            semantic_role="STRATEGY_CONDITION_THRESHOLD",
            executable_entry_range=False,
            classification="SEPARATED",
        ),
        {
            "strategy_context_conflict": "HIGH",
            "entry_context_conflict": "HIGH",
            "review_evidence_insufficient": "LOW",
        },
    )
    return fixtures


def build_canary_protocol_artifact() -> dict[str, Any]:
    spec = {
        "provider_id": JEV_TYPESAFE_PROVIDER_ID,
        "public_api_version": PUBLIC_API_VERSION,
        "models_endpoint": "https://api.typesafe.ai/v1/models",
        "systemone_endpoint": "https://api.typesafe.ai/v1/systemone",
        "model_discovery_calls_max": MAX_MODEL_DISCOVERY_CALLS,
        "systemone_calls_max": MAX_SYSTEM_ONE_CALLS,
        "total_api_calls_max": MAX_TOTAL_API_CALLS,
        "repetitions": CANARY_REPETITIONS,
        "api_budget_usd": CANARY_API_BUDGET_USD,
        "public_input_price_usd_per_million": (
            PUBLIC_INPUT_PRICE_USD_PER_MILLION
        ),
        "public_output_price_usd_per_million": (
            PUBLIC_OUTPUT_PRICE_USD_PER_MILLION
        ),
        "threshold_candidates": [
            {"low": low, "high": high}
            for low, high in THRESHOLD_CANDIDATES
        ],
        "preferred_threshold": {
            "low": PREFERRED_THRESHOLD[0],
            "high": PREFERRED_THRESHOLD[1],
        },
        "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION,
        "fixtures": synthetic_canary_fixtures(),
        "real_stock_data_allowed": False,
        "actual_trial_activation_allowed": False,
    }
    return {
        "artifact_version": CANARY_ARTIFACT_VERSION,
        "protocol_id": CANARY_PROTOCOL_ID,
        "status": "FROZEN_BEFORE_REAL_CALLS",
        "frozen_at": "2026-10-06",
        "protocol_hash": digest_json(spec),
        "spec": spec,
    }


def write_canary_protocol(
    path: Path = CANARY_PROTOCOL_PATH,
) -> Path:
    artifact = build_canary_protocol_artifact()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def validate_canary_contract() -> dict[str, Any]:
    artifact = build_canary_protocol_artifact()
    fixtures = artifact["spec"]["fixtures"]
    if len(fixtures) != 12:
        raise TypeSafeCanaryError("CANARY_FIXTURE_COUNT_INVALID")
    if len(fixtures) * CANARY_REPETITIONS != MAX_SYSTEM_ONE_CALLS:
        raise TypeSafeCanaryError("CANARY_CALL_BUDGET_INVALID")
    for fixture in fixtures:
        state = fixture["state"]
        encoded = canonical_json(state).lower()
        forbidden_tokens = (
            '"ticker"',
            '"name"',
            '"rank"',
            '"holdings"',
            '"account"',
            '"user_id"',
            '"future_outcome"',
        )
        if any(token in encoded for token in forbidden_tokens):
            raise TypeSafeCanaryError(
                "CANARY_REAL_DATA_FIELD_FORBIDDEN",
                str(fixture["fixture_id"]),
            )
        if set(fixture["expected_bands"]) != set(JEV_TYPESAFE_QUESTION_IDS):
            raise TypeSafeCanaryError("CANARY_EXPECTATION_SHAPE_INVALID")
    return artifact


def select_canary_model(
    models: list[dict[str, str]],
    *,
    override: str | None = None,
) -> dict[str, Any]:
    by_name = {item["name"]: item for item in models}
    if override:
        if override not in by_name:
            raise TypeSafeCanaryError("CANARY_MODEL_OVERRIDE_NOT_AVAILABLE")
        selected = by_name[override]
    else:
        versioned = [
            item
            for item in models
            if item["name"].lower().startswith("jev-")
            and "latest" not in item["name"].lower()
        ]
        versioned.sort(
            key=lambda item: (
                item.get("release_date", ""),
                item.get("name", ""),
            ),
            reverse=True,
        )
        if versioned:
            selected = versioned[0]
        elif "jev-latest" in by_name:
            selected = by_name["jev-latest"]
        else:
            selected = sorted(
                models,
                key=lambda item: (
                    item.get("release_date", ""),
                    item.get("name", ""),
                ),
                reverse=True,
            )[0]
    return {
        **selected,
        "alias_used": "latest" in selected["name"].lower(),
    }


def _band(value: float, low: float, high: float) -> str:
    if value <= low:
        return "LOW"
    if value >= high:
        return "HIGH"
    return "GRAY"


def evaluate_threshold_candidates(
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
) -> dict[str, Any]:
    fixtures = {
        item["fixture_id"]: item
        for item in artifact["spec"]["fixtures"]
    }
    results: list[dict[str, Any]] = []

    for candidate in artifact["spec"]["threshold_candidates"]:
        low = float(candidate["low"])
        high = float(candidate["high"])
        hard_mismatches = 0
        hard_checks = 0
        bands_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
        for record in records:
            fixture = fixtures[record["fixture_id"]]
            for question_id, probability in record["probabilities"].items():
                actual = _band(float(probability), low, high)
                bands_by_key[(record["fixture_id"], question_id)].add(actual)
                expected = fixture["expected_bands"][question_id]
                if fixture["hard_expectation"] and expected != "ANY":
                    hard_checks += 1
                    if actual != expected:
                        hard_mismatches += 1

        hard_instability = 0
        for (fixture_id, question_id), bands in bands_by_key.items():
            fixture = fixtures[fixture_id]
            expected = fixture["expected_bands"][question_id]
            if (
                fixture["hard_expectation"]
                and expected != "ANY"
                and len(bands) > 1
            ):
                hard_instability += 1
        results.append(
            {
                "low": low,
                "high": high,
                "hard_checks": hard_checks,
                "hard_mismatches": hard_mismatches,
                "hard_instability_count": hard_instability,
                "eligible": (
                    hard_mismatches == 0
                    and hard_instability == 0
                ),
            }
        )

    eligible = [item for item in results if item["eligible"]]
    selected = None
    if eligible:
        preferred = artifact["spec"]["preferred_threshold"]
        for item in eligible:
            if (
                item["low"] == float(preferred["low"])
                and item["high"] == float(preferred["high"])
            ):
                selected = item
                break
        if selected is None:
            selected = sorted(
                eligible,
                key=lambda item: (
                    abs(item["low"] - PREFERRED_THRESHOLD[0])
                    + abs(item["high"] - PREFERRED_THRESHOLD[1]),
                    -item["low"],
                ),
            )[0]
    return {
        "candidates": results,
        "selected": selected,
    }


def _safe_report_path() -> Path:
    return (
        CANARY_VALIDATION_DIR
        / f"JEV_TYPESAFE_CANARY_V1_{date.today().isoformat()}.json"
    )


def _estimated_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens / 1_000_000) * PUBLIC_INPUT_PRICE_USD_PER_MILLION
        + (output_tokens / 1_000_000) * PUBLIC_OUTPUT_PRICE_USD_PER_MILLION
    )


async def run_real_canary(
    *,
    model_override: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    deadline_seconds: float = 10.0,
) -> dict[str, Any]:
    artifact = validate_canary_contract()
    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    model_calls = 0

    try:
        models = await discover_typesafe_models(
            deadline_seconds=deadline_seconds,
            transport=transport,
        )
    except TypeSafeJevProviderError as exc:
        return {
            "report_version": "JEV_TYPESAFE_CANARY_REPORT_V1",
            "status": "FAIL",
            "canary_protocol_id": CANARY_PROTOCOL_ID,
            "canary_protocol_hash": artifact["protocol_hash"],
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "api_calls": {"model_discovery": 1, "systemone": 0, "total": 1},
            "errors": [exc.code],
            "real_stock_data_sent": False,
            "actual_trial_activation": False,
        }

    selected_model = select_canary_model(
        models,
        override=model_override,
    )
    provider = TypeSafeSystemOneProvider(
        model_id=selected_model["name"],
        transport=transport,
    )
    observed_model: str | None = None
    records: list[dict[str, Any]] = []
    stop = False

    for fixture in artifact["spec"]["fixtures"]:
        if stop:
            break
        for repetition in range(1, CANARY_REPETITIONS + 1):
            if model_calls >= MAX_SYSTEM_ONE_CALLS:
                errors.append("CANARY_SYSTEMONE_CALL_CAP_REACHED")
                stop = True
                break
            request = {
                "state": fixture["state"],
                "questions": build_typesafe_questions(),
                "model": selected_model["name"],
            }
            before = time.perf_counter()
            try:
                result = await provider.review(
                    request,
                    deadline_seconds=deadline_seconds,
                )
                normalized = validate_system_one_response(
                    result.raw_response,
                    expected_model_returned=observed_model,
                )
            except TypeSafeJevProviderError as exc:
                errors.append(exc.code)
                stop = True
                break
            latency_ms = int(round((time.perf_counter() - before) * 1000))
            model_calls += 1
            if observed_model is None:
                observed_model = str(normalized["model"])
            records.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "category": fixture["category"],
                    "fixture_hash": digest_json(fixture["state"]),
                    "repetition": repetition,
                    "model_requested": selected_model["name"],
                    "model_returned": normalized["model"],
                    "probabilities": normalized["probabilities"],
                    "usage": normalized["usage"],
                    "latency_ms": latency_ms,
                }
            )

    threshold_analysis = evaluate_threshold_candidates(records, artifact)
    input_tokens = sum(
        int(record["usage"]["input_tokens"])
        for record in records
    )
    output_tokens = sum(
        int(record["usage"]["output_tokens"])
        for record in records
    )
    estimated_cost = _estimated_cost(input_tokens, output_tokens)
    if estimated_cost > CANARY_API_BUDGET_USD:
        errors.append("CANARY_API_BUDGET_EXCEEDED")
    if model_calls != MAX_SYSTEM_ONE_CALLS:
        errors.append("CANARY_INCOMPLETE_SYSTEMONE_CALLS")
    if threshold_analysis["selected"] is None:
        errors.append("CANARY_NO_ELIGIBLE_THRESHOLD")

    returned_models = sorted(
        {str(record["model_returned"]) for record in records}
    )
    if len(returned_models) > 1:
        errors.append("CANARY_MODEL_IDENTITY_CHANGED")

    status = "PASS" if not errors else "FAIL"
    completed = datetime.now(timezone.utc).isoformat()
    binding = {
        "artifact_version": "JEV_TYPESAFE_MODEL_BINDING_ARTIFACT_V1",
        "status": "OBSERVED_CANARY_BINDING",
        "checked_at": completed,
        "provider_id": JEV_TYPESAFE_PROVIDER_ID,
        "available_models": models,
        "selected_request_model": selected_model["name"],
        "selected_release_date": selected_model.get("release_date"),
        "alias_used": bool(selected_model.get("alias_used")),
        "observed_response_model": observed_model,
        "discovery_hash": digest_json(models),
        "canary_protocol_hash": artifact["protocol_hash"],
    }
    report = {
        "report_version": "JEV_TYPESAFE_CANARY_REPORT_V1",
        "status": status,
        "canary_protocol_id": CANARY_PROTOCOL_ID,
        "canary_protocol_hash": artifact["protocol_hash"],
        "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION,
        "question_set_hash": JEV_TYPESAFE_QUESTION_SET_HASH,
        "started_at": started,
        "completed_at": completed,
        "public_contract_snapshot": {
            "api_version": PUBLIC_API_VERSION,
            "docs_url": "https://api.typesafe.ai/docs",
            "openapi_url": "https://api.typesafe.ai/openapi.json",
            "input_price_usd_per_million": (
                PUBLIC_INPUT_PRICE_USD_PER_MILLION
            ),
            "output_price_usd_per_million": (
                PUBLIC_OUTPUT_PRICE_USD_PER_MILLION
            ),
            "privacy_binding": "PUBLIC_POLICY_ONLY",
        },
        "model_binding": binding,
        "api_calls": {
            "model_discovery": 1,
            "systemone": model_calls,
            "total": 1 + model_calls,
            "hard_cap": MAX_TOTAL_API_CALLS,
        },
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_public_price_usd": estimated_cost,
            "hard_budget_usd": CANARY_API_BUDGET_USD,
        },
        "threshold_analysis": threshold_analysis,
        "records": records,
        "errors": sorted(set(errors)),
        "real_stock_data_sent": False,
        "actual_trial_activation": False,
        "trial_freeze_readiness": (
            "READY_FOR_POLICY_BINDING"
            if status == "PASS"
            else "BLOCKED_CANARY_FAILED"
        ),
        "account_policy_binding": "NOT_VERIFIED_BY_CANARY",
    }
    return report


def write_canary_outputs(
    report: dict[str, Any],
    *,
    report_path: Path | None = None,
    binding_path: Path = MODEL_BINDING_PATH,
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
