"""Phase-1 fresh capture proof: real Prospective writer + strictly offline audit."""
from __future__ import annotations

from copy import deepcopy
import json
import sqlite3

import pytest

from app.jev.scanner_capture_proof import inspect_capture_proof_readonly
from app.jev.scanner_reviewer_bridge import inspect_reviewer_candidate_readonly
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest
from app.simulation.strategy_change import production_blocked_approval_protocol
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_semantics import condition_sources
from app.strategy.production_selection_policy import (
    SELECTION_POLICY_CONTRACT_VERSION, SelectionPolicyPin,
    ProductionStrategySelectionRegistry, SelectionPolicyError,
)
import app.strategy.semantic_identity_bridge as source_bridge
from tools.data.jev_s7_shadow import build_parser, execute
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


DATE = "2026-10-08"
STRATEGY = "trend_following"


def _write_fresh_fixture(
    tmp_path, monkeypatch, *, missing_repro=False, conflict_rank=False,
    policy_pin=None,
):
    """Synthetic isolated Scanner output, executed via *real* ProspectiveCatalog.

    A test-only ACTIVE-like pin is injected here; no Q7 approval is manufactured
    in the real policy registry and no runtime source is touched.
    """
    db = tmp_path / "sim.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE synthetic_placeholder (id INTEGER PRIMARY KEY)")
    migrate_prospective_store(db)
    definition = next(
        row for row in current_strategy_definitions()
        if row.strategy_key == STRATEGY
    )
    conditions = list(condition_sources(STRATEGY))
    pin = SelectionPolicyPin(
        policy_id="test-only-policy",
        policy_hash="test-only-policy-hash",
        policy_contract_version=SELECTION_POLICY_CONTRACT_VERSION,
        policy_source="ACTIVE_SELECTION_POLICY",
        fallback_used=False,
        fallback_reason=None,
        operating_strategies=((
            definition.strategy_version_id, STRATEGY, definition.definition_hash,
        ),),
        scanner_baseline_id="SYNTHETIC_TEST_BASELINE",
        production_fingerprint="SYNTHETIC_TEST_FINGERPRINT",
        production_policy_fingerprint="SYNTHETIC_TEST_POLICY_FINGERPRINT",
    )
    if policy_pin is not None:
        pin = policy_pin
    candidate = {
        "market": "KOSPI", "code": "000001", "name": "synthetic-entry",
        "strategy": STRATEGY, "action": "ENTRY_CANDIDATE",
        "candidate_state": "READY", "decision_status": "READY",
        "data_date": DATE, "priority": {"rank": 1, "tier": "READY"},
        "strategy_version_id": definition.strategy_version_id,
        "strategy_definition_hash": definition.definition_hash,
        "risk": {"status": "READY", "warning": False},
        "conditions": {
            "passed": len(conditions), "total": len(conditions),
            "missing": 0, "top_missing": [],
        },
        "entry_risk_guide": {"price_rule": {
            "basis": "현재가가 20일 이동평균선 위",
            "semantic_role": "STRATEGY_REFERENCE",
            "executable_entry_range": False,
        }},
    }
    if conflict_rank:
        candidate["rank"] = 99

    repro_root = tmp_path / "repro"
    repro_root.mkdir()
    monkeypatch.setattr(source_bridge, "REPRO_ROOT", repro_root)
    filename = "scanner-repro_fixture.json"
    audited = {
        **candidate,
        "scanner_inputs": {"condition_details": [
            {"raw": raw, "condition_id": f"condition-{i}", "status": "PASS"}
            for i, raw in enumerate(conditions, 1)
        ]},
    }
    repro_payload = {
        "result_source": "fresh_analysis",
        "scanner_version": "synthetic-scanner-v1",
        "analysis_date": DATE, "market_scope": "ALL",
        "existing_latest_day_fingerprint": "synthetic-fingerprint",
        "candidate_pool_complete": True, "candidate_count": 1,
        "candidates": [audited],
    }
    path = repro_root / filename
    path.write_text(json.dumps(repro_payload, ensure_ascii=False), encoding="utf-8")
    result = {
        "version": "synthetic-scanner-v1", "scanner_cache_hit": False,
        "requested_as_of": DATE, "market_scope": "ALL",
        "input_fingerprint": "synthetic-fingerprint",
        "partial_data": False,
        "summary": {"candidate_count": 1, "shown_count": 1},
        "candidates": [candidate], "more_candidates": [],
        "strategy_selection_policy": pin.metadata(),
        "diagnostics": {"reproducibility_audit": {
            "written": not missing_repro,
            "result_source": "fresh_analysis",
            "filename": filename, "path": str(path),
            "analysis_date": DATE, "candidate_count": 1,
            "production_baseline": "SYNTHETIC_TEST_BASELINE",
        }},
    }
    request = ProspectiveCaptureRequest(
        market_scope="ALL", requested_as_of=DATE, candidate_limit=5,
        horizon_intent="SHORT",
        horizon_policy_version="VN_P1_S2_HORIZON_CONTEXT_V1",
        selection_policy_id=pin.policy_id,
        selection_policy_hash=pin.policy_hash,
    )
    catalog = ProspectiveCatalog(db)
    catalog.begin_capture(source_job_id="synthetic-only-job", request=request)
    saved = catalog.finalize_capture(
        source_job_id="synthetic-only-job",
        request=request, result=result, selection_policy_pin=pin,
    )
    return db, saved["id"]


