from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Protocol

from dotenv import dotenv_values

from app.core.config import PROJECT_ROOT

from .models import JEV_REASON_CODES


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
            return ProviderResult(raw_response=["not", "an", "object"], cost_usd=0.0)

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
            usage={"input_units": 0, "output_units": 0, "provider": "FAKE"},
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
            delay_seconds=float(settings.get("fake_delay_seconds") or 0.0),
        )

    if not allow_network:
        raise JevProviderError("JEV_NETWORK_NOT_AUTHORIZED")

    # Real network adapters remain disabled until provider/model/prompt and
    # source-transmission rights are explicitly frozen.
    raise JevProviderError("JEV_REAL_PROVIDER_NOT_FROZEN")
