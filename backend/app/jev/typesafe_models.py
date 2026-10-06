from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .models import JEV_COMPARISON_POLICY, canonical_json, digest_json


JEV_TYPESAFE_SCHEMA_VERSION = "JEV_TYPESAFE_STORAGE_V2"
JEV_TYPESAFE_PROTOCOL_VERSION = "JEV_TYPESAFE_TRIAL_PROTOCOL_V2"
JEV_TYPESAFE_STATE_CONTRACT_VERSION = "JEV_TYPESAFE_STATE_V1"
JEV_TYPESAFE_PROJECTOR_VERSION = "JEV_TYPESAFE_PROJECTOR_V1"
JEV_TYPESAFE_QUESTION_CONTRACT_VERSION = "JEV_TYPESAFE_QUESTIONS_V1"
JEV_TYPESAFE_DISPOSITION_POLICY_VERSION = "JEV_TYPESAFE_DISPOSITION_POLICY_V1"
JEV_TYPESAFE_ADAPTER_VERSION = "JEV_TYPESAFE_SYSTEMONE_ADAPTER_V1"
JEV_TYPESAFE_PROVIDER_ID = "TYPESAFE_SYSTEM_ONE"
JEV_TYPESAFE_ALLOWED_PAYLOAD_CLASS = "MINIMIZED_DERIVED_SCANNER_SEMANTIC_STATE_V1"

JEV_TYPESAFE_OPERATIONAL_STATUSES = frozenset(
    {"SKIPPED", "PENDING", "VALID", "ERROR", "LATE", "INTERRUPTED"}
)
JEV_TYPESAFE_TERMINAL_STATUSES = frozenset(
    {"SKIPPED", "VALID", "ERROR", "LATE", "INTERRUPTED"}
)
JEV_TYPESAFE_DISPOSITIONS = frozenset(
    {"PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN"}
)


def _unfrozen(value: Any) -> bool:
    return not str(value or "").strip() or str(value).strip().upper() == "UNFROZEN"


@dataclass(frozen=True, slots=True)
class TypeSafeJevTrialProtocolSpec:
    name: str
    provider_id: str = "UNFROZEN"
    model_requested: str = "UNFROZEN"
    expected_model_returned: str = "UNFROZEN"
    state_contract_version: str = JEV_TYPESAFE_STATE_CONTRACT_VERSION
    state_contract_hash: str = "UNFROZEN"
    projector_version: str = JEV_TYPESAFE_PROJECTOR_VERSION
    projector_hash: str = "UNFROZEN"
    question_contract_version: str = JEV_TYPESAFE_QUESTION_CONTRACT_VERSION
    question_set_hash: str = "UNFROZEN"
    disposition_policy_version: str = JEV_TYPESAFE_DISPOSITION_POLICY_VERSION
    disposition_policy_hash: str = "UNFROZEN"
    threshold_low: float | None = None
    threshold_high: float | None = None
    market_scope: str = "ALL"
    horizon_intents: tuple[str, ...] = ("SHORT", "MEDIUM")
    recruitment_mode: str = "ACTIVATION_FORWARD"
    recruitment_duration_calendar_days: int | None = None
    max_recruited_candidates: int | None = None
    duplicate_rule: str = (
        "FIRST_CANONICAL_PER_MARKET_TICKER_SIGNAL_DATE_STRATEGY_VERSION_HORIZON"
    )
    deadline_seconds: float = 12.0
    concurrency_cap: int = 1
    queue_cap: int = 16
    retry_count: int = 0
    budget_limit_usd: float | None = None
    per_call_reservation_usd: float | None = None
    source_transmission_approved: bool = False
    allowed_payload_class: str = JEV_TYPESAFE_ALLOWED_PAYLOAD_CLASS
    provider_policy_checked_at: str = ""
    retention_status: str = ""
    model_discovery_ref: str = ""
    model_discovery_hash: str = ""
    comparison_policy: str = JEV_COMPARISON_POLICY
    adapter_version: str = JEV_TYPESAFE_ADAPTER_VERSION
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["horizon_intents"] = list(self.horizon_intents)
        return payload

    def freeze_gaps(self) -> list[str]:
        missing: list[str] = []
        for name in (
            "provider_id",
            "model_requested",
            "expected_model_returned",
            "state_contract_hash",
            "projector_hash",
            "question_set_hash",
            "disposition_policy_hash",
        ):
            if _unfrozen(getattr(self, name)):
                missing.append(name)

        if self.threshold_low is None:
            missing.append("threshold_low")
        if self.threshold_high is None:
            missing.append("threshold_high")
        if self.threshold_low is not None and self.threshold_high is not None:
            low = float(self.threshold_low)
            high = float(self.threshold_high)
            if not (0.0 <= low < 0.5 < high <= 1.0):
                missing.append("threshold_order")

        if tuple(self.horizon_intents) != ("SHORT", "MEDIUM"):
            missing.append("horizon_intents")
        if self.recruitment_mode != "ACTIVATION_FORWARD":
            missing.append("recruitment_mode")
        if self.recruitment_duration_calendar_days is None:
            missing.append("recruitment_duration_calendar_days")
        if self.max_recruited_candidates is None:
            missing.append("max_recruited_candidates")
        if not str(self.duplicate_rule or "").strip():
            missing.append("duplicate_rule")
        if self.deadline_seconds <= 0:
            missing.append("deadline_seconds")
        if self.concurrency_cap <= 0:
            missing.append("concurrency_cap")
        if self.queue_cap <= 0:
            missing.append("queue_cap")
        if self.retry_count != 0:
            missing.append("retry_count")
        if self.budget_limit_usd is None:
            missing.append("budget_limit_usd")
        if self.per_call_reservation_usd is None:
            missing.append("per_call_reservation_usd")
        if self.comparison_policy != JEV_COMPARISON_POLICY:
            missing.append("comparison_policy")
        if self.adapter_version != JEV_TYPESAFE_ADAPTER_VERSION:
            missing.append("adapter_version")

        provider = str(self.provider_id or "").strip().upper()
        if provider != "FAKE":
            if provider != JEV_TYPESAFE_PROVIDER_ID:
                missing.append("provider_id")
            if not self.source_transmission_approved:
                missing.append("source_transmission_approved")
            for name in (
                "provider_policy_checked_at",
                "retention_status",
                "model_discovery_ref",
                "model_discovery_hash",
            ):
                if not str(getattr(self, name) or "").strip():
                    missing.append(name)
            if self.allowed_payload_class != JEV_TYPESAFE_ALLOWED_PAYLOAD_CLASS:
                missing.append("allowed_payload_class")
        return sorted(set(missing))

    def status(self) -> str:
        return "FROZEN" if not self.freeze_gaps() else "DRAFT"

    def spec_hash(self) -> str:
        return digest_json(self.to_dict())
