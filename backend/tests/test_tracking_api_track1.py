from fastapi.routing import APIRoute

import app.api.simulation as simulation_api


def test_tracking_routes_expose_source_safe_items_and_legacy_aliases():
    paths = {route.path for route in simulation_api.router.routes if isinstance(route, APIRoute)}
    for path in [
        "/tracking/items/from-scanner",
        "/tracking/items/manual/preview",
        "/tracking/items/manual",
        "/tracking/items",
        "/tracking/items/refresh-active",
        "/tracking/items/{recommendation_id}/refresh",
        "/tracking/items/{recommendation_id}/close",
        "/tracking/items/{recommendation_id}",
    ]:
        assert path in paths
    assert "/tracking/recommendations" in paths


def test_historical_validation_foundation_routes_are_registered():
    paths = {route.path for route in simulation_api.router.routes if isinstance(route, APIRoute)}
    assert "/simulation/validation-periods/preview" in paths
    assert "/simulation/validation-periods/validate" in paths
    assert "/simulation/legacy-validations" in paths
    assert "/simulation/legacy-validations/{portfolio_id}" in paths
    assert "/simulation/validations" in paths
    assert "/simulation/validations/{validation_id}" in paths
