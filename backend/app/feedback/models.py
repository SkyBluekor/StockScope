from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

FEEDBACK_ADAPTER_VERSION = "VN_P2_S1_EVIDENCE_ADAPTER_V1"
FEEDBACK_COHORT_VERSION = "VN_P2_S1_COHORT_V1"
FEEDBACK_REPORT_VERSION = "VN_P2_S1_REPORT_V1"
FEEDBACK_SCHEMA_VERSION = "VN_P2_S1_FEEDBACK_STORAGE_V1"


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
class EvidenceSelector:
    source_type: str
    source_id: str
    date_from: str | None = None
    date_to: str | None = None
    market: str | None = None
    strategy: str | None = None

    def normalized(self) -> "EvidenceSelector":
        return EvidenceSelector(
            source_type=(self.source_type or "").strip().upper(),
            source_id=(self.source_id or "").strip(),
            date_from=(self.date_from or "").strip() or None,
            date_to=(self.date_to or "").strip() or None,
            market=(self.market or "").strip().upper() or None,
            strategy=(self.strategy or "").strip() or None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())


@dataclass(frozen=True, slots=True)
class FeedbackEvidence:
    source_type: str
    source_owner: str
    source_id: str
    source_item_id: str
    source_hash: str
    durability: str
    origin_kind: str
    market: str | None
    ticker: str | None
    name: str | None
    signal_date: str | None
    strategy: str | None
    decision_status: str | None
    scanner_version: str | None
    scanner_baseline: str | None
    horizon_intent: str
    horizon_policy_version: str | None
    metric_definition: str
    execution_policy_version: str | None
    exit_policy_token: str | None
    fee_pct: float | None
    tax_pct: float | None
    slippage_pct: float | None
    maturity_status: str
    inclusion_status: str
    exclusion_reason: str | None
    available_trading_days: int | None
    metrics: dict[str, Any] = field(default_factory=dict)
    source_observed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def comparison_dimensions(self) -> dict[str, Any]:
        return {
            "origin_kind": self.origin_kind,
            "metric_definition": self.metric_definition,
            "market": self.market,
            "strategy": self.strategy,
            "scanner_version": self.scanner_version,
            "scanner_baseline": self.scanner_baseline,
            "horizon_intent": self.horizon_intent,
            "horizon_policy_version": self.horizon_policy_version,
            "execution_policy_version": self.execution_policy_version,
            "exit_policy_token": self.exit_policy_token,
            "fee_pct": self.fee_pct,
            "tax_pct": self.tax_pct,
            "slippage_pct": self.slippage_pct,
            "selection_method": self.metadata.get("selection_method"),
            "evaluation_window": self.metadata.get("evaluation_window"),
            "selector_date_from": self.metadata.get("selector_date_from"),
            "selector_date_to": self.metadata.get("selector_date_to"),
            "source_period_start": self.metadata.get("source_period_start"),
            "source_period_end": self.metadata.get("source_period_end"),
            "market_scope": self.metadata.get("market_scope"),
            "round_trip_cost_pct": self.metadata.get("round_trip_cost_pct"),
            "max_holding_days": self.metadata.get("max_holding_days"),
            "market_data_cutoff_date": self.metadata.get("market_data_cutoff_date"),
        }

    @property
    def comparison_key(self) -> str:
        return digest_json(self.comparison_dimensions())

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["comparison_key"] = self.comparison_key
        payload["comparison_dimensions"] = self.comparison_dimensions()
        return payload
