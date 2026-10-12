"""S7 actual Prospective *schema* + local market-price observation; never API."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta

import pytest

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_shadow_s7 import (
    S7ShadowJournal, inspect_real_candidates, load_frozen_candidates,
)
from app.prospective.models import digest_json
from tools.data.jev_s7_shadow import build_parser, display, execute


def _file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path, *, with_market=True):
    sim = tmp_path / "simulation.sqlite3"
    market = tmp_path / "market.sqlite3"
    with sqlite3.connect(sim) as conn:
        conn.executescript("""
        CREATE TABLE prospective_capture_run(
            id TEXT PRIMARY KEY,status TEXT,canonical_capture_id TEXT,
            source_execution_key TEXT,scanner_version TEXT,
            scanner_baseline TEXT,input_fingerprint TEXT,
            actual_data_date TEXT,horizon_intent TEXT,
            horizon_policy_version TEXT,completed_at TEXT,request_json TEXT
        );
        CREATE TABLE prospective_recommendation_sample(
            capture_run_id TEXT,sample_index INTEGER,snapshot_json TEXT,
            snapshot_hash TEXT,signal_date TEXT,market TEXT,ticker TEXT,
            name TEXT,strategy TEXT,action TEXT,rank INTEGER,
            decision_status TEXT,candidate_state TEXT
        );
        """)
        for cid, status, canonical in [
            ("capt-01", "COMPLETE", None),
            ("dup-01", "DUPLICATE", "capt-01"),
            ("pending-01", "PENDING", None),
        ]:
            conn.execute(
                "INSERT INTO prospective_capture_run VALUES"
                "(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cid, status, canonical, "job", "scanner-v1",
                    "frozen", "input-id", "2026-01-02", "SHORT",
                    "VN_P1_S2_HORIZON_CONTEXT_V1",
                    "2026-01-02T17:05:00+09:00", "{}",
                ),
            )
        for cid, idx, action in [
            ("capt-01", 0, "ENTRY_CANDIDATE"),
            ("capt-01", 1, "REFERENCE_ONLY"),
            ("pending-01", 0, "ENTRY_CANDIDATE"),
        ]:
            snapshot = {
                "action": action, "code": "005930", "name": "가상삼성",
                "market": "KOSPI", "strategy": "MOMENTUM",
                "risk": {"status": "READY", "warning": False},
                "entry_risk_guide": {"price_rule": {"kind": "RANGE",
                                                   "range_low": 100,
                                                   "range_high": 101}},
                "priority": {"rank": idx+1},
                "conditions": {"passed": 2, "total": 2, "missing": 0},
            }
            conn.execute(
                "INSERT INTO prospective_recommendation_sample "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cid, idx, json.dumps(snapshot, ensure_ascii=False),
                    digest_json(snapshot), "2026-01-02", "KOSPI",
                    "005930", "가상삼성", "MOMENTUM",
                    action, idx + 1, "READY", "ELIGIBLE",
                ),
            )
    if with_market:
        with sqlite3.connect(market) as conn:
            conn.executescript("""
            CREATE TABLE day_status(
                bas_dd TEXT, market TEXT, kind TEXT, status TEXT
            );
            CREATE TABLE stock_daily(
                market TEXT, stock_code TEXT, bas_dd TEXT,row_json TEXT
            );
            """)
            days = []
            cursor = date(2026, 1, 2)
            while len(days) < 22:
                if cursor.weekday() < 5:
                    days.append(cursor.strftime("%Y%m%d"))
                cursor += timedelta(days=1)
            for i, day in enumerate(days):
                price = 100 + i
                conn.execute(
                    "INSERT INTO day_status VALUES(?,?,?,?)",
                    (day, "KOSPI", "stock", "data"),
                )
                conn.execute(
                    "INSERT INTO stock_daily VALUES(?,?,?,?)",
                    (
                        "KOSPI", "005930", day,
                        json.dumps({"date": day, "close": price,
                                    "high": price + 1, "low": price - 1}),
                    ),
                )
    return sim, market


def test_readonly_canonical_capture_limit_and_hash(tmp_path):
    sim, market = _fixture(tmp_path)
    before = _file_hash(sim)
    source = load_frozen_candidates(sim)
    assert len(source) == 2
    duplicate = load_frozen_candidates(sim, capture_id="dup-01")
    assert len(duplicate) == 2
    assert all(c["id"] == "capt-01" for c, _ in duplicate)
    assert len(load_frozen_candidates(sim, limit=1)) == 1
    assert _file_hash(sim) == before
    with pytest.raises(DecisionReviewContractError, match="S7_LIMIT_INVALID"):
        load_frozen_candidates(sim, limit=0)
    with pytest.raises(DecisionReviewContractError, match="S7_CAPTURE_NOT_COMPLETE"):
        load_frozen_candidates(sim, capture_id="pending-01")


def test_real_capture_observation_windows_and_holds(tmp_path):
    sim, market = _fixture(tmp_path)
    sim_hash, market_hash = _file_hash(sim), _file_hash(market)
    report = inspect_real_candidates(sim, market)
    assert report["candidate_count"] == 2
    assert report["real_stock_provider_eligible"] == 0
    assert report["model_requests"] == 0
    assert report["investment_uplift_proven"] is False
    assert report["blocker_counts"]["EXTERNAL_SOURCE_RIGHTS_UNVERIFIED"] == 2
    entry = next(r for r in report["records"]
                 if r["baseline_action"] == "ENTRY_CANDIDATE")
    assert entry["review_status"] == "PROVIDER_HOLD"
    assert entry["jev_decision"] is None
    assert entry["baseline_action"] == "ENTRY_CANDIDATE"
    assert entry["observation"]["status"] == "OBSERVATION_ONLY"
    assert entry["observation"]["reference_price"] == 100.0
    assert entry["observation"]["return_5d"] == 5.0
    assert entry["observation"]["return_10d"] == 10.0
    assert entry["observation"]["return_20d"] == 20.0
    assert entry["observation"]["available_trading_days"] == 20
    assert entry["comparison_status"] == "NOT_EVALUATED_NO_AUTHORIZED_JEV"
    reference = next(r for r in report["records"]
                     if r["baseline_action"] == "REFERENCE_ONLY")
    assert reference["observation"]["status"] == "NOT_ENTRY_CANDIDATE"
    assert _file_hash(sim) == sim_hash
    assert _file_hash(market) == market_hash


def test_immutable_research_capture_and_report(tmp_path, capsys):
    sim, market = _fixture(tmp_path)
    separate = tmp_path / "research" / "s7.sqlite3"
    args = build_parser().parse_args([
        "capture", "--simulation-db", str(sim), "--market-db", str(market),
    ])
    report = execute(args, research_db=separate)
    assert report["research_write"] == {"inserted": 2, "reused": 0,
                                        "provider_calls": 0}
    second = execute(args, research_db=separate)
    assert second["research_write"]["inserted"] == 0
    assert second["research_write"]["reused"] == 2
    saved = S7ShadowJournal(separate).report()
    assert saved["candidate_count"] == 2
    assert saved["actual_jev_reviews"] == 0
    assert saved["window_summaries"]["5d"]["observed"] == 1
    assert saved["window_summaries"]["5d"]["average_signal_close_change_pct"] == 5
    assert saved["avoided_loss_pct"] is None
    assert saved["missed_gain_pct"] is None
    display(saved)
    shown = capsys.readouterr().out
    assert "실제 JEV 검토: 0건" in shown
    assert "실제 체결 수익률이 아닙니다" in shown
    with sqlite3.connect(separate) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM jev_s7_local_observation")


def test_missing_market_local_hold_never_invents_returns(tmp_path):
    sim, missing = _fixture(tmp_path, with_market=False)
    result = inspect_real_candidates(sim, missing)
    row = next(r for r in result["records"]
               if r["baseline_action"] == "ENTRY_CANDIDATE")
    assert row["observation"]["status"] == "UNAVAILABLE"
    assert row["observation"]["return_5d"] is None
    assert result["real_jev_review_count"] == 0


def test_actual_provider_cannot_be_activated_by_cli_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "fake-test-credential")
    db = tmp_path/"must_not_exist.sqlite3"
    args = build_parser().parse_args(["run-approved"])
    result = execute(args, research_db=db)
    assert result["status"] == "HOLD"
    assert result["actual_provider_calls"] == 0
    assert result["db_writes"] == 0
    assert not db.exists()


def test_corrupt_snapshot_cannot_be_observed(tmp_path):
    sim, market = _fixture(tmp_path)
    with sqlite3.connect(sim) as conn:
        conn.execute(
            "UPDATE prospective_recommendation_sample "
            "SET snapshot_hash='tampered' WHERE sample_index=0"
        )
    with pytest.raises(DecisionReviewContractError, match="S7_SNAPSHOT_HASH_MISMATCH"):
        inspect_real_candidates(sim, market)
