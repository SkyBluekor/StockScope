from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import get_settings

from app.holdings.analysis_history import (
    HoldingAnalysisHistoryService,
    HoldingsAnalysisHistoryError,
    StoredAnalysisResult,
)
from app.holdings.catalog import (
    DEFAULT_HOLDINGS_DB,
    HoldingsCatalog,
    HoldingsCatalogError,
)
from app.holdings.chart import HoldingsChartError, HoldingsChartService
from app.holdings.decision_context import HoldingDecisionContextService
from app.holdings.freshness import (
    HoldingsMarketFreshnessError,
    HoldingsMarketFreshnessService,
)
from app.holdings.kis_sync import (
    HoldingsKisSyncError,
    KisAccountSyncService,
)
from app.holdings.lifecycle import (
    HoldingsLifecycleError,
    PositionLifecycleResult,
    PositionLifecycleService,
)


router = APIRouter(prefix="/holdings", tags=["holdings"])


class WatchStockRequest(BaseModel):
    market: Literal["KOSPI", "KOSDAQ"]
    ticker: str = Field(pattern=r"^\d{6}$")
    name: str = Field(min_length=1, max_length=100)


class WatchStateRequest(BaseModel):
    enabled: bool


class ManualBuyRequest(BaseModel):
    stock_id: str = Field(min_length=1)
    account_id: str | None = None
    quantity: str = Field(min_length=1, max_length=80)
    unit_price: str = Field(min_length=1, max_length=80)
    effective_at: str = Field(min_length=1, max_length=80)
    analysis_revision_id: str | None = None
    note: str | None = Field(default=None, max_length=500)


class ManualSellRequest(BaseModel):
    quantity: str = Field(min_length=1, max_length=80)
    unit_price: str = Field(min_length=1, max_length=80)
    effective_at: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class ManualCorrectionRequest(BaseModel):
    quantity: str = Field(min_length=1, max_length=80)
    average_price: str = Field(min_length=1, max_length=80)
    effective_at: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _catalog() -> HoldingsCatalog:
    raw = os.getenv("STOCKSCOPE_HOLDINGS_DB")
    path = Path(raw) if raw else DEFAULT_HOLDINGS_DB
    catalog = HoldingsCatalog(path)
    catalog.initialize()
    return catalog


def _market_store_path() -> Path | None:
    raw = os.getenv("STOCKSCOPE_MARKET_STORE_DB")
    return Path(raw) if raw else None


def _history_service(catalog: HoldingsCatalog) -> HoldingAnalysisHistoryService:
    return HoldingAnalysisHistoryService(
        catalog,
        market_store_db=_market_store_path(),
    )


def _chart_service() -> HoldingsChartService:
    return HoldingsChartService(_market_store_path())


def _decision_service(catalog: HoldingsCatalog) -> HoldingDecisionContextService:
    return HoldingDecisionContextService(catalog)


def _freshness_service() -> HoldingsMarketFreshnessService:
    settings = get_settings()
    return HoldingsMarketFreshnessService(
        krx_api_key=settings.krx_api_key,
        market_store_db=_market_store_path(),
    )


def _lifecycle_service(catalog: HoldingsCatalog) -> PositionLifecycleService:
    return PositionLifecycleService(catalog)


def _kis_sync_service(catalog: HoldingsCatalog) -> KisAccountSyncService:
    return KisAccountSyncService(catalog)


