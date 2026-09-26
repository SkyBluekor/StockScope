from __future__ import annotations

from app.backtest.production_exit_policy import PRODUCTION_EXIT_POLICY_VERSION
from app.backtest.scanner import StockScannerService
from app.holdings.analysis import ANALYSIS_ENGINE_VERSION
from app.holdings.chart import RANGE_BARS

from .models import StockStateObservation
from .schema import (
    ActiveJobContract,
    AnalysisIdentityContract,
    AnalysisResourceContract,
    ChartRange,
    ChartResourceContract,
    ContractAction,
    DataContractRequestEcho,
    EodResourceContract,
    LedgerPositionContract,
    LedgerResourceContract,
    PreparationContract,
    RealtimeResourceContract,
    ResourceContracts,
    StockDataContract,
)


def _iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw or None


def _eod_contract(state: StockStateObservation) -> EodResourceContract:
    observed = state.eod
    confirmed = _iso_date(observed.market_confirmed_date)
    stock_date = _iso_date(observed.stock_latest_date)
    first_date = _iso_date(observed.stock_first_date)

    if observed.reason in {"STORE_NOT_FOUND", "DATA_ABSENT"}:
        status = "ABSENT"
        reason = observed.reason
    elif observed.reason in {"SCHEMA_UNAVAILABLE", "READ_FAILED"}:
        status = "UNVERIFIED"
        reason = observed.reason
    elif not observed.present:
        status = "ABSENT"
        reason = observed.reason or "DATA_ABSENT"
    elif not confirmed or not stock_date:
        status = "UNVERIFIED"
        reason = "EOD_DATE_UNVERIFIED"
    elif stock_date != confirmed:
        status = "INVALID"
        reason = "STALE_TO_MARKET_CONFIRMED" if stock_date < confirmed else "EOD_DATE_MISMATCH"
    else:
        status = "VALID"
        reason = None

    return EodResourceContract(
        status=status,
        present=observed.present,
        source=observed.source,
        market_confirmed_date=confirmed,
        stock_date=stock_date,
        first_date=first_date,
        row_count=observed.stock_row_count,
        reason_code=reason,
    )


def _chart_contract(
    state: StockStateObservation,
    chart_range: ChartRange | None,
) -> ChartResourceContract:
    observed = state.chart
    first_date = _iso_date(observed.first_date)
    last_date = _iso_date(observed.last_date)
    confirmed = _iso_date(observed.market_confirmed_date)
    required_rows = RANGE_BARS.get(chart_range) if chart_range is not None else None

    if observed.reason in {"STORE_NOT_FOUND", "DATA_ABSENT"}:
        status = "ABSENT"
        reason = observed.reason
    elif observed.reason in {"SCHEMA_UNAVAILABLE", "READ_FAILED"}:
        status = "UNVERIFIED"
        reason = observed.reason
    elif not observed.present:
        status = "ABSENT"
        reason = observed.reason or "DATA_ABSENT"
    elif not confirmed or not last_date:
        status = "UNVERIFIED"
        reason = "CHART_DATE_UNVERIFIED"
    elif last_date != confirmed:
        status = "INVALID"
        reason = "STALE_TO_MARKET_CONFIRMED" if last_date < confirmed else "CHART_DATE_MISMATCH"
    elif required_rows is not None and observed.row_count < required_rows:
        status = "INVALID"
        reason = "INSUFFICIENT_COVERAGE"
    else:
        status = "VALID"
        reason = None

    return ChartResourceContract(
        status=status,
        present=observed.present,
        source=observed.source,
        range=chart_range,
        from_date=first_date,
        to_date=last_date,
        row_count=observed.row_count,
        required_rows=required_rows,
        market_confirmed_date=confirmed,
        reason_code=reason,
    )


def _policy_family_matches(value: str | None) -> bool:
    if not value:
        return False
    return value == PRODUCTION_EXIT_POLICY_VERSION or value.startswith(
        f"{PRODUCTION_EXIT_POLICY_VERSION}-"
    )


