from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import PROJECT_ROOT, get_settings
from app.prospective import ProspectiveCatalogError, ProspectiveService
from app.quotes.websocket_manager import quote_websocket_manager

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    simulation_db = Path(
        os.getenv("STOCKSCOPE_SIM_DB")
        or PROJECT_ROOT / "backend" / "runtime" / "simulation" / "simulation.db"
    )
    market_db = Path(
        os.getenv("STOCKSCOPE_MARKET_DB")
        or PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
    )
    try:
        ProspectiveService(
            simulation_db,
            market_db,
        ).catalog.mark_pending_interrupted()
    except ProspectiveCatalogError as exc:
        if exc.code not in {
            "PROSPECTIVE_MIGRATION_REQUIRED",
            "PROSPECTIVE_SCHEMA_UNSUPPORTED",
        }:
            raise

    await quote_websocket_manager.start()
    try:
        yield
    finally:
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
