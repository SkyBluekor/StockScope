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

from app.holdings.decision_support import HOLDING_DECISION_SCHEMA_VERSION
from app.watch.policy import WATCH_POLICY_CONTRACT_VERSION
from app.watch.storage import WATCH_SCHEMA_VERSION, WATCH_TABLES
from tools.data.common import DataToolError, holdings_db_path, sqlite_readonly


REQUIRED_BASE_TABLES = {
    "holding_position",
    "holding_management_plan",
    "holding_decision_schema_meta",
}

TABLE_COLUMNS: dict[str, set[str]] = {
    "holding_watch_setting": {
        "id",
        "position_id",
        "plan_id",
        "plan_version",
        "enabled",
        "policy_version",
        "policy_contract_version",
        "status",
        "disabled_reason",
        "created_at",
        "updated_at",
    },
    "holding_watch_rule": {
        "id",
        "setting_id",
        "position_id",
        "plan_id",
        "plan_version",
        "rule_kind",
        "direction",
        "threshold_price",
        "policy_version",
        "confirmation_observations",
        "rearm_observations",
        "rearm_distance_bps",
        "max_quote_age_seconds",
        "state",
        "confirmation_count",
        "rearm_count",
        "last_observed_at",
        "last_price",
        "status",
        "closed_at",
        "created_at",
        "updated_at",
    },
    "holding_watch_episode": {
        "id",
        "rule_id",
        "setting_id",
        "position_id",
        "plan_id",
        "plan_version",
        "episode_no",
        "status",
        "opened_at",
        "confirmed_at",
        "resolved_at",
        "resolution_reason",
        "trigger_price",
        "confirmed_price",
        "created_at",
        "updated_at",
    },
    "holding_watch_coverage_gap": {
        "id",
        "setting_id",
        "position_id",
        "reason_code",
        "status",
        "started_at",
        "ended_at",
        "detail_json",
        "created_at",
        "updated_at",
    },
    "holding_watch_notification_outbox": {
        "id",
        "episode_id",
        "rule_id",
        "setting_id",
        "position_id",
        "plan_id",
        "notification_type",
        "delivery_status",
        "payload_json",
        "created_at",
        "delivered_at",
        "read_at",
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
                "VN-P4-S1 선행 Holdings/P3-S1 테이블이 없습니다: "
                + ", ".join(missing)
            )

        p3s1 = conn.execute(
            """
            SELECT value FROM holding_decision_schema_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if p3s1 is None or str(p3s1[0]) != HOLDING_DECISION_SCHEMA_VERSION:
            raise DataToolError(
                "VN-P3-S1 Holdings decision migration이 완료되지 않았습니다."
            )

        return {
            "position_count": int(
                conn.execute("SELECT COUNT(*) FROM holding_position").fetchone()[0]
            ),
            "open_position_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM holding_position WHERE status='OPEN'"
                ).fetchone()[0]
            ),
            "management_plan_count": int(
                conn.execute("SELECT COUNT(*) FROM holding_management_plan").fetchone()[0]
            ),
            "active_plan_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM holding_management_plan WHERE status='ACTIVE'"
                ).fetchone()[0]
            ),
        }


def _require_columns(conn: sqlite3.Connection, table: str) -> None:
    missing = sorted(TABLE_COLUMNS[table] - _columns(conn, table))
    if missing:
        raise DataToolError(
            f"{table} schema가 VN-P4-S1과 호환되지 않습니다: "
            + ", ".join(missing)
        )


def migrate_watch_store(path: Path) -> dict[str, object]:
    path = Path(path)
    source_state = _inspect_holdings_db(path)
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_watch_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            """
            SELECT value FROM holding_watch_schema_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO holding_watch_schema_meta(key,value)
                VALUES('schema_version',?)
                """,
                (WATCH_SCHEMA_VERSION,),
            )
            conn.execute(
                """
                INSERT INTO holding_watch_schema_meta(key,value)
                VALUES('policy_contract_version',?)
                """,
                (WATCH_POLICY_CONTRACT_VERSION,),
            )
        elif str(row[0]) != WATCH_SCHEMA_VERSION:
            raise DataToolError(
                f"지원하지 않는 Watch schema version입니다: {row[0]}"
            )

        contract_row = conn.execute(
            """
            SELECT value FROM holding_watch_schema_meta
            WHERE key='policy_contract_version'
            """
        ).fetchone()
        if (
            contract_row is None
            or str(contract_row[0]) != WATCH_POLICY_CONTRACT_VERSION
        ):
            raise DataToolError(
                "Watch policy contract version이 지원 범위와 다릅니다."
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_watch_setting(
                id TEXT PRIMARY KEY,
                position_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL CHECK(plan_version >= 1),
                enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                policy_version TEXT NOT NULL,
                policy_contract_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('ACTIVE','DISABLED')),
                disabled_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (status='ACTIVE' AND enabled=1 AND disabled_reason IS NULL)
                    OR
                    (status='DISABLED' AND enabled=0)
                ),
                FOREIGN KEY(position_id)
                    REFERENCES holding_position(id) ON DELETE RESTRICT,
                FOREIGN KEY(plan_id)
                    REFERENCES holding_management_plan(id) ON DELETE RESTRICT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_watch_rule(
                id TEXT PRIMARY KEY,
                setting_id TEXT NOT NULL,
                position_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL CHECK(plan_version >= 1),
                rule_kind TEXT NOT NULL CHECK(rule_kind IN (
                    'STOP','TARGET1','TARGET2'
                )),
                direction TEXT NOT NULL CHECK(direction IN (
                    'BELOW_OR_EQUAL','ABOVE_OR_EQUAL'
                )),
                threshold_price TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                confirmation_observations INTEGER NOT NULL
                    CHECK(confirmation_observations >= 1),
                rearm_observations INTEGER NOT NULL
                    CHECK(rearm_observations >= 1),
                rearm_distance_bps INTEGER NOT NULL
                    CHECK(rearm_distance_bps > 0),
                max_quote_age_seconds REAL NOT NULL
                    CHECK(max_quote_age_seconds > 0),
                state TEXT NOT NULL CHECK(state IN (
                    'ARMED','PENDING_CONFIRMATION','CONFIRMED',
                    'RESOLVED','DISABLED'
                )),
                confirmation_count INTEGER NOT NULL DEFAULT 0
                    CHECK(confirmation_count >= 0),
                rearm_count INTEGER NOT NULL DEFAULT 0
                    CHECK(rearm_count >= 0),
                last_observed_at TEXT,
                last_price TEXT,
                status TEXT NOT NULL CHECK(status IN ('ACTIVE','CLOSED')),
                closed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (status='ACTIVE' AND closed_at IS NULL)
                    OR
                    (status='CLOSED' AND closed_at IS NOT NULL)
                ),
                CHECK(
                    (rule_kind='STOP' AND direction='BELOW_OR_EQUAL')
                    OR
                    (rule_kind IN ('TARGET1','TARGET2')
                        AND direction='ABOVE_OR_EQUAL')
                ),
                UNIQUE(setting_id,rule_kind),
                FOREIGN KEY(setting_id)
                    REFERENCES holding_watch_setting(id) ON DELETE RESTRICT,
                FOREIGN KEY(position_id)
                    REFERENCES holding_position(id) ON DELETE RESTRICT,
                FOREIGN KEY(plan_id)
                    REFERENCES holding_management_plan(id) ON DELETE RESTRICT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_watch_episode(
                id TEXT PRIMARY KEY,
                rule_id TEXT NOT NULL,
                setting_id TEXT NOT NULL,
                position_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL CHECK(plan_version >= 1),
                episode_no INTEGER NOT NULL CHECK(episode_no >= 1),
                status TEXT NOT NULL CHECK(status IN (
                    'OPEN','RESOLVED','INVALIDATED'
                )),
                opened_at TEXT NOT NULL,
                confirmed_at TEXT,
                resolved_at TEXT,
                resolution_reason TEXT,
                trigger_price TEXT NOT NULL,
                confirmed_price TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (status='OPEN' AND resolved_at IS NULL)
                    OR
                    (status IN ('RESOLVED','INVALIDATED')
                        AND resolved_at IS NOT NULL)
                ),
                UNIQUE(rule_id,episode_no),
                FOREIGN KEY(rule_id)
                    REFERENCES holding_watch_rule(id) ON DELETE RESTRICT,
                FOREIGN KEY(setting_id)
                    REFERENCES holding_watch_setting(id) ON DELETE RESTRICT,
                FOREIGN KEY(position_id)
                    REFERENCES holding_position(id) ON DELETE RESTRICT,
                FOREIGN KEY(plan_id)
                    REFERENCES holding_management_plan(id) ON DELETE RESTRICT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_watch_coverage_gap(
                id TEXT PRIMARY KEY,
                setting_id TEXT NOT NULL,
                position_id TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED')),
                started_at TEXT NOT NULL,
                ended_at TEXT,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (status='OPEN' AND ended_at IS NULL)
                    OR
                    (status='CLOSED' AND ended_at IS NOT NULL)
                ),
                FOREIGN KEY(setting_id)
                    REFERENCES holding_watch_setting(id) ON DELETE RESTRICT,
                FOREIGN KEY(position_id)
                    REFERENCES holding_position(id) ON DELETE RESTRICT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holding_watch_notification_outbox(
                id TEXT PRIMARY KEY,
                episode_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                setting_id TEXT NOT NULL,
                position_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                notification_type TEXT NOT NULL CHECK(notification_type IN (
                    'WATCH_RULE_CONFIRMED'
                )),
                delivery_status TEXT NOT NULL CHECK(delivery_status IN (
                    'PENDING','DELIVERED'
                )),
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                delivered_at TEXT,
                read_at TEXT,
                UNIQUE(episode_id,notification_type),
                FOREIGN KEY(episode_id)
                    REFERENCES holding_watch_episode(id) ON DELETE RESTRICT,
                FOREIGN KEY(rule_id)
                    REFERENCES holding_watch_rule(id) ON DELETE RESTRICT,
                FOREIGN KEY(setting_id)
                    REFERENCES holding_watch_setting(id) ON DELETE RESTRICT,
                FOREIGN KEY(position_id)
                    REFERENCES holding_position(id) ON DELETE RESTRICT,
                FOREIGN KEY(plan_id)
                    REFERENCES holding_management_plan(id) ON DELETE RESTRICT
            )
            """
        )

        for table in TABLE_COLUMNS:
            _require_columns(conn, table)

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_holding_watch_active_position
            ON holding_watch_setting(position_id)
            WHERE status='ACTIVE'
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_holding_watch_setting_plan
            ON holding_watch_setting(plan_id,plan_version)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_holding_watch_rule_setting_state
            ON holding_watch_rule(setting_id,status,state)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_holding_watch_open_episode
            ON holding_watch_episode(rule_id)
            WHERE status='OPEN'
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_holding_watch_episode_position
            ON holding_watch_episode(position_id,created_at DESC)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_holding_watch_open_gap
            ON holding_watch_coverage_gap(setting_id,reason_code)
            WHERE status='OPEN'
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_holding_watch_notification_position
            ON holding_watch_notification_outbox(position_id,created_at DESC)
            """
        )

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            raise DataToolError(
                f"VN-P4-S1 migration FK 검증 실패: {len(fk)}건"
            )

        conn.commit()
        return {
            "schema_version": WATCH_SCHEMA_VERSION,
            "policy_contract_version": WATCH_POLICY_CONTRACT_VERSION,
            "tables": sorted(WATCH_TABLES),
            "source_state": source_state,
            "historical_watch_backfill_performed": False,
            "production_watch_activation_performed": False,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_watch(*, holdings_db: Path | None = None) -> dict[str, object]:
    return migrate_watch_store(Path(holdings_db or holdings_db_path()))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "VN-P4-S1 Watch 영속 schema를 명시적으로 생성합니다. "
            "기존 Position/Plan을 자동 감시 상태로 backfill하지 않습니다."
        )
    )
    parser.add_argument("--holdings-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_watch(holdings_db=args.holdings_db)
        print("VN-P4-S1 WATCH MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
