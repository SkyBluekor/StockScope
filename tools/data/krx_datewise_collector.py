"""S31-F: scanner-independent, bounded KRX daily EOD collector.

PLAN: read only the existing isolated research snapshot (or source Market DB).
COLLECT: explicit owner consent, creates an isolated SQLite ONLINE backup once,
then append-only persists missing KRX stock+main-index pairs into that copy.

Existing market data, scanner/risk/strategy, captures, trading and production
databases are never written. KRX calls use isolated research cache+budget.
No schedule, migrations, live intraday claims or fake holiday inferences.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
import os
import tempfile
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for p in (ROOT, BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.market.session_calendar_s21 import closure_evidence
from tools.data.common import market_db_path
from tools.data.prospective_outcome_refresh import (
    _commit_new_day, GapFillError, MIN_MARKET_ROWS,
)

VERSION = "STOCKSCOPE_S31F_DATEWISE_KRX_RESEARCH_EOD_V1"
KST = ZoneInfo("Asia/Seoul")
RESEARCH_ROOT = ROOT / "data" / "krx_datewise_collector"
RESEARCH_DB = RESEARCH_ROOT / "market_history_research.db"
MAX_CALENDAR_DAYS = 35
MAX_REQUEST_DAYS = 20
REQUIRED_TABLES = {"stock_daily", "main_index_daily", "day_status"}


class CollectorError(ValueError):
    pass


def _day(value: str) -> date:
    if not isinstance(value, str):
        raise CollectorError("DATE_MUST_BE_ISO")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CollectorError("DATE_MUST_BE_ISO") from exc
    if value != parsed.isoformat():
        raise CollectorError("DATE_MUST_BE_ISO")
    return parsed


def _range(start: str, through: str, today: date | None = None) -> list[date]:
    beginning, end = _day(start), _day(through)
    now = today or datetime.now(KST).date()
    if end >= now:
        raise CollectorError("TODAY_OR_FUTURE_EOD_UNVERIFIED")
    count = (end - beginning).days + 1
    if not 1 <= count <= MAX_CALENDAR_DAYS:
        raise CollectorError("DATE_RANGE_OUTSIDE_SAFE_LIMIT")
    return [beginning + timedelta(days=i) for i in range(count)]


def _connect_ro(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise CollectorError("MARKET_DB_NOT_FOUND")
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        tables = {
            str(x[0]) for x in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not REQUIRED_TABLES.issubset(tables):
            raise CollectorError("MARKET_DB_SCHEMA_INCOMPLETE")
    except Exception:
        connection.close()
        raise
    return connection


def _latest_complete_eod(conn: sqlite3.Connection, market: str) -> str | None:
    """Last wholly recorded stock+index market session, not a guessed weekday.

    The source DB may contain older partial attempts. Never consider a
    bare day_status marker to be a complete market-wide EOD snapshot.
    """
    row = conn.execute(
        """
        SELECT s.bas_dd FROM day_status AS s
        JOIN day_status AS i
          ON i.market=s.market AND i.bas_dd=s.bas_dd
         AND i.kind='index' AND i.status='data'
        WHERE s.market=? AND s.kind='stock' AND s.status='data'
          AND (SELECT COUNT(*) FROM stock_daily AS d
               WHERE d.market=s.market AND d.bas_dd=s.bas_dd) >= ?
          AND (SELECT COUNT(*) FROM main_index_daily AS idx
               WHERE idx.market=s.market AND idx.bas_dd=s.bas_dd) = 1
        ORDER BY s.bas_dd DESC LIMIT 1
        """,
        (market, MIN_MARKET_ROWS),
    ).fetchone()
    return str(row[0]) if row is not None else None


def _safe_paths(source_db: Path, research_db: Path, research_root: Path) -> None:
    src, dest, root = (
        Path(source_db).resolve(),
        Path(research_db).resolve(),
        Path(research_root).resolve(),
    )
    if src == dest or root not in dest.parents:
        raise CollectorError("RESEARCH_DB_MUST_BE_ISOLATED")


def plan(
    source_db: Path, research_db: Path, *,
    market: str, start: str | None = None, through: str | None = None,
    research_root: Path, today: date | None = None,
) -> dict[str, Any]:
    if market not in ("KOSPI", "KOSDAQ"):
        raise CollectorError("MARKET_MUST_BE_KOSPI_OR_KOSDAQ")
    _safe_paths(source_db, research_db, research_root)
    now = today or datetime.now(KST).date()
    end = _day(through) if through is not None else now - timedelta(days=1)
    if end >= now:
        raise CollectorError("TODAY_OR_FUTURE_EOD_UNVERIFIED")
    active = Path(research_db) if Path(research_db).is_file() else Path(source_db)
    rows = []
    with closing(_connect_ro(active)) as conn:
        latest = _latest_complete_eod(conn, market) if start is None else None
        if start is None and latest is None:
            raise CollectorError("AUTO_FROM_REQUIRES_EXISTING_COMPLETE_EOD")
        beginning = (
            date.fromisoformat(latest[:4] + "-" + latest[4:6] + "-" + latest[6:8])
            + timedelta(days=1)
            if start is None else _day(start)
        )
        # This is a valid automatic no-op, not a request to examine a
        # backwards range. An explicit backwards range still fails closed.
        days = (
            [] if start is None and beginning > end else
            _range(beginning.isoformat(), end.isoformat(), now)
        )
        for day in days:
            key = day.strftime("%Y%m%d")
            flags = conn.execute(
                "SELECT kind,status FROM day_status WHERE market=? AND bas_dd=?",
                (market, key),
            ).fetchall()
            stocks = int(conn.execute(
                "SELECT COUNT(*) FROM stock_daily WHERE market=? AND bas_dd=?",
                (market, key),
            ).fetchone()[0])
            indices = int(conn.execute(
                "SELECT COUNT(*) FROM main_index_daily WHERE market=? AND bas_dd=?",
                (market, key),
            ).fetchone()[0])
            statuses = {r["kind"]: r["status"] for r in flags}
            evidence = closure_evidence(day)
            if evidence is not None:
                status = "CONFLICT_WITH_VERIFIED_CLOSURE" if flags or stocks or indices else "VERIFIED_CLOSED"
            elif (
                len(flags) == 2 and statuses == {"stock": "data", "index": "data"}
                and stocks >= MIN_MARKET_ROWS and indices == 1
            ):
                status = "STORED_COMPLETE"
            elif flags or stocks or indices:
                status = "PARTIAL_EXISTING_MANUAL_REVIEW"
            else:
                status = "MISSING_UNVERIFIED_WEEKDAY"
            rows.append({
                "date": day.isoformat(), "status": status,
                "stock_rows": stocks, "index_rows": indices,
                **({"closure_reason": evidence["reason"]} if evidence else {}),
            })
    pending = [r for r in rows if r["status"] == "MISSING_UNVERIFIED_WEEKDAY"]
    conflicts = [r for r in rows if r["status"] in (
        "PARTIAL_EXISTING_MANUAL_REVIEW", "CONFLICT_WITH_VERIFIED_CLOSURE"
    )]
    return {
        "version": VERSION, "status": (
            "HOLD_EXISTING_DATA_CONFLICT" if conflicts
            else "HOLD_TOO_MANY_DAYS" if len(pending) > MAX_REQUEST_DAYS
            else "UP_TO_DATE" if not days and start is None
            else "PLAN_ONLY"
        ),
        "market": market,
        "from": beginning.isoformat(), "through": end.isoformat(),
        "from_resolution": "LAST_COMPLETE_PLUS_ONE" if start is None else "EXPLICIT",
        "last_complete_market_eod": latest,
        "older_gaps_prior_to_last_complete_scanned": False,
        "read_from": "RESEARCH_COPY" if active == Path(research_db) else "SOURCE_READ_ONLY",
        "source_market_db": str(Path(source_db).resolve()),
        "research_market_db": str(Path(research_db).resolve()),
        "days": rows, "pending_dates": [x["date"] for x in pending],
        "potential_api_requests": 2 * len(pending),
        "verified_closed_count": sum(r["status"] == "VERIFIED_CLOSED" for r in rows),
        "complete_count": sum(r["status"] == "STORED_COMPLETE" for r in rows),
        "conflict_count": len(conflicts),
        "unverified_weekday_is_not_confirmed_session": True,
        "production_market_db_writes": 0, "research_market_db_writes": 0,
        "network_requests": 0, "jev_calls": 0, "orders": 0,
    }


def _clone_if_missing(source_db: Path, research_db: Path, research_root: Path) -> bool:
    """Publish a WAL-safe SQLite backup only AFTER both handles are closed.

    A sqlite3.Connection context manager commits/rolls back but does NOT
    close the handle. On Windows the former S31-F implementation therefore
    raised PermissionError while renaming its still-open .initializing DB.
    Each attempt now uses an exclusive unique temp name, so an abandoned
    staging file from the old failure cannot block a fresh, safe backup.
    """
    _safe_paths(source_db, research_db, research_root)
    if research_db.is_file():
        return False
    if research_db.exists():
        raise CollectorError("RESEARCH_TARGET_IS_NOT_FILE")

    research_db.parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    stage = "CREATE"
    try:
        # mkstemp's OS handle must be closed before opening the file via
        # SQLite, particularly on Windows. Never overwrite another temp DB.
        fd, name = tempfile.mkstemp(
            prefix=research_db.name + ".", suffix=".initializing",
            dir=research_db.parent,
        )
        os.close(fd)
        tmp = Path(name)
        stage = "BACKUP"
        with closing(_connect_ro(source_db)) as src:
            with closing(sqlite3.connect(tmp)) as dest:
                src.backup(dest)

        # Both connections are now explicitly closed before atomic rename.
        stage = "PUBLISH"
        if research_db.exists():
            raise CollectorError("RESEARCH_TARGET_CREATED_CONCURRENTLY")
        tmp.replace(research_db)
        stage = "VERIFY"
        with closing(_connect_ro(research_db)):
            pass
    except PermissionError as exc:
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise CollectorError(f"RESEARCH_COPY_{stage}_PERMISSION_DENIED") from exc
    except Exception:
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
    return True


def _isolated_provider(root: Path) -> Any:
    # Import provider/credentials only when an explicitly authorized COLLECT
    # has something missing. PLAN never touches env secrets or network.
    from app.core.config import get_settings
    from app.market.krx_budget import KrxApiBudget
    from app.market.providers.krx import KrxProvider
    key = get_settings().krx_api_key
    if not key:
        raise CollectorError("KRX_API_KEY_MISSING")
    class ResearchKrx(KrxProvider):
        _cache_dir = root / "krx_cache"
        _rows_cache = {}
        _cache_expiry = {}
        _inflight_tasks = {}
    return ResearchKrx(
        key,
        budget=KrxApiBudget(db_path=root / "krx_budget.sqlite3", safe_limit=60),
    )


async def collect(
    source_db: Path, research_db: Path, *,
    research_root: Path, market: str,
    start: str | None = None, through: str | None = None,
    acknowledge: bool = False, today: date | None = None,
    provider: Any | None = None,
) -> dict[str, Any]:
    if not acknowledge:
        raise CollectorError("EXPLICIT_RESEARCH_WRITE_ACK_REQUIRED")
    before = plan(
        source_db, research_db, market=market, start=start, through=through,
        research_root=research_root, today=today,
    )
    if before["status"] not in ("PLAN_ONLY", "UP_TO_DATE"):
        raise CollectorError(before["status"])
    requested = list(before["pending_dates"])
    if not requested:
        return {
            **before, "status": "NO_MISSING_DAYS",
            "new_research_copy": False, "stored_days": [],
            "errors": [], "network_requests": 0,
        }

    source = provider if provider is not None else _isolated_provider(Path(research_root))
    try:
        source.assert_budget(2 * len(requested))
    except Exception as exc:
        raise CollectorError("KRX_RESEARCH_BUDGET_PREFLIGHT_BLOCKED") from exc

    cloned = _clone_if_missing(Path(source_db), Path(research_db), Path(research_root))
    # Re-check against the actual research destination immediately after the
    # backup, so a changing source DB never silently overwrites anything.
    after = plan(
        source_db, research_db, market=market, start=start, through=through,
        research_root=research_root, today=today,
    )
    if after["status"] != "PLAN_ONLY":
        raise CollectorError(after["status"])
    requested = list(after["pending_dates"])
    stored: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    await source.open_session()
    try:
        for day in requested:
            try:
                stocks = await source.stock_daily(market, date.fromisoformat(day))
                indexes = await source.index_daily(market, date.fromisoformat(day))
                if (
                    not isinstance(stocks, dict) or not isinstance(indexes, dict)
                    or stocks.get("date") != day.replace("-", "")
                    or indexes.get("date") != day.replace("-", "")
                ):
                    raise CollectorError("KRX_RESPONSE_DATE_MISMATCH")
                stock_rows, index_rows = stocks.get("rows"), indexes.get("rows")
                if not stock_rows and not index_rows:
                    # Could be a holiday OR a failed/delayed provider. Neither
                    # is proof; stop rather than skip a genuine trading day.
                    raise CollectorError("KRX_EMPTY_NO_INDEPENDENT_CLOSURE_PROOF")
                if not isinstance(stock_rows, list) or not isinstance(index_rows, list):
                    raise CollectorError("KRX_STOCK_INDEX_PAIR_INVALID")
                expected_index = "코스피" if market == "KOSPI" else "코스닥"
                main = next((
                    row for row in index_rows
                    if isinstance(row, dict) and row.get("name") == expected_index
                ), None)
                if main is None:
                    raise CollectorError("KRX_MAIN_INDEX_MISSING")
                count = _commit_new_day(
                    Path(research_db), market, day, stock_rows, main,
                )
                stored.append({"date": day, "stock_rows": count, "index_rows": 1})
            except Exception as exc:
                code = str(exc) if isinstance(exc, (CollectorError, GapFillError)) else type(exc).__name__
                errors.append({"date": day, "reason_code": code})
                break
    finally:
        await source.close_session()
    return {
        "version": VERSION,
        "status": "PARTIAL_UNVERIFIED" if errors else "RESEARCH_DAYS_STORED",
        "market": market, "from": start, "through": through,
        "source_market_db": str(Path(source_db).resolve()),
        "research_market_db": str(Path(research_db).resolve()),
        "new_research_copy": cloned,
        "stored_days": stored,
        "stored_count": len(stored), "errors": errors,
        "pending_before": requested,
        "network_requests": (
            source.request_stats().get("network_requests")
            if callable(getattr(source, "request_stats", None)) else None
        ),
        "production_market_db_writes": 0,
        "research_market_db_writes": len(stored),
        "jev_calls": 0, "orders": 0,
        "source_release_proven": False,
        "no_scanner_execution": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Isolated research KRX EOD by date; default plan, no Scanner"
    )
    parser.add_argument("mode", nargs="?", choices=("plan", "collect"), default="plan")
    parser.add_argument("--market", required=True, choices=("KOSPI", "KOSDAQ"))
    parser.add_argument("--from", dest="start", default=None,
                        help="YYYY-MM-DD; 생략 시 마지막 완료 EOD 다음 날 자동 계산")
    parser.add_argument("--through", default=None,
                        help="YYYY-MM-DD; 생략 시 한국시간 어제까지 (당일 EOD 제외)")
    parser.add_argument("--acknowledge-research-writes", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode == "plan":
            report = plan(
                market_db_path(), RESEARCH_DB, market=args.market,
                start=args.start, through=args.through, research_root=RESEARCH_ROOT,
            )
        else:
            report = asyncio.run(collect(
                market_db_path(), RESEARCH_DB, market=args.market,
                start=args.start, through=args.through, research_root=RESEARCH_ROOT,
                acknowledge=args.acknowledge_research_writes,
            ))
    except (CollectorError, GapFillError, sqlite3.Error, OSError, ValueError) as exc:
        code = str(exc) if isinstance(exc, (CollectorError, GapFillError)) else type(exc).__name__
        report = {
            "version": VERSION, "status": "HOLD",
            "reason_code": code, "production_market_db_writes": 0,
            "jev_calls": 0, "orders": 0,
        }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(f"StockScope 날짜별 KRX EOD · {report['status']}")
        if report["status"] == "HOLD":
            print(f"차단 이유: {report['reason_code']}")
        elif args.mode == "plan":
            print(f"시장: {report['market']} | 범위: {report['from']} ~ {report['through']} | 이미 완료: {report['complete_count']}일")
            if report["from_resolution"] == "LAST_COMPLETE_PLUS_ONE":
                print(f"자동 시작점: 마지막 완료 EOD {report['last_complete_market_eod']} 다음 날")
            print(f"확인된 휴장: {report['verified_closed_count']}일 | 새로 수집할 날짜: {len(report['pending_dates'])}일")
            for item in report["days"]:
                print(f"  {item['date']} · {item['status']}")
            print(f"예상 KRX 기본 요청: {report['potential_api_requests']}회")
        else:
            print(f"연구 DB 추가: {report.get('stored_count', 0)}일 | 실패: {report.get('errors', [])}")
            print(f"연구 DB: {report['research_market_db']}")
        print("Scanner/JEV 실행 없음. 원본 Market DB 변경 없음.")
    return 0 if report["status"] in (
        "PLAN_ONLY", "UP_TO_DATE", "NO_MISSING_DAYS", "RESEARCH_DAYS_STORED"
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
