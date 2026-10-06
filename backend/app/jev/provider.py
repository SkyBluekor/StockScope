from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from dotenv import dotenv_values

from app.core.config import PROJECT_ROOT

from .models import JEV_REASON_CODES, canonical_json
from .prompt import (
    JEV_OUTPUT_JSON_SCHEMA,
    JEV_OUTPUT_SCHEMA_HASH,
    JEV_PROMPT_HASH,
    JEV_PROMPT_VERSION,
    JEV_SYSTEM_PROMPT,
)


OPENAI_RESPONSES_PROVIDER_ID = "OPENAI_RESPONSES"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_TERRA_MODEL_ID = "gpt-5.6-terra"

# Frozen 2026-10-06 public list prices for GPT-5.6 Terra.
OPENAI_TERRA_INPUT_USD_PER_M = 2.00
OPENAI_TERRA_CACHED_INPUT_USD_PER_M = 0.20
OPENAI_TERRA_OUTPUT_USD_PER_M = 12.00


class JevProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProviderResult:
    raw_response: Any
    usage: dict[str, Any] | None = None
    cost_usd: float | None = None


class JevProvider(Protocol):
    async def review(
        self,
        request: dict[str, Any],
        *,
        deadline_seconds: float,
    ) -> ProviderResult:
        ...


def load_jev_api_key() -> str | None:
    raw = (os.getenv("JEV_API_KEY") or "").strip()
    if raw:
        return raw
    value = str(
        dotenv_values(PROJECT_ROOT / ".env").get("JEV_API_KEY") or ""
    ).strip()
    return value or None


def _openai_cost_usd(usage: dict[str, Any]) -> float | None:
    try:
        input_tokens = max(0, int(usage.get("input_tokens") or 0))
        output_tokens = max(0, int(usage.get("output_tokens") or 0))
        details = usage.get("input_tokens_details")
        cached_tokens = (
            max(0, int(details.get("cached_tokens") or 0))
            if isinstance(details, dict)
            else 0
        )
        cached_tokens = min(input_tokens, cached_tokens)
        uncached_tokens = input_tokens - cached_tokens
        return (
            uncached_tokens * OPENAI_TERRA_INPUT_USD_PER_M
            + cached_tokens * OPENAI_TERRA_CACHED_INPUT_USD_PER_M
            + output_tokens * OPENAI_TERRA_OUTPUT_USD_PER_M
        ) / 1_000_000.0
    except (TypeError, ValueError):
        return None


def _response_output_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    output = payload.get("output")
    if not isinstance(output, list):
        raise JevProviderError("PROVIDER_OUTPUT_MISSING")

    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise JevProviderError("PROVIDER_REFUSAL")
            if part.get("type") == "output_text":
                text = str(part.get("text") or "").strip()
                if text:
                    parts.append(text)
    if not parts:
        raise JevProviderError("PROVIDER_OUTPUT_MISSING")
    return "\n".join(parts)