def test_fresh_capture_writer_to_strict_review_input_offline(tmp_path, monkeypatch):
    db, capture_id = _write_fresh_fixture(tmp_path, monkeypatch)
    before = db.read_bytes()
    result = inspect_capture_proof_readonly(db, capture_id=capture_id)
    assert result["status"] == "CAPTURE_INPUT_READY_PROVIDER_HOLD", result["records"]
    assert result["entry_candidates"] == result["contract_ready"] == 1
    assert result["inspected_samples"] == result["expected_samples"] == 1
    assert result["reference_candidates"] == result["blocked"] == 0
    assert result["provider_calls"] == result["runtime_db_writes"] == 0
    assert result["actual_provider_eligible"] is False
    assert "input" not in result and "price" not in str(result)
    assert db.read_bytes() == before
    assert inspect_reviewer_candidate_readonly(
        db, capture_id=capture_id, sample_index=0,
    )["status"] == "LOCAL_PROJECTION_READY_PROVIDER_HOLD"
    args = build_parser().parse_args([
        "capture-proof", "--simulation-db", str(db),
        "--capture-id", capture_id, "--json",
    ])
    assert execute(args)["status"] == result["status"]
    assert db.read_bytes() == before


@pytest.mark.parametrize("failure", ["missing_repro", "conflict_rank"])
def test_fresh_capture_missing_provenance_stays_blocked(tmp_path, monkeypatch, failure):
    db, capture_id = _write_fresh_fixture(
        tmp_path, monkeypatch,
        missing_repro=failure == "missing_repro",
        conflict_rank=failure == "conflict_rank",
    )
    before = db.read_bytes()
    result = inspect_capture_proof_readonly(db, capture_id=capture_id)
    assert result["status"] == "CAPTURE_NOT_READY"
    assert result["contract_ready"] == 0
    assert result["blocked"] == 1
    assert result["records"][0]["status"] == "HOLD"
    if failure == "conflict_rank":
        assert result["records"][0]["reason_code"] == "BASELINE_RANK_MISMATCH"
        assert result["records"][0]["rank_diagnostic"] in (
            "RANK_MISSING", "RANK_REPRO_CONFLICT",
        )
    assert result["provider_calls"] == result["runtime_db_writes"] == 0
    assert db.read_bytes() == before


