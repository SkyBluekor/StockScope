"""S22 incremental, source-bound 5/10/20 EOD observation revisions.

PLAN is strictly read-only. APPLY explicitly creates only one new additive table
in the existing simulation DB, never changes frozen samples or earlier reports.
Stored revisions are NEVER trusted without matching current market evidence.
This is not an executable return, fair JEV uplift experiment, or Q7 approval.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import base64
import binascii
import json
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
from app.jev.scanner_shadow_s7 import load_frozen_candidates
from app.market.session_calendar_s21 import (
    CALENDAR_VERSION, closure_evidence, unresolved_weekdays,
)
from app.prospective.models import digest_json

VERSION = "S22_INCREMENTAL_EOD_OBSERVATION_V1"
EVALUATOR_VERSION = "S22_SIGNAL_CLOSE_RETURN_V1"
KST = ZoneInfo("Asia/Seoul")
HORIZONS = (5, 10, 20)
MAX_BATCH_CAPTURES = 40
MAX_SAMPLES_PER_CAPTURE = 499
TABLE = "prospective_observation_revision_s22"
_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_run_id TEXT NOT NULL,
    sample_index INTEGER NOT NULL,
    horizon_days INTEGER NOT NULL CHECK(horizon_days IN (5,10,20)),
    evidence_hash TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    calendar_version TEXT NOT NULL,
    evaluator_version TEXT NOT NULL,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    target_date TEXT NOT NULL,
    reference_close TEXT NOT NULL,
    target_close TEXT NOT NULL,
    close_change_pct REAL NOT NULL,
    source_integrity TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_s22_latest
ON {TABLE}(capture_run_id,sample_index,horizon_days,revision_id);
"""


class IncrementalObservationError(RuntimeError):
    pass


def _result(status: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "scanner_runs": 0, "new_captures": 0, "external_provider_calls": 0,
        "jev_model_calls": 0, "orders": 0, "q7_approval_eligible": False,
        "model_uplift_verified": False, "real_trade_profit_measured": False,
        "independent_precommitment_proven": False,
        **extra,
    }


def _db(db: Path) -> sqlite3.Connection:
    if not db.is_file():
        raise IncrementalObservationError("SOURCE_DB_MISSING")
    c = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    c.execute("BEGIN")
    return c


def _as_of(value: str | None, today: date | None) -> date:
    now = today or datetime.now(KST).date()
    last = now - timedelta(days=1)
    try:
        cutoff = date.fromisoformat(value) if value else last
    except (ValueError, TypeError) as exc:
        raise IncrementalObservationError("AS_OF_DATE_INVALID") from exc
    if cutoff > last:
        raise IncrementalObservationError("FUTURE_OR_TODAY_EOD_FORBIDDEN")
    return cutoff


