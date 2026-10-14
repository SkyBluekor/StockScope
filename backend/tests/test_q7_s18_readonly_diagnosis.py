"""S18 diagnostics against minimal synthetic SQLite, no production DB."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3

import pytest

from app.jev import q7_diagnosis_s18 as diagnosis
from app.prospective.models import digest_json


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "simulation.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE prospective_capture_run(
              id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              completed_at TEXT,
              actual_data_date TEXT,
              request_json TEXT,
              source_execution_key TEXT,
              scanner_version TEXT,
              scanner_baseline TEXT,
              input_fingerprint TEXT,
              horizon_intent TEXT,
              horizon_policy_version TEXT
            );
            CREATE TABLE prospective_recommendation_sample(
              capture_run_id TEXT NOT NULL,
              sample_index INTEGER NOT NULL,
              action TEXT,
              strategy TEXT,
              signal_date TEXT,
              market TEXT,
              ticker TEXT,
              rank INTEGER,
              snapshot_json TEXT,
              snapshot_hash TEXT,
              PRIMARY KEY(capture_run_id,sample_index)
            );
        """)
        conn.execute(
            "INSERT INTO prospective_capture_run VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("cap1", "COMPLETE", "2026-10-14T07:00:00+09:00",
             "2026-10-13", '{"market_scope":"KOSPI"}', "job1", "0.21", "baseline",
             "fingerprint", "default", "h1"),
        )
    return path


def _sample(conn, i: int, *, action="ENTRY_CANDIDATE", corrupt=False):
    original = {"priority": {"rank": i+1}, "data_date": "2026-10-13"}
    conn.execute(
        "INSERT INTO prospective_recommendation_sample VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("cap1", i, action, "trend_recovery", "2026-10-13", "KOSPI",
         f"00{i:04d}", i+1, json.dumps(original),
         "bad" if corrupt else digest_json(original)),
    )


def _fill(path):
    with sqlite3.connect(path) as conn:
        for i in range(5):
            _sample(conn, i, action="REFERENCE_ONLY" if i == 4 else "ENTRY_CANDIDATE",
                    corrupt=i == 3)


def _fake_s7(capture, sample):
    if sample["sample_index"] == 0:
        return {
            "category": "INVALID",
            "codes": ["RANK_MISSING", "POLICY_PROVENANCE_UNVERIFIED"],
            "rank": {"status": "FAIL"},
            "policy": {"status": "FAIL"},
            "strict_s3": {"status": "FAIL"},
        }
    if sample["sample_index"] == 1:
        return {
            "category": "LEGACY_LIMITED",
            "codes": ["LEGACY_DERIVED_IDENTITY", "STRATEGY_IDENTITY_MISMATCH"],
            "strategy": {"status": "LEGACY_DERIVED"},
            "strict_s3": {"status": "FAIL"},
        }
    return {"category": "LOCAL_VALIDATED", "codes": [], "rank": {"status": "PASS"}}


def test_diagnosis_exact_denominators_codes_and_clock(tmp_path, monkeypatch):
    path = _db(tmp_path)
    _fill(path)
    monkeypatch.setattr(diagnosis, "assess_frozen_candidate", _fake_s7)
    before = path.read_bytes()
    result = diagnosis.diagnose(path, detail_limit=2)
    assert path.read_bytes() == before
    assert result["status"] == "DIAGNOSIS_ONLY"
    assert result["counts_complete"] is True
    assert result["completed_captures_audited"] == 1
    assert result["all_samples_in_completed_captures"] == 5
    assert result["entry_candidates"] == 4
    assert result["reference_only"] == 1
    assert result["snapshot_hash_verified_entry_count"] == 3
    assert result["snapshot_hash_verified_reference_count"] == 1
    assert result["reference_snapshot_error_counts"] == {}
    assert result["entry_categories"] == {
        "INVALID": 1,
        "LEGACY_LIMITED": 1,
        "LOCAL_VALIDATED": 1,
        "SNAPSHOT_UNREADABLE_OR_MISMATCH": 1,
    }
    assert result["invalid_code_counts"] == {
        "POLICY_PROVENANCE_UNVERIFIED": 1, "RANK_MISSING": 1,
    }
    assert result["failing_check_counts"] == {
        "policy": 1, "rank": 1, "strict_s3": 1,
    }
    assert result["snapshot_or_assessment_error_counts"] == {
        "S7_SNAPSHOT_HASH_MISMATCH": 1,
    }
    assert result["completion_timing_counts"] == {
        "NEXT_CALENDAR_DAY_BEFORE_09_KST_UNVERIFIED": 4,
    }
    assert result["problematic_entries"] == 2
    assert not result["problematic_details_truncated"]
    assert len(result["problematic_details"]) == 2
    assert "snapshot_json" not in json.dumps(result)
    assert result["independent_timestamp_attestation"] is False


