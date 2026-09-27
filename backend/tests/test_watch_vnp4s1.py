from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.management import HoldingManagementService
from app.quotes.event_hub import QuoteEventHub
from app.quotes.models import QuoteCacheKey, QuoteSnapshot
from app.watch import (
    WATCH_POLICY_CONTRACT_VERSION,
    WATCH_SCHEMA_VERSION,
    WatchDemand,
    WatchCoordinator,
    WatchObservation,
    WatchPolicy,
    WatchPolicyError,
    WatchRuleRuntimeState,
    WatchRuleSpec,
    WatchService,
    advance_watch_rule,
    load_active_plan_watch_demands,
    production_watch_policy,
    watch_schema_available,
)
from tools.data.common import DataToolError
from tools.data.migrate_holdings_decision_vnp3s1 import (
    migrate_holdings_decision_store,
)
from tools.data.migrate_watch_vnp4s1 import migrate_watch_store


T0 = "2026-09-28T09:00:00+09:00"
T1 = "2026-09-28T09:10:00+09:00"
BASE_TIME = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)


def _env(tmp_path: Path):
    db = tmp_path / "holdings.db"
    catalog = HoldingsCatalog(db)
    catalog.initialize()
    migrate_holdings_decision_store(db)

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
        effective_at=T0,
    )

    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=opened.stock_id,
        market_date="2026-09-28",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="watch-r1",
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
        source_versions={"fixture": "watch-r1"},
        snapshot={"fixture": "watch-r1"},
        computed_at=T1,
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )
    plan = HoldingManagementService(catalog).apply_analysis_plan(
        position_id=opened.position.id,
        analysis_revision_id=revision.id,
        applied_at=T1,
    )
    return db, catalog, opened, plan


def _test_policy(
    *,
    confirmation: int = 2,
    rearm: int = 2,
    distance_bps: int = 100,
    max_age: float = 5.0,
) -> WatchPolicy:
    return WatchPolicy(
        policy_version="TEST_ONLY",
        enabled=True,
        confirmation_observations=confirmation,
        rearm_observations=rearm,
        rearm_distance_bps=distance_bps,
        max_quote_age_seconds=max_age,
    )


def _obs(
    seconds: int,
    price: str,
    *,
    age: float = 0.0,
    coverage_ok: bool = True,
    reason: str | None = None,
) -> WatchObservation:
    return WatchObservation(
        price=Decimal(price),
        observed_at=BASE_TIME + timedelta(seconds=seconds),
        age_seconds=age,
        coverage_ok=coverage_ok,
        coverage_reason=reason,
    )


def test_watch_migration_is_explicit_idempotent_and_does_not_backfill_active_plan(
    tmp_path: Path,
):
    db, catalog, opened, plan = _env(tmp_path)
    events_before = catalog.list_position_events(opened.position.id)

    first = migrate_watch_store(db)
    second = migrate_watch_store(db)

    assert first == second
    assert first["schema_version"] == WATCH_SCHEMA_VERSION
    assert first["policy_contract_version"] == WATCH_POLICY_CONTRACT_VERSION
    assert first["historical_watch_backfill_performed"] is False
    assert first["production_watch_activation_performed"] is False
    assert first["source_state"]["active_plan_count"] == 1

    with sqlite3.connect(db) as conn:
        assert watch_schema_available(conn) is True
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_watch_setting"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_watch_rule"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_watch_episode"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_watch_coverage_gap"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_watch_notification_outbox"
        ).fetchone()[0] == 0

    assert catalog.list_position_events(opened.position.id) == events_before
    active = HoldingManagementService(catalog).get_active_plan(opened.position.id)
    assert active is not None
    assert active.id == plan.id


def test_watch_migration_requires_p3s1(tmp_path: Path):
    db = tmp_path / "holdings.db"
    HoldingsCatalog(db).initialize()

    with pytest.raises(DataToolError):
        migrate_watch_store(db)

    with sqlite3.connect(db) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "holding_watch_schema_meta" not in names


def test_production_watch_policy_is_blocked_without_invented_thresholds():
    policy = production_watch_policy()

    assert policy.enabled is False
    assert policy.confirmation_observations is None
    assert policy.rearm_observations is None
    assert policy.rearm_distance_bps is None
    assert policy.max_quote_age_seconds is None
    assert policy.blocked_reason == "OPERATING_THRESHOLDS_UNAPPROVED"

    with pytest.raises(WatchPolicyError):
        policy.require_enabled()


