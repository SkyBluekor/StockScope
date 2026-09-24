from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.holdings as holdings_api


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "holdings.db"
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(db))
    app = FastAPI()
    app.include_router(holdings_api.router, prefix="/api")
    return TestClient(app)


def _held_payload(ticker: str = "005930", name: str = "삼성전자"):
    return {
        "market": "KOSPI",
        "ticker": ticker,
        "name": name,
        "quantity": "8",
        "average_price": "30000",
        "effective_at": "2026-09-24T16:43:00+09:00",
    }


def test_new_held_registration_is_one_atomic_user_operation(client):
    response = client.post("/api/holdings/held", json=_held_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["stock"]["watch_enabled"] is False
    assert body["stock"]["is_held"] is True
    assert body["position"]["quantity"] == "8"
    assert body["position"]["average_price"] == "30000"
    assert body["event"]["event_type"] == "OPENING_BALANCE"


def test_existing_watch_stock_keeps_watch_flag_when_promoted_to_held(client):
    watched = client.post(
        "/api/holdings/watch",
        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},
    )
    assert watched.status_code == 200
    stock_id = watched.json()["stock"]["stock_id"]

    response = client.post("/api/holdings/held", json=_held_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["created"] is False
    assert body["stock"]["stock_id"] == stock_id
    assert body["stock"]["watch_enabled"] is True
    assert body["stock"]["is_held"] is True


def test_invalid_initial_holding_does_not_leave_half_registered_stock(client):
    payload = _held_payload(ticker="000660", name="SK하이닉스")
    payload["average_price"] = "0"
    response = client.post("/api/holdings/held", json=payload)
    assert response.status_code == 400

    listing = client.get("/api/holdings/stocks")
    assert listing.status_code == 200
    assert all(item["ticker"] != "000660" for item in listing.json())


def test_duplicate_initial_holding_is_rejected_without_second_position(client):
    first = client.post("/api/holdings/held", json=_held_payload())
    assert first.status_code == 200
    second = client.post("/api/holdings/held", json=_held_payload())
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "HOLD_OPEN_POSITION_DUPLICATE"

    detail = client.get(f"/api/holdings/stocks/{first.json()['stock']['stock_id']}")
    assert detail.status_code == 200
    assert len(detail.json()["positions"]) == 1
    assert detail.json()["positions"][0]["quantity"] == "8"
