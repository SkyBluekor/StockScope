"""ACT2-S3 offline, real-shaped Prospective rows; no production DB or model."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from app.jev.decision_reviewer_offline import (
    DecisionReviewContractError, OfflineFakeShadowSession,
    audit_capture_review_scope_readonly,
    build_scanner_review_input, load_canonical_candidate_readonly,
    validate_decision_review_response,
)
from app.prospective.models import digest_json
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_semantics import condition_sources
from app.strategy.semantic_source_v2 import build_semantic_source_v2
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


STRATEGY = "trend_following"
DATE = "2026-10-08"


def _stored(tmp_path: Path, *, horizon: str = "SHORT", mutate_snapshot=None) -> tuple[Path, str]:
    db = tmp_path / "isolated_s3.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE synthetic_placeholder(id INTEGER PRIMARY KEY)")
    migrate_prospective_store(db)
    definition = next(d for d in current_strategy_definitions() if d.strategy_key == STRATEGY)
    conditions = list(condition_sources(STRATEGY))
    candidate = {
        "market": "KOSPI", "code": "000001", "name": "synthetic-only",
        "strategy": STRATEGY, "action": "ENTRY_CANDIDATE",
        "candidate_state": "READY", "decision_status": "READY",
        "data_date": DATE, "strategy_version_id": definition.strategy_version_id,
        "strategy_definition_hash": definition.definition_hash,
        "priority": {"rank": 1, "tier": "READY"},
        "conditions": {
            "passed": len(conditions), "total": len(conditions),
            "missing": 0, "top_missing": [],
        },
        "risk": {"status": "READY", "warning": False},
        "entry_risk_guide": {"price_rule": {
            "basis": "현재가가 20일 이동평균선 위",
            "semantic_role": "STRATEGY_REFERENCE",
            "executable_entry_range": False,
        }},
        "semantic_policy_provenance": {
            "status": "VERIFIED_PINNED_EXECUTION",
            "policy_id": "synthetic-policy", "policy_hash": "synthetic-policy-hash",
        },
        "semantic_condition_evidence": {
            "source": "SCANNER_REPRO_EVIDENCE",
            "strategy_key": STRATEGY,
            "passed": len(conditions), "total": len(conditions), "missing": 0,
            "items": [
                {"condition_id": f"condition-{i}", "source_condition": source,
                 "status": "PASS"}
                for i, source in enumerate(conditions, 1)
            ],
        },
    }
    candidate["semantic_source_v2"] = build_semantic_source_v2(candidate)
    assert candidate["semantic_source_v2"]["readiness"]["q2_status"] == "COMPLETE"
    assert candidate["semantic_source_v2"]["readiness"]["local_semantic_status"] == "LOCAL_MATCH"
    if mutate_snapshot is not None:
        mutate_snapshot(candidate)  # Fixture construction only, before immutable INSERT.
    capture_id = "s3-complete"
    request = {
        "selection_policy_id": "synthetic-policy",
        "selection_policy_hash": "synthetic-policy-hash",
    }
    with sqlite3.connect(db) as conn:
        conn.execute(
            """INSERT INTO prospective_capture_run(
                id,capture_version,source_job_id,status,request_json,
                market_scope,requested_as_of,actual_data_date,candidate_limit,
                horizon_intent,horizon_policy_version,scanner_version,
                source_execution_key,created_at,completed_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                capture_id, "SYNTHETIC_ONLY", "fake-job", "COMPLETE",
                json.dumps(request), "ALL", DATE, DATE, 5,
                horizon, "VN_P1_S2_HORIZON_CONTEXT_V1",
                "offline-scanner", "synthetic-execution",
                "2026-10-08T08:00:00Z", "2026-10-08T09:00:00Z",
                "2026-10-08T09:00:00Z",
            ),
        )
        conn.execute(
            """INSERT INTO prospective_recommendation_sample(
               capture_run_id,sample_index,market,ticker,name,rank,
               strategy,decision_status,candidate_state,action,signal_date,
               snapshot_json,snapshot_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                capture_id, 0, "KOSPI", "000001", "synthetic-only", 1,
                STRATEGY, "READY", "READY", "ENTRY_CANDIDATE", DATE,
                json.dumps(candidate, ensure_ascii=False),
                digest_json(candidate), "2026-10-08T09:00:00Z",
            ),
        )
    return db, capture_id


def _projection(db: Path, capture_id: str):
    capture, sample = load_canonical_candidate_readonly(
        db, capture_id=capture_id, sample_index=0
    )
    return build_scanner_review_input(capture, sample, protocol_id="FAKE-ONLY-S3")


def _reason(*, ref="condition-1", explanation="조건이 입력 근거와 일치합니다."):
    return {
        "code": "CONDITION_ALIGNMENT",
        "evidence_refs": [ref],
        "explanation": explanation,
    }


def _response(decision: str):
    return {
        "decision": decision,
        "abstain_reason": "INSUFFICIENT_EVIDENCE" if decision == "ABSTAIN" else None,
        "supporting_reasons": [_reason()] if decision == "PASS_THROUGH" else [],
        "opposing_reasons": [
            {"code": "CONDITION_CONFLICT", "evidence_refs": ["condition-1"],
             "explanation": "추가 확인해야 할 조건입니다."}
        ] if decision == "REVIEW_REQUIRED" else [],
    }


def _modified_copy(db: Path, capture_id: str, change):
    capture, sample = load_canonical_candidate_readonly(
        db, capture_id=capture_id, sample_index=0
    )
    change(sample["snapshot"])
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    return capture, sample


@pytest.mark.parametrize("decision,shadow", [
    ("PASS_THROUGH", "BASELINE_UNCHANGED"),
    ("REVIEW_REQUIRED", "DEFER_THIS_OPPORTUNITY"),
    ("ABSTAIN", "BASELINE_UNCHANGED"),
])
def test_stored_prospective_to_fake_shadow_without_mutation(tmp_path, decision, shadow):
    db, capture_id = _stored(tmp_path)
    with sqlite3.connect(db) as conn:
        before = "\n".join(conn.iterdump())
    projection = _projection(db, capture_id)
    assert projection["status"] == "OFFLINE_INSPECTABLE_ONLY"
    assert projection["actual_provider_eligible"] is False
    assert projection["input"]["as_of"]["time_proof"] == "EOD_DATE_ONLY_EXACT_RELEASE_TIME_UNPROVEN"
    assert len(projection["input"]["evidence_items"]) > 1
    assert projection["input"]["baseline_decision"]["risk"]["status"] == "READY"
    assert projection["input"]["missing_evidence"] == ["EXACT_SOURCE_RELEASE_TIMESTAMP"]
    session = OfflineFakeShadowSession()
    first = session.inspect(projection, _response(decision))
    second = session.inspect(projection, _response("REVIEW_REQUIRED"))
    assert first["status"] == "VALID"
    assert first["decision"] == decision
    assert first["shadow_action"] == shadow
    assert first["outcome_status"] == "NOT_EVALUATED"
    assert first["outcome_return"] is None
    assert second["reused"] is True
    assert second["decision"] == decision
    assert len(session.list_records()) == 1
    assert first["external_requests"] == 0
    with sqlite3.connect(db) as conn:
        assert before == "\n".join(conn.iterdump())


def test_duplicate_capture_references_same_canonical_shadow_identity(tmp_path):
    db, canonical = _stored(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """INSERT INTO prospective_capture_run(
                id,capture_version,source_job_id,status,request_json,
                market_scope,candidate_limit,horizon_intent,
                canonical_capture_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            ("s3-duplicate", "SYNTHETIC_ONLY", "duplicate-job", "DUPLICATE",
             "{}", "ALL", 5, "SHORT", canonical,
             "2026-10-09T00:00:00Z", "2026-10-09T00:00:00Z"),
        )
    direct = _projection(db, canonical)
    alias = _projection(db, "s3-duplicate")
    assert direct["input_hash"] == alias["input_hash"]
    session = OfflineFakeShadowSession()
    assert session.inspect(direct, _response("PASS_THROUGH"))["reused"] is False
    assert session.inspect(alias, _response("PASS_THROUGH"))["reused"] is True


def test_legacy_is_inspection_only_never_fake_review(tmp_path):
    db, capture_id = _stored(tmp_path, horizon="LEGACY_UNSPECIFIED")
    projection = _projection(db, capture_id)
    assert projection["status"] == "LEGACY_INSPECTION_ONLY"
    with pytest.raises(DecisionReviewContractError, match="HORIZON_NOT_FAKE_TEST_SCOPE"):
        OfflineFakeShadowSession().inspect(projection, _response("PASS_THROUGH"))


def test_external_provider_fails_without_use_or_credentials(tmp_path):
    db, capture_id = _stored(tmp_path)
    with pytest.raises(DecisionReviewContractError, match="EXTERNAL_PROVIDER_FORBIDDEN"):
        OfflineFakeShadowSession().inspect(
            _projection(db, capture_id), _response("PASS_THROUGH"),
            provider_id="TYPESAFE_SYSTEM_ONE",
        )


@pytest.mark.parametrize("change,reason", [
    (lambda x: x["risk"].update(status="BLOCK"), "RISK_BLOCKED_OUT_OF_SCOPE"),
    (lambda x: x.pop("semantic_policy_provenance"), "POLICY_PROVENANCE_UNVERIFIED"),
    (lambda x: x.update(data_date="2026-10-09"), "FUTURE_OR_MISMATCHED_EVIDENCE_DATE"),
    (lambda x: x.pop("entry_risk_guide"), "BASELINE_EVIDENCE_INCOMPLETE"),
    (lambda x: x["semantic_source_v2"].update(source_contract_hash="tampered"),
     "SEMANTIC_SOURCE_V2_CONTRACT_HASH_MISMATCH"),
])
def test_scope_evidence_temporal_and_policy_fail_closed(tmp_path, change, reason):
    db, capture_id = _stored(tmp_path)
    capture, modified_sample = _modified_copy(db, capture_id, change)
    with pytest.raises(DecisionReviewContractError, match=reason):
        build_scanner_review_input(
            capture, modified_sample, protocol_id="FAKE-ONLY-S3"
        )


def test_source_hash_tampering_and_non_complete_capture_fail_closed(tmp_path):
    db, capture_id = _stored(tmp_path)
    capture, sample = load_canonical_candidate_readonly(
        db, capture_id=capture_id, sample_index=0
    )
    sample["snapshot_hash"] = "forged"
    with pytest.raises(DecisionReviewContractError, match="SNAPSHOT_HASH_MISMATCH"):
        build_scanner_review_input(capture, sample, protocol_id="FAKE-ONLY-S3")
    # A separate never-completed capture is inserted, not an UPDATE to the
    # protected COMPLETE capture (immutable history remains untouched).
    with sqlite3.connect(db) as conn:
        conn.execute(
            """INSERT INTO prospective_capture_run(
                id,capture_version,source_job_id,status,request_json,
                market_scope,candidate_limit,horizon_intent,
                created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("s3-partial", "SYNTHETIC_ONLY", "partial-job", "PARTIAL",
             "{}", "ALL", 5, "LEGACY_UNSPECIFIED",
             "2026-10-09T00:00:00Z", "2026-10-09T00:00:00Z"),
        )
    with pytest.raises(DecisionReviewContractError, match="CAPTURE_NOT_COMPLETE"):
        load_canonical_candidate_readonly(
            db, capture_id="s3-partial", sample_index=0
        )


@pytest.mark.parametrize("tamper,reason", [
    (lambda r: r["opposing_reasons"][0].update(evidence_refs=["not-in-input"]),
     "RESPONSE_EVIDENCE_UNGROUNDED"),
    (lambda r: r["opposing_reasons"][0].update(explanation="목표주가 999999원"),
     "RESPONSE_UNSUPPORTED_NUMBER"),
    (lambda r: r.update(unsafe_trade_order="SELL"),
     "RESPONSE_SCHEMA_INVALID"),
    (lambda r: r.update(opposing_reasons=[]),
     "OPPOSING_EVIDENCE_REQUIRED"),
])
def test_fake_response_contract_rejects_fabrication(tmp_path, tamper, reason):
    db, capture_id = _stored(tmp_path)
    projection = _projection(db, capture_id)
    fake = _response("REVIEW_REQUIRED")
    tamper(fake)
    with pytest.raises(DecisionReviewContractError, match=reason):
        validate_decision_review_response(projection["input"], fake)
    record = OfflineFakeShadowSession().inspect(projection, fake)
    assert record["status"] == "ERROR"
    assert record["decision"] == "ABSTAIN"
    assert record["abstain_reason"] == "MODEL_ERROR"
    assert record["baseline_action"] == "ENTRY_CANDIDATE"
    assert record["shadow_action"] == "BASELINE_UNCHANGED"


def test_fake_input_tamper_is_not_accepted(tmp_path):
    db, capture_id = _stored(tmp_path)
    projection = _projection(db, capture_id)
    projection["input"]["baseline_decision"]["rank"] = 99
    with pytest.raises(DecisionReviewContractError, match="INPUT_IDENTITY_MISMATCH"):
        OfflineFakeShadowSession().inspect(projection, _response("PASS_THROUGH"))


def test_fake_shadow_records_are_copy_isolated(tmp_path):
    db, capture_id = _stored(tmp_path)
    projection = _projection(db, capture_id)
    session = OfflineFakeShadowSession()
    row = session.inspect(projection, _response("PASS_THROUGH"))
    row["decision"] = "REVIEW_REQUIRED"
    assert session.list_records()[0]["decision"] == "PASS_THROUGH"


def test_readonly_capture_scope_reports_exclusions_without_fake_calls(tmp_path):
    db, capture_id = _stored(tmp_path)
    report = audit_capture_review_scope_readonly(
        db, capture_id=capture_id, protocol_id="FAKE-ONLY-S3"
    )
    assert report["total_returned_samples"] == 1
    assert report["offline_inspectable"] == 1
    assert report["excluded"] == 0
    assert report["actual_provider_eligible"] == 0
    assert report["provider_calls"] == report["db_writes"] == 0

    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    blocked_db, blocked_id = _stored(
        blocked_dir, mutate_snapshot=lambda item: item["risk"].update(status="BLOCK")
    )
    result = audit_capture_review_scope_readonly(
        blocked_db, capture_id=blocked_id, protocol_id="FAKE-ONLY-S3"
    )
    assert result["excluded"] == 1
    assert result["reasons"]["RISK_BLOCKED_OUT_OF_SCOPE"] == 1


def test_malformed_abstain_reason_is_rejected_not_executed(tmp_path):
    db, capture_id = _stored(tmp_path)
    projection = _projection(db, capture_id)
    invalid = _response("ABSTAIN")
    invalid["abstain_reason"] = ["INSUFFICIENT_EVIDENCE"]
    record = OfflineFakeShadowSession().inspect(projection, invalid)
    assert record["status"] == "ERROR"
    assert record["failure_code"] == "ABSTAIN_REASON_INVALID"


# ACT2 Phase-1 integration: reuse S3 frozen source, S8's non-authorizing
# rights status, and the existing fake-only reviewer without re-ranking.
from app.jev.scanner_reviewer_bridge import (
    inspect_reviewer_candidate_readonly,
    inspect_synthetic_fake_review_readonly,
)
from tools.data.jev_s7_shadow import build_parser as s7_build_parser, execute as s7_execute


def test_phase1_bridge_inspects_real_shaped_source_without_source_export(tmp_path):
    db, capture_id = _stored(tmp_path)
    with sqlite3.connect(db) as conn:
        before = "\n".join(conn.iterdump())
    output = inspect_reviewer_candidate_readonly(
        db, capture_id=capture_id, sample_index=0,
    )
    assert output["status"] == "LOCAL_PROJECTION_READY_PROVIDER_HOLD"
    assert output["provider_gate"] == "NO_GO"
    assert output["source_rights"] == "UNVERIFIED"
    assert output["approved_trial_protocol"] is False
    assert output["actual_provider_eligible"] is False
    assert output["baseline_action"] == "ENTRY_CANDIDATE"
    assert output["baseline_rank"] == 1
    assert output["evidence_item_count"] >= 2
    assert output["publication_time_proven"] is False
    assert output["provider_calls"] == output["runtime_db_writes"] == 0
    assert "evidence_items" not in output
    assert "entry_risk_guide" not in output
    with sqlite3.connect(db) as conn:
        assert before == "\n".join(conn.iterdump())


@pytest.mark.parametrize("decision,action", [
    ("PASS_THROUGH", "BASELINE_UNCHANGED"),
    ("REVIEW_REQUIRED", "DEFER_THIS_OPPORTUNITY"),
    ("ABSTAIN", "BASELINE_UNCHANGED"),
])
def test_phase1_synthetic_only_fake_links_input_validation_without_ai(
    tmp_path, decision, action,
):
    db, capture_id = _stored(tmp_path)
    session = OfflineFakeShadowSession()
    result = inspect_synthetic_fake_review_readonly(
        db, capture_id=capture_id, sample_index=0,
        fake_response=_response(decision), session=session,
    )
    assert result["status"] == "SYNTHETIC_FAKE_REVIEW_ONLY"
    assert result["validation_status"] == "VALID"
    assert result["fake_decision"] == decision
    assert result["fake_shadow_action"] == action
    assert result["outcome_return"] is None
    assert result["provider_gate"] == "NO_GO"
    assert result["actual_provider_eligible"] is False
    assert result["external_requests"] == result["runtime_db_writes"] == 0
    assert result["production_action_modified"] is False
    assert result["investment_improvement_verified"] is False
    reused = inspect_synthetic_fake_review_readonly(
        db, capture_id=capture_id, sample_index=0,
        fake_response=_response("ABSTAIN"), session=session,
    )
    assert reused["reused"] is True
    assert reused["fake_decision"] == decision


def test_phase1_real_capture_is_never_silently_fake_reviewed(tmp_path, monkeypatch):
    from app.jev import scanner_reviewer_bridge as bridge

    db, capture_id = _stored(tmp_path)
    capture, sample, projection = bridge._candidate(
        db, capture_id=capture_id, sample_index=0,
    )
    # A completed Capture is immutable: exercise the REAL marker only on a
    # separate in-memory copy, never by updating the frozen SQLite source.
    real_capture = {**capture, "capture_version": "REAL"}
    monkeypatch.setattr(
        bridge, "_candidate",
        lambda *args, **kwargs: (real_capture, sample, projection),
    )
    plan = inspect_reviewer_candidate_readonly(
        db, capture_id=capture_id, sample_index=0,
    )
    assert plan["fake_only_available"] is False
    with pytest.raises(DecisionReviewContractError, match="REAL_CAPTURE_FAKE_REVIEW_FORBIDDEN"):
        inspect_synthetic_fake_review_readonly(
            db, capture_id=capture_id, sample_index=0,
            fake_response=_response("PASS_THROUGH"),
        )


def test_phase1_legacy_and_tampered_candidate_never_enable_provider(tmp_path):
    (tmp_path / "legacy").mkdir()
    legacy, lid = _stored(tmp_path / "legacy", horizon="LEGACY_UNSPECIFIED")
    result = inspect_reviewer_candidate_readonly(legacy, capture_id=lid, sample_index=0)
    assert result["status"] == "LEGACY_INSPECTION_ONLY"
    assert result["fake_only_available"] is False
    with pytest.raises(DecisionReviewContractError, match="HORIZON_NOT_FAKE_TEST_SCOPE"):
        inspect_synthetic_fake_review_readonly(
            legacy, capture_id=lid, sample_index=0,
            fake_response=_response("PASS_THROUGH"),
        )
    (tmp_path / "bad").mkdir()
    db, capture_id = _stored(tmp_path / "bad")
    from app.jev import scanner_reviewer_bridge as bridge
    capture, sample = load_canonical_candidate_readonly(
        db, capture_id=capture_id, sample_index=0,
    )
    # The immutable stored row must remain intact; change only a copy of
    # the candidate returned by the test's read adapter.
    broken_sample = {**sample, "snapshot_hash": "bad"}
    before = db.read_bytes()
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            bridge, "load_canonical_candidate_readonly",
            lambda *args, **kwargs: (capture, broken_sample),
        )
        result = inspect_reviewer_candidate_readonly(
            db, capture_id=capture_id, sample_index=0,
        )
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "SNAPSHOT_HASH_MISMATCH"
    assert result["provider_calls"] == 0
    assert db.read_bytes() == before


def test_phase1_bridge_cli_uses_existing_s7_command_without_feature_toggle(tmp_path):
    db, capture_id = _stored(tmp_path)
    args = s7_build_parser().parse_args([
        "reviewer-bridge", "--simulation-db", str(db),
        "--capture-id", capture_id, "--sample-index", "0", "--json",
    ])
    out = s7_execute(args)
    assert out["status"] == "LOCAL_PROJECTION_READY_PROVIDER_HOLD"
    assert out["provider_gate"] == "NO_GO"
    args.sample_index = None
    with pytest.raises(DecisionReviewContractError, match="REVIEWER_BRIDGE_ARGUMENT_CONFLICT"):
        s7_execute(args)


@pytest.mark.parametrize("capture_id,index", [
    ("", 0), ("x", -1), ("x", 500), ("x", True),
])
def test_phase1_malformed_reference_fails_without_model_calls(tmp_path, capture_id, index):
    db, _ = _stored(tmp_path)
    out = inspect_reviewer_candidate_readonly(
        db, capture_id=capture_id, sample_index=index,
    )
    assert out["status"] == "HOLD"
    assert out["reason_code"] == "REVIEWER_BRIDGE_REFERENCE_INVALID"
    assert out["external_requests"] == out["runtime_db_writes"] == 0


def test_phase1_legacy_derived_strategy_is_diagnostic_only_not_reviewable(tmp_path, monkeypatch):
    """Three school-PC candidates have source-only identity; never backfill."""
    from app.jev import scanner_reviewer_bridge as bridge
    from app.strategy.semantic_identity_bridge import ENGINE_VERIFIED_SOURCE

    db, capture_id = _stored(tmp_path)
    capture, sample = load_canonical_candidate_readonly(
        db, capture_id=capture_id, sample_index=0,
    )
    sample = deepcopy(sample)
    source = sample["snapshot"]["semantic_source_v2"]["strategy"]
    sample["snapshot"].pop("strategy_version_id")
    sample["snapshot"].pop("strategy_definition_hash")
    sample["snapshot"]["semantic_policy_provenance"][
        "policy_source"
    ] = "LEGACY_CURRENT_10_FALLBACK"
    sample["snapshot"]["semantic_strategy_identity"] = {
        "source": ENGINE_VERIFIED_SOURCE,
        "strategy_key": STRATEGY,
        "strategy_version_id": source["strategy_version_id"],
        "strategy_definition_hash": source["strategy_definition_hash"],
        "selection_policy_id": "synthetic-policy",
        "selection_policy_hash": "synthetic-policy-hash",
    }
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    original = db.read_bytes()
    monkeypatch.setattr(
        bridge, "load_canonical_candidate_readonly",
        lambda *args, **kwargs: (capture, sample),
    )
    status = inspect_reviewer_candidate_readonly(
        db, capture_id=capture_id, sample_index=0,
    )
    assert status["status"] == "LEGACY_INSPECTION_ONLY"
    assert status["reason_code"] == "LEGACY_DERIVED_IDENTITY"
    assert status["candidate_category"] == "LEGACY_LIMITED"
    assert status["strict_block_reason"] == "STRATEGY_IDENTITY_MISMATCH"
    assert status["semantic_strategy_identity"] == "DERIVED_NOT_ORIGINAL"
    assert status["actual_provider_eligible"] is False
    assert status["fake_only_available"] is False
    assert status["provider_calls"] == status["runtime_db_writes"] == 0
    assert "evidence_items" not in status
    assert db.read_bytes() == original
    with pytest.raises(DecisionReviewContractError, match="STRATEGY_IDENTITY_MISMATCH"):
        inspect_synthetic_fake_review_readonly(
            db, capture_id=capture_id, sample_index=0,
            fake_response=_response("PASS_THROUGH"),
        )

    # A fabricated derived-only identity must never earn LEGACY_LIMITED.
    sample["snapshot"]["semantic_strategy_identity"]["strategy_definition_hash"] = "forged"
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    forged = inspect_reviewer_candidate_readonly(
        db, capture_id=capture_id, sample_index=0,
    )
    assert forged["status"] == "HOLD"
    assert forged["reason_code"] == "STRATEGY_IDENTITY_MISMATCH"
    assert forged["actual_provider_eligible"] is False

    # A tampered immutable sample digest also fails closed.
    sample["snapshot_hash"] = "tampered"
    tampered = inspect_reviewer_candidate_readonly(
        db, capture_id=capture_id, sample_index=0,
    )
    assert tampered["status"] == "HOLD"
    assert tampered["reason_code"] == "SNAPSHOT_HASH_MISMATCH"
