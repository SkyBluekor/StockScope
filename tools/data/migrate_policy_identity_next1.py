from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from tools.data.common import DataToolError, simulation_db_path


SCHEMA_VERSION = "NEXT1_POLICY_IDENTITY_V1"
META_TABLE = "next1_policy_identity_meta"
VALIDATION_TABLE = "historical_validation_run"
EXECUTION_TABLE = "historical_execution_run"

PIN_COLUMNS: dict[str, str] = {
    "selection_policy_id": "TEXT",
    "selection_policy_hash": "TEXT",
    "selection_policy_contract_version": "TEXT",
    "selection_policy_pin_json": "TEXT",
}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def inspect_policy_identity(path: Path | None = None) -> dict[str, Any]:
    db = Path(path or simulation_db_path())
    if not db.is_file():
        return {"applicable": False, "current": True, "reason": "SIMULATION_DB_MISSING"}

    conn = sqlite3.connect(db)
    try:
        tables = _tables(conn)
        if VALIDATION_TABLE not in tables:
            return {
                "applicable": False,
                "current": True,
                "reason": "VALIDATION_DOMAIN_NOT_INITIALIZED",
            }

        validation_missing = sorted(
            set(PIN_COLUMNS) - _columns(conn, VALIDATION_TABLE)
        )
        execution_missing: list[str] = []
        if EXECUTION_TABLE in tables:
            execution_missing = sorted(
                set(PIN_COLUMNS) - _columns(conn, EXECUTION_TABLE)
            )

        meta_current = False
        if META_TABLE in tables:
            row = conn.execute(
                f"SELECT value FROM {META_TABLE} WHERE key='schema_version'"
            ).fetchone()
            meta_current = row is not None and str(row[0]) == SCHEMA_VERSION

        current = not validation_missing and not execution_missing and meta_current
        return {
            "applicable": True,
            "current": current,
            "validation_missing_columns": validation_missing,
            "execution_missing_columns": execution_missing,
            "meta_current": meta_current,
        }
    finally:
        conn.close()


def migrate_policy_identity(path: Path | None = None) -> dict[str, Any]:
    db = Path(path or simulation_db_path())
    if not db.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "SKIPPED_NOT_APPLICABLE",
            "reason": "SIMULATION_DB_MISSING",
            "historical_policy_backfill_performed": False,
            "external_network_requests": 0,
        }

    conn = sqlite3.connect(db)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        tables = _tables(conn)
        if VALIDATION_TABLE not in tables:
            conn.rollback()
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "SKIPPED_NOT_APPLICABLE",
                "reason": "VALIDATION_DOMAIN_NOT_INITIALIZED",
                "historical_policy_backfill_performed": False,
                "external_network_requests": 0,
            }

        for column, ddl in PIN_COLUMNS.items():
            if column not in _columns(conn, VALIDATION_TABLE):
                conn.execute(
                    f"ALTER TABLE {VALIDATION_TABLE} ADD COLUMN {column} {ddl}"
                )

        if EXECUTION_TABLE in tables:
            for column, ddl in PIN_COLUMNS.items():
                if column not in _columns(conn, EXECUTION_TABLE):
                    conn.execute(
                        f"ALTER TABLE {EXECUTION_TABLE} ADD COLUMN {column} {ddl}"
                    )

        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {META_TABLE}(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO {META_TABLE}(key,value)
            VALUES('schema_version',?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (SCHEMA_VERSION,),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise DataToolError(
            f"NEXT-1 Policy Identity migration 실패: {exc}"
        ) from exc
    finally:
        conn.close()

    state = inspect_policy_identity(db)
    if not state.get("current"):
        raise DataToolError(
            f"NEXT-1 Policy Identity migration 검증 실패: {state}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "CURRENT",
        "historical_policy_backfill_performed": False,
        "completed_run_rewrite_performed": False,
        "external_network_requests": 0,
    }


if __name__ == "__main__":
    print(migrate_policy_identity())
