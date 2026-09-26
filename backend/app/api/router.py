from fastapi import APIRouter

from app.api.backtest import router as backtest_router
from app.api.data_contract import router as data_contract_router
from app.api.data_sources import router as data_sources_router
from app.api.health import router as health_router
from app.api.news import router as news_router
from app.api.quotes import router as quotes_router

from app.api import simulation as simulation_api
from app.api.holdings import router as holdings_router
from app.api.integrations import router as integrations_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(news_router)
api_router.include_router(quotes_router)
api_router.include_router(data_contract_router)
api_router.include_router(data_sources_router)
api_router.include_router(backtest_router)
api_router.include_router(simulation_api.router)
api_router.include_router(holdings_router)
api_router.include_router(integrations_router)
