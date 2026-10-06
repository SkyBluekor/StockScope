from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import digest_json
from .typesafe_models import JEV_TYPESAFE_DISPOSITION_POLICY_VERSION
from .typesafe_questions import (
    ENTRY_CONTEXT_CONFLICT,
    REVIEW_EVIDENCE_INSUFFICIENT,
    STRATEGY_CONTEXT_CONFLICT,
)


POLICY_DEFINITION = {
    "version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION,
    "threshold_slots": ["threshold_low", "threshold_high"],
    "bands": {"LOW": "p <= L", "GRAY": "L < p < H", "HIGH": "p >= H"},
    "no_probability_aggregation": True,
}
JEV_TYPESAFE_DISPOSITION_POLICY_HASH = digest_json(POLICY_DEFINITION)


@dataclass(frozen=True, slots=True)
class TypeSafeDisposition:
    disposition: str
    reason_codes: tuple[str, ...]
    uncertainty_reason: str | None
    bands: dict[str, str]


def validate_thresholds(low: float, high: float) -> tuple[float, float]:
    low_f = float(low)
    high_f = float(high)
    if not (0.0 <= low_f < 0.5 < high_f <= 1.0):
        raise ValueError("JEV_TYPESAFE_THRESHOLD_INVALID")
    return low_f, high_f


def _band(value: float, low: float, high: float) -> str:
    if value <= low:
        return "LOW"
    if value >= high:
        return "HIGH"
    return "GRAY"


def decide_typesafe_disposition(
    probabilities: dict[str, Any],
    *,
    threshold_low: float,
    threshold_high: float,
) -> TypeSafeDisposition:
    low, high = validate_thresholds(threshold_low, threshold_high)
    required = (
        STRATEGY_CONTEXT_CONFLICT,
        ENTRY_CONTEXT_CONFLICT,
        REVIEW_EVIDENCE_INSUFFICIENT,
    )
    values: dict[str, float] = {}
    for key in required:
        raw = probabilities.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError("JEV_TYPESAFE_PROBABILITY_INVALID")
        value = float(raw)
        if value != value or not (0.0 <= value <= 1.0):
            raise ValueError("JEV_TYPESAFE_PROBABILITY_INVALID")
        values[key] = value

    bands = {key: _band(value, low, high) for key, value in values.items()}
    evidence_band = bands[REVIEW_EVIDENCE_INSUFFICIENT]
    if evidence_band == "HIGH":
        return TypeSafeDisposition("ABSTAIN", (), "EVIDENCE_INSUFFICIENT", bands)
    if evidence_band == "GRAY":
        return TypeSafeDisposition("ABSTAIN", (), "MODEL_UNCERTAIN", bands)

    positive: list[tuple[str, float, int]] = []
    ordered = (
        (STRATEGY_CONTEXT_CONFLICT, "STRATEGY_CONTEXT_CONFLICT", 0),
        (ENTRY_CONTEXT_CONFLICT, "ENTRY_CONTEXT_CONFLICT", 1),
    )
    for question_id, reason_code, order in ordered:
        if bands[question_id] == "HIGH":
            positive.append((reason_code, values[question_id], order))
    if positive:
        positive.sort(key=lambda item: (-item[1], item[2]))
        return TypeSafeDisposition(
            "REVIEW_REQUIRED",
            tuple(item[0] for item in positive[:2]),
            None,
            bands,
        )
    if all(bands[key] == "LOW" for key in required):
        return TypeSafeDisposition(
            "PASS_THROUGH",
            ("NO_ADDITIONAL_CONTEXT_CONFLICT",),
            None,
            bands,
        )
    return TypeSafeDisposition("ABSTAIN", (), "MODEL_UNCERTAIN", bands)
