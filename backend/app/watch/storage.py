from __future__ import annotations

import sqlite3

from .policy import WATCH_POLICY_CONTRACT_VERSION


WATCH_SCHEMA_VERSION = "VN_P4_S1_WATCH_V1"

WATCH_TABLES = frozenset(
    {
        "holding_watch_schema_meta",
        "holding_watch_setting",
        "holding_watch_rule",
        "holding_watch_episode",
        "holding_watch_coverage_gap",
        "holding_watch_notification_outbox",
    }
)


class WatchStorageError(RuntimeError):
    pass


def watch_schema_available(conn: sqlite3.Connection) -> bool:
    names = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if not WATCH_TABLES.issubset(names):
        return False
    schema_row = conn.execute(
        """
        SELECT value FROM holding_watch_schema_meta
        WHERE key='schema_version'
        """
    ).fetchone()
    contract_row = conn.execute(
        """
        SELECT value FROM holding_watch_schema_meta
        WHERE key='policy_contract_version'
        """
    ).fetchone()
    return (
        schema_row is not None
        and str(schema_row[0]) == WATCH_SCHEMA_VERSION
        and contract_row is not None
        and str(contract_row[0]) == WATCH_POLICY_CONTRACT_VERSION
    )


def require_watch_schema(conn: sqlite3.Connection) -> None:
    if not watch_schema_available(conn):
        raise WatchStorageError(
            "VN-P4-S1 Watch migration이 필요하거나 schema version이 호환되지 않습니다."
        )
