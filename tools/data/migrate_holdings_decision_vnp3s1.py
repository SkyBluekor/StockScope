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

from tools.data.common import DataToolError, holdings_db_path, sqlite_readonly

HOLDING_DECISION_SCHEMA_VERSION = "VN_P3_S1_HOLDING_DECISION_STORAGE_V1"
HOLDING_DECISION_POLICY_VERSION = "VN_P3_S1_HOLDING_DECISION_POLICY_V1"
HOLDING_PLAN_CONTEXT_VERSION = "VN_P3_S1_PLAN_CONTEXT_V1"

DECISION_TABLES = (
    "holding_decision_schema_meta",
    "holding_decision_record",
    "holding_decision_resolution",
    "holding_management_plan_context_vnp3s1",
)

REQUIRED_BASE_TABLES = {
    "holding_position",
    "stock_analysis_day",
    "stock_analysis_revision",
    "holding_management_plan",
}

TABLE_COLUMNS: dict[str, set[str]] = {
    "holding_decision_record": {
        "id","position_id","decision_policy_version","status","primary_action",
        "source_analysis_revision_id","source_active_plan_id","source_active_plan_version",
        "source_position_status","source_position_quantity","source_position_average_price",
        "valuation_market_date","valuation_price","valuation_source",
        "horizon_intent","horizon_policy_version","input_fingerprint",
        "evidence_json","alternatives_json","limitations_json","created_at",
    },
    "holding_decision_resolution": {
        "id","decision_id","selected_action","resolution_type","note",
        "resulting_plan_id","created_at",
    },
    "holding_management_plan_context_vnp3s1": {
        "plan_id","context_version","source_decision_id","selected_action",
        "review_cycle_trading_days","time_stop_trading_days",
        "adjustment_context_json","created_at",
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


def _inspect_holdings_db(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise DataToolError(f"Holdings DB를 찾을 수 없습니다: {path}")
    with sqlite_readonly(path) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        if row is None or str(row[0]).lower() != "ok":
            raise DataToolError("Holdings DB integrity_check에 실패했습니다.")
        tables = _table_names(conn)
        missing = sorted(REQUIRED_BASE_TABLES - tables)
        if missing:
            raise DataToolError(
                "P3-S1 선행 Holdings 테이블이 없습니다: " + ", ".join(missing)
            )
        return {
            "position_count": int(
                conn.execute("SELECT COUNT(*) FROM holding_position").fetchone()[0]
            ),
            "analysis_revision_count": int(
                conn.execute("SELECT COUNT(*) FROM stock_analysis_revision").fetchone()[0]
            ),
            "management_plan_count": int(
                conn.execute("SELECT COUNT(*) FROM holding_management_plan").fetchone()[0]
            ),
        }


def _require_columns(conn: sqlite3.Connection, table: str) -> None:
    missing = sorted(TABLE_COLUMNS[table] - _columns(conn, table))
    if missing:
        raise DataToolError(
            f"{table} schema가 VN-P3-S1과 호환되지 않습니다: "
            + ", ".join(missing)
        )


def migrate_holdings_decision_store(path: Path) -> dict[str, object]:
    path = Path(path)
    source_state = _inspect_holdings_db(path)
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_decision_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT value FROM holding_decision_schema_meta WHERE key='schema_version'"
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO holding_decision_schema_meta(key,value)
                VALUES('schema_version',?)
                """,
                (HOLDING_DECISION_SCHEMA_VERSION,),
            )
        elif str(row[0]) != HOLDING_DECISION_SCHEMA_VERSION:
            raise DataToolError(
                f"지원하지 않는 holding decision schema version입니다: {row[0]}"
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_decision_record(
                id TEXT PRIMARY KEY,
                position_id TEXT NOT NULL,
                decision_policy_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'ACTIONABLE','REVIEW_REQUIRED','DEFERRED',
                    'INSUFFICIENT_DATA','CONFLICT'
                )),
                primary_action TEXT CHECK(primary_action IN (
                    'HOLD','ADD','REDUCE','TAKE_PROFIT','STOP','EXIT'
                ) OR primary_action IS NULL),
                source_analysis_revision_id TEXT,
                source_active_plan_id TEXT,
                source_active_plan_version INTEGER,
                source_position_status TEXT NOT NULL,
                source_position_quantity TEXT NOT NULL,
                source_position_average_price TEXT,
                valuation_market_date TEXT,
                valuation_price TEXT,
                valuation_source TEXT,
                horizon_intent TEXT,
                horizon_policy_version TEXT,
                input_fingerprint TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                alternatives_json TEXT NOT NULL,
                limitations_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(position_id)
                    REFERENCES holding_position(id) ON DELETE RESTRICT,
                FOREIGN KEY(source_analysis_revision_id)
                    REFERENCES stock_analysis_revision(id) ON DELETE RESTRICT,
                FOREIGN KEY(source_active_plan_id)
                    REFERENCES holding_management_plan(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_decision_resolution(
                id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                selected_action TEXT CHECK(selected_action IN (
                    'HOLD','ADD','REDUCE','TAKE_PROFIT','STOP','EXIT'
                ) OR selected_action IS NULL),
                resolution_type TEXT NOT NULL CHECK(resolution_type IN (
                    'KEEP_CURRENT_PLAN','APPLY_NEW_PLAN','ACKNOWLEDGED','DEFERRED'
                )),
                note TEXT,
                resulting_plan_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(decision_id)
                    REFERENCES holding_decision_record(id) ON DELETE RESTRICT,
                FOREIGN KEY(resulting_plan_id)
                    REFERENCES holding_management_plan(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_management_plan_context_vnp3s1(
                plan_id TEXT PRIMARY KEY,
                context_version TEXT NOT NULL,
                source_decision_id TEXT NOT NULL,
                selected_action TEXT CHECK(selected_action IN (
                    'HOLD','ADD','REDUCE','TAKE_PROFIT','STOP','EXIT'
                ) OR selected_action IS NULL),
                review_cycle_trading_days INTEGER,
                time_stop_trading_days INTEGER,
                adjustment_context_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(plan_id)
                    REFERENCES holding_management_plan(id) ON DELETE RESTRICT,
                FOREIGN KEY(source_decision_id)
                    REFERENCES holding_decision_record(id) ON DELETE RESTRICT
            )
            """
        )

        for table in TABLE_COLUMNS:
            _require_columns(conn, table)

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_holding_decision_position_created
            ON holding_decision_record(position_id,created_at DESC,id DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_holding_decision_input
            ON holding_decision_record(position_id,input_fingerprint,created_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_holding_decision_resolution_decision
            ON holding_decision_resolution(decision_id,created_at,id)
            """
        )

        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_holding_decision_record_no_update
            BEFORE UPDATE ON holding_decision_record
            BEGIN
                SELECT RAISE(ABORT, 'holding_decision_record is append-only');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_holding_decision_record_no_delete
            BEFORE DELETE ON holding_decision_record
            BEGIN
                SELECT RAISE(ABORT, 'holding_decision_record is append-only');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_holding_decision_resolution_no_update
            BEFORE UPDATE ON holding_decision_resolution
            BEGIN
                SELECT RAISE(ABORT, 'holding_decision_resolution is append-only');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_holding_decision_resolution_no_delete
            BEFORE DELETE ON holding_decision_resolution
            BEGIN
                SELECT RAISE(ABORT, 'holding_decision_resolution is append-only');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_holding_plan_context_no_update
            BEFORE UPDATE ON holding_management_plan_context_vnp3s1
            BEGIN
                SELECT RAISE(ABORT, 'holding_management_plan_context_vnp3s1 is append-only');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_holding_plan_context_no_delete
            BEFORE DELETE ON holding_management_plan_context_vnp3s1
            BEGIN
                SELECT RAISE(ABORT, 'holding_management_plan_context_vnp3s1 is append-only');
            END
            """
        )

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            raise DataToolError(
                f"P3-S1 migration FK 검증 실패: {len(fk)}건"
            )
        conn.commit()
        return {
            "schema_version": HOLDING_DECISION_SCHEMA_VERSION,
            "decision_policy_version": HOLDING_DECISION_POLICY_VERSION,
            "plan_context_version": HOLDING_PLAN_CONTEXT_VERSION,
            "tables": list(DECISION_TABLES),
            "source_state": source_state,
            "historical_decision_backfill_performed": False,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_holdings_decision(
    *,
    holdings_db: Path | None = None,
) -> dict[str, object]:
    return migrate_holdings_decision_store(
        Path(holdings_db or holdings_db_path())
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VN-P3-S1 Holdings decision-support schema를 명시적으로 생성합니다."
    )
    parser.add_argument("--holdings-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_holdings_decision(
            holdings_db=args.holdings_db,
        )
        print("VN-P3-S1 HOLDING DECISION MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
