"""S17 daily: mock only local HTTP; ensure no retroactive/duplicate captures."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from tools.data import prospective_daily as daily


@pytest.fixture(autouse=True)
def _separate_s16_clock_from_synthetic_future_day(monkeypatch):
    """S16 future-date protection is tested separately using real dates."""
    monkeypatch.setattr(
        daily, "observe_outcomes",
        lambda db, market, **kw: {
            "status": "DESCRIPTIVE_OBSERVATIONS_ONLY",
            "windows": {"5d": {"observed": 0}},
        },
    )


KST = ZoneInfo("Asia/Seoul")
MONDAY = datetime(2026, 10, 19, 7, 0, tzinfo=KST)


def _db(tmp_path):
    path = tmp_path / "simulation.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE prospective_capture_run(
                id TEXT PRIMARY KEY,
                market_scope TEXT,
                requested_as_of TEXT,
                actual_data_date TEXT,
                status TEXT,
                created_at TEXT
            );
        """)
    return path


@contextmanager
def _server(_http):
    yield


def _client(fresh_date="2026-10-16", capture="COMPLETE"):
    seen = []
    def http(path, *, method="GET", payload=None, timeout=30):
        seen.append((path, method, payload))
        if path.endswith("/scanner/freshness"):
            return {"status": "READY", "resolved_as_of_date": fresh_date}
        if path.endswith("/scanner/jobs"):
            return {"job_id": "abc123ef01"}
        if path.endswith("/jobs/abc123ef01"):
            return {
                "job_id": "abc123ef01",
                "status": "completed",
                "result": {
                    "requested_as_of": fresh_date,
                    "prospective_capture": {
                        "status": capture, "capture_id": "capture-1",
                        "canonical_capture_id": None,
                        "returned_candidate_count": 15,
                    },
                },
            }
        raise AssertionError(path)
    return http, seen


def test_fresh_next_trading_day_produces_job_and_observations(tmp_path, monkeypatch):
    sim = _db(tmp_path)
    market = tmp_path / "market.db"
    market.write_bytes(b"synthetic")
    monkeypatch.setattr(daily, "observe_outcomes",
        lambda db, m, **kw: {"status": "DESCRIPTIVE_OBSERVATIONS_ONLY",
                             "windows": {"5d": {"observed": 0}}})
    http, calls = _client()
    proof_calls = []
    monkeypatch.setattr(
        daily, "_verify_persisted_capture",
        lambda db, **kw: (
            proof_calls.append((db, kw)) or
            {"persisted_capture_verified": True,
             "persisted_snapshot_hashes_verified": True,
             "persisted_sample_count": 15,
             "performance_verified": False}
        ),
    )
    before = sim.read_bytes()
    report = daily.run_once(
        now=MONDAY, simulation_db=sim, market_db=market,
        log_root=tmp_path / "daily", http=http, server=_server,
    )
    assert sim.read_bytes() == before
    assert report["status"] == "SCANNER_CAPTURED_AND_OUTCOME_CHECKED"
    assert report["source_data_date"] == "2026-10-16"
    assert report["outcome_status"] == "DESCRIPTIVE_OBSERVATIONS_ONLY"
    assert report["persisted_capture_verified"] is True
    assert proof_calls[0][1]["source_job_id"] == "abc123ef01"
    assert report["actual_orders"] == report["external_ai_calls"] == 0
    assert calls[1][0] == "/api/backtest/scanner/jobs"
    assert calls[1][2] == {
        "market_scope": "KOSPI", "as_of_date": "2026-10-16",
        "candidate_limit": 5, "force_refresh": True,
        "allow_large_sync": False, "horizon_intent": None,
    }
    assert (tmp_path / "daily" / "2026-10-19_kospi.json").is_file()
    assert not (tmp_path / "daily" / "2026-10-19_kospi.lock").exists()


def test_existing_capture_blocks_extra_scanner_even_without_runner_journal(tmp_path):
    sim = _db(tmp_path)
    with sqlite3.connect(sim) as conn:
        conn.execute(
            "INSERT INTO prospective_capture_run VALUES (?,?,?,?,?,?)",
            ("capture-prior","KOSPI","2026-10-16","2026-10-16",
             "COMPLETE","2026-10-19T06:58:00+09:00"),
        )
    http, calls = _client()
    report = daily.run_once(now=MONDAY, simulation_db=sim, market_db=tmp_path / "market.db",
                            log_root=tmp_path / "daily", http=http, server=_server)
    assert report["status"] == "SKIPPED_ALREADY_CAPTURED_OR_PENDING"
    assert report["existing_capture_id"] == "capture-prior"
    assert len(calls) == 1


