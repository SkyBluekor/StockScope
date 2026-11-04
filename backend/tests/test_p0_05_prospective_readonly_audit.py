"""P0-05/G0: genuine Prospective schema, synthetic local DBs and no side effects."""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.data.p0_05_prospective_readonly_audit import inspect, VERSION


def _sha(db: Path) -> str:
    return hashlib.sha256(db.read_bytes()).hexdigest()


def _env(tmp_path: Path):
    sim, market = tmp_path / "simulation.db", tmp_path / "market.db"
    sqlite3.connect(sim).close()
    migrate_prospective_store(sim)
    with sqlite3.connect(market) as c:
        c.executescript(
            "CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT);"
            "CREATE TABLE main_index_daily(market TEXT,bas_dd TEXT,row_json TEXT);"
        )
        # Six real source date labels; deliberately no stock prices for any
        # candidate. Eligibility != actual observed returns.
        start = date(2026, 10, 12)
        days = [start + timedelta(days=i) for i in range(12)]
        days = [d for d in days if d.weekday() < 5][:7]
        for d in days:
            stamp = d.strftime("%Y%m%d")
            c.execute("INSERT INTO day_status VALUES (?,?,?,?)",
                      ("KOSPI",stamp,"stock","data"))
            c.execute("INSERT INTO main_index_daily VALUES (?,?,?)",
                      ("KOSPI",stamp,"{}"))
    return sim, market


def _capture(db: Path, capture_id: str, *, status: str = "COMPLETE",
             canonical: str | None = None, fingerprint: str | None = "private-fingerprint",
             as_of: str = "2026-10-12", source_key: str | None = "key1"):
    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT INTO prospective_capture_run("
            "id,capture_version,source_job_id,source_execution_key,"
            "canonical_capture_id,status,request_json,scanner_version,"
            "scanner_baseline,market_scope,requested_as_of,actual_data_date,"
            "input_fingerprint,horizon_intent,horizon_policy_version,"
            "candidate_limit,actionable_candidate_count,returned_candidate_count,"
            "created_at,completed_at,updated_at"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                capture_id, "VN_P2_S2_V1", "job-" + capture_id,
                source_key,canonical,status,
                json.dumps({"private": "DO_NOT_LEAK_SECRET"}),
                "scanner-1","baseline-1","KOSPI",as_of,as_of,
                fingerprint,"UNSPECIFIED","HORIZON-1",5,1,1,
                "2026-10-13T07:00:00+09:00",
                "2026-10-13T07:05:00+09:00",
                "2026-10-13T07:05:00+09:00",
            ),
        )


def _sample(db: Path, capture: str, idx: int, *,
            date_str: str = "2026-10-12", action: str = "ENTRY_CANDIDATE",
            ticker: str = "SECRET_005930"):
    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT INTO prospective_recommendation_sample("
            "capture_run_id,sample_index,market,ticker,name,rank,strategy,"
            "decision_status,candidate_state,action,signal_date,"
            "snapshot_json,snapshot_hash,created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                capture,idx,"KOSPI",ticker,"PRIVATE_STOCK",1,"pullback",
                "WATCH","WATCH",action,date_str,
                '{"private":"PRIVATE_SNAPSHOT_CONTENT"}',"SECRET_HASH",
                "2026-10-13T07:03:00+09:00",
            ),
        )


def test_capture_inventory_real_schema_and_market_session_windows(tmp_path: Path):
    sim, market = _env(tmp_path)
    _capture(sim, "cap-1")
    _sample(sim, "cap-1", 0)
    _sample(sim, "cap-1", 1, action="REFERENCE_ONLY")
    before = _sha(sim), _sha(market)
    result = inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["version"] == VERSION
    assert result["status"] == "READ_ONLY_PROSPECTIVE_INVENTORY_OBSERVED"
    assert result["capture_status_counts"]["COMPLETE"] == 1
    assert result["complete_capture_samples"] == 2
    assert result["entry_candidate_rows"] == 1
    assert result["reference_or_other_samples"] == 1
    assert result["market_session_window_eligibility"]["5d"] == {
        "entry_candidate_rows": 1,
        "market_sessions_reached": 1,
        "awaiting_market_sessions": 0,
        "market_evidence_unknown": 0,
    }
    assert result["market_session_window_eligibility"]["10d"]["awaiting_market_sessions"] == 1
    assert result["market_session_window_eligibility"]["20d"]["awaiting_market_sessions"] == 1
    assert result["stored_evaluation_inventory"]["windows_with_nonnull_stored_return_rows"]["5d"] == 0
    assert result["official_latest_eod_verified"] is False
    assert result["production_activation_allowed"] is False
    serialized = json.dumps(result)
    for private in ("SECRET_005930","PRIVATE_STOCK","DO_NOT_LEAK_SECRET",
                    "PRIVATE_SNAPSHOT_CONTENT","SECRET_HASH","cap-1","job-cap-1",
                    "private-fingerprint"):
        assert private not in serialized
    assert (_sha(sim),_sha(market)) == before


