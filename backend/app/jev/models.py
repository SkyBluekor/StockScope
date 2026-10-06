from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


JEV_SCHEMA_VERSION = "JEV_SHADOW_STORAGE_V1"
JEV_TRIAL_PROTOCOL_VERSION = "JEV_SHADOW_TRIAL_PROTOCOL_V1"
JEV_INPUT_CONTRACT_VERSION = "JEV_SCANNER_REVIEW_INPUT_V1"
JEV_OUTPUT_CONTRACT_VERSION = "JEV_SCANNER_REVIEW_OUTPUT_V1"
JEV_ADAPTER_VERSION = "JEV_SHADOW_ADAPTER_V1"
JEV_COMPARISON_POLICY = "JEV_DEFER_THIS_OPPORTUNITY_V1"
JEV_COMPARISON_REPORT_VERSION = "JEV_SHADOW_COMPARISON_REPORT_V1"

JEV_DECISIONS = frozenset({"PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN"})
JEV_MODEL_ABSTAIN_REASONS = frozenset(
    {
        "INSUFFICIENT_EVIDENCE",
        "CONFLICT_UNRESOLVED",
        "OUT_OF_SCOPE",
        "STALE_INPUT",
    }
)
JEV_REASON_CODES = frozenset(
    {
        "CONDITION_ALIGNMENT",
        "CONDITION_CONFLICT",
        "ENTRY_CONTEXT_CONFLICT",
        "RISK_CAUTION",
        "EVIDENCE_LIMITATION",
    }
)
JEV_REVIEW_TERMINAL_STATUSES = frozenset(
    {"VALID", "ERROR", "LATE", "SKIPPED", "INTERRUPTED"}
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class JevTrialProtocolSpec:
    name: str
    provider_id: str = "UNFROZEN"
    model_id: str = "UNFROZEN"
    model_revision: str = "UNFROZEN"
    prompt_version: str = "UNFROZEN"
    prompt_hash: str = "UNFROZEN"
    generation_settings: dict[str, Any] = field(default_factory=dict)
    market_scope: str = "ALL"
    strategy: str | None = None
    horizon_intents: tuple[str, ...] = ()
    recruitment_start: str | None = None
    recruitment_end: str | None = None
    deadline_seconds: float = 8.0
    min_mature_candidates: int | None = None
    min_disagreements: int | None = None
    max_error_rate: float | None = None
    max_abstain_rate: float | None = None
    budget_limit_usd: float | None = None
    source_transmission_approved: bool = False
    comparison_policy: str = JEV_COMPARISON_POLICY
    input_contract_version: str = JEV_INPUT_CONTRACT_VERSION
    output_contract_version: str = JEV_OUTPUT_CONTRACT_VERSION
    adapter_version: str = JEV_ADAPTER_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["horizon_intents"] = list(self.horizon_intents)
        return payload

    def freeze_gaps(self) -> list[str]:
        missing: list[str] = []
        for name in (
            "provider_id",
            "model_id",
            "model_revision",
            "prompt_version",
            "prompt_hash",
        ):
            value = str(getattr(self, name) or "").strip()
            if not value or value.upper() == "UNFROZEN":
                missing.append(name)
        if not self.recruitment_start:
            missing.append("recruitment_start")
        if not self.recruitment_end:
            missing.append("recruitment_end")
        if self.min_mature_candidates is None:
            missing.append("min_mature_candidates")
        if self.min_disagreements is None:
            missing.append("min_disagreements")
        if self.max_error_rate is None:
            missing.append("max_error_rate")
        if self.max_abstain_rate is None:
            missing.append("max_abstain_rate")
        if self.budget_limit_usd is None:
            missing.append("budget_limit_usd")
        if self.comparison_policy != JEV_COMPARISON_POLICY:
            missing.append("comparison_policy")
        if (
            str(self.provider_id or "").strip().upper() != "FAKE"
            and not self.source_transmission_approved
        ):
            missing.append("source_transmission_approved")
        return missing

    def status(self) -> str:
        return "FROZEN" if not self.freeze_gaps() else "UNFROZEN"