def test_complete_aggregates_even_if_detail_is_truncated(tmp_path, monkeypatch):
    path = _db(tmp_path)
    _fill(path)
    monkeypatch.setattr(diagnosis, "assess_frozen_candidate", _fake_s7)
    result = diagnosis.diagnose(path, detail_limit=1)
    assert result["problematic_details_truncated"] is True
    assert len(result["problematic_details"]) == 1
    assert result["problematic_entries"] == 2
    assert result["counts_complete"] is True


def test_sample_cap_refuses_partial_count_and_no_assessment(tmp_path, monkeypatch):
    path = _db(tmp_path)
    _fill(path)
    monkeypatch.setattr(diagnosis, "assess_frozen_candidate",
                        lambda *a: pytest.fail("must not inspect partial cohort"))
    result = diagnosis.diagnose(path, max_samples=4)
    assert result["status"] == "COHORT_TOO_LARGE_FOR_DIAGNOSIS"
    assert result["counts_complete"] is False
    assert result["samples_found"] == 5
    assert "entry_categories" not in result


@pytest.mark.parametrize("day,completion,expected", [
    ("2026-10-13", "2026-10-14T07:00:00+09:00",
     "NEXT_CALENDAR_DAY_BEFORE_09_KST_UNVERIFIED"),
    ("2026-10-13", "2026-10-13T17:00:00+09:00",
     "COMPLETED_ON_SIGNAL_CALENDAR_DAY"),
    ("2026-10-13", "2026-10-18T07:00:00+09:00",
     "LATER_THAN_SIGNAL_CALENDAR_DAY_OTHER"),
    ("2026-10-13", "2026-10-12T07:00:00+09:00",
     "COMPLETED_BEFORE_SIGNAL_CALENDAR_DAY"),
    ("2026-10-13", "2026-10-14T07:00:00",
     "TIME_OR_SIGNAL_UNKNOWN"),
    ("2026-10-13", None, "TIME_OR_SIGNAL_UNKNOWN"),
    ("bad", "2026-10-14T07:00:00+09:00", "TIME_OR_SIGNAL_UNKNOWN"),
])
def test_timing_never_claims_independent_provenance(day, completion, expected):
    assert diagnosis._timing(completion, day) == expected


def test_missing_db_never_creates_empty_runtime(tmp_path):
    path = tmp_path / "missing.db"
    result = diagnosis.diagnose(path)
    assert result["status"] == "NO_SIMULATION_DB"
    assert not path.exists()


def test_schema_missing_fails_closed(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE prospective_capture_run(id TEXT)")
    result = diagnosis.diagnose(path)
    assert result["status"] == "SCHEMA_MISSING"
    assert result["counts_complete"] is False


def test_s7_real_validator_reports_codes_not_fake_validity(tmp_path):
    path = _db(tmp_path)
    with sqlite3.connect(path) as conn:
        _sample(conn, 0)
    result = diagnosis.diagnose(path)
    assert result["status"] == "DIAGNOSIS_ONLY"
    assert result["entry_candidates"] == 1
    assert result["entry_categories"] == {"INVALID": 1}
    assert result["invalid_code_counts"]
    assert result["q7_approval_eligible"] is False



def test_reference_only_corruption_is_not_silently_ignored(tmp_path):
    path = _db(tmp_path)
    with sqlite3.connect(path) as conn:
        _sample(conn, 0, action="REFERENCE_ONLY", corrupt=True)
    result = diagnosis.diagnose(path)
    assert result["status"] == "DIAGNOSIS_ONLY"
    assert result["reference_only"] == 1
    assert result["entry_candidates"] == 0
    assert result["reference_snapshot_error_counts"] == {
        "S7_SNAPSHOT_HASH_MISMATCH": 1,
    }
    assert result["snapshot_hash_verified_reference_count"] == 0
    assert result["runtime_db_writes"] == 0
