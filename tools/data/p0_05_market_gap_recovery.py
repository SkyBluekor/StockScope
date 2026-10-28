"""P0-05 G1 bounded, opt-in KRX missing-day repair. No default side effects.

PLAN never imports provider classes, opens a socket, or writes market DB.
RUN requires three explicit authorizations; fetches every slot and validates
before one SQLite transaction, and never overwrites existing market evidence.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for root in (ROOT, BACKEND):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from tools.data.common import market_db_path

VERSION = "STOCKSCOPE_P0_05_G1_BOUNDED_MARKET_RECOVERY_V1"
MARKETS = ("KOSPI", "KOSDAQ")
KINDS = ("stock", "index")
KST = timezone(timedelta(hours=9), name="KST")
REQUIRED = frozenset({"stock_daily", "main_index_daily", "day_status"})
MAX_DATES = 4


class RecoveryHold(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _today() -> date:
    return datetime.now(KST).date()


def _dates(raw: list[str], *, today: date) -> tuple[date, ...]:
    if not 1 <= len(raw) <= MAX_DATES:
        raise RecoveryHold("HOLD_DATE_COUNT_INVALID")
    try:
        parsed = [date.fromisoformat(item) for item in raw]
    except ValueError as exc:
        raise RecoveryHold("HOLD_DATE_FORMAT_INVALID") from exc
    if (len(set(parsed)) != len(parsed)
            or any(day >= today or day.weekday() >= 5 for day in parsed)
            or max(parsed) - min(parsed) > timedelta(days=14)):
        raise RecoveryHold("HOLD_DATE_RANGE_INVALID")
    return tuple(sorted(parsed))


def _inspect(db: Path, dates: tuple[date, ...]) -> list[dict[str, str]]:
    if not db.is_file():
        raise RecoveryHold("HOLD_MARKET_DB_MISSING")
    try:
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10,
        )) as conn:
            conn.execute("PRAGMA query_only=ON")
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if not REQUIRED.issubset(tables):
                raise RecoveryHold("HOLD_MARKET_SCHEMA_MISSING")
            slots = []
            for day in dates:
                bas_dd = day.strftime("%Y%m%d")
                for market in MARKETS:
                    counts = (
                        conn.execute(
                            "SELECT COUNT(*) FROM stock_daily WHERE market=? AND bas_dd=?",
                            (market, bas_dd),
                        ).fetchone()[0],
                        conn.execute(
                            "SELECT COUNT(*) FROM main_index_daily WHERE market=? AND bas_dd=?",
                            (market, bas_dd),
                        ).fetchone()[0],
                    )
                    markers = {
                        kind: status for kind, status in conn.execute(
                            "SELECT kind,status FROM day_status WHERE market=? AND bas_dd=?",
                            (market, bas_dd),
                        )
                    }
                    if any(counts) or markers:
                        raise RecoveryHold("HOLD_PREEXISTING_OR_PARTIAL_MARKET_DAY")
                    slots.append({"date": day.isoformat(), "market": market})
        return slots
    except sqlite3.Error as exc:
        raise RecoveryHold("HOLD_MARKET_DB_READ_FAILED") from exc


def plan(*, db: Path, raw_dates: list[str], today: date | None = None) -> dict[str, Any]:
    dates = _dates(raw_dates, today=today or _today())
    slots = _inspect(db, dates)
    return {
        "version": VERSION,
        "status": "READY_TO_REQUEST_SEPARATE_APPROVAL",
        "requested_dates": [item.isoformat() for item in dates],
        "markets": list(MARKETS),
        "missing_market_days": len(slots),
        "required_provider_endpoint_calls_without_retries": len(slots) * 2,
        "retry_or_shared_provider_usage_may_increase_calls": True,
        "official_trading_calendar_verified": False,
        "source_rights_verified": False,
        "api_entitlement_verified": False,
        "provider_budget_approved": False,
        "market_db_write_approved": False,
        "db_writes": 0,
        "external_requests": 0,
        "market_db_read_only": True,
        "scanner_job_started": False,
        "new_prospective_capture_created": False,
        "scheduler_registered": False,
        "actual_orders": 0,
    }


def _validate_stock(rows: Any, market: str, key: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or len(rows) < 100:
        raise RecoveryHold("HOLD_KRX_STOCK_RESPONSE_INCOMPLETE")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RecoveryHold("HOLD_KRX_STOCK_ROW_INVALID")
        code = str(row.get("code") or "").strip().upper()
        if (not code or code in seen or str(row.get("date") or "").replace("-", "") != key
                or row.get("close") is None):
            raise RecoveryHold("HOLD_KRX_STOCK_ROW_INVALID")
        seen.add(code)
    return rows


def _validate_index(rows: Any, market: str, key: str) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise RecoveryHold("HOLD_KRX_INDEX_RESPONSE_INCOMPLETE")
    target = "코스피" if market == "KOSPI" else "코스닥"
    found = [r for r in rows if (
        isinstance(r, dict) and str(r.get("name") or "").strip() == target
        and str(r.get("date") or "").replace("-", "") == key
        and isinstance(r.get("close"), (float, int)) and not isinstance(r.get("close"), bool)
        and r["close"] > 0
    )]
    if len(found) != 1:
        raise RecoveryHold("HOLD_KRX_INDEX_RESPONSE_INCOMPLETE")
    return found[0]


def _atomic_insert(db: Path, slots: list[dict[str, str]],
                   prepared: dict[tuple[str, str], tuple[list[dict[str, Any]], dict[str, Any]]]) -> int:
    # All provider responses were checked first. Never DELETE/REPLACE legacy
    # market rows or change existing integrity-verification evidence.
    try:
        with closing(sqlite3.connect(db, timeout=20)) as conn:
            conn.execute("PRAGMA busy_timeout=20000")
            conn.execute("BEGIN IMMEDIATE")
            for entry in slots:
                market = entry["market"]
                key = entry["date"].replace("-", "")
                # Recheck *inside* the lock: a live Scanner may have filled
                # this day after our read-only planning stage.
                if (conn.execute(
                    "SELECT COUNT(*) FROM stock_daily WHERE market=? AND bas_dd=?",
                    (market, key),
                ).fetchone()[0] or conn.execute(
                    "SELECT COUNT(*) FROM main_index_daily WHERE market=? AND bas_dd=?",
                    (market, key),
                ).fetchone()[0] or conn.execute(
                    "SELECT COUNT(*) FROM day_status WHERE market=? AND bas_dd=?",
                    (market, key),
                ).fetchone()[0]):
                    raise RecoveryHold("HOLD_CONCURRENT_MARKET_DAY_CHANGE")
                stocks, index = prepared[(market, key)]
                conn.executemany(
                    "INSERT INTO stock_daily(market,bas_dd,stock_code,row_json) VALUES (?,?,?,?)",
                    [(market, key, str(row["code"]).strip().upper(),
                      json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                     for row in stocks],
                )
                conn.execute(
                    "INSERT INTO main_index_daily(market,bas_dd,row_json) VALUES (?,?,?)",
                    (market, key, json.dumps(index, ensure_ascii=False, separators=(",", ":"))),
                )
                conn.executemany(
                    "INSERT INTO day_status(market,bas_dd,kind,status) VALUES (?,?,?,?)",
                    [(market, key, kind, "data") for kind in KINDS],
                )
                n = conn.execute(
                    "SELECT COUNT(*) FROM stock_daily WHERE market=? AND bas_dd=?",
                    (market, key),
                ).fetchone()[0]
                if n != len(stocks):
                    raise RecoveryHold("HOLD_MARKET_STAGING_READBACK_FAILED")
            conn.commit()
        return len(slots)
    except sqlite3.Error as exc:
        raise RecoveryHold("HOLD_ATOMIC_MARKET_INSERT_FAILED") from exc


class _CappedBudget:
    """Wrapper around the project's persistent KRX ledger, including retries."""
    def __init__(self, underlying: Any, max_requests: int):
        self.underlying = underlying
        self.max_requests = max_requests
        self.used = 0

    def consume(self, *, retry: bool = False):
        if self.used >= self.max_requests:
            raise RecoveryHold("HOLD_APPROVED_REQUEST_CAP_EXHAUSTED")
        snapshot = self.underlying.consume(retry=retry)
        self.used += 1
        return snapshot


