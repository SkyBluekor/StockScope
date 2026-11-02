"""ACT2 Phase-1 Scanner Decision Reviewer bridge, read-only and provider-disabled.

Reuses the frozen Scanner projection/contract instead of reconstructing
conditions, rank, Risk, or future performance. The default path reports
why a *particular canonical candidate* is not ready for real model use.
The optional fake-only path accepts only an explicitly synthetic capture
and a caller-supplied response, never live or proprietary market payloads.

This is NOT a TypeSafe V4 disposition, Q7 approval, AI output, or a basis to
modify Scanner/Strategy/Risk decisions. No credential/network/model/store calls.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.prospective.models import digest_json

from .decision_reviewer_offline import (
    DecisionReviewContractError,
    OfflineFakeShadowSession,
    build_scanner_review_input,
    load_canonical_candidate_readonly,
)
from .scanner_eligibility_s8 import RIGHTS_ACTIONS
from .scanner_integrity_s7_1 import assess_frozen_candidate

VERSION = "JEV_ACT2_PHASE1_REVIEW_BRIDGE_V1"
PROTOCOL = "JEV_ACT2_PHASE1_LOCAL_INSPECTION_V1"


def _base(status: str, reason: str, **fields: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "reason_code": reason,
        "provider_gate": "NO_GO",
        "source_rights": RIGHTS_ACTIONS["KRX_OPEN_API_DERIVED_TYPESAFE_AI"],
        "publication_time_proven": False,
        "approved_trial_protocol": False,
        "actual_provider_eligible": False,
        "provider_calls": 0,
        "external_requests": 0,
        "runtime_db_writes": 0,
        "production_action_modified": False,
        "investment_improvement_verified": False,
        **fields,
    }


def _candidate(
    simulation_db: Path, *, capture_id: str, sample_index: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if (
        type(capture_id) is not str or not 1 <= len(capture_id) <= 128
        or type(sample_index) is not int or not 0 <= sample_index < 500
    ):
        raise DecisionReviewContractError("REVIEWER_BRIDGE_REFERENCE_INVALID")
    capture, sample = load_canonical_candidate_readonly(
        simulation_db, capture_id=capture_id, sample_index=sample_index,
    )
    projected = build_scanner_review_input(
        capture, sample, protocol_id=PROTOCOL,
    )
    return capture, sample, projected


def _verified_legacy_explanation(
    simulation_db: Path, *, capture_id: str, sample_index: int,
) -> dict[str, Any] | None:
    """Describe independently verified derived-only legacy identity, never waive S3.

    A missing source identity alone proves nothing. Reuse the existing S7.1
    complete integrity result, re-check the immutable stored snapshot digest,
    and require the exact strict S3 rejection before labeling legacy-limited.
    """
    try:
        capture, sample = load_canonical_candidate_readonly(
            simulation_db, capture_id=capture_id, sample_index=sample_index,
        )
        snapshot = sample.get("snapshot")
        if (
            capture.get("status") != "COMPLETE"
            or not isinstance(snapshot, dict)
            or not sample.get("snapshot_hash")
            or digest_json(snapshot) != sample["snapshot_hash"]
            or sample.get("capture_run_id") != capture.get("id")
            or sample.get("action") != "ENTRY_CANDIDATE"
            or snapshot.get("action") != "ENTRY_CANDIDATE"
        ):
            return None
        audit = assess_frozen_candidate(capture, sample)
        if (
            audit.get("category") != "LEGACY_LIMITED"
            or audit.get("strategy", {}).get("code") != "LEGACY_DERIVED_IDENTITY"
            or audit.get("strict_s3", {}).get("code") != "STRATEGY_IDENTITY_MISMATCH"
        ):
            return None
        return _base(
            "LEGACY_INSPECTION_ONLY", "LEGACY_DERIVED_IDENTITY",
            strict_block_reason="STRATEGY_IDENTITY_MISMATCH",
            candidate_category="LEGACY_LIMITED",
            original_strategy_identity="MISSING",
            semantic_strategy_identity="DERIVED_NOT_ORIGINAL",
            canonical_capture_id=capture["id"],
            sample_index=sample["sample_index"],
            snapshot_hash=sample["snapshot_hash"],
            baseline_action=sample["action"],
            baseline_rank=sample["rank"],
            fake_only_available=False,
        )
    except (DecisionReviewContractError, KeyError, TypeError, ValueError):
        return None


def inspect_reviewer_candidate_readonly(
    simulation_db: Path, *, capture_id: str, sample_index: int,
) -> dict[str, Any]:
    """Evidence-only preflight for a real or synthetic frozen Scanner candidate.

    Does not construct/export an outbound AI packet, and never exposes raw
    conditions, prompt text, entry prices, credentials, or source data.
    """
    try:
        capture, sample, projected = _candidate(
            simulation_db, capture_id=capture_id, sample_index=sample_index,
        )
    except DecisionReviewContractError as exc:
        if exc.code == "STRATEGY_IDENTITY_MISMATCH":
            legacy = _verified_legacy_explanation(
                simulation_db, capture_id=capture_id, sample_index=sample_index,
            )
            if legacy is not None:
                return legacy
        return _base("HOLD", exc.code)
    review_input = projected["input"]
    return _base(
        "LOCAL_PROJECTION_READY_PROVIDER_HOLD"
        if projected["status"] == "OFFLINE_INSPECTABLE_ONLY"
        else "LEGACY_INSPECTION_ONLY",
        "SOURCE_RIGHTS_TIME_AND_TRIAL_APPROVAL_UNVERIFIED"
        if projected["status"] == "OFFLINE_INSPECTABLE_ONLY"
        else "LEGACY_HORIZON_CANNOT_BE_BACKFILLED",
        canonical_capture_id=capture["id"],
        sample_index=sample["sample_index"],
        snapshot_hash=sample["snapshot_hash"],
        request_id=review_input["request_id"],
        input_hash=projected["input_hash"],
        input_contract=review_input["schema_version"],
        output_contract="JEV_SCANNER_REVIEW_OUTPUT_V1",
        baseline_action=review_input["baseline_decision"]["action"],
        baseline_rank=review_input["baseline_decision"]["rank"],
        baseline_risk=review_input["baseline_decision"]["risk"]["status"],
        horizon_intent=review_input["baseline_identity"]["horizon_intent"],
        evidence_item_count=len(review_input["evidence_items"]),
        source_time_proof=review_input["as_of"]["time_proof"],
        fake_only_available=(
            capture.get("capture_version") == "SYNTHETIC_ONLY"
            and capture.get("source_execution_key") == "synthetic-execution"
            and projected["status"] == "OFFLINE_INSPECTABLE_ONLY"
        ),
    )


def inspect_synthetic_fake_review_readonly(
    simulation_db: Path, *, capture_id: str, sample_index: int,
    fake_response: dict[str, Any],
    session: OfflineFakeShadowSession | None = None,
) -> dict[str, Any]:
    """Exercise the *existing* Phase-1 reviewer contract with fixture-only data.

    This is a caller-provided mock decision, not a model-produced opinion.
    Synthetic CAPTURE markers are only a test boundary; they cannot grant
    transmission rights. Real captures and legacy Horizons are always blocked.
    """
    capture, _, projected = _candidate(
        simulation_db, capture_id=capture_id, sample_index=sample_index,
    )
    if (
        capture.get("capture_version") != "SYNTHETIC_ONLY"
        or capture.get("source_execution_key") != "synthetic-execution"
    ):
        raise DecisionReviewContractError("REAL_CAPTURE_FAKE_REVIEW_FORBIDDEN")
    if projected["status"] != "OFFLINE_INSPECTABLE_ONLY":
        raise DecisionReviewContractError("HORIZON_NOT_FAKE_TEST_SCOPE")
    if not isinstance(fake_response, dict):
        raise DecisionReviewContractError("FAKE_RESPONSE_INVALID")
    journal = session if session is not None else OfflineFakeShadowSession()
    record = journal.inspect(projected, fake_response, provider_id="FAKE")
    return _base(
        "SYNTHETIC_FAKE_REVIEW_ONLY", "NOT_AN_ACTUAL_AI_MODEL_OUTPUT",
        canonical_capture_id=capture["id"],
        sample_index=sample_index,
        review_identity=record["review_identity"],
        input_hash=record["input_hash"],
        reused=record["reused"],
        validation_status=record["status"],
        fake_decision=record["decision"],
        fake_shadow_action=record["shadow_action"],
        failure_code=record["failure_code"],
        outcome_status=record["outcome_status"],
        outcome_return=None,
    )
