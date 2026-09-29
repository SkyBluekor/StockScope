from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
DEFAULT_HOLDINGS_DB = BACKEND_ROOT / "runtime" / "holdings" / "holdings.db"
DEFAULT_MARKET_DB = BACKEND_ROOT / "runtime" / "market_history" / "market_history.db"
DEFAULT_SIMULATION_DB = BACKEND_ROOT / "runtime" / "simulation" / "simulation.db"
DEFAULT_TRACKING_DB = BACKEND_ROOT / "runtime" / "tracking" / "recommendation_tracking.db"
DEFAULT_MACRO_DB = BACKEND_ROOT / "runtime" / "macro" / "macro.db"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "backups"
BACKUP_FORMAT_VERSION = 1

HOLDINGS_COUNT_TABLES = (
    "monitored_stock",
    "position_account",
    "holding_position",
    "holding_position_event",
    "stock_analysis_day",
    "stock_analysis_revision",
    "holding_management_plan",
)

REQUIRED_HOLDINGS_TABLES = frozenset(
    {
        "position_account",
        "monitored_stock",
        "stock_analysis_day",
        "stock_analysis_revision",
        "holding_position",
        "holding_position_event",
        "holding_management_plan",
    }
)

HOLDING_DECISION_SCHEMA_VERSION = "VN_P3_S1_HOLDING_DECISION_STORAGE_V1"
HOLDING_DECISION_TABLES = frozenset(
    {
        "holding_decision_schema_meta",
        "holding_decision_record",
        "holding_decision_resolution",
        "holding_management_plan_context_vnp3s1",
    }
)

HOLDING_RECOVERY_SCHEMA_VERSION = "VN_P3_S2_RECOVERY_REVIEW_V1"
HOLDING_RECOVERY_TABLES = frozenset(
    {
        "holding_recovery_schema_meta",
        "holding_recovery_review",
        "holding_recovery_assessment",
    }
)

HOLDING_WATCH_SCHEMA_VERSION = "VN_P4_S1_WATCH_V1"
HOLDING_WATCH_POLICY_CONTRACT_VERSION = "VN_P4_S1_WATCH_POLICY_CONTRACT_V1"
HOLDING_WATCH_TABLES = frozenset(
    {
        "holding_watch_schema_meta",
        "holding_watch_setting",
        "holding_watch_rule",
        "holding_watch_episode",
        "holding_watch_coverage_gap",
        "holding_watch_notification_outbox",
    }
)

REQUIRED_MARKET_TABLES = frozenset(
    {
        "stock_daily",
        "main_index_daily",
        "day_status",
    }
)

SIMULATION_TABLE_FAMILIES = (
    frozenset({"simulation_schema_meta", "simulation_portfolio"}),
    frozenset({"historical_validation_run", "historical_validation_day"}),
    frozenset({"historical_execution_run"}),
    frozenset({
        "feedback_schema_meta",
        "feedback_source_ref",
        "feedback_cohort",
        "feedback_cohort_source",
        "feedback_cohort_member",
        "feedback_report",
    }),
    frozenset({
        "prospective_schema_meta",
        "prospective_capture_run",
        "prospective_recommendation_sample",
        "prospective_evaluation_protocol",
        "prospective_evaluation_run",
        "prospective_evaluation_unit",
        "prospective_evaluation_report",
    }),
)

REQUIRED_TRACKING_TABLES = frozenset(
    {
        "tracking_meta",
        "tracked_recommendation",
        "recommendation_performance",
    }
)


class DataToolError(RuntimeError):
    pass


def ensure_backend_import_path() -> None:
    raw = str(BACKEND_ROOT)
    if raw not in sys.path:
        sys.path.insert(0, raw)


