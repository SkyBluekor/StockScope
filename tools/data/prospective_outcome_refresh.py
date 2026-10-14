"""S20 opt-in, bounded EOD gap fill for existing frozen prospective candidates.

Read-only PLAN by default. APPLY requires explicit acknowledgment, only appends
verified *missing* market days, never starts Scanner or creates captures.
No trading, JEV, scheduling, historical reconstruction or Q7 approval.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for folder in (ROOT, BACKEND):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app.core.config import get_settings
from app.jev.q7_observation_s16 import measure as observe
from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
from app.jev.scanner_shadow_s7 import load_frozen_candidates
from app.market.providers import KrxProvider
from app.market.session_calendar_s21 import closure_evidence, CALENDAR_VERSION
from tools.data.common import market_db_path, simulation_db_path

VERSION = "STOCKSCOPE_S20_ON_DEMAND_OUTCOME_EOD_GAP_V1"
KST = ZoneInfo("Asia/Seoul")
MAX_SPAN_CALENDAR_DAYS = 90
MAX_CAPTURE_COUNT = 260
MAX_COHORT_SAMPLES = 6000
MAX_CAPTURE_SAMPLES = 499
MAX_APPLY_DAYS = 40
MIN_MARKET_ROWS = 100
MIN_PRIOR_ROW_RATIO = 0.80


class GapFillError(RuntimeError):
    pass


def _result(status: str, **values: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "scanner_runs": 0,
        "new_captures": 0,
        "orders": 0,
        "jev_model_calls": 0,
        "q7_approval_eligible": False,
        "independently_precommitted_predictions_proven": False,
        **values,
    }


def _cutoff(value: str | None, *, today: date | None = None) -> date:
    current = today or datetime.now(KST).date()
    last = current - timedelta(days=1)
    try:
        cutoff = date.fromisoformat(value) if value else last
    except (ValueError, TypeError) as exc:
        raise GapFillError("INVALID_THROUGH_DATE") from exc
    if cutoff > last:
        raise GapFillError("ONLY_PRIOR_CALENDAR_DAY_EOD_ALLOWED")
    return cutoff


def _readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise GapFillError("DATABASE_NOT_FOUND")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _candidates(db: Path, cutoff: date) -> tuple[dict[str, set[date]], dict[str, int]]:
    """Scan only complete cohorts accepted by the existing strict S7 local gate."""
    sources: dict[str, set[date]] = {"KOSPI": set(), "KOSDAQ": set()}
    stats: Counter[str] = Counter()
    with _readonly(db) as c:
        rows = c.execute(
            "SELECT r.id, COUNT(s.sample_index) AS samples "
            "FROM prospective_capture_run r "
            "LEFT JOIN prospective_recommendation_sample s ON s.capture_run_id=r.id "
            "WHERE r.status='COMPLETE' GROUP BY r.id ORDER BY r.completed_at,r.id"
        ).fetchall()
        if len(rows) > MAX_CAPTURE_COUNT or sum(int(x["samples"]) for x in rows) > MAX_COHORT_SAMPLES:
            raise GapFillError("COHORT_EXCEEDS_S16_COMPLETE_AUDIT_BOUND")
        if any(int(x["samples"]) > MAX_CAPTURE_SAMPLES for x in rows):
            raise GapFillError("CAPTURE_TOO_LARGE_FOR_S7_LOADER")
        stats["complete_captures"] = len(rows)
        stats["samples_in_complete_captures"] = sum(int(x["samples"]) for x in rows)
        for row in rows:
            pairs = load_frozen_candidates(db, capture_id=str(row["id"]), limit=500)
            if len(pairs) != int(row["samples"]):
                raise GapFillError("CAPTURE_CHANGED_DURING_PLAN")
            for capture, sample in pairs:
                if sample["action"] != "ENTRY_CANDIDATE":
                    continue
                stats["entry_candidates"] += 1
                category = assess_frozen_candidate(capture, sample)["category"]
                stats["s7_" + category.lower()] += 1
                if category not in ("LOCAL_VALIDATED", "LEGACY_LIMITED"):
                    continue
                market = str(sample["market"])
                if market not in sources:
                    raise GapFillError("CANDIDATE_MARKET_INVALID")
                try:
                    day = date.fromisoformat(str(sample["signal_date"]))
                except ValueError as exc:
                    raise GapFillError("CANDIDATE_DATE_INVALID") from exc
                if day > cutoff:
                    stats["not_yet_eligible"] += 1
                    continue
                sources[market].add(day)
    return sources, dict(sorted(stats.items()))


def _calendar_dates(sources: dict[str, set[date]], cutoff: date) -> dict[str, list[date]]:
    pending: dict[str, list[date]] = {}
    for market, signals in sources.items():
        if not signals:
            pending[market] = []
            continue
        start = min(signals)
        if (cutoff - start).days > MAX_SPAN_CALENDAR_DAYS:
            raise GapFillError("RANGE_TOO_WIDE_FOR_SAFE_BOUNDED_GAP_FILL")
        days: list[date] = []
        cursor = start + timedelta(days=1)
        while cursor <= cutoff:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += timedelta(days=1)
        pending[market] = days
    return pending


def plan(
    simulation_db: Path,
    market_db: Path,
    *,
    through: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """No provider objects, requests, schema migrations, or DB writes."""
    cutoff = _cutoff(through, today=today)
    sim, market = Path(simulation_db).expanduser(), Path(market_db).expanduser()
    sources, cohort_stats = _candidates(sim, cutoff)
    date_ranges = _calendar_dates(sources, cutoff)
    dates: list[dict[str, Any]] = []
    with _readonly(market) as c:
        required_tables = {"day_status", "stock_daily", "main_index_daily"}
        existing_tables = {
            str(r[0]) for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not required_tables.issubset(existing_tables):
            raise GapFillError("MARKET_SCHEMA_INCOMPLETE")
        for scope, days in sorted(date_ranges.items()):
            for day in days:
                evidence = closure_evidence(day)
                if evidence is not None:
                    dates.append({
                        "market": scope, "date": day.isoformat(),
                        "state": "CLOSED_VERIFIED", "stock_rows": 0,
                        "index_rows": 0, "closure_reason": evidence["reason"],
                        "closure_source": evidence["source"],
                    })
                    continue
                key = day.strftime("%Y%m%d")
                status_rows = c.execute(
                    "SELECT kind,status FROM day_status WHERE market=? AND bas_dd=?",
                    (scope, key),
                ).fetchall()
                flags = {str(r["kind"]): str(r["status"]) for r in status_rows}
                stocks = int(c.execute(
                    "SELECT COUNT(*) FROM stock_daily WHERE market=? AND bas_dd=?",
                    (scope, key),
                ).fetchone()[0])
                indexes = int(c.execute(
                    "SELECT COUNT(*) FROM main_index_daily WHERE market=? AND bas_dd=?",
                    (scope, key),
                ).fetchone()[0])
                if flags.get("stock") == "data" and flags.get("index") == "data" and stocks > 0 and indexes == 1:
                    state = "STORED_COMPLETE"
                elif flags or stocks or indexes:
                    state = "PARTIAL_OR_UNVERIFIED_EXISTING"
                else:
                    state = "MISSING"
                dates.append({
                    "market": scope, "date": day.isoformat(), "state": state,
                    "stock_rows": stocks, "index_rows": indexes,
                })
    counts = dict(sorted(Counter(x["state"] for x in dates).items()))
    return _result(
        "PLAN_ONLY", as_of_cutoff=cutoff.isoformat(),
        simulation_db=str(sim.resolve()), market_db=str(market.resolve()),
        cohort=cohort_stats,
        signals_by_market={k: sorted(d.isoformat() for d in v) for k, v in sources.items()},
        date_counts=counts, days=dates,
        exact_trading_calendar_verified=False,
        calendar_evidence_version=CALENDAR_VERSION,
        performance_is_trading_profit=False,
        notice="Only dated, sourced closures are known. MISSING means unresolved weekday without stored rows, NOT a verified open session.",
        runtime_db_writes=0, network_requests=0,
    )


def _commit_new_day(
    market_db: Path, market: str, day: str, stock_rows: list[dict[str, Any]],
    index_row: dict[str, Any],
) -> int:
    """Append one complete market/day as a single transaction; never overwrite."""
    key = date.fromisoformat(day).strftime("%Y%m%d")
    expected_name = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}.get(market)
    if expected_name is None:
        raise GapFillError("MARKET_INVALID")
    if not isinstance(stock_rows, list) or len(stock_rows) < MIN_MARKET_ROWS:
        raise GapFillError("STOCK_RESPONSE_TOO_SMALL")
    if (
        not isinstance(index_row, dict) or index_row.get("name") != expected_name
        or str(index_row.get("date")) != key
        or type(index_row.get("close")) not in (int, float)
        or index_row["close"] <= 0
    ):
        raise GapFillError("MAIN_INDEX_INVALID")
    codes: set[str] = set()
    for row in stock_rows:
        if not isinstance(row, dict):
            raise GapFillError("STOCK_ROW_INVALID")
        code = row.get("code")
        if (
            not isinstance(code, str) or not code.strip()
            or code.strip().upper() in codes or str(row.get("date")) != key
        ):
            raise GapFillError("STOCK_IDENTITY_OR_DATE_INVALID")
        codes.add(code.strip().upper())
    with sqlite3.connect(Path(market_db).resolve(), timeout=20) as c:
        c.execute("PRAGMA busy_timeout=20000")
        c.execute("BEGIN IMMEDIATE")
        existing = (
            c.execute(
                "SELECT COUNT(*) FROM day_status WHERE market=? AND bas_dd=?",
                (market, key),
            ).fetchone()[0]
            + c.execute(
                "SELECT COUNT(*) FROM stock_daily WHERE market=? AND bas_dd=?",
                (market, key),
            ).fetchone()[0]
            + c.execute(
                "SELECT COUNT(*) FROM main_index_daily WHERE market=? AND bas_dd=?",
                (market, key),
            ).fetchone()[0]
        )
        if existing:
            raise GapFillError("EXISTING_DAY_NEVER_REPLACED")
        # Guard against a severely truncated full-market response using the
        # nearest historical full-market day as a local size sanity check.
        prior = c.execute(
            "SELECT bas_dd FROM day_status WHERE market=? AND kind='stock' "
            "AND status='data' AND bas_dd<? ORDER BY bas_dd DESC LIMIT 1",
            (market, key),
        ).fetchone()
        if prior:
            prev_count = c.execute(
                "SELECT COUNT(*) FROM stock_daily WHERE market=? AND bas_dd=?",
                (market, prior[0]),
            ).fetchone()[0]
            if prev_count and len(stock_rows) < MIN_PRIOR_ROW_RATIO * prev_count:
                raise GapFillError("STOCK_RESPONSE_UNEXPECTEDLY_SMALL")
        c.executemany(
            "INSERT INTO stock_daily(market,bas_dd,stock_code,row_json) VALUES(?,?,?,?)",
            [
                (market, key, str(r["code"]).strip().upper(),
                 json.dumps(r, ensure_ascii=False, separators=(",", ":")))
                for r in stock_rows
            ],
        )
        c.execute(
            "INSERT INTO main_index_daily(market,bas_dd,row_json) VALUES(?,?,?)",
            (market, key, json.dumps(index_row, ensure_ascii=False, separators=(",", ":"))),
        )
        c.executemany(
            "INSERT INTO day_status(market,bas_dd,kind,status) VALUES(?,?,?,'data')",
            [(market, key, "stock"), (market, key, "index")],
        )
    return len(stock_rows)


async def apply(
    sim: Path, market_db: Path, *,
    through: str | None = None, provider: KrxProvider | None = None,
    today: date | None = None, max_days: int = MAX_APPLY_DAYS,
) -> dict[str, Any]:
    if type(max_days) is not int or not 1 <= max_days <= MAX_APPLY_DAYS:
        raise GapFillError("INVALID_MAX_DAYS")
    before = plan(sim, market_db, through=through, today=today)
    if before["date_counts"].get("PARTIAL_OR_UNVERIFIED_EXISTING", 0):
        raise GapFillError("PARTIAL_EXISTING_DAYS_REQUIRE_MANUAL_REVIEW")
    missing = [x for x in before["days"] if x["state"] == "MISSING"]
    if len(missing) > max_days:
        raise GapFillError("MISSING_DAY_COUNT_EXCEEDS_EXPLICIT_CAP")
    if not missing:
        observed = observe(sim, market_db, as_of=date.fromisoformat(before["as_of_cutoff"]))
        return _result(
            "NO_MISSING_POTENTIAL_SESSIONS", as_of_cutoff=before["as_of_cutoff"],
            day_counts=before["date_counts"], outcomes=observed,
            runtime_db_writes=0, network_requests=0,
        )
    source = provider or KrxProvider(get_settings().krx_api_key)
    if not source.api_key:
        raise GapFillError("KRX_API_KEY_MISSING")
    # Preflight against the shared KRX quota ledger before any market write.
    # Estimate conservatively: stock and index endpoint for each missing day.
    try:
        source.assert_budget(2 * len(missing))
    except Exception as exc:
        raise GapFillError("KRX_BUDGET_PREFLIGHT_BLOCKED") from exc
    report: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        await source.open_session()
        for target in missing:
            scope, day = target["market"], target["date"]
            try:
                stocks = await source.stock_daily(scope, day)
                indices = await source.index_daily(scope, day)
                if stocks.get("date") != day.replace("-", "") or indices.get("date") != day.replace("-", ""):
                    raise GapFillError("PROVIDER_DATE_MISMATCH")
                rows = stocks.get("rows")
                index_rows = indices.get("rows")
                if not rows and not index_rows:
                    report.append({"market": scope, "date": day, "status": "EMPTY_KRX_UNVERIFIED_CLOSURE"})
                    continue
                if not isinstance(rows, list) or not isinstance(index_rows, list) or not rows or not index_rows:
                    raise GapFillError("INCOMPLETE_PROVIDER_PAIR")
                # An arbitrary fallback index is not sufficient to mark data complete.
                index = next(
                    (r for r in index_rows if r.get("name") == ("코스피" if scope == "KOSPI" else "코스닥")),
                    None,
                )
                if not index:
                    raise GapFillError("MAIN_INDEX_NOT_FOUND")
                size = _commit_new_day(market_db, scope, day, rows, index)
                report.append({"market": scope, "date": day, "status": "STORED_NEW_DAY", "stock_rows": size})
            except (GapFillError, OSError, sqlite3.Error, ValueError, KeyError) as exc:
                reason = str(exc) if isinstance(exc, GapFillError) else type(exc).__name__
                errors.append(f"{scope} {day}: {reason}")
                break
            except Exception as exc:
                # Provider failures must not be silently interpreted as holidays.
                errors.append(f"{scope} {day}: {type(exc).__name__}")
                break
    finally:
        await source.close_session()
    after = plan(sim, market_db, through=through, today=today)
    incomplete = after["date_counts"].get("MISSING", 0) + after["date_counts"].get(
        "PARTIAL_OR_UNVERIFIED_EXISTING", 0
    )
    # S16 itself remains an observation-only statistical instrument and does
    # not persist a new run. Never claim matured 5d/10d/20d data with gaps.
    observed = observe(sim, market_db, as_of=date.fromisoformat(after["as_of_cutoff"]))
    return _result(
        "PARTIAL_OR_UNVERIFIED_GAPS" if incomplete or errors else "MARKET_GAPS_FILLED",
        as_of_cutoff=after["as_of_cutoff"], stored_days=sum(
            item["status"] == "STORED_NEW_DAY" for item in report
        ),
        retrieved_days=report, errors=errors,
        remaining_date_counts=after["date_counts"],
        outstanding_calendar_verification=bool(incomplete),
        outcome_status=observed["status"],
        outcome_windows=observed.get("windows"),
        outcome_trust="DESCRIPTIVE_ONLY_NOT_COMPLETE_IF_GAPS",
        runtime_db_writes=sum(item["status"] == "STORED_NEW_DAY" for item in report),
        network_requests=source.request_stats().get("network_requests"),
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="S20 on-demand EOD market gap fill (never Scanner)")
    p.add_argument("mode", choices=("plan", "apply"))
    p.add_argument("--through", help="Last EOD calendar date, <= KST yesterday")
    p.add_argument("--simulation-db", type=Path, default=None)
    p.add_argument("--market-db", type=Path, default=None)
    p.add_argument("--max-days", type=int, default=MAX_APPLY_DAYS)
    p.add_argument("--acknowledge-market-writes", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        sim, market = args.simulation_db or simulation_db_path(), args.market_db or market_db_path()
        if args.mode == "plan":
            report = plan(sim, market, through=args.through)
        else:
            if not args.acknowledge_market_writes:
                raise GapFillError("APPLY_REQUIRES_EXPLICIT_MARKET_WRITES_ACKNOWLEDGMENT")
            report = asyncio.run(apply(sim, market, through=args.through, max_days=args.max_days))
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if report["status"] in {
            "PLAN_ONLY", "NO_MISSING_POTENTIAL_SESSIONS", "MARKET_GAPS_FILLED"
        } else 2
    except (GapFillError, sqlite3.Error, ValueError) as exc:
        print(json.dumps(_result("BLOCKED", reason=str(exc), runtime_db_writes=0), ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