def _http_status(code: str) -> int:
    if "NOT_FOUND" in code:
        return 404
    if code in {
        "HOLD_STOCK_DUPLICATE",
        "HOLD_ACCOUNT_DUPLICATE",
        "HOLD_OPEN_POSITION_DUPLICATE",
        "HOLD_POSITION_ALREADY_CLOSED",
        "HOLD_POSITION_SELL_EXCEEDS_HOLDING",
        "HOLD_POSITION_SOURCE_MANAGED_EXTERNALLY",
        "HOLD_POSITION_EVENT_OUT_OF_ORDER",
        "HOLD_POSITION_REVISION_FROM_FUTURE",
        "HOLD_POSITION_REVISION_MISMATCH",
        "HOLD_POSITION_CONFLICT",
        "HOLD_KIS_SYNC_CONFIGURATION_ERROR",
        "HOLD_KIS_SYNC_ACCOUNT_CONFLICT",
        "HOLD_KIS_SYNC_INCOMPLETE",
        "HOLD_KIS_SYNC_DUPLICATE_TICKER",
        "HOLD_KIS_SYNC_MARKET_UNRESOLVED",
        "HOLD_KIS_SYNC_STORAGE_CONFLICT",
        "HOLD_ANALYSIS_HISTORY_CONFLICT",
    }:
        return 409
    if code in {
        "HOLD_KIS_SYNC_BALANCE_FAILED",
        "HOLD_MARKET_FRESHNESS_UPDATE_FAILED",
    }:
        return 502
    return 400


def _raise_holdings_error(error: Exception) -> None:
    code = getattr(error, "code", "HOLD_API_ERROR")
    message = getattr(error, "message", str(error))
    raise HTTPException(
        status_code=_http_status(str(code)),
        detail={"code": str(code), "message": str(message)},
    ) from error


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _account_payload(account: Any) -> dict[str, Any]:
    return {
        "id": account.id,
        "provider": account.provider,
        "account_kind": account.account_kind,
        "broker_environment": account.broker_environment,
        "display_name": account.display_name,
        "status": account.status,
    }


def _position_payload(catalog: HoldingsCatalog, position: Any) -> dict[str, Any]:
    account = catalog.get_position_account(position.position_account_id)
    return {
        "position_id": position.id,
        "account_id": account.id,
        "provider": account.provider,
        "account_kind": account.account_kind,
        "broker_environment": account.broker_environment,
        "account_name": account.display_name,
        "status": position.status,
        "opened_at": position.opened_at,
        "closed_at": position.closed_at,
        "quantity": _json_safe(position.current_quantity),
        "average_price": _json_safe(position.current_average_price),
        "cost_basis": _json_safe(position.current_cost_basis),
        "opened_reason": position.opened_reason,
        "last_observed_at": position.last_observed_at,
    }


def _event_payload(event: Any) -> dict[str, Any]:
    return {
        "event_id": event.id,
        "position_id": event.position_id,
        "event_type": event.event_type,
        "quantity_delta": _json_safe(event.quantity_delta),
        "unit_price": _json_safe(event.unit_price),
        "before_quantity": _json_safe(event.before_quantity),
        "after_quantity": _json_safe(event.after_quantity),
        "before_average_price": _json_safe(event.before_average_price),
        "after_average_price": _json_safe(event.after_average_price),
        "observed_at": event.observed_at,
        "effective_at": event.effective_at,
        "analysis_revision_id": event.analysis_revision_id,
        "account_sync_run_id": event.account_sync_run_id,
        "note": event.note,
        "created_at": event.created_at,
    }


