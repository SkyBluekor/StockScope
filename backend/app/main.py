from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "StockScope investment analysis, backtest and portfolio simulation API. "
        "Real brokerage order execution is intentionally not supported."
    ),
    version=settings.app_version,
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