def test_duplicate_capture_status_does_not_become_extra_complete_sample(tmp_path: Path):
    sim, market = _env(tmp_path)
    _capture(sim, "cap-one")
    _sample(sim, "cap-one", 0)
    _capture(sim, "cap-duplicate", status="DUPLICATE", canonical="cap-one")
    _capture(sim, "cap-partial", status="PARTIAL", source_key="partial")
    _sample(sim, "cap-partial", 0)
    result = inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["capture_count"] == 3
    assert result["capture_status_counts"] == {
        "COMPLETE": 1, "DUPLICATE": 1, "PARTIAL": 1,
    }
    assert result["complete_capture_samples"] == 1
    assert result["entry_candidate_rows"] == 1
    assert result["evidence_anomaly_counts"]["duplicate_capture_scope_and_date_rows"] == 2
    assert result["evidence_anomaly_counts"]["invalid_canonical_capture_links"] == 0


def test_distinct_duplicate_signal_keys_are_not_independent_samples(tmp_path: Path):
    sim, market = _env(tmp_path)
    _capture(sim, "cap-1", source_key="key1")
    _sample(sim, "cap-1", 0)
    _capture(sim, "cap-2", source_key="key2")
    _sample(sim, "cap-2", 0)
    result = inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"] == "READ_ONLY_PROSPECTIVE_INVENTORY_OBSERVED"
    assert result["entry_candidate_rows"] == 2
    assert result["distinct_entry_signal_keys"] == 1
    assert result["evidence_anomaly_counts"]["duplicate_entry_signal_keys"] == 1
    assert result["q7_approval_eligible"] is False


def test_no_schema_or_missing_db_returns_hold_without_creation(tmp_path: Path):
    sim = tmp_path / "missing-sim.db"
    market = tmp_path / "missing-market.db"
    assert inspect(sim, market)["status"] == "HOLD_SIMULATION_DB_MISSING"
    assert not sim.exists()
    sqlite3.connect(sim).close()
    assert inspect(sim, market)["status"] == "HOLD_MARKET_DB_MISSING"
    sqlite3.connect(market).close()
    assert inspect(sim, market)["status"] == "HOLD_PROSPECTIVE_SCHEMA_NOT_READY"
    with sqlite3.connect(sim) as c:
        c.execute("CREATE TABLE prospective_capture_run(id TEXT)")
        c.execute("CREATE TABLE prospective_recommendation_sample(id TEXT)")
    with sqlite3.connect(market) as c:
        c.execute("CREATE TABLE day_status(id TEXT)")
        c.execute("CREATE TABLE main_index_daily(id TEXT)")
    assert inspect(sim, market)["status"] == "HOLD_SCHEMA_INCOMPATIBLE"


def test_empty_inventory_and_invalid_date_fail_closed(tmp_path: Path):
    sim, market = _env(tmp_path)
    result = inspect(sim, market)
    assert result["status"] == "HOLD_NO_CAPTURES"
    assert result["capture_count"] == 0
    assert result["counts_complete"] is True
    assert inspect(sim, market, as_of=date(2100, 1, 1))["status"] == "HOLD_INVALID_OR_FUTURE_AS_OF"
    _capture(sim, "cap-1")
    _sample(sim, "cap-1", 0, date_str="not-a-date")
    report = inspect(sim, market, as_of=date(2026, 10, 23))
    assert report["status"] == "HOLD_INCONSISTENT_CAPTURE_EVIDENCE"
    assert report["market_session_window_eligibility"]["5d"]["market_evidence_unknown"] == 1
    assert report["evidence_anomaly_counts"]["entry_rows_with_invalid_signal_date"] == 1


def test_audit_bound_fails_before_scanning_full_cohort(tmp_path: Path):
    sim, market = _env(tmp_path)
    with sqlite3.connect(sim) as c:
        c.executemany(
            "INSERT INTO prospective_capture_run("
            "id,capture_version,source_job_id,status,request_json,market_scope,"
            "horizon_intent,candidate_limit,created_at,updated_at)"
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(f"capture-{i:03d}", "v1", f"job-{i:03d}", "PENDING",
              "{}", "KOSPI", "UNSPECIFIED", 5,
              "2026-10-20T00:00:00+00:00","2026-10-20T00:00:00+00:00")
             for i in range(261)],
        )
    result = inspect(sim, market)
    assert result["status"] == "HOLD_EXCEEDS_AUDIT_LIMIT"
    assert result["counts_complete"] is False
    assert result["capture_count"] == 261


def test_cli_reports_only_aggregate_json_and_exit_codes(tmp_path: Path):
    sim, market = _env(tmp_path)
    script = Path(__file__).resolve().parents[2] / "tools/data/p0_05_prospective_readonly_audit.py"
    cmd = [sys.executable, str(script), "--simulation-db", str(sim),
           "--market-db", str(market), "--as-of", "2026-10-23"]
    failed = subprocess.run(cmd, capture_output=True, text=True)
    assert failed.returncode == 2
    assert json.loads(failed.stdout)["status"] == "HOLD_NO_CAPTURES"
    _capture(sim, "cap-1")
    _sample(sim, "cap-1", 0)
    before = (_sha(sim),_sha(market))
    success = subprocess.run(cmd, capture_output=True, text=True)
    assert success.returncode == 0, success.stderr
    report = json.loads(success.stdout)
    assert report["status"] == "READ_ONLY_PROSPECTIVE_INVENTORY_OBSERVED"
    assert report["db_write_calls"] == 0
    assert report["external_requests"] == 0
    assert "PRIVATE_STOCK" not in success.stdout
    assert (_sha(sim),_sha(market)) == before
