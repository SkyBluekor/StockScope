"""G2-03: per-stock saved Scanner timeline behavior and immutability."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from app.prospective.models import digest_json
from app.prospective import stock_capture_timeline as timeline

TICKER = "005930"


def _fixture(tmp_path: Path) -> Path:
    db = tmp_path / "operational_simulation.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
        CREATE TABLE prospective_capture_run (
            id TEXT PRIMARY KEY,status TEXT,canonical_capture_id TEXT,
            actual_data_date TEXT,created_at TEXT,completed_at TEXT,
            returned_candidate_count INTEGER,market_scope TEXT,candidate_limit INTEGER,
            scanner_version TEXT,source_execution_key TEXT,scanner_baseline TEXT,
            input_fingerprint TEXT,horizon_intent TEXT,horizon_policy_version TEXT,
            request_json TEXT
        );
        CREATE TABLE prospective_recommendation_sample (
            capture_run_id TEXT,sample_index INTEGER,
            signal_date TEXT,market TEXT,ticker TEXT,name TEXT,
            rank INTEGER,strategy TEXT,action TEXT,candidate_state TEXT,
            decision_status TEXT,snapshot_json TEXT,snapshot_hash TEXT
        );
        """)
        rows = [
            ("c1", "2026-10-21", "2026-10-22T01:00:00+00:00",
             "KOSPI", TICKER, "삼성전자", "ENTRY_CANDIDATE", 3, "pullback"),
            ("c2", "2026-10-27", "2026-10-28T04:50:00+00:00",
             "KOSPI", TICKER, "삼성전자", "WAIT", 2, "breakout"),
            ("c3", "2026-10-27", "2026-10-28T04:51:18+00:00",
             "KOSPI", TICKER, "삼성전자", "ENTRY_CANDIDATE", 1, "breakout"),
            ("other", "2026-10-27", "2026-10-28T04:53:00+00:00",
             "KOSPI", "000001", "다른종목", "ENTRY_CANDIDATE", 5, "pullback"),
        ]
        for cid, day, timestamp, market, ticker, name, action, rank, strategy in rows:
            con.execute(
                "INSERT INTO prospective_capture_run VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, "COMPLETE", None, day, timestamp, timestamp,
                 1, "ALL", 15, "v1", "f"*64, "baseline",
                 "input", "LEGACY_UNSPECIFIED", None,
                 json.dumps({"market_scope": "ALL"})),
            )
            snapshot = {
                "data_date": day, "market": market, "code": ticker,
                "action": action, "strategy": strategy, "priority": {"rank": rank},
                "private_data": "never-export",
            }
            con.execute(
                "INSERT INTO prospective_recommendation_sample VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, 0, day, market, ticker, name, rank, strategy, action,
                 "WATCH", "WATCH", json.dumps(snapshot), digest_json(snapshot)),
            )
    return db


def _hash(db: Path) -> str:
    return hashlib.sha256(db.read_bytes()).hexdigest()


def _call(db: Path, market: str = "KOSPI", ticker: str = TICKER, **options):
    return timeline.stock_capture_timeline(
        db, db.with_name("no_market.db"), market=market, ticker=ticker, **options,
    )


def test_stock_timeline_pages_only_selected_stock_and_distinguishes_repeat_signal_day(tmp_path):
    db = _fixture(tmp_path)
    before = _hash(db)
    page1 = _call(db, limit=2, offset=0)
    assert page1["status"] == "READY"
    assert page1["summary"] == {
        "capture_appearances": 3, "distinct_signal_days": 2,
        "first_signal_date": "2026-10-21",
        "latest_signal_date": "2026-10-27",
    }
    assert [x["capture_id"] for x in page1["entries"]] == ["c3", "c2"]
    assert page1["next_offset"] == 2
    assert [x["rank"] for x in page1["entries"]] == [1, 2]
    assert page1["entries"][0]["windows"]["5d"]["signal_close_change_pct"] is None
    assert page1["entries"][0]["windows"]["5d"]["status"] == "INTEGRITY_NOT_VERIFIED"
    assert page1["entries"][1]["windows"]["5d"]["status"] == "NOT_ENTRY_CANDIDATE"
    page2 = _call(db, limit=2, offset=2)
    assert page2["status"] == "READY"
    assert [x["capture_id"] for x in page2["entries"]] == ["c1"]
    assert page2["next_offset"] is None
    assert page1["db_writes"] == page1["external_requests"] == 0
    assert page1["ranking_recomputed"] is False
    assert page1["q7_approved"] is False
    assert _hash(db) == before
    assert "never-export" not in json.dumps(page1)


