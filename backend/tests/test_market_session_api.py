from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

import app.api.market_session as market_session_api
from app.main import app
from app.market_session.models import DomesticMarketSession


client = TestClient(app)


def _session() -> DomesticMarketSession:
    return DomesticMarketSession(
        market="DOMESTIC_EQUITY",
        venue="INTEGRATED",
        timezone="Asia/Seoul",
        checked_at="2026-09-25T09:00:00+09:00",
        local_date="2026-09-25",
        trading_day=True,
        phase="REGULAR",
        quote_polling_allowed=True,
        market_active=True,
        next_transition_at="2026-09-25T15:30:00+09:00",
        source="SESSION_CLOCK",
        reason_code=None,
    )


def test_market_session_api_returns_no_store_contract(monkeypatch) -> None:
    class Service:
        def get_session(self, venue):
            assert venue == "INTEGRATED"
            return _session()

    monkeypatch.setattr(market_session_api, "market_session_service", Service())

    response = client.get("/api/market-session/domestic")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "market": "DOMESTIC_EQUITY",
        "venue": "INTEGRATED",
        "timezone": "Asia/Seoul",
        "checked_at": "2026-09-25T09:00:00+09:00",
        "local_date": "2026-09-25",
        "trading_day": True,
        "phase": "REGULAR",
        "quote_polling_allowed": True,
        "market_active": True,
        "next_transition_at": "2026-09-25T15:30:00+09:00",
        "source": "SESSION_CLOCK",
        "reason_code": None,
    }


def test_market_session_api_rejects_non_integrated_venue() -> None:
    response = client.get(
        "/api/market-session/domestic",
        params={"venue": "KRX"},
    )
    assert response.status_code == 422
