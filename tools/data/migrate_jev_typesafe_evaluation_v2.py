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

from app.jev.typesafe_evaluation_models import (
    JEV_TYPESAFE_EVALUATION_SCHEMA_VERSION,
)
from tools.data.common import DataToolError, simulation_db_path


REQUIRED_BASE_TABLES = frozenset(
    {
        "prospective_capture_run",
        "prospective_recommendation_sample",
        "jev_typesafe_protocol",
        "jev_typesafe_recruitment",
        "jev_typesafe_review",
    }
)

JEV_TYPESAFE_EVALUATION_TABLE_COLUMNS: dict[str, set[str]] = {
    "jev_typesafe_evaluation_run": {
        "id","client_request_id","run_version","protocol_id",
        "protocol_spec_hash","evaluation_policy_id","evaluation_policy_hash",
        "evaluation_as_of","exit_policy_token","status","source_set_hash",
        "recruited_count","callable_count","review_created_count","valid_count",
        "mature_count","comparable_closed_count","disagreement_count",
        "created_at","completed_at","error_code","error_message",
    },
    "jev_typesafe_evaluation_unit": {
        "evaluation_run_id","recruitment_id","capture_run_id","sample_index",
        "review_id","market","ticker","name","signal_date","strategy","horizon",
        "callable","skip_reason","operational_status","disposition",
        "failure_code","integrity_status","provider_id","model_requested",
        "model_returned","model_identity_status","model_cohort_key","latency_ms",
        "reserved_cost_usd","known_cost_usd","cost_unknown","maturity_status",
        "available_trading_days","evaluated_through","return_5d","return_10d",
        "return_20d","mfe_pct","mae_pct","execution_status","execution_reason",
        "entry_date","entry_price","exit_date","exit_price","exit_reason",
        "holding_days","gross_return_pct","net_return_pct","mark_return_pct",
        "comparison_eligible","details_json","computed_at",
    },
    "jev_typesafe_evaluation_report": {
        "id","evaluation_run_id","report_version","source_set_hash",
        "summary_json","created_at",
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


def migrate_jev_typesafe_evaluation(
    simulation_db: Path | None = None,
) -> dict[str, object]:
    path = Path(simulation_db or simulation_db_path())
    if not path.is_file():
        raise DataToolError("Simulation DB가 없습니다.")
    with sqlite3.connect(path) as conn:
        names = _tables(conn)
    missing = sorted(REQUIRED_BASE_TABLES - names)
    if missing:
        raise DataToolError(
            "TypeSafe JEV Evaluation V2 prerequisite가 없습니다: "
            + ", ".join(missing)
        )

    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_typesafe_evaluation_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            """
            SELECT value FROM jev_typesafe_evaluation_schema_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO jev_typesafe_evaluation_schema_meta(key,value)
                VALUES('schema_version',?)
                """,
                (JEV_TYPESAFE_EVALUATION_SCHEMA_VERSION,),
            )
        elif str(row[0]) != JEV_TYPESAFE_EVALUATION_SCHEMA_VERSION:
            raise DataToolError(
                "Unsupported TypeSafe JEV Evaluation schema: " + str(row[0])
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_typesafe_evaluation_run(
                id TEXT PRIMARY KEY,
                client_request_id TEXT NOT NULL UNIQUE,
                run_version TEXT NOT NULL,
                protocol_id TEXT NOT NULL,
                protocol_spec_hash TEXT NOT NULL,
                evaluation_policy_id TEXT NOT NULL,
                evaluation_policy_hash TEXT NOT NULL,
                evaluation_as_of TEXT NOT NULL,
                exit_policy_token TEXT NOT NULL,
                status TEXT NOT NULL,
                source_set_hash TEXT,
                recruited_count INTEGER NOT NULL DEFAULT 0,
                callable_count INTEGER NOT NULL DEFAULT 0,
                review_created_count INTEGER NOT NULL DEFAULT 0,
                valid_count INTEGER NOT NULL DEFAULT 0,
                mature_count INTEGER NOT NULL DEFAULT 0,
                comparable_closed_count INTEGER NOT NULL DEFAULT 0,
                disagreement_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                error_code TEXT,
                error_message TEXT,
                FOREIGN KEY(protocol_id)
                    REFERENCES jev_typesafe_protocol(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_typesafe_evaluation_unit(
                evaluation_run_id TEXT NOT NULL,
                recruitment_id TEXT NOT NULL,
                capture_run_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                review_id TEXT,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                signal_date TEXT NOT NULL,
                strategy TEXT,
                horizon TEXT,
                callable INTEGER NOT NULL,
                skip_reason TEXT,
                operational_status TEXT NOT NULL,
                disposition TEXT,
                failure_code TEXT,
                integrity_status TEXT NOT NULL,
                provider_id TEXT,
                model_requested TEXT,
                model_returned TEXT,
                model_identity_status TEXT,
                model_cohort_key TEXT,
                latency_ms INTEGER,
                reserved_cost_usd REAL NOT NULL DEFAULT 0,
                known_cost_usd REAL,
                cost_unknown INTEGER NOT NULL DEFAULT 0,
                maturity_status TEXT NOT NULL,
                available_trading_days INTEGER NOT NULL DEFAULT 0,
                evaluated_through TEXT,
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                mfe_pct REAL,
                mae_pct REAL,
                execution_status TEXT NOT NULL,
                execution_reason TEXT,
                entry_date TEXT,
                entry_price REAL,
                exit_date TEXT,
                exit_price REAL,
                exit_reason TEXT,
                holding_days INTEGER,
                gross_return_pct REAL,
                net_return_pct REAL,
                mark_return_pct REAL,
                comparison_eligible INTEGER NOT NULL CHECK(comparison_eligible IN (0,1)),
                details_json TEXT NOT NULL,
                computed_at TEXT NOT NULL,
                PRIMARY KEY(evaluation_run_id,recruitment_id),
                FOREIGN KEY(evaluation_run_id)
                    REFERENCES jev_typesafe_evaluation_run(id) ON DELETE RESTRICT,
                FOREIGN KEY(recruitment_id)
                    REFERENCES jev_typesafe_recruitment(id) ON DELETE RESTRICT,
                FOREIGN KEY(review_id)
                    REFERENCES jev_typesafe_review(id) ON DELETE RESTRICT,
                FOREIGN KEY(capture_run_id,sample_index)
                    REFERENCES prospective_recommendation_sample(
                        capture_run_id,sample_index
                    ) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_typesafe_evaluation_report(
                id TEXT PRIMARY KEY,
                evaluation_run_id TEXT NOT NULL UNIQUE,
                report_version TEXT NOT NULL,
                source_set_hash TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(evaluation_run_id)
                    REFERENCES jev_typesafe_evaluation_run(id) ON DELETE RESTRICT
            )
            """
        )

        for table, required in JEV_TYPESAFE_EVALUATION_TABLE_COLUMNS.items():
            absent = sorted(required - _columns(conn, table))
            if absent:
                raise DataToolError(
                    f"{table} schema mismatch: " + ", ".join(absent)
                )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jev_typesafe_eval_run_status
            ON jev_typesafe_evaluation_run(status,created_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jev_typesafe_eval_unit_signal
            ON jev_typesafe_evaluation_unit(signal_date,market,ticker)
            """
        )
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise DataToolError(
                "TypeSafe JEV Evaluation migration FK 오류: "
                + str(len(fk_errors))
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "schema_version": JEV_TYPESAFE_EVALUATION_SCHEMA_VERSION,
        "historical_backfill_performed": False,
        "external_network_requests": 0,
        "model_calls_executed": 0,
        "secret_values_read": False,
        "tables": sorted(JEV_TYPESAFE_EVALUATION_TABLE_COLUMNS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create additive TypeSafe JEV Evaluation V2 storage. "
            "No provider call, credential read, or actual evaluation is performed."
        )
    )
    parser.add_argument("--simulation-db", type=Path)
    args = parser.parse_args()
    try:
        result = migrate_jev_typesafe_evaluation(args.simulation_db)
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("JEV TYPESAFE EVALUATION V2 MIGRATION PASS")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
