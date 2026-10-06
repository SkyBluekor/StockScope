from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import PROJECT_ROOT, get_settings
from app.holdings.catalog import DEFAULT_HOLDINGS_DB, HoldingsCatalog
from app.jev import (
    JevCatalog,
    JevCatalogError,
    JevEvaluationCatalog,
    JevEvaluationCatalogError,
    TypeSafeJevCatalog,
    TypeSafeJevCatalogError,
)
from app.prospective import ProspectiveCatalogError, ProspectiveService
from app.quotes.websocket_manager import quote_websocket_manager
from app.watch import WatchCoordinator, WatchService
from app.watch.observability import WatchRuntimeObserver

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    simulation_db = Path(
        os.getenv("STOCKSCOPE_SIM_DB")
        or PROJECT_ROOT / "backend" / "runtime" / "simulation" / "simulation.db"
    )
    market_db = Path(
        (os.getenv("STOCKSCOPE_MARKET_STORE_DB") or os.getenv("STOCKSCOPE_MARKET_DB"))
        or PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
    )
    try:
        prospective_catalog = ProspectiveService(
            simulation_db,
            market_db,
        ).catalog
        prospective_catalog.mark_pending_interrupted()
        prospective_catalog.mark_running_evaluations_interrupted()
    except ProspectiveCatalogError as exc:
        if exc.code not in {
            "PROSPECTIVE_MIGRATION_REQUIRED",
            "PROSPECTIVE_SCHEMA_UNSUPPORTED",
        }:
            raise

    try:
        JevCatalog(simulation_db).mark_pending_interrupted()
    except JevCatalogError as exc:
        if exc.code not in {
            "JEV_MIGRATION_REQUIRED",
            "JEV_SCHEMA_UNSUPPORTED",
        }:
            raise

    try:
        JevEvaluationCatalog(
            simulation_db
        ).mark_running_interrupted()
    except JevEvaluationCatalogError as exc:
        if exc.code not in {
            "JEV_EVALUATION_MIGRATION_REQUIRED",
            "JEV_EVALUATION_SCHEMA_UNSUPPORTED",
        }:
            raise

    try:
        TypeSafeJevCatalog(simulation_db).mark_pending_interrupted()
    except TypeSafeJevCatalogError as exc:
        if exc.code not in {
            "JEV_TYPESAFE_MIGRATION_REQUIRED",
            "JEV_TYPESAFE_SCHEMA_UNSUPPORTED",
        }:
            raise

    holdings_db = Path(
        os.getenv("STOCKSCOPE_HOLDINGS_DB")
        or DEFAULT_HOLDINGS_DB
    )
    holdings_catalog = HoldingsCatalog(holdings_db)
    watch_service = WatchService(holdings_catalog)
    watch_runtime = WatchRuntimeObserver(holdings_catalog)

    def reconcile_watch(demands, policy):
        result = watch_service.reconcile(demands, policy)
        watch_service.check_quote_silence(
            demands,
            market_session_phase=quote_websocket_manager.session_phase,
            policy=policy,
        )
        if policy.enabled and quote_websocket_manager.transport_state in {
            "BACKOFF",
            "DEGRADED",
        }:
            for demand in demands:
                watch_service.record_coverage_issue(
                    demand,
                    f"TRANSPORT_{quote_websocket_manager.transport_state}",
                    detail={
                        "transport_state": quote_websocket_manager.transport_state,
                        "market_session_phase": quote_websocket_manager.session_phase,
                    },
                    policy=policy,
                )
        return result

    def runtime_event(event, detail):
        detail = detail or {}
        watch_runtime.record_event(
            event,
            error_code=(
                str(detail.get("error_code"))
                if detail.get("error_code") not in (None, "")
                else None
            ),
            transport_state=quote_websocket_manager.transport_state,
            market_session_phase=quote_websocket_manager.session_phase,
            detail=detail,
        )

    watch_coordinator = WatchCoordinator(
        holdings_catalog,
        on_reconcile=reconcile_watch,
        on_quote=watch_service.process_quote,
        on_coverage_issue=watch_service.record_coverage_issue,
        on_runtime_event=runtime_event,
    )

    watch_runtime.start(
        transport_state=quote_websocket_manager.transport_state,
        market_session_phase=quote_websocket_manager.session_phase,
    )
    await quote_websocket_manager.start()
    await watch_coordinator.start()
    try:
        yield
    finally:
        await watch_coordinator.stop()
        watch_runtime.stop(
            transport_state=quote_websocket_manager.transport_state,
            market_session_phase=quote_websocket_manager.session_phase,
        )
        await quote_websocket_manager.stop()


app = FastAPI(
    title=settings.app_name,
    description=(
        "StockScope investment analysis, backtest and portfolio simulation API. "
        "Real brokerage order execution is intentionally not supported."
    ),
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/", tags=["system"])
async def root() -> dict[str, object]:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "real_trading": False,
    }