def _cursor(value: str | None) -> tuple[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= 512:
        raise IncrementalObservationError("CAPTURE_CURSOR_INVALID")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        fields = json.loads(raw)
        if (
            not isinstance(fields, list) or len(fields) != 2
            or not all(type(x) is str and 1 <= len(x) <= 100 for x in fields)
        ):
            raise ValueError()
        return fields[0], fields[1]
    except (ValueError, UnicodeError, binascii.Error, json.JSONDecodeError) as exc:
        raise IncrementalObservationError("CAPTURE_CURSOR_INVALID") from exc


def _encode_cursor(completed: str, capture_id: str) -> str:
    return base64.urlsafe_b64encode(
        json.dumps([completed, capture_id], separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")


def _number(value: Any) -> Decimal | None:
    try:
        d = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return None
    return d if d.is_finite() and d > 0 else None


def _market_days(
    c: sqlite3.Connection, market: str, signal: date, as_of: date,
) -> list[tuple[date, str]]:
    # The actual day list is source evidence; unlike weekday arithmetic it
    # cannot certify an unobserved market session. Strictly require stock AND
    # index rows and both stable completion markers.
    rows = c.execute(
        """
        SELECT d.bas_dd, x.row_json
        FROM day_status d
        JOIN day_status i ON i.market=d.market AND i.bas_dd=d.bas_dd
          AND i.kind='index' AND i.status='data'
        JOIN main_index_daily x ON x.market=d.market AND x.bas_dd=d.bas_dd
        WHERE d.market=? AND d.kind='stock' AND d.status='data'
          AND d.bas_dd>? AND d.bas_dd<=?
          AND EXISTS (
            SELECT 1 FROM stock_daily s
            WHERE s.market=d.market AND s.bas_dd=d.bas_dd
          )
        ORDER BY d.bas_dd
        """,
        (market, signal.strftime("%Y%m%d"), as_of.strftime("%Y%m%d")),
    ).fetchall()
    result: list[tuple[date, str]] = []
    for raw, index_json in rows:
        try:
            parsed = json.loads(index_json)
            index_date = date.fromisoformat(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise IncrementalObservationError("MARKET_INDEX_EVIDENCE_INVALID") from exc
        expected_name = "코스피" if market == "KOSPI" else "코스닥"
        if (not isinstance(parsed, dict) or parsed.get("name") != expected_name
                or str(parsed.get("date")) != raw or _number(parsed.get("close")) is None):
            raise IncrementalObservationError("MARKET_INDEX_EVIDENCE_INVALID")
        result.append((index_date, str(index_json)))
    return result


def _market_row(c: sqlite3.Connection, market: str, ticker: str, day: date) -> str | None:
    row = c.execute(
        "SELECT row_json FROM stock_daily "
        "WHERE market=? AND stock_code=? AND bas_dd=?",
        (market, ticker, day.strftime("%Y%m%d")),
    ).fetchone()
    return str(row[0]) if row else None


def _close(raw: str | None, day: date, ticker: str) -> Decimal | None:
    if raw is None:
        return None
    try:
        row = json.loads(raw)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(row, dict) or str(row.get("date")) != day.strftime("%Y%m%d"):
        return None
    if str(row.get("code", "")).strip().upper() != ticker:
        return None
    return _number(row.get("close"))


def _closure_conflicts(
    c: sqlite3.Connection, market: str, start: date, end: date,
) -> bool:
    day = start + timedelta(days=1)
    while day <= end:
        if closure_evidence(day):
            d = day.strftime("%Y%m%d")
            if (c.execute(
                "SELECT 1 FROM day_status WHERE market=? AND bas_dd=? LIMIT 1",
                (market, d),
            ).fetchone() or c.execute(
                "SELECT 1 FROM stock_daily WHERE market=? AND bas_dd=? LIMIT 1",
                (market, d),
            ).fetchone() or c.execute(
                "SELECT 1 FROM main_index_daily WHERE market=? AND bas_dd=? LIMIT 1",
                (market, d),
            ).fetchone()):
                return True
        day += timedelta(days=1)
    return False


def _fingerprint(
    sample: dict[str, Any], horizon: int, reference: str,
    future: list[tuple[date, str]], candidate_rows: dict[str, str | None],
    category: str,
) -> str:
    # Include every chosen session's index snapshot, target stock rows, source
    # row, frozen candidate hash and contract versions. A changed bar, a new
    # missing intermediate session, or a revised calendar invalidates reuse.
    return digest_json({
        "algorithm": EVALUATOR_VERSION, "calendar": CALENDAR_VERSION,
        "capture_id": sample["capture_run_id"],
        "sample_index": sample["sample_index"], "horizon": horizon,
        "signal_date": sample["signal_date"],
        "ticker": sample["ticker"], "market": sample["market"],
        "snapshot_hash": sample["snapshot_hash"],
        "strategy": sample.get("strategy"), "source_integrity": category,
        "reference_row": reference,
        "session_evidence": [
            [day.isoformat(), index, candidate_rows.get(day.isoformat())]
            for day, index in future[:horizon]
        ],
    })


def _batch(c: sqlite3.Connection, limit: int, cursor: tuple[str, str] | None):
    if cursor:
        rows = c.execute(
            "SELECT id,completed_at FROM prospective_capture_run "
            "WHERE status='COMPLETE' "
            "AND (completed_at>? OR (completed_at=? AND id>?)) "
            "ORDER BY completed_at,id LIMIT ?",
            (cursor[0], cursor[0], cursor[1], limit + 1),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT id,completed_at FROM prospective_capture_run "
            "WHERE status='COMPLETE' ORDER BY completed_at,id LIMIT ?",
            (limit + 1,),
        ).fetchall()
    return [dict(r) for r in rows]


def evaluate_batch(
    simulation_db: Path, market_db: Path, *,
    as_of: str | None = None, after: str | None = None,
    limit_captures: int = 20, today: date | None = None,
) -> dict[str, Any]:
    """Read-only, no on-disk cache creation. Describe future safe insertions."""
    if type(limit_captures) is not int or not 1 <= limit_captures <= MAX_BATCH_CAPTURES:
        raise IncrementalObservationError("BATCH_CAPTURE_LIMIT_INVALID")
    cutoff = _as_of(as_of, today)
    cursor = _cursor(after)
    report: Counter[str] = Counter()
    ready: list[dict[str, Any]] = []
    selected = 0
    next_cursor: str | None = None
    with closing(_db(Path(simulation_db))) as sim, closing(_db(Path(market_db))) as market:
        table_exists = sim.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,),
        ).fetchone() is not None
        rows = _batch(sim, limit_captures, cursor)
        bounded_rows = rows[:limit_captures]
        if len(rows) > limit_captures and bounded_rows:
            last = bounded_rows[-1]
            next_cursor = _encode_cursor(str(last["completed_at"]), str(last["id"]))
        market_day_cache: dict[tuple[str, str], list[tuple[date, str]]] = {}
        for capture in bounded_rows:
            selected += 1
            cid = str(capture["id"])
            count = int(sim.execute(
                "SELECT COUNT(*) FROM prospective_recommendation_sample "
                "WHERE capture_run_id=?", (cid,),
            ).fetchone()[0])
            if count > MAX_SAMPLES_PER_CAPTURE:
                raise IncrementalObservationError("CAPTURE_SAMPLE_LIMIT_EXCEEDED")
            pairs = load_frozen_candidates(Path(simulation_db), capture_id=cid, limit=500)
            if len(pairs) != count:
                raise IncrementalObservationError("CAPTURE_SOURCE_CHANGED")
            for original, sample in pairs:
                if sample["action"] != "ENTRY_CANDIDATE":
                    continue
                report["entry_candidates"] += 1
                category = assess_frozen_candidate(original, sample)["category"]
                report["s7_" + category.lower()] += 1
                if category not in ("LOCAL_VALIDATED", "LEGACY_LIMITED"):
                    continue
                try:
                    signal = date.fromisoformat(str(sample["signal_date"]))
                except ValueError as exc:
                    raise IncrementalObservationError("SIGNAL_DATE_INVALID") from exc
                scope, ticker = str(sample["market"]), str(sample["ticker"])
                if scope not in ("KOSPI", "KOSDAQ"):
                    raise IncrementalObservationError("MARKET_INVALID")
                if signal >= cutoff:
                    report["signal_not_yet_eligible"] += len(HORIZONS)
                    continue
                cache_key = (scope, signal.isoformat())
                if cache_key not in market_day_cache:
                    market_day_cache[cache_key] = _market_days(market, scope, signal, cutoff)
                sessions = market_day_cache[cache_key]
                session_dates = [d for d, _ in sessions]
                source_json = _market_row(market, scope, ticker, signal)
                source_close = _close(source_json, signal, ticker)
                for horizon in HORIZONS:
                    if len(sessions) < horizon:
                        until = cutoff
                    else:
                        until = sessions[horizon - 1][0]
                    if _closure_conflicts(market, scope, signal, until):
                        report["closure_data_conflict"] += 1
                        continue
                    if unresolved_weekdays(signal, until, session_dates):
                        report["unverified_calendar_or_market_gap"] += 1
                        continue
                    if len(sessions) < horizon:
                        report["awaiting_future_trading_days"] += 1
                        continue
                    if source_close is None or source_json is None:
                        report["signal_reference_price_missing"] += 1
                        continue
                    endpoint = sessions[horizon - 1][0]
                    # For a complete horizon only its own sessions matter; no
                    # dependency on future 10d/20d EOD rows.
                    target_rows: dict[str, str | None] = {
                        day.isoformat(): _market_row(market, scope, ticker, day)
                        for day, _ in sessions[:horizon]
                    }
                    target = _close(target_rows[endpoint.isoformat()], endpoint, ticker)
                    if target is None:
                        report["target_price_missing"] += 1
                        continue
                    evid = _fingerprint(
                        sample, horizon, source_json, sessions, target_rows, category,
                    )
                    stored = sim.execute(
                        f"SELECT revision_id,evidence_hash FROM {TABLE} "
                        "WHERE capture_run_id=? AND sample_index=? AND horizon_days=? "
                        "ORDER BY revision_id DESC LIMIT 1",
                        (cid, int(sample["sample_index"]), horizon),
                    ).fetchone() if table_exists else None
                    change = round(
                        float((target - source_close) / source_close * Decimal("100")),
                        4,
                    )
                    if stored is not None and stored["evidence_hash"] == evid:
                        report["cache_hit"] += 1
                        state = "CACHE_HIT"
                    else:
                        report["revision_required" if stored is not None else "new_observation"] += 1
                        state = "REVISION_REQUIRED" if stored is not None else "NEW_OBSERVATION"
                    ready.append({
                        "capture_run_id": cid, "sample_index": int(sample["sample_index"]),
                        "horizon_days": horizon, "evidence_hash": evid,
                        "snapshot_hash": sample["snapshot_hash"],
                        "calendar_version": CALENDAR_VERSION,
                        "evaluator_version": EVALUATOR_VERSION,
                        "market": scope, "ticker": ticker,
                        "signal_date": signal.isoformat(),
                        "target_date": endpoint.isoformat(),
                        "reference_close": str(source_close),
                        "target_close": str(target),
                        "close_change_pct": change,
                        "source_integrity": category,
                        "planned_state": state,
                    })
    return _result(
        "PLAN_ONLY", as_of_eod=cutoff.isoformat(), counts=dict(sorted(report.items())),
        inspected_captures=selected, complete_page=next_cursor is None,
        next_cursor=next_cursor, observed_or_cached=ready,
        calendar_evidence_version=CALENDAR_VERSION,
        actual_market_revision_tracking="ON_READ_FINGERPRINT_ONLY",
        source_scope="LOCAL_FROZEN_CAPTURE_AND_MARKET_EOD",
        simulation_db=str(Path(simulation_db).resolve()),
        market_db=str(Path(market_db).resolve()),
        simulation_db_writes=0, market_db_writes=0,
    )


def apply_batch(
    simulation_db: Path, market_db: Path, *,
    as_of: str | None = None, after: str | None = None,
    limit_captures: int = 20, today: date | None = None,
) -> dict[str, Any]:
    """Persist only matured horizon revisions. Must be explicitly invoked."""
    planned = evaluate_batch(
        simulation_db, market_db, as_of=as_of, after=after,
        limit_captures=limit_captures, today=today,
    )
    pending = [
        r for r in planned["observed_or_cached"]
        if r["planned_state"] != "CACHE_HIT"
    ]
    if not pending:
        return {**planned, "status": "NO_NEW_MATURE_OBSERVATIONS",
                "simulation_db_writes": 0}
    written = revised = 0
    with closing(sqlite3.connect(Path(simulation_db).resolve(), timeout=20)) as conn:
        conn.row_factory = sqlite3.Row
        # executescript() commits pending transactions in sqlite3. Install
        # additive schema BEFORE opening the atomic revision-write transaction.
        conn.executescript(_SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        for item in pending:
            prior = conn.execute(
                f"SELECT evidence_hash FROM {TABLE} "
                "WHERE capture_run_id=? AND sample_index=? AND horizon_days=? "
                "ORDER BY revision_id DESC LIMIT 1",
                (item["capture_run_id"], item["sample_index"], item["horizon_days"]),
            ).fetchone()
            if prior and prior["evidence_hash"] == item["evidence_hash"]:
                continue
            # Immutable revisions, including when the market source changes
            # back to a prior fingerprint; a later revision is still recorded.
            conn.execute(
                f"""INSERT INTO {TABLE} (
                    capture_run_id,sample_index,horizon_days,evidence_hash,
                    snapshot_hash,calendar_version,evaluator_version,
                    market,ticker,signal_date,target_date,
                    reference_close,target_close,close_change_pct,
                    source_integrity,recorded_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item["capture_run_id"], item["sample_index"], item["horizon_days"],
                    item["evidence_hash"], item["snapshot_hash"],
                    item["calendar_version"], item["evaluator_version"],
                    item["market"], item["ticker"], item["signal_date"],
                    item["target_date"], item["reference_close"], item["target_close"],
                    item["close_change_pct"], item["source_integrity"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            written += 1
            if prior:
                revised += 1
        conn.commit()
    return {**planned, "status": "SAVED_INCREMENTAL_OBSERVATIONS",
            "simulation_db_writes": written,
            "new_observations_saved": written - revised,
            "revisions_saved": revised}