def test_enabled_watch_policy_requires_explicit_confirmation_rearm_and_freshness():
    with pytest.raises(WatchPolicyError):
        WatchPolicy(
            policy_version="INVALID",
            enabled=True,
            confirmation_observations=None,
            rearm_observations=None,
            rearm_distance_bps=None,
            max_quote_age_seconds=None,
        )

    policy = _test_policy()
    assert policy.require_enabled() is policy


def test_stop_rule_requires_confirmation_and_transient_touch_does_not_alert():
    rule = WatchRuleSpec(
        rule_kind="STOP",
        direction="BELOW_OR_EQUAL",
        threshold_price=Decimal("90"),
    )
    policy = _test_policy(confirmation=2)
    runtime = WatchRuleRuntimeState()

    entered = advance_watch_rule(rule, runtime, _obs(1, "89"), policy)
    assert entered.event == "CONDITION_ENTERED"
    assert entered.current.state == "PENDING_CONFIRMATION"
    assert entered.current.confirmation_count == 1

    reset = advance_watch_rule(rule, entered.current, _obs(2, "91"), policy)
    assert reset.event == "CONFIRMATION_RESET"
    assert reset.current.state == "ARMED"
    assert reset.current.confirmation_count == 0

    entered_again = advance_watch_rule(rule, reset.current, _obs(3, "89"), policy)
    confirmed = advance_watch_rule(
        rule,
        entered_again.current,
        _obs(4, "88"),
        policy,
    )
    assert confirmed.event == "CONFIRMED"
    assert confirmed.current.state == "CONFIRMED"


def test_confirmed_rule_resolves_then_rearms_only_after_hysteresis_observations():
    rule = WatchRuleSpec(
        rule_kind="STOP",
        direction="BELOW_OR_EQUAL",
        threshold_price=Decimal("90"),
    )
    policy = _test_policy(confirmation=1, rearm=2, distance_bps=100)

    confirmed = advance_watch_rule(
        rule,
        WatchRuleRuntimeState(),
        _obs(1, "89"),
        policy,
    )
    assert confirmed.current.state == "CONFIRMED"

    resolved = advance_watch_rule(
        rule,
        confirmed.current,
        _obs(2, "91"),
        policy,
    )
    assert resolved.event == "RESOLVED"
    assert resolved.current.state == "RESOLVED"
    assert resolved.current.rearm_count == 0

    near_line = advance_watch_rule(
        rule,
        resolved.current,
        _obs(3, "90.5"),
        policy,
    )
    assert near_line.current.state == "RESOLVED"
    assert near_line.current.rearm_count == 0

    first_rearm = advance_watch_rule(
        rule,
        near_line.current,
        _obs(4, "91"),
        policy,
    )
    assert first_rearm.current.state == "RESOLVED"
    assert first_rearm.current.rearm_count == 1

    rearmed = advance_watch_rule(
        rule,
        first_rearm.current,
        _obs(5, "91.5"),
        policy,
    )
    assert rearmed.event == "REARMED"
    assert rearmed.current.state == "ARMED"


def test_target_rule_uses_above_or_equal_direction():
    rule = WatchRuleSpec(
        rule_kind="TARGET1",
        direction="ABOVE_OR_EQUAL",
        threshold_price=Decimal("120"),
    )
    policy = _test_policy(confirmation=1)

    below = advance_watch_rule(
        rule,
        WatchRuleRuntimeState(),
        _obs(1, "119"),
        policy,
    )
    assert below.current.state == "ARMED"

    hit = advance_watch_rule(rule, below.current, _obs(2, "120"), policy)
    assert hit.event == "CONFIRMED"
    assert hit.current.state == "CONFIRMED"


