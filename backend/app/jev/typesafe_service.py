from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .typesafe_policy import decide_typesafe_disposition
from .typesafe_provider import TypeSafeJevProvider, validate_system_one_response
from .typesafe_questions import build_typesafe_questions
from .typesafe_state import TypeSafeStateProjection, project_typesafe_state


@dataclass(frozen=True, slots=True)
class TypeSafeCoreReview:
    projection: TypeSafeStateProjection
    request: dict[str, Any]
    normalized_response: dict[str, Any]
    disposition: str
    reason_codes: tuple[str, ...]
    uncertainty_reason: str | None
    bands: dict[str, str]
    cost_usd: float | None
    cost_unknown: bool


class TypeSafeCoreQueueError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def build_system_one_request(
    sample: dict[str, Any],
    protocol_spec: dict[str, Any],
) -> tuple[dict[str, Any], TypeSafeStateProjection]:
    projection = project_typesafe_state(sample)
    model = str(protocol_spec.get("model_requested") or "").strip()
    if not model or model.upper() == "UNFROZEN":
        raise ValueError("TYPESAFE_MODEL_REQUIRED")
    return {
        "state": projection.state,
        "questions": build_typesafe_questions(),
        "model": model,
    }, projection


async def review_once(
    sample: dict[str, Any],
    protocol_spec: dict[str, Any],
    provider: TypeSafeJevProvider,
) -> TypeSafeCoreReview:
    request, projection = build_system_one_request(sample, protocol_spec)
    result = await provider.review(
        request,
        deadline_seconds=float(protocol_spec.get("deadline_seconds") or 12.0),
    )
    normalized = validate_system_one_response(
        result.raw_response,
        expected_model_returned=str(
            protocol_spec.get("expected_model_returned") or ""
        ),
    )
    decision = decide_typesafe_disposition(
        normalized["probabilities"],
        threshold_low=float(protocol_spec["threshold_low"]),
        threshold_high=float(protocol_spec["threshold_high"]),
    )
    return TypeSafeCoreReview(
        projection=projection,
        request=request,
        normalized_response=normalized,
        disposition=decision.disposition,
        reason_codes=decision.reason_codes,
        uncertainty_reason=decision.uncertainty_reason,
        bands=decision.bands,
        cost_usd=result.cost_usd,
        cost_unknown=result.cost_unknown,
    )


class TypeSafeCoreQueue:
    """Bounded, retry-free core executor.

    This is intentionally not connected to Scanner yet. The next integration phase
    can hand recruited V2 units to this queue without changing the provider/question
    contracts frozen by TYPE-JEV-DESIGN-FREEZE.
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
                # Phase 1 retry count is fixed to zero: exactly one provider attempt.
                return await review_once(sample, protocol_spec, provider)
        finally:
            async with self._lock:
                self._active -= 1
