from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

import app.api.simulation as simulation_api


def _routes():
    return {(route.path, tuple(sorted(route.methods))) for route in simulation_api.router.routes if isinstance(route, APIRoute)}


def test_simulation_ui1_router_exposes_portfolio_trading_and_playback_contracts():
    paths = {path for path, _ in _routes()}
    assert "/simulation/portfolios" in paths
    assert "/simulation/portfolios/{portfolio_id}" in paths
    assert "/simulation/portfolios/{portfolio_id}/positions" in paths
    assert "/simulation/portfolios/{portfolio_id}/buy" in paths
    assert "/simulation/portfolios/{portfolio_id}/sell" in paths
    assert "/simulation/portfolios/{portfolio_id}/sessions" in paths
    assert "/simulation/portfolios/{portfolio_id}/session" in paths
    assert "/simulation/portfolios/{portfolio_id}/next-day" in paths
    assert "/simulation/portfolios/{portfolio_id}/advance" in paths
    assert "/simulation/portfolios/{portfolio_id}/position-marks" in paths
    assert "/simulation/portfolios/{portfolio_id}/quote/{stock_code}" in paths


def test_simulation_ui1_routes_keep_http_methods_separate():
    route_map = {path: methods for path, methods in _routes()}
    assert "POST" in route_map["/simulation/portfolios"]
    assert "GET" in route_map["/simulation/portfolios/{portfolio_id}"]
    assert "POST" in route_map["/simulation/portfolios/{portfolio_id}/buy"]
    assert "POST" in route_map["/simulation/portfolios/{portfolio_id}/sell"]
    assert "POST" in route_map["/simulation/portfolios/{portfolio_id}/next-day"]
    assert "GET" in route_map["/simulation/portfolios/{portfolio_id}/position-marks"]
    assert "GET" in route_map["/simulation/portfolios/{portfolio_id}/quote/{stock_code}"]


def test_simulation_quote_uses_active_session_date_and_local_market_provider(monkeypatch):
    class FakeRepository:
        def get_portfolio(self, portfolio_id):
            return SimpleNamespace(id=portfolio_id)

    class FakePlaybackStore:
        def __init__(self, repository):
            self.repository = repository

        def active_session(self, portfolio_id):
            return SimpleNamespace(portfolio_id=portfolio_id, current_date=date(2025, 1, 3))

    seen = {}

    class FakeProvider:
        def get_bar(self, market, stock_code, trading_date):
            seen.update(market=market, stock_code=stock_code, trading_date=trading_date)
            return SimpleNamespace(market="KOSPI", trading_date=trading_date, close=Decimal("77700"))

    monkeypatch.setattr(simulation_api, "_repository", lambda: FakeRepository())
    monkeypatch.setattr(simulation_api, "SimulationPlaybackStore", FakePlaybackStore)
    monkeypatch.setattr(simulation_api, "HistoricalMarketStoreProvider", FakeProvider)

    payload = simulation_api.simulation_quote("portfolio-1", "005930", "KOSPI")

    assert payload == {
        "stock_code": "005930",
        "market": "KOSPI",
        "trading_date": "2025-01-03",
        "close": "77700",
    }
    assert seen == {"market": "KOSPI", "stock_code": "005930", "trading_date": date(2025, 1, 3)}


def test_simulation_quote_requires_active_session(monkeypatch):
    class FakeRepository:
        def get_portfolio(self, portfolio_id):
            return SimpleNamespace(id=portfolio_id)

    class FakePlaybackStore:
        def __init__(self, repository):
            self.repository = repository

        def active_session(self, portfolio_id):
            return None

    monkeypatch.setattr(simulation_api, "_repository", lambda: FakeRepository())
    monkeypatch.setattr(simulation_api, "SimulationPlaybackStore", FakePlaybackStore)

    with pytest.raises(HTTPException) as exc:
        simulation_api.simulation_quote("portfolio-1", "005930", "KOSPI")
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SIM_SESSION_NOT_FOUND"
