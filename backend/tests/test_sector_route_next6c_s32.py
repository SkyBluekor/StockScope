from __future__ import annotations

from app.macro import (
    HISTORICAL_IMPACT_MARKET_STOCK_ONLY,
    HISTORICAL_SECTOR_BLOCKED_EXTERNAL_SOURCE,
    PROSPECTIVE_SECTOR_NOT_STARTED,
    SECTOR_ROUTE_CONTRACT_VERSION,
    SECTOR_ROUTE_UNLOCK_REQUIREMENTS,
    build_sector_route,
)


def test_historical_sector_route_is_explicitly_blocked_by_external_source():
    route = build_sector_route()

    assert route["contract_version"] == SECTOR_ROUTE_CONTRACT_VERSION
    assert (
        route["historical_sector_status"]
        == HISTORICAL_SECTOR_BLOCKED_EXTERNAL_SOURCE
    )
    assert (
        route["historical_impact_mode"]
        == HISTORICAL_IMPACT_MARKET_STOCK_ONLY
    )
    assert (
        route["prospective_sector_status"]
        == PROSPECTIVE_SECTOR_NOT_STARTED
    )
    assert route["unlock_requirements"] == list(
        SECTOR_ROUTE_UNLOCK_REQUIREMENTS
    )
    assert route["production_decision_approved"] is False


def test_sector_route_cannot_unlock_from_static_current_or_inferred_time():
    route = build_sector_route()

    assert all(
        value is False
        for value in route["current_unlock_state"].values()
    )
    assert "OPENDART_STATIC_CURRENT" in route["prohibited_unlock_inputs"]
    assert "CURRENT_INDUSTRY_BACKFILL" in route["prohibited_unlock_inputs"]
    assert "QUERY_DATE_AS_KNOWN_AT" in route["prohibited_unlock_inputs"]
    assert "FETCH_TIME_AS_KNOWN_AT" in route["prohibited_unlock_inputs"]
    assert "UNAUTHORIZED_KRX_WEB_BACKEND" in route["prohibited_unlock_inputs"]


def test_sector_route_requires_every_s2_unlock_proof():
    route = build_sector_route()

    assert set(route["unlock_requirements"]) == {
        "AUTHORIZED_KRX_SOURCE",
        "KNOWN_AT_PROVEN",
        "EFFECTIVE_MEMBERSHIP_PROVEN",
        "BENCHMARK_IDENTITY_PROVEN",
        "S2_PIT_COMPATIBLE",
    }
    assert "MARKET_STOCK_ONLY_UNTIL_UNLOCK" in route["limitations"]