def test_capture_proof_does_not_rescue_missing_or_partial_captures(tmp_path, monkeypatch):
    db, capture_id = _write_fresh_fixture(tmp_path, monkeypatch)
    before = db.read_bytes()
    assert inspect_capture_proof_readonly(
        db, capture_id="not-existing",
    )["reason_code"] == "CAPTURE_NOT_FOUND"
    assert inspect_capture_proof_readonly(
        db, capture_id=capture_id, max_samples=0,
    )["reason_code"] == "CAPTURE_AUDIT_LIMIT_INVALID"
    assert inspect_capture_proof_readonly(
        db, capture_id=capture_id, max_samples=True,
    )["reason_code"] == "CAPTURE_AUDIT_LIMIT_INVALID"
    assert db.read_bytes() == before



class _IsolatedQ7TestChange:
    """Only in-memory test approval; never a production StrategyChangeService."""

    def __init__(self, *, test_only=True):
        defs = current_strategy_definitions()
        rows = [
            {"strategy_version_id": x.strategy_version_id,
             "strategy_key": x.strategy_key, "definition_hash": x.definition_hash}
            for x in defs
        ]
        self.proposal = {
            "id": "proposal-q7-fixture", "proposal_hash": "proposal-q7-fixture-hash",
            "proposal_integrity": "MATCH",
            "evidence_bundle_hash": "synthetic-evidence",
            "base_registry_snapshot_hash": "synthetic-registry",
            "candidate_policy_intent_hash": "synthetic-intent",
            "rollback_basis_hash": "synthetic-rollback",
            "candidate_policy_intent": {
                "operating_strategies": rows,
                "risk_gate_preserved": True,
                "no_trade_safety_path_preserved": True,
                "score_formula_changed": False,
                "candidate_priority_changed": False,
                "production_activation_performed": False,
            },
            "rollback_basis": {
                "operating_strategies": rows,
                "scanner_baseline_id": "SYNTHETIC_BASELINE",
                "production_fingerprint": "SYNTHETIC_PROD",
                "production_policy_fingerprint": "SYNTHETIC_POLICY",
            },
            "scanner_baseline_id": "SYNTHETIC_BASELINE",
            "production_fingerprint": "SYNTHETIC_PROD",
            "production_policy_fingerprint": "SYNTHETIC_POLICY",
            "created_at": "2026-10-08T08:00:00+00:00",
        }
        self.approval = {
            "id": "approval-q7-fixture", "approval_hash": "approval-q7-hash",
            "approval_integrity": "MATCH",
            "proposal_id": self.proposal["id"],
            "proposal_hash": self.proposal["proposal_hash"],
            "evidence_bundle_hash": self.proposal["evidence_bundle_hash"],
            "registry_snapshot_hash": self.proposal["base_registry_snapshot_hash"],
            "candidate_policy_intent_hash": self.proposal["candidate_policy_intent_hash"],
            "rollback_basis_hash": self.proposal["rollback_basis_hash"],
            "approved_at": "2026-10-08T08:00:00+00:00",
            "approval_context": {"protocol": {"test_only": test_only}},
        }

    def get_approval(self, key):
        assert key == self.approval["id"]
        return deepcopy(self.approval)

    def get_proposal(self, key):
        assert key == self.proposal["id"]
        return deepcopy(self.proposal)

    def verify_proposal(self, key):
        assert key == self.proposal["id"]
        return {"status": "CURRENT"}


def _isolated_registry(root, change, *, allow_test_activation, baseline_provider):
    return ProductionStrategySelectionRegistry(
        runtime_dir=root / "q7_test_selection",
        change_service=change,
        allow_test_activation=allow_test_activation,
        clock=lambda: "2026-10-08T08:00:00+00:00",
        baseline_identity_provider=baseline_provider,
    )