async def recover_approved(
    *, db: Path, raw_dates: list[str], max_requests: int,
    approved_requests: bool, approved_write: bool, rights_confirmed: bool,
    provider: Any | None = None, today: date | None = None,
) -> dict[str, Any]:
    # Flags require a separate conscious command; we never call this in plan.
    if not all((approved_requests, approved_write, rights_confirmed)):
        raise RecoveryHold("HOLD_EXPLICIT_APPROVAL_REQUIRED")
    evidence = plan(db=db, raw_dates=raw_dates, today=today)
    slots = [{"date": day, "market": m}
             for day in evidence["requested_dates"] for m in MARKETS]
    required = len(slots) * len(KINDS)
    if not required <= max_requests <= 64:
        raise RecoveryHold("HOLD_NETWORK_REQUEST_CAP_INVALID")
    if provider is None:
        from app.core.config import get_settings
        from app.market.krx_budget import KrxApiBudget
        from app.market.providers.krx import KrxProvider

        credential = get_settings().krx_api_key
        if not credential:
            raise RecoveryHold("HOLD_KRX_KEY_MISSING")
        budget = KrxApiBudget()
        budget.assert_can_start(max_requests)
        capped = _CappedBudget(budget, max_requests)
        provider = KrxProvider(credential, budget=capped)
    prepared: dict[tuple[str, str], tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    try:
        await provider.open_session()
        for entry in slots:
            market = entry["market"]
            key = entry["date"].replace("-", "")
            stock = await provider.stock_daily(market, key, force_refresh=True)
            index = await provider.index_daily(market, key, force_refresh=True)
            prepared[(market, key)] = (
                _validate_stock(stock.get("rows"), market, key),
                _validate_index(index.get("rows"), market, key),
            )
        written = _atomic_insert(db, slots, prepared)
    finally:
        await provider.close_session()
    return {
        "version": VERSION, "status": "MISSING_MARKET_DAYS_RESTORED",
        "market_days_written": written, "dates": evidence["requested_dates"],
        "scope": "ALL", "all_or_nothing_transaction": True,
        "existing_market_rows_overwritten": False,
        "official_publication_time_attested": False,
        "new_prospective_capture_created": False, "real_orders": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded P0-05 G1 missing-day KRX recovery")
    parser.add_argument("--market-db", type=Path, default=market_db_path())
    parser.add_argument("--date", action="append", required=True, dest="dates",
                        help="YYYY-MM-DD; repeat for up to four dated gaps")
    parser.add_argument("--max-requests", type=int, default=16)
    parser.add_argument("--run-approved", action="store_true")
    parser.add_argument("--approve-krx-requests", action="store_true")
    parser.add_argument("--approve-market-write", action="store_true")
    parser.add_argument("--confirm-source-rights", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.run_approved:
            result = asyncio.run(recover_approved(
                db=args.market_db, raw_dates=args.dates,
                max_requests=args.max_requests,
                approved_requests=args.approve_krx_requests,
                approved_write=args.approve_market_write,
                rights_confirmed=args.confirm_source_rights,
            ))
        elif any((args.approve_krx_requests, args.approve_market_write,
                  args.confirm_source_rights)):
            raise RecoveryHold("HOLD_APPROVAL_FLAGS_WITHOUT_RUN")
        else:
            result = plan(db=args.market_db, raw_dates=args.dates)
    except RecoveryHold as exc:
        result = {
            "version": VERSION, "status": exc.code,
            "market_write_success": False,
            "scanner_job_started": False,
            "new_prospective_capture_created": False,
            "official_publication_time_attested": False,
            "real_orders": 0,
        }
    except Exception:
        # Do not leak provider responses, API keys, paths, or raw stock rows.
        result = {
            "version": VERSION, "status": "HOLD_KRX_RECOVERY_FAILED",
            "market_write_success": False,
            "new_prospective_capture_created": False,
            "real_orders": 0,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {
        "READY_TO_REQUEST_SEPARATE_APPROVAL", "MISSING_MARKET_DAYS_RESTORED",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