def _current_analysis_payload(
    catalog: HoldingsCatalog,
    stock_id: str,
) -> dict[str, Any] | None:
    with catalog.connection() as conn:
        row = conn.execute(
            """
            SELECT
                d.market_date,
                r.id AS revision_id,
                r.revision_no,
                r.strategy_key,
                r.action_state,
                r.risk_state,
                r.reference_price,
                r.stop_price,
                r.target1_price,
                r.target2_price,
                r.scanner_version,
                r.analysis_engine_version,
                r.policy_version,
                r.revision_reason,
                r.computed_at
            FROM stock_analysis_day d
            JOIN stock_analysis_revision r ON r.id=d.current_revision_id
            WHERE d.monitored_stock_id=?
            ORDER BY d.market_date DESC
            LIMIT 1
            """,
            (stock_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "market_date": row["market_date"],
        "revision_id": row["revision_id"],
        "revision_no": int(row["revision_no"]),
        "strategy_key": row["strategy_key"],
        "action_state": row["action_state"],
        "risk_state": row["risk_state"],
        "reference_price": row["reference_price"],
        "stop_price": row["stop_price"],
        "target1_price": row["target1_price"],
        "target2_price": row["target2_price"],
        "scanner_version": row["scanner_version"],
        "analysis_engine_version": row["analysis_engine_version"],
        "policy_version": row["policy_version"],
        "revision_reason": row["revision_reason"],
        "computed_at": row["computed_at"],
    }


def _stock_payload(
    catalog: HoldingsCatalog,
    stock: Any,
    *,
    include_latest_event: bool = False,
) -> dict[str, Any]:
    positions = catalog.list_positions(stock.id, status="OPEN")
    payload: dict[str, Any] = {
        "stock_id": stock.id,
        "market": stock.market,
        "ticker": stock.ticker,
        "name": stock.name,
        "watch_enabled": stock.watch_enabled,
        "is_held": bool(positions),
        "positions": [_position_payload(catalog, item) for item in positions],
        "current_analysis": _current_analysis_payload(catalog, stock.id),
        "decision_context": _decision_service(catalog).build(stock.id),
    }
    if include_latest_event:
        with catalog.connection() as conn:
            row = conn.execute(
                """
                SELECT e.*
                FROM holding_position_event e
                JOIN holding_position p ON p.id=e.position_id
                WHERE p.monitored_stock_id=?
                ORDER BY e.created_at DESC,e.id DESC
                LIMIT 1
                """,
                (stock.id,),
            ).fetchone()
        payload["latest_position_event"] = (
            _event_payload(catalog._event_from_row(row)) if row else None
        )
    return payload


def _ensure_default_manual_account(catalog: HoldingsCatalog) -> Any:
    with catalog.connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM position_account
            WHERE provider='MANUAL'
              AND account_kind='MANUAL'
              AND status='ACTIVE'
            ORDER BY created_at,id
            LIMIT 1
            """
        ).fetchone()
    if row is not None:
        return catalog._account_from_row(row)
    try:
        return catalog.create_position_account(
            provider="MANUAL",
            account_kind="MANUAL",
            display_name="수동 기록",
        )
    except HoldingsCatalogError:
        with catalog.connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM position_account
                WHERE provider='MANUAL'
                  AND account_kind='MANUAL'
                  AND status='ACTIVE'
                ORDER BY created_at,id
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            raise
        return catalog._account_from_row(row)


def _lifecycle_payload(result: PositionLifecycleResult) -> dict[str, Any]:
    return {
        "position": {
            "position_id": result.position.id,
            "stock_id": result.position.monitored_stock_id,
            "account_id": result.position.position_account_id,
            "status": result.position.status,
            "quantity": _json_safe(result.position.current_quantity),
            "average_price": _json_safe(result.position.current_average_price),
            "cost_basis": _json_safe(result.position.current_cost_basis),
            "opened_at": result.position.opened_at,
            "closed_at": result.position.closed_at,
        },
        "event": _event_payload(result.event),
    }


def _stored_analysis_payload(
    catalog: HoldingsCatalog,
    stored: StoredAnalysisResult,
) -> dict[str, Any]:
    with catalog.connection() as conn:
        row = conn.execute(
            "SELECT market_date FROM stock_analysis_day WHERE id=?",
            (stored.analysis_day_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "HOLD_ANALYSIS_HISTORY_CONFLICT",
                "message": "저장된 Analysis Day를 다시 확인할 수 없습니다.",
            },
        )
    revision = stored.revision
    return {
        "market_date": row["market_date"],
        "revision_id": revision.id,
        "revision_no": revision.revision_no,
        "created_revision": stored.created_revision,
        "promoted_current": stored.promoted_current,
        "strategy_key": revision.strategy_key,
        "action_state": revision.action_state,
        "risk_state": revision.risk_state,
        "reference_price": _json_safe(revision.reference_price),
        "stop_price": _json_safe(revision.stop_price),
        "target1_price": _json_safe(revision.target1_price),
        "target2_price": _json_safe(revision.target2_price),
        "revision_reason": revision.revision_reason,
        "computed_at": revision.computed_at,
    }


@router.get("/stocks")
def list_stocks() -> list[dict[str, Any]]:
    catalog = _catalog()
    try:
        targets = _history_service(catalog).list_analysis_targets()
        return [_stock_payload(catalog, stock) for stock in targets]
    except (HoldingsCatalogError, HoldingsAnalysisHistoryError) as error:
        _raise_holdings_error(error)


@router.get("/stocks/{stock_id}")
def stock_detail(stock_id: str) -> dict[str, Any]:
    catalog = _catalog()
    try:
        stock = catalog.get_monitored_stock(stock_id)
        return _stock_payload(catalog, stock, include_latest_event=True)
    except HoldingsCatalogError as error:
        _raise_holdings_error(error)


@router.get("/stocks/{stock_id}/chart")
def stock_chart(
    stock_id: str,
    chart_range: Literal["1m", "3m", "6m", "1y"] = Query(default="1m", alias="range"),
) -> dict[str, Any]:
    catalog = _catalog()
    try:
        stock = catalog.get_monitored_stock(stock_id)
        if stock is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "HOLD_STOCK_NOT_FOUND",
                    "message": "등록된 종목을 찾을 수 없습니다.",
                },
            )
        result = _chart_service().load(
            market=stock.market,
            ticker=stock.ticker,
            chart_range=chart_range,
        )
        return result.to_dict()
    except (HoldingsCatalogError, HoldingsChartError) as error:
        _raise_holdings_error(error)


@router.post("/watch")
def register_watch(request: WatchStockRequest) -> dict[str, Any]:
    catalog = _catalog()
    market = request.market.upper()
    ticker = request.ticker.strip()
    with catalog.connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM monitored_stock
            WHERE market=? AND ticker=?
            """,
            (market, ticker),
        ).fetchone()
    if row is not None:
        stock = catalog._stock_from_row(row)
        if stock.archived_at is not None:
            now = _now()
            with catalog.connection() as conn:
                conn.execute(
                    """
                    UPDATE monitored_stock
                    SET archived_at=NULL,watch_enabled=1,updated_at=?
                    WHERE id=?
                    """,
                    (now, stock.id),
                )
            stock = catalog.get_monitored_stock(stock.id)
        elif not stock.watch_enabled:
            stock = catalog.set_watch_enabled(stock.id, True)
        return {"created": False, "stock": _stock_payload(catalog, stock)}

    try:
        stock = catalog.create_monitored_stock(
            market=market,
            ticker=ticker,
            name=request.name.strip(),
            watch_enabled=True,
        )
        return {"created": True, "stock": _stock_payload(catalog, stock)}
    except HoldingsCatalogError as error:
        _raise_holdings_error(error)


