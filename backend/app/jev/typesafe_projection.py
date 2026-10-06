from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .typesafe_models import (
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V1,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V1,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
)
from .typesafe_policy import decide_typesafe_disposition
from .typesafe_policy_v2 import decide_typesafe_disposition_v2
from .typesafe_questions import JEV_TYPESAFE_QUESTION_IDS
from .typesafe_questions_v2 import JEV_TYPESAFE_QUESTION_IDS_V2


@dataclass(frozen=True, slots=True)
class TypeSafeReviewProjection:
    operational_status: str
    disposition: str | None
    reason_codes: tuple[str, ...]
    uncertainty_reason: str | None
    failure_code: str | None
    integrity_status: str
    bands: dict[str, str]
    gate_results: dict[str, bool]


def _family(review: dict[str, Any], protocol_spec: dict[str, Any]) -> str:
    question_version = str(
        review.get("question_contract_version")
        or protocol_spec.get("question_contract_version")
        or JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V1
    )
    policy_version = str(
        review.get("disposition_policy_version")
        or protocol_spec.get("disposition_policy_version")
        or JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V1
    )
    if (
        question_version == JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V1
        and policy_version == JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V1
    ):
        return "V1"
    if (
        question_version == JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2
        and policy_version == JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2
    ):
        return "V2"
    raise ValueError("JEV_TYPESAFE_CONTRACT_VERSION_MISMATCH")


def _probabilities(
    typed_answers: Any,
    question_ids: tuple[str, ...],
) -> dict[str, float]:
    if not isinstance(typed_answers, dict):
        raise ValueError("TYPED_ANSWER_INTEGRITY_ERROR")
    if set(typed_answers) != set(question_ids):
        raise ValueError("TYPED_ANSWER_INTEGRITY_ERROR")
    probabilities: dict[str, float] = {}
    for question_id in question_ids:
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


def _error(
    *,
    status: str,
    failure_code: str | None,
    integrity_status: str,
    bands: dict[str, str] | None = None,
    gate_results: dict[str, bool] | None = None,
) -> TypeSafeReviewProjection:
    return TypeSafeReviewProjection(
        operational_status=status,
        disposition=None,
        reason_codes=(),
        uncertainty_reason=None,
        failure_code=failure_code,
        integrity_status=integrity_status,
        bands=dict(bands or {}),
        gate_results=dict(gate_results or {}),
    )


def project_typesafe_review(
    review: dict[str, Any],
    protocol_spec: dict[str, Any],
) -> TypeSafeReviewProjection:
    status = str(review.get("status") or "").upper()
    stored_disposition = review.get("disposition")

    if status != "VALID":
        return _error(
            status=status or "ERROR",
            failure_code=(
                str(review.get("failure_code"))
                if review.get("failure_code") is not None
                else None
            ),
            integrity_status="NOT_APPLICABLE",
        )

    if str(review.get("model_identity_status") or "") != "MATCHED":
        return _error(
            status="ERROR",
            failure_code="MODEL_IDENTITY_UNVERIFIED",
            integrity_status="MISMATCH",
        )

    try:
        family = _family(review, protocol_spec)
        if family == "V2":
            required_thresholds = (
                protocol_spec.get("threshold_strategy"),
                protocol_spec.get("threshold_entry"),
                protocol_spec.get("threshold_evidence"),
            )
            if any(value is None for value in required_thresholds):
                return _error(
                    status="ERROR",
                    failure_code="DISPOSITION_POLICY_UNFROZEN",
                    integrity_status="MISMATCH",
                )
            probabilities = _probabilities(
                review.get("typed_answers"),
                JEV_TYPESAFE_QUESTION_IDS_V2,
            )
            decision = decide_typesafe_disposition_v2(
                probabilities,
                threshold_strategy=required_thresholds[0],
                threshold_entry=required_thresholds[1],
                threshold_evidence=required_thresholds[2],
            )
            bands: dict[str, str] = {}
            gate_results = dict(decision.gate_results)
        else:
            low = protocol_spec.get("threshold_low")
            high = protocol_spec.get("threshold_high")
            if low is None or high is None:
                return _error(
                    status="ERROR",
                    failure_code="DISPOSITION_POLICY_UNFROZEN",
                    integrity_status="MISMATCH",
                )
            probabilities = _probabilities(
                review.get("typed_answers"),
                JEV_TYPESAFE_QUESTION_IDS,
            )
            decision = decide_typesafe_disposition(
                probabilities,
                threshold_low=float(low),
                threshold_high=float(high),
            )
            bands = dict(decision.bands)
            gate_results = {}
    except (TypeError, ValueError):
        return _error(
            status="ERROR",
            failure_code="TYPED_ANSWER_INTEGRITY_ERROR",
            integrity_status="MISMATCH",
        )

    if stored_disposition != decision.disposition:
        return _error(
            status="ERROR",
            failure_code="DISPOSITION_INTEGRITY_MISMATCH",
            integrity_status="MISMATCH",
            bands=bands,
            gate_results=gate_results,
        )

    return TypeSafeReviewProjection(
        operational_status="VALID",
        disposition=decision.disposition,
        reason_codes=decision.reason_codes,
        uncertainty_reason=decision.uncertainty_reason,
        failure_code=None,
        integrity_status="MATCHED",
        bands=bands,
        gate_results=gate_results,
    )
