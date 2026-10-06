from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .typesafe_policy import decide_typesafe_disposition
from .typesafe_questions import JEV_TYPESAFE_QUESTION_IDS


@dataclass(frozen=True, slots=True)
class TypeSafeReviewProjection:
    operational_status: str
    disposition: str | None
    reason_codes: tuple[str, ...]
    uncertainty_reason: str | None
    failure_code: str | None
    integrity_status: str
    bands: dict[str, str]


def _probabilities(typed_answers: Any) -> dict[str, float]:
    if not isinstance(typed_answers, dict):
        raise ValueError("TYPED_ANSWER_INTEGRITY_ERROR")
    probabilities: dict[str, float] = {}
    if set(typed_answers) != set(JEV_TYPESAFE_QUESTION_IDS):
        raise ValueError("TYPED_ANSWER_INTEGRITY_ERROR")
    for question_id in JEV_TYPESAFE_QUESTION_IDS:
        answer = typed_answers.get(question_id)
        if not isinstance(answer, dict) or answer.get("type") != "noul":
            raise ValueError("TYPED_ANSWER_INTEGRITY_ERROR")
        raw = answer.get("noul")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError("TYPED_ANSWER_INTEGRITY_ERROR")
        value = float(raw)
        if value != value or not 0.0 <= value <= 1.0:
            raise ValueError("TYPED_ANSWER_INTEGRITY_ERROR")
        probabilities[question_id] = value
    return probabilities


def project_typesafe_review(
    review: dict[str, Any],
    protocol_spec: dict[str, Any],
) -> TypeSafeReviewProjection:
    status = str(review.get("status") or "").upper()
    stored_disposition = review.get("disposition")

    if status != "VALID":
        return TypeSafeReviewProjection(
            operational_status=status or "ERROR",
            disposition=None,
            reason_codes=(),
            uncertainty_reason=None,
            failure_code=(
                str(review.get("failure_code"))
                if review.get("failure_code") is not None
                else None
            ),
            integrity_status="NOT_APPLICABLE",
            bands={},
        )

    if str(review.get("model_identity_status") or "") != "MATCHED":
        return TypeSafeReviewProjection(
            operational_status="ERROR",
            disposition=None,
            reason_codes=(),
            uncertainty_reason=None,
            failure_code="MODEL_IDENTITY_UNVERIFIED",
            integrity_status="MISMATCH",
            bands={},
        )

    low = protocol_spec.get("threshold_low")
    high = protocol_spec.get("threshold_high")
    if low is None or high is None:
        return TypeSafeReviewProjection(
            operational_status="ERROR",
            disposition=None,
            reason_codes=(),
            uncertainty_reason=None,
            failure_code="DISPOSITION_POLICY_UNFROZEN",
            integrity_status="MISMATCH",
            bands={},
        )

    try:
        probabilities = _probabilities(review.get("typed_answers"))
        decision = decide_typesafe_disposition(
            probabilities,
            threshold_low=float(low),
            threshold_high=float(high),
        )
    except (TypeError, ValueError):
        return TypeSafeReviewProjection(
            operational_status="ERROR",
            disposition=None,
            reason_codes=(),
            uncertainty_reason=None,
            failure_code="TYPED_ANSWER_INTEGRITY_ERROR",
            integrity_status="MISMATCH",
            bands={},
        )

    if stored_disposition != decision.disposition:
        return TypeSafeReviewProjection(
            operational_status="ERROR",
            disposition=None,
            reason_codes=(),
            uncertainty_reason=None,
            failure_code="DISPOSITION_INTEGRITY_MISMATCH",
            integrity_status="MISMATCH",
            bands=decision.bands,
        )

    return TypeSafeReviewProjection(
        operational_status="VALID",
        disposition=decision.disposition,
        reason_codes=decision.reason_codes,
        uncertainty_reason=decision.uncertainty_reason,
        failure_code=None,
        integrity_status="MATCHED",
        bands=decision.bands,
    )
