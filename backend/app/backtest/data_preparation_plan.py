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
from app.backtest.historical_evidence import validation_start_for_years
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
    # An empty HTTP response (even a stable cached .empty marker) cannot prove
    # an exchange holiday or a complete trading-day snapshot. Conservatively
    # estimate a request unless there is actual usable cached KRX data.
    return False


def plan_scanner_data(
    *,
    market_scope: str = "ALL",
    as_of_date: str | None = None,
    candidate_limit: int = 5,
    market_db: Path | None = None,
    raw_cache_root: Path | None = None,
    budget_db: Path | None = None,
    today: date | None = None,
    history_calendar_days: int | None = None,
) -> dict:
    if market_scope not in {"ALL", *MARKETS} or not 1 <= candidate_limit <= 10:
        raise ValueError("INVALID_SCANNER_PLAN_REQUEST")
    current = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    end = min(date.fromisoformat(as_of_date), current - timedelta(days=1)) if as_of_date else current - timedelta(days=1)
    window = StockScannerService.FAST_HISTORY_CALENDAR_DAYS if history_calendar_days is None else history_calendar_days
    if not isinstance(window, int) or not 1 <= window <= 2000:
        raise ValueError("INVALID_SCANNER_HISTORY_WINDOW")
    start = end - timedelta(days=window)
    markets = MARKETS if market_scope == "ALL" else (market_scope,)
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)
             if (start + timedelta(days=i)).weekday() < 5]

    db = market_db or Path(os.getenv("STOCKSCOPE_MARKET_STORE_DB") or os.getenv("STOCKSCOPE_MARKET_DB")
                           or PROJECT_ROOT / "backend/runtime/market_history/market_history.db")
    cache = raw_cache_root or KrxProvider._cache_dir
    status: dict[tuple[str, str, str], bool] = {}
    # The operational Market Store is the only input. This is NOT a KRX
    # publication-time, official holiday-calendar, or row-content audit.
    persisted_dates: dict[str, dict[str, set[str]]] = {
        market: {kind: set() for kind in KINDS} for market in markets
    }
    incomplete_data_markers: dict[str, set[tuple[str, str]]] = {market: set() for market in markets}
    unverified_empty_markers: dict[str, set[tuple[str, str]]] = {market: set() for market in markets}
    warnings = []
    if db.is_file():
        try:
            with _readonly(db) as conn:
                names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"day_status", "stock_daily", "main_index_daily"}.issubset(names) and names:
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
                    # A day_status='data' flag is not enough: it can survive
                    # a partial/corrupt snapshot or a manual DB restore. Check
                    # the actual market/date rows using PK-backed EXISTS probes.
                    # All of this is read-only, against the operational DB path.
                    for market, dd, kind, label, has_rows in conn.execute(
                        "SELECT ds.market,ds.bas_dd,ds.kind,ds.status, "
                        "CASE WHEN ds.kind='stock' THEN EXISTS("
                        " SELECT 1 FROM stock_daily s "
                        " WHERE s.market=ds.market AND s.bas_dd=ds.bas_dd"
                        ") ELSE EXISTS("
                        " SELECT 1 FROM main_index_daily i "
                        " WHERE i.market=ds.market AND i.bas_dd=ds.bas_dd"
                        ") END "
                        "FROM day_status ds "
                        "WHERE ds.market IN ('KOSPI','KOSDAQ') AND ds.bas_dd<=?",
                        (last,),
                    ):
                        market, dd, kind = str(market), str(dd), str(kind)
                        if market not in persisted_dates or kind not in KINDS:
                            continue
                        try:
                            valid_date = date.fromisoformat(f"{dd[:4]}-{dd[4:6]}-{dd[6:8]}")
                            if len(dd) != 8 or valid_date.strftime("%Y%m%d") != dd:
                                continue
                        except ValueError:
                            continue
                        key = (market, dd, kind)
                        if label == "data" and bool(has_rows):
                            persisted_dates[market][kind].add(dd)
                            if dd >= first:
                                status[key] = True
                        elif dd >= first and label == "data":
                            incomplete_data_markers[market].add((dd, kind))
                        elif dd >= first and label == "empty":
                            unverified_empty_markers[market].add((dd, kind))
        except sqlite3.Error:
            return {
                "version": SCHEMA, "status": "BLOCKED_SCHEMA",
                "reason": "MARKET_DB_UNREADABLE", "provider_calls": 0, "db_writes": 0,
            }
    else:
        warnings.append("NEW_DEVICE_MARKET_DB_NOT_PRESENT")

    if any(incomplete_data_markers.values()):
        warnings.append("MARKET_DATA_MARKER_WITHOUT_PERSISTED_ROWS")
    if any(unverified_empty_markers.values()):
        warnings.append("MARKET_EMPTY_RESPONSE_NOT_PROVEN_HOLIDAY")

    def iso_latest(days: set[str]) -> str | None:
        if not days:
            return None
        dd = max(days)
        return f"{dd[:4]}-{dd[4:6]}-{dd[6:]}"

    # Scope is a true intersection across every selected market AND its
    # stock/index stored-row presence on the same date. Never substitute
    # min(latest(stock), latest(index)) for a proved intersection.
    coincident_days: dict[str, set[str]] = {
        market: persisted_dates[market]["stock"] & persisted_dates[market]["index"]
        for market in markets
    }
    scope_common_days = set.intersection(*(coincident_days[m] for m in markets))
    observed_common_date = iso_latest(scope_common_days)
    operational_eod = {
        "source": "OPERATIONAL_MARKET_STORE_READONLY",
        "market_scope": market_scope,
        "inspection_end": end.isoformat(),
        "lookback_start": start.isoformat(),
        "stored_same_day_stock_index_date": observed_common_date,
        "days_behind_inspection_end": (
            (end - date.fromisoformat(observed_common_date)).days
            if observed_common_date else None
        ),
        "markets": {
            market: {
                "last_stock_rows_date": iso_latest(persisted_dates[market]["stock"]),
                "last_index_row_date": iso_latest(persisted_dates[market]["index"]),
                "last_same_day_rows_date": iso_latest(coincident_days[market]),
                "same_day_rows_in_lookback": sum(dd >= start.strftime("%Y%m%d") for dd in coincident_days[market]),
            }
            for market in markets
        },
        "verification": "DAY_STATUS_DATA_PLUS_PERSISTED_ROW_PRESENCE_ONLY",
        "provider_publication_time_verified": False,
        "official_holiday_calendar_verified": False,
        "full_lookback_ready": False,
        "reason": "Read-only stored-row observation; provider confirmation and trading-calendar/strategy lookback checks are still required.",
    }

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
        "operational_eod": operational_eod,
        "data_markers_missing_rows": {market: len(incomplete_data_markers[market]) for market in markets},
        "unverified_empty_slots": {market: len(unverified_empty_markers[market]) for market in markets},
        "unverified_status_samples": [
            {
                "market": market,
                "date": f"{dd[:4]}-{dd[4:6]}-{dd[6:]}",
                "kind": kind,
                "reason": reason,
            }
            for market in markets
            for reason, slots in (
                ("DATA_MARKER_WITHOUT_ROWS", incomplete_data_markers[market]),
                ("EMPTY_NOT_PROVEN_HOLIDAY", unverified_empty_markers[market]),
            )
            for dd, kind in sorted(slots, reverse=True)
        ][:12],
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


