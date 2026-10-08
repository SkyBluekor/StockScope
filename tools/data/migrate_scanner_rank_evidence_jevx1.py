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
from tools.data.common import DataToolError, simulation_db_path, sqlite_readonly

RANK_EVIDENCE_SCHEMA_VERSION = "SCANNER_RANK_EVIDENCE_STORAGE_V1"
RANK_EVIDENCE_META_TABLE = "scanner_rank_evidence_schema_meta"
RANK_EVIDENCE_TABLE = "scanner_rank_evidence"
RANK_EVIDENCE_TABLES = {RANK_EVIDENCE_META_TABLE, RANK_EVIDENCE_TABLE}
REQUIRED_BASE_TABLES = {
    "prospective_schema_meta",
    "prospective_capture_run",
    "prospective_recommendation_sample",
}


def migrate_scanner_rank_evidence_store(path: Path) -> dict[str, object]:
    path = Path(path)
    if not path.is_file():
        raise DataToolError(f"Simulation DB missing: {path}")
    with sqlite_readonly(path) as reader:
        tables = {
            str(row[0]) for row in reader.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if REQUIRED_BASE_TABLES - tables:
            raise DataToolError("Prospective base schema missing")
        row = reader.execute(
            "SELECT value FROM prospective_schema_meta WHERE key='schema_version'"
        ).fetchone()
        if row is None or str(row[0]) != PROSPECTIVE_SCHEMA_VERSION:
            raise DataToolError("Prospective schema incompatible")
        before = int(reader.execute(
            "SELECT COUNT(*) FROM prospective_recommendation_sample"
        ).fetchone()[0])

    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS scanner_rank_evidence_schema_meta("
            "key TEXT PRIMARY KEY,value TEXT NOT NULL)"
        )
        row = conn.execute(
            "SELECT value FROM scanner_rank_evidence_schema_meta "
            "WHERE key='schema_version'"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO scanner_rank_evidence_schema_meta(key,value) "
                "VALUES('schema_version',?)",
                (RANK_EVIDENCE_SCHEMA_VERSION,),
            )
        elif str(row[0]) != RANK_EVIDENCE_SCHEMA_VERSION:
            raise DataToolError("Scanner rank evidence schema incompatible")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scanner_rank_evidence(
                capture_run_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                contract_version TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                evidence_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(capture_run_id,sample_index),
                FOREIGN KEY(capture_run_id,sample_index)
                    REFERENCES prospective_recommendation_sample(
                        capture_run_id,sample_index
                    ) ON DELETE RESTRICT
            )
            """
        )
        expected = {
            "capture_run_id", "sample_index", "contract_version",
            "evidence_json", "evidence_hash", "created_at",
        }
        cols = {
            str(row[1]) for row in conn.execute(
                "PRAGMA table_info(scanner_rank_evidence)"
            ).fetchall()
        }
        if not expected.issubset(cols):
            raise DataToolError("Scanner rank evidence columns missing")
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_scanner_rank_evidence_immutable
            BEFORE UPDATE ON scanner_rank_evidence
            BEGIN
                SELECT RAISE(ABORT,'Scanner rank evidence is immutable');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_scanner_rank_evidence_no_delete
            BEFORE DELETE ON scanner_rank_evidence
            BEGIN
                SELECT RAISE(ABORT,'Scanner rank evidence is immutable');
            END
            """
        )
        after = int(conn.execute(
            "SELECT COUNT(*) FROM prospective_recommendation_sample"
        ).fetchone()[0])
        if after != before:
            raise DataToolError("Historical Prospective samples changed")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise DataToolError("Scanner rank evidence FK failed")
        conn.commit()
        return {
            "schema_version": RANK_EVIDENCE_SCHEMA_VERSION,
            "existing_samples_unchanged": True,
            "historical_backfill_performed": False,
            "external_network_requests": 0,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_scanner_rank_evidence(*, simulation_db: Path | None = None) -> dict[str, object]:
    return migrate_scanner_rank_evidence_store(
        Path(simulation_db or simulation_db_path())
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Scanner rank evidence sidecar migration")
    parser.add_argument("--simulation-db", type=Path)
    args = parser.parse_args()
    try:
        result = migrate_scanner_rank_evidence(simulation_db=args.simulation_db)
        print("SCANNER RANK EVIDENCE MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
