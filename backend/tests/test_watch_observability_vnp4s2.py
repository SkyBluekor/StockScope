from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.management import HoldingManagementService
from app.quotes.models import QuoteSnapshot
from app.watch import WatchPolicy, WatchService, load_active_plan_watch_demands
from app.watch.observability import WatchRuntimeObserver, read_watch_runtime_health
from tools.data.migrate_holdings_decision_vnp3s1 import (
    migrate_holdings_decision_store,
)
from tools.data.migrate_watch_observability_vnp4s2 import (
    WATCH_OBSERVABILITY_SCHEMA_VERSION,
    migrate_watch_observability,
)
from tools.data.migrate_watch_vnp4s1 import migrate_watch_store


BASE = datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)


def _env(tmp_path: Path):
    db = tmp_path / "holdings.db"
    catalog = HoldingsCatalog(db)
    catalog.initialize()
    migrate_holdings_decision_store(db)

    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동 기록",
    )
    opened = PositionLifecycleService(catalog).register_initial_holding(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        position_account_id=account.id,
        quantity="10",
        average_price="100",
        effective_at="2026-09-29T09:00:00+09:00",
    )
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=opened.stock_id,
        market_date="2026-09-29",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="next4-watch",
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
        source_versions={"fixture": "next4"},
        snapshot={"fixture": "next4"},
        computed_at="2026-09-29T09:01:00+09:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )
    HoldingManagementService(catalog).apply_analysis_plan(
        position_id=opened.position.id,
        analysis_revision_id=revision.id,
        applied_at="2026-09-29T09:02:00+09:00",
    )
    migrate_watch_store(db)
    return db, catalog, opened


def _policy() -> WatchPolicy:
    return WatchPolicy(
        policy_version="NEXT4_TEST_ONLY",
        enabled=True,
        confirmation_observations=2,
        rearm_observations=2,
        rearm_distance_bps=100,
        max_quote_age_seconds=60,
    )


def _snapshot(at: datetime, price: str = "100") -> QuoteSnapshot:
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
        low_price=Decimal("100"),
        base_price=Decimal("100"),
        accumulated_volume=Decimal("1000"),
        provider_timestamp=at.isoformat(),
        received_at=at,
        transport="WEBSOCKET",
    )


def test_watch_observability_migration_is_additive_without_backfill(tmp_path: Path):
    db, _catalog, _opened = _env(tmp_path)

    before = sqlite3.connect(db).execute(
        "SELECT COUNT(*) FROM holding_watch_setting"
    ).fetchone()[0]

    result = migrate_watch_observability(db)

    assert result["schema_version"] == WATCH_OBSERVABILITY_SCHEMA_VERSION
    assert result["backfilled_rows"] == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_watch_setting"
        ).fetchone()[0] == before
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_watch_runtime_session"
        ).fetchone()[0] == 0


def test_runtime_restart_marks_previous_session_unmonitored(tmp_path: Path):
    db, catalog, _opened = _env(tmp_path)
    migrate_watch_observability(db)
    now = [BASE]

    first = WatchRuntimeObserver(catalog, clock=lambda: now[0])
    first_id = first.start(
        transport_state="CONNECTED",
        market_session_phase="REGULAR",
    )
    first.record_event("RECONCILE_OK", transport_state="CONNECTED")

    now[0] = BASE + timedelta(minutes=90)
    second = WatchRuntimeObserver(catalog, clock=lambda: now[0])
    second_id = second.start(
        transport_state="CONNECTING",
        market_session_phase="REGULAR",
    )

    health = read_watch_runtime_health(catalog)
    assert first_id is not None
    assert second_id is not None
    assert health["session"]["runtime_session_id"] == second_id
    assert health["session"]["continuity_state"] == "UNMONITORED"
    assert health["session"]["previous_session_id"] == first_id
    assert health["session"]["previous_last_heartbeat_at"] is not None

    with sqlite3.connect(db) as conn:
        previous = conn.execute(
            "SELECT status FROM holding_watch_runtime_session WHERE id=?",
            (first_id,),
        ).fetchone()
    assert previous[0] == "INTERRUPTED"


def test_quote_silence_is_session_aware_and_fresh_quote_closes_gap(tmp_path: Path):
    db, catalog, _opened = _env(tmp_path)
    now = [BASE]
    policy = _policy()
    service = WatchService(
        catalog,
        policy_provider=lambda: policy,
        clock=lambda: now[0],
    )
    demand = load_active_plan_watch_demands(catalog)[0]
    service.reconcile([demand], policy)

    now[0] = BASE + timedelta(seconds=61)
    closed = service.check_quote_silence(
        [demand],
        market_session_phase="CLOSED",
        policy=policy,
    )
    assert closed == {"checked": 0, "gaps": 0}

    regular = service.check_quote_silence(
        [demand],
        market_session_phase="REGULAR",
        policy=policy,
    )
    assert regular == {"checked": 1, "gaps": 1}

    with sqlite3.connect(db) as conn:
        gap = conn.execute(
            """
            SELECT reason_code,status
            FROM holding_watch_coverage_gap
            WHERE reason_code='QUOTE_NOT_RECEIVED'
            """
        ).fetchone()
    assert gap == ("QUOTE_NOT_RECEIVED", "OPEN")

    service.process_quote(demand, _snapshot(now[0], "100"), policy)
    with sqlite3.connect(db) as conn:
        gap = conn.execute(
            """
            SELECT status,ended_at
            FROM holding_watch_coverage_gap
            WHERE reason_code='QUOTE_NOT_RECEIVED'
            """
        ).fetchone()
    assert gap[0] == "CLOSED"
    assert gap[1] is not None
