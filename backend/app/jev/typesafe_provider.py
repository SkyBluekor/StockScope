from __future__ import annotations

import asyncio
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from dotenv import dotenv_values

from app.core.config import PROJECT_ROOT

from .typesafe_models import JEV_TYPESAFE_PROVIDER_ID
from .typesafe_questions import JEV_TYPESAFE_QUESTION_IDS


TYPESAFE_SYSTEM_ONE_URL = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_MODELS_URL = "https://api.typesafe.ai/v1/models"


class TypeSafeJevProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TypeSafeProviderResult:
    raw_response: dict[str, Any]
    usage: dict[str, int]
    cost_usd: float | None
    cost_unknown: bool


class TypeSafeJevProvider(Protocol):
    async def review(
        self,
        request: dict[str, Any],
        *,
        deadline_seconds: float,
    ) -> TypeSafeProviderResult:
        ...


def load_typesafe_jev_api_key() -> str | None:
    raw = (os.getenv("JEV_API_KEY") or "").strip()
    if raw:
        return raw
    value = str(
        dotenv_values(PROJECT_ROOT / ".env").get("JEV_API_KEY") or ""
    ).strip()
    return value or None


async def discover_typesafe_models(
    *,
    deadline_seconds: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[dict[str, str]]:
    api_key = load_typesafe_jev_api_key()
    if not api_key:
        raise TypeSafeJevProviderError("JEV_API_KEY_MISSING")
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = httpx.Timeout(max(0.1, float(deadline_seconds)))
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
        ) as client:
            response = await client.get(
                TYPESAFE_MODELS_URL,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        raise TypeSafeJevProviderError("TYPESAFE_MODELS_TIMEOUT") from exc
    except httpx.HTTPError as exc:
        raise TypeSafeJevProviderError("TYPESAFE_MODELS_NETWORK_ERROR") from exc

    if response.status_code == 401:
        raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_AUTH_ERROR")
    if response.status_code == 429:
        raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_RATE_LIMIT")
    if response.status_code >= 500:
        raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_UNAVAILABLE")
    if response.status_code >= 400:
        raise TypeSafeJevProviderError("TYPESAFE_MODELS_REQUEST_REJECTED")
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise TypeSafeJevProviderError("TYPESAFE_MODELS_INVALID_JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise TypeSafeJevProviderError("TYPESAFE_MODELS_RESPONSE_INVALID")

    models: list[dict[str, str]] = []
    for item in payload["models"]:
        if not isinstance(item, dict):
            raise TypeSafeJevProviderError("TYPESAFE_MODEL_METADATA_INVALID")
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        release_date = str(item.get("release_date") or "").strip()
        if not name or not description or not release_date:
            raise TypeSafeJevProviderError("TYPESAFE_MODEL_METADATA_INVALID")
        models.append(
            {
                "name": name,
                "description": description,
                "release_date": release_date,
            }
        )
    if not models:
        raise TypeSafeJevProviderError("TYPESAFE_MODELS_EMPTY")
    return models


def _token_count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeSafeJevProviderError(f"TYPESAFE_USAGE_{field.upper()}_INVALID")
    return int(value)


def validate_system_one_response(
    payload: Any,
    *,
    expected_model_returned: str | None = None,
    expected_question_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeSafeJevProviderError("TYPESAFE_RESPONSE_INVALID")
    model = str(payload.get("model") or "").strip()
    if not model:
        raise TypeSafeJevProviderError("TYPESAFE_MODEL_MISSING")
    expected = str(expected_model_returned or "").strip()
    if expected and expected.upper() != "UNFROZEN" and model != expected:
        raise TypeSafeJevProviderError("TYPESAFE_MODEL_IDENTITY_CHANGED")
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise TypeSafeJevProviderError("TYPESAFE_ANSWERS_MISSING")
    question_ids = tuple(expected_question_ids or JEV_TYPESAFE_QUESTION_IDS)
    if not question_ids or len(set(question_ids)) != len(question_ids):
        raise TypeSafeJevProviderError("TYPESAFE_QUESTION_SET_INVALID")
    if set(answers) != set(question_ids):
        raise TypeSafeJevProviderError("TYPESAFE_ANSWER_SET_MISMATCH")

    probabilities: dict[str, float] = {}
    normalized_answers: dict[str, dict[str, Any]] = {}
    for question_id in question_ids:
        answer = answers.get(question_id)
        if not isinstance(answer, dict) or answer.get("type") != "noul":
            raise TypeSafeJevProviderError("TYPESAFE_ANSWER_TYPE_INVALID")
        raw_probability = answer.get("noul")
        if isinstance(raw_probability, bool) or not isinstance(
            raw_probability, (int, float)
        ):
            raise TypeSafeJevProviderError("TYPESAFE_PROBABILITY_INVALID")
        probability = float(raw_probability)
        if not math.isfinite(probability) or not (0.0 <= probability <= 1.0):
            raise TypeSafeJevProviderError("TYPESAFE_PROBABILITY_INVALID")
        probabilities[question_id] = probability
        normalized_answers[question_id] = {"type": "noul", "noul": probability}

    usage_raw = payload.get("usage")
    if not isinstance(usage_raw, dict):
        raise TypeSafeJevProviderError("TYPESAFE_USAGE_MISSING")
    usage = {
        "input_tokens": _token_count(usage_raw.get("input_tokens"), "input_tokens"),
        "output_tokens": _token_count(usage_raw.get("output_tokens"), "output_tokens"),
    }
    return {
        "model": model,
        "answers": normalized_answers,
        "probabilities": probabilities,
        "usage": usage,
    }


class TypeSafeSystemOneProvider:
    def __init__(
        self,
        *,
        model_id: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        clean = model_id.strip()
        if not clean:
            raise TypeSafeJevProviderError("TYPESAFE_MODEL_REQUIRED")
        self.model_id = clean
        self.transport = transport

    async def review(
        self,
        request: dict[str, Any],
        *,
        deadline_seconds: float,
    ) -> TypeSafeProviderResult:
        api_key = load_typesafe_jev_api_key()
        if not api_key:
            raise TypeSafeJevProviderError("JEV_API_KEY_MISSING")
        body = {
            "state": request.get("state"),
            "questions": request.get("questions"),
            "model": self.model_id,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(max(0.1, float(deadline_seconds)))
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
                response = await client.post(
                    TYPESAFE_SYSTEM_ONE_URL,
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_NETWORK_ERROR") from exc

        if response.status_code == 401:
            raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_AUTH_ERROR")
        if response.status_code == 422:
            raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_REQUEST_REJECTED")
        if response.status_code == 429:
            raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_RATE_LIMIT")
        if response.status_code == 529 or response.status_code >= 500:
            raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_UNAVAILABLE")
        if response.status_code >= 400:
            raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_REQUEST_REJECTED")
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise TypeSafeJevProviderError("TYPESAFE_RESPONSE_INVALID_JSON") from exc
        questions = request.get("questions")
        question_ids = (
            tuple(questions)
            if isinstance(questions, dict) and questions
            else JEV_TYPESAFE_QUESTION_IDS
        )
        normalized = validate_system_one_response(
            payload,
            expected_question_ids=question_ids,
        )
        return TypeSafeProviderResult(
            raw_response=dict(payload),
            usage=dict(normalized["usage"]),
            cost_usd=None,
            cost_unknown=True,
        )


class FakeTypeSafeJevProvider:
    def __init__(
        self,
        *,
        probabilities: dict[str, float] | None = None,
        returned_model: str = "FAKE-JEV-V2",
        delay_seconds: float = 0.0,
        mode: str = "VALID",
    ) -> None:
        self.probabilities = dict(
            probabilities
            or {
                "strategy_context_conflict": 0.05,
                "entry_context_conflict": 0.05,
                "review_evidence_insufficient": 0.05,
            }
        )
        self.returned_model = returned_model
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.mode = mode.strip().upper()

    async def review(
        self,
        request: dict[str, Any],
        *,
        deadline_seconds: float,
    ) -> TypeSafeProviderResult:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.mode == "ERROR":
            raise TypeSafeJevProviderError("FAKE_TYPESAFE_PROVIDER_ERROR")
        if self.mode == "MALFORMED":
            return TypeSafeProviderResult(
                raw_response={"model": self.returned_model},
                usage={"input_tokens": 0, "output_tokens": 0},
                cost_usd=0.0,
                cost_unknown=False,
            )
        questions = request.get("questions")
        question_ids = (
            tuple(questions)
            if isinstance(questions, dict) and questions
            else JEV_TYPESAFE_QUESTION_IDS
        )
        payload = {
            "model": self.returned_model,
            "answers": {
                question_id: {
                    "type": "noul",
                    "noul": self.probabilities.get(question_id, 0.05),
                }
                for question_id in question_ids
            },
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        normalized = validate_system_one_response(
            payload,
            expected_question_ids=question_ids,
        )
        return TypeSafeProviderResult(
            raw_response=payload,
            usage=dict(normalized["usage"]),
            cost_usd=0.0,
            cost_unknown=False,
        )


def provider_from_typesafe_spec(
    spec: dict[str, Any],
    *,
    allow_network: bool,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TypeSafeJevProvider:
    provider_id = str(spec.get("provider_id") or "").strip().upper()
    if provider_id == "FAKE":
        extra = spec.get("extra")
        extra = dict(extra) if isinstance(extra, dict) else {}
        return FakeTypeSafeJevProvider(
            probabilities=extra.get("fake_probabilities"),
            returned_model=str(
                extra.get("fake_returned_model")
                or spec.get("expected_model_returned")
                or "FAKE-JEV-V2"
            ),
        )
    if provider_id != JEV_TYPESAFE_PROVIDER_ID:
        raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_UNSUPPORTED")
    if not allow_network:
        raise TypeSafeJevProviderError("JEV_NETWORK_NOT_AUTHORIZED")
    if not bool(spec.get("source_transmission_approved")):
        raise TypeSafeJevProviderError("JEV_SOURCE_TRANSMISSION_NOT_APPROVED")
    model_id = str(spec.get("model_requested") or "").strip()
    if not model_id or model_id.upper() == "UNFROZEN":
        raise TypeSafeJevProviderError("TYPESAFE_MODEL_REQUIRED")
    return TypeSafeSystemOneProvider(model_id=model_id, transport=transport)
