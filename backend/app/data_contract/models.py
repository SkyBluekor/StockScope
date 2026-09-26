from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MarketEodObservation:
    available: bool
    present: bool
    source: str
    market: str
    ticker: str
    market_confirmed_date: str | None = None
    stock_first_date: str | None = None
    stock_latest_date: str | None = None
    stock_row_count: int = 0
    reason: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ChartCoverageObservation:
    available: bool
    present: bool
    source: str
    market: str
    ticker: str
    first_date: str | None = None
    last_date: str | None = None
    row_count: int = 0
    market_confirmed_date: str | None = None
    reason: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class StoredAnalysisObservation:
    available: bool
    present: bool
    source: str
    market: str
    ticker: str
    monitored_stock_id: str | None = None
    watch_enabled: bool | None = None
    archived_at: str | None = None
    market_date: str | None = None
    revision_id: str | None = None
    revision_no: int | None = None
    computed_at: str | None = None
    strategy_key: str | None = None
    action_state: str | None = None
    risk_state: str | None = None
    input_fingerprint: str | None = None
    scanner_version: str | None = None
    analysis_engine_version: str | None = None
    policy_version: str | None = None
    source_versions: dict[str, Any] | None = None
    reason: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class LedgerPositionObservation:
    position_id: str
    account_id: str
    provider: str
    account_kind: str
    broker_environment: str | None
    current_quantity: str
    current_average_price: str | None
    current_cost_basis: str | None
    opened_reason: str
    opened_at: str
    last_observed_at: str | None
    last_sync_run_id: str | None


@dataclass(frozen=True, slots=True)
class LedgerObservation:
    available: bool
    present: bool
    source: str
    market: str
    ticker: str
    monitored_stock_id: str | None = None
    watch_enabled: bool | None = None
    archived_at: str | None = None
    open_position_count: int = 0
    positions: tuple[LedgerPositionObservation, ...] = ()
    reason: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RealtimeQuoteObservation:
    capable: bool
    present: bool
    source: str
    market: str
    ticker: str
    provider: str | None = None
    mode: str | None = None
    venue: str | None = None
    current_price: str | None = None
    provider_timestamp: str | None = None
    received_at: str | None = None
    age_ms: int | None = None
    freshness_seconds: float | None = None
    reason: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class KnownJobObservation:
    available: bool
    present: bool
    source: str
    job_id: str | None
    status: str | None = None
    stage: str | None = None
    message: str | None = None
    current: int | None = None
    total: int | None = None
    details: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class StockStateObservation:
    checked_at: str
    market: str
    ticker: str
    eod: MarketEodObservation
    chart: ChartCoverageObservation
    analysis: StoredAnalysisObservation
    ledger: LedgerObservation
    realtime: RealtimeQuoteObservation
    active_job: KnownJobObservation
