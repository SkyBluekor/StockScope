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

from app.feedback.models import FEEDBACK_SCHEMA_VERSION
from tools.data.common import DataToolError, simulation_db_path, sqlite_readonly


KNOWN_SOURCE_TABLES = {
    "historical_validation_run",
    "historical_execution_run",
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _inspect_source_schema(path: Path) -> dict[str, list[str]]:
    """Inspect optional evaluation sources without requiring them to exist.

    P2-S1 Feedback storage is allowed on a valid Simulation DB even when VAL.2
    (or VAL.1) has never been initialized locally. Missing sources are surfaced
    later by the read-only adapters instead of blocking schema migration.
    """
    if not path.is_file():
        raise DataToolError(f"Simulation DB를 찾을 수 없습니다: {path}")
    with sqlite_readonly(path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise DataToolError("Simulation DB integrity_check에 실패했습니다.")
        names = _table_names(conn)
    available = sorted(KNOWN_SOURCE_TABLES & names)
    missing = sorted(KNOWN_SOURCE_TABLES - names)
    return {
        "available": available,
        "missing": missing,
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _require_columns(
    conn: sqlite3.Connection,
    table: str,
    required: set[str],
) -> None:
    missing = sorted(required - _columns(conn, table))
    if missing:
        raise DataToolError(
            f"{table} Feedback schema가 호환되지 않습니다: "
            + ", ".join(missing)
        )


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback_schema_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    row = conn.execute(
        "SELECT value FROM feedback_schema_meta WHERE key='schema_version'"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO feedback_schema_meta(key,value) VALUES('schema_version',?)",
            (FEEDBACK_SCHEMA_VERSION,),
        )
    elif str(row[0]) != FEEDBACK_SCHEMA_VERSION:
        raise DataToolError(
            f"지원하지 않는 Feedback schema입니다: {row[0]}"
        )


def migrate_feedback_store(path: Path) -> dict[str, object]:
    path = Path(path)
    source_schema = _inspect_source_schema(path)
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        _ensure_meta(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_source_ref(
                id TEXT PRIMARY KEY,
                adapter_version TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_owner TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_item_id TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                durability TEXT NOT NULL,
                origin_kind TEXT NOT NULL,
                comparison_key TEXT NOT NULL,
                comparison_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                source_observed_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(source_type,source_id,source_item_id,source_hash)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_cohort(
                id TEXT PRIMARY KEY,
                client_request_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                cohort_version TEXT NOT NULL,
                filter_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_cohort_source(
                cohort_id TEXT NOT NULL,
                source_order INTEGER NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                selector_json TEXT NOT NULL,
                status TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY(cohort_id,source_order),
                FOREIGN KEY(cohort_id)
                    REFERENCES feedback_cohort(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_cohort_member(
                cohort_id TEXT NOT NULL,
                source_ref_id TEXT NOT NULL,
                inclusion_status TEXT NOT NULL,
                exclusion_reason TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(cohort_id,source_ref_id),
                FOREIGN KEY(cohort_id)
                    REFERENCES feedback_cohort(id) ON DELETE CASCADE,
                FOREIGN KEY(source_ref_id)
                    REFERENCES feedback_source_ref(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_report(
                id TEXT PRIMARY KEY,
                cohort_id TEXT NOT NULL,
                client_request_id TEXT NOT NULL UNIQUE,
                report_version TEXT NOT NULL,
                report_sequence INTEGER NOT NULL,
                source_set_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(cohort_id,report_sequence),
                FOREIGN KEY(cohort_id)
                    REFERENCES feedback_cohort(id) ON DELETE CASCADE
            )
            """
        )
        _require_columns(
            conn,
            "feedback_source_ref",
            {
                "id","adapter_version","source_type","source_owner","source_id",
                "source_item_id","source_hash","durability","origin_kind",
                "comparison_key","comparison_json","evidence_json",
                "source_observed_at","created_at",
            },
        )
        _require_columns(
            conn,
            "feedback_cohort",
            {
                "id","client_request_id","name","cohort_version",
                "filter_json","status","created_at",
            },
        )
        _require_columns(
            conn,
            "feedback_cohort_source",
            {
                "cohort_id","source_order","source_type","source_id",
                "selector_json","status","error_code","error_message",
                "evidence_count","created_at",
            },
        )
        _require_columns(
            conn,
            "feedback_cohort_member",
            {
                "cohort_id","source_ref_id","inclusion_status",
                "exclusion_reason","created_at",
            },
        )
        _require_columns(
            conn,
            "feedback_report",
            {
                "id","cohort_id","client_request_id","report_version",
                "report_sequence","source_set_hash","status","summary_json",
                "created_at",
            },
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_feedback_ref_origin
            ON feedback_source_ref(source_type,source_id,source_item_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_feedback_member_cohort
            ON feedback_cohort_member(cohort_id,inclusion_status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_feedback_report_cohort
            ON feedback_report(cohort_id,report_sequence DESC)
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_feedback_source_ref_immutable
            BEFORE UPDATE ON feedback_source_ref
            BEGIN
                SELECT RAISE(ABORT, 'Feedback source reference is immutable');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_feedback_report_immutable
            BEFORE UPDATE ON feedback_report
            BEGIN
                SELECT RAISE(ABORT, 'Feedback report is immutable');
            END
            """
        )

        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise DataToolError(
                f"Feedback migration FK 검증 실패: {len(fk_errors)}건"
            )
        conn.commit()
        return {
            "schema_version": FEEDBACK_SCHEMA_VERSION,
            "tables": [
                "feedback_source_ref",
                "feedback_cohort",
                "feedback_cohort_source",
                "feedback_cohort_member",
                "feedback_report",
            ],
            "source_tables": source_schema,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_feedback(
    *,
    simulation_db: Path | None = None,
) -> dict[str, object]:
    return migrate_feedback_store(
        Path(simulation_db or simulation_db_path())
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VN-P2-S1 Feedback/cohort/report schema를 명시적으로 생성합니다."
    )
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_feedback(simulation_db=args.simulation_db)
        print("VN-P2-S1 FEEDBACK MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