def test_coverage_gap_and_stale_quote_reset_unfinished_confirmation():
    rule = WatchRuleSpec(
        rule_kind="STOP",
        direction="BELOW_OR_EQUAL",
        threshold_price=Decimal("90"),
    )
    policy = _test_policy(confirmation=2, max_age=5)

    entered = advance_watch_rule(
        rule,
        WatchRuleRuntimeState(),
        _obs(1, "89"),
        policy,
    )
    gap = advance_watch_rule(
        rule,
        entered.current,
        _obs(
            2,
            "88",
            coverage_ok=False,
            reason="WS_RECONNECT",
        ),
        policy,
    )
    assert gap.accepted is False
    assert gap.event == "COVERAGE_GAP_RESET"
    assert gap.coverage_reason == "WS_RECONNECT"
    assert gap.current.state == "ARMED"
    assert gap.current.confirmation_count == 0

    entered_again = advance_watch_rule(
        rule,
        gap.current,
        _obs(3, "89"),
        policy,
    )
    stale = advance_watch_rule(
        rule,
        entered_again.current,
        _obs(4, "88", age=6),
        policy,
    )
    assert stale.accepted is False
    assert stale.coverage_reason == "STALE_QUOTE"
    assert stale.current.state == "ARMED"


def test_out_of_order_observation_is_ignored_without_mutating_runtime():
    rule = WatchRuleSpec(
        rule_kind="STOP",
        direction="BELOW_OR_EQUAL",
        threshold_price=Decimal("90"),
    )
    policy = _test_policy()

    first = advance_watch_rule(
        rule,
        WatchRuleRuntimeState(),
        _obs(10, "95"),
        policy,
    )
    older = advance_watch_rule(
        rule,
        first.current,
        _obs(9, "80"),
        policy,
    )

    assert older.accepted is False
    assert older.event == "OUT_OF_ORDER_IGNORED"
    assert older.current == first.current



class _FakeWebSocketManager:
    def __init__(self, *, reject: bool = False):
        self.reject = reject
        self.touched: list[QuoteCacheKey] = []

    def touch_demand(self, key: QuoteCacheKey) -> bool:
        self.touched.append(key)
        return not self.reject

    def subscription_error(self, _key: QuoteCacheKey) -> str | None:
        return "SUBSCRIPTION_LIMIT" if self.reject else None


def _quote_key(
    *,
    market: str = "KOSPI",
    ticker: str = "005930",
    venue: str = "INTEGRATED",
) -> QuoteCacheKey:
    return QuoteCacheKey(
        environment="virtual",
        credential_fingerprint="f" * 64,
        market=market,
        ticker=ticker,
        venue=venue,  # type: ignore[arg-type]
    )


def _snapshot(key: QuoteCacheKey, price: str = "91") -> QuoteSnapshot:
    return QuoteSnapshot(
        market=key.market,
        ticker=key.ticker,
        name="삼성전자",
        venue=key.venue,
        provider_market_division="UN",
        environment=key.environment,
        current_price=Decimal(price),
        change_amount=Decimal("1"),
        change_rate=Decimal("1"),
        change_sign="2",
        open_price=Decimal("90"),
        high_price=Decimal("92"),
        low_price=Decimal("89"),
        base_price=Decimal("90"),
        accumulated_volume=Decimal("1000"),
        provider_timestamp="2026-09-28T09:00:00+09:00",
        received_at=BASE_TIME,
        transport="WEBSOCKET",
    )


def test_active_plan_watch_demand_is_read_only_projection(tmp_path: Path):
    _db, catalog, opened, plan = _env(tmp_path)
    events_before = catalog.list_position_events(opened.position.id)

    demands = load_active_plan_watch_demands(catalog)

    assert len(demands) == 1
    demand = demands[0]
    assert demand.position_id == opened.position.id
    assert demand.plan_id == plan.id
    assert demand.plan_version == plan.plan_version
    assert demand.market == "KOSPI"
    assert demand.ticker == "005930"
    assert demand.stop_price == Decimal("90")
    assert demand.target1_price == Decimal("120")
    assert demand.target2_price == Decimal("130")
    assert catalog.list_position_events(opened.position.id) == events_before
    active = HoldingManagementService(catalog).get_active_plan(opened.position.id)
    assert active is not None
    assert active.id == plan.id


