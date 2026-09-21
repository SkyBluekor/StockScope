from fastapi.routing import APIRoute

import app.api.simulation as simulation_api


def test_tracking_routes_expose_refresh_and_close_contracts():
    paths = {route.path for route in simulation_api.router.routes if isinstance(route, APIRoute)}
    assert "/tracking/recommendations" in paths
    assert "/tracking/recommendations/refresh" in paths
    assert "/tracking/recommendations/{recommendation_id}/refresh" in paths
    assert "/tracking/recommendations/{recommendation_id}/close" in paths