def plan_scanner_evidence_data(
    *,
    market: str,
    data_end: str,
    market_db: Path | None = None,
    raw_cache_root: Path | None = None,
    budget_db: Path | None = None,
    today: date | None = None,
) -> dict:
    """Read-only, fail-closed KRX estimate for explicit 3-year evidence preparation.

    Unlike the fast Scanner plan, this covers the entire validation window and
    technical-indicator warmup. Empty day markers cannot prove a holiday, so
    the estimate is intentionally conservative. The actual provider enforces
    budget limits again when it runs.
    """
    current = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    if market not in MARKETS:
        raise ValueError("INVALID_EVIDENCE_MARKET")
    end = date.fromisoformat(data_end)
    if end > current - timedelta(days=1):
        raise ValueError("EVIDENCE_DATE_NOT_CONFIRMED_EOD")
    validation_start = validation_start_for_years(end)
    warmup_start = validation_start - timedelta(days=StockScannerService.THREE_YEAR_WARMUP_DAYS)
    plan = plan_scanner_data(
        market_scope=market,
        as_of_date=data_end,
        market_db=market_db,
        raw_cache_root=raw_cache_root,
        budget_db=budget_db,
        today=current,
        history_calendar_days=(end - warmup_start).days,
    )
    return {
        **plan,
        "version": "SCANNER_EVIDENCE_DATA_PREFLIGHT_V1",
        "market": market,
        "data_end": end.isoformat(),
        "validation_start": validation_start.isoformat(),
        "warmup_start": warmup_start.isoformat(),
        "requires_explicit_large_sync_approval": plan["status"] == "APPROVAL_REQUIRED",
    }
