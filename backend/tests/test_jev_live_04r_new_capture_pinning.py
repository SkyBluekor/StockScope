"""LIVE-04R-P2: new Scanner capture cannot change policy/horizon mid-flight.

Strictly private authored synthetic DB. Real Scanner capture and holdings are
never read, modified, recreated or transmitted.
"""
from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from app.jev.synthetic_live_01 import prepare_synthetic_service
from app.prospective.catalog import ProspectiveCatalog, ProspectiveCatalogError
from app.prospective.models import ProspectiveCaptureRequest


def _catalog(tmp_path):
    db = tmp_path / "new-capture-pinning-synthetic.db"
    prepare_synthetic_service(
        db, model_requested="jev-latest",
        expected_model_returned="jev-mock-returned",
        evidence={
            "provider_policy_checked_at": "MOCK_ONLY",
            "retention_status": "MOCK_ONLY",
            "model_discovery_ref": "MOCK_ONLY",
            "model_discovery_hash": "MOCK_ONLY",
        },
    )
    return ProspectiveCatalog(db), db


def _request():
    return ProspectiveCaptureRequest(
        market_scope="KOSPI",
        requested_as_of="2026-10-28",
        candidate_limit=5,
        horizon_intent="SHORT",
        horizon_policy_version="VN_P1_S2_HORIZON_CONTEXT_V1",
        selection_policy_id="SYNTHETIC-ACTIVE-PIN-A",
        selection_policy_hash="synthetic-hash-a",
    )


def _result():
    return {
        "version": "SYNTHETIC-SCANNER-ORIGINAL-EVIDENCE",
        "market_scope": "KOSPI",
        "requested_as_of": "2026-10-28",
        "input_fingerprint": "authored-synthetic",
        "summary": {"candidate_count": 0},
        "candidates": [],
        "more_candidates": [],
        "partial_data": False,
    }


@pytest.mark.parametrize("changes", [
    {"horizon_intent": "MEDIUM"},
    {"horizon_policy_version": "OTHER-VERSION"},
    {"selection_policy_id": "SYNTHETIC-ACTIVE-PIN-B"},
    {"selection_policy_hash": "synthetic-hash-b"},
    {"requested_as_of": "2026-10-27"},
    {"candidate_limit": 10},
    {"market_scope": "KOSDAQ"},
])
def test_begin_and_finalize_cannot_swap_original_request(tmp_path, changes):
    catalog, db = _catalog(tmp_path)
    baseline = _request()
    first = catalog.begin_capture(source_job_id="new-fresh-scanner", request=baseline)
    assert first["status"] == "PENDING"
    modified = replace(baseline, **changes)

    with pytest.raises(
        ProspectiveCatalogError, match="Scanner 시작과 완료 시점",
    ) as start_exc:
        catalog.begin_capture(source_job_id="new-fresh-scanner", request=modified)
    assert start_exc.value.code == "PROSPECTIVE_CAPTURE_REQUEST_DRIFT"

    with pytest.raises(
        ProspectiveCatalogError, match="Scanner 시작과 완료 시점",
    ) as finish_exc:
        catalog.finalize_capture(
            source_job_id="new-fresh-scanner", request=modified, result=_result(),
        )
    assert finish_exc.value.code == "PROSPECTIVE_CAPTURE_REQUEST_DRIFT"

    unchanged = catalog.get_capture(first["id"])
    assert unchanged["status"] == "PENDING"
    assert unchanged["request"] == baseline.to_dict()
    assert unchanged["source_snapshot_hash"] is None
    assert unchanged["result_hash"] is None
    with sqlite3.connect(db) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM prospective_recommendation_sample WHERE capture_run_id=?",
            (first["id"],),
        ).fetchone()[0]
    assert count == 0


def test_same_pinned_request_finalizes_once_without_changing_horizon(tmp_path):
    catalog, _db = _catalog(tmp_path)
    request = _request()
    started = catalog.begin_capture(source_job_id="new-fresh-scanner", request=request)
    repeated = catalog.begin_capture(source_job_id="new-fresh-scanner", request=request)
    assert repeated["id"] == started["id"]
    finished = catalog.finalize_capture(
        source_job_id="new-fresh-scanner", request=request, result=_result(),
    )
    assert finished["status"] == "COMPLETE"
    assert finished["horizon_intent"] == "SHORT"
    assert finished["horizon_policy_version"] == "VN_P1_S2_HORIZON_CONTEXT_V1"
    assert finished["request"]["selection_policy_hash"] == "synthetic-hash-a"

    # Do not recapture a terminal result or rewrite its frozen request.
    final_again = catalog.finalize_capture(
        source_job_id="new-fresh-scanner",
        request=replace(request, horizon_intent="MEDIUM"),
        result=_result(),
    )
    assert final_again["id"] == finished["id"]
    assert final_again["source_snapshot_hash"] == finished["source_snapshot_hash"]


def test_invalid_original_begin_contract_fails_closed(tmp_path):
    catalog, _db = _catalog(tmp_path)
    request = _request()
    started = catalog.begin_capture(source_job_id="new-fresh-scanner", request=request)
    with catalog.connect() as conn:
        conn.execute(
            "UPDATE prospective_capture_run SET request_json='invalid json' WHERE id=?",
            (started["id"],),
        )
    with pytest.raises(ProspectiveCatalogError) as error:
        catalog.finalize_capture(
            source_job_id="new-fresh-scanner", request=request, result=_result(),
        )
    assert error.value.code == "PROSPECTIVE_CAPTURE_REQUEST_INVALID"
