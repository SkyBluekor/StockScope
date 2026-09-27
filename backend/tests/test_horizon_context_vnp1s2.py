from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.management import HoldingManagementService, HoldingsManagementError
from app.horizon import (
    HORIZON_POLICY_VERSION,
    HorizonPolicyError,
    horizon_policy_catalog,
    require_horizon_activatable,
    resolve_horizon_context,
)
from app.horizon_context import (
    ANALYSIS_HORIZON_TABLE,
    EXECUTION_HORIZON_TABLE,
    PLAN_HORIZON_TABLE,
    VALIDATION_HORIZON_TABLE,
    get_analysis_horizon,
    get_execution_horizon,
    get_plan_horizon,
    get_validation_horizon,
    set_analysis_horizon,
)
from app.simulation.execution_catalog import (
    ExecutionCatalogError,
    HistoricalExecutionCatalog,
)
from app.simulation.validation_catalog import HistoricalValidationCatalog
from tools.data.backup_runtime import create_backup
from tools.data.migrate_horizon_context_vnp1s2 import migrate_horizon_context
from tools.data.restore_runtime import restore_backup


T0 = "2026-09-27T00:00:00+00:00"
T1 = "2026-09-27T01:00:00+00:00"


def _holdings_fixture(path: Path):
    catalog = HoldingsCatalog(path)
    catalog.initialize()
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
        effective_at=T0,
    )
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=opened.stock_id,
        market_date="2026-09-26",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="horizon-fixture-v1",
        strategy_key="trend_following",
        action_state="READY",
        risk_state="READY",
        reference_price="100",
        stop_price="90",
        target1_price="110",
        target2_price="120",
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_SINGLE_STOCK_V1",
        policy_version="PROD_EXIT_V1",
        source_versions={},
        snapshot={},
        computed_at=T0,
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )
    return catalog, opened.position.id, revision.id


def _simulation_fixture(path: Path):
    validation = HistoricalValidationCatalog(path)
    validation.initialize()
    execution = HistoricalExecutionCatalog(path)
    execution.initialize()
    return validation, execution


def _draft(catalog: HistoricalValidationCatalog, name: str, *, horizon=None):
    return catalog.create_draft(
        name=name,
        market_scope="KOSPI",
        requested_period_type="custom",
        requested_start_month="2026-09",
        requested_end_month="2026-09",
        resolved_start_date="2026-09-25",
        resolved_end_date="2026-09-25",
        trading_day_count=1,
        horizon_context=horizon,
    )


def test_horizon_contract_does_not_invent_numeric_policy() -> None:
    legacy = resolve_horizon_context(None)
    assert legacy.intent == "LEGACY_UNSPECIFIED"
    assert legacy.policy_version is None
    assert legacy.support_status == "LEGACY_UNSPECIFIED"

    for intent in ("SHORT", "MEDIUM", "LONG"):
        context = resolve_horizon_context(intent)
        assert context.policy_version == HORIZON_POLICY_VERSION
        assert context.support_status == "EVALUATION_PENDING"
        assert context.review_cycle_trading_days is None
        assert context.time_stop_trading_days is None
        with pytest.raises(HorizonPolicyError) as caught:
            require_horizon_activatable(context)
        assert caught.value.code == "HORIZON_POLICY_NOT_ACTIVE"

    policy = horizon_policy_catalog()
    assert policy["numeric_policy_approved"] is False
    assert policy["rules"]["tracking_5_10_20_are_observation_windows"] is True
    assert policy["rules"]["validation_20d_is_not_horizon_intent"] is True


def test_horizon_migration_is_repeatable_and_does_not_backfill(tmp_path: Path) -> None:
    holdings, _, revision_id = _holdings_fixture(tmp_path / "holdings.db")
    validation, _ = _simulation_fixture(tmp_path / "simulation.db")

    with holdings.connection() as conn:
        assert get_analysis_horizon(conn, revision_id).intent == "LEGACY_UNSPECIFIED"

    first = migrate_horizon_context(
        holdings_db=holdings.db_path,
        simulation_db=validation.db_path,
    )
    second = migrate_horizon_context(
        holdings_db=holdings.db_path,
        simulation_db=validation.db_path,
    )
    assert first == second

    with holdings.connection() as conn:
        assert conn.execute(
            f"SELECT COUNT(*) FROM {ANALYSIS_HORIZON_TABLE}"
        ).fetchone()[0] == 0
        assert conn.execute(
            f"SELECT COUNT(*) FROM {PLAN_HORIZON_TABLE}"
        ).fetchone()[0] == 0
        assert get_analysis_horizon(conn, revision_id).intent == "LEGACY_UNSPECIFIED"

    with validation.connect() as conn:
        assert conn.execute(
            f"SELECT COUNT(*) FROM {VALIDATION_HORIZON_TABLE}"
        ).fetchone()[0] == 0
        assert conn.execute(
            f"SELECT COUNT(*) FROM {EXECUTION_HORIZON_TABLE}"
        ).fetchone()[0] == 0


