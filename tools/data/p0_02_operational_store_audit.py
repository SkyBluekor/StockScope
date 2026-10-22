"""P0-02: inspect only the operational Scanner Market Store, without changing it.

Stdlib only. No KRX provider, HistoricalMarketStore constructor, networking,
account access, SQLite migration, or provider/data-cache side effects.
Prints dates, row counts and missing-marker categories, never stock prices/codes.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
VERSION = "STOCKSCOPE_P0_02_OPERATIONAL_STORE_AUDIT_V1"
MARKETS = ("KOSPI", "KOSDAQ")
KINDS = ("stock", "index")


def _iso(compact: str | None) -> str | None:
    if not compact:
        return None
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": reason,
        "operational_db_read_only": True,
        "provider_calls": 0,
        "db_writes": 0,
        "latest_krx_publication_verified": False,
        "scanner_job_executed": False,
    }


def inspect_operational_store(
    db_path: Path, *,
    as_of: date,
    market_scope: str = "ALL",
    lookback_calendar_days: int = 220,
) -> dict[str, Any]:
    """Read SQLite day_status plus both persisted market row tables.

    A checked/empty day is not proof of an exchange holiday. Equally, matching
    table rows do not prove current KRX publication, strategy lookback sufficiency,
    pricing validity or an actual Scanner result.
    """
    if market_scope not in {"ALL", *MARKETS}:
        raise ValueError("market_scope must be ALL, KOSPI or KOSDAQ")
    if lookback_calendar_days < 1 or lookback_calendar_days > 3650:
        raise ValueError("lookback_calendar_days must be 1..3650")
    markets = MARKETS if market_scope == "ALL" else (market_scope,)
    db = Path(db_path)
    if not db.is_file():
        return _blocked("BLOCKED_OPERATIONAL_DB_MISSING")
    start = as_of - timedelta(days=lookback_calendar_days)
    weekdays = [
        start + timedelta(days=i) for i in range((as_of - start).days + 1)
        if (start + timedelta(days=i)).weekday() < 5
    ]
    first, last = start.strftime("%Y%m%d"), as_of.strftime("%Y%m%d")
    result_by_market: dict[str, Any] = {}
    common_sets: list[set[str]] = []

    try:
        # SQLite's read-only URI protects the original DB while respecting
        # committed WAL records. Never use immutable=1 on a possibly live DB:
        # that could silently ignore not-yet-checkpointed WAL records.
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            tables = {str(row[0]) for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if not {"day_status", "stock_daily", "main_index_daily"}.issubset(tables):
                return _blocked("BLOCKED_MARKET_SCHEMA_MISSING")

            for market in markets:
                markers = {
                    (str(dd), str(kind)): str(status)
                    for dd, kind, status in conn.execute(
                        "SELECT bas_dd,kind,status FROM day_status "
                        "WHERE market=? AND bas_dd>=? AND bas_dd<=?",
                        (market, first, last),
                    )
                }
                stock_counts = {
                    str(dd): int(n)
                    for dd, n in conn.execute(
                        "SELECT bas_dd,COUNT(*) FROM stock_daily "
                        "WHERE market=? AND bas_dd>=? AND bas_dd<=? GROUP BY bas_dd",
                        (market, first, last),
                    )
                }
                index_counts = {
                    str(dd): int(n)
                    for dd, n in conn.execute(
                        "SELECT bas_dd,COUNT(*) FROM main_index_daily "
                        "WHERE market=? AND bas_dd>=? AND bas_dd<=? GROUP BY bas_dd",
                        (market, first, last),
                    )
                }
                validated: dict[str, set[str]] = {kind: set() for kind in KINDS}
                unverified_empty = {kind: 0 for kind in KINDS}
                marker_without_rows = {kind: 0 for kind in KINDS}
                rows_without_data_marker = {kind: 0 for kind in KINDS}
                weekday_gap_examples: list[dict[str, Any]] = []
                for day in weekdays:
                    dd = day.strftime("%Y%m%d")
                    missing: list[str] = []
                    for kind, counts in (("stock", stock_counts), ("index", index_counts)):
                        marker = markers.get((dd, kind))
                        rows = counts.get(dd, 0)
                        if marker == "data" and rows > 0:
                            validated[kind].add(dd)
                            continue
                        if marker == "empty":
                            unverified_empty[kind] += 1
                            missing.append(kind + ":EMPTY_UNVERIFIED_HOLIDAY")
                        elif marker == "data":
                            marker_without_rows[kind] += 1
                            missing.append(kind + ":MARKER_WITHOUT_ROWS")
                        elif rows > 0:
                            rows_without_data_marker[kind] += 1
                            missing.append(kind + ":ROWS_WITHOUT_DATA_MARKER")
                        else:
                            missing.append(kind + ":NO_MARKED_DATA")
                    if missing and len(weekday_gap_examples) < 12:
                        weekday_gap_examples.append({"date": day.isoformat(), "reasons": missing})

                intersection = validated["stock"] & validated["index"]
                common_sets.append(intersection)
                latest = max(intersection) if intersection else None
                result_by_market[market] = {
                    "latest_marked_stock_row_date": _iso(max(validated["stock"])) if validated["stock"] else None,
                    "latest_marked_index_row_date": _iso(max(validated["index"])) if validated["index"] else None,
                    "latest_same_day_stock_index_date": _iso(latest),
                    "latest_same_day_stock_rows": stock_counts.get(latest, 0) if latest else 0,
                    "latest_same_day_index_rows": index_counts.get(latest, 0) if latest else 0,
                    "marked_stock_data_days": len(validated["stock"]),
                    "marked_index_data_days": len(validated["index"]),
                    "same_day_data_days": len(intersection),
                    "weekday_dates_inspected": len(weekdays),
                    "weekdays_without_both_marked_rows": len(weekdays) - len(intersection),
                    "unverified_empty_markers": unverified_empty,
                    "data_markers_without_rows": marker_without_rows,
                    "rows_without_data_markers": rows_without_data_marker,
                    "weekday_gap_examples": weekday_gap_examples,
                    "holiday_calendar_checked": False,
                    "complete_strategy_lookback_proven": False,
                }
    except (sqlite3.DatabaseError, OSError):
        return _blocked("BLOCKED_OPERATIONAL_DB_UNREADABLE")

    common = set.intersection(*common_sets)
    last_common = max(common) if common else None
    return {
        "version": VERSION,
        "status": "STORED_ROW_EVIDENCE_ONLY" if last_common else "NO_COMMON_MARKED_EOD",
        "source": "OPERATIONAL_SCANNER_MARKET_STORE",
        "market_scope": market_scope,
        "as_of_cutoff": as_of.isoformat(),
        "lookback_start": start.isoformat(),
        "lookback_calendar_days": lookback_calendar_days,
        "last_common_marked_stock_index_date": _iso(last_common),
        "calendar_days_behind_cutoff": (
            (as_of - date.fromisoformat(_iso(last_common))).days if last_common else None
        ),
        "markets": result_by_market,
        "provider_data_confirmed": False,
        "official_holidays_checked": False,
        "full_strategy_lookback_proven": False,
        "scanner_job_executed": False,
        "operational_db_read_only": True,
        "provider_calls": 0,
        "db_writes": 0,
        "next_gate": (
            "Verify source calendar/publication permissions and availability, "
            "prepare data using the existing authorized KRX/Scanner path, then "
            "compare an actual Scanner job/capture on the same checked-out SHA."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of real StockScope operational Market Store; no network or DB modifications."
    )
    parser.add_argument("--market-db", type=Path, default=Path(
        os.environ.get("STOCKSCOPE_MARKET_STORE_DB")
        or os.environ.get("STOCKSCOPE_MARKET_DB")
        or DEFAULT_DB
    ))
    parser.add_argument("--as-of", help="YYYY-MM-DD; default: yesterday in Korea")
    parser.add_argument("--market-scope", choices=("ALL", *MARKETS), default="ALL")
    parser.add_argument("--lookback-calendar-days", type=int, default=220)
    args = parser.parse_args()
    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).date()
    as_of = date.fromisoformat(args.as_of) if args.as_of else today_kst - timedelta(days=1)
    if as_of > today_kst:
        parser.error("--as-of must not be after today (Asia/Seoul)")
    try:
        report = inspect_operational_store(
            args.market_db,
            as_of=as_of,
            market_scope=args.market_scope,
            lookback_calendar_days=args.lookback_calendar_days,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["status"].startswith("BLOCKED_") else 0


if __name__ == "__main__":
    raise SystemExit(main())