@pytest.mark.asyncio
async def test_blocked_production_policy_creates_no_server_quote_demand(
    tmp_path: Path,
):
    catalog = HoldingsCatalog(tmp_path / "holdings.db")
    manager = _FakeWebSocketManager()
    hub = QuoteEventHub()
    demand = WatchDemand(
        position_id="p1",
        plan_id="plan1",
        plan_version=1,
        market="KOSPI",
        ticker="005930",
        stop_price=Decimal("90"),
        target1_price=Decimal("120"),
        target2_price=Decimal("130"),
    )
    coordinator = WatchCoordinator(
        catalog,
        policy_provider=production_watch_policy,
        demand_loader=lambda _catalog: [demand],
        resolve_key=lambda **kwargs: _quote_key(**kwargs),
        websocket_manager=manager,
        event_hub=hub,
    )

    result = await coordinator.reconcile_once()

    assert result.enabled is False
    assert result.blocked_reason == "OPERATING_THRESHOLDS_UNAPPROVED"
    assert manager.touched == []
    assert await hub.subscriber_count(_quote_key()) == 0


@pytest.mark.asyncio
async def test_watch_demand_deduplicates_resource_and_receives_quotes_without_browser(
    tmp_path: Path,
):
    catalog = HoldingsCatalog(tmp_path / "holdings.db")
    manager = _FakeWebSocketManager()
    hub = QuoteEventHub()
    key = _quote_key()
    received: list[tuple[str, str]] = []

    demands = [
        WatchDemand(
            position_id="p1",
            plan_id="plan1",
            plan_version=1,
            market="KOSPI",
            ticker="005930",
            stop_price=Decimal("90"),
            target1_price=Decimal("120"),
            target2_price=Decimal("130"),
        ),
        WatchDemand(
            position_id="p2",
            plan_id="plan2",
            plan_version=3,
            market="KOSPI",
            ticker="005930",
            stop_price=Decimal("88"),
            target1_price=None,
            target2_price=None,
        ),
    ]

    async def on_quote(demand: WatchDemand, snapshot: QuoteSnapshot) -> None:
        received.append((demand.position_id, str(snapshot.current_price)))

    coordinator = WatchCoordinator(
        catalog,
        policy_provider=lambda: _test_policy(),
        demand_loader=lambda _catalog: demands,
        resolve_key=lambda **_kwargs: key,
        websocket_manager=manager,
        event_hub=hub,
        on_quote=on_quote,
    )

    result = await coordinator.reconcile_once()
    await asyncio.sleep(0)

    assert result.enabled is True
    assert result.demand_count == 2
    assert result.resource_count == 1
    assert result.leased_count == 1
    assert result.rejected_count == 0
    assert manager.touched == [key]
    assert await hub.subscriber_count(key) == 1

    await hub.publish(key, _snapshot(key, "91"))
    await asyncio.sleep(0)

    assert sorted(received) == [("p1", "91"), ("p2", "91")]

    await coordinator.stop()
    assert await hub.subscriber_count(key) == 0


@pytest.mark.asyncio
async def test_browser_and_watch_have_separate_consumers_on_same_quote_resource(
    tmp_path: Path,
):
    catalog = HoldingsCatalog(tmp_path / "holdings.db")
    manager = _FakeWebSocketManager()
    hub = QuoteEventHub()
    key = _quote_key()
    received: list[str] = []
    demand = WatchDemand(
        position_id="p1",
        plan_id="plan1",
        plan_version=1,
        market="KOSPI",
        ticker="005930",
        stop_price=Decimal("90"),
        target1_price=Decimal("120"),
        target2_price=Decimal("130"),
    )

    coordinator = WatchCoordinator(
        catalog,
        policy_provider=lambda: _test_policy(),
        demand_loader=lambda _catalog: [demand],
        resolve_key=lambda **_kwargs: key,
        websocket_manager=manager,
        event_hub=hub,
        on_quote=lambda item, _snapshot_value: received.append(item.position_id),
    )

    await coordinator.reconcile_once()
    await asyncio.sleep(0)
    browser_queue = await hub.subscribe(key)
    assert await hub.subscriber_count(key) == 2

    snapshot = _snapshot(key)
    await hub.publish(key, snapshot)
    browser_received = await asyncio.wait_for(browser_queue.get(), timeout=1)
    await asyncio.sleep(0)

    assert browser_received == snapshot
    assert received == ["p1"]

    await hub.unsubscribe(key, browser_queue)
    await coordinator.stop()
    assert await hub.subscriber_count(key) == 0