def test_q7_test_only_p5_activation_to_real_prospective_writer_to_s3(
    tmp_path, monkeypatch,
):
    """Exercise the full sanctioned test-only lifecycle; no production Q7 approval."""
    baseline = {
        "scanner_baseline_id": "SYNTHETIC_BASELINE",
        "production_fingerprint": "SYNTHETIC_PROD",
        "production_policy_fingerprint": "SYNTHETIC_POLICY",
    }
    change = _IsolatedQ7TestChange()
    blocked = _isolated_registry(
        tmp_path / "blocked", change, allow_test_activation=False,
        baseline_provider=lambda: dict(baseline),
    )
    with pytest.raises(SelectionPolicyError) as err:
        blocked.activate_approved_policy(
            approval_artifact_id="approval-q7-fixture", expected_active_policy_id=None,
        )
    assert err.value.code == "TEST_APPROVAL_ACTIVATION_FORBIDDEN"
    assert not blocked.active_path.exists()

    # A test gate can exercise P5's actual snapshot + pin validation in a
    # temporary directory, but NEVER yields an approved production Q7 protocol.
    registry = _isolated_registry(
        tmp_path, change, allow_test_activation=True,
        baseline_provider=lambda: dict(baseline),
    )
    activated = registry.activate_approved_policy(
        approval_artifact_id="approval-q7-fixture", expected_active_policy_id=None,
    )
    assert activated["changed"] is True
    pin = registry.pin_active_selection_policy()
    assert pin.policy_source == "ACTIVE_SELECTION_POLICY"
    assert pin.strategy_reference(STRATEGY)["strategy_version_id"]
    assert pin.strategy_reference(STRATEGY)["definition_hash"]
    assert production_blocked_approval_protocol().activation_eligible is False

    db, capture_id = _write_fresh_fixture(
        tmp_path, monkeypatch, policy_pin=pin,
    )
    before = db.read_bytes()
    proof = inspect_capture_proof_readonly(
        db, capture_id=capture_id, runtime_dir=registry.runtime_dir,
    )
    assert proof["status"] == "CAPTURE_INPUT_READY_PROVIDER_HOLD", proof["records"]
    assert proof["contract_ready"] == 1
    gate = proof["current_policy_gate"]
    assert gate["selection_policy_source"] == "LEGACY_CURRENT_10_FALLBACK" or (
        gate["selection_policy_source"] == "ACTIVE_SELECTION_POLICY"
    )
    assert gate["q7_activation_eligible"] is False
    assert gate["q7_precommitted"] is False
    assert gate["cannot_upgrade_frozen_capture"] is True
    assert gate["observed_at_inspection_not_capture"] is True
    assert gate["jev_trial_approved"] is False
    assert gate["model_data_transmission_approved"] is False
    assert proof["provider_calls"] == proof["runtime_db_writes"] == 0
    assert db.read_bytes() == before

    # A subsequent baseline mismatch must NOT turn a previously frozen
    # canonical capture into a different original Scanner decision.
    registry.baseline_identity_provider = lambda: {
        **baseline, "production_fingerprint": "DIFFERENT_BASELINE",
    }
    assert registry.pin_active_selection_policy().policy_source == (
        "LEGACY_CURRENT_10_FALLBACK"
    )
    proof_after = inspect_capture_proof_readonly(
        db, capture_id=capture_id, runtime_dir=registry.runtime_dir,
    )
    assert proof_after["status"] == "CAPTURE_INPUT_READY_PROVIDER_HOLD"
    assert proof_after["current_policy_gate"]["q7_activation_eligible"] is False
    assert db.read_bytes() == before


def test_q7_research_and_spoofed_operating_approval_cannot_activate(
    tmp_path,
):
    """A plausible non-test approval is still Q7-unapproved in production."""
    service = _IsolatedQ7TestChange(test_only=False)
    registry = _isolated_registry(
        tmp_path, service, allow_test_activation=True,
        baseline_provider=lambda: {},
    )
    with pytest.raises(SelectionPolicyError) as err:
        registry.activate_approved_policy(
            approval_artifact_id="approval-q7-fixture", expected_active_policy_id=None,
        )
    assert err.value.code == "Q7_APPROVAL_PROTOCOL_UNAPPROVED"
    assert not registry.active_path.exists()
