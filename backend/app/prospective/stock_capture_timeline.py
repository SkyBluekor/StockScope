"""G2-03: per-stock immutable Scanner recommendation timeline.

Queries only saved COMPLETE Scanner snapshots, one market+ticker at a time.
Distinct signal dates and capture occurrences are deliberately different.
No scanner rerun, market provider requests, DB migration or trading execution.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.q7_observation_s16 import _record_windows
from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
from app.jev.scanner_shadow_s7 import EVALUATION_SPEC, WINDOWS
from app.prospective.evaluation import ProspectiveEvaluator, ProspectiveEvaluationError
from app.prospective.models import digest_json
from .capture_observation_journal import _conn

VERSION = "STOCKSCOPE_G2_03_STOCK_TIMELINE_V1"
KST = timezone(timedelta(hours=9), name="KST")
TICKER = re.compile(r"^[A-Z0-9]{5,12}$")
MAX_PAGE_SIZE = 30
MAX_OFFSET = 100000


def _response(status: str, **payload: Any) -> dict[str, Any]:
    return {
        "version": VERSION, "status": status, "read_only": True,
        "db_writes": 0, "external_requests": 0,
        "scanner_jobs_created": 0, "real_orders": 0,
        "ranking_recomputed": False, "q7_approved": False,
        "investment_returns_verified": False, **payload,
    }


def _window(status: str, change: float | None = None) -> dict[str, Any]:
    return {"status": status, "signal_close_change_pct": change}


def _observation(sample: dict[str, Any], category: str,
                 evaluator: ProspectiveEvaluator | None, cutoff: str) -> dict[str, Any]:
    if sample["action"] != "ENTRY_CANDIDATE":
        return {f"{w}d": _window("NOT_ENTRY_CANDIDATE") for w in WINDOWS}
    if category not in {"LEGACY_LIMITED", "LOCAL_VALIDATED"}:
        return {f"{w}d": _window("INTEGRITY_NOT_VERIFIED") for w in WINDOWS}
    if evaluator is None:
        return {f"{w}d": _window("MARKET_EVIDENCE_UNAVAILABLE") for w in WINDOWS}
    try:
        evaluation = evaluator.evaluate_sample(
            sample=sample,
            spec={**EVALUATION_SPEC, "as_of_date": cutoff, "require_complete_market_eod": True},
        )
        checked, _ = _record_windows(
            evaluation, datetime.fromisoformat(cutoff).date(),
            signal_date=str(sample["signal_date"]),
        )
        return {
            f"{w}d": _window(
                checked[w][0],
                round(checked[w][1], 4) if checked[w][1] is not None else None,
            ) for w in WINDOWS
        }
    except (ProspectiveEvaluationError, sqlite3.Error, ValueError,
            TypeError, KeyError, OverflowError):
        return {f"{w}d": _window("MARKET_EVIDENCE_UNAVAILABLE") for w in WINDOWS}


def stock_capture_timeline(
    simulation_db: Path, market_db: Path, *, market: str, ticker: str,
    limit: int = 20, offset: int = 0,
) -> dict[str, Any]:
    if (
        market not in {"KOSPI", "KOSDAQ"}
        or type(ticker) is not str or TICKER.fullmatch(ticker) is None
        or type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE
        or type(offset) is not int or not 0 <= offset <= MAX_OFFSET
    ):
        return _response("INVALID_QUERY")
    try:
        with closing(_conn(simulation_db)) as conn:
            conn.execute("BEGIN")
            args = (market, ticker)
            where = (
                "FROM prospective_recommendation_sample s "
                "JOIN prospective_capture_run r ON r.id=s.capture_run_id "
                "WHERE r.status='COMPLETE' AND s.market=? AND s.ticker=?"
            )
            total = conn.execute(
                "SELECT COUNT(*) AS appearances,"
                "COUNT(DISTINCT s.signal_date) AS distinct_signal_days,"
                "MIN(s.signal_date) AS first_signal_date,"
                "MAX(s.signal_date) AS latest_signal_date " + where, args,
            ).fetchone()
            rows = conn.execute(
                "SELECT r.*, s.sample_index AS s_sample_index,"
                "s.capture_run_id AS s_capture_run_id, s.market AS s_market,"
                "s.ticker AS s_ticker, s.name AS s_name,"
                "s.rank AS s_rank, s.strategy AS s_strategy,"
                "s.action AS s_action, s.candidate_state AS s_candidate_state,"
                "s.decision_status AS s_decision_status, s.signal_date AS s_signal_date,"
                "s.snapshot_json AS s_snapshot_json, s.snapshot_hash AS s_snapshot_hash "
                + where +
                " ORDER BY s.signal_date DESC,r.created_at DESC,r.id DESC,s.sample_index ASC"
                " LIMIT ? OFFSET ?",
                (*args, limit + 1, offset),
            ).fetchall()
            raw_page = rows[:limit]
            has_more = len(rows) > limit
            # Count each COMPLETE capture once before reading its metadata.
            cap_ids = {str(r["id"]) for r in raw_page}
            counts = {}
            for capture_id in cap_ids:
                counts[capture_id] = conn.execute(
                    "SELECT COUNT(*) FROM prospective_recommendation_sample "
                    "WHERE capture_run_id=?", (capture_id,),
                ).fetchone()[0]

            cutoff = (datetime.now(KST).date() - timedelta(days=1)).isoformat()
            evaluator = ProspectiveEvaluator(market_db) if Path(market_db).is_file() else None
            entries: list[dict[str, Any]] = []
            for row in raw_page:
                capture_id = str(row["id"])
                if (
                    row["status"] != "COMPLETE" or row["canonical_capture_id"] is not None
                    or type(row["returned_candidate_count"]) is not int
                    or row["returned_candidate_count"] != counts[capture_id]
                    or not 0 <= counts[capture_id] <= 500
                    or row["actual_data_date"] != row["s_signal_date"]
                    or row["s_capture_run_id"] != capture_id
                    or row["s_market"] != market or row["s_ticker"] != ticker
                ):
                    return _response("CAPTURE_INTEGRITY_UNAVAILABLE")
                try:
                    snapshot = json.loads(row["s_snapshot_json"])
                except (ValueError, TypeError):
                    return _response("CAPTURE_INTEGRITY_UNAVAILABLE")
                if (
                    not isinstance(snapshot, dict)
                    or not row["s_snapshot_hash"]
                    or digest_json(snapshot) != row["s_snapshot_hash"]
                    or snapshot.get("data_date") != row["s_signal_date"]
                    or (snapshot.get("market") is not None and snapshot["market"] != market)
                    or (snapshot.get("code") is not None and str(snapshot["code"]) != ticker)
                    or (snapshot.get("strategy") is not None
                        and snapshot["strategy"] != row["s_strategy"])
                    or (snapshot.get("action") is not None
                        and snapshot["action"] != row["s_action"])
                ):
                    return _response("CAPTURE_INTEGRITY_UNAVAILABLE")
                sample = {
                    "sample_index": row["s_sample_index"],
                    "capture_run_id": capture_id,
                    "market": market, "ticker": ticker,
                    "name": row["s_name"], "rank": row["s_rank"],
                    "strategy": row["s_strategy"], "action": row["s_action"],
                    "candidate_state": row["s_candidate_state"],
                    "decision_status": row["s_decision_status"],
                    "signal_date": row["s_signal_date"], "snapshot": snapshot,
                    "snapshot_hash": row["s_snapshot_hash"],
                }
                capture = dict(row)
                try:
                    judgement = assess_frozen_candidate(capture, sample)
                    category = judgement["category"]
                    if category not in {
                        "REFERENCE_ONLY", "LEGACY_LIMITED", "LOCAL_VALIDATED", "INVALID"
                    }:
                        raise DecisionReviewContractError("G2_03_UNSUPPORTED_CATEGORY")
                except (DecisionReviewContractError, KeyError, TypeError, ValueError):
                    category = "INVALID"
                windows = _observation(sample, category, evaluator, cutoff)
                entries.append({
                    "capture_id": capture_id,
                    "signal_date": row["s_signal_date"],
                    "captured_at": row["created_at"],
                    "sample_index": row["s_sample_index"],
                    "name": row["s_name"], "market": market, "ticker": ticker,
                    "strategy": row["s_strategy"],
                    "action": row["s_action"],
                    "candidate_state": row["s_candidate_state"],
                    "rank": row["s_rank"] if type(row["s_rank"]) is int and row["s_rank"] > 0 else None,
                    "integrity_category": category,
                    "scanner_version": row["scanner_version"],
                    "market_scope": row["market_scope"],
                    "candidate_limit": row["candidate_limit"],
                    "windows": windows,
                })
            return _response(
                "READY", market=market, ticker=ticker,
                name=entries[0]["name"] if entries else None,
                summary={
                    "capture_appearances": total["appearances"],
                    "distinct_signal_days": total["distinct_signal_days"],
                    "first_signal_date": total["first_signal_date"],
                    "latest_signal_date": total["latest_signal_date"],
                },
                entries=entries, next_offset=offset + limit if has_more else None,
                limit=limit, offset=offset,
                market_eod_cutoff_date=cutoff,
                observation_basis="SIGNAL_DAY_EOD_CLOSE_NOT_EXECUTABLE_ENTRY",
                note="Only saved returned Scanner candidates; omitted days do not mean the stock was screened and rejected.",
            )
    except (sqlite3.Error, DecisionReviewContractError, OSError, ValueError, TypeError):
        return _response("SOURCE_INTEGRITY_OR_SCHEMA_UNAVAILABLE")
