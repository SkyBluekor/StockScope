"""G2-02 user-facing cross-date saved Scanner comparison behavior."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import sqlite3
from pathlib import Path

from app.prospective.models import digest_json
from app.prospective import saved_capture_comparison as diff

OLD = "capture-older"
NEW = "capture-newer"
POLICY = {"market_scope": "ALL", "selection_policy_id": "legacy-policy",
          "selection_policy_hash": "h" * 64}


def _db(tmp_path: Path, *, altered: str | None = None) -> Path:
    path = tmp_path / "simulation.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE prospective_capture_run (
                id TEXT PRIMARY KEY, status TEXT, canonical_capture_id TEXT,
                actual_data_date TEXT, market_scope TEXT, scanner_version TEXT,
                scanner_baseline TEXT, candidate_limit INTEGER, created_at TEXT,
                completed_at TEXT, request_json TEXT, source_execution_key TEXT,
                input_fingerprint TEXT, horizon_intent TEXT, horizon_policy_version TEXT,
                returned_candidate_count INTEGER
            );
            CREATE TABLE prospective_recommendation_sample (
                capture_run_id TEXT,sample_index INTEGER,snapshot_json TEXT,
                snapshot_hash TEXT,signal_date TEXT,market TEXT,ticker TEXT,
                name TEXT,strategy TEXT,action TEXT,rank INTEGER,
                decision_status TEXT,candidate_state TEXT
            );
        """)
        rows = [
            (OLD, "2026-10-26", "2026-10-27T00:04:00+00:00",
             [
                 ("KOSPI", "000000", "첫 종목", "pullback", "ENTRY_CANDIDATE", "READY", 2),
                 ("KOSDAQ", "000001", "사라진 종목", "breakout", "WAIT", "WATCH", 1),
             ]),
            (NEW, "2026-10-27", "2026-10-28T04:51:18+00:00",
             [
                 ("KOSPI", "000000", "첫 종목", "breakout", "WAIT", "WATCH", 1),
                 ("KOSDAQ", "000002", "새 종목", "pullback", "ENTRY_CANDIDATE", "READY", 2),
             ]),
        ]
        for cid, signal, timestamp, candidates in rows:
            conn.execute(
                "INSERT INTO prospective_capture_run VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, "COMPLETE", None, signal, "ALL",
                 "v-1", "baseline-1", 5, timestamp, timestamp,
                 json.dumps(POLICY), "f" * 64, "input", "LEGACY_UNSPECIFIED",
                 None, len(candidates)),
            )
            for index, (market, ticker, name, strategy, action, state, rank) in enumerate(candidates):
                snapshot = {
                    "market": market, "code": ticker, "name": name,
                    "strategy": strategy, "action": action, "data_date": signal,
                    "candidate_state": state, "priority": {"rank": rank},
                    "private": "never leak this exact snapshot",
                }
                conn.execute(
                    "INSERT INTO prospective_recommendation_sample VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, index, json.dumps(snapshot), digest_json(snapshot), signal,
                     market, ticker, name, strategy, action, rank, "WATCH", state),
                )
        if altered == "changed_scope":
            conn.execute("UPDATE prospective_capture_run SET market_scope='KOSPI' WHERE id=?", (OLD,))
        if altered == "changed_policy":
            conn.execute(
                "UPDATE prospective_capture_run SET request_json=? WHERE id=?",
                (json.dumps({**POLICY, "selection_policy_id": "different"}), OLD),
            )
        if altered == "missing_policy":
            conn.execute(
                "UPDATE prospective_capture_run SET request_json=? WHERE id=?",
                (json.dumps({"market_scope": "ALL"}), OLD),
            )
        if altered == "bad_hash":
            conn.execute(
                "UPDATE prospective_recommendation_sample SET snapshot_hash=? "
                "WHERE capture_run_id=? AND sample_index=0", ("0" * 64, NEW),
            )
        if altered == "duplicate_stock":
            conn.execute(
                "UPDATE prospective_recommendation_sample SET ticker='000000' "
                "WHERE capture_run_id=? AND sample_index=1", (NEW,),
            )
    return path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_cross_date_list_change_and_rank_without_db_updates(tmp_path):
    db = _db(tmp_path)
    old_hash = _hash(db)
    result = diff.compare_saved_captures(
        db, previous_capture_id=OLD, current_capture_id=NEW,
    )
    assert result["status"] == "READY"
    assert result["read_only"] is True
    assert result["db_writes"] == result["provider_calls"] == 0
    assert result["scanner_jobs_created"] == result["real_orders"] == 0
    assert result["ranking_recomputed"] is False
    assert result["comparability"] == {
        "rank_comparable": True, "warnings": [],
        "same_market_scope": True, "same_scanner_version": True,
    }
    summary = result["summary"]
    assert (summary["new"], summary["retained"], summary["removed_from_returned_list"]) == (1,1,1)
    assert (summary["rank_up"], summary["rank_down"], summary["strategy_changed"]) == (1,0,1)
    assert summary["action_changed"] == summary["state_changed"] == 1
    members = {x["ticker"]: x for x in result["items"]}
    assert members["000000"]["rank_movement"] == "UP"
    assert members["000000"]["rank_delta"] == 1
    assert members["000000"]["strategy_changed"] is True
    assert members["000001"]["presence"] == "REMOVED"
    assert members["000001"]["current"] is None
    assert members["000002"]["presence"] == "NEW"
    assert members["000002"]["previous"] is None
    assert _hash(db) == old_hash
    assert "never leak this exact snapshot" not in json.dumps(result)