@pytest.mark.asyncio
async def test_subscription_rejection_reports_coverage_issue_without_consumer(
    tmp_path: Path,
):
    catalog = HoldingsCatalog(tmp_path / "holdings.db")
    manager = _FakeWebSocketManager(reject=True)
    hub = QuoteEventHub()
    key = _quote_key()
    coverage: list[tuple[str, str]] = []
    demand = WatchDemand(
        position_id="p1",
        plan_id="plan1",
        plan_version=1,
        market="KOSPI",
        ticker="005930",
        stop_price=Decimal("90"),
        target1_price=None,
        target2_price=None,
    )

    coordinator = WatchCoordinator(
        catalog,
        policy_provider=lambda: _test_policy(),
        demand_loader=lambda _catalog: [demand],
        resolve_key=lambda **_kwargs: key,
        websocket_manager=manager,
        event_hub=hub,
        on_coverage_issue=lambda item, reason: coverage.append(
            (item.position_id, reason)
        ),
    )

    result = await coordinator.reconcile_once()

    assert result.leased_count == 0
    assert result.rejected_count == 1
    assert coverage == [("p1", "SUBSCRIPTION_LIMIT")]
    assert await hub.subscriber_count(key) == 0
    await coordinator.stop()



def _snapshot_at(
    key: QuoteCacheKey,
    seconds: int,
    price: str,
) -> QuoteSnapshot:
    base = _snapshot(key, price)
    return QuoteSnapshot(
        market=base.market,
        ticker=base.ticker,
        name=base.name,
        venue=base.venue,
        provider_market_division=base.provider_market_division,
        environment=base.environment,
        current_price=base.current_price,
        change_amount=base.change_amount,
        change_rate=base.change_rate,
        change_sign=base.change_sign,
        open_price=base.open_price,
        high_price=base.high_price,
        low_price=base.low_price,
        base_price=base.base_price,
        accumulated_volume=base.accumulated_volume,
        provider_timestamp=base.provider_timestamp,
        received_at=BASE_TIME + timedelta(seconds=seconds),
        transport=base.transport,
    )


def test_durable_watch_confirmation_creates_single_episode_and_notification(
    tmp_path: Path,
):
    db, catalog, opened, plan = _env(tmp_path)
    migrate_watch_store(db)
    events_before = catalog.list_position_events(opened.position.id)
    demand = load_active_plan_watch_demands(catalog)[0]
    policy = _test_policy(confirmation=2, max_age=60)
    service = WatchService(
        catalog,
        policy_provider=lambda: policy,
        clock=lambda: BASE_TIME + timedelta(seconds=10),
    )
    key = _quote_key()

    reconciled = service.reconcile([demand])
    first = service.process_quote(demand, _snapshot_at(key, 1, "89"))
    second = service.process_quote(demand, _snapshot_at(key, 2, "88"))
    repeated = service.process_quote(demand, _snapshot_at(key, 3, "87"))

    assert reconciled["active_settings"] == 1
    assert any(
        item["event"] == "CONDITION_ENTERED"
        and item["rule_kind"] == "STOP"
        for item in first["transitions"]
    )
    assert any(
        item["event"] == "CONFIRMED"
        and item["rule_kind"] == "STOP"
        for item in second["transitions"]
    )
    assert all(
        item["event"] != "CONFIRMED"
        for item in repeated["transitions"]
    )

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        settings = conn.execute(
            "SELECT * FROM holding_watch_setting"
        ).fetchall()
        rules = conn.execute(
            "SELECT * FROM holding_watch_rule ORDER BY rule_kind"
        ).fetchall()
        episodes = conn.execute(
            "SELECT * FROM holding_watch_episode"
        ).fetchall()
        notifications = conn.execute(
            "SELECT * FROM holding_watch_notification_outbox"
        ).fetchall()

    assert len(settings) == 1
    assert str(settings[0]["plan_id"]) == plan.id
    assert len(rules) == 3
    stop_rule = next(row for row in rules if row["rule_kind"] == "STOP")
    assert stop_rule["state"] == "CONFIRMED"
    assert stop_rule["confirmation_observations"] == 2
    assert stop_rule["rearm_observations"] == 2
    assert stop_rule["rearm_distance_bps"] == 100
    assert stop_rule["max_quote_age_seconds"] == 60
    assert len(episodes) == 1
    assert episodes[0]["status"] == "OPEN"
    assert episodes[0]["confirmed_at"] is not None
    assert len(notifications) == 1
    assert notifications[0]["delivery_status"] == "PENDING"
    assert catalog.list_position_events(opened.position.id) == events_before
    active = HoldingManagementService(catalog).get_active_plan(opened.position.id)
    assert active is not None
    assert active.id == plan.id


