from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.holdings.catalog import HoldingsCatalog

WATCH_OBSERVABILITY_SCHEMA_VERSION = "VN_P4_S2_WATCH_OBSERVABILITY_V1"
WATCH_OBSERVABILITY_META_TABLE = "holding_watch_observability_schema_meta"
WATCH_RUNTIME_TABLE = "holding_watch_runtime_session"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def watch_observability_schema_available(conn: sqlite3.Connection) -> bool:
    names = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if {
        WATCH_OBSERVABILITY_META_TABLE,
        WATCH_RUNTIME_TABLE,
    } - names:
        return False
    row = conn.execute(
        f"SELECT value FROM {WATCH_OBSERVABILITY_META_TABLE} "
        "WHERE key='schema_version'"
    ).fetchone()
    return row is not None and str(row[0]) == WATCH_OBSERVABILITY_SCHEMA_VERSION


class WatchRuntimeObserver:
    def __init__(
        self,
        catalog: HoldingsCatalog,
        *,
        clock=_now,
    ) -> None:
        self.catalog = catalog
        self.clock = clock
        self.session_id: str | None = None

    def start(
        self,
        *,
        transport_state: str | None = None,
        market_session_phase: str | None = None,
    ) -> str | None:
        if not self.catalog.db_path.is_file():
            return None
        now = _dt(self.clock())
        with self.catalog.connection() as conn:
            if not watch_observability_schema_available(conn):
                return None
            previous = conn.execute(
                f"""
                SELECT *
                FROM {WATCH_RUNTIME_TABLE}
                ORDER BY started_at DESC,rowid DESC
                LIMIT 1
                """
            ).fetchone()
            previous_id = None
            previous_heartbeat = None
            continuity_state = "NEW"
            if previous is not None:
                previous_id = str(previous["id"])
                previous_heartbeat = str(previous["last_heartbeat_at"])
                if str(previous["status"]) == "RUNNING":
                    conn.execute(
                        f"""
                        UPDATE {WATCH_RUNTIME_TABLE}
                        SET status='INTERRUPTED',updated_at=?
                        WHERE id=?
                        """,
                        (now, previous_id),
                    )
                # Any interval between two runtime sessions is not observed by
                # StockScope. Do not call it a market-data outage, but do not
                # claim continuous monitoring either.
                continuity_state = "UNMONITORED"

            session_id = str(uuid4())
            conn.execute(
                f"""
                INSERT INTO {WATCH_RUNTIME_TABLE}(
                    id,status,started_at,last_heartbeat_at,stopped_at,
                    last_reconcile_at,last_reconcile_status,
                    last_error_code,last_error_at,
                    transport_state,market_session_phase,
                    previous_session_id,previous_last_heartbeat_at,
                    continuity_state,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    session_id,
                    "RUNNING",
                    now,
                    now,
                    None,
                    None,
                    None,
                    None,
                    None,
                    transport_state,
                    market_session_phase,
                    previous_id,
                    previous_heartbeat,
                    continuity_state,
                    now,
                    now,
                ),
            )
        self.session_id = session_id
        return session_id

    def record_event(
        self,
        event: str,
        *,
        error_code: str | None = None,
        transport_state: str | None = None,
        market_session_phase: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if self.session_id is None:
            return
        now = _dt(self.clock())
        reconcile_status = "OK" if event == "RECONCILE_OK" else event
        with self.catalog.connection() as conn:
            if not watch_observability_schema_available(conn):
                return
            conn.execute(
                f"""
                UPDATE {WATCH_RUNTIME_TABLE}
                SET last_heartbeat_at=?,
                    last_reconcile_at=?,
                    last_reconcile_status=?,
                    last_error_code=CASE
                        WHEN ? IS NULL THEN last_error_code
                        ELSE ?
                    END,
                    last_error_at=CASE
                        WHEN ? IS NULL THEN last_error_at
                        ELSE ?
                    END,
                    transport_state=COALESCE(?,transport_state),
                    market_session_phase=COALESCE(?,market_session_phase),
                    updated_at=?
                WHERE id=? AND status='RUNNING'
                """,
                (
                    now,
                    now,
                    reconcile_status,
                    error_code,
                    error_code,
                    error_code,
                    now,
                    transport_state,
                    market_session_phase,
                    now,
                    self.session_id,
                ),
            )
            if detail:
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {WATCH_OBSERVABILITY_META_TABLE}(key,value)
                    VALUES('last_runtime_detail_json',?)
                    """,
                    (
                        json.dumps(
                            detail,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )

    def stop(
        self,
        *,
        transport_state: str | None = None,
        market_session_phase: str | None = None,
    ) -> None:
        if self.session_id is None:
            return
        now = _dt(self.clock())
        with self.catalog.connection() as conn:
            if not watch_observability_schema_available(conn):
                self.session_id = None
                return
            conn.execute(
                f"""
                UPDATE {WATCH_RUNTIME_TABLE}
                SET status='STOPPED',
                    stopped_at=COALESCE(stopped_at,?),
                    last_heartbeat_at=?,
                    transport_state=COALESCE(?,transport_state),
                    market_session_phase=COALESCE(?,market_session_phase),
                    updated_at=?
                WHERE id=? AND status='RUNNING'
                """,
                (
                    now,
                    now,
                    transport_state,
                    market_session_phase,
                    now,
                    self.session_id,
                ),
            )
        self.session_id = None


def read_watch_runtime_health(catalog: HoldingsCatalog) -> dict[str, Any]:
    if not catalog.db_path.is_file():
        return {
            "available": False,
            "migration_required": True,
            "session": None,
        }
    with catalog.connection() as conn:
        if not watch_observability_schema_available(conn):
            return {
                "available": False,
                "migration_required": True,
                "session": None,
            }
        row = conn.execute(
            f"""
            SELECT *
            FROM {WATCH_RUNTIME_TABLE}
            ORDER BY started_at DESC,rowid DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return {
            "available": True,
            "migration_required": False,
            "session": None,
        }

    return {
        "available": True,
        "migration_required": False,
        "session": {
            "runtime_session_id": str(row["id"]),
            "status": str(row["status"]),
            "started_at": str(row["started_at"]),
            "last_heartbeat_at": str(row["last_heartbeat_at"]),
            "stopped_at": row["stopped_at"],
            "last_reconcile_at": row["last_reconcile_at"],
            "last_reconcile_status": row["last_reconcile_status"],
            "last_error_code": row["last_error_code"],
            "last_error_at": row["last_error_at"],
            "transport_state": row["transport_state"],
            "market_session_phase": row["market_session_phase"],
            "previous_session_id": row["previous_session_id"],
            "previous_last_heartbeat_at": row["previous_last_heartbeat_at"],
            "continuity_state": str(row["continuity_state"]),
        },
    }
