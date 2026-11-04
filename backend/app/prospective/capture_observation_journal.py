"""User-facing immutable Scanner capture journal with local EOD follow-up.

Read-only SQLite evidence, no API provider, no scanner rerun, no orders and
no policy promotion. A signal-day close change is NOT an executable return.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.q7_observation_s16 import _record_windows
from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
from app.jev.scanner_shadow_s7 import EVALUATION_SPEC, WINDOWS, load_frozen_candidates
from app.prospective.evaluation import ProspectiveEvaluator, ProspectiveEvaluationError

KST = timezone(timedelta(hours=9), name="KST")
VERSION = "STOCKSCOPE_CAPTURE_JOURNAL_V1"
MAX_CAPTURE_RESULTS = 50
MAX_SAMPLES_PER_CAPTURE = 500
EMPTY_WINDOWS = {w: {"status": "AWAITING_FUTURE_DAYS", "signal_close_change_pct": None} for w in WINDOWS}


def _conn(path: Path) -> sqlite3.Connection:
    if not Path(path).is_file():
        raise DecisionReviewContractError("JOURNAL_SIMULATION_DB_MISSING")
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _base(status: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "read_only": True,
        "external_provider_calls": 0,
        "db_writes": 0,
        "scanner_jobs_created": 0,
        "real_orders": 0,
        "q7_approved": False,
        "independent_release_time_verified": False,
        "execution_returns_measured": False,
        **extra,
    }


def list_journal(simulation_db: Path, *, limit: int = 20) -> dict[str, Any]:
    if type(limit) is not int or not 1 <= limit <= MAX_CAPTURE_RESULTS:
        return _base("INVALID_LIMIT", captures=[])
    try:
        with closing(_conn(simulation_db)) as conn:
            rows = conn.execute(
                "SELECT id,status,actual_data_date,market_scope,created_at,"
                "completed_at,returned_candidate_count FROM prospective_capture_run "
                "WHERE status='COMPLETE' ORDER BY created_at DESC,id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return _base("READY", captures=[dict(row) for row in rows])
    except (sqlite3.Error, DecisionReviewContractError, OSError):
        return _base("SOURCE_UNAVAILABLE", captures=[])


def capture_journal(
    simulation_db: Path, market_db: Path, *, capture_id: str,
    as_of: date | None = None,
) -> dict[str, Any]:
    if type(capture_id) is not str or not 1 <= len(capture_id) <= 128:
        return _base("INVALID_CAPTURE_ID", candidates=[])
    today = datetime.now(KST).date()
    if as_of is not None and (type(as_of) is not date or as_of > today):
        return _base("INVALID_AS_OF_DATE", candidates=[])
    cutoff = min(as_of or today, today - timedelta(days=1))
    if not Path(market_db).is_file():
        return _base("MARKET_STORE_MISSING", candidates=[])
    try:
        with closing(_conn(simulation_db)) as conn:
            row = conn.execute(
                "SELECT id,status,actual_data_date,created_at,completed_at,"
                "market_scope,returned_candidate_count FROM prospective_capture_run "
                "WHERE id=?", (capture_id,),
            ).fetchone()
            if row is None:
                return _base("CAPTURE_NOT_FOUND", candidates=[])
            capture = dict(row)
            if capture["status"] != "COMPLETE":
                return _base("CAPTURE_NOT_COMPLETE", candidates=[])
            expected = capture["returned_candidate_count"]
            if type(expected) is not int or not 0 <= expected <= MAX_SAMPLES_PER_CAPTURE:
                return _base("SAMPLE_COUNT_OUT_OF_BOUNDS", candidates=[])
            # All rows must be checked; never silently show a truncated journal.
            actual = int(conn.execute(
                "SELECT COUNT(*) FROM prospective_recommendation_sample WHERE capture_run_id=?",
                (capture_id,),
            ).fetchone()[0])
            if actual != expected:
                return _base("SAMPLE_COUNT_MISMATCH", candidates=[])
        # This loader verifies every frozen sample's SHA256 and canonical
        # COMPLETE capture identity before we use its stock/date fields.
        rows = load_frozen_candidates(
            simulation_db, capture_id=capture_id, limit=MAX_SAMPLES_PER_CAPTURE,
        )
        if len(rows) != expected:
            return _base("CAPTURE_CHANGED_DURING_READ", candidates=[])
        evaluator = ProspectiveEvaluator(market_db)
        candidates: list[dict[str, Any]] = []
        category_counts: dict[str, int] = {}
        for source, sample in rows:
            category = assess_frozen_candidate(source, sample)["category"]
            category_counts[category] = category_counts.get(category, 0) + 1
            windows = {
                f"{w}d": {
                    "status": "NOT_ENTRY_CANDIDATE" if sample["action"] != "ENTRY_CANDIDATE" else "INTEGRITY_NOT_VERIFIED",
                    "signal_close_change_pct": None,
                } for w in WINDOWS
            }
            available = None
            if sample["action"] == "ENTRY_CANDIDATE" and category in {"LOCAL_VALIDATED", "LEGACY_LIMITED"}:
                try:
                    observation = evaluator.evaluate_sample(
                        sample=sample,
                        spec={**EVALUATION_SPEC,
                              "as_of_date": cutoff.isoformat(),
                              "require_complete_market_eod": True},
                    )
                    checked, _ = _record_windows(
                        observation, cutoff,
                        signal_date=str(sample["signal_date"]),
                    )
                    available = observation.get("available_trading_days")
                    windows = {
                        f"{w}d": {
                            "status": checked[w][0],
                            "signal_close_change_pct": (
                                round(checked[w][1], 4) if checked[w][1] is not None else None
                            ),
                        } for w in WINDOWS
                    }
                except (ProspectiveEvaluationError, sqlite3.Error, ValueError,
                        TypeError, KeyError, OverflowError):
                    windows = {
                        f"{w}d": {
                            "status": "MARKET_EVIDENCE_UNAVAILABLE",
                            "signal_close_change_pct": None,
                        } for w in WINDOWS
                    }
            candidates.append({
                "sample_index": sample["sample_index"],
                "market": sample["market"],
                "ticker": sample["ticker"],
                "name": sample["name"],
                "strategy": sample["strategy"],
                "action": sample["action"],
                "rank": sample["rank"],
                "integrity_category": category,
                "available_confirmed_trading_days": available,
                "windows": windows,
            })
        return _base(
            "READY",
            capture={
                **capture, "sample_count": len(candidates),
            },
            market_eod_cutoff_date=cutoff.isoformat(),
            observation_basis="SIGNAL_DAY_EOD_CLOSE_NOT_EXECUTABLE_ENTRY",
            integrity_counts=category_counts,
            candidates=candidates,
        )
    except (sqlite3.Error, DecisionReviewContractError, OSError, ValueError, KeyError, TypeError):
        return _base("SOURCE_INTEGRITY_OR_SCHEMA_UNAVAILABLE", candidates=[])
