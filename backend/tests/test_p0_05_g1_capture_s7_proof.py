"""G1 operational capture S7 proof: synthetic, side-effect-free regression tests."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.prospective.models import digest_json
from tools.data import p0_05_g1_capture_s7_proof as proof


CID = "9b65b836-8f60-42c5-8792-8053b89ca5e9"
DATE = "2026-10-27"
CREATED = "2026-10-28T04:51:18.337678+00:00"
CAPTURE_COLS = {
    "id": "TEXT PRIMARY KEY", "status": "TEXT", "canonical_capture_id": "TEXT",
    "source_job_id": "TEXT", "source_execution_key": "TEXT",
    "source_snapshot_hash": "TEXT", "result_hash": "TEXT",
    "scanner_version": "TEXT", "market_scope": "TEXT",
    "actual_data_date": "TEXT", "request_json": "TEXT",
    "returned_candidate_count": "INTEGER", "created_at": "TEXT",
    "completed_at": "TEXT", "scanner_baseline": "TEXT",
    "input_fingerprint": "TEXT", "horizon_intent": "TEXT",
    "horizon_policy_version": "TEXT",
}
SAMPLE_COLS = {
    "capture_run_id": "TEXT", "sample_index": "INTEGER", "market": "TEXT",
    "ticker": "TEXT", "name": "TEXT", "strategy": "TEXT", "action": "TEXT",
    "rank": "INTEGER", "decision_status": "TEXT",
    "candidate_state": "TEXT", "signal_date": "TEXT",
    "snapshot_json": "TEXT", "snapshot_hash": "TEXT",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path, *, count: int = 15, status: str = "COMPLETE",
             action: str = "REFERENCE", corrupt: int | None = None,
             entries: int = 0) -> Path:
    db = tmp_path / "operational_simulation.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE prospective_capture_run (" + ",".join(
            key + " " + typ for key, typ in CAPTURE_COLS.items()
        ) + ")")
        conn.execute("CREATE TABLE prospective_recommendation_sample (" + ",".join(
            key + " " + typ for key, typ in SAMPLE_COLS.items()
        ) + ")")
        capture = {
            "id": CID, "status": status, "canonical_capture_id": None,
            "source_job_id": "bdb1beac1d1000",
            "source_execution_key": "a" * 64,
            "source_snapshot_hash": "b" * 64, "result_hash": "c" * 64,
            "scanner_version": "0.21.3.9",
            "market_scope": "ALL", "actual_data_date": DATE,
            "request_json": json.dumps({"market_scope": "ALL"}),
            "returned_candidate_count": count, "created_at": CREATED,
            "completed_at": "2026-10-28T04:53:00+00:00",
            "scanner_baseline": "BASELINE",
            "input_fingerprint": "stable", "horizon_intent": "DEFAULT",
            "horizon_policy_version": "v1",
        }
        conn.execute(
            "INSERT INTO prospective_capture_run (" + ",".join(capture) +
            ") VALUES (" + ",".join("?" for _ in capture) + ")",
            list(capture.values()),
        )
        if status == "COMPLETE":
            for idx in range(count):
                item = {"data_date": DATE, "private": "never-disclose"}
                sample = {
                    "capture_run_id": CID, "sample_index": idx,
                    "market": "KOSPI" if idx % 2 == 0 else "KOSDAQ",
                    "ticker": f"{idx:06d}", "name": "SENSITIVE",
                    "strategy": "pullback",
                    "action": "ENTRY_CANDIDATE" if idx < entries else action,
                    "rank": idx + 1,
                    "decision_status": "WATCH", "candidate_state": "WATCH",
                    "signal_date": DATE, "snapshot_json": json.dumps(item),
                    "snapshot_hash": ("0" * 64 if idx == corrupt else digest_json(item)),
                }
                conn.execute(
                    "INSERT INTO prospective_recommendation_sample (" +
                    ",".join(sample) + ") VALUES (" + ",".join("?" for _ in sample) + ")",
                    list(sample.values()),
                )
    return db


def test_g1_exact_operational_capture_15_of_15_hashes_and_reference_s7(tmp_path):
    db = _fixture(tmp_path)
    before = _digest(db)
    result = proof.inspect(db, capture_id=CID)
    assert result["status"] == "CAPTURE_STORAGE_VERIFIED_S7_REVIEWED"
    assert result["capture_id"] == CID
    assert result["scope"] == "ALL"
    assert result["signal_data_date"] == DATE
    assert result["expected_samples"] == result["actual_samples"] == 15
    assert result["snapshot_hash_verified"] == 15
    assert result["snapshot_hash_failed"] == result["row_identity_failed"] == 0
    assert result["s7_category_counts"] == {"REFERENCE_ONLY": 15}
    assert result["s7_reason_code_counts"] == {}
    assert result["s7_reference_exclusion_counts"] == {"NOT_ENTRY_CANDIDATE": 15}
    assert result["capture_created_at_kst"].startswith("2026-10-28T13:51:18")
    assert result["was_created_after_signal_day"] is True
    assert result["premarket_recommendation_eligible"] is False
    assert result["root_source_hashes_independently_recomputed"] is False
    assert result["q7_approval_eligible"] is False
    assert result["db_writes"] == result["external_requests"] == 0
    assert "SENSITIVE" not in json.dumps(result)
    assert "never-disclose" not in json.dumps(result)
    assert _digest(db) == before


def test_g1_reference_exclusions_not_misclassified_as_s7_failure(tmp_path, monkeypatch):
    db = _fixture(tmp_path, count=15, entries=9)
    before = _digest(db)
    real_assess = proof.assess_frozen_candidate

    def assess(capture, sample):
        if sample["action"] == "ENTRY_CANDIDATE":
            return {"category": "LEGACY_LIMITED",
                    "codes": ["LEGACY_DERIVED_IDENTITY", "STRATEGY_IDENTITY_MISMATCH"]}
        return real_assess(capture, sample)

    monkeypatch.setattr(proof, "assess_frozen_candidate", assess)
    result = proof.inspect(db, capture_id=CID)
    assert result["status"] == "CAPTURE_STORAGE_VERIFIED_S7_REVIEWED"
    assert result["expected_samples"] == result["actual_samples"] == 15
    assert result["snapshot_hash_verified"] == 15
    assert result["s7_category_counts"] == {"LEGACY_LIMITED": 9, "REFERENCE_ONLY": 6}
    assert result["s7_reason_code_counts"] == {
        "LEGACY_DERIVED_IDENTITY": 9,
        "STRATEGY_IDENTITY_MISMATCH": 9,
    }
    assert result["s7_reference_exclusion_counts"] == {"NOT_ENTRY_CANDIDATE": 6}
    assert "S7_UNCLASSIFIED" not in result["s7_reason_code_counts"]
    assert result["s7_invalid_count"] == 0
    assert result["local_validated_entry_count"] == 0
    assert _digest(db) == before


def test_g1_tampered_hash_fails_closed_without_rewriting(tmp_path):
    db = _fixture(tmp_path, corrupt=7)
    before = _digest(db)
    result = proof.inspect(db, capture_id=CID)
    assert result["status"] == "HOLD_CAPTURE_STORAGE_INTEGRITY_FAILED"
    assert result["snapshot_hash_verified"] == 14
    assert result["snapshot_hash_failed"] == 1
    assert _digest(db) == before


@pytest.mark.parametrize("tamper,expected", [
    ("wrong_date", "row_identity_failed"),
    ("missing_index", "metadata_verified"),
    ("root_hash", "metadata_verified"),
    ("count", "metadata_verified"),
])
def test_g1_corrupt_row_lineage_and_count_is_rejected(tmp_path, tamper, expected):
    db = _fixture(tmp_path)
    with sqlite3.connect(db) as conn:
        if tamper == "wrong_date":
            conn.execute(
                "UPDATE prospective_recommendation_sample SET signal_date='2026-10-21' "
                "WHERE sample_index=0"
            )
        elif tamper == "missing_index":
            conn.execute(
                "UPDATE prospective_recommendation_sample SET sample_index=999 "
                "WHERE sample_index=0"
            )
        elif tamper == "root_hash":
            conn.execute("UPDATE prospective_capture_run SET result_hash=NULL")
        elif tamper == "count":
            conn.execute("UPDATE prospective_capture_run SET returned_candidate_count=14")
    result = proof.inspect(db, capture_id=CID)
    assert result["status"] == "HOLD_CAPTURE_STORAGE_INTEGRITY_FAILED"
    if expected == "metadata_verified":
        assert result["metadata_verified"] is False
    else:
        assert result[expected] > 0


def test_g1_s7_invalid_does_not_falsely_mean_json_corruption(tmp_path, monkeypatch):
    db = _fixture(tmp_path, action="ENTRY_CANDIDATE")

    def invalid(capture, sample):
        assert sample["snapshot"]["data_date"] == DATE
        return {"category": "INVALID", "codes": ["RANK_MISSING"]}

    monkeypatch.setattr(proof, "assess_frozen_candidate", invalid)
    result = proof.inspect(db, capture_id=CID)
    assert result["status"] == "CAPTURE_STORAGE_VERIFIED_S7_REVIEWED"
    assert result["snapshot_hash_verified"] == 15
    assert result["s7_category_counts"] == {"INVALID": 15}
    assert result["s7_reason_code_counts"] == {"RANK_MISSING": 15}
    assert result["s7_invalid_count"] == 15
    assert result["q7_approval_eligible"] is False


@pytest.mark.parametrize("status", ["DUPLICATE", "PENDING", "FAILED", "PARTIAL"])
def test_g1_noncomplete_is_not_verified(tmp_path, status):
    db = _fixture(tmp_path, status=status)
    result = proof.inspect(db, capture_id=CID)
    assert result["status"] == "HOLD_CAPTURE_NOT_COMPLETE"
    assert result["capture_status"] == status


def test_g1_wrong_target_and_missing_db_are_inert(tmp_path):
    absent = tmp_path / "missing.db"
    assert proof.inspect(absent, capture_id=CID)["status"] == "HOLD_OPERATIONAL_SIMULATION_DB_MISSING"
    assert not absent.exists()
    db = _fixture(tmp_path)
    assert proof.inspect(db, capture_id="unknown")["status"] == "HOLD_CAPTURE_NOT_FOUND"
    assert proof.inspect(db, capture_id="")["status"] == "HOLD_CAPTURE_ID_INVALID"


def test_g1_cli_readonly_with_correct_target(tmp_path, capsys, monkeypatch):
    db = _fixture(tmp_path, count=15)
    before = _digest(db)
    code = proof.main(["--simulation-db", str(db), "--capture-id", CID])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["snapshot_hash_verified"] == 15
    assert _digest(db) == before
