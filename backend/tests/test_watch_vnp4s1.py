from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.management import HoldingManagementService
from app.watch import (
    WATCH_POLICY_CONTRACT_VERSION,
    WATCH_SCHEMA_VERSION,
    WatchObservation,
    WatchPolicy,
    WatchPolicyError,
    WatchRuleRuntimeState,
    WatchRuleSpec,
    advance_watch_rule,
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
