from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.watch as watch_api
from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.management import HoldingManagementService
from app.quotes.models import QuoteCacheKey, QuoteSnapshot
from app.watch import WatchPolicy, WatchService, load_active_plan_watch_demands
from tools.data.migrate_holdings_decision_vnp3s1 import (
    migrate_holdings_decision_store,
)
from tools.data.migrate_watch_vnp4s1 import migrate_watch_store


BASE_TIME = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def api_env(tmp_path: Path, monkeypatch):
    holdings_db = tmp_path / "holdings.db"
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings_db))

    catalog = HoldingsCatalog(holdings_db)
    catalog.initialize()
    migrate_holdings_decision_store(holdings_db)

    lifecycle = PositionLifecycleService(catalog)
    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동 기록",
    )
    opened = lifecycle.register_initial_holding(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        position_account_id=account.id,
        quantity="10",
        average_price="100",
        effective_at="2026-09-28T09:00:00+09:00",
    )
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=opened.stock_id,
        market_date="2026-09-28",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="watch-api-r1",
        strategy_key="trend_following",
        action_state="WATCH",
        risk_state="READY",
        reference_price="100",
        stop_price="90",
        target1_price="120",
        target2_price="130",
        scanner_version="test",
        analysis_engine_version="test",
        policy_version="test",
        source_versions={"fixture": "watch-api"},
        snapshot={"fixture": True},
        computed_at="2026-09-28T09:10:00+09:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )
    plan = HoldingManagementService(catalog).apply_analysis_plan(
        position_id=opened.position.id,
        analysis_revision_id=revision.id,
        applied_at="2026-09-28T09:11:00+09:00",
    )

    app = FastAPI()
    app.include_router(watch_api.router, prefix="/api")
    return {
        "client": TestClient(app),
        "catalog": catalog,
        "opened": opened,
        "plan": plan,
        "holdings_db": holdings_db,
    }


def _test_policy() -> WatchPolicy:
    return WatchPolicy(
        policy_version="TEST_ONLY",
        enabled=True,
        confirmation_observations=2,
        rearm_observations=2,
        rearm_distance_bps=100,
        max_quote_age_seconds=60,
    )


def _snapshot(seconds: int, price: str) -> QuoteSnapshot:
    return QuoteSnapshot(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        venue="INTEGRATED",
        provider_market_division="UN",
        environment="virtual",
        current_price=Decimal(price),
        change_amount=Decimal("0"),
        change_rate=Decimal("0"),
        change_sign="3",
        open_price=Decimal("100"),
        high_price=Decimal("100"),
        low_price=Decimal(price),
        base_price=Decimal("100"),
        accumulated_volume=Decimal("1000"),
        provider_timestamp="2026-09-28T09:00:00+09:00",
        received_at=BASE_TIME + timedelta(seconds=seconds),
        transport="WEBSOCKET",
    )


def test_watch_status_read_before_migration_has_no_schema_side_effect(api_env):
    response = api_env["client"].get("/api/watch/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["migration_required"] is True
    assert payload["policy_enabled"] is False
    assert payload["blocked_reason"] == "OPERATING_THRESHOLDS_UNAPPROVED"

    with sqlite3.connect(api_env["holdings_db"]) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "holding_watch_schema_meta" not in names
    assert "holding_watch_setting" not in names


def test_watch_position_after_migration_exposes_blocked_policy_without_creating_setting(
    api_env,
):
    migrate_watch_store(api_env["holdings_db"])

    response = api_env["client"].get(
        f"/api/watch/positions/{api_env['opened'].position.id}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["migration_required"] is False
    assert payload["policy_enabled"] is False
    assert payload["blocked_reason"] == "OPERATING_THRESHOLDS_UNAPPROVED"
    assert payload["setting"] is None
    assert payload["rules"] == []
    assert payload["open_gaps"] == []
    assert payload["latest_notification"] is None

    with sqlite3.connect(api_env["holdings_db"]) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_watch_setting"
        ).fetchone()[0] == 0


def test_watch_notification_api_lists_and_marks_durable_notification_read(api_env):
    migrate_watch_store(api_env["holdings_db"])
    catalog = api_env["catalog"]
    demand = load_active_plan_watch_demands(catalog)[0]
    policy = _test_policy()
    service = WatchService(
        catalog,
        policy_provider=lambda: policy,
        clock=lambda: BASE_TIME + timedelta(seconds=10),
    )

    service.reconcile([demand])
    service.process_quote(demand, _snapshot(1, "89"))
    service.process_quote(demand, _snapshot(2, "88"))

    listed = api_env["client"].get(
        "/api/watch/notifications?unread_only=true"
    )
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["count"] == 1
    item = payload["items"][0]
    assert item["position_id"] == api_env["opened"].position.id
    assert item["plan_id"] == api_env["plan"].id
    assert item["ticker"] == "005930"
    assert item["name"] == "삼성전자"
    assert item["payload"]["rule_kind"] == "STOP"
    assert item["payload"]["threshold_price"] == "90"
    assert item["payload"]["confirmed_price"] == "88"
    assert item["read_at"] is None

    read = api_env["client"].post(
        f"/api/watch/notifications/{item['notification_id']}/read"
    )
    assert read.status_code == 200
    assert read.json()["delivery_status"] == "DELIVERED"
    assert read.json()["read_at"] is not None

    unread = api_env["client"].get(
        "/api/watch/notifications?unread_only=true"
    )
    assert unread.status_code == 200
    assert unread.json()["items"] == []

    all_rows = api_env["client"].get("/api/watch/notifications")
    assert all_rows.status_code == 200
    assert all_rows.json()["count"] == 1
    assert all_rows.json()["items"][0]["read_at"] is not None


def test_watch_notification_read_missing_id_returns_404(api_env):
    migrate_watch_store(api_env["holdings_db"])

    response = api_env["client"].post(
        "/api/watch/notifications/missing/read"
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "WATCH_NOTIFICATION_NOT_FOUND"
