from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
API_DIR = ROOT / "backend" / "app" / "api"
HOLDINGS_DIR = ROOT / "backend" / "app" / "holdings"

ROUTER = API_DIR / "router.py"
MAIN = ROOT / "backend" / "app" / "main.py"
CONFIG = ROOT / "backend" / "app" / "core" / "config.py"
DATA_SOURCES = API_DIR / "data_sources.py"

HOLDINGS_API = API_DIR / "holdings.py"
INTEGRATIONS_API = API_DIR / "integrations.py"
TEST_HOLDINGS = ROOT / "backend" / "tests" / "test_holdings_api_hold1f.py"
TEST_INTEGRATIONS = ROOT / "backend" / "tests" / "test_integrations_status_hold1f.py"

CATALOG = HOLDINGS_DIR / "catalog.py"
DOMAIN = HOLDINGS_DIR / "domain.py"
ANALYSIS = HOLDINGS_DIR / "analysis.py"
LIFECYCLE = HOLDINGS_DIR / "lifecycle.py"
KIS_SYNC = HOLDINGS_DIR / "kis_sync.py"
ANALYSIS_HISTORY = HOLDINGS_DIR / "analysis_history.py"

HOLDINGS_API_CONTENT = 'from __future__ import annotations\n\nimport os\nfrom datetime import datetime, timezone\nfrom decimal import Decimal\nfrom pathlib import Path\nfrom typing import Any, Literal\n\nfrom fastapi import APIRouter, HTTPException, Query\nfrom pydantic import BaseModel, Field\n\nfrom app.holdings.analysis_history import (\n    HoldingAnalysisHistoryService,\n    HoldingsAnalysisHistoryError,\n    StoredAnalysisResult,\n)\nfrom app.holdings.catalog import (\n    DEFAULT_HOLDINGS_DB,\n    HoldingsCatalog,\n    HoldingsCatalogError,\n)\nfrom app.holdings.kis_sync import (\n    HoldingsKisSyncError,\n    KisAccountSyncService,\n)\nfrom app.holdings.lifecycle import (\n    HoldingsLifecycleError,\n    PositionLifecycleResult,\n    PositionLifecycleService,\n)\n\n\nrouter = APIRouter(prefix="/holdings", tags=["holdings"])\n\n\nclass WatchStockRequest(BaseModel):\n    market: Literal["KOSPI", "KOSDAQ"]\n    ticker: str = Field(pattern=r"^\\d{6}$")\n    name: str = Field(min_length=1, max_length=100)\n\n\nclass WatchStateRequest(BaseModel):\n    enabled: bool\n\n\nclass ManualBuyRequest(BaseModel):\n    stock_id: str = Field(min_length=1)\n    account_id: str | None = None\n    quantity: str = Field(min_length=1, max_length=80)\n    unit_price: str = Field(min_length=1, max_length=80)\n    effective_at: str = Field(min_length=1, max_length=80)\n    analysis_revision_id: str | None = None\n    note: str | None = Field(default=None, max_length=500)\n\n\nclass ManualSellRequest(BaseModel):\n    quantity: str = Field(min_length=1, max_length=80)\n    unit_price: str = Field(min_length=1, max_length=80)\n    effective_at: str = Field(min_length=1, max_length=80)\n    note: str | None = Field(default=None, max_length=500)\n\n\nclass ManualCorrectionRequest(BaseModel):\n    quantity: str = Field(min_length=1, max_length=80)\n    average_price: str = Field(min_length=1, max_length=80)\n    effective_at: str = Field(min_length=1, max_length=80)\n    note: str | None = Field(default=None, max_length=500)\n\n\ndef _now() -> str:\n    return datetime.now(timezone.utc).isoformat()\n\n\ndef _catalog() -> HoldingsCatalog:\n    raw = os.getenv("STOCKSCOPE_HOLDINGS_DB")\n    path = Path(raw) if raw else DEFAULT_HOLDINGS_DB\n    catalog = HoldingsCatalog(path)\n    catalog.initialize()\n    return catalog\n\n\ndef _history_service(catalog: HoldingsCatalog) -> HoldingAnalysisHistoryService:\n    return HoldingAnalysisHistoryService(catalog)\n\n\ndef _lifecycle_service(catalog: HoldingsCatalog) -> PositionLifecycleService:\n    return PositionLifecycleService(catalog)\n\n\ndef _kis_sync_service(catalog: HoldingsCatalog) -> KisAccountSyncService:\n    return KisAccountSyncService(catalog)\n\n\ndef _http_status(code: str) -> int:\n    if "NOT_FOUND" in code:\n        return 404\n    if code in {\n        "HOLD_STOCK_DUPLICATE",\n        "HOLD_ACCOUNT_DUPLICATE",\n        "HOLD_OPEN_POSITION_DUPLICATE",\n        "HOLD_POSITION_ALREADY_CLOSED",\n        "HOLD_POSITION_SELL_EXCEEDS_HOLDING",\n        "HOLD_POSITION_SOURCE_MANAGED_EXTERNALLY",\n        "HOLD_POSITION_EVENT_OUT_OF_ORDER",\n        "HOLD_POSITION_REVISION_FROM_FUTURE",\n        "HOLD_POSITION_REVISION_MISMATCH",\n        "HOLD_POSITION_CONFLICT",\n        "HOLD_KIS_SYNC_CONFIGURATION_ERROR",\n        "HOLD_KIS_SYNC_ACCOUNT_CONFLICT",\n        "HOLD_KIS_SYNC_INCOMPLETE",\n        "HOLD_KIS_SYNC_DUPLICATE_TICKER",\n        "HOLD_KIS_SYNC_MARKET_UNRESOLVED",\n        "HOLD_KIS_SYNC_STORAGE_CONFLICT",\n        "HOLD_ANALYSIS_HISTORY_CONFLICT",\n    }:\n        return 409\n    if code in {\n        "HOLD_KIS_SYNC_BALANCE_FAILED",\n    }:\n        return 502\n    return 400\n\n\ndef _raise_holdings_error(error: Exception) -> None:\n    code = getattr(error, "code", "HOLD_API_ERROR")\n    message = getattr(error, "message", str(error))\n    raise HTTPException(\n        status_code=_http_status(str(code)),\n        detail={"code": str(code), "message": str(message)},\n    ) from error\n\n\ndef _json_safe(value: Any) -> Any:\n    if isinstance(value, Decimal):\n        return format(value, "f")\n    if isinstance(value, dict):\n        return {str(key): _json_safe(item) for key, item in value.items()}\n    if isinstance(value, (list, tuple)):\n        return [_json_safe(item) for item in value]\n    return value\n\n\ndef _account_payload(account: Any) -> dict[str, Any]:\n    return {\n        "id": account.id,\n        "provider": account.provider,\n        "account_kind": account.account_kind,\n        "broker_environment": account.broker_environment,\n        "display_name": account.display_name,\n        "status": account.status,\n    }\n\n\ndef _position_payload(catalog: HoldingsCatalog, position: Any) -> dict[str, Any]:\n    account = catalog.get_position_account(position.position_account_id)\n    return {\n        "position_id": position.id,\n        "account_id": account.id,\n        "provider": account.provider,\n        "account_kind": account.account_kind,\n        "broker_environment": account.broker_environment,\n        "account_name": account.display_name,\n        "status": position.status,\n        "opened_at": position.opened_at,\n        "closed_at": position.closed_at,\n        "quantity": _json_safe(position.current_quantity),\n        "average_price": _json_safe(position.current_average_price),\n        "cost_basis": _json_safe(position.current_cost_basis),\n        "opened_reason": position.opened_reason,\n        "last_observed_at": position.last_observed_at,\n    }\n\n\ndef _event_payload(event: Any) -> dict[str, Any]:\n    return {\n        "event_id": event.id,\n        "position_id": event.position_id,\n        "event_type": event.event_type,\n        "quantity_delta": _json_safe(event.quantity_delta),\n        "unit_price": _json_safe(event.unit_price),\n        "before_quantity": _json_safe(event.before_quantity),\n        "after_quantity": _json_safe(event.after_quantity),\n        "before_average_price": _json_safe(event.before_average_price),\n        "after_average_price": _json_safe(event.after_average_price),\n        "observed_at": event.observed_at,\n        "effective_at": event.effective_at,\n        "analysis_revision_id": event.analysis_revision_id,\n        "account_sync_run_id": event.account_sync_run_id,\n        "note": event.note,\n        "created_at": event.created_at,\n    }\n\n\ndef _current_analysis_payload(\n    catalog: HoldingsCatalog,\n    stock_id: str,\n) -> dict[str, Any] | None:\n    with catalog.connection() as conn:\n        row = conn.execute(\n            """\n            SELECT\n                d.market_date,\n                r.id AS revision_id,\n                r.revision_no,\n                r.strategy_key,\n                r.action_state,\n                r.risk_state,\n                r.reference_price,\n                r.stop_price,\n                r.target1_price,\n                r.target2_price,\n                r.scanner_version,\n                r.analysis_engine_version,\n                r.policy_version,\n                r.revision_reason,\n                r.computed_at\n            FROM stock_analysis_day d\n            JOIN stock_analysis_revision r ON r.id=d.current_revision_id\n            WHERE d.monitored_stock_id=?\n            ORDER BY d.market_date DESC\n            LIMIT 1\n            """,\n            (stock_id,),\n        ).fetchone()\n    if row is None:\n        return None\n    return {\n        "market_date": row["market_date"],\n        "revision_id": row["revision_id"],\n        "revision_no": int(row["revision_no"]),\n        "strategy_key": row["strategy_key"],\n        "action_state": row["action_state"],\n        "risk_state": row["risk_state"],\n        "reference_price": row["reference_price"],\n        "stop_price": row["stop_price"],\n        "target1_price": row["target1_price"],\n        "target2_price": row["target2_price"],\n        "scanner_version": row["scanner_version"],\n        "analysis_engine_version": row["analysis_engine_version"],\n        "policy_version": row["policy_version"],\n        "revision_reason": row["revision_reason"],\n        "computed_at": row["computed_at"],\n    }\n\n\ndef _stock_payload(\n    catalog: HoldingsCatalog,\n    stock: Any,\n    *,\n    include_latest_event: bool = False,\n) -> dict[str, Any]:\n    positions = catalog.list_positions(stock.id, status="OPEN")\n    payload: dict[str, Any] = {\n        "stock_id": stock.id,\n        "market": stock.market,\n        "ticker": stock.ticker,\n        "name": stock.name,\n        "watch_enabled": stock.watch_enabled,\n        "is_held": bool(positions),\n        "positions": [_position_payload(catalog, item) for item in positions],\n        "current_analysis": _current_analysis_payload(catalog, stock.id),\n    }\n    if include_latest_event:\n        with catalog.connection() as conn:\n            row = conn.execute(\n                """\n                SELECT e.*\n                FROM holding_position_event e\n                JOIN holding_position p ON p.id=e.position_id\n                WHERE p.monitored_stock_id=?\n                ORDER BY e.created_at DESC,e.id DESC\n                LIMIT 1\n                """,\n                (stock.id,),\n            ).fetchone()\n        payload["latest_position_event"] = (\n            _event_payload(catalog._event_from_row(row)) if row else None\n        )\n    return payload\n\n\ndef _ensure_default_manual_account(catalog: HoldingsCatalog) -> Any:\n    with catalog.connection() as conn:\n        row = conn.execute(\n            """\n            SELECT *\n            FROM position_account\n            WHERE provider=\'MANUAL\'\n              AND account_kind=\'MANUAL\'\n              AND status=\'ACTIVE\'\n            ORDER BY created_at,id\n            LIMIT 1\n            """\n        ).fetchone()\n    if row is not None:\n        return catalog._account_from_row(row)\n    try:\n        return catalog.create_position_account(\n            provider="MANUAL",\n            account_kind="MANUAL",\n            display_name="수동 기록",\n        )\n    except HoldingsCatalogError:\n        with catalog.connection() as conn:\n            row = conn.execute(\n                """\n                SELECT *\n                FROM position_account\n                WHERE provider=\'MANUAL\'\n                  AND account_kind=\'MANUAL\'\n                  AND status=\'ACTIVE\'\n                ORDER BY created_at,id\n                LIMIT 1\n                """\n            ).fetchone()\n        if row is None:\n            raise\n        return catalog._account_from_row(row)\n\n\ndef _lifecycle_payload(result: PositionLifecycleResult) -> dict[str, Any]:\n    return {\n        "position": {\n            "position_id": result.position.id,\n            "stock_id": result.position.monitored_stock_id,\n            "account_id": result.position.position_account_id,\n            "status": result.position.status,\n            "quantity": _json_safe(result.position.current_quantity),\n            "average_price": _json_safe(result.position.current_average_price),\n            "cost_basis": _json_safe(result.position.current_cost_basis),\n            "opened_at": result.position.opened_at,\n            "closed_at": result.position.closed_at,\n        },\n        "event": _event_payload(result.event),\n    }\n\n\ndef _stored_analysis_payload(\n    catalog: HoldingsCatalog,\n    stored: StoredAnalysisResult,\n) -> dict[str, Any]:\n    with catalog.connection() as conn:\n        row = conn.execute(\n            "SELECT market_date FROM stock_analysis_day WHERE id=?",\n            (stored.analysis_day_id,),\n        ).fetchone()\n    if row is None:\n        raise HTTPException(\n            status_code=409,\n            detail={\n                "code": "HOLD_ANALYSIS_HISTORY_CONFLICT",\n                "message": "저장된 Analysis Day를 다시 확인할 수 없습니다.",\n            },\n        )\n    revision = stored.revision\n    return {\n        "market_date": row["market_date"],\n        "revision_id": revision.id,\n        "revision_no": revision.revision_no,\n        "created_revision": stored.created_revision,\n        "promoted_current": stored.promoted_current,\n        "strategy_key": revision.strategy_key,\n        "action_state": revision.action_state,\n        "risk_state": revision.risk_state,\n        "reference_price": _json_safe(revision.reference_price),\n        "stop_price": _json_safe(revision.stop_price),\n        "target1_price": _json_safe(revision.target1_price),\n        "target2_price": _json_safe(revision.target2_price),\n        "revision_reason": revision.revision_reason,\n        "computed_at": revision.computed_at,\n    }\n\n\n@router.get("/stocks")\ndef list_stocks() -> list[dict[str, Any]]:\n    catalog = _catalog()\n    try:\n        targets = _history_service(catalog).list_analysis_targets()\n        return [_stock_payload(catalog, stock) for stock in targets]\n    except (HoldingsCatalogError, HoldingsAnalysisHistoryError) as error:\n        _raise_holdings_error(error)\n\n\n@router.get("/stocks/{stock_id}")\ndef stock_detail(stock_id: str) -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        stock = catalog.get_monitored_stock(stock_id)\n        return _stock_payload(catalog, stock, include_latest_event=True)\n    except HoldingsCatalogError as error:\n        _raise_holdings_error(error)\n\n\n@router.post("/watch")\ndef register_watch(request: WatchStockRequest) -> dict[str, Any]:\n    catalog = _catalog()\n    market = request.market.upper()\n    ticker = request.ticker.strip()\n    with catalog.connection() as conn:\n        row = conn.execute(\n            """\n            SELECT *\n            FROM monitored_stock\n            WHERE market=? AND ticker=?\n            """,\n            (market, ticker),\n        ).fetchone()\n    if row is not None:\n        stock = catalog._stock_from_row(row)\n        if stock.archived_at is not None:\n            now = _now()\n            with catalog.connection() as conn:\n                conn.execute(\n                    """\n                    UPDATE monitored_stock\n                    SET archived_at=NULL,watch_enabled=1,updated_at=?\n                    WHERE id=?\n                    """,\n                    (now, stock.id),\n                )\n            stock = catalog.get_monitored_stock(stock.id)\n        elif not stock.watch_enabled:\n            stock = catalog.set_watch_enabled(stock.id, True)\n        return {"created": False, "stock": _stock_payload(catalog, stock)}\n\n    try:\n        stock = catalog.create_monitored_stock(\n            market=market,\n            ticker=ticker,\n            name=request.name.strip(),\n            watch_enabled=True,\n        )\n        return {"created": True, "stock": _stock_payload(catalog, stock)}\n    except HoldingsCatalogError as error:\n        _raise_holdings_error(error)\n\n\n@router.patch("/stocks/{stock_id}/watch")\ndef set_watch_state(\n    stock_id: str,\n    request: WatchStateRequest,\n) -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        stock = catalog.set_watch_enabled(stock_id, request.enabled)\n        return {"stock": _stock_payload(catalog, stock)}\n    except HoldingsCatalogError as error:\n        _raise_holdings_error(error)\n\n\n@router.get("/accounts")\ndef list_accounts() -> list[dict[str, Any]]:\n    catalog = _catalog()\n    with catalog.connection() as conn:\n        rows = conn.execute(\n            """\n            SELECT *\n            FROM position_account\n            WHERE status=\'ACTIVE\'\n            ORDER BY account_kind,provider,display_name,id\n            """\n        ).fetchall()\n    return [_account_payload(catalog._account_from_row(row)) for row in rows]\n\n\n@router.post("/manual/buy")\ndef record_manual_buy(request: ManualBuyRequest) -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        account_id = request.account_id\n        if account_id is None:\n            account_id = _ensure_default_manual_account(catalog).id\n        result = _lifecycle_service(catalog).record_buy(\n            monitored_stock_id=request.stock_id,\n            position_account_id=account_id,\n            quantity=request.quantity,\n            unit_price=request.unit_price,\n            effective_at=request.effective_at,\n            analysis_revision_id=request.analysis_revision_id,\n            note=request.note,\n        )\n        return _lifecycle_payload(result)\n    except (HoldingsCatalogError, HoldingsLifecycleError) as error:\n        _raise_holdings_error(error)\n\n\n@router.post("/manual/{position_id}/sell")\ndef record_manual_sell(\n    position_id: str,\n    request: ManualSellRequest,\n) -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        result = _lifecycle_service(catalog).record_sell(\n            position_id=position_id,\n            quantity=request.quantity,\n            unit_price=request.unit_price,\n            effective_at=request.effective_at,\n            note=request.note,\n        )\n        return _lifecycle_payload(result)\n    except (HoldingsCatalogError, HoldingsLifecycleError) as error:\n        _raise_holdings_error(error)\n\n\n@router.post("/manual/{position_id}/correction")\ndef record_manual_correction(\n    position_id: str,\n    request: ManualCorrectionRequest,\n) -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        result = _lifecycle_service(catalog).record_correction(\n            position_id=position_id,\n            corrected_quantity=request.quantity,\n            corrected_average_price=request.average_price,\n            effective_at=request.effective_at,\n            note=request.note,\n        )\n        return _lifecycle_payload(result)\n    except (HoldingsCatalogError, HoldingsLifecycleError) as error:\n        _raise_holdings_error(error)\n\n\n@router.get("/stocks/{stock_id}/analysis")\ndef current_analysis(stock_id: str) -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        catalog.get_monitored_stock(stock_id)\n    except HoldingsCatalogError as error:\n        _raise_holdings_error(error)\n    analysis = _current_analysis_payload(catalog, stock_id)\n    return {"available": analysis is not None, "analysis": analysis}\n\n\n@router.post("/stocks/{stock_id}/analysis/refresh")\ndef refresh_analysis(stock_id: str) -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        stored = _history_service(catalog).analyze_latest_confirmed(\n            monitored_stock_id=stock_id,\n        )\n        return _stored_analysis_payload(catalog, stored)\n    except (HoldingsCatalogError, HoldingsAnalysisHistoryError) as error:\n        _raise_holdings_error(error)\n\n\n@router.get("/stocks/{stock_id}/analysis/timeline")\ndef analysis_timeline(\n    stock_id: str,\n    limit: int = Query(default=30, ge=1, le=365),\n) -> list[dict[str, Any]]:\n    catalog = _catalog()\n    try:\n        items = _history_service(catalog).get_analysis_timeline(\n            stock_id,\n            limit=limit,\n        )\n    except (HoldingsCatalogError, HoldingsAnalysisHistoryError) as error:\n        _raise_holdings_error(error)\n\n    return [\n        {\n            "market_date": item.market_date,\n            "analysis_day_id": item.analysis_day_id,\n            "revision_id": item.revision_id,\n            "revision_no": item.revision_no,\n            "computed_at": item.computed_at,\n            "strategy_key": item.strategy_key,\n            "action_state": item.action_state,\n            "risk_state": item.risk_state,\n            "reference_price": _json_safe(item.reference_price),\n            "stop_price": _json_safe(item.stop_price),\n            "target1_price": _json_safe(item.target1_price),\n            "target2_price": _json_safe(item.target2_price),\n            "previous": {\n                "strategy_key": item.previous_strategy_key,\n                "action_state": item.previous_action_state,\n                "risk_state": item.previous_risk_state,\n                "reference_price": _json_safe(item.previous_reference_price),\n                "stop_price": _json_safe(item.previous_stop_price),\n                "target1_price": _json_safe(item.previous_target1_price),\n                "target2_price": _json_safe(item.previous_target2_price),\n            },\n            "changes": {\n                "strategy": item.strategy_changed,\n                "action": item.action_changed,\n                "risk": item.risk_changed,\n                "reference_price": item.reference_price_changed,\n                "stop_price": item.stop_price_changed,\n                "target1_price": item.target1_price_changed,\n                "target2_price": item.target2_price_changed,\n            },\n            "deltas": {\n                "reference_price": _json_safe(item.reference_price_delta),\n                "stop_price": _json_safe(item.stop_price_delta),\n                "target1_price": _json_safe(item.target1_price_delta),\n                "target2_price": _json_safe(item.target2_price_delta),\n            },\n        }\n        for item in items\n    ]\n\n\n@router.get("/stocks/{stock_id}/timeline")\ndef stock_timeline(\n    stock_id: str,\n    limit: int = Query(default=100, ge=1, le=500),\n) -> list[dict[str, Any]]:\n    catalog = _catalog()\n    try:\n        items = _history_service(catalog).get_stock_timeline(\n            stock_id,\n            limit=limit,\n        )\n    except (HoldingsCatalogError, HoldingsAnalysisHistoryError) as error:\n        _raise_holdings_error(error)\n    return [\n        {\n            "kind": item.kind,\n            "occurred_at": item.occurred_at,\n            "market_date": item.market_date,\n            "analysis_revision_id": item.analysis_revision_id,\n            "position_id": item.position_id,\n            "event_type": item.event_type,\n            "payload": _json_safe(item.payload),\n        }\n        for item in items\n    ]\n\n\n@router.get("/stocks/{stock_id}/analysis/{market_date}/revisions")\ndef analysis_revisions(\n    stock_id: str,\n    market_date: str,\n) -> list[dict[str, Any]]:\n    catalog = _catalog()\n    try:\n        revisions = _history_service(catalog).get_day_revisions(\n            monitored_stock_id=stock_id,\n            market_date=market_date,\n        )\n    except (HoldingsCatalogError, HoldingsAnalysisHistoryError) as error:\n        _raise_holdings_error(error)\n\n    return [\n        {\n            "revision_id": revision.id,\n            "revision_no": revision.revision_no,\n            "input_fingerprint": revision.input_fingerprint,\n            "strategy_key": revision.strategy_key,\n            "action_state": revision.action_state,\n            "risk_state": revision.risk_state,\n            "reference_price": _json_safe(revision.reference_price),\n            "stop_price": _json_safe(revision.stop_price),\n            "target1_price": _json_safe(revision.target1_price),\n            "target2_price": _json_safe(revision.target2_price),\n            "scanner_version": revision.scanner_version,\n            "analysis_engine_version": revision.analysis_engine_version,\n            "policy_version": revision.policy_version,\n            "revision_reason": revision.revision_reason,\n            "computed_at": revision.computed_at,\n        }\n        for revision in revisions\n    ]\n\n\n@router.post("/kis/sync")\ndef sync_kis_balance() -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        result = _kis_sync_service(catalog).sync()\n    except (HoldingsCatalogError, HoldingsKisSyncError) as error:\n        _raise_holdings_error(error)\n\n    return {\n        "status": result.status,\n        "sync_run_id": result.sync_run_id,\n        "account_id": result.account_id,\n        "observed_at": result.observed_at,\n        "page_count": result.page_count,\n        "holding_count": result.holding_count,\n        "created": result.created_positions,\n        "reconciled": result.reconciled_positions,\n        "closed": result.closed_positions,\n        "unchanged": result.unchanged_positions,\n    }\n'
INTEGRATIONS_API_CONTENT = 'from __future__ import annotations\n\nfrom typing import Any, Literal\n\nfrom fastapi import APIRouter, HTTPException\nfrom starlette.concurrency import run_in_threadpool\n\nfrom app.core.config import Settings, get_settings\nfrom app.integrations.kis.account import KisAccountError, inquire_domestic_balance\nfrom app.integrations.kis.client import KisConfigurationError\nfrom app.market.providers import KrxProvider, OpenDartProvider\nfrom app.market.providers.base import ProviderError, ProviderNotConfigured\n\n\nrouter = APIRouter(prefix="/integrations", tags=["integrations"])\nProviderName = Literal["kis", "krx", "dart"]\n\n\ndef _configured(settings: Settings) -> dict[str, bool]:\n    return {\n        "kis": bool(\n            settings.kis_app_key\n            and settings.kis_app_secret\n            and settings.kis_account_no\n            and settings.kis_account_product_code\n        ),\n        "krx": bool(settings.krx_api_key),\n        "dart": bool(settings.dart_api_key),\n    }\n\n\ndef _status_payload(settings: Settings) -> dict[str, Any]:\n    configured = _configured(settings)\n    return {\n        "kis": {\n            "configured": configured["kis"],\n            "status": "CONFIGURED" if configured["kis"] else "NOT_CONFIGURED",\n            "role": "실계좌 잔고 · 현재가 · 실시간 시세",\n            "check_supported": True,\n        },\n        "krx": {\n            "configured": configured["krx"],\n            "status": "CONFIGURED" if configured["krx"] else "NOT_CONFIGURED",\n            "role": "시장 · 종목 · 일별 시세 · 지수",\n            "check_supported": True,\n        },\n        "dart": {\n            "configured": configured["dart"],\n            "status": "CONFIGURED" if configured["dart"] else "NOT_CONFIGURED",\n            "role": "기업 · 공시 · 재무 정보",\n            "check_supported": True,\n        },\n    }\n\n\n@router.get("/status")\ndef integration_status() -> dict[str, Any]:\n    return _status_payload(get_settings())\n\n\nasync def _check_kis(settings: Settings) -> dict[str, Any]:\n    balance = await run_in_threadpool(inquire_domestic_balance, settings)\n    return {\n        "configured": True,\n        "reachable": True,\n        "holding_count": len(balance.holdings),\n        "page_count": balance.page_count,\n    }\n\n\nasync def _check_krx(settings: Settings) -> dict[str, Any]:\n    provider = KrxProvider(settings.krx_api_key)\n    try:\n        result = await provider.latest_basic_info("KOSPI")\n    finally:\n        await provider.close_session()\n    return {\n        "configured": True,\n        "reachable": True,\n        "date": result.get("date"),\n        "count": result.get("count"),\n    }\n\n\nasync def _check_dart(settings: Settings) -> dict[str, Any]:\n    provider = OpenDartProvider(settings.dart_api_key)\n    result = await provider.company("00126380")\n    return {\n        "configured": True,\n        "reachable": True,\n        "provider": "OpenDART",\n        "sample_stock_code": result.get("stock_code"),\n    }\n\n\n@router.post("/{provider}/check")\nasync def check_integration(provider: ProviderName) -> dict[str, Any]:\n    settings = get_settings()\n    configured = _configured(settings)\n    if not configured[provider]:\n        raise HTTPException(\n            status_code=409,\n            detail={\n                "code": f"{provider.upper()}_NOT_CONFIGURED",\n                "message": f"{provider.upper()} 연동 설정이 필요합니다.",\n            },\n        )\n\n    try:\n        if provider == "kis":\n            result = await _check_kis(settings)\n        elif provider == "krx":\n            result = await _check_krx(settings)\n        else:\n            result = await _check_dart(settings)\n    except (KisConfigurationError, ProviderNotConfigured) as exc:\n        raise HTTPException(\n            status_code=409,\n            detail={\n                "code": f"{provider.upper()}_NOT_CONFIGURED",\n                "message": str(exc),\n            },\n        ) from exc\n    except (KisAccountError, ProviderError) as exc:\n        raise HTTPException(\n            status_code=502,\n            detail={\n                "code": f"{provider.upper()}_CONNECTION_FAILED",\n                "message": str(exc),\n            },\n        ) from exc\n    except ValueError as exc:\n        raise HTTPException(\n            status_code=400,\n            detail={\n                "code": f"{provider.upper()}_CHECK_INVALID",\n                "message": str(exc),\n            },\n        ) from exc\n\n    return {\n        "provider": provider,\n        "status": "CONNECTED",\n        **result,\n    }\n'
TEST_HOLDINGS_CONTENT = 'from __future__ import annotations\n\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\nimport pytest\nfrom fastapi import FastAPI\nfrom fastapi.testclient import TestClient\n\nimport app.api.holdings as holdings_api\nfrom app.holdings import HoldingsCatalog\n\n\n@pytest.fixture()\ndef client(tmp_path, monkeypatch):\n    db = tmp_path / "holdings.db"\n    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(db))\n    app = FastAPI()\n    app.include_router(holdings_api.router, prefix="/api")\n    return TestClient(app)\n\n\ndef _catalog_from_env(monkeypatch, tmp_path):\n    db = tmp_path / "holdings.db"\n    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(db))\n    catalog = HoldingsCatalog(db)\n    catalog.initialize()\n    return catalog\n\n\ndef test_watch_registration_is_idempotent_and_watch_off_keeps_held_stock(client):\n    first = client.post(\n        "/api/holdings/watch",\n        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},\n    )\n    assert first.status_code == 200\n    assert first.json()["created"] is True\n    stock_id = first.json()["stock"]["stock_id"]\n\n    second = client.post(\n        "/api/holdings/watch",\n        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},\n    )\n    assert second.status_code == 200\n    assert second.json()["created"] is False\n    assert second.json()["stock"]["stock_id"] == stock_id\n\n    bought = client.post(\n        "/api/holdings/manual/buy",\n        json={\n            "stock_id": stock_id,\n            "quantity": "10",\n            "unit_price": "70000",\n            "effective_at": "2026-09-23T09:00:00+09:00",\n        },\n    )\n    assert bought.status_code == 200\n    assert bought.json()["position"]["quantity"] == "10"\n    assert bought.json()["position"]["average_price"] == "70000"\n\n    disabled = client.patch(\n        f"/api/holdings/stocks/{stock_id}/watch",\n        json={"enabled": False},\n    )\n    assert disabled.status_code == 200\n    assert disabled.json()["stock"]["watch_enabled"] is False\n    assert disabled.json()["stock"]["is_held"] is True\n\n    listing = client.get("/api/holdings/stocks")\n    assert listing.status_code == 200\n    assert len(listing.json()) == 1\n    assert listing.json()[0]["stock_id"] == stock_id\n\n\ndef test_manual_sell_correction_and_broker_guard(client):\n    watched = client.post(\n        "/api/holdings/watch",\n        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},\n    ).json()\n    stock_id = watched["stock"]["stock_id"]\n\n    bought = client.post(\n        "/api/holdings/manual/buy",\n        json={\n            "stock_id": stock_id,\n            "quantity": "10",\n            "unit_price": "70000",\n            "effective_at": "2026-09-23T09:00:00+09:00",\n        },\n    ).json()\n    position_id = bought["position"]["position_id"]\n\n    oversell = client.post(\n        f"/api/holdings/manual/{position_id}/sell",\n        json={\n            "quantity": "11",\n            "unit_price": "71000",\n            "effective_at": "2026-09-23T10:00:00+09:00",\n        },\n    )\n    assert oversell.status_code == 409\n    assert oversell.json()["detail"]["code"] == "HOLD_POSITION_SELL_EXCEEDS_HOLDING"\n\n    correction = client.post(\n        f"/api/holdings/manual/{position_id}/correction",\n        json={\n            "quantity": "9",\n            "average_price": "70500",\n            "effective_at": "2026-09-23T10:01:00+09:00",\n            "note": None,\n        },\n    )\n    assert correction.status_code == 400\n    assert correction.json()["detail"]["code"] == "HOLD_POSITION_CORRECTION_NOTE_REQUIRED"\n\n    sold = client.post(\n        f"/api/holdings/manual/{position_id}/sell",\n        json={\n            "quantity": "5",\n            "unit_price": "72000",\n            "effective_at": "2026-09-23T10:02:00+09:00",\n        },\n    )\n    assert sold.status_code == 200\n    assert sold.json()["position"]["quantity"] == "5"\n\n    catalog = holdings_api._catalog()\n    account = catalog.create_position_account(\n        provider="KIS",\n        account_kind="BROKER",\n        broker_environment="REAL",\n        external_account_fingerprint="a" * 64,\n        display_name="한국투자증권 실계좌",\n    )\n    broker_position = catalog.open_position(\n        monitored_stock_id=stock_id,\n        position_account_id=account.id,\n        opened_reason="KIS_OBSERVED",\n        current_quantity="1",\n        current_average_price="70000",\n        current_cost_basis="70000",\n    )\n    blocked = client.post(\n        f"/api/holdings/manual/{broker_position.id}/sell",\n        json={\n            "quantity": "1",\n            "unit_price": "70000",\n            "effective_at": "2026-09-23T10:03:00+09:00",\n        },\n    )\n    assert blocked.status_code == 409\n    assert blocked.json()["detail"]["code"] == "HOLD_POSITION_SOURCE_MANAGED_EXTERNALLY"\n\n\ndef test_accounts_and_stock_detail_use_separate_account_positions(client):\n    stock_id = client.post(\n        "/api/holdings/watch",\n        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},\n    ).json()["stock"]["stock_id"]\n    client.post(\n        "/api/holdings/manual/buy",\n        json={\n            "stock_id": stock_id,\n            "quantity": "2",\n            "unit_price": "70000",\n            "effective_at": "2026-09-23T09:00:00+09:00",\n        },\n    )\n    accounts = client.get("/api/holdings/accounts")\n    assert accounts.status_code == 200\n    assert len(accounts.json()) == 1\n    assert accounts.json()[0]["account_kind"] == "MANUAL"\n\n    detail = client.get(f"/api/holdings/stocks/{stock_id}")\n    assert detail.status_code == 200\n    assert detail.json()["is_held"] is True\n    assert len(detail.json()["positions"]) == 1\n    assert detail.json()["positions"][0]["quantity"] == "2"\n    assert detail.json()["latest_position_event"]["event_type"] == "BUY"\n\n\ndef test_analysis_read_timeline_revision_and_refresh_contract(client, monkeypatch):\n    stock_id = client.post(\n        "/api/holdings/watch",\n        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},\n    ).json()["stock"]["stock_id"]\n\n    empty = client.get(f"/api/holdings/stocks/{stock_id}/analysis")\n    assert empty.status_code == 200\n    assert empty.json() == {"available": False, "analysis": None}\n\n    catalog = holdings_api._catalog()\n    day = catalog.get_or_create_analysis_day(\n        monitored_stock_id=stock_id,\n        market_date="2026-09-18",\n    )\n    revision = catalog.append_analysis_revision(\n        analysis_day_id=day.id,\n        input_fingerprint="fp-api",\n        strategy_key="ma20_rebound",\n        action_state="WATCH",\n        risk_state="READY",\n        reference_price="261000",\n        stop_price="254124.8",\n        target1_price="271000",\n        target2_price="274750.4",\n        scanner_version="0.21.3.7",\n        analysis_engine_version="HOLD_SINGLE_STOCK_V1",\n        policy_version="P1",\n        source_versions={"fixture": "api"},\n        snapshot={"fixture": True},\n        revision_reason="INITIAL",\n        computed_at="2026-09-23T00:00:00+00:00",\n    )\n    catalog.promote_current_revision(\n        analysis_day_id=day.id,\n        revision_id=revision.id,\n    )\n\n    current = client.get(f"/api/holdings/stocks/{stock_id}/analysis")\n    assert current.status_code == 200\n    assert current.json()["available"] is True\n    assert current.json()["analysis"]["market_date"] == "2026-09-18"\n    assert current.json()["analysis"]["reference_price"] == "261000"\n\n    revisions = client.get(\n        f"/api/holdings/stocks/{stock_id}/analysis/2026-09-18/revisions"\n    )\n    assert revisions.status_code == 200\n    assert len(revisions.json()) == 1\n    assert revisions.json()[0]["revision_id"] == revision.id\n\n    timeline = client.get(f"/api/holdings/stocks/{stock_id}/analysis/timeline")\n    assert timeline.status_code == 200\n    assert len(timeline.json()) == 1\n    assert timeline.json()[0]["reference_price"] == "261000"\n\n    stored = SimpleNamespace(\n        analysis_day_id=day.id,\n        revision=revision,\n        created_revision=False,\n        promoted_current=False,\n    )\n    fake = SimpleNamespace(\n        analyze_latest_confirmed=lambda **kwargs: stored,\n    )\n    monkeypatch.setattr(holdings_api, "_history_service", lambda catalog: fake)\n    refreshed = client.post(f"/api/holdings/stocks/{stock_id}/analysis/refresh")\n    assert refreshed.status_code == 200\n    assert refreshed.json()["market_date"] == "2026-09-18"\n    assert refreshed.json()["created_revision"] is False\n\n\ndef test_combined_timeline_and_kis_sync_endpoint_delegate_only(client, monkeypatch):\n    stock_id = client.post(\n        "/api/holdings/watch",\n        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},\n    ).json()["stock"]["stock_id"]\n    client.post(\n        "/api/holdings/manual/buy",\n        json={\n            "stock_id": stock_id,\n            "quantity": "1",\n            "unit_price": "70000",\n            "effective_at": "2026-09-23T09:00:00+09:00",\n        },\n    )\n    timeline = client.get(f"/api/holdings/stocks/{stock_id}/timeline")\n    assert timeline.status_code == 200\n    assert any(item["kind"] == "POSITION_EVENT" for item in timeline.json())\n\n    result = SimpleNamespace(\n        status="COMPLETED",\n        sync_run_id="sync-1",\n        account_id="account-1",\n        observed_at="2026-09-23T00:00:00+00:00",\n        page_count=1,\n        holding_count=0,\n        created_positions=0,\n        reconciled_positions=0,\n        closed_positions=0,\n        unchanged_positions=0,\n    )\n    fake = SimpleNamespace(sync=lambda: result)\n    monkeypatch.setattr(holdings_api, "_kis_sync_service", lambda catalog: fake)\n\n    response = client.post("/api/holdings/kis/sync")\n    assert response.status_code == 200\n    assert response.json()["status"] == "COMPLETED"\n    assert response.json()["holding_count"] == 0\n\n\ndef test_router_has_no_scanner_strategy_risk_or_order_implementation():\n    source = Path("backend/app/api/holdings.py").read_text(encoding="utf-8")\n    assert "StockScannerService" not in source\n    assert "app.strategy" not in source\n    assert "app.risk" not in source\n    assert "place_order" not in source\n    assert "order_cash" not in source\n'
TEST_INTEGRATIONS_CONTENT = 'from __future__ import annotations\n\nfrom types import SimpleNamespace\n\nimport pytest\nfrom fastapi import FastAPI\nfrom fastapi.testclient import TestClient\n\nimport app.api.integrations as integrations_api\n\n\n@pytest.fixture()\ndef client():\n    app = FastAPI()\n    app.include_router(integrations_api.router, prefix="/api")\n    return TestClient(app)\n\n\ndef _settings(**overrides):\n    values = {\n        "kis_app_key": "kis-key",\n        "kis_app_secret": "kis-secret",\n        "kis_account_no": "12345678",\n        "kis_account_product_code": "01",\n        "kis_env": "real",\n        "krx_api_key": "krx-secret",\n        "dart_api_key": "dart-secret",\n    }\n    values.update(overrides)\n    return SimpleNamespace(**values)\n\n\ndef test_status_reports_configuration_without_exposing_secrets(client, monkeypatch):\n    settings = _settings(dart_api_key=None)\n    monkeypatch.setattr(integrations_api, "get_settings", lambda: settings)\n\n    response = client.get("/api/integrations/status")\n    assert response.status_code == 200\n    body = response.json()\n    assert body["kis"]["status"] == "CONFIGURED"\n    assert body["krx"]["status"] == "CONFIGURED"\n    assert body["dart"]["status"] == "NOT_CONFIGURED"\n\n    serialized = response.text\n    for secret in (\n        "kis-key",\n        "kis-secret",\n        "12345678",\n        "krx-secret",\n        "dart-secret",\n    ):\n        assert secret not in serialized\n\n\ndef test_check_requires_configuration(client, monkeypatch):\n    settings = _settings(\n        kis_app_key=None,\n        kis_app_secret=None,\n        kis_account_no=None,\n    )\n    monkeypatch.setattr(integrations_api, "get_settings", lambda: settings)\n\n    response = client.post("/api/integrations/kis/check")\n    assert response.status_code == 409\n    assert response.json()["detail"]["code"] == "KIS_NOT_CONFIGURED"\n\n\n@pytest.mark.parametrize("provider", ["kis", "krx", "dart"])\ndef test_explicit_check_delegates_to_read_only_provider_check(\n    client,\n    monkeypatch,\n    provider,\n):\n    settings = _settings()\n    monkeypatch.setattr(integrations_api, "get_settings", lambda: settings)\n\n    calls = []\n    async def fake_check(value):\n        calls.append(value)\n        return {"configured": True, "reachable": True}\n\n    monkeypatch.setattr(integrations_api, f"_check_{provider}", fake_check)\n    response = client.post(f"/api/integrations/{provider}/check")\n    assert response.status_code == 200\n    assert response.json()["provider"] == provider\n    assert response.json()["status"] == "CONNECTED"\n    assert response.json()["reachable"] is True\n    assert calls == [settings]\n\n\ndef test_status_api_does_not_write_env_file():\n    source = open("backend/app/api/integrations.py", encoding="utf-8").read()\n    assert "write_text" not in source\n    assert "dotenv" not in source.lower()\n    assert ".env" not in source\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(cmd: list[str], label: str, *, env: dict[str, str] | None = None) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, env=env)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    if not path.exists():
        return "MISSING"
    files = [path] if path.is_file() else sorted(
        item for item in path.rglob("*.py")
        if "__pycache__" not in item.parts
    )
    for item in files:
        hasher.update(str(item.relative_to(ROOT)).replace("\\", "/").encode())
        hasher.update(b"\0")
        hasher.update(item.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def patch_router(text: str) -> str:
    if "holdings_router" in text or "integrations_router" in text:
        fail("api/router.py already appears to contain HOLD.1-F routes.")

    anchor = "api_router = APIRouter()"
    if text.count(anchor) != 1:
        fail("api/router.py APIRouter anchor was not found exactly once.")

    imports = (
        "from app.api.holdings import router as holdings_router\n"
        "from app.api.integrations import router as integrations_router\n\n"
    )
    patched = text.replace(anchor, imports + anchor, 1)
    patched = patched.rstrip() + (
        "\napi_router.include_router(holdings_router)\n"
        "api_router.include_router(integrations_router)\n"
    )
    return patched


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("HOLD.1-F Holdings API")
    print("Business logic: HOLD.1-A/B/C/D/E reuse")
    print("Frontend modified: NO")
    print("DB schema change: NO")
    print(".env write API: NO")
    print("Broker order API: NO")

    required = [
        ROUTER,
        MAIN,
        CONFIG,
        DATA_SOURCES,
        CATALOG,
        DOMAIN,
        ANALYSIS,
        LIFECYCLE,
        KIS_SYNC,
        ANALYSIS_HISTORY,
    ]
    for path in required:
        if not path.is_file():
            fail(f"Required file missing: {path}")

    for target in (
        HOLDINGS_API,
        INTEGRATIONS_API,
        TEST_HOLDINGS,
        TEST_INTEGRATIONS,
    ):
        if target.exists():
            fail(f"Target already exists: {target}")

    config_text = CONFIG.read_text(encoding="utf-8-sig")
    for marker in (
        "krx_api_key:",
        "dart_api_key:",
        "kis_app_key:",
        "kis_app_secret:",
        "kis_account_no:",
        "kis_account_product_code:",
    ):
        if marker not in config_text:
            print()
            print("F.0 SOURCE AUDIT: STOP")
            print("Expected integration setting is missing; no files were changed.")
            print("Missing marker:", marker)
            return 2

    for path, markers in (
        (
            CATALOG,
            (
                "def connection(self)",
                "CREATE TABLE IF NOT EXISTS monitored_stock (",
                "CREATE TABLE IF NOT EXISTS holding_position (",
                "CREATE TABLE IF NOT EXISTS stock_analysis_revision (",
            ),
        ),
        (
            LIFECYCLE,
            (
                "class PositionLifecycleService",
                "def record_buy(",
                "def record_sell(",
                "def record_correction(",
            ),
        ),
        (
            KIS_SYNC,
            (
                "class KisAccountSyncService",
                "BALANCE_OBSERVED",
                "RECONCILED",
            ),
        ),
        (
            ANALYSIS_HISTORY,
            (
                "class HoldingAnalysisHistoryService",
                "def analyze_latest_confirmed(",
                "def get_analysis_timeline(",
                "def get_stock_timeline(",
            ),
        ),
    ):
        source = path.read_text(encoding="utf-8-sig")
        missing = [marker for marker in markers if marker not in source]
        if missing:
            print()
            print("F.0 SOURCE AUDIT: STOP")
            print("Unexpected HOLD source structure; no files were changed.")
            print("FILE:", path)
            print("Missing markers:", missing)
            return 2

    router_before = ROUTER.read_text(encoding="utf-8-sig")
    router_after = patch_router(router_before)

    compile(HOLDINGS_API_CONTENT, str(HOLDINGS_API), "exec")
    compile(INTEGRATIONS_API_CONTENT, str(INTEGRATIONS_API), "exec")
    compile(TEST_HOLDINGS_CONTENT, str(TEST_HOLDINGS), "exec")
    compile(TEST_INTEGRATIONS_CONTENT, str(TEST_INTEGRATIONS), "exec")
    compile(router_after, str(ROUTER), "exec")

    protected = {
        "main": sha256(MAIN),
        "config": sha256(CONFIG),
        "data_sources": sha256(DATA_SOURCES),
        "catalog": sha256(CATALOG),
        "domain": sha256(DOMAIN),
        "analysis": sha256(ANALYSIS),
        "lifecycle": sha256(LIFECYCLE),
        "kis_sync": sha256(KIS_SYNC),
        "analysis_history": sha256(ANALYSIS_HISTORY),
        "scanner": tree_hash(ROOT / "backend" / "app" / "backtest" / "scanner.py"),
        "strategy": tree_hash(ROOT / "backend" / "app" / "strategy"),
        "risk": tree_hash(ROOT / "backend" / "app" / "risk"),
        "kis": tree_hash(ROOT / "backend" / "app" / "integrations" / "kis"),
    }

    created: list[Path] = []
    router_changed = False

    try:
        HOLDINGS_API.write_text(
            HOLDINGS_API_CONTENT,
            encoding="utf-8",
            newline="\n",
        )
        created.append(HOLDINGS_API)

        INTEGRATIONS_API.write_text(
            INTEGRATIONS_API_CONTENT,
            encoding="utf-8",
            newline="\n",
        )
        created.append(INTEGRATIONS_API)

        TEST_HOLDINGS.write_text(
            TEST_HOLDINGS_CONTENT,
            encoding="utf-8",
            newline="\n",
        )
        created.append(TEST_HOLDINGS)

        TEST_INTEGRATIONS.write_text(
            TEST_INTEGRATIONS_CONTENT,
            encoding="utf-8",
            newline="\n",
        )
        created.append(TEST_INTEGRATIONS)

        ROUTER.write_text(router_after, encoding="utf-8", newline="\n")
        router_changed = True

        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        python_exe = str(
            venv_python if venv_python.is_file() else Path(sys.executable)
        )

        run(
            [
                python_exe,
                "-m",
                "pytest",
                "backend/tests/test_holdings_api_hold1f.py",
                "backend/tests/test_integrations_status_hold1f.py",
                "-q",
            ],
            "HOLD.1-F API tests",
        )

        run(
            [
                python_exe,
                "-m",
                "pytest",
                "backend/tests/test_holdings_catalog_hold1a.py",
                "backend/tests/test_holdings_analysis_hold1b.py",
                "backend/tests/test_holdings_lifecycle_hold1c.py",
                "backend/tests/test_holdings_kis_sync_hold1d.py",
                "backend/tests/test_holdings_analysis_history_hold1e.py",
                "-q",
            ],
            "HOLD.1-A/B/C/D/E regression",
        )

        after = {
            "main": sha256(MAIN),
            "config": sha256(CONFIG),
            "data_sources": sha256(DATA_SOURCES),
            "catalog": sha256(CATALOG),
            "domain": sha256(DOMAIN),
            "analysis": sha256(ANALYSIS),
            "lifecycle": sha256(LIFECYCLE),
            "kis_sync": sha256(KIS_SYNC),
            "analysis_history": sha256(ANALYSIS_HISTORY),
            "scanner": tree_hash(ROOT / "backend" / "app" / "backtest" / "scanner.py"),
            "strategy": tree_hash(ROOT / "backend" / "app" / "strategy"),
            "risk": tree_hash(ROOT / "backend" / "app" / "risk"),
            "kis": tree_hash(ROOT / "backend" / "app" / "integrations" / "kis"),
        }
        changed = [key for key in protected if protected[key] != after[key]]
        if changed:
            fail("Protected source changed during HOLD.1-F: " + ", ".join(changed))

        print()
        print("=== HOLD.1-F ROUTER REGISTRATION ===")
        route_code = r"""
import sys
sys.path.insert(0, "backend")
from app.api.router import api_router

paths = {getattr(route, "path", None) for route in api_router.routes}
required = {
    "/holdings/stocks",
    "/holdings/watch",
    "/holdings/accounts",
    "/holdings/manual/buy",
    "/holdings/kis/sync",
    "/integrations/status",
    "/integrations/{provider}/check",
}
missing = sorted(required - paths)
if missing:
    raise SystemExit("Missing HOLD.1-F routes: " + ", ".join(missing))
print("HOLDINGS ROUTER: REGISTERED")
print("INTEGRATIONS ROUTER: REGISTERED")
print("REQUIRED ROUTES:", len(required))
"""
        run([python_exe, "-c", route_code], "HOLD.1-F route smoke")

        print()
        print("=== HOLD.1-F TEMP DB API SMOKE ===")
        smoke_code = r"""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, "backend")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.holdings import router as holdings_router
from app.api.integrations import router as integrations_router

with tempfile.TemporaryDirectory() as td:
    os.environ["STOCKSCOPE_HOLDINGS_DB"] = str(Path(td) / "holdings.db")
    app = FastAPI()
    app.include_router(holdings_router, prefix="/api")
    app.include_router(integrations_router, prefix="/api")
    client = TestClient(app)

    watched = client.post(
        "/api/holdings/watch",
        json={
            "market": "KOSPI",
            "ticker": "005930",
            "name": "삼성전자",
        },
    )
    assert watched.status_code == 200, watched.text
    stock_id = watched.json()["stock"]["stock_id"]

    listing = client.get("/api/holdings/stocks")
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) == 1

    status = client.get("/api/integrations/status")
    assert status.status_code == 200, status.text
    body = status.json()
    assert set(body) == {"kis", "krx", "dart"}

    serialized = status.text
    from app.core.config import get_settings
    settings = get_settings()
    for value in (
        settings.kis_app_key,
        settings.kis_app_secret,
        settings.kis_account_no,
        settings.krx_api_key,
        settings.dart_api_key,
    ):
        if value:
            assert str(value) not in serialized

    print("WATCH API: PASS")
    print("STOCK LIST API: PASS")
    print("INTEGRATION STATUS API: PASS")
    print("SECRET VALUES RETURNED: NO")
    print("ENV FILE WRITTEN: NO")
    print("EXTERNAL CHECK CALLED: NO")
    print("ORDER API CALLED: NO")
"""
        run([python_exe, "-c", smoke_code], "HOLD.1-F temp DB API smoke")

        print()
        print("HOLD.1-F CLOSED")
        print("Added:")
        print(" - backend/app/api/holdings.py")
        print(" - backend/app/api/integrations.py")
        print(" - backend/tests/test_holdings_api_hold1f.py")
        print(" - backend/tests/test_integrations_status_hold1f.py")
        print("Modified:")
        print(" - backend/app/api/router.py (router registration only)")
        print("Holdings list/detail API: PASS")
        print("Watch idempotent API: PASS")
        print("Manual ledger BUY/SELL/CORRECTION API: PASS")
        print("BROKER manual mutation guard: PASS")
        print("Analysis/current/timeline/revision API: PASS")
        print("KIS balance sync delegation API: PASS")
        print("KIS/KRX/DART configuration status API: PASS")
        print("Explicit read-only connection-check routes: PASS")
        print("Secret values returned: NO")
        print(".env write API: NO")
        print("Decimal response strings: PASS")
        print("DB schema changed: NO")
        print("HOLD.1-A/B/C/D/E regression: PASS")
        print("Scanner/Strategy/Risk/KIS changed: NO")
        print("Frontend changed: NO")
        print("Broker order API called: NO")
        return 0

    except Exception:
        if router_changed:
            ROUTER.write_text(router_before, encoding="utf-8", newline="\n")
        for path in reversed(created):
            if path.exists():
                path.unlink()
        print()
        print("FAILED — HOLD.1-F changes were rolled back.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
