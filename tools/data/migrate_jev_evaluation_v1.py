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

from app.jev.evaluation_models import JEV_EVALUATION_SCHEMA_VERSION
from tools.data.common import DataToolError, simulation_db_path, sqlite_readonly


REQUIRED_BASE_TABLES = frozenset(
    {
        "jev_shadow_schema_meta",
        "jev_shadow_protocol",
        "jev_shadow_review",
        "jev_shadow_comparison_report",
        "prospective_capture_run",
        "prospective_recommendation_sample",
    }
)

JEV_EVALUATION_TABLE_COLUMNS: dict[str, set[str]] = {
    "jev_evaluation_run": {
        "id",
        "client_request_id",
        "run_version",
        "protocol_id",
        "protocol_spec_hash",
        "evaluation_policy_id",
        "evaluation_policy_hash",
        "evaluation_as_of",
        "exit_policy_token",
        "status",
        "source_set_hash",
        "recruited_count",
        "mature_count",
        "comparable_closed_count",
        "disagreement_count",
        "created_at",
        "completed_at",
        "error_code",
        "error_message",
    },
    "jev_evaluation_unit": {
        "evaluation_run_id",
        "capture_run_id",
        "sample_index",
        "review_id",
        "market",
        "ticker",
        "name",
        "signal_date",
        "strategy",
        "horizon",
        "review_status",
        "review_decision",
        "provider_id",
        "model_id",
        "served_model",
        "model_cohort_key",
        "maturity_status",
        "available_trading_days",
        "evaluated_through",
        "return_5d",
        "return_10d",
        "return_20d",
        "mfe_pct",
        "mae_pct",
        "execution_status",
        "execution_reason",
        "entry_date",
        "entry_price",
        "exit_date",
        "exit_price",
        "exit_reason",
        "holding_days",
        "gross_return_pct",
        "net_return_pct",
        "mark_return_pct",
        "comparison_eligible",
        "details_json",
        "computed_at",
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
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _inspect(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise DataToolError(f"Simulation DB를 찾을 수 없습니다: {path}")
    with sqlite_readonly(path) as conn:
        names = _table_names(conn)
        missing = sorted(REQUIRED_BASE_TABLES - names)
        if missing:
            raise DataToolError(
                "JEV evaluation은 JEV Shadow migration 이후에만 생성할 수 있습니다: "
                + ", ".join(missing)
            )
        row = conn.execute("PRAGMA integrity_check").fetchone()
        if row is None or str(row[0]).lower() != "ok":
            raise DataToolError("Simulation DB integrity_check에 실패했습니다.")
    return {
        "required_base_present": True,
        "historical_backfill_performed": False,
        "external_network_requests": 0,
        "model_calls_executed": 0,
    }


def migrate_jev_evaluation_store(path: Path) -> dict[str, object]:
    path = Path(path)
    source_state = _inspect(path)
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_evaluation_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            """
            SELECT value
            FROM jev_evaluation_schema_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO jev_evaluation_schema_meta(key,value)
                VALUES('schema_version',?)
                """,
                (JEV_EVALUATION_SCHEMA_VERSION,),
            )
        elif str(row[0]) != JEV_EVALUATION_SCHEMA_VERSION:
            raise DataToolError(
                "지원하지 않는 JEV evaluation schema version입니다: "
                + str(row[0])
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_evaluation_run(
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
                mature_count INTEGER NOT NULL DEFAULT 0,
                comparable_closed_count INTEGER NOT NULL DEFAULT 0,
                disagreement_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                error_code TEXT,
                error_message TEXT,
                FOREIGN KEY(protocol_id)
                    REFERENCES jev_shadow_protocol(id)
                    ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_evaluation_unit(
                evaluation_run_id TEXT NOT NULL,
                capture_run_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                review_id TEXT NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                signal_date TEXT NOT NULL,
                strategy TEXT,
                horizon TEXT,
                review_status TEXT NOT NULL,
                review_decision TEXT,
                provider_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                served_model TEXT,
                model_cohort_key TEXT NOT NULL,
                maturity_status TEXT NOT NULL,
                available_trading_days INTEGER NOT NULL,
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
                PRIMARY KEY(evaluation_run_id,capture_run_id,sample_index),
                FOREIGN KEY(evaluation_run_id)
                    REFERENCES jev_evaluation_run(id)
                    ON DELETE RESTRICT,
                FOREIGN KEY(review_id)
                    REFERENCES jev_shadow_review(id)
                    ON DELETE RESTRICT,
                FOREIGN KEY(capture_run_id,sample_index)
                    REFERENCES prospective_recommendation_sample(
                        capture_run_id,sample_index
                    )
                    ON DELETE RESTRICT
            )
            """
        )

        for table, required in JEV_EVALUATION_TABLE_COLUMNS.items():
            missing = sorted(required - _columns(conn, table))
            if missing:
                raise DataToolError(
                    f"{table} schema가 JEV Evaluation V1과 호환되지 않습니다: "
                    + ", ".join(missing)
                )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jev_eval_run_status
            ON jev_evaluation_run(status,created_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jev_eval_unit_review
            ON jev_evaluation_unit(review_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jev_eval_unit_signal
            ON jev_evaluation_unit(signal_date,market,ticker)
            """
        )
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise DataToolError(
                f"JEV Evaluation migration FK 검증 실패: {len(fk_errors)}건"
            )
        conn.commit()
        return {
            "schema_version": JEV_EVALUATION_SCHEMA_VERSION,
            "tables": [
                "jev_evaluation_run",
                "jev_evaluation_unit",
            ],
            **source_state,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_jev_evaluation(
    *,
    simulation_db: Path | None = None,
) -> dict[str, object]:
    return migrate_jev_evaluation_store(
        Path(simulation_db or simulation_db_path())
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JEV Reviewer Evaluation V1 storage를 명시적으로 생성합니다."
    )
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_jev_evaluation(
            simulation_db=args.simulation_db
        )
        print("JEV REVIEWER EVALUATION V1 MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
