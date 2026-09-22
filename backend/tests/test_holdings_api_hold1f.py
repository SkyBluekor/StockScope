from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.holdings as holdings_api
from app.holdings import HoldingsCatalog


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "holdings.db"
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(db))
    app = FastAPI()
    app.include_router(holdings_api.router, prefix="/api")
    return TestClient(app)


def _catalog_from_env(monkeypatch, tmp_path):
    db = tmp_path / "holdings.db"
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(db))
    catalog = HoldingsCatalog(db)
    catalog.initialize()
    return catalog


def test_watch_registration_is_idempotent_and_watch_off_keeps_held_stock(client):
    first = client.post(
        "/api/holdings/watch",
        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},
    )
    assert first.status_code == 200
    assert first.json()["created"] is True
    stock_id = first.json()["stock"]["stock_id"]

    second = client.post(
        "/api/holdings/watch",
        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},
    )
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["stock"]["stock_id"] == stock_id

    bought = client.post(
        "/api/holdings/manual/buy",
        json={
            "stock_id": stock_id,
            "quantity": "10",
            "unit_price": "70000",
            "effective_at": "2026-09-23T09:00:00+09:00",
        },
    )
    assert bought.status_code == 200
    assert bought.json()["position"]["quantity"] == "10"
    assert bought.json()["position"]["average_price"] == "70000"

    disabled = client.patch(
        f"/api/holdings/stocks/{stock_id}/watch",
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["stock"]["watch_enabled"] is False
    assert disabled.json()["stock"]["is_held"] is True

    listing = client.get("/api/holdings/stocks")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["stock_id"] == stock_id


def test_manual_sell_correction_and_broker_guard(client):
    watched = client.post(
        "/api/holdings/watch",
        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},
    ).json()
    stock_id = watched["stock"]["stock_id"]

    bought = client.post(
        "/api/holdings/manual/buy",
        json={
            "stock_id": stock_id,
            "quantity": "10",
            "unit_price": "70000",
            "effective_at": "2026-09-23T09:00:00+09:00",
        },
    ).json()
    position_id = bought["position"]["position_id"]

    oversell = client.post(
        f"/api/holdings/manual/{position_id}/sell",
        json={
            "quantity": "11",
            "unit_price": "71000",
            "effective_at": "2026-09-23T10:00:00+09:00",
        },
    )
    assert oversell.status_code == 409
    assert oversell.json()["detail"]["code"] == "HOLD_POSITION_SELL_EXCEEDS_HOLDING"

    correction = client.post(
        f"/api/holdings/manual/{position_id}/correction",
        json={
            "quantity": "9",
            "average_price": "70500",
            "effective_at": "2026-09-23T10:01:00+09:00",
            "note": None,
        },
    )
    assert correction.status_code == 400
    assert correction.json()["detail"]["code"] == "HOLD_POSITION_CORRECTION_NOTE_REQUIRED"

    sold = client.post(
        f"/api/holdings/manual/{position_id}/sell",
        json={
            "quantity": "5",
            "unit_price": "72000",
            "effective_at": "2026-09-23T10:02:00+09:00",
        },
    )
    assert sold.status_code == 200
    assert sold.json()["position"]["quantity"] == "5"

    catalog = holdings_api._catalog()
    account = catalog.create_position_account(
        provider="KIS",
        account_kind="BROKER",
        broker_environment="REAL",
        external_account_fingerprint="a" * 64,
        display_name="한국투자증권 실계좌",
    )
    broker_position = catalog.open_position(
        monitored_stock_id=stock_id,
        position_account_id=account.id,
        opened_reason="KIS_OBSERVED",
        current_quantity="1",
        current_average_price="70000",
        current_cost_basis="70000",
    )
    blocked = client.post(
        f"/api/holdings/manual/{broker_position.id}/sell",
        json={
            "quantity": "1",
            "unit_price": "70000",
            "effective_at": "2026-09-23T10:03:00+09:00",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "HOLD_POSITION_SOURCE_MANAGED_EXTERNALLY"


def test_accounts_and_stock_detail_use_separate_account_positions(client):
    stock_id = client.post(
        "/api/holdings/watch",
        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},
    ).json()["stock"]["stock_id"]
    client.post(
        "/api/holdings/manual/buy",
        json={
            "stock_id": stock_id,
            "quantity": "2",
            "unit_price": "70000",
            "effective_at": "2026-09-23T09:00:00+09:00",
        },
    )
    accounts = client.get("/api/holdings/accounts")
    assert accounts.status_code == 200
    assert len(accounts.json()) == 1
    assert accounts.json()[0]["account_kind"] == "MANUAL"

    detail = client.get(f"/api/holdings/stocks/{stock_id}")
    assert detail.status_code == 200
    assert detail.json()["is_held"] is True
    assert len(detail.json()["positions"]) == 1
    assert detail.json()["positions"][0]["quantity"] == "2"
    assert detail.json()["latest_position_event"]["event_type"] == "BUY"


def test_analysis_read_timeline_revision_and_refresh_contract(client, monkeypatch):
    stock_id = client.post(
        "/api/holdings/watch",
        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},
    ).json()["stock"]["stock_id"]

    empty = client.get(f"/api/holdings/stocks/{stock_id}/analysis")
    assert empty.status_code == 200
    assert empty.json() == {"available": False, "analysis": None}

    catalog = holdings_api._catalog()
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock_id,
        market_date="2026-09-18",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="fp-api",
        strategy_key="ma20_rebound",
        action_state="WATCH",
        risk_state="READY",
        reference_price="261000",
        stop_price="254124.8",
        target1_price="271000",
        target2_price="274750.4",
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_SINGLE_STOCK_V1",
        policy_version="P1",
        source_versions={"fixture": "api"},
        snapshot={"fixture": True},
        revision_reason="INITIAL",
        computed_at="2026-09-23T00:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )

    current = client.get(f"/api/holdings/stocks/{stock_id}/analysis")
    assert current.status_code == 200
    assert current.json()["available"] is True
    assert current.json()["analysis"]["market_date"] == "2026-09-18"
    assert current.json()["analysis"]["reference_price"] == "261000"

    revisions = client.get(
        f"/api/holdings/stocks/{stock_id}/analysis/2026-09-18/revisions"
    )
    assert revisions.status_code == 200
    assert len(revisions.json()) == 1
    assert revisions.json()[0]["revision_id"] == revision.id

    timeline = client.get(f"/api/holdings/stocks/{stock_id}/analysis/timeline")
    assert timeline.status_code == 200
    assert len(timeline.json()) == 1
    assert timeline.json()[0]["reference_price"] == "261000"

    stored = SimpleNamespace(
        analysis_day_id=day.id,
        revision=revision,
        created_revision=False,
        promoted_current=False,
    )
    fake = SimpleNamespace(
        analyze_latest_confirmed=lambda **kwargs: stored,
    )
    monkeypatch.setattr(holdings_api, "_history_service", lambda catalog: fake)
    refreshed = client.post(f"/api/holdings/stocks/{stock_id}/analysis/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["market_date"] == "2026-09-18"
    assert refreshed.json()["created_revision"] is False


def test_combined_timeline_and_kis_sync_endpoint_delegate_only(client, monkeypatch):
    stock_id = client.post(
        "/api/holdings/watch",
        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},
    ).json()["stock"]["stock_id"]
    client.post(
        "/api/holdings/manual/buy",
        json={
            "stock_id": stock_id,
            "quantity": "1",
            "unit_price": "70000",
            "effective_at": "2026-09-23T09:00:00+09:00",
        },
    )
    timeline = client.get(f"/api/holdings/stocks/{stock_id}/timeline")
    assert timeline.status_code == 200
    assert any(item["kind"] == "POSITION_EVENT" for item in timeline.json())

    result = SimpleNamespace(
        status="COMPLETED",
        sync_run_id="sync-1",
        account_id="account-1",
        observed_at="2026-09-23T00:00:00+00:00",
        page_count=1,
        holding_count=0,
        created_positions=0,
        reconciled_positions=0,
        closed_positions=0,
        unchanged_positions=0,
    )
    fake = SimpleNamespace(sync=lambda: result)
    monkeypatch.setattr(holdings_api, "_kis_sync_service", lambda catalog: fake)

    response = client.post("/api/holdings/kis/sync")
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["holding_count"] == 0


def test_router_has_no_scanner_strategy_risk_or_order_implementation():
    source = Path("backend/app/api/holdings.py").read_text(encoding="utf-8")
    assert "StockScannerService" not in source
    assert "app.strategy" not in source
    assert "app.risk" not in source
    assert "place_order" not in source
    assert "order_cash" not in source
