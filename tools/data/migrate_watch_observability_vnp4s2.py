from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.watch.storage import WATCH_TABLES
from tools.data.common import DataToolError, holdings_db_path, sqlite_readonly


WATCH_OBSERVABILITY_SCHEMA_VERSION = "VN_P4_S2_WATCH_OBSERVABILITY_V1"
WATCH_OBSERVABILITY_META_TABLE = "holding_watch_observability_schema_meta"
WATCH_RUNTIME_TABLE = "holding_watch_runtime_session"
WATCH_OBSERVABILITY_TABLES = frozenset(
    {WATCH_OBSERVABILITY_META_TABLE, WATCH_RUNTIME_TABLE}
)
REQUIRED_BASE_TABLES = set(WATCH_TABLES)


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def inspect_watch_observability(path: Path) -> dict[str, object]:
    path = Path(path)
    if not path.is_file():
        return {
            "status": "MISSING",
            "missing_base_tables": sorted(REQUIRED_BASE_TABLES),
            "schema_version": None,
        }
    with sqlite_readonly(path) as conn:
        names = _table_names(conn)
        present = WATCH_OBSERVABILITY_TABLES & names
        if not present:
            return {
                "status": "MISSING",
                "missing_base_tables": sorted(REQUIRED_BASE_TABLES - names),
                "schema_version": None,
            }
        if present != WATCH_OBSERVABILITY_TABLES:
            return {
                "status": "PARTIAL",
                "missing_base_tables": sorted(REQUIRED_BASE_TABLES - names),
                "schema_version": None,
            }
        row = conn.execute(
            f"SELECT value FROM {WATCH_OBSERVABILITY_META_TABLE} "
            "WHERE key='schema_version'"
        ).fetchone()
        version = None if row is None else str(row[0])
        return {
            "status": (
                "CURRENT"
                if version == WATCH_OBSERVABILITY_SCHEMA_VERSION
                else "INCOMPATIBLE"
            ),
            "missing_base_tables": sorted(REQUIRED_BASE_TABLES - names),
            "schema_version": version,
        }


def migrate_watch_observability(path: Path) -> dict[str, object]:
    path = Path(path)
    if not path.is_file():
        raise DataToolError(f"Holdings DB를 찾을 수 없습니다: {path}")

    with sqlite_readonly(path) as conn:
        names = _table_names(conn)
        missing_base = sorted(REQUIRED_BASE_TABLES - names)
        if missing_base:
            raise DataToolError(
                "VN-P4-S2 선행 VN-P4-S1 Watch 테이블이 없습니다: "
                + ", ".join(missing_base)
            )

    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {WATCH_OBSERVABILITY_META_TABLE}(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            f"SELECT value FROM {WATCH_OBSERVABILITY_META_TABLE} "
            "WHERE key='schema_version'"
        ).fetchone()
        if row is None:
            conn.execute(
                f"INSERT INTO {WATCH_OBSERVABILITY_META_TABLE}(key,value) "
                "VALUES('schema_version',?)",
                (WATCH_OBSERVABILITY_SCHEMA_VERSION,),
            )
        elif str(row[0]) != WATCH_OBSERVABILITY_SCHEMA_VERSION:
            raise DataToolError(
                "지원하지 않는 Watch observability schema version입니다: "
                f"{row[0]}"
            )

        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {WATCH_RUNTIME_TABLE}(
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN (
                    'RUNNING','STOPPED','INTERRUPTED'
                )),
                started_at TEXT NOT NULL,
                last_heartbeat_at TEXT NOT NULL,
                stopped_at TEXT,
                last_reconcile_at TEXT,
                last_reconcile_status TEXT,
                last_error_code TEXT,
                last_error_at TEXT,
                transport_state TEXT,
                market_session_phase TEXT,
                previous_session_id TEXT,
                previous_last_heartbeat_at TEXT,
                continuity_state TEXT NOT NULL CHECK(continuity_state IN (
                    'NEW','CONTINUOUS','UNMONITORED'
                )),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS ix_watch_runtime_started
            ON {WATCH_RUNTIME_TABLE}(started_at DESC)
            """
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    state = inspect_watch_observability(path)
    if state["status"] != "CURRENT":
        raise DataToolError(
            "Watch observability migration 후 schema가 CURRENT가 아닙니다: "
            f"{state}"
        )
    return {
        "schema_version": WATCH_OBSERVABILITY_SCHEMA_VERSION,
        "status": "MIGRATED",
        "backfilled_rows": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="VN-P4-S2 Watch runtime observability schema를 적용합니다."
    )
    parser.add_argument("--holdings-db", type=Path)
    args = parser.parse_args()
    path = Path(args.holdings_db or holdings_db_path())
    try:
        result = migrate_watch_observability(path)
        print("VN-P4-S2 WATCH OBSERVABILITY MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