def test_pending_analysis_horizon_cannot_be_applied_as_plan(tmp_path: Path) -> None:
    holdings, position_id, revision_id = _holdings_fixture(tmp_path / "holdings.db")
    simulation = tmp_path / "simulation.db"
    _simulation_fixture(simulation)
    migrate_horizon_context(
        holdings_db=holdings.db_path,
        simulation_db=simulation,
    )

    pending = resolve_horizon_context("MEDIUM")
    with holdings.connection() as conn:
        set_analysis_horizon(conn, revision_id, pending, created_at=T0)

    with pytest.raises(HoldingsManagementError) as caught:
        HoldingManagementService(
            holdings,
            clock=lambda: T1,
        ).apply_analysis_plan(
            position_id=position_id,
            analysis_revision_id=revision_id,
            applied_at=T1,
        )
    assert caught.value.code == "HOLD_PLAN_HORIZON_NOT_ACTIVE"

    with holdings.connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_management_plan"
        ).fetchone()[0] == 0


def test_legacy_plan_keeps_unspecified_horizon(tmp_path: Path) -> None:
    holdings, position_id, revision_id = _holdings_fixture(tmp_path / "holdings.db")
    simulation = tmp_path / "simulation.db"
    _simulation_fixture(simulation)
    migrate_horizon_context(
        holdings_db=holdings.db_path,
        simulation_db=simulation,
    )

    plan = HoldingManagementService(
        holdings,
        clock=lambda: T1,
    ).apply_analysis_plan(
        position_id=position_id,
        analysis_revision_id=revision_id,
        applied_at=T1,
    )
    with holdings.connection() as conn:
        context = get_plan_horizon(conn, plan.id)
    assert context.intent == "LEGACY_UNSPECIFIED"


def test_validation_horizon_is_stored_and_blocks_replay_policy_use(tmp_path: Path) -> None:
    holdings, _, _ = _holdings_fixture(tmp_path / "holdings.db")
    validation, execution = _simulation_fixture(tmp_path / "simulation.db")
    migrate_horizon_context(
        holdings_db=holdings.db_path,
        simulation_db=validation.db_path,
    )

    pending = _draft(
        validation,
        "중기 정책 대기",
        horizon=resolve_horizon_context("MEDIUM"),
    )
    with validation.connect() as conn:
        context = get_validation_horizon(conn, pending.id)
    assert context.intent == "MEDIUM"
    assert context.support_status == "EVALUATION_PENDING"

    with validation.connect() as conn:
        conn.execute(
            "UPDATE historical_validation_run SET status='COMPLETED' WHERE id=?",
            (pending.id,),
        )
    with pytest.raises(ExecutionCatalogError) as caught:
        execution.create_run(
            validation_id=pending.id,
            market_data_cutoff_date="2026-09-27",
            production_exit_policy_token="TEST-POLICY",
        )
    assert caught.value.code == "VAL2_HORIZON_NOT_ACTIVE"


def test_legacy_validation_execution_stays_legacy(tmp_path: Path) -> None:
    holdings, _, _ = _holdings_fixture(tmp_path / "holdings.db")
    validation, execution = _simulation_fixture(tmp_path / "simulation.db")
    migrate_horizon_context(
        holdings_db=holdings.db_path,
        simulation_db=validation.db_path,
    )

    legacy = _draft(validation, "기존 호환 검증")
    with validation.connect() as conn:
        conn.execute(
            "UPDATE historical_validation_run SET status='COMPLETED' WHERE id=?",
            (legacy.id,),
        )

    run = execution.create_run(
        validation_id=legacy.id,
        market_data_cutoff_date="2026-09-27",
        production_exit_policy_token="TEST-POLICY",
    )
    with execution.connect() as conn:
        context = get_execution_horizon(conn, run.id)
    assert context.intent == "LEGACY_UNSPECIFIED"


def test_horizon_context_survives_runtime_backup_restore(tmp_path: Path) -> None:
    holdings, _, revision_id = _holdings_fixture(tmp_path / "holdings.db")
    validation, _ = _simulation_fixture(tmp_path / "simulation.db")
    migrate_horizon_context(
        holdings_db=holdings.db_path,
        simulation_db=validation.db_path,
    )

    with holdings.connection() as conn:
        set_analysis_horizon(
            conn,
            revision_id,
            resolve_horizon_context("LONG"),
            created_at=T0,
        )
    draft = _draft(
        validation,
        "장기 정책 대기",
        horizon=resolve_horizon_context("LONG"),
    )

    backup = create_backup(
        destination=tmp_path / "backup",
        holdings_db=holdings.db_path,
        simulation_db=validation.db_path,
        include_tracking=False,
    )
    restored_holdings = tmp_path / "restored-holdings.db"
    restored_simulation = tmp_path / "restored-simulation.db"
    restore_backup(
        backup,
        restore_simulation=True,
        target_holdings=restored_holdings,
        target_simulation=restored_simulation,
    )

    with sqlite3.connect(restored_holdings) as conn:
        assert get_analysis_horizon(conn, revision_id).intent == "LONG"
    with sqlite3.connect(restored_simulation) as conn:
        assert get_validation_horizon(conn, draft.id).intent == "LONG"
