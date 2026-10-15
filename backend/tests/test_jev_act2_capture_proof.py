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



def _study_spec():
    """Explicit synthetic thresholds are ONLY for contract/CLI tests."""
    from app.jev.q7_precommit_s15 import template
    spec = template(STRATEGY)
    spec.update({
        "study_id": "synthetic-study-fixture",
        "operator": "SYNTHETIC_TEST_OPERATOR",
        "market_scope": "KOSPI",
    })
    spec["time_split"].update({
        "development_start": "2026-10-01",
        "development_end": "2026-10-14",
        "holdout_start": "2026-11-16",
        "holdout_end": "2027-03-31",
        "purge_trading_days": 20,
    })
    spec["population"].update({
        "universe_rule": "Frozen KOSPI test candidates whose membership was known on signal date",
        "regime_rule": "Use past-only index bands and a fixed prior window for labels",
        "minimum_independent_samples_total": 40,
        "minimum_independent_samples_per_regime": 8,
        "maturity_trading_days": 20,
    })
    spec["comparison"].update({
        "round_trip_cost_pct": 0.2,
        "fee_pct": 0.05, "tax_pct": 0.1, "slippage_pct": 0.1,
        "min_outperformance_pct": 1.5,
        "max_drawdown_pct": 12,
        "confidence_level_pct": 95,
        "multiple_testing_rule": "Control false discoveries across all fixed prospective strategy cohorts",
    })
    spec["decision"].update({
        "promotion_rule": "Only promote following a separately verified independent holdout evaluation",
        "abstain_rule": "Always abstain when original strategy identity or source timestamps are unproven",
        "demotion_rule": "Demote only after a separately specified future regression criterion",
        "rollback_rule": "Restore the pinned previous policy on a verified safety regression",
    })
    return spec