def _analysis_contract(
    state: StockStateObservation,
    eod: EodResourceContract,
) -> AnalysisResourceContract:
    observed = state.analysis
    identity = AnalysisIdentityContract(
        input_fingerprint=observed.input_fingerprint,
        scanner_version=observed.scanner_version,
        analysis_engine_version=observed.analysis_engine_version,
        policy_version=observed.policy_version,
        source_versions=observed.source_versions,
    )
    basis_date = _iso_date(observed.market_date)

    if observed.reason in {"STORE_NOT_FOUND", "ANALYSIS_ABSENT"}:
        status = "ABSENT"
        reason = observed.reason
    elif observed.reason in {"SCHEMA_UNAVAILABLE", "READ_FAILED"}:
        status = "UNVERIFIED"
        reason = observed.reason
    elif observed.reason == "ANALYSIS_CURRENT_REVISION_MISSING":
        status = "INVALID"
        reason = "CURRENT_REVISION_MISSING"
    elif observed.reason == "DATA_INVALID":
        status = "INVALID"
        reason = "ANALYSIS_METADATA_INVALID"
    elif not observed.present:
        status = "ABSENT"
        reason = observed.reason or "ANALYSIS_ABSENT"
    elif not basis_date:
        status = "UNVERIFIED"
        reason = "ANALYSIS_BASIS_UNVERIFIED"
    elif eod.status == "VALID" and eod.stock_date and basis_date != eod.stock_date:
        status = "INVALID"
        reason = "ANALYSIS_BASIS_STALE" if basis_date < eod.stock_date else "ANALYSIS_BASIS_MISMATCH"
    elif observed.analysis_engine_version and observed.analysis_engine_version != ANALYSIS_ENGINE_VERSION:
        status = "INVALID"
        reason = "ANALYSIS_ENGINE_VERSION_MISMATCH"
    elif observed.scanner_version and observed.scanner_version != StockScannerService.VERSION:
        status = "INVALID"
        reason = "SCANNER_VERSION_MISMATCH"
    elif observed.policy_version and not _policy_family_matches(observed.policy_version):
        status = "INVALID"
        reason = "POLICY_VERSION_FAMILY_MISMATCH"
    elif not (
        observed.input_fingerprint
        and observed.analysis_engine_version
        and observed.scanner_version
        and observed.policy_version
    ):
        status = "UNVERIFIED"
        reason = "ANALYSIS_IDENTITY_INCOMPLETE"
    else:
        # J-8.2 deliberately does not reconstruct the current input fingerprint.
        status = "UNVERIFIED"
        reason = "CURRENT_INPUT_IDENTITY_NOT_PROVEN"

    return AnalysisResourceContract(
        status=status,
        present=observed.present,
        source=observed.source,
        basis="CONFIRMED_EOD" if observed.present else None,
        basis_date=basis_date,
        monitored_stock_id=observed.monitored_stock_id,
        revision_id=observed.revision_id,
        revision_no=observed.revision_no,
        computed_at=observed.computed_at,
        strategy_key=observed.strategy_key,
        action_state=observed.action_state,
        risk_state=observed.risk_state,
        identity=identity,
        displayable=observed.present,
        current_use_allowed=status == "VALID",
        reason_code=reason,
    )


def _ledger_contract(state: StockStateObservation) -> LedgerResourceContract:
    observed = state.ledger
    if observed.reason in {"STORE_NOT_FOUND", "LEDGER_ABSENT"}:
        status = "ABSENT"
        reason = observed.reason
    elif observed.reason in {"SCHEMA_UNAVAILABLE", "READ_FAILED"}:
        status = "UNVERIFIED"
        reason = observed.reason
    elif observed.present:
        status = "VALID"
        reason = None
    else:
        status = "ABSENT"
        reason = observed.reason or "LEDGER_ABSENT"

    return LedgerResourceContract(
        status=status,
        present=observed.present,
        source=observed.source,
        monitored_stock_id=observed.monitored_stock_id,
        watch_enabled=observed.watch_enabled,
        archived_at=observed.archived_at,
        open_position_count=observed.open_position_count,
        positions=[
            LedgerPositionContract(
                position_id=item.position_id,
                account_id=item.account_id,
                provider=item.provider,
                account_kind=item.account_kind,
                broker_environment=item.broker_environment,
                current_quantity=item.current_quantity,
                current_average_price=item.current_average_price,
                current_cost_basis=item.current_cost_basis,
                opened_reason=item.opened_reason,
                opened_at=item.opened_at,
                last_observed_at=item.last_observed_at,
                last_sync_run_id=item.last_sync_run_id,
            )
            for item in observed.positions
        ],
        reason_code=reason,
    )


