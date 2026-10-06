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

from app.jev.models import JEV_SCHEMA_VERSION
from tools.data.common import DataToolError, simulation_db_path, sqlite_readonly


REQUIRED_BASE_TABLES = frozenset(
    {
        "prospective_schema_meta",
        "prospective_capture_run",
        "prospective_recommendation_sample",
    }
)

JEV_TABLE_COLUMNS: dict[str, set[str]] = {
    "jev_shadow_protocol": {
        "id",
        "client_request_id",
        "protocol_version",
        "name",
        "status",
        "spec_json",
        "spec_hash",
        "created_at",
    },
    "jev_shadow_activation": {
        "singleton_id",
        "protocol_id",
        "enabled",
        "allow_network",
        "updated_at",
    },
    "jev_shadow_review": {
        "id",
        "request_id",
        "protocol_id",
        "capture_run_id",
        "sample_index",
        "candidate_ref",
        "candidate_snapshot_hash",
        "idempotency_key",
        "attempt",
        "input_hash",
        "input_json",
        "provider_id",
        "model_id",
        "model_revision",
        "prompt_version",
        "prompt_hash",
        "output_contract_version",
        "adapter_version",
        "comparison_policy",
        "requested_at",
        "completed_at",
        "deadline_at",
        "status",
        "decision",
        "abstain_reason",
        "failure_code",
        "normalized_response_json",
        "raw_response_hash",
        "latency_ms",
        "usage_json",
        "cost_usd",
    },
    "jev_shadow_comparison_report": {
        "id",
        "protocol_id",
        "report_version",
        "source_set_hash",
        "summary_json",
        "created_at",
    },
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


def _inspect(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise DataToolError(
            f"Simulation DB를 찾을 수 없습니다: {path}"
        )
    with sqlite_readonly(path) as conn:
        names = _table_names(conn)
        missing = sorted(REQUIRED_BASE_TABLES - names)
        if missing:
            raise DataToolError(
                "JEV Shadow는 Prospective base migration 이후에만 "
                "생성할 수 있습니다: "
                + ", ".join(missing)
            )
        row = conn.execute("PRAGMA integrity_check").fetchone()
        if row is None or str(row[0]).lower() != "ok":
            raise DataToolError(
                "Simulation DB integrity_check에 실패했습니다."
            )
    return {
        "prospective_base_present": True,
        "historical_backfill_performed": False,
        "external_network_requests": 0,
    }


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jev_shadow_schema_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    row = conn.execute(
        """
        SELECT value
        FROM jev_shadow_schema_meta
        WHERE key='schema_version'
        """
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO jev_shadow_schema_meta(key,value)
            VALUES('schema_version',?)
            """,
            (JEV_SCHEMA_VERSION,),
        )
    elif str(row[0]) != JEV_SCHEMA_VERSION:
        raise DataToolError(
            "지원하지 않는 JEV shadow schema version입니다: "
            + str(row[0])
        )


def migrate_jev_shadow_store(path: Path) -> dict[str, object]:
    path = Path(path)
    source_state = _inspect(path)
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        _ensure_meta(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_shadow_protocol(
                id TEXT PRIMARY KEY,
                client_request_id TEXT NOT NULL UNIQUE,
                protocol_version TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                spec_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_shadow_activation(
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                protocol_id TEXT NOT NULL,
                enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                allow_network INTEGER NOT NULL CHECK(allow_network IN (0,1)),
                updated_at TEXT NOT NULL,
                FOREIGN KEY(protocol_id)
                    REFERENCES jev_shadow_protocol(id)
                    ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_shadow_review(
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                protocol_id TEXT NOT NULL,
                capture_run_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                candidate_ref TEXT NOT NULL,
                candidate_snapshot_hash TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                attempt INTEGER NOT NULL DEFAULT 1,
                input_hash TEXT NOT NULL,
                input_json TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                model_revision TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                prompt_hash TEXT NOT NULL,
                output_contract_version TEXT NOT NULL,
                adapter_version TEXT NOT NULL,
                comparison_policy TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                completed_at TEXT,
                deadline_at TEXT,
                status TEXT NOT NULL,
                decision TEXT,
                abstain_reason TEXT,
                failure_code TEXT,
                normalized_response_json TEXT,
                raw_response_hash TEXT,
                latency_ms INTEGER,
                usage_json TEXT,
                cost_usd REAL,
                FOREIGN KEY(protocol_id)
                    REFERENCES jev_shadow_protocol(id)
                    ON DELETE RESTRICT,
                FOREIGN KEY(capture_run_id,sample_index)
                    REFERENCES prospective_recommendation_sample(
                        capture_run_id,sample_index
                    )
                    ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_shadow_comparison_report(
                id TEXT PRIMARY KEY,
                protocol_id TEXT NOT NULL,
                report_version TEXT NOT NULL,
                source_set_hash TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(protocol_id,source_set_hash),
                FOREIGN KEY(protocol_id)
                    REFERENCES jev_shadow_protocol(id)
                    ON DELETE RESTRICT
            )
            """
        )

        for table, required in JEV_TABLE_COLUMNS.items():
            missing = sorted(required - _columns(conn, table))
            if missing:
                raise DataToolError(
                    f"{table} schema가 JEV Shadow V1과 호환되지 "
                    "않습니다: "
                    + ", ".join(missing)
                )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jev_shadow_review_capture
            ON jev_shadow_review(
                capture_run_id,sample_index,requested_at
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jev_shadow_review_protocol
            ON jev_shadow_review(
                protocol_id,status,requested_at
            )
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
            trg_jev_shadow_protocol_immutable
            BEFORE UPDATE ON jev_shadow_protocol
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'JEV shadow protocol is immutable'
                );
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
            trg_jev_shadow_review_terminal_immutable
            BEFORE UPDATE ON jev_shadow_review
            WHEN OLD.status IN (
                'VALID',
                'ERROR',
                'LATE',
                'SKIPPED',
                'INTERRUPTED'
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Terminal JEV shadow review is immutable'
                );
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
            trg_jev_shadow_report_immutable
            BEFORE UPDATE ON jev_shadow_comparison_report
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'JEV shadow comparison report is immutable'
                );
            END
            """
        )

        fk_errors = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if fk_errors:
            raise DataToolError(
                "JEV Shadow migration FK 검증 실패: "
                f"{len(fk_errors)}건"
            )
        conn.commit()
        return {
            "schema_version": JEV_SCHEMA_VERSION,
            "tables": [
                "jev_shadow_protocol",
                "jev_shadow_activation",
                "jev_shadow_review",
                "jev_shadow_comparison_report",
            ],
            **source_state,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_jev_shadow(
    *,
    simulation_db: Path | None = None,
) -> dict[str, object]:
    return migrate_jev_shadow_store(
        Path(simulation_db or simulation_db_path())
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JEV Shadow V1 storage를 명시적으로 생성합니다."
    )
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_jev_shadow(
            simulation_db=args.simulation_db
        )
        print("JEV SHADOW V1 MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
