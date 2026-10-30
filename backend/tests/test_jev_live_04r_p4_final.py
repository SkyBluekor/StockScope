"""P4 FINAL local-only frozen SHORT inspection, never a market-provider test.

All stored rows below are authored for isolated synthetic SQLite. No live
KRX, actual account credentials, numeric Horizon approval, or TypeSafe call.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.horizon import HORIZON_POLICY_VERSION
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.live_04r_p4_final import (
    find_stored_horizon_captures, inspect_stored_horizon_capture,
)
from app.jev.synthetic_live_01 import _synthetic_candidate, FIXTURE_DATE
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest
from tools.data.jev_live_04r_p4_final import main
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


def _authored_db(tmp_path):
    import sqlite3
    db = tmp_path / "authored-short-p4.db"
    sqlite3.connect(db).close()
    migrate_prospective_store(db)
    store = ProspectiveCatalog(db)
    request = ProspectiveCaptureRequest(
        market_scope="KOSPI", requested_as_of=FIXTURE_DATE,
        candidate_limit=1, horizon_intent="SHORT",
        horizon_policy_version=HORIZON_POLICY_VERSION,
        horizon_purpose="LOCAL_REVIEW_ONLY",
        selection_policy_id="AUTHORED-P4-LOCAL",
        selection_policy_hash="AUTHORED-NONREAL-HASH",
    )
    authored = _synthetic_candidate()
    authored["priority"] = {
        "rank": 1, "tier": "READY", "label": "Authored",
        "strict_rank": True,
    }
    authored["data_date"] = FIXTURE_DATE
    authored["risk"] = {"status": "READY", "warning": False, "warnings": []}
    authored["entry_risk_guide"] = {"action": {"status": "REVIEW"}}
    result = {
        "version": "P4-AUTHORED-LOCAL-SCANNER",
        "market_scope": "KOSPI",
        "requested_as_of": FIXTURE_DATE,
        "input_fingerprint": "AUTHORED-NO-KRX",
        "summary": {"candidate_count": 1},
        "candidates": [authored],
        "more_candidates": [],
        "partial_data": False,
        "strategy_selection_policy": {
            "policy_id": request.selection_policy_id,
            "policy_hash": request.selection_policy_hash,
        },
        "horizon_context": {
            "intent": "SHORT", "purpose": "LOCAL_REVIEW_ONLY",
            "policy_version": HORIZON_POLICY_VERSION,
        },
    }
    store.begin_capture(source_job_id="authored-p4-1", request=request)
    original = store.finalize_capture(
        source_job_id="authored-p4-1", request=request, result=result,
        require_policy_provenance=False,
    )
    store.begin_capture(source_job_id="authored-p4-duplicate", request=request)
    duplicate = store.finalize_capture(
        source_job_id="authored-p4-duplicate", request=request, result=result,
        require_policy_provenance=False,
    )
    assert original["status"] == "COMPLETE"
    assert duplicate["status"] == "DUPLICATE"
    assert duplicate["canonical_capture_id"] == original["id"]
    return db, store, original, duplicate


def test_short_discovery_and_explicit_duplicate_source_do_not_modify_sqlite(tmp_path, capsys):
    db, _, original, duplicate = _authored_db(tmp_path)
    before = db.read_bytes()
    listing = find_stored_horizon_captures(db)
    assert listing["status"] == "FOUND"
    assert len(listing["captures"]) == 2
    assert listing["selection_required"] is True
    for record in listing["captures"]:
        assert record["horizon_intent"] == "SHORT"
        assert record["horizon_purpose"] == "LOCAL_REVIEW_ONLY"
    dup = next(r for r in listing["captures"] if r["capture_id"] == duplicate["id"])
    assert dup["canonical_capture_id"] == original["id"]
    assert dup["stored_samples_on_this_row"] == 0
    assert main(["--find-short", "--simulation-db", str(db)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["selection_required"]
    assert len(printed["captures"]) == 2
    assert db.read_bytes() == before


def test_existing_short_canonical_v4_is_independent_of_numeric_policy_and_rights(tmp_path):
    db, _, original, duplicate = _authored_db(tmp_path)
    before = db.read_bytes()
    review = inspect_stored_horizon_capture(db, capture_id=duplicate["id"])
    assert review["selection"]["requested_capture_id"] == duplicate["id"]
    assert review["selection"]["canonical_capture_id"] == original["id"]
    assert review["selection"]["reused_canonical"] is True
    assert review["selection"]["fresh_scan_independently_verified"] is False
    assert review["candidate"]["snapshot_hash_verified_by_loader"] is True
    assert review["candidate"]["sample_index"] == 0
    assert review["frozen_contract"]["horizon_intent"] == "SHORT"
    assert review["frozen_contract"]["horizon_purpose"] == "LOCAL_REVIEW_ONLY"
    assert review["frozen_contract"]["request_horizon_matches_canonical"] is True
    assert review["frozen_contract"]["requested_canonical_context_match"] is True
    assert review["horizon_execution"]["support_status"] == "EVALUATION_PENDING"
    assert review["horizon_execution"]["numeric_policy_approved"] is False
    assert review["provider_authorization"]["decision"] == "HOLD"
    assert review["provider_authorization"]["actual_provider_calls"] == 0
    assert review["provider_authorization"]["db_writes"] == 0
    assert review["local_v4"]["status"] in {
        "BLOCKED_SEMANTIC_SOURCE", "BLOCKED_INTEGRITY",
        "SKIPPED_LOCAL", "LOCAL_V4_PROJECTABLE",
    }
    if review["local_v4"]["status"] == "LOCAL_V4_PROJECTABLE":
        assert review["local_v4"]["state_hash"]
    assert db.read_bytes() == before


def test_cli_policy_status_never_activates_policy(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR", str(tmp_path))
    assert main(["--policy-status"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["effective_pin_source"] == "LEGACY_CURRENT_10_FALLBACK"
    assert info["original_strategy_identity_count"] == 0
    assert info["actual_provider_calls"] == 0
    assert info["db_writes"] == 0
    assert list(tmp_path.iterdir()) == []


def test_cli_explicit_capture_with_no_data_body_or_secret(tmp_path, capsys):
    db, _, _, duplicate = _authored_db(tmp_path)
    before = db.read_bytes()
    assert main(["--capture-id", duplicate["id"], "--simulation-db", str(db)]) == 0
    printed = capsys.readouterr().out
    info = json.loads(printed)
    assert info["selection"]["reused_canonical"]
    assert info["provider_authorization"]["decision"] == "HOLD"
    assert "snapshot_json" not in printed
    assert "JEV_API_KEY" not in printed
    assert "state_bytes" not in printed
    assert db.read_bytes() == before


def test_missing_and_unsupported_capture_fail_closed(tmp_path, capsys):
    db, _, original, _ = _authored_db(tmp_path)
    with pytest.raises(DecisionReviewContractError, match="P4_CAPTURE_NOT_COMPLETE"):
        inspect_stored_horizon_capture(db, capture_id="does-not-exist")
    with pytest.raises(ValueError, match="P4_SAMPLE_NOT_FOUND"):
        inspect_stored_horizon_capture(db, capture_id=original["id"], sample_index=499)
    with pytest.raises(ValueError, match="P4_UNSUPPORTED_DISCOVERY_HORIZON"):
        find_stored_horizon_captures(db, horizon_intent="LONG")
    assert main(["--capture-id", "does-not-exist", "--simulation-db", str(db)]) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "P4_CAPTURE_NOT_COMPLETE"


def test_independent_v4_status_does_not_hide_unapproved_horizon_or_legacy(tmp_path, monkeypatch):
    db, _, original, _ = _authored_db(tmp_path)
    import app.jev.live_04r_p4_final as module
    original_integrity = module.assess_frozen_candidate

    def authored_integrity(capture, sample):
        info = original_integrity(capture, sample)
        info["strategy"]["status"] = "LEGACY_DERIVED"
        info["strategy"]["code"] = "LEGACY_DERIVED_IDENTITY"
        return info

    def authored_v4(_capture, _sample):
        return {
            "local_v4_status": "LOCAL_V4_PROJECTABLE",
            "v4_local_semantic_status": "RESIDUAL_SEMANTIC_REVIEW",
            "v4_state_hash": "authored-state-hash-only",
            "lineage_analysis_status": "COMPLETE",
            "reason_codes": [],
        }

    monkeypatch.setattr(module, "assess_frozen_candidate", authored_integrity)
    monkeypatch.setattr(module, "diagnose_v4", authored_v4)
    report = inspect_stored_horizon_capture(db, capture_id=original["id"])
    assert report["horizon_execution"]["numeric_policy_approved"] is False
    assert report["strategy_identity"]["legacy_derived_is_not_original"] is True
    assert report["strategy_identity"]["verified_original"] is False
    assert report["provider_authorization"]["decision"] == "HOLD"
    # Even a mocked technical V4 route cannot authorize outbound data.
    if report["frozen_contract"]["semantic_source_v2_valid"]:
        assert report["local_v4"]["status"] == "LOCAL_V4_PROJECTABLE"
    else:
        assert report["local_v4"]["status"] == "BLOCKED_SEMANTIC_SOURCE"
        assert report["local_v4"]["state_hash"] is None
