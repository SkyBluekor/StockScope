from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

import app.api.quotes as quotes_api
from app.main import app
from app.quotes.models import QuoteResult, QuoteSnapshot
from app.quotes.service import QuoteServiceError


client = TestClient(app)


def _result() -> QuoteResult:
    return QuoteResult(
        snapshot=QuoteSnapshot(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            venue="INTEGRATED",
            provider_market_division="UN",
            environment="real",
            current_price=Decimal("84200"),
            change_amount=Decimal("1200"),
            change_rate=Decimal("1.45"),
            change_sign="2",
            open_price=Decimal("83300"),
            high_price=Decimal("85000"),
            low_price=Decimal("82900"),
            base_price=Decimal("83000"),
            accumulated_volume=Decimal("12345678"),
            provider_timestamp=None,
            received_at=datetime(2026, 9, 26, 6, 50, 12, tzinfo=timezone.utc),
        ),
        delivery_source="UPSTREAM",
        cache_age_ms=0,
    )


def test_quote_api_returns_product_snapshot_contract(monkeypatch) -> None:
    class Service:
        def get_quote(self, *, market, ticker, venue):
            assert (market, ticker, venue) == ("KOSPI", "005930", "INTEGRATED")
            return _result()

    monkeypatch.setattr(quotes_api, "quote_service", Service())

    response = client.get(
        "/api/quotes/stocks/005930",
        params={"market": "KOSPI"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["resource_key"] == "KOSPI:005930"
    assert body["provider"] == "KIS"
    assert body["mode"] == "SNAPSHOT"
    assert body["venue"] == "INTEGRATED"
    assert body["provider_market_division"] == "UN"
    assert body["current_price"] == "84200"
    assert body["change_rate"] == "1.45"
    assert body["provider_timestamp"] is None
    assert body["received_at"] == "2026-09-26T06:50:12+00:00"
    assert body["delivery"] == {"source": "UPSTREAM", "cache_age_ms": 0}

    serialized = response.text.lower()
    assert "app-secret" not in serialized
    assert "access_token" not in serialized
    assert "app_key" not in serialized
    assert "app_secret" not in serialized
    assert "account_no" not in serialized


def test_quote_api_maps_configuration_error(monkeypatch) -> None:
    class Service:
        def get_quote(self, *, market, ticker, venue):
            raise QuoteServiceError(
                "KIS_QUOTE_NOT_CONFIGURED",
                "KIS 연동 설정이 필요합니다.",
                status_code=409,
            )

    monkeypatch.setattr(quotes_api, "quote_service", Service())
    response = client.get(
        "/api/quotes/stocks/005930",
        params={"market": "KOSPI"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "KIS_QUOTE_NOT_CONFIGURED"


def test_quote_api_requires_market_and_valid_identity() -> None:
    assert client.get("/api/quotes/stocks/005930").status_code == 422
    assert client.get(
        "/api/quotes/stocks/5930",
        params={"market": "KOSPI"},
    ).status_code == 422
    assert client.get(
        "/api/quotes/stocks/005930",
        params={"market": "KOSPI", "venue": "BAD"},
    ).status_code == 422


def test_quote_backend_is_separate_from_balance_domain_and_websocket() -> None:
    api_source = Path("backend/app/api/quotes.py").read_text(encoding="utf-8")
    service_source = Path("backend/app/quotes/service.py").read_text(encoding="utf-8")
    combined = api_source + "\n" + service_source

    assert "inquire_domestic_balance" not in combined
    assert "KisAccountSyncService" not in combined
    assert "H0STCNT0" not in combined
    assert "StrategyAnalysisService" not in combined
    assert "RiskEngine" not in combined
    assert "StockScannerService" not in combined
    assert "BacktestService" not in combined
