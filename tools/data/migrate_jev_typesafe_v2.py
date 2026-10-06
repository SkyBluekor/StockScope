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

from app.jev.typesafe_models import JEV_TYPESAFE_SCHEMA_VERSION
from tools.data.common import DataToolError, simulation_db_path


REQUIRED_BASE_TABLES = frozenset(
    {
        "prospective_schema_meta",
        "prospective_capture_run",
        "prospective_recommendation_sample",
    }
)

JEV_TYPESAFE_TABLE_COLUMNS: dict[str, set[str]] = {
    "jev_typesafe_protocol": {
        "id", "client_request_id", "protocol_version", "name", "status",
        "spec_json", "spec_hash", "created_at",
    },
    "jev_typesafe_activation": {
        "singleton_id", "protocol_id", "enabled", "allow_network", "updated_at",
    },
    "jev_typesafe_recruitment": {
        "id", "protocol_id", "capture_run_id", "sample_index",
        "analysis_unit_key", "candidate_snapshot_hash", "recruited_at",
        "callable", "skip_reason", "reserved_cost_usd", "known_cost_usd",
        "cost_unknown", "review_id",
    },
    "jev_typesafe_review": {
        "id", "recruitment_id", "request_id", "protocol_id",
        "state_contract_version", "state_hash", "state_json",
        "projector_version", "projector_hash", "question_contract_version",
        "question_set_hash", "disposition_policy_version",
        "disposition_policy_hash", "provider_id", "model_requested",
        "model_returned", "model_identity_status", "adapter_version",
        "requested_at", "completed_at", "deadline_at", "status",
        "disposition", "uncertainty_reason", "failure_code",
        "typed_answers_json", "raw_response_hash", "latency_ms",
        "usage_json", "cost_usd", "cost_unknown",
    },
}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def migrate_jev_typesafe(
    simulation_db: Path | None = None,
) -> dict[str, object]:
    path = Path(simulation_db or simulation_db_path())
    if not path.is_file():
        raise DataToolError("Simulation DB가 없습니다.")
    with sqlite3.connect(path) as conn:
        base_tables = _tables(conn)
    if not REQUIRED_BASE_TABLES.issubset(base_tables):
        raise DataToolError(
            "TypeSafe JEV V2 migration requires prospective capture tables."
        )

    with sqlite3.connect(path, timeout=20.0) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_typesafe_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT value FROM jev_typesafe_schema_meta WHERE key='schema_version'"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO jev_typesafe_schema_meta(key,value) VALUES('schema_version',?)",
                (JEV_TYPESAFE_SCHEMA_VERSION,),
            )
        elif str(row[0]) != JEV_TYPESAFE_SCHEMA_VERSION:
            raise DataToolError(
                "Unsupported TypeSafe JEV schema version: " + str(row[0])
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_typesafe_protocol(
                id TEXT PRIMARY KEY,
                client_request_id TEXT NOT NULL UNIQUE,
                protocol_version TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('DRAFT','FROZEN')),
                spec_json TEXT NOT NULL,
                spec_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_typesafe_activation(
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                protocol_id TEXT NOT NULL,
                enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                allow_network INTEGER NOT NULL CHECK(allow_network IN (0,1)),
                updated_at TEXT NOT NULL,
                FOREIGN KEY(protocol_id) REFERENCES jev_typesafe_protocol(id)
                    ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_typesafe_recruitment(
                id TEXT PRIMARY KEY,
                protocol_id TEXT NOT NULL,
                capture_run_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                analysis_unit_key TEXT NOT NULL,
                candidate_snapshot_hash TEXT NOT NULL,
                recruited_at TEXT NOT NULL,
                callable INTEGER NOT NULL CHECK(callable IN (0,1)),
                skip_reason TEXT,
                reserved_cost_usd REAL NOT NULL DEFAULT 0,
                known_cost_usd REAL,
                cost_unknown INTEGER NOT NULL DEFAULT 0
                    CHECK(cost_unknown IN (0,1)),
                review_id TEXT,
                UNIQUE(protocol_id,analysis_unit_key),
                FOREIGN KEY(protocol_id) REFERENCES jev_typesafe_protocol(id)
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
            CREATE TABLE IF NOT EXISTS jev_typesafe_review(
                id TEXT PRIMARY KEY,
                recruitment_id TEXT NOT NULL UNIQUE,
                request_id TEXT NOT NULL UNIQUE,
                protocol_id TEXT NOT NULL,
                state_contract_version TEXT NOT NULL,
                state_hash TEXT NOT NULL,
                state_json TEXT NOT NULL,
                projector_version TEXT NOT NULL,
                projector_hash TEXT NOT NULL,
                question_contract_version TEXT NOT NULL,
                question_set_hash TEXT NOT NULL,
                disposition_policy_version TEXT NOT NULL,
                disposition_policy_hash TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                model_requested TEXT NOT NULL,
                model_returned TEXT,
                model_identity_status TEXT NOT NULL,
                adapter_version TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                completed_at TEXT,
                deadline_at TEXT,
                status TEXT NOT NULL,
                disposition TEXT,
                uncertainty_reason TEXT,
                failure_code TEXT,
                typed_answers_json TEXT,
                raw_response_hash TEXT,
                latency_ms INTEGER,
                usage_json TEXT,
                cost_usd REAL,
                cost_unknown INTEGER NOT NULL DEFAULT 1
                    CHECK(cost_unknown IN (0,1)),
                FOREIGN KEY(recruitment_id)
                    REFERENCES jev_typesafe_recruitment(id)
                    ON DELETE RESTRICT,
                FOREIGN KEY(protocol_id)
                    REFERENCES jev_typesafe_protocol(id)
                    ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS jev_typesafe_review_terminal_immutable
            BEFORE UPDATE ON jev_typesafe_review
            WHEN OLD.status <> 'PENDING'
            BEGIN
                SELECT RAISE(ABORT,'terminal TypeSafe JEV review is immutable');
            END
            """
        )
        conn.commit()

        tables = _tables(conn)
        for table, required_columns in JEV_TYPESAFE_TABLE_COLUMNS.items():
            if table not in tables:
                raise DataToolError(f"TypeSafe JEV migration missing table: {table}")
            missing = required_columns - _columns(conn, table)
            if missing:
                raise DataToolError(
                    f"TypeSafe JEV migration missing columns in {table}: "
                    + ", ".join(sorted(missing))
                )

    return {
        "schema_version": JEV_TYPESAFE_SCHEMA_VERSION,
        "required_base_present": True,
        "historical_backfill_performed": False,
        "external_network_requests": 0,
        "model_calls_executed": 0,
        "secret_values_read": False,
        "tables": sorted(JEV_TYPESAFE_TABLE_COLUMNS),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create additive TypeSafe JEV V2 storage. "
            "No provider call or historical backfill is performed."
        )
    )
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_jev_typesafe(args.simulation_db)
    except DataToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("JEV TYPESAFE V2 MIGRATION PASS")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
