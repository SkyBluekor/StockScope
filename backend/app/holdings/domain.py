from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


ACCOUNT_KINDS = frozenset({"BROKER", "MANUAL", "VIRTUAL"})
BROKER_ENVIRONMENTS = frozenset({"REAL", "VIRTUAL"})
ACCOUNT_STATUSES = frozenset({"ACTIVE", "ARCHIVED"})
POSITION_STATUSES = frozenset({"OPEN", "CLOSED"})
POSITION_OPEN_REASONS = frozenset({"MANUAL", "KIS_OBSERVED", "VIRTUAL"})
POSITION_EVENT_TYPES = frozenset(
    {"BUY", "SELL", "CORRECTION", "BALANCE_OBSERVED", "RECONCILED"}
)
SYNC_STATUSES = frozenset({"RUNNING", "COMPLETED", "FAILED"})


def account_fingerprint(
    *,
    provider: str,
    broker_environment: str,
    account_number: str,
    product_code: str,
) -> str:
    """Return a stable identifier without persisting the raw broker account number."""
    material = "|".join(
        [
            provider.strip().upper(),
            broker_environment.strip().upper(),
            account_number.strip(),
            product_code.strip(),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PositionAccount:
    id: str
    provider: str
    account_kind: str
    broker_environment: str | None
    external_account_fingerprint: str | None
    display_name: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class MonitoredStock:
    id: str
    market: str
    ticker: str
    name: str
    watch_enabled: bool
    archived_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AccountSyncRun:
    id: str
    position_account_id: str
    status: str
    started_at: str
    completed_at: str | None
    is_complete: bool
    observed_at: str | None
    page_count: int
    holding_count: int
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class HoldingPosition:
    id: str
    monitored_stock_id: str
    position_account_id: str
    status: str
    opened_at: str
    closed_at: str | None
    current_quantity: Decimal
    current_average_price: Decimal | None
    current_cost_basis: Decimal | None
    opened_reason: str
    last_observed_at: str | None
    last_sync_run_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class HoldingPositionEvent:
    id: str
    position_id: str
    event_type: str
    quantity_delta: Decimal | None
    unit_price: Decimal | None
    before_quantity: Decimal | None
    after_quantity: Decimal | None
    before_average_price: Decimal | None
    after_average_price: Decimal | None
    observed_at: str | None
    effective_at: str | None
    analysis_revision_id: str | None
    account_sync_run_id: str | None
    external_event_key: str | None
    note: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class StockAnalysisDay:
    id: str
    monitored_stock_id: str
    market_date: str
    current_revision_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class StockAnalysisRevision:
    id: str
    analysis_day_id: str
    revision_no: int
    input_fingerprint: str
    strategy_key: str | None
    action_state: str | None
    risk_state: str | None
    reference_price: Decimal | None
    stop_price: Decimal | None
    target1_price: Decimal | None
    target2_price: Decimal | None
    scanner_version: str | None
    analysis_engine_version: str | None
    policy_version: str | None
    source_versions: Any
    snapshot: Any
    revision_reason: str | None
    computed_at: str
    created_at: str