@pytest.mark.parametrize("now,reason", [
    (datetime(2026,10,17,7,tzinfo=KST), "SKIPPED_WEEKEND"),
    (datetime(2026,10,19,12,tzinfo=KST), "SKIPPED_OUTSIDE_PREMARKET_WINDOW"),
    (datetime(2026,10,19,3,tzinfo=KST), "SKIPPED_OUTSIDE_PREMARKET_WINDOW"),
])
def test_nontrading_and_off_window_never_hit_network(tmp_path, now, reason):
    def no_http(*args, **kwargs):
        pytest.fail("no API should run")
    report = daily.run_once(now=now, log_root=tmp_path / "daily", http=no_http, server=_server)
    assert report["status"] == reason
    assert not (tmp_path / "daily").exists()


@pytest.mark.parametrize("value", [
    "2026-10-19", # no current-day EOD
    "2026-10-20", # no future day
    "2026-10-01", # no deep stale catch-up
    "2026-10-14", # too old
    "not-a-day", None,
])
def test_future_or_stale_data_not_scanned(tmp_path, value):
    sim = _db(tmp_path)
    http, calls = _client(fresh_date=value)
    report = daily.run_once(now=MONDAY, simulation_db=sim,
                            log_root=tmp_path / "daily",
                            http=http, server=_server)
    assert report["status"] == "SKIPPED_NO_FRESH_CONFIRMED_EOD"
    assert len(calls) == 1
    assert report["retroactive_capture_created"] is False


def test_running_capture_is_not_duplicated(tmp_path):
    sim = _db(tmp_path)
    with sqlite3.connect(sim) as conn:
        conn.execute(
            "INSERT INTO prospective_capture_run VALUES (?,?,?,?,?,?)",
            ("running-1","KOSPI","2026-10-16",None,
             "PENDING","2026-10-19T07:00:00+09:00"),
        )
    http, calls = _client()
    report = daily.run_once(now=MONDAY, simulation_db=sim,
                            log_root=tmp_path / "daily",
                            http=http, server=_server)
    assert report["status"] == "SKIPPED_ALREADY_CAPTURED_OR_PENDING"
    assert report["existing_capture_status"] == "PENDING"


def test_wrong_capture_status_does_not_claim_success(tmp_path):
    sim = _db(tmp_path)
    http, calls = _client(capture="PARTIAL")
    report = daily.run_once(now=MONDAY, simulation_db=sim,
                            log_root=tmp_path / "daily",
                            http=http, server=_server)
    assert report["status"] == "HOLD_MANUAL_REVIEW"
    assert report["error_code"] == "FROZEN_CAPTURE_NOT_COMPLETE"
    assert report["external_ai_calls"] == 0


def test_lock_prevents_concurrent_run_without_touching_it(tmp_path):
    path = tmp_path / "daily"
    path.mkdir()
    lock = path / "2026-10-19_kospi.lock"
    lock.write_text("live task")
    report = daily.run_once(now=MONDAY, log_root=path, server=_server)
    assert report["status"] == "HOLD_EXISTING_RUN_LOCK"
    assert lock.read_text() == "live task"


def test_backend_is_started_locally_only_and_preexisting_is_not_owned(monkeypatch):
    # Non-network control unit; no actual servers or subprocesses.
    class FakeProcess:
        stopped = False
        def poll(self): return None
        def terminate(self): self.stopped = True
        def wait(self, *, timeout): return 0
    process = FakeProcess()
    calls = []
    monkeypatch.setattr(daily.subprocess, "Popen",
                        lambda args, **kw: (calls.append((args, kw)) or process))
    responses = iter((False, True))
    monkeypatch.setattr(daily, "_check_backend", lambda http: next(responses))
    monkeypatch.setattr(daily.time_module, "sleep", lambda t: None)
    with daily._backend_session(lambda path: {}):
        assert calls[0][0][-4:] == ["--host", "127.0.0.1", "--port", "8000"]
        assert calls[0][1]["cwd"] == daily.BACKEND
    assert process.stopped


