from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.holdings as holdings_api
from app.holdings import HoldingsCatalog, HoldingsLifecycleError, PositionLifecycleService

T0 = "2026-09-24T09:00:00+09:00"
T1 = "2026-09-24T10:00:00+09:00"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "holdings.db"
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(db))
    app = FastAPI()
    app.include_router(holdings_api.router, prefix="/api")
    return TestClient(app)


@pytest.fixture()
def env(tmp_path):
    catalog = HoldingsCatalog(tmp_path / "holdings.db")
    catalog.initialize()
    return catalog, PositionLifecycleService(catalog)


def _manual(catalog):
    return catalog.create_position_account(provider="MANUAL", account_kind="MANUAL", display_name="수동 기록")


def _broker(catalog):
    return catalog.create_position_account(
        provider="KIS", account_kind="BROKER", broker_environment="REAL",
        external_account_fingerprint="a" * 64, display_name="KIS 실계좌",
    )


def test_held_endpoint_creates_opening_balance_not_buy(client):
    r = client.post("/api/holdings/held", json={
        "market":"KOSPI","ticker":"005930","name":"삼성전자",
        "quantity":"20","average_price":"70000","effective_at":T0,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["event"]["event_type"] == "OPENING_BALANCE"
    assert body["event"]["analysis_revision_id"] is None
    assert body["position"]["quantity"] == "20"
    assert body["position"]["average_price"] == "70000"
    assert body["position"]["cost_basis"] == "1400000"


def test_opening_balance_then_real_buy_keeps_distinct_meaning(env):
    catalog, service = env
    account = _manual(catalog)
    opened = service.register_initial_holding(
        market="KOSPI",ticker="005930",name="삼성전자",position_account_id=account.id,
        quantity="10",average_price="100",effective_at=T0,
    )
    bought = service.record_buy(
        monitored_stock_id=opened.stock_id,position_account_id=account.id,
        quantity="10",unit_price="120",effective_at=T1,
    )
    assert bought.position.current_quantity == Decimal("20")
    assert bought.position.current_average_price == Decimal("110")
    assert [e.event_type for e in catalog.list_position_events(opened.position.id)] == ["OPENING_BALANCE", "BUY"]


def test_duplicate_opening_balance_is_rejected(env):
    catalog, service = env
    account = _manual(catalog)
    first = service.register_initial_holding(
        market="KOSPI",ticker="005930",name="삼성전자",position_account_id=account.id,
        quantity="8",average_price="30000",effective_at=T0,
    )
    with pytest.raises(HoldingsLifecycleError) as exc:
        service.register_initial_holding(
            market="KOSPI",ticker="005930",name="삼성전자",position_account_id=account.id,
            quantity="9",average_price="31000",effective_at=T1,
        )
    assert exc.value.code == "HOLD_OPEN_POSITION_DUPLICATE"
    assert [e.event_type for e in catalog.list_position_events(first.position.id)] == ["OPENING_BALANCE"]


@pytest.mark.parametrize("quantity,price", [("0","100"),("-1","100"),("1","0"),("1","-1")])
def test_opening_balance_requires_positive_values(env, quantity, price):
    catalog, service = env
    account = _manual(catalog)
    with pytest.raises(HoldingsLifecycleError):
        service.register_initial_holding(
            market="KOSPI",ticker="005930",name="삼성전자",position_account_id=account.id,
            quantity=quantity,average_price=price,effective_at=T0,
        )
    assert catalog.list_monitored_stocks() == []


def test_broker_direct_opening_balance_is_blocked(env):
    catalog, service = env
    account = _broker(catalog)
    with pytest.raises(HoldingsLifecycleError) as exc:
        service.register_initial_holding(
            market="KOSPI",ticker="005930",name="삼성전자",position_account_id=account.id,
            quantity="1",average_price="70000",effective_at=T0,
        )
    assert exc.value.code == "HOLD_POSITION_SOURCE_MANAGED_EXTERNALLY"
    assert catalog.list_monitored_stocks() == []


def test_manual_buy_endpoint_remains_buy(client):
    held = client.post("/api/holdings/held", json={
        "market":"KOSPI","ticker":"005930","name":"삼성전자",
        "quantity":"10","average_price":"100","effective_at":T0,
    }).json()
    r = client.post("/api/holdings/manual/buy", json={
        "stock_id":held["stock"]["stock_id"],"quantity":"1","unit_price":"120","effective_at":T1,
    })
    assert r.status_code == 200
    assert r.json()["event"]["event_type"] == "BUY"
