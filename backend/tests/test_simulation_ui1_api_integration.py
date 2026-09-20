from fastapi.routing import APIRoute

from app.api.simulation import router


def _routes():
    return {(route.path, tuple(sorted(route.methods))) for route in router.routes if isinstance(route, APIRoute)}


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


def test_simulation_ui1_routes_keep_http_methods_separate():
    route_map = {path: methods for path, methods in _routes()}
    assert "POST" in route_map["/simulation/portfolios"]
    assert "GET" in route_map["/simulation/portfolios/{portfolio_id}"]
    assert "POST" in route_map["/simulation/portfolios/{portfolio_id}/buy"]
    assert "POST" in route_map["/simulation/portfolios/{portfolio_id}/sell"]
    assert "POST" in route_map["/simulation/portfolios/{portfolio_id}/next-day"]
    assert "GET" in route_map["/simulation/portfolios/{portfolio_id}/position-marks"]