def holdings_db_path() -> Path:
    raw = (os.getenv("STOCKSCOPE_HOLDINGS_DB") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_HOLDINGS_DB


def market_db_path() -> Path:
    raw = (os.getenv("STOCKSCOPE_MARKET_STORE_DB") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_MARKET_DB


def simulation_db_path() -> Path:
    raw = (os.getenv("STOCKSCOPE_SIM_DB") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_SIMULATION_DB


def tracking_db_path() -> Path:
    raw = (os.getenv("STOCKSCOPE_TRACKING_DB") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_TRACKING_DB


def macro_db_path() -> Path:
    raw = (os.getenv("STOCKSCOPE_MACRO_DB") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_MACRO_DB


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_state(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return (int(stat.st_size), int(stat.st_mtime_ns))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            block = fp.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def sqlite_readonly(path: Path) -> Iterator[sqlite3.Connection]:
    if not path.is_file():
        raise DataToolError(f"SQLite DB를 찾을 수 없습니다: {path}")
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _integrity_check(conn: sqlite3.Connection) -> None:
    row = conn.execute("PRAGMA integrity_check").fetchone()
    value = str(row[0] if row else "")
    if value.lower() != "ok":
        raise DataToolError(f"SQLite integrity_check 실패: {value or 'unknown'}")


def _foreign_key_check(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    if rows:
        sample = [tuple(row) for row in rows[:5]]
        raise DataToolError(f"SQLite foreign_key_check 실패: {sample}")


def holdings_counts(path: Path) -> dict[str, int]:
    with sqlite_readonly(path) as conn:
        names = table_names(conn)
        result: dict[str, int] = {}
        for name in HOLDINGS_COUNT_TABLES:
            if name in names:
                result[name] = int(
                    conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                )
        return result


def validate_holdings_db(path: Path) -> dict[str, Any]:
    with sqlite_readonly(path) as conn:
        names = table_names(conn)
        missing = sorted(REQUIRED_HOLDINGS_TABLES - names)
        if missing:
            raise DataToolError(
                "Holdings DB 필수 테이블이 없습니다: " + ", ".join(missing)
            )

        _integrity_check(conn)
        _foreign_key_check(conn)

        decision_present = HOLDING_DECISION_TABLES & names
        if decision_present and not HOLDING_DECISION_TABLES.issubset(names):
            missing_decision = sorted(HOLDING_DECISION_TABLES - names)
            raise DataToolError(
                "Holdings decision store가 부분 migration 상태입니다: "
                + ", ".join(missing_decision)
            )
        if HOLDING_DECISION_TABLES.issubset(names):
            row = conn.execute(
                """
                SELECT value FROM holding_decision_schema_meta
                WHERE key='schema_version'
                """
            ).fetchone()
            if row is None or str(row[0]) != HOLDING_DECISION_SCHEMA_VERSION:
                raise DataToolError(
                    "Holdings decision schema version이 지원 범위와 다릅니다."
                )

            invalid_apply = conn.execute(
                """
                SELECT id FROM holding_decision_resolution
                WHERE resolution_type='APPLY_NEW_PLAN'
                  AND resulting_plan_id IS NULL
                LIMIT 5
                """
            ).fetchall()
            if invalid_apply:
                raise DataToolError(
                    "APPLY_NEW_PLAN resolution에 resulting plan 참조가 없습니다."
                )

            unsupported_numeric_context = conn.execute(
                """
                SELECT plan_id
                FROM holding_management_plan_context_vnp3s1
                WHERE review_cycle_trading_days IS NOT NULL
                   OR time_stop_trading_days IS NOT NULL
                LIMIT 5
                """
            ).fetchall()
            if unsupported_numeric_context:
                raise DataToolError(
                    "P3-S1 plan context에 승인되지 않은 Review Cycle/Time Stop 수치가 있습니다."
                )

        recovery_present = HOLDING_RECOVERY_TABLES & names
        if recovery_present and not HOLDING_RECOVERY_TABLES.issubset(names):
            missing_recovery = sorted(HOLDING_RECOVERY_TABLES - names)
            raise DataToolError(
                "Holdings Recovery store가 부분 migration 상태입니다: "
                + ", ".join(missing_recovery)
            )
        if HOLDING_RECOVERY_TABLES.issubset(names):
            row = conn.execute(
                """
                SELECT value FROM holding_recovery_schema_meta
                WHERE key='schema_version'
                """
            ).fetchone()
            if row is None or str(row[0]) != HOLDING_RECOVERY_SCHEMA_VERSION:
                raise DataToolError(
                    "Holdings Recovery schema version이 지원 범위와 다릅니다."
                )

            duplicate_recovery = conn.execute(
                """
                SELECT position_id,COUNT(*) AS n
                FROM holding_recovery_review
                WHERE status='OPEN'
                GROUP BY position_id
                HAVING COUNT(*) > 1
                LIMIT 5
                """
            ).fetchall()
            if duplicate_recovery:
                raise DataToolError(
                    "한 Position에 OPEN Recovery review가 2개 이상 있습니다."
                )

            mismatched_assessment = conn.execute(
                """
                SELECT a.id
                FROM holding_recovery_assessment a
                JOIN holding_recovery_review r ON r.id=a.review_id
                WHERE a.position_id<>r.position_id
                LIMIT 5
                """
            ).fetchall()
            if mismatched_assessment:
                raise DataToolError(
                    "Recovery assessment의 Position이 review와 일치하지 않습니다."
                )

        watch_present = HOLDING_WATCH_TABLES & names
        if watch_present and not HOLDING_WATCH_TABLES.issubset(names):
            missing_watch = sorted(HOLDING_WATCH_TABLES - names)
            raise DataToolError(
                "Holdings Watch store가 부분 migration 상태입니다: "
                + ", ".join(missing_watch)
            )
        if HOLDING_WATCH_TABLES.issubset(names):
            schema_row = conn.execute(
                """
                SELECT value FROM holding_watch_schema_meta
                WHERE key='schema_version'
                """
            ).fetchone()
            if (
                schema_row is None
                or str(schema_row[0]) != HOLDING_WATCH_SCHEMA_VERSION
            ):
                raise DataToolError(
                    "Holdings Watch schema version이 지원 범위와 다릅니다."
                )

            contract_row = conn.execute(
                """
                SELECT value FROM holding_watch_schema_meta
                WHERE key='policy_contract_version'
                """
            ).fetchone()
            if (
                contract_row is None
                or str(contract_row[0]) != HOLDING_WATCH_POLICY_CONTRACT_VERSION
            ):
                raise DataToolError(
                    "Holdings Watch policy contract version이 지원 범위와 다릅니다."
                )

            duplicate_watch = conn.execute(
                """
                SELECT position_id,COUNT(*) AS n
                FROM holding_watch_setting
                WHERE status='ACTIVE'
                GROUP BY position_id
                HAVING COUNT(*) > 1
                LIMIT 5
                """
            ).fetchall()
            if duplicate_watch:
                raise DataToolError(
                    "한 Position에 ACTIVE Watch setting이 2개 이상 있습니다."
                )

            stale_active_watch = conn.execute(
                """
                SELECT ws.id
                FROM holding_watch_setting ws
                JOIN holding_position p ON p.id=ws.position_id
                JOIN holding_management_plan mp ON mp.id=ws.plan_id
                WHERE ws.status='ACTIVE'
                  AND (
                    p.status<>'OPEN'
                    OR mp.status<>'ACTIVE'
                    OR mp.position_id<>ws.position_id
                    OR mp.plan_version<>ws.plan_version
                  )
                LIMIT 5
                """
            ).fetchall()
            if stale_active_watch:
                raise DataToolError(
                    "ACTIVE Watch setting이 현재 OPEN Position/ACTIVE Plan과 일치하지 않습니다."
                )

            mismatched_watch_rule = conn.execute(
                """
                SELECT wr.id
                FROM holding_watch_rule wr
                JOIN holding_watch_setting ws ON ws.id=wr.setting_id
                WHERE wr.position_id<>ws.position_id
                   OR wr.plan_id<>ws.plan_id
                   OR wr.plan_version<>ws.plan_version
                LIMIT 5
                """
            ).fetchall()
            if mismatched_watch_rule:
                raise DataToolError(
                    "Watch rule의 Position/Plan snapshot이 setting과 일치하지 않습니다."
                )

        duplicate_open = conn.execute(
            """
            SELECT monitored_stock_id,position_account_id,COUNT(*) AS n
            FROM holding_position
            WHERE status='OPEN'
            GROUP BY monitored_stock_id,position_account_id
            HAVING COUNT(*) > 1
            LIMIT 5
            """
        ).fetchall()
        if duplicate_open:
            raise DataToolError(
                "같은 종목/계좌에 OPEN Position이 중복되어 있습니다."
            )

        duplicate_active_plan = conn.execute(
            """
            SELECT position_id,COUNT(*) AS n
            FROM holding_management_plan
            WHERE status='ACTIVE'
            GROUP BY position_id
            HAVING COUNT(*) > 1
            LIMIT 5
            """
        ).fetchall()
        if duplicate_active_plan:
            raise DataToolError(
                "한 Position에 ACTIVE 관리 계획이 2개 이상 있습니다."
            )

        active_on_closed = conn.execute(
            """
            SELECT p.id
            FROM holding_management_plan mp
            JOIN holding_position p ON p.id=mp.position_id
            WHERE mp.status='ACTIVE' AND p.status<>'OPEN'
            LIMIT 5
            """
        ).fetchall()
        if active_on_closed:
            raise DataToolError(
                "CLOSED Position에 ACTIVE 관리 계획이 남아 있습니다."
            )

        bad_current_revision = conn.execute(
            """
            SELECT d.id
            FROM stock_analysis_day d
            LEFT JOIN stock_analysis_revision r ON r.id=d.current_revision_id
            WHERE d.current_revision_id IS NOT NULL
              AND (r.id IS NULL OR r.analysis_day_id<>d.id)
            LIMIT 5
            """
        ).fetchall()
        if bad_current_revision:
            raise DataToolError(
                "Analysis Day의 current_revision 연결이 올바르지 않습니다."
            )

        counts = {
            name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in HOLDINGS_COUNT_TABLES
        }
        decision_counts = None
        if HOLDING_DECISION_TABLES.issubset(names):
            decision_counts = {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in sorted(HOLDING_DECISION_TABLES)
                if table != "holding_decision_schema_meta"
            }
        recovery_counts = None
        if HOLDING_RECOVERY_TABLES.issubset(names):
            recovery_counts = {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in sorted(HOLDING_RECOVERY_TABLES)
                if table != "holding_recovery_schema_meta"
            }
        watch_counts = None
        if HOLDING_WATCH_TABLES.issubset(names):
            watch_counts = {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in sorted(HOLDING_WATCH_TABLES)
                if table != "holding_watch_schema_meta"
            }
        return {
            "integrity": "ok",
            "foreign_keys": "ok",
            "domain": "ok",
            "counts": counts,
            "holding_decision": {
                "present": decision_counts is not None,
                "schema_version": (
                    HOLDING_DECISION_SCHEMA_VERSION if decision_counts is not None else None
                ),
                "counts": decision_counts,
            },
            "holding_recovery": {
                "present": recovery_counts is not None,
                "schema_version": (
                    HOLDING_RECOVERY_SCHEMA_VERSION if recovery_counts is not None else None
                ),
                "counts": recovery_counts,
            },
            "holding_watch": {
                "present": watch_counts is not None,
                "schema_version": (
                    HOLDING_WATCH_SCHEMA_VERSION if watch_counts is not None else None
                ),
                "policy_contract_version": (
                    HOLDING_WATCH_POLICY_CONTRACT_VERSION
                    if watch_counts is not None
                    else None
                ),
                "counts": watch_counts,
            },
        }


def validate_market_db(path: Path) -> dict[str, Any]:
    with sqlite_readonly(path) as conn:
        names = table_names(conn)
        missing = sorted(REQUIRED_MARKET_TABLES - names)
        if missing:
            raise DataToolError(
                "Market Store 필수 테이블이 없습니다: " + ", ".join(missing)
            )
        _integrity_check(conn)
        return {
            "integrity": "ok",
            "tables": sorted(REQUIRED_MARKET_TABLES),
        }


def validate_runtime_domain_db(
    path: Path,
    *,
    required_tables: frozenset[str],
    label: str,
) -> dict[str, Any]:
    """Validate an existing domain DB without creating or migrating it."""
    with sqlite_readonly(path) as conn:
        names = table_names(conn)
        missing = sorted(required_tables - names)
        if missing:
            raise DataToolError(
                f"{label} 필수 테이블이 없습니다: " + ", ".join(missing)
            )
        _integrity_check(conn)
        _foreign_key_check(conn)
        counts = {
            name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in sorted(required_tables)
        }
        return {
            "integrity": "ok",
            "foreign_keys": "ok",
            "tables": sorted(required_tables),
            "counts": counts,
        }


def validate_simulation_db(path: Path) -> dict[str, Any]:
    """Accept the currently populated Simulation domain families without creating them.

    Legacy SIM.1~3 and Historical/Execution Validation share one DB file but are
    independently initialized. A valid validation-only DB must therefore not be
    rejected merely because the legacy portfolio family was never created.
    """
    with sqlite_readonly(path) as conn:
        names = table_names(conn)
        present_families = [
            family for family in SIMULATION_TABLE_FAMILIES
            if family.issubset(names)
        ]
        if not present_families:
            raise DataToolError(
                "Simulation DB에서 지원되는 기존 도메인 테이블을 찾을 수 없습니다."
            )
        _integrity_check(conn)
        _foreign_key_check(conn)
        recognized = sorted(set().union(*present_families))
        counts = {
            name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in recognized
        }
        return {
            "integrity": "ok",
            "foreign_keys": "ok",
            "tables": recognized,
            "counts": counts,
        }


def validate_tracking_db(path: Path) -> dict[str, Any]:
    return validate_runtime_domain_db(
        path,
        required_tables=REQUIRED_TRACKING_TABLES,
        label="Tracking DB",
    )


def sqlite_snapshot(source: Path, target: Path) -> None:
    if not source.is_file():
        raise DataToolError(f"백업할 DB를 찾을 수 없습니다: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise DataToolError(f"대상 파일이 이미 존재합니다: {target}")

    source_uri = source.resolve().as_uri() + "?mode=ro"
    src = sqlite3.connect(source_uri, uri=True, timeout=20.0)
    dst = sqlite3.connect(target, timeout=20.0)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def project_version() -> str | None:
    pyproject = BACKEND_ROOT / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        with pyproject.open("rb") as fp:
            payload = tomllib.load(fp)
        value = payload.get("project", {}).get("version")
        return str(value) if value else None
    except (OSError, tomllib.TOMLDecodeError):
        return None


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp, path)


def manifest_file_entry(path: Path) -> dict[str, Any]:
    return {
        "size_bytes": int(path.stat().st_size),
        "sha256": sha256_file(path),
    }


def validate_manifest_hash(path: Path, entry: dict[str, Any], label: str) -> None:
    expected = str(entry.get("sha256") or "").strip().lower()
    if not expected:
        raise DataToolError(f"{label} manifest SHA-256이 없습니다.")
    actual = sha256_file(path)
    if actual.lower() != expected:
        raise DataToolError(
            f"{label} SHA-256이 manifest와 일치하지 않습니다."
        )


def secret_like_paths(root: Path) -> list[str]:
    blocked_names = {
        ".env",
        ".env.local",
        ".env.development",
        ".env.production",
        ".dev.vars",
    }
    results: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower in blocked_names:
            results.append(str(path.relative_to(root)))
        elif lower.endswith((".pem", ".p12", ".pfx")):
            results.append(str(path.relative_to(root)))
    return sorted(results)


def latest_common_market_date(conn: sqlite3.Connection, market: str) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(s.bas_dd)
        FROM day_status s
        JOIN day_status i
          ON i.market=s.market
         AND i.bas_dd=s.bas_dd
         AND i.kind='index'
         AND i.status='data'
        WHERE s.market=?
          AND s.kind='stock'
          AND s.status='data'
        """,
        (market,),
    ).fetchone()
    value = str(row[0] or "") if row else ""
    return value if len(value) == 8 and value.isdigit() else None


def monitored_targets(path: Path) -> list[dict[str, Any]]:
    with sqlite_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT
                s.id,
                s.market,
                s.ticker,
                s.name,
                s.watch_enabled,
                EXISTS(
                    SELECT 1
                    FROM holding_position p
                    WHERE p.monitored_stock_id=s.id
                      AND p.status='OPEN'
                ) AS is_held
            FROM monitored_stock s
            WHERE s.archived_at IS NULL
              AND (
                    s.watch_enabled=1
                    OR EXISTS(
                        SELECT 1
                        FROM holding_position p
                        WHERE p.monitored_stock_id=s.id
                          AND p.status='OPEN'
                    )
              )
            ORDER BY s.market,s.ticker
            """
        ).fetchall()
    return [
        {
            "stock_id": str(row["id"]),
            "market": str(row["market"]),
            "ticker": str(row["ticker"]),
            "name": str(row["name"]),
            "watch_enabled": bool(row["watch_enabled"]),
            "is_held": bool(row["is_held"]),
        }
        for row in rows
    ]


def assert_replaceable(path: Path) -> None:
    if not path.exists():
        return
    try:
        conn = sqlite3.connect(path, timeout=1.0)
        try:
            conn.execute("PRAGMA busy_timeout=1000")
            conn.execute("BEGIN EXCLUSIVE")
            conn.rollback()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise DataToolError(
            f"DB가 사용 중이라 복원할 수 없습니다. StockScope 서버를 종료한 뒤 다시 시도하세요: {path}"
        ) from exc

    sidecars = [
        Path(str(path) + "-wal"),
        Path(str(path) + "-shm"),
    ]
    live_sidecars = [
        item for item in sidecars
        if item.exists() and item.stat().st_size > 0
    ]
    if live_sidecars:
        raise DataToolError(
            "SQLite WAL/SHM 파일이 남아 있습니다. StockScope 서버를 완전히 종료한 뒤 다시 시도하세요: "
            + ", ".join(str(item) for item in live_sidecars)
        )