def test_watch_coverage_gap_is_durable_idempotent_and_resets_pending_only(
    tmp_path: Path,
):
    db, catalog, opened, _plan = _env(tmp_path)
    migrate_watch_store(db)
    demand = load_active_plan_watch_demands(catalog)[0]
    policy = _test_policy(confirmation=2, max_age=60)
    service = WatchService(
        catalog,
        policy_provider=lambda: policy,
        clock=lambda: BASE_TIME + timedelta(seconds=10),
    )
    key = _quote_key()

    service.reconcile([demand])
    service.process_quote(demand, _snapshot_at(key, 1, "89"))
    service.record_coverage_issue(demand, "WS_RECONNECT")
    service.record_coverage_issue(demand, "WS_RECONNECT")

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        stop = conn.execute(
            """
            SELECT * FROM holding_watch_rule
            WHERE rule_kind='STOP'
            """
        ).fetchone()
        episodes = conn.execute(
            "SELECT * FROM holding_watch_episode"
        ).fetchall()
        gaps = conn.execute(
            "SELECT * FROM holding_watch_coverage_gap"
        ).fetchall()

    assert stop is not None
    assert stop["state"] == "ARMED"
    assert stop["confirmation_count"] == 0
    assert len(episodes) == 1
    assert episodes[0]["status"] == "INVALIDATED"
    assert episodes[0]["resolution_reason"] == "COVERAGE_GAP:WS_RECONNECT"
    assert len(gaps) == 1
    assert gaps[0]["status"] == "OPEN"

    service.process_quote(demand, _snapshot_at(key, 3, "95"))
    with sqlite3.connect(db) as conn:
        closed_gap = conn.execute(
            "SELECT status,ended_at FROM holding_watch_coverage_gap"
        ).fetchone()
    assert closed_gap[0] == "CLOSED"
    assert closed_gap[1] is not None


def test_watch_plan_change_invalidates_old_setting_and_preserves_history(
    tmp_path: Path,
):
    db, catalog, opened, old_plan = _env(tmp_path)
    migrate_watch_store(db)
    policy = _test_policy(max_age=60)
    service = WatchService(
        catalog,
        policy_provider=lambda: policy,
        clock=lambda: BASE_TIME + timedelta(seconds=30),
    )
    old_demand = load_active_plan_watch_demands(catalog)[0]
    service.reconcile([old_demand])

    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=opened.stock_id,
        market_date="2026-09-28",
    )
    revision2 = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="watch-r2",
        strategy_key="trend_following",
        action_state="WATCH",
        risk_state="READY",
        reference_price="101",
        stop_price="92",
        target1_price="125",
        target2_price="135",
        scanner_version="test",
        analysis_engine_version="test",
        policy_version="test",
        source_versions={"fixture": "watch-r2"},
        snapshot={"fixture": "watch-r2"},
        computed_at="2026-09-28T09:20:00+09:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision2.id,
    )
    new_plan = HoldingManagementService(catalog).apply_analysis_plan(
        position_id=opened.position.id,
        analysis_revision_id=revision2.id,
        applied_at="2026-09-28T09:21:00+09:00",
    )
    assert new_plan.id != old_plan.id

    new_demand = load_active_plan_watch_demands(catalog)[0]
    service.reconcile([new_demand])

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        settings = conn.execute(
            """
            SELECT * FROM holding_watch_setting
            ORDER BY created_at,rowid
            """
        ).fetchall()
        old_rules = conn.execute(
            """
            SELECT * FROM holding_watch_rule
            WHERE setting_id=?
            """,
            (settings[0]["id"],),
        ).fetchall()

    assert len(settings) == 2
    assert settings[0]["plan_id"] == old_plan.id
    assert settings[0]["status"] == "DISABLED"
    assert settings[0]["disabled_reason"] == "PLAN_OR_POLICY_CHANGED"
    assert all(row["status"] == "CLOSED" for row in old_rules)
    assert settings[1]["plan_id"] == new_plan.id
    assert settings[1]["status"] == "ACTIVE"
