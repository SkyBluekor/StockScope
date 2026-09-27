from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.simulation.strategy_governance import (
    STRATEGY_BOOTSTRAP_DEFINITION_VERSION,
    STRATEGY_BOOTSTRAP_SOURCE,
    STRATEGY_FINGERPRINT_CONTRACT_VERSION,
    STRATEGY_GOVERNANCE_SCHEMA_VERSION,
    current_strategy_definitions,
    current_strategy_set_fingerprint,
)
from app.strategy.models import StrategyName
from tools.data.common import DataToolError
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.data.migrate_strategy_governance_vnp5s1 import (
    migrate_strategy_governance_store,
)


def _simulation_db(tmp_path: Path) -> Path:
    path = tmp_path / "simulation.db"
    sqlite3.connect(path).close()
    migrate_prospective_store(path)
    return path


def test_current_strategy_registry_definition_is_exactly_existing_ten():
    first = current_strategy_definitions()
    second = current_strategy_definitions()

    assert len(first) == 10
    assert first == second
    assert len({item.strategy_key for item in first}) == 10
    assert StrategyName.NO_TRADE.value not in {
        item.strategy_key for item in first
    }
    assert all(item.operational_status == "OPERATING" for item in first)
    assert all(item.validation_status == "UNVERIFIED" for item in first)
    assert all(item.source == STRATEGY_BOOTSTRAP_SOURCE for item in first)
    assert all(
        item.definition_version == STRATEGY_BOOTSTRAP_DEFINITION_VERSION
        for item in first
    )
    assert all(
        item.fingerprint_contract_version
        == STRATEGY_FINGERPRINT_CONTRACT_VERSION
        for item in first
    )
    assert all(len(item.definition_hash) == 64 for item in first)
    assert len(current_strategy_set_fingerprint()) == 64


def test_strategy_governance_migration_requires_vnp2s2(tmp_path: Path):
    path = tmp_path / "simulation.db"
    sqlite3.connect(path).close()

    with pytest.raises(DataToolError):
        migrate_strategy_governance_store(path)

    with sqlite3.connect(path) as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "strategy_governance_schema_meta" not in tables
    assert "strategy_registry_version" not in tables


def test_strategy_governance_bootstrap_is_idempotent_and_unverified(
    tmp_path: Path,
):
    path = _simulation_db(tmp_path)

    first = migrate_strategy_governance_store(path)
    second = migrate_strategy_governance_store(path)

    assert first["schema_version"] == STRATEGY_GOVERNANCE_SCHEMA_VERSION
    assert (
        first["fingerprint_contract_version"]
        == STRATEGY_FINGERPRINT_CONTRACT_VERSION
    )
    assert first["strategy_count"] == 10
    assert first["inserted_strategy_count"] == 10
    assert first["verified_strategy_count"] == 0
    assert first["operational_status_counts"] == {"OPERATING": 10}
    assert first["no_trade_registered"] is False
    assert first["performance_validation_backfill_performed"] is False
    assert first["production_selection_policy_changed"] is False

    assert second["inserted_strategy_count"] == 0
    assert second["verified_strategy_count"] == 10
    assert second["strategy_set_fingerprint"] == first["strategy_set_fingerprint"]

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM strategy_registry_version
            ORDER BY strategy_key
            """
        ).fetchall()
        meta = {
            str(row["key"]): str(row["value"])
            for row in conn.execute(
                "SELECT key,value FROM strategy_governance_schema_meta"
            ).fetchall()
        }

    assert len(rows) == 10
    assert all(row["operational_status"] == "OPERATING" for row in rows)
    assert all(row["validation_status"] == "UNVERIFIED" for row in rows)
    assert all(row["source"] == STRATEGY_BOOTSTRAP_SOURCE for row in rows)
    assert all(row["strategy_key"] != StrategyName.NO_TRADE.value for row in rows)
    assert meta["schema_version"] == STRATEGY_GOVERNANCE_SCHEMA_VERSION
    assert (
        meta["fingerprint_contract_version"]
        == STRATEGY_FINGERPRINT_CONTRACT_VERSION
    )
    assert (
        meta["bootstrap_strategy_set_fingerprint"]
        == current_strategy_set_fingerprint()
    )


def test_migration_does_not_silently_replace_drifted_bootstrap_definition(
    tmp_path: Path,
):
    path = _simulation_db(tmp_path)
    migrate_strategy_governance_store(path)

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT strategy_version_id
            FROM strategy_registry_version
            WHERE strategy_key='trend_following'
            """
        ).fetchone()
        assert row is not None
        conn.execute(
            """
            UPDATE strategy_registry_version
            SET definition_hash=?
            WHERE strategy_version_id=?
            """,
            ("0" * 64, str(row[0])),
        )
        conn.commit()

    with pytest.raises(DataToolError):
        migrate_strategy_governance_store(path)

    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            """
            SELECT strategy_key,definition_hash
            FROM strategy_registry_version
            WHERE strategy_key='trend_following'
            """
        ).fetchall()

    assert rows == [("trend_following", "0" * 64)]


def test_registry_enforces_single_operating_version_per_strategy(tmp_path: Path):
    path = _simulation_db(tmp_path)
    migrate_strategy_governance_store(path)

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT * FROM strategy_registry_version
            WHERE strategy_key='pullback'
            """
        ).fetchone()
        assert row is not None
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO strategy_registry_version(
                    strategy_version_id,strategy_key,definition_version,
                    definition_hash,fingerprint_contract_version,
                    implementation_key,operational_status,
                    validation_status,source,definition_json,
                    created_at,retired_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "test-second-operating-pullback",
                    "pullback",
                    "TEST_V2",
                    "f" * 64,
                    STRATEGY_FINGERPRINT_CONTRACT_VERSION,
                    "StrategyEngine._pullback",
                    "OPERATING",
                    "UNVERIFIED",
                    "TEST",
                    "{}",
                    "2026-09-28T00:00:00+00:00",
                    None,
                ),
            )
