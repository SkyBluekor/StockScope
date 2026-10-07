from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .models import digest_json
from .typesafe_models import JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4
from .typesafe_questions_v4 import STRATEGY_RELATION_CONFLICT


POLICY_DEFINITION_V4 = {
    "version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
    "threshold_slots": ["threshold_strategy"],
    "gate": "p(strategy_relation_conflict) >= T_strategy",
    "precedence": ["strategy_relation_conflict", "pass_through"],
    "semantic_insufficiency_owner": "LOCAL_PRECALL_READINESS",
    "local_terminal_states_call_provider": False,
    "no_probability_aggregation": True,
}
JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V4 = digest_json(POLICY_DEFINITION_V4)


@dataclass(frozen=True, slots=True)
class TypeSafeDispositionV4:
    disposition: str
    reason_codes: tuple[str, ...]
    uncertainty_reason: str | None
    gate_results: dict[str, bool]


def _probability(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("JEV_TYPESAFE_PROBABILITY_INVALID")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError("JEV_TYPESAFE_PROBABILITY_INVALID")
    return number


def _threshold(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("JEV_TYPESAFE_THRESHOLD_INVALID")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError("JEV_TYPESAFE_THRESHOLD_INVALID")
    return number


def decide_typesafe_disposition_v4(
    probabilities: dict[str, Any],
    *,
    threshold_strategy: float,
) -> TypeSafeDispositionV4:
    if set(probabilities) != {STRATEGY_RELATION_CONFLICT}:
        raise ValueError("JEV_TYPESAFE_PROBABILITY_SET_INVALID")

    value = _probability(probabilities[STRATEGY_RELATION_CONFLICT])
    threshold = _threshold(threshold_strategy)
    conflict = value >= threshold
    gates = {STRATEGY_RELATION_CONFLICT: conflict}

    if conflict:
        return TypeSafeDispositionV4(
            disposition="REVIEW_REQUIRED",
            reason_codes=("STRATEGY_RELATION_CONFLICT",),
            uncertainty_reason=None,
            gate_results=gates,
        )
    return TypeSafeDispositionV4(
        disposition="PASS_THROUGH",
        reason_codes=("NO_ADDITIONAL_RELATION_CONFLICT",),
        uncertainty_reason=None,
        gate_results=gates,
    )
