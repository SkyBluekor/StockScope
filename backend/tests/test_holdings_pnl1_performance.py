from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.holdings as holdings_api
from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.performance import HoldingPerformanceService


T0 = "2026-09-24T09:00:00+09:00"
T1 = "2026-09-24T10:00:00+09:00"
T2 = "2026-09-24T11:00:00+09:00"
T3 = "2026-09-24T12:00:00+09:00"


def _market_store(path, *, close: str = "120", bas_dd: str = "20260924"):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE day_status(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE stock_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                row_json TEXT NOT NULL
            );
            """
        )
        payload = {
            "date": f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}",
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": "1000",
        }
        conn.execute(
            "INSERT INTO day_status(market,bas_dd,kind,status) VALUES('KOSPI',?,'stock','data')",
            (bas_dd,),
        )
        conn.execute(
            "INSERT INTO stock_daily(market,bas_dd,stock_code,row_json) VALUES('KOSPI',?,'005930',?)",
            (bas_dd, json.dumps(payload)),
        )


def _env(tmp_path, *, close: str = "120"):
    holdings_db = tmp_path / "holdings.db"
    market_db = tmp_path / "market.db"
    _market_store(market_db, close=close)
    catalog = HoldingsCatalog(holdings_db)
    catalog.initialize()
    service = PositionLifecycleService(catalog)
    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동 기록",
    )
    return catalog, service, account, market_db


def test_opening_balance_unrealized_pnl(tmp_path):
    catalog, lifecycle, account, market_db = _env(tmp_path)
    opened = lifecycle.register_initial_holding(
        market="KOSPI", ticker="005930", name="삼성전자",
        position_account_id=account.id, quantity="10", average_price="100", effective_at=T0,
    )
    pnl = HoldingPerformanceService(
        catalog, market_store_db=market_db
    ).calculate(opened.stock_id).positions[0]

    assert pnl.cost_basis == Decimal("1000")
    assert pnl.market_value == Decimal("1200")
    assert pnl.unrealized_pnl == Decimal("200")
    assert pnl.unrealized_return_pct == Decimal("20")
    assert pnl.confirmed_realized_pnl == Decimal("0")
    assert pnl.tracked_pnl == Decimal("200")
    assert pnl.calculation_status == "COMPLETE_SINCE_TRACKING_START"


def test_buy_sell_realized_and_remaining_unrealized(tmp_path):
    catalog, lifecycle, account, market_db = _env(tmp_path)
    opened = lifecycle.register_initial_holding(
        market="KOSPI", ticker="005930", name="삼성전자",
        position_account_id=account.id, quantity="10", average_price="100", effective_at=T0,
    )
    lifecycle.record_buy(
        monitored_stock_id=opened.stock_id, position_account_id=account.id,
        quantity="10", unit_price="120", effective_at=T1,
    )
    lifecycle.record_sell(
        position_id=opened.position.id, quantity="5", unit_price="130", effective_at=T2,
    )

    pnl = HoldingPerformanceService(
        catalog, market_store_db=market_db
    ).calculate(opened.stock_id).positions[0]

    assert pnl.quantity == Decimal("15")
    assert pnl.average_price == Decimal("110")
    assert pnl.cost_basis == Decimal("1650")
    assert pnl.confirmed_realized_pnl == Decimal("100")
    assert pnl.market_value == Decimal("1800")
    assert pnl.unrealized_pnl == Decimal("150")
    assert pnl.tracked_pnl == Decimal("250")


def test_later_buy_does_not_rewrite_old_realized_pnl(tmp_path):
    catalog, lifecycle, account, market_db = _env(tmp_path)
    opened = lifecycle.register_initial_holding(
        market="KOSPI", ticker="005930", name="삼성전자",
        position_account_id=account.id, quantity="10", average_price="100", effective_at=T0,
    )
    lifecycle.record_buy(
        monitored_stock_id=opened.stock_id, position_account_id=account.id,
        quantity="10", unit_price="120", effective_at=T1,
    )
    lifecycle.record_sell(
        position_id=opened.position.id, quantity="5", unit_price="130", effective_at=T2,
    )
    before = HoldingPerformanceService(
        catalog, market_store_db=market_db
    ).calculate(opened.stock_id).positions[0].confirmed_realized_pnl

    lifecycle.record_buy(
        monitored_stock_id=opened.stock_id, position_account_id=account.id,
        quantity="5", unit_price="140", effective_at=T3,
    )
    after = HoldingPerformanceService(
        catalog, market_store_db=market_db
    ).calculate(opened.stock_id).positions[0].confirmed_realized_pnl
    assert before == Decimal("100")
    assert after == Decimal("100")


def test_correction_changes_current_basis_without_creating_realized_pnl(tmp_path):
    catalog, lifecycle, account, market_db = _env(tmp_path)
    opened = lifecycle.register_initial_holding(
        market="KOSPI", ticker="005930", name="삼성전자",
        position_account_id=account.id, quantity="10", average_price="100", effective_at=T0,
    )
    lifecycle.record_correction(
        position_id=opened.position.id,
        corrected_quantity="10",
        corrected_average_price="110",
        effective_at=T1,
        note="평단 정정",
    )
    pnl = HoldingPerformanceService(
        catalog, market_store_db=market_db
    ).calculate(opened.stock_id).positions[0]

    assert pnl.cost_basis == Decimal("1100")
    assert pnl.confirmed_realized_pnl == Decimal("0")
    assert pnl.unrealized_pnl == Decimal("100")
    assert pnl.calculation_status == "PARTIAL"


def test_missing_market_price_is_not_zero(tmp_path):
    catalog = HoldingsCatalog(tmp_path / "holdings.db")
    catalog.initialize()
    lifecycle = PositionLifecycleService(catalog)
    account = catalog.create_position_account(
        provider="MANUAL", account_kind="MANUAL", display_name="수동 기록",
    )
    opened = lifecycle.register_initial_holding(
        market="KOSPI", ticker="005930", name="삼성전자",
        position_account_id=account.id, quantity="10", average_price="100", effective_at=T0,
    )
    pnl = HoldingPerformanceService(
        catalog, market_store_db=tmp_path / "missing_market.db"
    ).calculate(opened.stock_id).positions[0]

    assert pnl.market_value is None
    assert pnl.unrealized_pnl is None
    assert pnl.unrealized_return_pct is None
    assert pnl.confirmed_realized_pnl == Decimal("0")
    assert pnl.tracked_pnl is None
    assert pnl.calculation_status == "UNAVAILABLE"


def test_broker_balance_is_valuation_only(tmp_path):
    catalog, _, _, market_db = _env(tmp_path)
    stock = catalog.create_monitored_stock(
        market="KOSPI", ticker="005930", name="삼성전자", watch_enabled=False,
    )
    broker = catalog.create_position_account(
        provider="KIS", account_kind="BROKER", broker_environment="REAL",
        external_account_fingerprint="b" * 64, display_name="KIS 실계좌",
    )
    position = catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=broker.id,
        opened_reason="KIS_OBSERVED",
        opened_at=T0,
        current_quantity="10",
        current_average_price="100",
        current_cost_basis="1000",
    )
    catalog.append_position_event(
        position_id=position.id,
        event_type="BALANCE_OBSERVED",
        before_quantity="0",
        after_quantity="10",
        before_average_price=None,
        after_average_price="100",
        observed_at=T0,
        effective_at=T0,
    )
    pnl = HoldingPerformanceService(
        catalog, market_store_db=market_db
    ).calculate(stock.id).positions[0]

    assert pnl.market_value == Decimal("1200")
    assert pnl.unrealized_pnl == Decimal("200")
    assert pnl.confirmed_realized_pnl is None
    assert pnl.calculation_status == "VALUATION_ONLY"


def test_api_contract_returns_decimal_strings(tmp_path, monkeypatch):
    holdings_db = tmp_path / "holdings.db"
    market_db = tmp_path / "market.db"
    _market_store(market_db, close="120")
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings_db))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))

    app = FastAPI()
    app.include_router(holdings_api.router, prefix="/api")
    client = TestClient(app)
    held = client.post(
        "/api/holdings/held",
        json={
            "market": "KOSPI", "ticker": "005930", "name": "삼성전자",
            "quantity": "10", "average_price": "100", "effective_at": T0,
        },
    )
    assert held.status_code == 200
    stock_id = held.json()["stock"]["stock_id"]

    response = client.get(f"/api/holdings/stocks/{stock_id}/performance")
    assert response.status_code == 200
    body = response.json()
    assert body["valuation"]["source"] == "MARKET_STORE_CONFIRMED_EOD"
    assert body["valuation"]["price"] == "120"
    assert body["positions"][0]["market_value"] == "1200"
    assert body["positions"][0]["unrealized_pnl"] == "200"
    assert body["positions"][0]["confirmed_realized_pnl"] == "0"
    assert body["positions"][0]["tracked_pnl"] == "200"
