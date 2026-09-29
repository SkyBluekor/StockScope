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

from tools.data.common import DataToolError, simulation_db_path, sqlite_readonly


SELECTION_PIN_SCHEMA_VERSION = "VN_P1_S3_SELECTION_POLICY_PIN_V1"
SELECTION_PIN_META_TABLE = "selection_policy_pin_schema_meta"
VALIDATION_RUN_TABLE = "historical_validation_run"
EXECUTION_RUN_TABLE = "historical_execution_run"
SELECTION_PIN_COLUMN = "selection_policy_json"


def _table_names(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    with sqlite_readonly(path) as conn:
        return {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }


def _columns(path: Path, table: str) -> set[str]:
    if not path.is_file():
        return set()
    with sqlite_readonly(path) as conn:
        return {
            str(row[1])
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }


def inspect_selection_policy_pin_schema(path: Path) -> dict[str, object]:
    path = Path(path)
    names = _table_names(path)
    required = {VALIDATION_RUN_TABLE, EXECUTION_RUN_TABLE}
    missing_base = sorted(required - names)
    if missing_base:
        return {
            "status": "NOT_APPLICABLE",
            "missing_base_tables": missing_base,
            "meta_present": SELECTION_PIN_META_TABLE in names,
            "validation_column": False,
            "execution_column": False,
        }

    validation_column = (
        SELECTION_PIN_COLUMN in _columns(path, VALIDATION_RUN_TABLE)
    )
    execution_column = (
        SELECTION_PIN_COLUMN in _columns(path, EXECUTION_RUN_TABLE)
    )
    meta_present = SELECTION_PIN_META_TABLE in names
    version = None
    if meta_present:
        with sqlite_readonly(path) as conn:
            row = conn.execute(
                f"SELECT value FROM {SELECTION_PIN_META_TABLE} "
                "WHERE key='schema_version'"
            ).fetchone()
            version = None if row is None else str(row[0])

    if (
        meta_present
        and version == SELECTION_PIN_SCHEMA_VERSION
        and validation_column
        and execution_column
    ):
        status = "CURRENT"
    elif meta_present and version not in (None, SELECTION_PIN_SCHEMA_VERSION):
        status = "INCOMPATIBLE"
    elif (
        not meta_present
        and validation_column == execution_column
    ):
        # Both columns absent means an old DB; both present means a fresh DB
        # created by the new catalog before Local Sync. Both cases are safe,
        # additive MISSING states for the explicit migration.
        status = "MISSING"
    else:
        status = "PARTIAL"

    return {
        "status": status,
        "schema_version": version,
        "meta_present": meta_present,
        "validation_column": validation_column,
        "execution_column": execution_column,
        "missing_base_tables": [],
    }


def migrate_selection_policy_pin(path: Path) -> dict[str, object]:
    path = Path(path)
    state = inspect_selection_policy_pin_schema(path)
    if state["status"] == "NOT_APPLICABLE":
        raise DataToolError(
            "Selection Policy Pin migration에 필요한 Simulation base table이 없습니다: "
            + ", ".join(state["missing_base_tables"])
        )
    if state["status"] == "CURRENT":
        return {
            "schema_version": SELECTION_PIN_SCHEMA_VERSION,
            "status": "CURRENT",
            "backfilled_rows": 0,
        }

    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for table in (VALIDATION_RUN_TABLE, EXECUTION_RUN_TABLE):
            columns = {
                str(row[1])
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if SELECTION_PIN_COLUMN not in columns:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {SELECTION_PIN_COLUMN} TEXT"
                )

        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {SELECTION_PIN_META_TABLE}(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            f"SELECT value FROM {SELECTION_PIN_META_TABLE} "
            "WHERE key='schema_version'"
        ).fetchone()
        if row is None:
            conn.execute(
                f"INSERT INTO {SELECTION_PIN_META_TABLE}(key,value) "
                "VALUES('schema_version',?)",
                (SELECTION_PIN_SCHEMA_VERSION,),
            )
        elif str(row[0]) != SELECTION_PIN_SCHEMA_VERSION:
            raise DataToolError(
                "지원하지 않는 Selection Policy Pin schema입니다: "
                f"{row[0]}"
            )

        # Historical rows are deliberately not backfilled. Their policy identity
        # cannot be reconstructed reliably after the fact.
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    after = inspect_selection_policy_pin_schema(path)
    if after["status"] != "CURRENT":
        raise DataToolError(
            "Selection Policy Pin migration 후 schema가 CURRENT가 아닙니다: "
            f"{after}"
        )
    return {
        "schema_version": SELECTION_PIN_SCHEMA_VERSION,
        "status": "MIGRATED",
        "backfilled_rows": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "VN-P1-S3 Historical Validation/Execution Selection Policy pin "
            "schema를 명시적으로 적용합니다."
        )
    )
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = Path(args.simulation_db or simulation_db_path())
    try:
        result = migrate_selection_policy_pin(path)
        print("VN-P1-S3 SELECTION POLICY PIN MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
