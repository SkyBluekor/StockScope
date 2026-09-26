from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


CONTRACT_VERSION = "DATA_CONTRACT_V1"
ResourceStatus = Literal["ABSENT", "UNVERIFIED", "VALID", "INVALID"]
ChartRange = Literal["1m", "3m", "6m", "1y"]


class DataContractRequestEcho(BaseModel):
    market: Literal["KOSPI", "KOSDAQ"]
    ticker: str
    range: ChartRange | None = None
    job_id: str | None = None


class EodResourceContract(BaseModel):
    status: ResourceStatus
    present: bool
    source: str
    basis: Literal["CONFIRMED_EOD"] = "CONFIRMED_EOD"
    market_confirmed_date: str | None = None
    stock_date: str | None = None
    first_date: str | None = None
    row_count: int = 0
    reason_code: str | None = None


class ChartResourceContract(BaseModel):
    status: ResourceStatus
    present: bool
    source: str
    range: ChartRange | None = None
    from_date: str | None = None
    to_date: str | None = None
    row_count: int = 0
    required_rows: int | None = None
    market_confirmed_date: str | None = None
    reason_code: str | None = None


class AnalysisIdentityContract(BaseModel):
    input_fingerprint: str | None = None
    scanner_version: str | None = None
    analysis_engine_version: str | None = None
    policy_version: str | None = None
    source_versions: dict[str, Any] | None = None


class AnalysisResourceContract(BaseModel):
    status: ResourceStatus
    present: bool
    source: str
    basis: Literal["CONFIRMED_EOD"] | None = None
    basis_date: str | None = None
    monitored_stock_id: str | None = None
    revision_id: str | None = None
    revision_no: int | None = None
    computed_at: str | None = None
    strategy_key: str | None = None
    action_state: str | None = None
    risk_state: str | None = None
    identity: AnalysisIdentityContract
    displayable: bool
    current_use_allowed: bool
    reason_code: str | None = None


class RealtimeResourceContract(BaseModel):
    status: ResourceStatus
    present: bool
    source: str
    capability: bool
    provider: str | None = None
    mode: str | None = None
    venue: str | None = None
    current_price: str | None = None
    provider_timestamp: str | None = None
    received_at: str | None = None
    age_ms: int | None = None
    freshness_seconds: float | None = None
    reason_code: str | None = None


class LedgerPositionContract(BaseModel):
    position_id: str
    account_id: str
    provider: str
    account_kind: str
    broker_environment: str | None = None
    current_quantity: str
    current_average_price: str | None = None
    current_cost_basis: str | None = None
    opened_reason: str
    opened_at: str
    last_observed_at: str | None = None
    last_sync_run_id: str | None = None


class LedgerResourceContract(BaseModel):
    status: ResourceStatus
    present: bool
    source: str
    monitored_stock_id: str | None = None
    watch_enabled: bool | None = None
    archived_at: str | None = None
    open_position_count: int = 0
    positions: list[LedgerPositionContract]
    reason_code: str | None = None


class ResourceContracts(BaseModel):
    eod: EodResourceContract
    chart: ChartResourceContract
    analysis_result: AnalysisResourceContract
    realtime: RealtimeResourceContract
    ledger: LedgerResourceContract


class PreparationContract(BaseModel):
    required: bool
    targets: list[Literal["eod", "chart"]]
    supported: bool
    reason_codes: list[str]


class ActiveJobContract(BaseModel):
    state: Literal["KNOWN", "UNKNOWN"]
    job_id: str
    status: str | None = None
    stage: str | None = None
    message: str | None = None
    current: int | None = None
    total: int | None = None
    details: dict[str, Any] | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    reason_code: str | None = None


class ContractAction(BaseModel):
    id: Literal["PREPARE_CHART", "REFRESH_HOLDING_ANALYSIS", "VIEW_ACTIVE_JOB"]
    target: Literal["chart", "analysis_result", "active_job"]
    enabled: bool
    requires_user_initiation: Literal[True] = True
    reason_code: str | None = None


class StockDataContract(BaseModel):
    contract_version: Literal["DATA_CONTRACT_V1"] = CONTRACT_VERSION
    resource_key: str
    checked_at: str
    request: DataContractRequestEcho
    resources: ResourceContracts
    preparation: PreparationContract
    active_job: ActiveJobContract | None
    actions: list[ContractAction]
