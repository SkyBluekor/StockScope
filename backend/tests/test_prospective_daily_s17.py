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
    before = sim.read_bytes()
    report = daily.run_once(
        now=MONDAY, simulation_db=sim, market_db=market,
        log_root=tmp_path / "daily", http=http, server=_server,
    )
    assert sim.read_bytes() == before
    assert report["status"] == "SCANNER_CAPTURED_AND_OUTCOME_CHECKED"
    assert report["source_data_date"] == "2026-10-16"
    assert report["outcome_status"] == "DESCRIPTIVE_OBSERVATIONS_ONLY"
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



def test_s23_completed_daily_run_persists_lineage_status_without_q7_promotion(
    tmp_path, monkeypatch,
):
    sim = _db(tmp_path)
    http, calls = _client()
    examined = []

    def lineage(db, *, capture_id, expected_source_date):
        examined.append((db, capture_id, expected_source_date))
        return {
            "status": "LEGACY_ORIGINAL_IDENTITY_MISSING",
            "reason_code": "ORIGINAL_STRATEGY_IDENTITY_MISSING",
            "strict_jev_input_ready": False,
            "q7_approval_eligible": False,
            "verified_provider_publication_timestamp": False,
            "runtime_db_writes": 0,
            "external_ai_calls": 0,
        }

    monkeypatch.setattr(daily, "audit_daily_capture_readonly", lineage)
    before = sim.read_bytes()
    report = daily.run_once(
        now=MONDAY, simulation_db=sim, market_db=tmp_path / "market.db",
        log_root=tmp_path / "daily", http=http, server=_server,
    )
    assert report["status"] == "SCANNER_CAPTURED_AND_OUTCOME_CHECKED"
    assert examined == [(sim, "capture-1", "2026-10-16")]
    assert report["capture_lineage"]["status"] == "LEGACY_ORIGINAL_IDENTITY_MISSING"
    assert report["q7_approval_eligible"] is False
    assert report["external_ai_calls"] == 0
    import json
    persisted = json.loads(
        (tmp_path / "daily" / "2026-10-19_kospi.json").read_text(encoding="utf-8")
    )
    assert persisted["capture_lineage"]["strict_jev_input_ready"] is False
    assert sim.read_bytes() == before


def test_s23_existing_complete_is_audited_but_pending_is_not(
    tmp_path, monkeypatch,
):
    sim = _db(tmp_path)
    calls = []

    def lineage(db, *, capture_id, expected_source_date):
        calls.append(capture_id)
        return {"status": "SOURCE_CONTRACT_READY_Q7_HOLD",
                "strict_jev_input_ready": True, "q7_approval_eligible": False}

    monkeypatch.setattr(daily, "audit_daily_capture_readonly", lineage)
    with sqlite3.connect(sim) as conn:
        conn.execute(
            "INSERT INTO prospective_capture_run VALUES (?,?,?,?,?,?)",
            ("stored", "KOSPI", "2026-10-16", "2026-10-16",
             "COMPLETE", "2026-10-19T06:58:00+09:00"),
        )
    http, http_calls = _client()
    report = daily.run_once(
        now=MONDAY, simulation_db=sim,
        log_root=tmp_path / "daily", http=http, server=_server,
    )
    assert report["status"] == "SKIPPED_ALREADY_CAPTURED_OR_PENDING"
    assert report["capture_lineage"]["strict_jev_input_ready"] is True
    assert report["capture_lineage"]["q7_approval_eligible"] is False
    assert calls == ["stored"]
    assert len(http_calls) == 1

    with sqlite3.connect(sim) as conn:
        conn.execute("DELETE FROM prospective_capture_run")
        conn.execute(
            "INSERT INTO prospective_capture_run VALUES (?,?,?,?,?,?)",
            ("pending", "KOSPI", "2026-10-16", "2026-10-16",
             "PENDING", "2026-10-19T06:58:00+09:00"),
        )
    other = daily.run_once(
        now=MONDAY, simulation_db=sim, log_root=tmp_path / "daily",
        http=http, server=_server,
    )
    assert other["capture_lineage"]["status"] == "HOLD"
    assert other["capture_lineage"]["strict_jev_input_ready"] is False
    assert calls == ["stored"]
