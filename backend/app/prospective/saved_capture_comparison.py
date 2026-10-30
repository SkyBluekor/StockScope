"""G2-02: compare two immutable Scanner capture cohorts, never rerun Scanner.

This is a recorded-list difference only, not a ranking model, trading result,
new recommendation, or approval. The existing S7 frozen loader verifies SHA256.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date
import json
from pathlib import Path
import sqlite3
from typing import Any

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_shadow_s7 import load_frozen_candidates
from .capture_observation_journal import _conn

VERSION = "STOCKSCOPE_G2_02_SAVED_CAPTURE_DIFF_V1"
MAX_ROWS = 500

def _reply(status: str, **rest: Any) -> dict[str, Any]:
    return {
        "version": VERSION, "status": status, "read_only": True,
        "db_writes": 0, "provider_calls": 0, "scanner_jobs_created": 0,
        "real_orders": 0, "q7_approved": False,
        "ranking_recomputed": False, "trading_performance_measured": False,
        **rest,
    }


def _read_capture(conn: sqlite3.Connection, capture_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id,status,actual_data_date,market_scope,scanner_version,"
        "scanner_baseline,candidate_limit,created_at,completed_at,request_json,"
        "returned_candidate_count FROM prospective_capture_run WHERE id=?",
        (capture_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    try:
        request = json.loads(result["request_json"])
        if not isinstance(request, dict):
            raise ValueError("invalid request")
        result["selection_policy_id"] = request.get("selection_policy_id")
        result["selection_policy_hash"] = request.get("selection_policy_hash")
    except (ValueError, TypeError):
        result["selection_policy_id"] = None
        result["selection_policy_hash"] = None
    del result["request_json"]
    return result


def _frozen_rows(db: Path, capture: dict[str, Any]) -> list[dict[str, Any]]:
    expected = capture["returned_candidate_count"]
    if type(expected) is not int or not 0 <= expected <= MAX_ROWS:
        raise DecisionReviewContractError("G2_INVALID_SAMPLE_COUNT")
    pairs = load_frozen_candidates(db, capture_id=capture["id"], limit=MAX_ROWS)
    if len(pairs) != expected:
        raise DecisionReviewContractError("G2_SAMPLE_COUNT_MISMATCH")
    out: list[dict[str, Any]] = []
    sample_indices: set[int] = set()
    stock_keys: set[tuple[str, str]] = set()
    for _, sample in pairs:
        snap = sample["snapshot"]
        market, ticker = sample["market"], sample["ticker"]
        index = sample["sample_index"]
        key = (market, ticker)
        if (
            type(index) is not int or index < 0 or index in sample_indices
            or type(market) is not str or market not in {"KOSPI", "KOSDAQ"}
            or type(ticker) is not str or not ticker
            or key in stock_keys
            or sample["capture_run_id"] != capture["id"]
            or sample["signal_date"] != capture["actual_data_date"]
            or (snap.get("market") is not None and snap["market"] != market)
            or (snap.get("code") is not None and str(snap["code"]) != ticker)
            or (snap.get("action") is not None and snap["action"] != sample["action"])
            or (snap.get("strategy") is not None and snap["strategy"] != sample["strategy"])
        ):
            raise DecisionReviewContractError("G2_SAMPLE_IDENTITY_INCONSISTENT")
        sample_indices.add(index)
        stock_keys.add(key)
        # Never infer ranks from array order or recompute a ranking.
        rank = sample["rank"] if type(sample["rank"]) is int and sample["rank"] > 0 else None
        priority = snap.get("priority")
        original_rank = priority.get("rank") if isinstance(priority, dict) else None
        if original_rank is not None and rank != original_rank:
            rank = None
        out.append({
            "sample_index": index, "market": market, "ticker": ticker,
            "name": sample["name"], "strategy": sample["strategy"],
            "action": sample["action"], "candidate_state": sample["candidate_state"],
            "rank": rank,
        })
    if sample_indices != set(range(expected)):
        raise DecisionReviewContractError("G2_SAMPLE_INDICES_NONCONTIGUOUS")
    return out


def compare_saved_captures(
    simulation_db: Path, *, previous_capture_id: str, current_capture_id: str,
) -> dict[str, Any]:
    if any(
        type(x) is not str or not 1 <= len(x) <= 128
        for x in (previous_capture_id, current_capture_id)
    ) or previous_capture_id == current_capture_id:
        return _reply("INVALID_COMPARISON_PAIR")
    try:
        with closing(_conn(simulation_db)) as conn:
            conn.execute("BEGIN")
            previous = _read_capture(conn, previous_capture_id)
            current = _read_capture(conn, current_capture_id)
            if previous is None or current is None:
                return _reply("CAPTURE_NOT_FOUND")
            if previous["status"] != "COMPLETE" or current["status"] != "COMPLETE":
                return _reply("CAPTURE_NOT_COMPLETE")
            try:
                old_day = date.fromisoformat(previous["actual_data_date"])
                new_day = date.fromisoformat(current["actual_data_date"])
            except (ValueError, TypeError):
                return _reply("CAPTURE_DATA_DATE_UNAVAILABLE")
            if old_day >= new_day:
                return _reply("CAPTURES_NOT_IN_CHRONOLOGICAL_ORDER")

            # Count identities in a consistent SQLite read snapshot first.
            for cap in (previous, current):
                count = int(conn.execute(
                    "SELECT COUNT(*) FROM prospective_recommendation_sample "
                    "WHERE capture_run_id=?", (cap["id"],),
                ).fetchone()[0])
                if (type(cap["returned_candidate_count"]) is not int
                        or count != cap["returned_candidate_count"]
                        or count > MAX_ROWS):
                    return _reply("CAPTURE_SAMPLE_COUNT_MISMATCH")

        old_rows = _frozen_rows(simulation_db, previous)
        new_rows = _frozen_rows(simulation_db, current)

        warnings: list[str] = []
        fields = (
            ("market_scope", "MARKET_SCOPE_CHANGED"),
            ("scanner_version", "SCANNER_VERSION_CHANGED"),
            ("scanner_baseline", "SCANNER_BASELINE_CHANGED"),
            ("candidate_limit", "CANDIDATE_LIMIT_CHANGED"),
            ("selection_policy_id", "SELECTION_POLICY_CHANGED"),
            ("selection_policy_hash", "SELECTION_POLICY_CHANGED"),
        )
        for key, code in fields:
            if previous.get(key) != current.get(key) and code not in warnings:
                warnings.append(code)
        # Missing policy evidence cannot establish comparable rank semantics.
        if (not previous.get("selection_policy_id")
                or not current.get("selection_policy_id")
                or not previous.get("selection_policy_hash")
                or not current.get("selection_policy_hash")):
            warnings.append("SELECTION_POLICY_UNVERIFIED")
        ranks_comparable = not warnings
        old_by_key = {(r["market"], r["ticker"]): r for r in old_rows}
        new_by_key = {(r["market"], r["ticker"]): r for r in new_rows}
        keys = sorted(
            set(old_by_key) | set(new_by_key),
            key=lambda k: (
                0 if k in new_by_key else 1,
                (new_by_key.get(k) or old_by_key[k])["sample_index"],
                k,
            ),
        )
        items: list[dict[str, Any]] = []
        summary = {
            "previous_total": len(old_rows), "current_total": len(new_rows),
            "new": 0, "retained": 0, "removed_from_returned_list": 0,
            "rank_up": 0, "rank_down": 0, "rank_same": 0,
            "rank_not_comparable": 0, "strategy_changed": 0,
            "action_changed": 0, "state_changed": 0,
        }
        for key in keys:
            old = old_by_key.get(key)
            new = new_by_key.get(key)
            presence = "RETAINED" if old and new else "NEW" if new else "REMOVED"
            summary[{"RETAINED": "retained", "NEW": "new", "REMOVED": "removed_from_returned_list"}[presence]] += 1
            movement = "NOT_APPLICABLE"
            delta: int | None = None
            if old and new:
                if ranks_comparable and old["rank"] is not None and new["rank"] is not None:
                    delta = old["rank"] - new["rank"]
                    movement = "UP" if delta > 0 else "DOWN" if delta < 0 else "SAME"
                    summary[{"UP": "rank_up", "DOWN": "rank_down", "SAME": "rank_same"}[movement]] += 1
                else:
                    movement = "NOT_COMPARABLE"
                    summary["rank_not_comparable"] += 1
                for field, tally in (
                    ("strategy", "strategy_changed"), ("action", "action_changed"),
                    ("candidate_state", "state_changed"),
                ):
                    if old[field] != new[field]:
                        summary[tally] += 1
            items.append({
                "market": key[0], "ticker": key[1],
                "name": (new or old)["name"],
                "presence": presence,
                "previous": old, "current": new,
                "rank_movement": movement, "rank_delta": delta,
                "strategy_changed": bool(old and new and old["strategy"] != new["strategy"]),
                "action_changed": bool(old and new and old["action"] != new["action"]),
                "state_changed": bool(old and new and old["candidate_state"] != new["candidate_state"]),
            })
        return _reply(
            "READY", previous_capture=previous, current_capture=current,
            comparability={
                "rank_comparable": ranks_comparable,
                "warnings": warnings,
                "same_market_scope": previous["market_scope"] == current["market_scope"],
                "same_scanner_version": previous["scanner_version"] == current["scanner_version"],
            },
            summary=summary, items=items,
            limitation="RETURNED_SCANNER_LIST_DIFFERENCE_NOT_MARKET_EXIT_OR_PROFIT",
        )
    except (DecisionReviewContractError, sqlite3.Error, OSError, ValueError, KeyError, TypeError):
        return _reply("CAPTURE_INTEGRITY_OR_SCHEMA_UNAVAILABLE")
