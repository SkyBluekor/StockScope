from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.horizon_context import (
    ANALYSIS_HORIZON_TABLE,
    EXECUTION_HORIZON_TABLE,
    HORIZON_META_TABLE,
    HORIZON_SCHEMA_VERSION,
    PLAN_HORIZON_TABLE,
    VALIDATION_HORIZON_TABLE,
)
from tools.data.common import (
    DataToolError,
    holdings_db_path,
    simulation_db_path,
    sqlite_readonly,
)


def _existing_core_tables(path: Path, required: set[str]) -> None:
    if not path.is_file():
        raise DataToolError(f"SQLite DB를 찾을 수 없습니다: {path}")
    with sqlite_readonly(path) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    missing = sorted(required - names)
    if missing:
        raise DataToolError(
            f"{path.name}에 필요한 기존 table이 없습니다: {', '.join(missing)}"
        )


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {HORIZON_META_TABLE}(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    row = conn.execute(
        f"SELECT value FROM {HORIZON_META_TABLE} WHERE key='schema_version'"
    ).fetchone()
    if row is None:
        conn.execute(
            f"INSERT INTO {HORIZON_META_TABLE}(key,value) VALUES('schema_version',?)",
            (HORIZON_SCHEMA_VERSION,),
        )
    elif str(row[0]) != HORIZON_SCHEMA_VERSION:
        raise DataToolError(
            f"지원하지 않는 Horizon schema입니다: {row[0]}"
        )


def migrate_holdings_horizon(path: Path) -> dict[str, str]:
    path = Path(path)
    _existing_core_tables(
        path,
        {
            "stock_analysis_revision",
            "holding_management_plan",
        },
    )
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        _ensure_meta(conn)
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {ANALYSIS_HORIZON_TABLE}(
                revision_id TEXT PRIMARY KEY,
                intent TEXT NOT NULL CHECK(intent IN ('SHORT','MEDIUM','LONG')),
                policy_version TEXT NOT NULL,
                support_status TEXT NOT NULL
                    CHECK(support_status IN ('SUPPORTED','EVALUATION_PENDING','UNSUPPORTED')),
                created_at TEXT NOT NULL,
                FOREIGN KEY(revision_id)
                    REFERENCES stock_analysis_revision(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS {PLAN_HORIZON_TABLE}(
                plan_id TEXT PRIMARY KEY,
                source_revision_id TEXT NOT NULL,
                intent TEXT NOT NULL CHECK(intent IN ('SHORT','MEDIUM','LONG')),
                policy_version TEXT NOT NULL,
                support_status TEXT NOT NULL
                    CHECK(support_status IN ('SUPPORTED','EVALUATION_PENDING','UNSUPPORTED')),
                created_at TEXT NOT NULL,
                FOREIGN KEY(plan_id)
                    REFERENCES holding_management_plan(id) ON DELETE CASCADE,
                FOREIGN KEY(source_revision_id)
                    REFERENCES stock_analysis_revision(id) ON DELETE RESTRICT
            );
            """
        )
        conn.commit()
        return {"schema_version": HORIZON_SCHEMA_VERSION}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_simulation_horizon(path: Path) -> dict[str, str]:
    path = Path(path)
    _existing_core_tables(
        path,
        {
            "historical_validation_run",
            "historical_execution_run",
        },
    )
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        _ensure_meta(conn)
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {VALIDATION_HORIZON_TABLE}(
                validation_id TEXT PRIMARY KEY,
                intent TEXT NOT NULL CHECK(intent IN ('SHORT','MEDIUM','LONG')),
                policy_version TEXT NOT NULL,
                support_status TEXT NOT NULL
                    CHECK(support_status IN ('SUPPORTED','EVALUATION_PENDING','UNSUPPORTED')),
                created_at TEXT NOT NULL,
                FOREIGN KEY(validation_id)
                    REFERENCES historical_validation_run(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS {EXECUTION_HORIZON_TABLE}(
                execution_run_id TEXT PRIMARY KEY,
                validation_id TEXT NOT NULL,
                intent TEXT NOT NULL CHECK(intent IN ('SHORT','MEDIUM','LONG')),
                policy_version TEXT NOT NULL,
                support_status TEXT NOT NULL
                    CHECK(support_status IN ('SUPPORTED','EVALUATION_PENDING','UNSUPPORTED')),
                created_at TEXT NOT NULL,
                FOREIGN KEY(execution_run_id)
                    REFERENCES historical_execution_run(id) ON DELETE CASCADE,
                FOREIGN KEY(validation_id)
                    REFERENCES historical_validation_run(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
        return {"schema_version": HORIZON_SCHEMA_VERSION}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_horizon_context(
    *,
    holdings_db: Path | None = None,
    simulation_db: Path | None = None,
) -> dict[str, object]:
    holdings_path = Path(holdings_db or holdings_db_path())
    simulation_path = Path(simulation_db or simulation_db_path())

    holdings_result = migrate_holdings_horizon(holdings_path)
    if simulation_path.is_file():
        simulation_result: dict[str, str] = migrate_simulation_horizon(
            simulation_path
        )
    else:
        simulation_result = {"status": "SKIPPED_MISSING"}

    return {
        "holdings": holdings_result,
        "simulation": simulation_result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VN-P1-S2 Horizon context side-table migration을 명시적으로 실행합니다."
    )
    parser.add_argument("--holdings-db", type=Path)
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_horizon_context(
            holdings_db=args.holdings_db,
            simulation_db=args.simulation_db,
        )
        print("VN-P1-S2 HORIZON CONTEXT MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
