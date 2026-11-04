"""Real saved-capture browser journal: read-only synthetic end-to-end behavior."""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from app.prospective.models import digest_json
from app.prospective import capture_observation_journal as journal


CAPTURE_ID = "g2-browser-journal-test-capture"
SIGNAL_DATE = "2026-10-27"


def fixture(tmp_path: Path) -> tuple[Path, Path]:
    sim = tmp_path / "runtime/simulation/simulation.db"
    market = tmp_path / "runtime/market_history/market_history.db"
    sim.parent.mkdir(parents=True)
    market.parent.mkdir(parents=True)
    with sqlite3.connect(market) as db:
        db.execute("CREATE TABLE market_placeholder(x INTEGER)")
    with sqlite3.connect(sim) as db:
        db.executescript("""
        CREATE TABLE prospective_capture_run (
            id TEXT PRIMARY KEY, status TEXT, actual_data_date TEXT,
            market_scope TEXT,created_at TEXT,completed_at TEXT,
            returned_candidate_count INTEGER,source_execution_key TEXT,
            scanner_version TEXT,scanner_baseline TEXT,input_fingerprint TEXT,
            horizon_intent TEXT,horizon_policy_version TEXT,request_json TEXT,
            canonical_capture_id TEXT
        );
        CREATE TABLE prospective_recommendation_sample (
            capture_run_id TEXT,sample_index INTEGER,snapshot_json TEXT,
            snapshot_hash TEXT,signal_date TEXT,market TEXT,ticker TEXT,
            name TEXT,strategy TEXT,action TEXT,rank INTEGER,
            decision_status TEXT,candidate_state TEXT
        );
        """)
        db.execute(
            "INSERT INTO prospective_capture_run VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (CAPTURE_ID, "COMPLETE", SIGNAL_DATE, "ALL",
             "2026-10-28T04:51:18+00:00", "2026-10-28T04:52:00+00:00", 2,
             "f" * 64, "v", "base", "fingerprint", "LEGACY_UNSPECIFIED",
             None, json.dumps({"market_scope": "ALL"}), None),
        )
        for index, action in enumerate(("ENTRY_CANDIDATE", "WAIT")):
            snap = {"data_date": SIGNAL_DATE, "code": f"{index:06d}",
                    "action": action, "private": "do-not-export"}
            db.execute(
                "INSERT INTO prospective_recommendation_sample VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (CAPTURE_ID,index,json.dumps(snap),digest_json(snap),SIGNAL_DATE,
                 "KOSPI","%06d" % index,"종목", "pullback", action,
                 index + 1,"WATCH","WATCH"),
            )
    return sim, market


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_journal_lists_saved_complete_without_network_or_writes(tmp_path):
    sim, market = fixture(tmp_path)
    before = digest(sim)
    r = journal.list_journal(sim, limit=10)
    assert r["status"] == "READY"
    assert r["captures"][0]["id"] == CAPTURE_ID
    assert r["captures"][0]["returned_candidate_count"] == 2
    assert r["read_only"] is True
    assert r["external_provider_calls"] == r["db_writes"] == 0
    assert digest(sim) == before
    assert "do-not-export" not in json.dumps(r)


def test_journal_shows_entry_and_reference_windows_without_execution(tmp_path, monkeypatch):
    sim, market = fixture(tmp_path)
    original = digest(sim)
    original_market = digest(market)

    def assess(_capture, sample):
        return {"category": "LEGACY_LIMITED" if sample["action"] == "ENTRY_CANDIDATE"
                else "REFERENCE_ONLY"}

    class FakeEvaluator:
        def __init__(self, path):
            assert path == market
        def evaluate_sample(self, *, sample, spec):
            assert spec["execution_mode"] == "OBSERVATION_ONLY"
            assert spec["require_complete_market_eod"] is True
            assert "as_of_date" in spec
            assert sample["snapshot"]["private"] == "do-not-export"
            return {"available_trading_days": 0}

    def windows(_result, _cutoff, *, signal_date):
        assert signal_date == SIGNAL_DATE
        return {
            5: ("AWAITING_FUTURE_DAYS", None),
            10: ("AWAITING_FUTURE_DAYS", None),
            20: ("AWAITING_FUTURE_DAYS", None),
        }, None

    monkeypatch.setattr(journal, "assess_frozen_candidate", assess)
    monkeypatch.setattr(journal, "ProspectiveEvaluator", FakeEvaluator)
    monkeypatch.setattr(journal, "_record_windows", windows)
    result = journal.capture_journal(sim, market, capture_id=CAPTURE_ID)
    assert result["status"] == "READY"
    assert len(result["candidates"]) == 2
    assert result["integrity_counts"] == {"LEGACY_LIMITED": 1, "REFERENCE_ONLY": 1}
    assert result["candidates"][0]["windows"]["5d"] == {
        "status": "AWAITING_FUTURE_DAYS", "signal_close_change_pct": None
    }
    assert result["candidates"][1]["windows"]["20d"] == {
        "status": "NOT_ENTRY_CANDIDATE", "signal_close_change_pct": None
    }
    assert result["external_provider_calls"] == result["db_writes"] == 0
    assert result["q7_approved"] is False
    assert result["execution_returns_measured"] is False
    assert digest(sim) == original and digest(market) == original_market
    assert "do-not-export" not in json.dumps(result)