@router.patch("/stocks/{stock_id}/watch")
def set_watch_state(
    stock_id: str,
    request: WatchStateRequest,
) -> dict[str, Any]:
    catalog = _catalog()
    try:
        stock = catalog.set_watch_enabled(stock_id, request.enabled)
        return {"stock": _stock_payload(catalog, stock)}
    except HoldingsCatalogError as error:
        _raise_holdings_error(error)


@router.get("/accounts")
def list_accounts() -> list[dict[str, Any]]:
    catalog = _catalog()
    with catalog.connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM position_account
            WHERE status='ACTIVE'
            ORDER BY account_kind,provider,display_name,id
            """
        ).fetchall()
    return [_account_payload(catalog._account_from_row(row)) for row in rows]


@router.post("/manual/buy")
def record_manual_buy(request: ManualBuyRequest) -> dict[str, Any]:
    catalog = _catalog()
    try:
        account_id = request.account_id
        if account_id is None:
            account_id = _ensure_default_manual_account(catalog).id
        result = _lifecycle_service(catalog).record_buy(
            monitored_stock_id=request.stock_id,
            position_account_id=account_id,
            quantity=request.quantity,
            unit_price=request.unit_price,
            effective_at=request.effective_at,
            analysis_revision_id=request.analysis_revision_id,
            note=request.note,
        )
        return _lifecycle_payload(result)
    except (HoldingsCatalogError, HoldingsLifecycleError) as error:
        _raise_holdings_error(error)


@router.post("/manual/{position_id}/sell")
def record_manual_sell(
    position_id: str,
    request: ManualSellRequest,
) -> dict[str, Any]:
    catalog = _catalog()
    try:
        result = _lifecycle_service(catalog).record_sell(
            position_id=position_id,
            quantity=request.quantity,
            unit_price=request.unit_price,
            effective_at=request.effective_at,
            note=request.note,
        )
        return _lifecycle_payload(result)
    except (HoldingsCatalogError, HoldingsLifecycleError) as error:
        _raise_holdings_error(error)


@router.post("/manual/{position_id}/correction")
def record_manual_correction(
    position_id: str,
    request: ManualCorrectionRequest,
) -> dict[str, Any]:
    catalog = _catalog()
    try:
        result = _lifecycle_service(catalog).record_correction(
            position_id=position_id,
            corrected_quantity=request.quantity,
            corrected_average_price=request.average_price,
            effective_at=request.effective_at,
            note=request.note,
        )
        return _lifecycle_payload(result)
    except (HoldingsCatalogError, HoldingsLifecycleError) as error:
        _raise_holdings_error(error)


@router.get("/stocks/{stock_id}/analysis")
def current_analysis(stock_id: str) -> dict[str, Any]:
    catalog = _catalog()
    try:
        catalog.get_monitored_stock(stock_id)
    except HoldingsCatalogError as error:
        _raise_holdings_error(error)
    analysis = _current_analysis_payload(catalog, stock_id)
    return {"available": analysis is not None, "analysis": analysis}


@router.post("/stocks/{stock_id}/analysis/refresh")
async def refresh_analysis(
    stock_id: str,
    prepare_latest: bool = Query(default=False),
) -> dict[str, Any]:
    catalog = _catalog()
    try:
        # Existing API callers keep the HOLD.1-F behavior and make no external
        # freshness request. The UI opts in only when the user clicks 새로고침.
        if not prepare_latest:
            stored = _history_service(catalog).analyze_latest_confirmed(
                monitored_stock_id=stock_id,
            )
            return _stored_analysis_payload(catalog, stored)

        stock = catalog.get_monitored_stock(stock_id)
        if stock is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "HOLD_STOCK_NOT_FOUND",
                    "message": "등록된 종목을 찾을 수 없습니다.",
                },
            )

        current = _current_analysis_payload(catalog, stock_id)
        known_data_date = current.get("market_date") if current else None
        freshness = await _freshness_service().prepare(
            market=stock.market,
            known_data_date=known_data_date,
        )

        # Freshness updates the same Market Store first. Reuse the established
        # HOLD.1-E/F latest-confirmed analysis contract instead of introducing
        # a second analysis path.
        stored = _history_service(catalog).analyze_latest_confirmed(
            monitored_stock_id=stock_id,
        )
        payload = _stored_analysis_payload(catalog, stored)
        if payload.get("market_date") != freshness.resolved_as_of_date:
            raise HoldingsMarketFreshnessError(
                "HOLD_ANALYSIS_HISTORY_CONFLICT",
                "최신 확정 시세 준비일과 실제 분석 기준일이 일치하지 않습니다.",
            )
        payload["previous_analysis_date"] = known_data_date
        payload["data_freshness"] = freshness.to_dict()
        return payload
    except (
        HoldingsCatalogError,
        HoldingsAnalysisHistoryError,
        HoldingsMarketFreshnessError,
    ) as error:
        _raise_holdings_error(error)


@router.get("/stocks/{stock_id}/analysis/timeline")
def analysis_timeline(
    stock_id: str,
    limit: int = Query(default=30, ge=1, le=365),
) -> list[dict[str, Any]]:
    catalog = _catalog()
    try:
        items = _history_service(catalog).get_analysis_timeline(
            stock_id,
            limit=limit,
        )
    except (HoldingsCatalogError, HoldingsAnalysisHistoryError) as error:
        _raise_holdings_error(error)

    return [
        {
            "market_date": item.market_date,
            "analysis_day_id": item.analysis_day_id,
            "revision_id": item.revision_id,
            "revision_no": item.revision_no,
            "computed_at": item.computed_at,
            "strategy_key": item.strategy_key,
            "action_state": item.action_state,
            "risk_state": item.risk_state,
            "reference_price": _json_safe(item.reference_price),
            "stop_price": _json_safe(item.stop_price),
            "target1_price": _json_safe(item.target1_price),
            "target2_price": _json_safe(item.target2_price),
            "previous": {
                "strategy_key": item.previous_strategy_key,
                "action_state": item.previous_action_state,
                "risk_state": item.previous_risk_state,
                "reference_price": _json_safe(item.previous_reference_price),
                "stop_price": _json_safe(item.previous_stop_price),
                "target1_price": _json_safe(item.previous_target1_price),
                "target2_price": _json_safe(item.previous_target2_price),
            },
            "changes": {
                "strategy": item.strategy_changed,
                "action": item.action_changed,
                "risk": item.risk_changed,
                "reference_price": item.reference_price_changed,
                "stop_price": item.stop_price_changed,
                "target1_price": item.target1_price_changed,
                "target2_price": item.target2_price_changed,
            },
            "deltas": {
                "reference_price": _json_safe(item.reference_price_delta),
                "stop_price": _json_safe(item.stop_price_delta),
                "target1_price": _json_safe(item.target1_price_delta),
                "target2_price": _json_safe(item.target2_price_delta),
            },
        }
        for item in items
    ]


@router.get("/stocks/{stock_id}/timeline")
def stock_timeline(
    stock_id: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    catalog = _catalog()
    try:
        items = _history_service(catalog).get_stock_timeline(
            stock_id,
            limit=limit,
        )
    except (HoldingsCatalogError, HoldingsAnalysisHistoryError) as error:
        _raise_holdings_error(error)
    return [
        {
            "kind": item.kind,
            "occurred_at": item.occurred_at,
            "market_date": item.market_date,
            "analysis_revision_id": item.analysis_revision_id,
            "position_id": item.position_id,
            "event_type": item.event_type,
            "payload": _json_safe(item.payload),
        }
        for item in items
    ]


@router.get("/stocks/{stock_id}/analysis/{market_date}/revisions")
def analysis_revisions(
    stock_id: str,
    market_date: str,
) -> list[dict[str, Any]]:
    catalog = _catalog()
    try:
        revisions = _history_service(catalog).get_day_revisions(
            monitored_stock_id=stock_id,
            market_date=market_date,
        )
    except (HoldingsCatalogError, HoldingsAnalysisHistoryError) as error:
        _raise_holdings_error(error)

    return [
        {
            "revision_id": revision.id,
            "revision_no": revision.revision_no,
            "input_fingerprint": revision.input_fingerprint,
            "strategy_key": revision.strategy_key,
            "action_state": revision.action_state,
            "risk_state": revision.risk_state,
            "reference_price": _json_safe(revision.reference_price),
            "stop_price": _json_safe(revision.stop_price),
            "target1_price": _json_safe(revision.target1_price),
            "target2_price": _json_safe(revision.target2_price),
            "scanner_version": revision.scanner_version,
            "analysis_engine_version": revision.analysis_engine_version,
            "policy_version": revision.policy_version,
            "revision_reason": revision.revision_reason,
            "computed_at": revision.computed_at,
        }
        for revision in revisions
    ]


@router.post("/kis/sync")
def sync_kis_balance() -> dict[str, Any]:
    catalog = _catalog()
    try:
        result = _kis_sync_service(catalog).sync()
    except (HoldingsCatalogError, HoldingsKisSyncError) as error:
        _raise_holdings_error(error)

    return {
        "status": result.status,
        "sync_run_id": result.sync_run_id,
        "account_id": result.account_id,
        "observed_at": result.observed_at,
        "page_count": result.page_count,
        "holding_count": result.holding_count,
        "created": result.created_positions,
        "reconciled": result.reconciled_positions,
        "closed": result.closed_positions,
        "unchanged": result.unchanged_positions,
    }
