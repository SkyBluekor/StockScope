from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .models import digest_json
from .typesafe_models import JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2
from .typesafe_questions_v2 import (
    ENTRY_CONTEXT_CONFLICT,
    OVERALL_SEMANTIC_REVIEW_INSUFFICIENT,
    STRATEGY_CONTEXT_CONFLICT,
)


POLICY_DEFINITION_V2 = {
    "version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
    "threshold_slots": [
        "threshold_strategy",
        "threshold_entry",
        "threshold_evidence",
    ],
    "gates": {
        "strategy": "p1 >= T_strategy",
        "entry": "p2 >= T_entry",
        "evidence": "p3 >= T_evidence",
    },
    "precedence": [
        "conflict(Q1,Q2)",
        "overall_semantic_review_insufficient(Q3)",
        "pass_through",
    ],
    "reason_order": ["Q1", "Q2"],
    "no_probability_aggregation": True,
}
JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V2 = digest_json(POLICY_DEFINITION_V2)


@dataclass(frozen=True, slots=True)
class TypeSafeDispositionV2:
    disposition: str
    reason_codes: tuple[str, ...]
    uncertainty_reason: str | None
    gate_results: dict[str, bool]


def _threshold(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("JEV_TYPESAFE_THRESHOLD_INVALID")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError("JEV_TYPESAFE_THRESHOLD_INVALID")
    return number


def validate_v2_thresholds(
    strategy: Any,
    entry: Any,
    evidence: Any,
) -> tuple[float, float, float]:
    return (_threshold(strategy), _threshold(entry), _threshold(evidence))


def decide_typesafe_disposition_v2(
    probabilities: dict[str, Any],
    *,
    threshold_strategy: float,
    threshold_entry: float,
    threshold_evidence: float,
) -> TypeSafeDispositionV2:
    strategy_t, entry_t, evidence_t = validate_v2_thresholds(
        threshold_strategy,
        threshold_entry,
        threshold_evidence,
    )
    required = (
        STRATEGY_CONTEXT_CONFLICT,
        ENTRY_CONTEXT_CONFLICT,
        OVERALL_SEMANTIC_REVIEW_INSUFFICIENT,
    )
    if set(probabilities) != set(required):
        raise ValueError("JEV_TYPESAFE_PROBABILITY_SET_INVALID")

    values: dict[str, float] = {}
    for key in required:
        raw = probabilities.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError("JEV_TYPESAFE_PROBABILITY_INVALID")
        value = float(raw)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("JEV_TYPESAFE_PROBABILITY_INVALID")
        values[key] = value

    gates = {
        STRATEGY_CONTEXT_CONFLICT: (
            values[STRATEGY_CONTEXT_CONFLICT] >= strategy_t
        ),
        ENTRY_CONTEXT_CONFLICT: (
            values[ENTRY_CONTEXT_CONFLICT] >= entry_t
        ),
        OVERALL_SEMANTIC_REVIEW_INSUFFICIENT: (
            values[OVERALL_SEMANTIC_REVIEW_INSUFFICIENT] >= evidence_t
        ),
    }

    reasons: list[str] = []
    if gates[STRATEGY_CONTEXT_CONFLICT]:
        reasons.append("STRATEGY_CONTEXT_CONFLICT")
    if gates[ENTRY_CONTEXT_CONFLICT]:
        reasons.append("ENTRY_CONTEXT_CONFLICT")
    if reasons:
        return TypeSafeDispositionV2(
            "REVIEW_REQUIRED",
            tuple(reasons),
            None,
            gates,
        )

    if gates[OVERALL_SEMANTIC_REVIEW_INSUFFICIENT]:
        return TypeSafeDispositionV2(
            "ABSTAIN",
            (),
            "EVIDENCE_INSUFFICIENT",
            gates,
        )

    return TypeSafeDispositionV2(
        "PASS_THROUGH",
        ("NO_ADDITIONAL_CONTEXT_CONFLICT",),
        None,
        gates,
    )
