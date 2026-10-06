from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


JEV_SCHEMA_VERSION = "JEV_SHADOW_STORAGE_V1"
JEV_TRIAL_PROTOCOL_VERSION = "JEV_SHADOW_TRIAL_PROTOCOL_V1"
JEV_INPUT_CONTRACT_VERSION = "JEV_SCANNER_REVIEW_INPUT_V1"
JEV_OUTPUT_CONTRACT_VERSION = "JEV_SCANNER_REVIEW_OUTPUT_V1"
JEV_ADAPTER_VERSION = "JEV_OPENAI_RESPONSES_ADAPTER_V1"
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
    recruitment_mode: str = "FIXED_DATES"
    recruitment_start: str | None = None
    recruitment_end: str | None = None
    recruitment_duration_calendar_days: int | None = None
    max_recruited_candidates: int | None = None
    duplicate_rule: str = ""
    deadline_seconds: float = 8.0
    max_observation_trading_days: int = 20
    purge_trading_days: int = 20
    min_mature_candidates: int | None = None
    min_disagreements: int | None = None
    max_error_rate: float | None = None
    max_abstain_rate: float | None = None
    max_review_rate: float | None = None
    budget_limit_usd: float | None = None
    round_trip_cost_pct: float = 0.0
    fee_pct: float = 0.0
    tax_pct: float = 0.0
    slippage_pct: float = 0.0
    cost_assumption_note: str = ""
    model_revision_policy: str = ""
    source_transmission_approved: bool = False
    source_policy_version: str = ""
    provider_policy_checked_at: str = ""
    retention_mode: str = ""
    training_use_status: str = ""
    allowed_payload_class: str = ""
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
        recruitment_mode = str(self.recruitment_mode or "").strip().upper()
        if recruitment_mode == "ACTIVATION_FORWARD":
            if self.recruitment_duration_calendar_days is None:
                missing.append("recruitment_duration_calendar_days")
            if self.max_recruited_candidates is None:
                missing.append("max_recruited_candidates")
        else:
            if not self.recruitment_start:
                missing.append("recruitment_start")
            if not self.recruitment_end:
                missing.append("recruitment_end")
        if not str(self.duplicate_rule or "").strip():
            missing.append("duplicate_rule")
        if self.min_mature_candidates is None:
            missing.append("min_mature_candidates")
        if self.min_disagreements is None:
            missing.append("min_disagreements")
        if self.max_error_rate is None:
            missing.append("max_error_rate")
        if self.max_abstain_rate is None:
            missing.append("max_abstain_rate")
        if self.max_review_rate is None:
            missing.append("max_review_rate")
        if self.budget_limit_usd is None:
            missing.append("budget_limit_usd")
        if self.max_observation_trading_days <= 0:
            missing.append("max_observation_trading_days")
        if self.purge_trading_days < 0:
            missing.append("purge_trading_days")
        if not str(self.model_revision_policy or "").strip():
            missing.append("model_revision_policy")
        if self.comparison_policy != JEV_COMPARISON_POLICY:
            missing.append("comparison_policy")
        if str(self.provider_id or "").strip().upper() != "FAKE":
            if not self.source_transmission_approved:
                missing.append("source_transmission_approved")
            for name in (
                "source_policy_version",
                "provider_policy_checked_at",
                "retention_mode",
                "training_use_status",
                "allowed_payload_class",
            ):
                if not str(getattr(self, name) or "").strip():
                    missing.append(name)
        return missing

    def status(self) -> str:
        return "FROZEN" if not self.freeze_gaps() else "UNFROZEN"
