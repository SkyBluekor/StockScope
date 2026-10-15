"""Read-only proof of an entire frozen Scanner->Prospective capture for JEV Phase 1.

This is a diagnostic receipt, not JEV activation or an external model request.
Only original immutable rows qualify; never synthesize missing rank/identity
or treat legacy-derived semantic identities as production strategy identity.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Any

from app.prospective.models import digest_json
from app.strategy.production_selection_policy import DEFAULT_RUNTIME_DIR

from .local_readiness_s13 import _current_policy_state

from .decision_reviewer_offline import (
    DecisionReviewContractError, load_canonical_candidate_readonly,
)
from .scanner_integrity_s7_1 import assess_frozen_candidate
from .scanner_reviewer_bridge import inspect_reviewer_candidate_readonly

VERSION = "JEV_ACT2_PHASE1_CAPTURE_PROOF_V1"
MAX_SAMPLES = 500


def _report(status: str, reason_code: str, **details: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "reason_code": reason_code,
        "provider_gate": "NO_GO",
        "provider_calls": 0,
        "external_requests": 0,
        "runtime_db_writes": 0,
        "production_action_modified": False,
        "investment_improvement_verified": False,
        "actual_provider_eligible": False,
        **details,
    }


def inspect_capture_proof_readonly(
    simulation_db: Path, *, capture_id: str, max_samples: int = 60,
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    """Audit all original entry candidates and reference-row hashes; no DB writes.

    The max_samples bound is a fail-closed completeness limit, not a silent
    pagination of the scored cohort. Both canonical and duplicate IDs work.
    """
    if type(capture_id) is not str or not 1 <= len(capture_id) <= 128:
        return _report("HOLD", "CAPTURE_REFERENCE_INVALID")
    if type(max_samples) is not int or not 1 <= max_samples <= MAX_SAMPLES:
        return _report("HOLD", "CAPTURE_AUDIT_LIMIT_INVALID")
    db = Path(simulation_db)
    if not db.is_file():
        return _report("HOLD", "LOCAL_SIMULATION_DB_NOT_FOUND")
    try:
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            selected = conn.execute(
                "SELECT id,status,canonical_capture_id "
                "FROM prospective_capture_run WHERE id=?", (capture_id,),
            ).fetchone()
            if selected is None:
                return _report("HOLD", "CAPTURE_NOT_FOUND")
            if selected["status"] not in ("COMPLETE", "DUPLICATE"):
                return _report("HOLD", "CAPTURE_NOT_COMPLETE")
            canonical_id = (
                selected["canonical_capture_id"]
                if selected["status"] == "DUPLICATE" else selected["id"]
            )
            if not canonical_id:
                return _report("HOLD", "CANONICAL_CAPTURE_ID_MISSING")
            capture = conn.execute(
                "SELECT id,status,returned_candidate_count "
                "FROM prospective_capture_run WHERE id=?", (canonical_id,),
            ).fetchone()
            if capture is None or capture["status"] != "COMPLETE":
                return _report("HOLD", "CANONICAL_CAPTURE_NOT_COMPLETE")
            rows = conn.execute(
                "SELECT sample_index,action,rank,snapshot_json,snapshot_hash "
                "FROM prospective_recommendation_sample WHERE capture_run_id=? "
                "ORDER BY sample_index LIMIT ?",
                (canonical_id, max_samples + 1),
            ).fetchall()
            expected = capture["returned_candidate_count"]
            if type(expected) is not int or expected < 0:
                return _report("HOLD", "CAPTURE_EXPECTED_COUNT_INVALID")
            if expected > max_samples or len(rows) > max_samples:
                return _report(
                    "HOLD", "CAPTURE_SAMPLE_LIMIT_EXCEEDED",
                    canonical_capture_id=canonical_id,
                    expected_samples=expected, max_samples=max_samples,
                )
            if len(rows) != expected:
                return _report(
                    "HOLD", "CAPTURE_SAMPLE_COUNT_MISMATCH",
                    canonical_capture_id=canonical_id,
                    expected_samples=expected, observed_samples=len(rows),
                )
            # Check even non-entry snapshots: corrupt references cannot make
            # an entire frozen capture appear independently complete.
            for i, row in enumerate(rows):
                if type(row["sample_index"]) is not int or row["sample_index"] != i:
                    return _report("HOLD", "CAPTURE_SAMPLE_INDEX_GAP")
                try:
                    snapshot = json.loads(row["snapshot_json"])
                except (ValueError, TypeError):
                    return _report("HOLD", "CAPTURE_SNAPSHOT_INVALID")
                if not isinstance(snapshot, dict):
                    return _report("HOLD", "CAPTURE_SNAPSHOT_INVALID")
                if (not row["snapshot_hash"]
                        or digest_json(snapshot) != row["snapshot_hash"]):
                    return _report("HOLD", "CAPTURE_SNAPSHOT_HASH_MISMATCH")
                if snapshot.get("action") != row["action"]:
                    return _report("HOLD", "CAPTURE_ACTION_MISMATCH")
            references = sum(row["action"] != "ENTRY_CANDIDATE" for row in rows)
            entries = [row for row in rows if row["action"] == "ENTRY_CANDIDATE"]
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return _report("HOLD", "CAPTURE_AUDIT_READ_UNAVAILABLE")

    # Scanner and Prospective are immutable at this boundary. Reuse the exact
    # S3 contract and S7.1 integrity verdict rather than a new relaxed gate.
    records: list[dict[str, Any]] = []
    for row in entries:
        index = row["sample_index"]
        result = inspect_reviewer_candidate_readonly(
            db, capture_id=canonical_id, sample_index=index,
        )
        item = {
            "sample_index": index,
            "status": result["status"],
            "reason_code": result["reason_code"],
            "candidate_category": result.get("candidate_category"),
        }
        if "strict_block_reason" in result:
            item["strict_block_reason"] = result["strict_block_reason"]
        if result["reason_code"] == "BASELINE_RANK_MISMATCH":
            try:
                c, s = load_canonical_candidate_readonly(
                    db, capture_id=canonical_id, sample_index=index,
                )
                item["rank_diagnostic"] = assess_frozen_candidate(c, s)[
                    "rank"
                ]["code"]
            except (DecisionReviewContractError, KeyError, TypeError, ValueError):
                item["rank_diagnostic"] = "RANK_DIAGNOSTIC_UNAVAILABLE"
        records.append(item)

    counts = Counter(record["status"] for record in records)
    ready = counts["LOCAL_PROJECTION_READY_PROVIDER_HOLD"]
    legacy = counts["LEGACY_INSPECTION_ONLY"]
    hold = len(records) - ready - legacy
    if not records:
        status, reason = "NO_ENTRY_CANDIDATES", "REFERENCE_CAPTURE_ONLY"
    elif ready == len(records):
        status, reason = (
            "CAPTURE_INPUT_READY_PROVIDER_HOLD",
            "ALL_ORIGINAL_ENTRY_PROOFS_VALID_EXTERNAL_MODEL_BLOCKED",
        )
    elif legacy == len(records):
        status, reason = "CAPTURE_LEGACY_LIMITED", "ORIGINAL_STRATEGY_IDENTITY_MISSING"
    else:
        status, reason = "CAPTURE_NOT_READY", "ORIGINAL_ENTRY_PROOFS_INCOMPLETE"
    # Current policy resolution is an observation at inspection time, NOT
    # proof that the policy existed when the frozen capture was produced.
    # Reuse the same Q7 gate and baseline-aware pin resolver as S13; never
    # reinterpret the original strategy IDs or use a test-only activation as
    # production/Q7 approval.
    gate = _current_policy_state(
        db.resolve(), Path(runtime_dir or DEFAULT_RUNTIME_DIR),
    )
    return _report(
        status, reason,
        current_policy_gate={
            **gate,
            "observed_at_inspection_not_capture": True,
            "cannot_upgrade_frozen_capture": True,
            "jev_trial_approved": False,
            "model_data_transmission_approved": False,
        },
        requested_capture_id=capture_id,
        canonical_capture_id=canonical_id,
        duplicate_resolved=(canonical_id != capture_id),
        expected_samples=expected,
        inspected_samples=len(rows),
        entry_candidates=len(entries),
        reference_candidates=references,
        contract_ready=ready,
        legacy_limited=legacy,
        blocked=hold,
        records=records,
    )
