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

REQUIRED_MARKET_TABLES = frozenset(
    {
        "stock_daily",
        "main_index_daily",
        "day_status",
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
        return {
            "integrity": "ok",
            "foreign_keys": "ok",
            "domain": "ok",
            "counts": counts,
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
