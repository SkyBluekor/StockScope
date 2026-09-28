from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.simulation.execution_catalog import ExecutionCatalogError, HistoricalExecutionCatalog
from app.simulation.validation_catalog import HistoricalValidationCatalog, ValidationCatalogError
from app.strategy.production_selection_policy import SelectionPolicyPin
from app.simulation.selection_policy_pin import (
    deserialize_selection_policy_pin,
    serialize_selection_policy_pin,
)
from tools.data.migrate_policy_identity_next1 import (
    META_TABLE,
    PIN_COLUMNS,
    SCHEMA_VERSION,
    migrate_policy_identity,
)


def _pin(seed: str = "e") -> SelectionPolicyPin:
    return SelectionPolicyPin(
        policy_id="TEST-POLICY",
        policy_hash=seed * 64,
        policy_contract_version="VN_P5_S1_SELECTION_POLICY_V1",
        policy_source="TEST",
        fallback_used=False,
        fallback_reason=None,
        operating_strategies=((None, "pullback", None),),
        scanner_baseline_id="0.21.3.8",
        production_fingerprint=None,
        production_policy_fingerprint=None,
    )


def _draft(catalog: HistoricalValidationCatalog, *, pin: SelectionPolicyPin | None = None):
    return catalog.create_draft(
        name="NEXT-1 policy identity",
        market_scope="KOSPI",
        requested_period_type="custom",
        requested_start_month="2026-01",
        requested_end_month="2026-01",
        resolved_start_date="2026-01-02",
        resolved_end_date="2026-01-02",
        trading_day_count=1,
        selection_policy_pin=serialize_selection_policy_pin(pin) if pin else None,
    )


def test_selection_policy_pin_round_trip_preserves_identity():
    original = _pin()
    restored = deserialize_selection_policy_pin(serialize_selection_policy_pin(original))

    assert restored == original
    assert restored.strategy_reference("pullback") == {
        "strategy_version_id": None,
        "strategy_key": "pullback",
        "definition_hash": None,
    }


def test_next1_migration_is_additive_and_does_not_backfill_legacy_runs(tmp_path: Path):
    db = tmp_path / "simulation.db"
    validation = HistoricalValidationCatalog(db)
    validation.initialize()
    draft = _draft(validation)
    with validation.connect() as conn:
        conn.execute(
            "UPDATE historical_validation_run SET status='COMPLETED' WHERE id=?",
            (draft.id,),
        )

    execution = HistoricalExecutionCatalog(db)
    execution.initialize()

    result = migrate_policy_identity(db)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["historical_policy_backfill_performed"] is False
    assert result["completed_run_rewrite_performed"] is False
    with sqlite3.connect(db) as conn:
        validation_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(historical_validation_run)")
        }
        execution_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(historical_execution_run)")
        }
        assert set(PIN_COLUMNS).issubset(validation_columns)
        assert set(PIN_COLUMNS).issubset(execution_columns)
        row = conn.execute(
            "SELECT selection_policy_id,selection_policy_pin_json "
            "FROM historical_validation_run WHERE id=?",
            (draft.id,),
        ).fetchone()
        assert row == (None, None)
        assert conn.execute(
            f"SELECT value FROM {META_TABLE} WHERE key='schema_version'"
        ).fetchone()[0] == SCHEMA_VERSION


def test_completed_legacy_validation_cannot_be_policy_backfilled(tmp_path: Path):
    db = tmp_path / "simulation.db"
    catalog = HistoricalValidationCatalog(db)
    catalog.initialize()
    draft = _draft(catalog)
    with catalog.connect() as conn:
        conn.execute(
            "UPDATE historical_validation_run SET status='COMPLETED' WHERE id=?",
            (draft.id,),
        )

    with pytest.raises(ValidationCatalogError) as caught:
        catalog.ensure_selection_policy_pin(draft.id, serialize_selection_policy_pin(_pin()))

    assert caught.value.code == "VAL_SELECTION_POLICY_LEGACY_UNAVAILABLE"
    assert catalog.get(draft.id).selection_policy_pin is None


def test_execution_rejects_completed_legacy_validation_without_policy_identity(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source = HistoricalValidationCatalog(db)
    source.initialize()
    draft = _draft(source)
    with source.connect() as conn:
        conn.execute(
            "UPDATE historical_validation_run SET status='COMPLETED' WHERE id=?",
            (draft.id,),
        )

    execution = HistoricalExecutionCatalog(db)
    execution.initialize()
    with pytest.raises(ExecutionCatalogError) as caught:
        execution.create_run(
            validation_id=draft.id,
            market_data_cutoff_date="2026-02-03",
            production_exit_policy_token="TOKEN",
        )

    assert caught.value.code == "VAL2_SELECTION_POLICY_IDENTITY_REQUIRED"