def _realtime_contract(state: StockStateObservation) -> RealtimeResourceContract:
    observed = state.realtime
    if observed.reason == "KIS_QUOTE_NOT_CONFIGURED":
        status = "ABSENT"
        reason = observed.reason
    elif observed.reason == "QUOTE_NOT_OBSERVED":
        status = "ABSENT"
        reason = observed.reason
    elif observed.reason == "QUOTE_OBSERVATION_FAILED":
        status = "UNVERIFIED"
        reason = observed.reason
    elif not observed.present:
        status = "ABSENT" if observed.capable else "UNVERIFIED"
        reason = observed.reason or "QUOTE_NOT_OBSERVED"
    elif observed.age_ms is None or observed.freshness_seconds is None:
        status = "UNVERIFIED"
        reason = "QUOTE_FRESHNESS_UNVERIFIED"
    elif observed.age_ms > int(observed.freshness_seconds * 1000):
        status = "UNVERIFIED"
        reason = "QUOTE_SNAPSHOT_STALE"
    else:
        status = "VALID"
        reason = None

    return RealtimeResourceContract(
        status=status,
        present=observed.present,
        source=observed.source,
        capability=observed.capable,
        provider=observed.provider,
        mode=observed.mode,
        venue=observed.venue,
        current_price=observed.current_price,
        provider_timestamp=observed.provider_timestamp,
        received_at=observed.received_at,
        age_ms=observed.age_ms,
        freshness_seconds=observed.freshness_seconds,
        reason_code=reason,
    )


def _active_job_contract(state: StockStateObservation) -> ActiveJobContract | None:
    observed = state.active_job
    if observed.job_id is None:
        return None
    if not observed.present:
        return ActiveJobContract(
            state="UNKNOWN",
            job_id=observed.job_id,
            reason_code=observed.reason or "JOB_NOT_FOUND",
        )
    return ActiveJobContract(
        state="KNOWN",
        job_id=observed.job_id,
        status=observed.status,
        stage=observed.stage,
        message=observed.message,
        current=observed.current,
        total=observed.total,
        details=observed.details,
        error=observed.error_message,
        created_at=observed.created_at,
        updated_at=observed.updated_at,
    )


def _preparation_contract(
    *,
    eod: EodResourceContract,
    chart: ChartResourceContract,
    analysis: AnalysisResourceContract,
    chart_range: ChartRange | None,
) -> PreparationContract:
    targets: list[str] = []
    reasons: list[str] = []

    if eod.status in {"ABSENT", "INVALID"}:
        targets.append("eod")
        if eod.reason_code:
            reasons.append(eod.reason_code)

    if chart_range is not None and chart.status in {"ABSENT", "INVALID"}:
        targets.append("chart")
        if chart.reason_code and chart.reason_code not in reasons:
            reasons.append(chart.reason_code)

    eod_supported = "eod" not in targets or bool(analysis.monitored_stock_id)
    chart_supported = "chart" not in targets or chart_range is not None

    return PreparationContract(
        required=bool(targets),
        targets=targets,
        supported=eod_supported and chart_supported,
        reason_codes=reasons,
    )


def _actions(
    *,
    chart: ChartResourceContract,
    analysis: AnalysisResourceContract,
    active_job: ActiveJobContract | None,
    chart_range: ChartRange | None,
) -> list[ContractAction]:
    actions: list[ContractAction] = []

    if chart_range is not None and chart.status in {"ABSENT", "INVALID"}:
        actions.append(
            ContractAction(
                id="PREPARE_CHART",
                target="chart",
                enabled=True,
                reason_code=chart.reason_code,
            )
        )

    if analysis.monitored_stock_id and analysis.status in {"ABSENT", "UNVERIFIED", "INVALID"}:
        actions.append(
            ContractAction(
                id="REFRESH_HOLDING_ANALYSIS",
                target="analysis_result",
                enabled=True,
                reason_code=analysis.reason_code,
            )
        )

    if (
        active_job is not None
        and active_job.state == "KNOWN"
        and active_job.status in {"queued", "running"}
    ):
        actions.append(
            ContractAction(
                id="VIEW_ACTIVE_JOB",
                target="active_job",
                enabled=True,
                reason_code=None,
            )
        )

    return actions


def build_stock_data_contract(
    state: StockStateObservation,
    *,
    chart_range: ChartRange | None = None,
    job_id: str | None = None,
) -> StockDataContract:
    eod = _eod_contract(state)
    chart = _chart_contract(state, chart_range)
    analysis = _analysis_contract(state, eod)
    ledger = _ledger_contract(state)
    realtime = _realtime_contract(state)
    active_job = _active_job_contract(state)
    preparation = _preparation_contract(
        eod=eod,
        chart=chart,
        analysis=analysis,
        chart_range=chart_range,
    )
    actions = _actions(
        chart=chart,
        analysis=analysis,
        active_job=active_job,
        chart_range=chart_range,
    )

    return StockDataContract(
        resource_key=f"{state.market}:{state.ticker}",
        checked_at=state.checked_at,
        request=DataContractRequestEcho(
            market=state.market,
            ticker=state.ticker,
            range=chart_range,
            job_id=(job_id or "").strip() or None,
        ),
        resources=ResourceContracts(
            eod=eod,
            chart=chart,
            analysis_result=analysis,
            realtime=realtime,
            ledger=ledger,
        ),
        preparation=preparation,
        active_job=active_job,
        actions=actions,
    )