def test_different_selection_policy_preserves_membership_but_disables_rank(tmp_path):
    db = _db(tmp_path, altered="changed_policy")
    result = diff.compare_saved_captures(db, previous_capture_id=OLD, current_capture_id=NEW)
    assert result["status"] == "READY"
    assert result["comparability"]["rank_comparable"] is False
    assert "SELECTION_POLICY_CHANGED" in result["comparability"]["warnings"]
    assert result["summary"]["retained"] == 1
    assert result["summary"]["rank_not_comparable"] == 1
    common = next(x for x in result["items"] if x["ticker"] == "000000")
    assert common["rank_movement"] == "NOT_COMPARABLE"
    assert common["rank_delta"] is None
    assert common["strategy_changed"] is True


def test_changed_market_scope_warning_and_missing_policy_warning(tmp_path):
    db = _db(tmp_path, altered="changed_scope")
    result = diff.compare_saved_captures(db, previous_capture_id=OLD, current_capture_id=NEW)
    assert result["status"] == "READY"
    assert "MARKET_SCOPE_CHANGED" in result["comparability"]["warnings"]
    assert result["comparability"]["rank_comparable"] is False


def test_missing_original_selection_policy_suppresses_rank_comparison(tmp_path):
    db = _db(tmp_path, altered="missing_policy")
    result = diff.compare_saved_captures(db, previous_capture_id=OLD, current_capture_id=NEW)
    assert result["status"] == "READY"
    assert result["comparability"]["rank_comparable"] is False
    assert "SELECTION_POLICY_UNVERIFIED" in result["comparability"]["warnings"]


def test_capture_date_pair_must_be_distinct_and_in_order(tmp_path):
    db = _db(tmp_path)
    assert diff.compare_saved_captures(db, previous_capture_id=OLD, current_capture_id=OLD)["status"] == "INVALID_COMPARISON_PAIR"
    assert diff.compare_saved_captures(db, previous_capture_id=NEW, current_capture_id=OLD)["status"] == "CAPTURES_NOT_IN_CHRONOLOGICAL_ORDER"
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE prospective_capture_run SET actual_data_date='2026-10-27' WHERE id=?", (OLD,))
    assert diff.compare_saved_captures(db, previous_capture_id=OLD, current_capture_id=NEW)["status"] == "CAPTURES_NOT_IN_CHRONOLOGICAL_ORDER"


def test_corrupted_snapshot_fails_closed_and_does_not_mutate_capture(tmp_path):
    db = _db(tmp_path, altered="bad_hash")
    before = _hash(db)
    result = diff.compare_saved_captures(db, previous_capture_id=OLD, current_capture_id=NEW)
    assert result["status"] == "CAPTURE_INTEGRITY_OR_SCHEMA_UNAVAILABLE"
    assert _hash(db) == before


def test_conflicting_sample_identity_fails_closed(tmp_path):
    db = _db(tmp_path, altered="duplicate_stock")
    result = diff.compare_saved_captures(db, previous_capture_id=OLD, current_capture_id=NEW)
    assert result["status"] == "CAPTURE_INTEGRITY_OR_SCHEMA_UNAVAILABLE"


def test_missing_database_and_noncomplete_capture_do_not_create_state(tmp_path):
    missing = tmp_path / "missing.db"
    assert diff.compare_saved_captures(
        missing, previous_capture_id=OLD, current_capture_id=NEW,
    )["status"] == "CAPTURE_INTEGRITY_OR_SCHEMA_UNAVAILABLE"
    assert not missing.exists()
    db = _db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE prospective_capture_run SET status='DUPLICATE' WHERE id=?", (OLD,))
    assert diff.compare_saved_captures(
        db, previous_capture_id=OLD, current_capture_id=NEW,
    )["status"] == "CAPTURE_NOT_COMPLETE"


def test_http_get_route_runs_comparison_without_market_provider_or_scanner(tmp_path, monkeypatch):
    from app.api import prospective as api
    db = _db(tmp_path)
    class StubService:
        catalog = type("Catalog", (), {"db_path": db})()
    monkeypatch.setattr(api, "_service", lambda: StubService())
    response = api.compare_scanner_capture_history(NEW, previous_capture_id=OLD)
    assert response["status"] == "READY"
    assert response["summary"]["retained"] == 1
