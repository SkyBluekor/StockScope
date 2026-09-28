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


RECOVERY_SCHEMA_VERSION = "VN_P3_S2_RECOVERY_REVIEW_V1"
P3S1_SCHEMA_VERSION = "VN_P3_S1_HOLDING_DECISION_STORAGE_V1"

RECOVERY_TABLES = (
    "holding_recovery_schema_meta",
    "holding_recovery_review",
    "holding_recovery_assessment",
)

REQUIRED_BASE_TABLES = {
    "holding_position",
    "stock_analysis_day",
    "stock_analysis_revision",
    "holding_management_plan",
    "holding_decision_schema_meta",
    "holding_decision_record",
}

TABLE_COLUMNS: dict[str, set[str]] = {
    "holding_recovery_review": {
        "id",
        "position_id",
        "status",
        "opened_at",
        "opened_note",
        "closed_at",
        "close_reason",
        "close_note",
        "created_at",
        "updated_at",
    },
    "holding_recovery_assessment": {
        "id",
        "review_id",
        "position_id",
        "thesis_state",
        "review_action",
        "reason_note",
        "source_analysis_revision_id",
        "source_active_plan_id",
        "source_active_plan_version",
        "source_position_status",
        "source_position_quantity",
        "source_position_average_price",
        "valuation_market_date",
        "valuation_price",
        "unrealized_pnl",
        "unrealized_return_pct",
        "linked_decision_id",
        "limitations_json",
        "evidence_json",
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
                "VN-P3-S2 선행 Holdings/P3-S1 테이블이 없습니다: "
                + ", ".join(missing)
            )

        p3s1 = conn.execute(
            """
            SELECT value FROM holding_decision_schema_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if p3s1 is None or str(p3s1[0]) != P3S1_SCHEMA_VERSION:
            raise DataToolError(
                "VN-P3-S1 Holdings decision migration이 완료되지 않았습니다."
            )

        return {
            "position_count": int(
                conn.execute("SELECT COUNT(*) FROM holding_position").fetchone()[0]
            ),
            "decision_count": int(
                conn.execute("SELECT COUNT(*) FROM holding_decision_record").fetchone()[0]
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
            f"{table} schema가 VN-P3-S2와 호환되지 않습니다: "
            + ", ".join(missing)
        )


def migrate_holdings_recovery_store(path: Path) -> dict[str, object]:
    path = Path(path)
    source_state = _inspect_holdings_db(path)
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_recovery_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            """
            SELECT value FROM holding_recovery_schema_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO holding_recovery_schema_meta(key,value)
                VALUES('schema_version',?)
                """,
                (RECOVERY_SCHEMA_VERSION,),
            )
        elif str(row[0]) != RECOVERY_SCHEMA_VERSION:
            raise DataToolError(
                f"지원하지 않는 Recovery schema version입니다: {row[0]}"
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_recovery_review(
                id TEXT PRIMARY KEY,
                position_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED')),
                opened_at TEXT NOT NULL,
                opened_note TEXT,
                closed_at TEXT,
                close_reason TEXT,
                close_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (status='OPEN' AND closed_at IS NULL)
                    OR
                    (status='CLOSED' AND closed_at IS NOT NULL)
                ),
                FOREIGN KEY(position_id)
                    REFERENCES holding_position(id) ON DELETE RESTRICT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_recovery_assessment(
                id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL,
                position_id TEXT NOT NULL,
                thesis_state TEXT NOT NULL CHECK(thesis_state IN (
                    'INTACT','WEAKENED','BROKEN','UNKNOWN'
                )),
                review_action TEXT NOT NULL CHECK(review_action IN (
                    'UNDECIDED','HOLD','REDUCE','EXIT','ADD_REVIEW'
                )),
                reason_note TEXT,
                source_analysis_revision_id TEXT,
                source_active_plan_id TEXT,
                source_active_plan_version INTEGER,
                source_position_status TEXT NOT NULL,
                source_position_quantity TEXT NOT NULL,
                source_position_average_price TEXT,
                valuation_market_date TEXT,
                valuation_price TEXT,
                unrealized_pnl TEXT,
                unrealized_return_pct TEXT,
                linked_decision_id TEXT,
                limitations_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(review_id)
                    REFERENCES holding_recovery_review(id) ON DELETE RESTRICT,
                FOREIGN KEY(position_id)
                    REFERENCES holding_position(id) ON DELETE RESTRICT,
                FOREIGN KEY(source_analysis_revision_id)
                    REFERENCES stock_analysis_revision(id) ON DELETE RESTRICT,
                FOREIGN KEY(source_active_plan_id)
                    REFERENCES holding_management_plan(id) ON DELETE RESTRICT,
                FOREIGN KEY(linked_decision_id)
                    REFERENCES holding_decision_record(id) ON DELETE RESTRICT
            )
            """
        )

        for table in TABLE_COLUMNS:
            _require_columns(conn, table)

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_holding_recovery_open_position
            ON holding_recovery_review(position_id)
            WHERE status='OPEN'
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_holding_recovery_position_created
            ON holding_recovery_review(position_id,created_at DESC,id DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_holding_recovery_assessment_review
            ON holding_recovery_assessment(review_id,created_at,id)
            """
        )

        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_holding_recovery_review_update_guard
            BEFORE UPDATE ON holding_recovery_review
            WHEN
                OLD.position_id <> NEW.position_id
                OR OLD.opened_at <> NEW.opened_at
                OR COALESCE(OLD.opened_note,'') <> COALESCE(NEW.opened_note,'')
                OR OLD.created_at <> NEW.created_at
                OR OLD.status <> 'OPEN'
                OR NEW.status <> 'CLOSED'
                OR NEW.closed_at IS NULL
            BEGIN
                SELECT RAISE(ABORT, 'holding_recovery_review lifecycle is immutable except OPEN->CLOSED');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_holding_recovery_review_no_delete
            BEFORE DELETE ON holding_recovery_review
            BEGIN
                SELECT RAISE(ABORT, 'holding_recovery_review cannot be deleted');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_holding_recovery_assessment_no_update
            BEFORE UPDATE ON holding_recovery_assessment
            BEGIN
                SELECT RAISE(ABORT, 'holding_recovery_assessment is append-only');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_holding_recovery_assessment_no_delete
            BEFORE DELETE ON holding_recovery_assessment
            BEGIN
                SELECT RAISE(ABORT, 'holding_recovery_assessment is append-only');
            END
            """
        )

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            raise DataToolError(
                f"VN-P3-S2 migration FK 검증 실패: {len(fk)}건"
            )

        conn.commit()
        return {
            "schema_version": RECOVERY_SCHEMA_VERSION,
            "tables": list(RECOVERY_TABLES),
            "source_state": source_state,
            "historical_recovery_backfill_performed": False,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_holdings_recovery(
    *,
    holdings_db: Path | None = None,
) -> dict[str, object]:
    return migrate_holdings_recovery_store(
        Path(holdings_db or holdings_db_path())
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VN-P3-S2 Holdings Recovery review schema를 명시적으로 생성합니다."
    )
    parser.add_argument("--holdings-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_holdings_recovery(
            holdings_db=args.holdings_db,
        )
        print("VN-P3-S2 HOLDING RECOVERY MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
