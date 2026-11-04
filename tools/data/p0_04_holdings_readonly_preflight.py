"""P0-04: inspect actual Windows Holdings/Market SQLite without modifying either.

Stdlib-only operational preflight. No HoldingsCatalog.initialize(), migrations,
HTTP server, KIS/TypeSafe/JEV/KRX requests, DB backups or plan application.
No account identifiers, ticker codes, positions, quantities or prices are printed.
The report is evidence of stored local state, NOT approval of a live plan.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Any

VERSION = "STOCKSCOPE_P0_04_HOLDINGS_READONLY_PREFLIGHT_V1"

BASE_TABLES = frozenset({
    "monitored_stock", "position_account", "holding_position",
    "holding_position_event", "stock_analysis_day", "stock_analysis_revision",
    "holding_management_plan",
})
SCHEMA_GROUPS = {
    "decision": (
        frozenset({
            "holding_decision_schema_meta", "holding_decision_record",
            "holding_decision_resolution", "holding_management_plan_context_vnp3s1",
        }),
        "holding_decision_schema_meta", "VN_P3_S1_HOLDING_DECISION_STORAGE_V1",
    ),
    "recovery": (
        frozenset({
            "holding_recovery_schema_meta", "holding_recovery_review",
            "holding_recovery_assessment",
        }),
        "holding_recovery_schema_meta", "VN_P3_S2_RECOVERY_REVIEW_V1",
    ),
    "watch": (
        frozenset({
            "holding_watch_schema_meta", "holding_watch_setting",
            "holding_watch_rule", "holding_watch_episode",
            "holding_watch_coverage_gap", "holding_watch_notification_outbox",
        }),
        "holding_watch_schema_meta", "VN_P4_S1_WATCH_V1",
    ),
}
# Verify minimal columns before querying; do not infer a healthy schema solely
# from CREATE TABLE names and do not execute any migration to repair it.
REQUIRED_COLUMNS = {
    "holding_position": {"id", "status", "monitored_stock_id", "position_account_id"},
    "holding_management_plan": {
        "id", "position_id", "status", "plan_version", "source_analysis_revision_id",
    },
    "stock_analysis_day": {"id", "monitored_stock_id", "current_revision_id"},
    "stock_analysis_revision": {"id", "analysis_day_id"},
    "holding_decision_record": {"id", "position_id"},
    "holding_decision_resolution": {"id", "decision_id", "resulting_plan_id"},
    "holding_recovery_review": {"id", "position_id"},
    "holding_watch_setting": {"id", "position_id"},
}
MARKET_TABLES = frozenset({"day_status", "stock_daily", "main_index_daily"})


def _blocked(status: str) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "operational_db_read_only": True,
        "db_write_calls": 0,
        "external_requests": 0,
        "actual_plan_applied": False,
        "live_account_verified": False,
        "latest_official_eod_verified": False,
    }


def _connect_readonly(path: Path) -> sqlite3.Connection:
    # Do not use immutable=1; a live SQLite WAL could contain committed data.
    # mode=ro prevents modifications to the underlying SQLite main database.
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        conn.close()
        raise


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0]) for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    # All table names originate from the fixed REQUIRED_COLUMNS dictionary.
    return {
        str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")
    }


def _schema_family(conn: sqlite3.Connection, tables: set[str], family: str) -> dict[str, Any]:
    required, meta, expected = SCHEMA_GROUPS[family]
    found = required & tables
    if not found:
        return {"status": "MIGRATION_REQUIRED", "present_tables": 0, "expected_tables": len(required)}
    if found != required:
        return {
            "status": "PARTIAL_SCHEMA_REVIEW_REQUIRED",
            "present_tables": len(found),
            "expected_tables": len(required),
        }
    for table in required:
        columns = REQUIRED_COLUMNS.get(table)
        if columns and not columns.issubset(_columns(conn, table)):
            return {
                "status": "SCHEMA_UNSUPPORTED",
                "present_tables": len(found),
                "expected_tables": len(required),
            }
    try:
        row = conn.execute(
            f"SELECT value FROM {meta} WHERE key='schema_version'"
        ).fetchone()
    except sqlite3.DatabaseError:
        return {
            "status": "SCHEMA_UNSUPPORTED",
            "present_tables": len(found),
            "expected_tables": len(required),
        }
    return {
        "status": "READY" if row is not None and str(row[0]) == expected else "SCHEMA_UNSUPPORTED",
        "present_tables": len(found),
        "expected_tables": len(required),
    }


def inspect_holdings_environment(holdings_db: Path, market_db: Path) -> dict[str, Any]:
    """Aggregate the persisted state with SQLite mode=ro; no catalog initialization."""
    base = _blocked("BLOCKED_HOLDINGS_DB_MISSING")
    if not holdings_db.is_file():
        return base
    if not market_db.is_file():
        return {**base, "status": "BLOCKED_MARKET_DB_MISSING"}

    try:
        with closing(_connect_readonly(holdings_db)) as hconn:
            if str(hconn.execute("PRAGMA quick_check(1)").fetchone()[0]).lower() != "ok":
                return {**base, "status": "BLOCKED_HOLDINGS_INTEGRITY"}
            tables = _tables(hconn)
            missing = BASE_TABLES - tables
            if missing:
                return {
                    **base, "status": "BLOCKED_HOLDINGS_BASE_SCHEMA_MISSING",
                    "missing_base_tables": sorted(missing),
                }
            bad_columns = sorted(
                name for name in BASE_TABLES
                if REQUIRED_COLUMNS.get(name)
                and not REQUIRED_COLUMNS[name].issubset(_columns(hconn, name))
            )
            if bad_columns:
                return {
                    **base, "status": "BLOCKED_HOLDINGS_BASE_SCHEMA_UNSUPPORTED",
                    "affected_tables": bad_columns,
                }

            domain_status = {
                name: _schema_family(hconn, tables, name)
                for name in SCHEMA_GROUPS
            }
            counts = {
                "registered_accounts": int(hconn.execute(
                    "SELECT COUNT(*) FROM position_account"
                ).fetchone()[0]),
                "monitored_stocks": int(hconn.execute(
                    "SELECT COUNT(*) FROM monitored_stock"
                ).fetchone()[0]),
                "open_positions": int(hconn.execute(
                    "SELECT COUNT(*) FROM holding_position WHERE status='OPEN'"
                ).fetchone()[0]),
                "closed_positions": int(hconn.execute(
                    "SELECT COUNT(*) FROM holding_position WHERE status='CLOSED'"
                ).fetchone()[0]),
                "ledger_events": int(hconn.execute(
                    "SELECT COUNT(*) FROM holding_position_event"
                ).fetchone()[0]),
                "active_plans": int(hconn.execute(
                    "SELECT COUNT(*) FROM holding_management_plan WHERE status='ACTIVE'"
                ).fetchone()[0]),
                "analysis_revisions": int(hconn.execute(
                    "SELECT COUNT(*) FROM stock_analysis_revision"
                ).fetchone()[0]),
            }
            consistency = {
                "active_plan_for_closed_position": int(hconn.execute(
                    "SELECT COUNT(*) FROM holding_management_plan p "
                    "JOIN holding_position h ON h.id=p.position_id "
                    "WHERE p.status='ACTIVE' AND h.status<>'OPEN'"
                ).fetchone()[0]),
                "multiple_active_plans_per_position": int(hconn.execute(
                    "SELECT COUNT(*) FROM (SELECT position_id FROM holding_management_plan "
                    "WHERE status='ACTIVE' GROUP BY position_id HAVING COUNT(*)>1)"
                ).fetchone()[0]),
                "active_plans_for_missing_position": int(hconn.execute(
                    "SELECT COUNT(*) FROM holding_management_plan p "
                    "LEFT JOIN holding_position h ON h.id=p.position_id "
                    "WHERE p.status='ACTIVE' AND h.id IS NULL"
                ).fetchone()[0]),
                "open_positions_without_active_plan": int(hconn.execute(
                    "SELECT COUNT(*) FROM holding_position h WHERE h.status='OPEN' "
                    "AND NOT EXISTS (SELECT 1 FROM holding_management_plan p "
                    "WHERE p.position_id=h.id AND p.status='ACTIVE')"
                ).fetchone()[0]),
            }

        with closing(_connect_readonly(market_db)) as mconn:
            market_tables = _tables(mconn)
            if not MARKET_TABLES.issubset(market_tables):
                return {**base, "status": "BLOCKED_MARKET_SCHEMA_MISSING"}
            market_summary = {
                "status": "STORED_DATA_ONLY",
                "stock_rows": int(mconn.execute(
                    "SELECT COUNT(*) FROM stock_daily"
                ).fetchone()[0]),
                "index_rows": int(mconn.execute(
                    "SELECT COUNT(*) FROM main_index_daily"
                ).fetchone()[0]),
                "latest_stock_date": mconn.execute(
                    "SELECT MAX(bas_dd) FROM stock_daily"
                ).fetchone()[0],
            }

        has_inconsistency = any(
            consistency[key] > 0
            for key in (
                "active_plan_for_closed_position",
                "multiple_active_plans_per_position",
                "active_plans_for_missing_position",
            )
        )
        if has_inconsistency:
            status = "BLOCKED_HOLDINGS_PLAN_INCONSISTENT"
        elif domain_status["decision"]["status"] != "READY":
            status = "HOLD_DECISION_SCHEMA_PREPARATION_REQUIRED"
        elif counts["open_positions"] == 0:
            status = "NO_OPEN_POSITIONS_TO_UAT"
        else:
            status = "READ_ONLY_HOLDINGS_PREFLIGHT_OBSERVED"

        return {
            **base, "status": status,
            "domains": domain_status,
            "counts": counts,
            "consistency": consistency,
            "market": market_summary,
            "ready_for_plan_write": False,
            "user_confirmation_still_required": True,
            "notes": [
                "No database migration, new decision, plan application or order was executed.",
                "Storage shape and counts do not prove a currently usable analysis, EOD publication or live account.",
                "Optional recovery/watch migrations are reported but never executed.",
            ],
        }
    except (sqlite3.Error, OSError, ValueError):
        # No absolute user paths, account identifiers or underlying SQL error
        # strings may leak into a terminal transcript.
        return {**base, "status": "BLOCKED_READ_ONLY_DB_QUERY_FAILED"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdings-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    args = parser.parse_args()
    result = inspect_holdings_environment(args.holdings_db, args.market_db)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] in {
        "READ_ONLY_HOLDINGS_PREFLIGHT_OBSERVED",
        "NO_OPEN_POSITIONS_TO_UAT",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
