"""LIVE-04R-P3: no-network one-capture local audit and CLI.

Synthetic fixture tests the tool mechanics; it never qualifies as a new
actual-market Scanner run, license grant, or TypeSafe review.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.live_04r_p3_capture_probe import (
    inspect_one_capture, discover_new_capture_ids,
)
from app.jev.synthetic_live_01 import prepare_synthetic_service
from tools.data.jev_live_04r_p3_one_capture import main


def _fixture(tmp_path: Path):
    db = tmp_path / "authored-synthetic-capture.db"
    _service, preview = prepare_synthetic_service(
        db, model_requested="jev-latest",
        expected_model_returned="jev-mock-returned",
        evidence={
            "provider_policy_checked_at": "MOCK_ONLY",
            "retention_status": "MOCK_ONLY",
            "model_discovery_ref": "MOCK_ONLY",
            "model_discovery_hash": "MOCK_ONLY",
        },
    )
    return db, preview


def _cutoff(offset=timedelta(hours=-1)) -> str:
    return (datetime.now(timezone.utc) + offset).isoformat()


def test_exact_one_capture_readonly_reports_real_blockers_separately(tmp_path):
    db, preview = _fixture(tmp_path)
    before = db.read_bytes()
    status = inspect_one_capture(
        db, capture_id=preview["capture_id"],
        captured_after=_cutoff(),
        sample_index=preview["sample_index"],
    )
    assert status["capture"]["freshness_time_consistent"] is True
    assert status["capture"]["canonical_capture_id"] == preview["capture_id"]
    assert status["candidate"]["sample_index"] == preview["sample_index"]
    assert status["candidate"]["snapshot_hash"] == preview["snapshot_hash"]
    assert status["capture"]["source_job_id"]
    assert status["capture"]["fresh_scanner_audit_independently_verified"] is False
    assert status["source_kind"] == "NOT_INDEPENDENTLY_ATTESTED"
    assert status["evidence"]["source_publication_time_verified"] is False
    assert status["outbound"]["decision"] == "HOLD"
    assert status["outbound"]["actual_provider_calls"] == 0
    assert status["outbound"]["db_writes"] == 0
    assert status["v4"]["local_status"]
    assert status["p3_local_status"]
    assert db.read_bytes() == before


def test_stale_capture_is_not_called_a_new_real_scan(tmp_path):
    db, preview = _fixture(tmp_path)
    before = db.read_bytes()
    status = inspect_one_capture(
        db, capture_id=preview["capture_id"],
        captured_after=_cutoff(timedelta(hours=1)),
    )
    assert status["capture"]["freshness_time_consistent"] is False
    assert status["first_blocker"] == {
        "stage": "FRESH_CAPTURE",
        "code": "P3_NEW_CAPTURE_TIME_NOT_VERIFIED",
    }
    assert status["p3_local_status"] == "EVIDENCE_INCOMPLETE_OR_NOT_NEW"
    assert status["outbound"]["decision"] == "HOLD"
    assert db.read_bytes() == before


@pytest.mark.parametrize("invalid", [
    "2026-10-29T15:00:00", "2026-10-29", "nonsense",
])
def test_naive_or_invalid_cutoff_fails_closed(tmp_path, invalid):
    db, preview = _fixture(tmp_path)
    with pytest.raises(ValueError, match="P3_CAPTURED_AFTER_REQUIRES_TIMEZONE"):
        inspect_one_capture(db, capture_id=preview["capture_id"],
                            captured_after=invalid)


def test_wrong_capture_or_sample_does_not_fall_back_to_old_capture(tmp_path):
    db, preview = _fixture(tmp_path)
    with pytest.raises(DecisionReviewContractError, match="S7_CAPTURE_NOT_COMPLETE"):
        inspect_one_capture(db, capture_id="does-not-exist", captured_after=_cutoff())
    with pytest.raises(ValueError, match="P3_SAMPLE_NOT_FOUND"):
        inspect_one_capture(db, capture_id=preview["capture_id"],
                            captured_after=_cutoff(), sample_index=499)


def test_cli_renders_json_without_raw_market_payload(tmp_path, capsys):
    db, preview = _fixture(tmp_path)
    before = db.read_bytes()
    code = main([
        "--capture-id", preview["capture_id"],
        "--sample-index", str(preview["sample_index"]),
        "--captured-after", _cutoff(),
        "--simulation-db", str(db),
    ])
    assert code == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["candidate"]["snapshot_hash"] == preview["snapshot_hash"]
    assert "strategy_intent" not in output
    assert "passed_condition_meanings" not in output
    assert "source_payload" not in output
    assert "JEV_API_KEY" not in output
    assert parsed["outbound"]["actual_provider_calls"] == 0
    assert db.read_bytes() == before


def test_cli_fail_closed_has_no_exception_traceback_or_data_dump(tmp_path, capsys):
    path = tmp_path / "never-created.db"
    assert main([
        "--capture-id", "nope",
        "--captured-after", _cutoff(),
        "--simulation-db", str(path),
    ]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "BLOCKED"
    assert report["reason_code"] == "S7_SOURCE_DB_NOT_FOUND"
    assert report["actual_provider_calls"] == 0
    assert not path.exists()


def test_new_capture_discovery_is_readonly_and_never_attests_market_origin(tmp_path, capsys):
    db, preview = _fixture(tmp_path)
    before = db.read_bytes()
    found = discover_new_capture_ids(db, captured_after=_cutoff())
    assert len(found) == 1
    assert found[0]["capture_id"] == preview["capture_id"]
    assert found[0]["source_job_id"]

    code = main([
        "--find-new",
        "--captured-after", _cutoff(),
        "--simulation-db", str(db),
    ])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "FOUND"
    assert len(report["new_complete_entry_captures"]) == 1
    assert report["new_complete_entry_captures"][0]["capture_id"] == preview["capture_id"]
    assert report["actual_provider_calls"] == 0
    assert "snapshot" not in report
    assert db.read_bytes() == before


def test_new_capture_discovery_rejects_historical_and_conflicting_ids(tmp_path, capsys):
    db, preview = _fixture(tmp_path)
    assert discover_new_capture_ids(
        db, captured_after=_cutoff(timedelta(days=1))
    ) == []
    assert main([
        "--find-new", "--capture-id", preview["capture_id"],
        "--captured-after", _cutoff(), "--simulation-db", str(db),
    ]) == 2
    error = json.loads(capsys.readouterr().out)
    assert error["reason_code"] == "P3_DISCOVER_AND_EXPLICIT_ID_CONFLICT"
