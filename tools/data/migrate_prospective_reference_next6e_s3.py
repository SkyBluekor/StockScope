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

from app.prospective.models import PROSPECTIVE_SCHEMA_VERSION
from app.prospective.reference_capture import (
    NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION,
)
from tools.data.common import (
    DataToolError,
    simulation_db_path,
    sqlite_readonly,
)


_REQUIRED_BASE_TABLES = {
    "prospective_schema_meta",
    "prospective_capture_run",
    "prospective_recommendation_sample",
}
_REFERENCE_TABLES = {
    "prospective_reference_schema_meta",
    "prospective_reference_capture",
    "prospective_reference_attachment",
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _inspect_base(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise DataToolError(f"Simulation DB를 찾을 수 없습니다: {path}")
    with sqlite_readonly(path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise DataToolError("Simulation DB integrity_check에 실패했습니다.")

        tables = _table_names(conn)
        missing = sorted(_REQUIRED_BASE_TABLES - tables)
        if missing:
            raise DataToolError(
                "Prospective base schema가 준비되지 않았습니다: "
                + ", ".join(missing)
            )
        row = conn.execute(
            """
            SELECT value
            FROM prospective_schema_meta
            WHERE key='schema_version'
            LIMIT 1
            """
        ).fetchone()
        if row is None or str(row[0]) != PROSPECTIVE_SCHEMA_VERSION:
            raise DataToolError(
                "Prospective base schema version이 지원 범위와 다릅니다."
            )

        capture_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM prospective_capture_run"
            ).fetchone()[0]
        )
        sample_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM prospective_recommendation_sample"
            ).fetchone()[0]
        )
    return {
        "base_schema_version": PROSPECTIVE_SCHEMA_VERSION,
        "existing_capture_count": capture_count,
        "existing_sample_count": sample_count,
    }


def migrate_prospective_reference_store(path: Path) -> dict[str, object]:
    path = Path(path)
    source_state = _inspect_base(path)

    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prospective_reference_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            """
            SELECT value
            FROM prospective_reference_schema_meta
            WHERE key='schema_version'
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO prospective_reference_schema_meta(key,value)
                VALUES('schema_version',?)
                """,
                (NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION,),
            )
        elif str(row[0]) != NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION:
            raise DataToolError(
                "지원하지 않는 Prospective reference schema version입니다."
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prospective_reference_capture(
                capture_run_id TEXT PRIMARY KEY,
                capture_contract_version TEXT NOT NULL,
                storage_version TEXT NOT NULL,
                status TEXT NOT NULL,
                reference_cutoff TEXT NOT NULL,
                cutoff_policy_version TEXT NOT NULL,
                reference_temporal_mode TEXT NOT NULL,
                source_sample_count INTEGER NOT NULL,
                attachment_count INTEGER NOT NULL,
                attachment_set_hash TEXT NOT NULL,
                source_manifest_hash TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(capture_run_id)
                    REFERENCES prospective_capture_run(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prospective_reference_attachment(
                capture_run_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                attachment_id TEXT NOT NULL UNIQUE,
                attachment_hash TEXT NOT NULL,
                source_snapshot_hash TEXT NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                signal_date TEXT NOT NULL,
                reference_cutoff TEXT NOT NULL,
                projection_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(capture_run_id,sample_index),
                FOREIGN KEY(capture_run_id)
                    REFERENCES prospective_reference_capture(capture_run_id)
                    ON DELETE RESTRICT,
                FOREIGN KEY(capture_run_id,sample_index)
                    REFERENCES prospective_recommendation_sample(
                        capture_run_id,sample_index
                    ) ON DELETE RESTRICT
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_prospective_reference_status
            ON prospective_reference_capture(status,completed_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_prospective_reference_sample
            ON prospective_reference_attachment(
                signal_date,market,ticker
            )
            """
        )

        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_prospective_reference_attachment_immutable
            BEFORE UPDATE ON prospective_reference_attachment
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Prospective reference attachment is immutable'
                );
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_prospective_reference_capture_terminal_immutable
            BEFORE UPDATE ON prospective_reference_capture
            WHEN OLD.status IN ('COMPLETE','FAILED')
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Terminal prospective reference capture is immutable'
                );
            END
            """
        )

        tables = _table_names(conn)
        missing_reference = sorted(_REFERENCE_TABLES - tables)
        if missing_reference:
            raise DataToolError(
                "Prospective reference migration table 생성 실패: "
                + ", ".join(missing_reference)
            )

        reference_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM prospective_reference_capture"
            ).fetchone()[0]
        )
        attachment_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM prospective_reference_attachment"
            ).fetchone()[0]
        )
        if reference_count != 0 or attachment_count != 0:
            # Existing rows are allowed on an idempotent rerun, but migration
            # itself never creates historical attachments.
            pass

        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise DataToolError(
                f"Prospective reference migration FK 검증 실패: "
                f"{len(fk_errors)}건"
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "schema_version": NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION,
        "tables": sorted(_REFERENCE_TABLES),
        "source_state": source_state,
        "historical_backfill_performed": False,
    }


def migrate_prospective_reference(
    *,
    simulation_db: Path | None = None,
) -> dict[str, object]:
    return migrate_prospective_reference_store(
        Path(simulation_db or simulation_db_path())
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "NEXT-6E-S3 prospective reference attachment schema를 "
            "명시적으로 생성합니다."
        )
    )
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_prospective_reference(
            simulation_db=args.simulation_db
        )
        print("NEXT-6E-S3 PROSPECTIVE REFERENCE MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
