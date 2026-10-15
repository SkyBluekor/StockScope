"""S25 conservative local last-session evidence gate for research-only Scanner.

No guessed KRX openings: an intervening weekday without a complete EOD
snapshot or a sourced closure is UNKNOWN, not automatically a trading day.
Neither local SQLite timestamps nor this calendar establish market publication
time or independent precommit. Read-only; no market/provider/network writes.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
import sqlite3
from typing import Any

from app.market.session_calendar_s21 import CALENDAR_VERSION, closure_evidence

VERSION = "Q7_S25_LOCAL_MARKET_SESSION_CONTIGUITY_V1"
MAX_LOOKBACK_DAYS = 10


def inspect_latest_session_readonly(
    market_db: Path, *, market: str, latest_eod: date | None, today: date,
) -> dict[str, Any]:
    """Inspect every calendar day since latest *complete* local EOD through yesterday.

    Do not equate an absent local day with verified exchange closure, and do
    not silently ignore stray rows or markers on independently closed days.
    """
    base: dict[str, Any] = {
        "session_gate_version": VERSION,
        "calendar_evidence_version": CALENDAR_VERSION,
        "calendar_audit_through": (today - timedelta(days=1)).isoformat(),
        "unverified_prior_weekday_dates": [],
        "unverified_prior_weekday_states": [],
        "verified_closure_dates": [],
        "closure_data_conflict_dates": [],
        "exchange_calendar_complete": False,
        "market_publication_time_proven": False,
        "independent_prediction_time_proven": False,
        "verified_latest_actual_session": False,
    }
    if latest_eod is None:
        return {**base, "session_evidence_status": "NO_COMPLETE_LOCAL_EOD"}
    age = (today - latest_eod).days
    if age < 1:
        return {**base, "session_evidence_status": "NOT_A_PRIOR_EOD"}
    if age > MAX_LOOKBACK_DAYS:
        return {**base, "session_evidence_status": "SOURCE_EOD_TOO_OLD_FOR_BOUNDED_CHECK"}
    if market not in ("KOSPI", "KOSDAQ"):
        return {**base, "session_evidence_status": "MARKET_INVALID"}

    gap_states: list[dict[str, Any]] = []
    closures: list[dict[str, Any]] = []
    conflicts: list[str] = []
    path = Path(market_db)
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            day = latest_eod
            while day < today:
                stamp = day.strftime("%Y%m%d")
                verified = closure_evidence(day)
                if verified is not None or day > latest_eod:
                    flags = conn.execute(
                        "SELECT kind, status FROM day_status WHERE market=? AND bas_dd=?",
                        (market, stamp),
                    ).fetchall()
                    stocks = conn.execute(
                        "SELECT COUNT(*) FROM stock_daily WHERE market=? AND bas_dd=?",
                        (market, stamp),
                    ).fetchone()[0]
                    indexes = conn.execute(
                        "SELECT COUNT(*) FROM main_index_daily WHERE market=? AND bas_dd=?",
                        (market, stamp),
                    ).fetchone()[0]
                    has_any = bool(flags or stocks or indexes)
                    if verified is not None:
                        closures.append({
                            "date": day.isoformat(),
                            "reason": verified["reason"],
                            "source": verified["source"],
                        })
                        if has_any:
                            conflicts.append(day.isoformat())
                    else:
                        # By construction latest_eod is the MAX complete EOD
                        # before today. Any newer weekday with data markers is
                        # partial/unverified, never an accepted newer session.
                        gap_states.append({
                            "date": day.isoformat(),
                            "state": (
                                "PARTIAL_OR_UNVERIFIED_EXISTING" if has_any
                                else "MISSING"
                            ),
                        })
                day += timedelta(days=1)
    except (sqlite3.Error, OSError):
        return {**base, "session_evidence_status": "LOCAL_MARKET_EVIDENCE_UNAVAILABLE"}

    reason = (
        "CLOSURE_MARKET_DATA_CONFLICT" if conflicts
        else "UNVERIFIED_PRIOR_WEEKDAY_GAP" if gap_states
        else "LOCAL_SESSION_CONTIGUITY_CHECKED"
    )
    return {
        **base,
        "session_evidence_status": reason,
        "unverified_prior_weekday_dates": [x["date"] for x in gap_states],
        "unverified_prior_weekday_states": gap_states,
        "verified_closure_dates": closures,
        "closure_data_conflict_dates": conflicts,
    }
