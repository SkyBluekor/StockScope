from fastapi import APIRouter

from app.api.backtest import router as backtest_router
from app.api.data_sources import router as data_sources_router
from app.api.health import router as health_router

from app.api import simulation as simulation_api
api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(data_sources_router)
api_router.include_router(backtest_router)
api_router.include_router(simulation_api.router)
