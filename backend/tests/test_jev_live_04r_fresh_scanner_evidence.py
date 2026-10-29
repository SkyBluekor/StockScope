"""LIVE-04R-P2: fresh Scanner original pin + reproducibility evidence -> V2.

All stock/ticker/date rows in this test are authored. A monkeypatched audit
reader stands in for a *previously verified* local scanner-repro file; this is
not a real provider test, source-license proof, or Horizon activation.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from app.jev.synthetic_live_01 import _synthetic_candidate, FIXTURE_DATE
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest
from app.strategy.condition_semantics import condition_sources
from app.strategy.production_selection_policy import (
    SELECTION_POLICY_CONTRACT_VERSION,
    SelectionPolicyPin,
)
from app.strategy.semantic_identity_bridge import scanner_repro_candidate_key
from app.strategy.semantic_source_v2 import verify_semantic_source_v2


def _pin(candidate):
    return SelectionPolicyPin(
        policy_id="AUTHORED-ACTIVE-PIN",
        policy_hash="authored-active-policy-hash",
        policy_contract_version=SELECTION_POLICY_CONTRACT_VERSION,
        policy_source="ACTIVE_SELECTION_POLICY",
        fallback_used=False, fallback_reason=None,
        operating_strategies=((
            candidate["strategy_version_id"],
            candidate["strategy"],
            candidate["strategy_definition_hash"],
        ),),
        scanner_baseline_id="authored-scanner-baseline",
        production_fingerprint="authored-scanner-execution",
        production_policy_fingerprint="authored-strategy-selection",
    )


def _candidate():
    result = _synthetic_candidate()
    result["data_date"] = FIXTURE_DATE
    result["current_price"] = 100
    result["risk"] = {"status": "AUTHORED_RISK_PLACEHOLDER"}
    return result


def _audited(candidate):
    result = deepcopy(candidate)
    result["scanner_inputs"] = {
        "condition_details": [
            {"raw": source, "status": "PASS", "condition_id": f"AUTHORED-{i}"}
            for i, source in enumerate(condition_sources(candidate["strategy"]), start=1)
        ],
    }
    return result


@pytest.mark.parametrize("tamper", [None, "missing-audit", "wrong-condition", "wrong-policy"])
def test_scanner_fresh_active_candidate_source_chain_only_accepts_matching_evidence(
    monkeypatch, tamper,
):
    import app.prospective.catalog as catalog_module

    candidate = _candidate()
    audit = _audited(candidate)
    pin = _pin(candidate)
    key = scanner_repro_candidate_key(candidate)
    assert all(key)

    def verified_rows(_result):
        if tamper == "missing-audit":
            return {}
        row = deepcopy(audit)
        if tamper == "wrong-condition":
            row["conditions"]["passed"] = 0
        return {key: row}

    monkeypatch.setattr(catalog_module, "verified_scanner_repro_rows", verified_rows)
    request = ProspectiveCaptureRequest(
        market_scope="KOSPI", requested_as_of=FIXTURE_DATE,
        candidate_limit=1, horizon_intent="SHORT",
        horizon_policy_version="VN_P1_S2_HORIZON_CONTEXT_V1",
        selection_policy_id=pin.policy_id,
        selection_policy_hash=pin.policy_hash,
    )
    selection = pin.metadata()
    if tamper == "wrong-policy":
        selection = {**selection, "policy_hash": "not-the-real-pin"}

    # Exercise the exact source-row binding that finalize_capture uses before
    # freezing. No real market store, network, paid review or operational DB.
    from app.strategy.semantic_policy_provenance import validate_pinned_selection_policy
    policy_verified, policy_reason = validate_pinned_selection_policy(
        scanner_policy=selection,
        request_policy_id=request.selection_policy_id,
        request_policy_hash=request.selection_policy_hash,
        pin=pin,
    )
    verified = verified_rows({})
    snapshot = ProspectiveCatalog._candidate_snapshot(
        candidate, selection_policy=selection, audited=verified.get(key),
        selection_policy_pin=pin,
        policy_verified=policy_verified,
        policy_reason=policy_reason,
    )
    assert snapshot.get("priority") == candidate.get("priority")
    assert snapshot["rank"] == candidate["rank"]
    assert snapshot["risk"] == candidate["risk"]
    assert snapshot["strategy_version_id"] == candidate["strategy_version_id"]
    assert snapshot["strategy_definition_hash"] == candidate["strategy_definition_hash"]

    if tamper is None:
        assert snapshot["semantic_policy_provenance"]["status"] == "VERIFIED_PINNED_EXECUTION"
        evidence = snapshot["semantic_condition_evidence"]
        assert evidence["source"] == "SCANNER_REPRO_ENGINE_PASSED_CONDITIONS_V1"
        assert len(evidence["items"]) == len(condition_sources(candidate["strategy"]))
        assert {item["status"] for item in evidence["items"]} == {"PASS"}
        assert verify_semantic_source_v2(snapshot["semantic_source_v2"]) == (True, None)
        assert snapshot["semantic_source_v2"]["strategy"]["strategy_version_id"] == candidate["strategy_version_id"]
    else:
        assert "semantic_condition_evidence" not in snapshot
        assert snapshot["semantic_source_v2"]["strategy"]["strategy_version_id"] is None
        assert (
            snapshot["semantic_policy_provenance"]["status"] == "UNVERIFIED"
            if tamper == "wrong-policy" else True
        )


def test_begin_finalize_fresh_active_candidate_preserves_v2_snapshot_end_to_end(
    tmp_path, monkeypatch,
):
    """Actual Prospective begin/finalize/list calls on authored local SQLite.

    Fresh repro reader is substituted with a controlled authored row, not a
    fake real-market audit or evidence of external disclosure permission.
    """
    import app.prospective.catalog as catalog_module
    from app.jev.synthetic_live_01 import prepare_synthetic_service
    from app.prospective.models import digest_json

    db = tmp_path / "authored-fresh-active.db"
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
    candidate = _candidate()
    pin = _pin(candidate)
    key = scanner_repro_candidate_key(candidate)
    monkeypatch.setattr(
        catalog_module, "verified_scanner_repro_rows",
        lambda _result: {key: _audited(candidate)},
    )
    request = ProspectiveCaptureRequest(
        market_scope="KOSPI", requested_as_of=FIXTURE_DATE,
        candidate_limit=1, horizon_intent="SHORT",
        horizon_policy_version="VN_P1_S2_HORIZON_CONTEXT_V1",
        selection_policy_id=pin.policy_id,
        selection_policy_hash=pin.policy_hash,
    )
    source_job = "authored-active-fresh"
    catalog = ProspectiveCatalog(db)
    initial = catalog.begin_capture(source_job_id=source_job, request=request)
    result = {
        "version": "AUTHORED-NEW-SCANNER",
        "scanner_cache_hit": False,
        "market_scope": "KOSPI",
        "requested_as_of": FIXTURE_DATE,
        "input_fingerprint": "authored-test-original-input",
        "summary": {"candidate_count": 1},
        "candidates": [candidate],
        "more_candidates": [],
        "partial_data": False,
        "strategy_selection_policy": pin.metadata(),
        "diagnostics": {
            "reproducibility_audit": {"production_baseline": "authored-baseline"}
        },
    }
    frozen = catalog.finalize_capture(
        source_job_id=source_job, request=request, result=result,
        selection_policy_pin=pin,
    )
    assert frozen["id"] == initial["id"]
    assert frozen["status"] == "COMPLETE"
    assert frozen["horizon_intent"] == "SHORT"
    assert frozen["request"]["selection_policy_id"] == pin.policy_id
    assert frozen["request"]["selection_policy_hash"] == pin.policy_hash
    rows = catalog.list_samples(capture_run_id=frozen["id"])
    assert len(rows) == 1
    saved = rows[0]
    snap = saved["snapshot"]
    assert saved["snapshot_hash"] == digest_json(snap)
    assert snap["strategy_version_id"] == candidate["strategy_version_id"]
    assert snap["strategy_definition_hash"] == candidate["strategy_definition_hash"]
    assert snap["semantic_policy_provenance"]["status"] == "VERIFIED_PINNED_EXECUTION"
    assert snap["semantic_condition_evidence"]["source"] == "SCANNER_REPRO_ENGINE_PASSED_CONDITIONS_V1"
    assert verify_semantic_source_v2(snap["semantic_source_v2"]) == (True, None)
    assert snap["risk"] == candidate["risk"]
    assert saved["rank"] == 1

    # Exact historical capture idempotence, with no snapshot rewrite.
    replayed = catalog.finalize_capture(
        source_job_id=source_job, request=request, result=result,
        selection_policy_pin=pin,
    )
    assert replayed["id"] == frozen["id"]
    assert catalog.list_samples(capture_run_id=frozen["id"])[0]["snapshot_hash"] == saved["snapshot_hash"]