def _real_capture(tmp_path):
    """Generate the real VN-P2-S2 schema and a genuine Catalog COMPLETE row."""
    from app.prospective.catalog import ProspectiveCatalog
    from app.prospective.models import ProspectiveCaptureRequest
    from app.strategy.models import StrategyName
    from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store

    db = tmp_path / "real_prospective.db"
    sqlite3.connect(db).close()
    migrate_prospective_store(db)
    catalog = ProspectiveCatalog(db)
    request = ProspectiveCaptureRequest(
        market_scope="KOSPI", requested_as_of="2026-10-16",
        candidate_limit=5, horizon_intent="LEGACY_UNSPECIFIED",
        horizon_policy_version=None,
    )
    result = {
        "version": "synthetic-only", "requested_as_of": "2026-10-16",
        "market_scope": "KOSPI", "input_fingerprint": "synthetic",
        "partial_data": False, "summary": {"candidate_count": 1},
        "candidates": [{
            "market": "KOSPI", "code": "000001", "name": "synthetic",
            "priority": {"rank": 1}, "strategy": StrategyName.TREND_FOLLOWING.value,
            "data_date": "2026-10-16", "action": "ENTRY_CANDIDATE",
            "risk": {"status": "READY", "warning": False},
            "conditions": {"passed": 0, "total": 0, "missing": 0},
            "entry_risk_guide": {},
        }],
        "more_candidates": [],
    }
    catalog.begin_capture(source_job_id="proof-job-123", request=request)
    first = catalog.finalize_capture(
        source_job_id="proof-job-123", request=request, result=result,
    )
    return db, catalog, request, result, first


def _proof(db, capture, job="proof-job-123"):
    return daily._verify_persisted_capture(
        db, source_job_id=job,
        capture={
            "status": capture["status"],
            "capture_id": capture["id"],
            "canonical_capture_id": capture["canonical_capture_id"],
            "returned_candidate_count": capture["returned_candidate_count"],
        },
        signal_date=datetime(2026, 10, 16).date(), market_scope="KOSPI",
    )


def test_p005_g1_real_sqlite_capture_proof_and_duplicate_are_readonly(tmp_path):
    import hashlib

    db, catalog, request, result, first = _real_capture(tmp_path)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    verified = _proof(db, first)
    assert verified["persisted_capture_verified"] is True
    assert verified["persisted_snapshot_hashes_verified"] is True
    assert verified["persisted_sample_count"] == 1
    assert verified["performance_verified"] is False
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before

    catalog.begin_capture(source_job_id="proof-job-456", request=request)
    duplicate = catalog.finalize_capture(
        source_job_id="proof-job-456", request=request, result=result,
    )
    assert duplicate["status"] == "DUPLICATE"
    assert duplicate["canonical_capture_id"] == first["id"]
    before_duplicate = hashlib.sha256(db.read_bytes()).hexdigest()
    assert _proof(db, duplicate, "proof-job-456")["persisted_sample_count"] == 1
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before_duplicate


def test_p005_g1_http_complete_without_sqlite_proof_is_hold(tmp_path):
    db, _, _, _, capture = _real_capture(tmp_path)
    with pytest.raises(daily.DailyError, match="FROZEN_CAPTURE_DB_PROOF_MISMATCH"):
        _proof(db, capture, "fabricated-job")
    claim = {
        "status": "COMPLETE", "capture_id": "not-stored",
        "canonical_capture_id": None, "returned_candidate_count": 1,
    }
    with pytest.raises(daily.DailyError, match="FROZEN_CAPTURE_DB_PROOF_MISMATCH"):
        daily._verify_persisted_capture(
            db, source_job_id="fabricated-job", capture=claim,
            signal_date=datetime(2026, 10, 16).date(), market_scope="KOSPI",
        )
    with pytest.raises(daily.DailyError, match="FROZEN_CAPTURE_PROOF_UNAVAILABLE"):
        _proof(tmp_path / "missing.db", capture)
    assert not (tmp_path / "missing.db").exists()


def test_p005_g1_tampered_snapshot_hash_never_claims_persisted_proof(tmp_path):
    db, _, _, _, capture = _real_capture(tmp_path)
    # Deliberately corrupt *only* a synthetic DB after dropping its fixture
    # protection trigger. Never touch the user's immutable historical rows.
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TRIGGER trg_prospective_sample_immutable")
        conn.execute(
            "UPDATE prospective_recommendation_sample SET snapshot_hash=? "
            "WHERE capture_run_id=?", ("tampered", capture["id"]),
        )
    with pytest.raises(daily.DailyError, match="FROZEN_CAPTURE_SNAPSHOT_MISMATCH"):
        _proof(db, capture)


def test_p005_g1_fake_http_success_cannot_pass_without_sqlite_capture(tmp_path):
    sim = _db(tmp_path)
    http, _ = _client()
    report = daily.run_once(
        now=MONDAY, simulation_db=sim, market_db=tmp_path / "market.db",
        log_root=tmp_path / "daily", http=http, server=_server,
    )
    assert report["status"] == "HOLD_MANUAL_REVIEW"
    assert report["error_code"] == "FROZEN_CAPTURE_DB_READ_UNAVAILABLE"
    assert report["q7_approval_eligible"] is False

