from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .typesafe_models import (
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V1,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V3,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V1,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
)
from .typesafe_policy import decide_typesafe_disposition
from .typesafe_policy_v2 import decide_typesafe_disposition_v2
from .typesafe_policy_v3 import decide_typesafe_disposition_v3
from .typesafe_policy_v4 import decide_typesafe_disposition_v4
from .typesafe_provider import TypeSafeJevProvider, validate_system_one_response
from .typesafe_questions import JEV_TYPESAFE_QUESTION_IDS, build_typesafe_questions
from .typesafe_questions_v2 import (
    JEV_TYPESAFE_QUESTION_IDS_V2,
    build_typesafe_questions_v2,
)
from .typesafe_questions_v3 import (
    JEV_TYPESAFE_QUESTION_IDS_V3,
    build_typesafe_questions_v3,
)
from .typesafe_questions_v4 import (
    JEV_TYPESAFE_QUESTION_IDS_V4,
    build_typesafe_questions_v4,
)
from .typesafe_state import TypeSafeStateProjection, project_typesafe_state
from .typesafe_state_v3 import project_typesafe_state_v3
from .typesafe_state_v4 import project_typesafe_state_v4


@dataclass(frozen=True, slots=True)
class TypeSafeCoreReview:
    projection: TypeSafeStateProjection
    request: dict[str, Any]
    normalized_response: dict[str, Any]
    disposition: str
    reason_codes: tuple[str, ...]
    uncertainty_reason: str | None
    bands: dict[str, str]
    gate_results: dict[str, bool]
    cost_usd: float | None
    cost_unknown: bool


class TypeSafeCoreQueueError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _contract_family(protocol_spec: dict[str, Any]) -> str:
    question_version = str(
        protocol_spec.get("question_contract_version")
        or JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V1
    )
    policy_version = str(
        protocol_spec.get("disposition_policy_version")
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
    if (
        question_version == JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3
        and policy_version == JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V3
    ):
        return "V3"
    if (
        question_version == JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4
        and policy_version == JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4
    ):
        return "V4"
    raise ValueError("JEV_TYPESAFE_CONTRACT_VERSION_MISMATCH")


def build_system_one_request(
    sample: dict[str, Any],
    protocol_spec: dict[str, Any],
) -> tuple[dict[str, Any], TypeSafeStateProjection]:
    family = _contract_family(protocol_spec)
    projection = (
        project_typesafe_state_v4(sample)
        if family == "V4"
        else (
            project_typesafe_state_v3(sample)
            if family == "V3"
            else project_typesafe_state(sample)
        )
    )
    model = str(protocol_spec.get("model_requested") or "").strip()
    if not model or model.upper() == "UNFROZEN":
        raise ValueError("TYPESAFE_MODEL_REQUIRED")
    if family == "V4":
        questions = build_typesafe_questions_v4()
    elif family == "V3":
        questions = build_typesafe_questions_v3()
    elif family == "V2":
        questions = build_typesafe_questions_v2()
    else:
        questions = build_typesafe_questions()
    return {
        "state": projection.state,
        "questions": questions,
        "model": model,
    }, projection


async def review_once(
    sample: dict[str, Any],
    protocol_spec: dict[str, Any],
    provider: TypeSafeJevProvider,
) -> TypeSafeCoreReview:
    request, projection = build_system_one_request(sample, protocol_spec)
    family = _contract_family(protocol_spec)
    result = await provider.review(
        request,
        deadline_seconds=float(protocol_spec.get("deadline_seconds") or 12.0),
    )
    if family == "V4":
        question_ids = JEV_TYPESAFE_QUESTION_IDS_V4
    elif family == "V3":
        question_ids = JEV_TYPESAFE_QUESTION_IDS_V3
    elif family == "V2":
        question_ids = JEV_TYPESAFE_QUESTION_IDS_V2
    else:
        question_ids = JEV_TYPESAFE_QUESTION_IDS
    normalized = validate_system_one_response(
        result.raw_response,
        expected_model_returned=str(
            protocol_spec.get("expected_model_returned") or ""
        ),
        expected_question_ids=question_ids,
    )

    if family == "V4":
        decision = decide_typesafe_disposition_v4(
            normalized["probabilities"],
            threshold_strategy=protocol_spec["threshold_strategy"],
        )
        bands: dict[str, str] = {}
        gate_results = dict(decision.gate_results)
    elif family == "V3":
        decision = decide_typesafe_disposition_v3(
            normalized["probabilities"],
            threshold_strategy=protocol_spec["threshold_strategy"],
        )
        bands: dict[str, str] = {}
        gate_results = dict(decision.gate_results)
    elif family == "V2":
        decision = decide_typesafe_disposition_v2(
            normalized["probabilities"],
            threshold_strategy=protocol_spec["threshold_strategy"],
            threshold_entry=protocol_spec["threshold_entry"],
            threshold_evidence=protocol_spec["threshold_evidence"],
        )
        bands = {}
        gate_results = dict(decision.gate_results)
    else:
        decision = decide_typesafe_disposition(
            normalized["probabilities"],
            threshold_low=float(protocol_spec["threshold_low"]),
            threshold_high=float(protocol_spec["threshold_high"]),
        )
        bands = dict(decision.bands)
        gate_results = {}

    return TypeSafeCoreReview(
        projection=projection,
        request=request,
        normalized_response=normalized,
        disposition=decision.disposition,
        reason_codes=decision.reason_codes,
        uncertainty_reason=decision.uncertainty_reason,
        bands=bands,
        gate_results=gate_results,
        cost_usd=result.cost_usd,
        cost_unknown=result.cost_unknown,
    )


class TypeSafeCoreQueue:
    """Bounded, retry-free core executor.

    This remains disconnected from Scanner activation. A later prospective-trial
    step can hand recruited units to this queue only after the V2 canary and
    trial protocol are separately approved.
    """

    def __init__(self, *, concurrency_cap: int, queue_cap: int) -> None:
        if concurrency_cap <= 0 or queue_cap <= 0:
            raise ValueError("JEV_TYPESAFE_QUEUE_LIMIT_INVALID")
        self._semaphore = asyncio.Semaphore(int(concurrency_cap))
        self._capacity = int(queue_cap)
        self._active = 0
        self._lock = asyncio.Lock()

    async def review(
        self,
        sample: dict[str, Any],
        protocol_spec: dict[str, Any],
        provider: TypeSafeJevProvider,
    ) -> TypeSafeCoreReview:
        async with self._lock:
            if self._active >= self._capacity:
                raise TypeSafeCoreQueueError("QUEUE_CAP_REACHED")
            self._active += 1
        try:
            async with self._semaphore:
                return await review_once(sample, protocol_spec, provider)
        finally:
            async with self._lock:
                self._active -= 1