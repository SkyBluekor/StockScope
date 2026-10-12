"""Read-only, conservative Scanner data preparation estimate for a new device.

No KRX provider or MarketStore instance is constructed: both can open/write
runtime databases. This code never issues HTTP, creates directories, or changes
raw caches. Scanner itself remains the authority on the confirmed EOD date,
daily KRX budget and whether additional data is actually needed.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import gzip
import json
import os
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from app.core.config import PROJECT_ROOT
from app.backtest.scanner import StockScannerService
from app.market.krx_budget import KrxApiBudget
from app.market.providers.krx import KrxProvider

SCHEMA = "SCANNER_DATA_AUTO_PREFLIGHT_V1"
KINDS = ("stock", "index")
MARKETS = ("KOSPI", "KOSDAQ")


def _readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _valid_raw_cache(root: Path, market: str, day: date, kind: str, *, today: date) -> bool:
    """Inspect gzip without the provider's legacy cleanup side effects."""
    endpoint = KrxProvider._endpoint_for_kind(market, kind)
    stamp = day.strftime("%Y%m%d")
    name = endpoint.path.replace("/", "__") + "__" + stamp
    path = root / (name + ".json.gz")
    if path.is_file():
        try:
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            return bool(
                isinstance(payload, list)
                and payload
                and all(
                    isinstance(row, dict) and str(row.get("BAS_DD") or "") == stamp
                    for row in payload
                )
            )
        except (OSError, UnicodeError, ValueError, TypeError):
            return False
    # A verified historical empty marker avoids querying valid exchange holidays.
    marker = root / (name + ".empty")
    return marker.is_file() and day <= today - timedelta(days=3)


def plan_scanner_data(
    *,
    market_scope: str = "ALL",
    as_of_date: str | None = None,
    candidate_limit: int = 5,
    market_db: Path | None = None,
    raw_cache_root: Path | None = None,
    budget_db: Path | None = None,
    today: date | None = None,
) -> dict:
    if market_scope not in {"ALL", *MARKETS} or not 1 <= candidate_limit <= 10:
        raise ValueError("INVALID_SCANNER_PLAN_REQUEST")
    current = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    end = min(date.fromisoformat(as_of_date), current - timedelta(days=1)) if as_of_date else current - timedelta(days=1)
    start = end - timedelta(days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS)
    markets = MARKETS if market_scope == "ALL" else (market_scope,)
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)
             if (start + timedelta(days=i)).weekday() < 5]

    db = market_db or Path(os.getenv("STOCKSCOPE_MARKET_STORE_DB") or os.getenv("STOCKSCOPE_MARKET_DB")
                           or PROJECT_ROOT / "backend/runtime/market_history/market_history.db")
    cache = raw_cache_root or KrxProvider._cache_dir
    status = {}
    warnings = []
    if db.is_file():
        try:
            with _readonly(db) as conn:
                names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "day_status" not in names and names:
                    return {
                        "version": SCHEMA, "status": "BLOCKED_SCHEMA",
                        "reason": "MARKET_SCHEMA_MISSING", "provider_calls": 0, "db_writes": 0,
                    }
                if not names:
                    # An empty DB from first startup is recoverable. The existing
                    # MarketStore constructor will initialize it when Scanner runs.
                    warnings.append("NEW_DEVICE_MARKET_SCHEMA_NOT_INITIALIZED")
                else:
                    first = start.strftime("%Y%m%d")
                    last = end.strftime("%Y%m%d")
                    for market, dd, kind in conn.execute(
                        "SELECT market,bas_dd,kind FROM day_status "
                        "WHERE market IN ('KOSPI','KOSDAQ') AND bas_dd>=? AND bas_dd<=?",
                        (first, last),
                    ):
                        status[(str(market), str(dd), str(kind))] = True
        except sqlite3.Error:
            return {
                "version": SCHEMA, "status": "BLOCKED_SCHEMA",
                "reason": "MARKET_DB_UNREADABLE", "provider_calls": 0, "db_writes": 0,
            }
    else:
        warnings.append("NEW_DEVICE_MARKET_DB_NOT_PRESENT")

    requested = 0
    raw_hits = 0
    missing = {}
    for market in markets:
        slots = 0
        for day in dates:
            for kind in KINDS:
                if status.get((market, day.strftime("%Y%m%d"), kind)):
                    continue
                slots += 1
                if _valid_raw_cache(cache, market, day, kind, today=current):
                    raw_hits += 1
                else:
                    requested += 1
        missing[market] = slots

    fast_limit = StockScannerService.fast_request_limit()
    try:
        safe_limit = max(1, int(os.getenv("KRX_DAILY_SAFE_LIMIT", str(KrxApiBudget.DEFAULT_SAFE_LIMIT))))
    except (ValueError, TypeError):
        safe_limit = KrxApiBudget.DEFAULT_SAFE_LIMIT
    budget_path = budget_db or KrxApiBudget._default_db
    remaining = None
    if budget_path.is_file():
        try:
            with _readonly(budget_path) as conn:
                day_key = current.isoformat()
                row = conn.execute("SELECT requests FROM krx_daily_usage WHERE day=?", (day_key,)).fetchone()
                remaining = max(0, safe_limit - (int(row[0]) if row else 0))
        except sqlite3.Error:
            warnings.append("LOCAL_BUDGET_UNKNOWN")
    else:
        warnings.append("LOCAL_BUDGET_NOT_INITIALIZED")

    if remaining is not None and requested > remaining:
        result_status = "REVIEW_BUDGET"
    elif requested > fast_limit:
        result_status = "APPROVAL_REQUIRED"
    else:
        result_status = "AUTO_ALLOWED"
    return {
        "version": SCHEMA,
        "status": result_status,
        "market_scope": market_scope,
        "planning_date": end.isoformat(),
        "date_is_confirmed": False,
        "candidate_limit": candidate_limit,
        "store_slots_missing": missing,
        "raw_cache_slots_reusable": raw_hits,
        "estimated_missing_krx_slots": requested,
        "fast_request_limit": fast_limit,
        "daily_budget_remaining": remaining,
        "warnings": warnings,
        "estimate_note": (
            "Estimated base history requests only; holiday discovery, latest-EOD "
            "confirmation, integrity verification and retries may add calls. "
            "The actual Scanner rechecks requirements and enforces its KRX budget."
        ),
        "requires_explicit_large_sync_approval": result_status == "APPROVAL_REQUIRED",
        "provider_calls": 0,
        "db_writes": 0,
    }