def test_timeline_for_unknown_stock_is_empty_not_fabricated(tmp_path):
    db = _fixture(tmp_path)
    result = _call(db, ticker="999999")
    assert result["status"] == "READY"
    assert result["summary"]["capture_appearances"] == 0
    assert result["entries"] == []
    assert result["next_offset"] is None


def test_timeline_only_existing_complete_captures(tmp_path):
    db = _fixture(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE prospective_capture_run SET status='DUPLICATE' WHERE id='c2'")
    result = _call(db)
    assert result["status"] == "READY"
    assert result["summary"]["capture_appearances"] == 2
    assert {x["capture_id"] for x in result["entries"]} == {"c1", "c3"}


def test_timeline_fails_closed_on_hash_mismatch_without_writes(tmp_path):
    db = _fixture(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE prospective_recommendation_sample SET snapshot_hash=? "
            "WHERE capture_run_id='c3'", ("0"*64,),
        )
    before = _hash(db)
    result = _call(db)
    assert result["status"] == "CAPTURE_INTEGRITY_UNAVAILABLE"
    assert "entries" not in result
    assert _hash(db) == before


def test_timeline_observation_is_still_not_execution_return(tmp_path, monkeypatch):
    db = _fixture(tmp_path)
    market = tmp_path / "market.db"
    with sqlite3.connect(market) as con:
        con.execute("CREATE TABLE placeholder(x)")
    monkeypatch.setattr(timeline, "assess_frozen_candidate",
                        lambda _capture, sample: {
                            "category": "LEGACY_LIMITED" if sample["action"] == "ENTRY_CANDIDATE"
                            else "REFERENCE_ONLY",
                        })

    class FakeEvaluator:
        def __init__(self, path):
            assert path == market
        def evaluate_sample(self, *, sample, spec):
            assert spec["execution_mode"] == "OBSERVATION_ONLY"
            assert spec["require_complete_market_eod"] is True
            return {"available_trading_days": 7}

    monkeypatch.setattr(timeline, "ProspectiveEvaluator", FakeEvaluator)
    monkeypatch.setattr(timeline, "_record_windows",
                        lambda *_args, **_kw: ({
                            5: ("OBSERVED", 2.12346),
                            10: ("AWAITING_FUTURE_DAYS", None),
                            20: ("UNVERIFIED_CALENDAR_OR_DATA_GAP", None),
                        }, None))
    r = timeline.stock_capture_timeline(db, market, market="KOSPI", ticker=TICKER)
    assert r["status"] == "READY"
    assert r["investment_returns_verified"] is False
    assert r["entries"][0]["windows"]["5d"]["signal_close_change_pct"] == 2.1235
    assert r["entries"][0]["windows"]["10d"]["signal_close_change_pct"] is None
    assert r["entries"][0]["windows"]["20d"]["status"] == "UNVERIFIED_CALENDAR_OR_DATA_GAP"


def test_bad_query_and_missing_db_fail_without_creation(tmp_path):
    db = tmp_path / "missing.db"
    assert _call(db)["status"] == "SOURCE_INTEGRITY_OR_SCHEMA_UNAVAILABLE"
    assert not db.exists()
    exists = _fixture(tmp_path)
    for market, ticker, limit, offset in [
        ("UNKNOWN", TICKER, 20, 0),
        ("KOSPI", "5' OR 1=1", 20, 0),
        ("KOSPI", TICKER, 31, 0),
        ("KOSPI", TICKER, 20, -1),
    ]:
        assert _call(exists, market, ticker, limit=limit, offset=offset)["status"] == "INVALID_QUERY"


def test_http_route_timeline_is_get_only_and_uses_existing_db(tmp_path, monkeypatch):
    from app.api import prospective as api
    db = _fixture(tmp_path)
    class FakeService:
        catalog = type("Catalog", (), {"db_path": db})()
        evaluator = type("Eval", (), {"market": type("Market", (), {"db_path": db.with_name("no_market.db")})()})()
    monkeypatch.setattr(api, "_service", lambda: FakeService())
    result = api.get_scanner_stock_timeline("KOSPI", TICKER, limit=20, offset=0)
    assert result["status"] == "READY"
    assert result["summary"]["capture_appearances"] == 3