def _frozen_study(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.jev.q7_precommit_s15 import freeze

    root = tmp_path / "isolated-research-freeze"
    spec = _study_spec()
    record = freeze(
        spec, root=root,
        now=datetime(2026, 10, 15, 9, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    assert record["q7_approval_eligible"] is False
    return spec, root


def test_q7_study_v1_real_capture_binding_keeps_approval_blocked(tmp_path, monkeypatch):
    from datetime import date
    from app.jev.q7_study_audit import audit_study_readonly

    db, capture_id = _write_fresh_fixture(tmp_path, monkeypatch)
    spec, root = _frozen_study(tmp_path)
    before_db = db.read_bytes()
    before_study = (root / (spec["study_id"] + ".json")).read_bytes()

    r = audit_study_readonly(
        db, study_id=spec["study_id"], root=root, as_of=date(2026, 10, 15),
    )
    assert r["status"] == "RESEARCH_STUDY_HOLD", r
    assert r["counts_complete"] is True
    assert r["matched_entry_rows"] == r["distinct_signal_keys_descriptive"] == 1
    assert r["cohorts"]["DEVELOPMENT"]["strict_original_identity_match"] == 1
    assert r["cohorts"]["HOLDOUT"]["matched_entries"] is None
    assert r["cohorts"]["HOLDOUT"]["inspection_status"] == "LOCKED_NOT_QUERIED"
    assert "FUTURE_HOLDOUT_NOT_STARTED" in r["remaining_blockers"]
    assert r["independent_samples_verified"] is None
    assert r["trusted_source_publication_time_proven"] is False
    assert r["q7_approval_eligible"] is False
    assert r["production_activation_allowed"] is False
    assert r["external_provider_calls"] == r["runtime_db_writes"] == 0
    assert db.read_bytes() == before_db
    assert (root / (spec["study_id"] + ".json")).read_bytes() == before_study

    args = __import__(
        "tools.data.q7_precommit", fromlist=["parser"]
    ).parser().parse_args([
        "study-audit", "--study-id", spec["study_id"],
        "--store-dir", str(root), "--simulation-db", str(db),
        "--as-of", "2026-10-15",
    ])
    from tools.data import q7_precommit as cli
    assert cli.execute(args)["study_spec_hash"] == r["study_spec_hash"]


def test_q7_study_future_holdout_and_missing_history_are_not_promoted(tmp_path):
    from datetime import date
    from app.jev.q7_study_audit import audit_study_readonly
    spec, root = _frozen_study(tmp_path)
    missing = audit_study_readonly(
        tmp_path / "missing.db", study_id=spec["study_id"], root=root,
    )
    assert missing["status"] == "NO_SIMULATION_DB"
    assert missing["counts_complete"] is False
    assert missing["production_activation_allowed"] is False
    assert audit_study_readonly(
        tmp_path / "missing.db", study_id=spec["study_id"], root=root,
        as_of=date(2099, 1, 1),
    )["status"] == "INVALID_AS_OF"


def test_q7_study_unexpected_extra_frozen_reference_fails_closed(tmp_path, monkeypatch):
    from datetime import date
    from app.jev.q7_study_audit import audit_study_readonly

    db, capture_id = _write_fresh_fixture(tmp_path, monkeypatch)
    spec, root = _frozen_study(tmp_path)
    # Only insert an extra row into an isolated synthetic DB. The immutable
    # COMPLETE capture must keep its original expected count unchanged;
    # a new unaccounted-for reference must block the study audit.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO prospective_recommendation_sample("
            "capture_run_id,sample_index,market,ticker,name,rank,"
            "strategy,decision_status,candidate_state,action,signal_date,"
            "snapshot_json,snapshot_hash,created_at) "
            "SELECT capture_run_id,1,market,'000002',name,rank,"
            "strategy,decision_status,candidate_state,'REFERENCE_ONLY',"
            "signal_date,snapshot_json,'broken',created_at "
            "FROM prospective_recommendation_sample WHERE capture_run_id=? "
            "AND sample_index=0",
            (capture_id,),
        )
    before = db.read_bytes()
    result = audit_study_readonly(
        db, study_id=spec["study_id"], root=root,
        as_of=date(2026, 10, 15),
    )
    assert result["status"] == "STUDY_CAPTURE_PROOF_INCOMPLETE"
    assert result["counts_complete"] is False
    assert result["q7_approval_eligible"] is False
    assert db.read_bytes() == before


def test_q7_study_capture_original_strategy_identity_must_match_frozen_spec(
    tmp_path, monkeypatch,
):
    from datetime import date
    from app.jev import q7_study_audit
    db, _ = _write_fresh_fixture(tmp_path, monkeypatch)
    spec, root = _frozen_study(tmp_path)
    source_reader = q7_study_audit.load_canonical_candidate_readonly

    def differing_original(*args, **kwargs):
        capture, sample = source_reader(*args, **kwargs)
        cloned = {**sample, "snapshot": {
            **sample["snapshot"],
            "strategy_definition_hash": "0" * 64,
        }}
        return capture, cloned

    monkeypatch.setattr(
        q7_study_audit, "load_canonical_candidate_readonly", differing_original,
    )
    result = q7_study_audit.audit_study_readonly(
        db, study_id=spec["study_id"], root=root,
        as_of=date(2026, 10, 15),
    )
    assert result["counts_complete"] is True
    assert result["cohorts"]["DEVELOPMENT"]["study_strategy_version_mismatch"] == 1
    assert result["cohorts"]["DEVELOPMENT"]["strict_original_identity_match"] == 0
    assert "STUDY_STRATEGY_VERSION_MISMATCH" in result["failure_reasons"]



def test_s23_readonly_lineage_receipt_after_real_prospective_writer(tmp_path, monkeypatch):
    """Actual isolated writer → strict S3 proof → S23 daily evidence receipt."""
    from app.jev.daily_capture_lineage_s23 import audit_daily_capture_readonly
    db, capture_id = _write_fresh_fixture(tmp_path, monkeypatch)
    original = db.read_bytes()
    result = audit_daily_capture_readonly(
        db, capture_id=capture_id, expected_source_date=DATE,
        runtime_dir=tmp_path / "unapproved_selection",
    )
    assert result["status"] == "SOURCE_CONTRACT_READY_Q7_HOLD", result
    assert result["strict_jev_input_ready"] is True
    assert result["contract_ready_candidates"] == 1
    assert result["original_source_date_matches_requested"] is True
    assert result["q7_approval_eligible"] is False
    assert result["q7_research_study_bound"] is False
    assert result["independent_timestamp_attestation"] is False
    assert result["verified_provider_publication_timestamp"] is False
    assert result["external_ai_calls"] == result["runtime_db_writes"] == 0
    assert "name" not in result and "price" not in result
    assert db.read_bytes() == original

    wrong_date = audit_daily_capture_readonly(
        db, capture_id=capture_id, expected_source_date="2026-10-07",
        runtime_dir=tmp_path / "unapproved_selection",
    )
    assert wrong_date["status"] == "HOLD"
    assert wrong_date["reason_code"] == "SOURCE_DATE_OR_REQUEST_MISMATCH"
    assert wrong_date["strict_jev_input_ready"] is False
    assert db.read_bytes() == original


def test_s23_original_rank_conflict_blocks_receipt(tmp_path, monkeypatch):
    from app.jev.daily_capture_lineage_s23 import audit_daily_capture_readonly
    db, capture_id = _write_fresh_fixture(tmp_path, monkeypatch, conflict_rank=True)
    before = db.read_bytes()
    outcome = audit_daily_capture_readonly(
        db, capture_id=capture_id, expected_source_date=DATE,
        runtime_dir=tmp_path / "unapproved_selection",
    )
    assert outcome["status"] == "CAPTURE_EVIDENCE_INCOMPLETE"
    assert outcome["strict_jev_input_ready"] is False
    assert outcome["contract_blocked_candidates"] == 1
    assert outcome["q7_approval_eligible"] is False
    assert db.read_bytes() == before


def test_s23_missing_or_invalid_source_never_synthesizes_lineage(tmp_path):
    from app.jev.daily_capture_lineage_s23 import audit_daily_capture_readonly
    missing_db = tmp_path / "not_created.db"
    result = audit_daily_capture_readonly(
        missing_db, capture_id="synthetic-capture", expected_source_date=DATE,
    )
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "SIMULATION_DB_NOT_FOUND"
    assert not missing_db.exists()
    assert audit_daily_capture_readonly(
        missing_db, capture_id="synthetic-capture", expected_source_date="invalid",
    )["reason_code"] == "EXPECTED_SOURCE_DATE_INVALID"



def test_s23_direct_cli_date_bound_and_no_side_effects(tmp_path, monkeypatch):
    from tools.data.jev_s7_shadow import build_parser, execute
    from app.jev.decision_reviewer_offline import DecisionReviewContractError

    db, capture_id = _write_fresh_fixture(tmp_path, monkeypatch)
    old = db.read_bytes()
    parsed = build_parser().parse_args([
        "daily-lineage", "--capture-id", capture_id,
        "--expected-source-date", DATE, "--simulation-db", str(db), "--json",
    ])
    report = execute(parsed)
    assert report["status"] == "SOURCE_CONTRACT_READY_Q7_HOLD"
    assert report["q7_approval_eligible"] is False
    assert report["verified_provider_publication_timestamp"] is False
    assert db.read_bytes() == old
    with pytest.raises(DecisionReviewContractError) as caught:
        execute(build_parser().parse_args([
            "daily-lineage", "--capture-id", capture_id,
            "--expected-source-date", DATE, "--limit", "1",
            "--simulation-db", str(db),
        ]))
    assert caught.value.code == "DAILY_LINEAGE_ARGUMENT_CONFLICT"