class OpenAIResponsesJevProvider:
    def __init__(
        self,
        *,
        model_id: str,
        reasoning_effort: str = "low",
        max_output_tokens: int = 1200,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model_id = model_id.strip()
        self.reasoning_effort = reasoning_effort.strip() or "low"
        self.max_output_tokens = max(256, int(max_output_tokens))
        self.transport = transport

    async def review(
        self,
        request: dict[str, Any],
        *,
        deadline_seconds: float,
    ) -> ProviderResult:
        api_key = load_jev_api_key()
        if not api_key:
            raise JevProviderError("JEV_API_KEY_MISSING")

        body = {
            "model": self.model_id,
            "instructions": JEV_SYSTEM_PROMPT,
            "input": canonical_json(request),
            "store": False,
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": self.max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "jev_decision_review_v1",
                    "strict": True,
                    "schema": JEV_OUTPUT_JSON_SCHEMA,
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(max(0.1, float(deadline_seconds)))
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    OPENAI_RESPONSES_URL,
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise JevProviderError("PROVIDER_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise JevProviderError("PROVIDER_NETWORK_ERROR") from exc

        if response.status_code == 401:
            raise JevProviderError("PROVIDER_AUTH_ERROR")
        if response.status_code == 429:
            raise JevProviderError("PROVIDER_RATE_LIMIT")
        if response.status_code >= 500:
            raise JevProviderError("PROVIDER_UNAVAILABLE")
        if response.status_code >= 400:
            raise JevProviderError("PROVIDER_REQUEST_REJECTED")

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise JevProviderError("PROVIDER_RESPONSE_INVALID_JSON") from exc
        if not isinstance(payload, dict):
            raise JevProviderError("PROVIDER_RESPONSE_INVALID_JSON")
        if str(payload.get("status") or "") != "completed":
            raise JevProviderError("PROVIDER_RESPONSE_INCOMPLETE")

        output_text = _response_output_text(payload)
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise JevProviderError("PROVIDER_OUTPUT_INVALID_JSON") from exc

        usage_raw = payload.get("usage")
        usage = dict(usage_raw) if isinstance(usage_raw, dict) else {}
        usage.update(
            {
                "provider": OPENAI_RESPONSES_PROVIDER_ID,
                "served_model": str(payload.get("model") or ""),
                "response_id": str(payload.get("id") or ""),
                "prompt_version": JEV_PROMPT_VERSION,
                "prompt_hash": JEV_PROMPT_HASH,
                "output_schema_hash": JEV_OUTPUT_SCHEMA_HASH,
                "store": False,
            }
        )
        return ProviderResult(
            raw_response=parsed,
            usage=usage,
            cost_usd=_openai_cost_usd(usage),
        )


class FakeJevProvider:
    """Deterministic provider for contract/fallback tests only."""

    def __init__(
        self,
        *,
        mode: str = "PASS_THROUGH",
        delay_seconds: float = 0.0,
    ) -> None:
        self.mode = mode.strip().upper()
        self.delay_seconds = max(0.0, float(delay_seconds))

    async def review(
        self,
        request: dict[str, Any],
        *,
        deadline_seconds: float,
    ) -> ProviderResult:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)

        if self.mode == "PROVIDER_ERROR":
            raise JevProviderError("FAKE_PROVIDER_ERROR")
        if self.mode == "MALFORMED":
            return ProviderResult(
                raw_response=["not", "an", "object"],
                cost_usd=0.0,
            )

        evidence = request.get("evidence_items") or []
        evidence_id = (
            str(evidence[0].get("evidence_id"))
            if evidence and isinstance(evidence[0], dict)
            else "missing"
        )
        reason = {
            "code": "CONDITION_ALIGNMENT",
            "evidence_refs": [evidence_id],
            "explanation": "Deterministic fake-provider reason.",
        }

        if self.mode == "UNKNOWN_EVIDENCE":
            reason["evidence_refs"] = ["UNKNOWN-EVIDENCE"]
        if self.mode == "INVALID_REASON_CODE":
            reason["code"] = "NOT_ALLOWED"
        if self.mode == "INVALID_ENUM":
            decision = "BUY_NOW"
        elif self.mode == "REVIEW_REQUIRED":
            decision = "REVIEW_REQUIRED"
        elif self.mode == "ABSTAIN":
            decision = "ABSTAIN"
        else:
            decision = "PASS_THROUGH"

        if decision == "ABSTAIN":
            payload = {
                "decision": "ABSTAIN",
                "abstain_reason": "INSUFFICIENT_EVIDENCE",
                "supporting_reasons": [],
                "opposing_reasons": [],
            }
        elif decision == "REVIEW_REQUIRED":
            opposing = dict(reason)
            opposing["code"] = (
                reason["code"]
                if reason["code"] not in JEV_REASON_CODES
                else "CONDITION_CONFLICT"
            )
            payload = {
                "decision": decision,
                "abstain_reason": None,
                "supporting_reasons": [],
                "opposing_reasons": [opposing],
            }
        else:
            payload = {
                "decision": decision,
                "abstain_reason": None,
                "supporting_reasons": [reason],
                "opposing_reasons": [],
            }

        return ProviderResult(
            raw_response=payload,
            usage={
                "input_units": 0,
                "output_units": 0,
                "provider": "FAKE",
            },
            cost_usd=0.0,
        )


def provider_from_protocol(
    spec: dict[str, Any],
    *,
    allow_network: bool,
) -> JevProvider:
    provider_id = str(spec.get("provider_id") or "").strip().upper()
    if provider_id == "FAKE":
        settings = dict(spec.get("generation_settings") or {})
        return FakeJevProvider(
            mode=str(settings.get("fake_mode") or "PASS_THROUGH"),
            delay_seconds=float(
                settings.get("fake_delay_seconds") or 0.0
            ),
        )

    if not allow_network:
        raise JevProviderError("JEV_NETWORK_NOT_AUTHORIZED")
    if not bool(spec.get("source_transmission_approved")):
        raise JevProviderError("JEV_SOURCE_TRANSMISSION_NOT_APPROVED")
    if provider_id != OPENAI_RESPONSES_PROVIDER_ID:
        raise JevProviderError("JEV_PROVIDER_UNSUPPORTED")
    if str(spec.get("model_id") or "") != OPENAI_TERRA_MODEL_ID:
        raise JevProviderError("JEV_MODEL_ID_MISMATCH")
    if str(spec.get("prompt_version") or "") != JEV_PROMPT_VERSION:
        raise JevProviderError("JEV_PROMPT_VERSION_MISMATCH")
    if str(spec.get("prompt_hash") or "") != JEV_PROMPT_HASH:
        raise JevProviderError("JEV_PROMPT_HASH_MISMATCH")

    settings = dict(spec.get("generation_settings") or {})
    if settings.get("store") is not False:
        raise JevProviderError("JEV_PROVIDER_STORE_MUST_BE_FALSE")
    if (
        str(settings.get("structured_output_schema_hash") or "")
        != JEV_OUTPUT_SCHEMA_HASH
    ):
        raise JevProviderError("JEV_OUTPUT_SCHEMA_HASH_MISMATCH")

    return OpenAIResponsesJevProvider(
        model_id=OPENAI_TERRA_MODEL_ID,
        reasoning_effort=str(
            settings.get("reasoning_effort") or "low"
        ),
        max_output_tokens=int(
            settings.get("max_output_tokens") or 1200
        ),
    )