def test_journal_only_displays_observed_change_when_market_window_is_proven(tmp_path, monkeypatch):
    sim, market = fixture(tmp_path)
    monkeypatch.setattr(journal, "assess_frozen_candidate",
                        lambda _capture, sample: {
                            "category": "LEGACY_LIMITED" if sample["action"] == "ENTRY_CANDIDATE"
                            else "REFERENCE_ONLY"
                        })
    class FakeEvaluator:
        def __init__(self, _path):
            pass
        def evaluate_sample(self, *, sample, spec):
            assert spec["execution_mode"] == "OBSERVATION_ONLY"
            return {"available_trading_days": 7}

    monkeypatch.setattr(journal, "ProspectiveEvaluator", FakeEvaluator)
    monkeypatch.setattr(journal, "_record_windows", lambda *_args, **_kw: ({
        5: ("OBSERVED", 1.234567),
        10: ("AWAITING_FUTURE_DAYS", None),
        20: ("UNVERIFIED_CALENDAR_OR_DATA_GAP", None),
    }, None))
    r = journal.capture_journal(sim, market, capture_id=CAPTURE_ID)
    entry = r["candidates"][0]
    assert entry["windows"]["5d"]["signal_close_change_pct"] == 1.2346
    assert entry["windows"]["10d"]["signal_close_change_pct"] is None
    assert entry["windows"]["20d"]["status"] == "UNVERIFIED_CALENDAR_OR_DATA_GAP"


def test_journal_fail_closed_on_corrupt_snapshot_and_no_trading(tmp_path):
    sim, market = fixture(tmp_path)
    with sqlite3.connect(sim) as db:
        db.execute("UPDATE prospective_recommendation_sample SET snapshot_hash=? WHERE sample_index=0",
                   ("0" * 64,))
    before = digest(sim)
    r = journal.capture_journal(sim, market, capture_id=CAPTURE_ID)
    assert r["status"] == "SOURCE_INTEGRITY_OR_SCHEMA_UNAVAILABLE"
    assert r["candidates"] == []
    assert digest(sim) == before


def test_journal_never_treats_missing_db_as_empty_initialized_db(tmp_path):
    sim = tmp_path / "no.db"
    market = tmp_path / "market.db"
    assert journal.list_journal(sim)["status"] == "SOURCE_UNAVAILABLE"
    assert journal.capture_journal(sim, market, capture_id=CAPTURE_ID)["status"] == "MARKET_STORE_MISSING"
    assert not sim.exists() and not market.exists()


def test_journal_empty_and_duplicate_status_not_misrepresented(tmp_path):
    sim, market = fixture(tmp_path)
    assert journal.capture_journal(sim, market, capture_id="missing")["status"] == "CAPTURE_NOT_FOUND"
    assert journal.capture_journal(sim, market, capture_id="")["status"] == "INVALID_CAPTURE_ID"
    assert journal.capture_journal(sim, market, capture_id=CAPTURE_ID, as_of=date(9999,1,1))["status"] == "INVALID_AS_OF_DATE"
    with sqlite3.connect(sim) as db:
        db.execute("UPDATE prospective_capture_run SET status='DUPLICATE'")
    assert journal.list_journal(sim)["captures"] == []
    assert journal.capture_journal(sim, market, capture_id=CAPTURE_ID)["status"] == "CAPTURE_NOT_COMPLETE"


def test_browser_get_endpoints_use_journal_without_scanner_run(tmp_path, monkeypatch):
    from app.api import prospective as api
    sim, market = fixture(tmp_path)

    class DummyService:
        catalog = type("Cat", (), {"db_path": sim})()
        evaluator = type("Eval", (), {"market": type("M", (), {"db_path": market})()})()

    monkeypatch.setattr(api, "_service", lambda: DummyService())
    response = api.list_scanner_capture_journal(limit=10)
    assert response["status"] == "READY"
    assert response["captures"][0]["id"] == CAPTURE_ID
    # If frozen integrity is not complete, show a safe error, not an invented outcome.
    assert api.get_scanner_capture_observation_journal("missing")["status"] == "CAPTURE_NOT_FOUND"
