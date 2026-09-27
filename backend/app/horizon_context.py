from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.horizon import HorizonContext, resolve_horizon_context

HORIZON_META_TABLE = "horizon_context_meta"
ANALYSIS_HORIZON_TABLE = "analysis_horizon_context"
PLAN_HORIZON_TABLE = "management_plan_horizon_context"
VALIDATION_HORIZON_TABLE = "validation_horizon_context"
EXECUTION_HORIZON_TABLE = "execution_horizon_context"
HORIZON_SCHEMA_VERSION = "VN_P1_S2_HORIZON_STORAGE_V1"


class HorizonStorageError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def horizon_storage_ready(conn: sqlite3.Connection, *tables: str) -> bool:
    if not _table_exists(conn, HORIZON_META_TABLE):
        return False
    row = conn.execute(
        f"SELECT value FROM {HORIZON_META_TABLE} WHERE key='schema_version' LIMIT 1"
    ).fetchone()
    if row is None or str(row[0]) != HORIZON_SCHEMA_VERSION:
        return False
    return all(_table_exists(conn, table) for table in tables)


def _read_context(
    conn: sqlite3.Connection,
    *,
    table: str,
    key_column: str,
    key: str,
) -> HorizonContext:
    if not horizon_storage_ready(conn, table):
        return resolve_horizon_context(None)
    row = conn.execute(
        f"""
        SELECT intent,policy_version,support_status
        FROM {table}
        WHERE {key_column}=?
        LIMIT 1
        """,
        (key,),
    ).fetchone()
    if row is None:
        return resolve_horizon_context(None)
    stored = HorizonContext(
        intent=str(row[0]),
        policy_version=str(row[1]),
        support_status=str(row[2]),
        reason_code=None,
    )
    current = resolve_horizon_context(
        stored.intent,
        policy_version=stored.policy_version,
    )
    if current.support_status != stored.support_status:
        return HorizonContext(
            intent=stored.intent,
            policy_version=stored.policy_version,
            support_status=current.support_status,
            reason_code="HORIZON_SUPPORT_STATUS_CHANGED",
        )
    return HorizonContext(
        intent=stored.intent,
        policy_version=stored.policy_version,
        support_status=stored.support_status,
        reason_code=current.reason_code,
    )


def _require_table(conn: sqlite3.Connection, table: str) -> None:
    if not horizon_storage_ready(conn, table):
        raise HorizonStorageError(
            "HORIZON_MIGRATION_REQUIRED",
            "VN-P1-S2 Horizon migration을 먼저 실행해야 합니다.",
        )


def set_analysis_horizon(
    conn: sqlite3.Connection,
    revision_id: str,
    context: HorizonContext,
    *,
    created_at: str | None = None,
) -> None:
    if context.is_legacy:
        return
    _require_table(conn, ANALYSIS_HORIZON_TABLE)
    conn.execute(
        f"""
        INSERT INTO {ANALYSIS_HORIZON_TABLE}(
            revision_id,intent,policy_version,support_status,created_at
        ) VALUES(?,?,?,?,?)
        ON CONFLICT(revision_id) DO UPDATE SET
            intent=excluded.intent,
            policy_version=excluded.policy_version,
            support_status=excluded.support_status
        """,
        (
            revision_id,
            context.intent,
            context.policy_version,
            context.support_status,
            created_at or _now(),
        ),
    )


def get_analysis_horizon(conn: sqlite3.Connection, revision_id: str) -> HorizonContext:
    return _read_context(
        conn,
        table=ANALYSIS_HORIZON_TABLE,
        key_column="revision_id",
        key=revision_id,
    )


def copy_analysis_horizon_to_plan(
    conn: sqlite3.Connection,
    *,
    revision_id: str,
    plan_id: str,
    created_at: str | None = None,
) -> HorizonContext:
    context = get_analysis_horizon(conn, revision_id)
    if context.is_legacy:
        return context
    _require_table(conn, PLAN_HORIZON_TABLE)
    conn.execute(
        f"""
        INSERT INTO {PLAN_HORIZON_TABLE}(
            plan_id,source_revision_id,intent,policy_version,support_status,created_at
        ) VALUES(?,?,?,?,?,?)
        """,
        (
            plan_id,
            revision_id,
            context.intent,
            context.policy_version,
            context.support_status,
            created_at or _now(),
        ),
    )
    return context


def get_plan_horizon(conn: sqlite3.Connection, plan_id: str) -> HorizonContext:
    return _read_context(
        conn,
        table=PLAN_HORIZON_TABLE,
        key_column="plan_id",
        key=plan_id,
    )


def set_validation_horizon(
    conn: sqlite3.Connection,
    validation_id: str,
    context: HorizonContext,
    *,
    created_at: str | None = None,
) -> None:
    if context.is_legacy:
        return
    _require_table(conn, VALIDATION_HORIZON_TABLE)
    conn.execute(
        f"""
        INSERT INTO {VALIDATION_HORIZON_TABLE}(
            validation_id,intent,policy_version,support_status,created_at
        ) VALUES(?,?,?,?,?)
        ON CONFLICT(validation_id) DO UPDATE SET
            intent=excluded.intent,
            policy_version=excluded.policy_version,
            support_status=excluded.support_status
        """,
        (
            validation_id,
            context.intent,
            context.policy_version,
            context.support_status,
            created_at or _now(),
        ),
    )


def get_validation_horizon(
    conn: sqlite3.Connection,
    validation_id: str,
) -> HorizonContext:
    return _read_context(
        conn,
        table=VALIDATION_HORIZON_TABLE,
        key_column="validation_id",
        key=validation_id,
    )


def copy_validation_horizon_to_execution(
    conn: sqlite3.Connection,
    *,
    validation_id: str,
    execution_run_id: str,
    created_at: str | None = None,
) -> HorizonContext:
    context = get_validation_horizon(conn, validation_id)
    if context.is_legacy:
        return context
    _require_table(conn, EXECUTION_HORIZON_TABLE)
    conn.execute(
        f"""
        INSERT INTO {EXECUTION_HORIZON_TABLE}(
            execution_run_id,validation_id,intent,policy_version,support_status,created_at
        ) VALUES(?,?,?,?,?,?)
        """,
        (
            execution_run_id,
            validation_id,
            context.intent,
            context.policy_version,
            context.support_status,
            created_at or _now(),
        ),
    )
    return context


def get_execution_horizon(
    conn: sqlite3.Connection,
    execution_run_id: str,
) -> HorizonContext:
    return _read_context(
        conn,
        table=EXECUTION_HORIZON_TABLE,
        key_column="execution_run_id",
        key=execution_run_id,
    )
