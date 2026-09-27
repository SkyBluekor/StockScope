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


TABLE_COLUMNS: dict[str, set[str]] = {
    "prospective_capture_run": {
        "id","capture_version","source_job_id","source_execution_key",
        "canonical_capture_id","status","request_json","scanner_version",
        "scanner_baseline","market_scope","requested_as_of","actual_data_date",
        "input_fingerprint","horizon_intent","horizon_policy_version",
        "candidate_limit","actionable_candidate_count","returned_candidate_count",
        "result_hash","source_snapshot_hash","error_code","error_message",
        "created_at","started_at","completed_at","updated_at",
    },
    "prospective_recommendation_sample": {
        "capture_run_id","sample_index","market","ticker","name","rank",
        "strategy","decision_status","candidate_state","action","signal_date",
        "snapshot_json","snapshot_hash","created_at",
    },
    "prospective_evaluation_protocol": {
        "id","client_request_id","protocol_version","name","status",
        "spec_json","spec_hash","created_at",
    },
    "prospective_evaluation_run": {
        "id","protocol_id","client_request_id","evaluation_version","status",
        "source_capture_count","source_sample_count","development_count",
        "holdout_count","purged_count","mature_count","immature_count",
        "excluded_count","failed_count","processed_count","cancel_requested",
        "restart_count","error_code","error_message",
        "created_at","started_at","completed_at","updated_at",
    },
    "prospective_evaluation_unit": {
        "evaluation_run_id","capture_run_id","sample_index","split",
        "maturity_status","exclusion_reason","signal_date","market","ticker",
        "strategy","available_trading_days","evaluated_through",
        "return_5d","return_10d","return_20d","mfe_pct","mae_pct",
        "entry_comparable","entry_touched","stop_comparable","stop_touched",
        "target1_comparable","target1_touched","target2_comparable",
        "target2_touched","execution_status","execution_reason",
        "entry_date","entry_price","exit_date","exit_price","exit_reason",
        "holding_days","gross_return_pct","net_return_pct","mark_return_pct",
        "details_json","computed_at",
    },
    "prospective_evaluation_report": {
        "id","evaluation_run_id","report_version","source_set_hash",
        "summary_json","created_at",
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


def _require_columns(conn: sqlite3.Connection, table: str) -> None:
    missing = sorted(TABLE_COLUMNS[table] - _columns(conn, table))
    if missing:
        raise DataToolError(
            f"{table} schema가 VN-P2-S2와 호환되지 않습니다: "
            + ", ".join(missing)
        )


def _inspect_simulation_db(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise DataToolError(f"Simulation DB를 찾을 수 없습니다: {path}")
    with sqlite_readonly(path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise DataToolError("Simulation DB integrity_check에 실패했습니다.")
        tables = sorted(_table_names(conn))
    return {
        "existing_table_count": len(tables),
        "feedback_v1_present": "feedback_schema_meta" in tables,
        "validation_present": "historical_validation_run" in tables,
        "execution_present": "historical_execution_run" in tables,
    }


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prospective_schema_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    row = conn.execute(
        "SELECT value FROM prospective_schema_meta WHERE key='schema_version'"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO prospective_schema_meta(key,value) VALUES('schema_version',?)",
            (PROSPECTIVE_SCHEMA_VERSION,),
        )
    elif str(row[0]) != PROSPECTIVE_SCHEMA_VERSION:
        raise DataToolError(
            f"지원하지 않는 prospective schema version입니다: {row[0]}"
        )


def migrate_prospective_store(path: Path) -> dict[str, object]:
    path = Path(path)
    source_state = _inspect_simulation_db(path)
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        _ensure_meta(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prospective_capture_run(
                id TEXT PRIMARY KEY,
                capture_version TEXT NOT NULL,
                source_job_id TEXT NOT NULL UNIQUE,
                source_execution_key TEXT,
                canonical_capture_id TEXT,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                scanner_version TEXT,
                scanner_baseline TEXT,
                market_scope TEXT NOT NULL,
                requested_as_of TEXT,
                actual_data_date TEXT,
                input_fingerprint TEXT,
                horizon_intent TEXT NOT NULL,
                horizon_policy_version TEXT,
                candidate_limit INTEGER NOT NULL,
                actionable_candidate_count INTEGER NOT NULL DEFAULT 0,
                returned_candidate_count INTEGER NOT NULL DEFAULT 0,
                result_hash TEXT,
                source_snapshot_hash TEXT,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(canonical_capture_id)
                    REFERENCES prospective_capture_run(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prospective_recommendation_sample(
                capture_run_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT NOT NULL,
                rank INTEGER,
                strategy TEXT,
                decision_status TEXT,
                candidate_state TEXT,
                action TEXT,
                signal_date TEXT,
                snapshot_json TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(capture_run_id,sample_index),
                FOREIGN KEY(capture_run_id)
                    REFERENCES prospective_capture_run(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prospective_evaluation_protocol(
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
            CREATE TABLE IF NOT EXISTS prospective_evaluation_run(
                id TEXT PRIMARY KEY,
                protocol_id TEXT NOT NULL,
                client_request_id TEXT NOT NULL UNIQUE,
                evaluation_version TEXT NOT NULL,
                status TEXT NOT NULL,
                source_capture_count INTEGER NOT NULL DEFAULT 0,
                source_sample_count INTEGER NOT NULL DEFAULT 0,
                development_count INTEGER NOT NULL DEFAULT 0,
                holdout_count INTEGER NOT NULL DEFAULT 0,
                purged_count INTEGER NOT NULL DEFAULT 0,
                mature_count INTEGER NOT NULL DEFAULT 0,
                immature_count INTEGER NOT NULL DEFAULT 0,
                excluded_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                processed_count INTEGER NOT NULL DEFAULT 0,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                restart_count INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(protocol_id)
                    REFERENCES prospective_evaluation_protocol(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prospective_evaluation_unit(
                evaluation_run_id TEXT NOT NULL,
                capture_run_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                split TEXT NOT NULL,
                maturity_status TEXT NOT NULL,
                exclusion_reason TEXT,
                signal_date TEXT,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                strategy TEXT,
                available_trading_days INTEGER NOT NULL DEFAULT 0,
                evaluated_through TEXT,
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                mfe_pct REAL,
                mae_pct REAL,
                entry_comparable INTEGER NOT NULL DEFAULT 0,
                entry_touched INTEGER NOT NULL DEFAULT 0,
                stop_comparable INTEGER NOT NULL DEFAULT 0,
                stop_touched INTEGER NOT NULL DEFAULT 0,
                target1_comparable INTEGER NOT NULL DEFAULT 0,
                target1_touched INTEGER NOT NULL DEFAULT 0,
                target2_comparable INTEGER NOT NULL DEFAULT 0,
                target2_touched INTEGER NOT NULL DEFAULT 0,
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
                details_json TEXT NOT NULL,
                computed_at TEXT NOT NULL,
                PRIMARY KEY(evaluation_run_id,capture_run_id,sample_index),
                FOREIGN KEY(evaluation_run_id)
                    REFERENCES prospective_evaluation_run(id) ON DELETE CASCADE,
                FOREIGN KEY(capture_run_id,sample_index)
                    REFERENCES prospective_recommendation_sample(capture_run_id,sample_index)
                    ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prospective_evaluation_report(
                id TEXT PRIMARY KEY,
                evaluation_run_id TEXT NOT NULL UNIQUE,
                report_version TEXT NOT NULL,
                source_set_hash TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(evaluation_run_id)
                    REFERENCES prospective_evaluation_run(id) ON DELETE CASCADE
            )
            """
        )

        for table in TABLE_COLUMNS:
            _require_columns(conn, table)

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_prospective_capture_source
            ON prospective_capture_run(source_execution_key,status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_prospective_sample_signal
            ON prospective_recommendation_sample(signal_date,market,strategy)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_prospective_eval_run_protocol
            ON prospective_evaluation_run(protocol_id,created_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_prospective_eval_unit_split
            ON prospective_evaluation_unit(evaluation_run_id,split,maturity_status)
            """
        )

        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_prospective_sample_immutable
            BEFORE UPDATE ON prospective_recommendation_sample
            BEGIN
                SELECT RAISE(ABORT, 'Prospective recommendation sample is immutable');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_prospective_protocol_immutable
            BEFORE UPDATE ON prospective_evaluation_protocol
            BEGIN
                SELECT RAISE(ABORT, 'Prospective evaluation protocol is immutable');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_prospective_report_immutable
            BEFORE UPDATE ON prospective_evaluation_report
            BEGIN
                SELECT RAISE(ABORT, 'Prospective evaluation report is immutable');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_prospective_capture_terminal_immutable
            BEFORE UPDATE ON prospective_capture_run
            WHEN OLD.status IN ('COMPLETE','DUPLICATE','FAILED','CANCELLED','INTERRUPTED')
            BEGIN
                SELECT RAISE(ABORT, 'Terminal prospective capture is immutable');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_prospective_eval_completed_immutable
            BEFORE UPDATE ON prospective_evaluation_run
            WHEN OLD.status='COMPLETED'
            BEGIN
                SELECT RAISE(ABORT, 'Completed prospective evaluation run is immutable');
            END
            """
        )

        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise DataToolError(
                f"Prospective migration FK 검증 실패: {len(fk_errors)}건"
            )
        conn.commit()
        return {
            "schema_version": PROSPECTIVE_SCHEMA_VERSION,
            "tables": [
                "prospective_capture_run",
                "prospective_recommendation_sample",
                "prospective_evaluation_protocol",
                "prospective_evaluation_run",
                "prospective_evaluation_unit",
                "prospective_evaluation_report",
            ],
            "source_state": source_state,
            "historical_backfill_performed": False,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_prospective(*, simulation_db: Path | None = None) -> dict[str, object]:
    return migrate_prospective_store(Path(simulation_db or simulation_db_path()))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VN-P2-S2 prospective 추천/평가 schema를 명시적으로 생성합니다."
    )
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_prospective(simulation_db=args.simulation_db)
        print("VN-P2-S2 PROSPECTIVE MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
