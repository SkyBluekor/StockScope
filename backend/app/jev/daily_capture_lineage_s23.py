"""S23: local, read-only final receipt for a scheduled Scanner Capture.

The prospective Scanner job may create a COMPLETE capture, but completeness of
rows does not establish original identity, Q7 approval or publication time.
Treat verification failures as HOLD: never rewrite old captures or promote
legacy semantic/engine-derived strategy identities.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3
from typing import Any

from .q7_diagnosis_s18 import classify_capture_timing
from .scanner_capture_proof import inspect_capture_proof_readonly

VERSION = "S23_DAILY_CAPTURE_LINEAGE_RECEIPT_V1"


def _receipt(status: str, reason_code: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "reason_code": reason_code,
        "strict_jev_input_ready": False,
        "q7_approval_eligible": False,
        "q7_research_study_bound": False,
        "verified_provider_publication_timestamp": False,
        "independent_timestamp_attestation": False,
        "trusted_prospective_prediction_proven": False,
        "model_uplift_verified": False,
        "external_ai_calls": 0,
        "runtime_db_writes": 0,
        "scanner_runs": 0,
        "production_decision_modified": False,
        **extra,
    }


def audit_daily_capture_readonly(
    simulation_db: Path, *, capture_id: str,
    expected_source_date: str, runtime_dir: Path | None = None,
) -> dict[str, Any]:
    """Return a compact lineage receipt from the exact immutable source capture.

    All values are interpreted at inspection time. Even SOURCE_CONTRACT_READY
    means only local JEV input checks passed: never a Q7/AI/trading approval.
    """
    if type(capture_id) is not str or not 1 <= len(capture_id) <= 128:
        return _receipt("HOLD", "CAPTURE_ID_INVALID")
    if type(expected_source_date) is not str:
        return _receipt("HOLD", "EXPECTED_SOURCE_DATE_INVALID")
    try:
        if date.fromisoformat(expected_source_date).isoformat() != expected_source_date:
            raise ValueError
    except ValueError:
        return _receipt("HOLD", "EXPECTED_SOURCE_DATE_INVALID")

    db = Path(simulation_db)
    if not db.is_file():
        return _receipt("HOLD", "SIMULATION_DB_NOT_FOUND")
    try:
        proof = inspect_capture_proof_readonly(
            db, capture_id=capture_id, max_samples=500,
            runtime_dir=runtime_dir,
        )
        canonical_id = proof.get("canonical_capture_id")
        if proof["status"] == "HOLD" or not canonical_id:
            return _receipt(
                "HOLD", str(proof.get("reason_code") or "CAPTURE_PROOF_UNAVAILABLE"),
                original_capture_proof_status=proof.get("status"),
            )
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            row = conn.execute(
                "SELECT status,completed_at,actual_data_date,requested_as_of "
                "FROM prospective_capture_run WHERE id=?", (canonical_id,),
            ).fetchone()
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError):
        return _receipt("HOLD", "CAPTURE_LINEAGE_READ_UNAVAILABLE")

    if row is None or row["status"] != "COMPLETE":
        return _receipt("HOLD", "CANONICAL_CAPTURE_NOT_COMPLETE")
    actual_source = row["actual_data_date"]
    # The Scanner result requested date and the stored actual EOD may differ.
    # Do not certify a dated prediction from a mismatched source.
    if actual_source != expected_source_date or row["requested_as_of"] != expected_source_date:
        return _receipt(
            "HOLD", "SOURCE_DATE_OR_REQUEST_MISMATCH",
            original_capture_proof_status=proof["status"],
        )

    timing = classify_capture_timing(row["completed_at"], actual_source)
    contract_ready = proof["status"] == "CAPTURE_INPUT_READY_PROVIDER_HOLD"
    status = (
        "SOURCE_CONTRACT_READY_Q7_HOLD" if contract_ready
        else "LEGACY_ORIGINAL_IDENTITY_MISSING"
        if proof["status"] == "CAPTURE_LEGACY_LIMITED"
        else "REFERENCE_CAPTURE_ONLY"
        if proof["status"] == "NO_ENTRY_CANDIDATES"
        else "CAPTURE_EVIDENCE_INCOMPLETE"
    )
    gate = proof.get("current_policy_gate")
    return _receipt(
        status,
        str(proof.get("reason_code") or "CAPTURE_PROOF_UNAVAILABLE"),
        strict_jev_input_ready=contract_ready,
        canonical_capture_id=canonical_id,
        duplicate_resolved=bool(proof.get("duplicate_resolved")),
        original_capture_proof_status=proof["status"],
        expected_samples=proof.get("expected_samples"),
        entry_candidates=proof.get("entry_candidates"),
        contract_ready_candidates=proof.get("contract_ready"),
        legacy_limited_candidates=proof.get("legacy_limited"),
        contract_blocked_candidates=proof.get("blocked"),
        original_source_date_matches_requested=True,
        completion_calendar_classification=timing,
        completion_clock_is_not_source_publication_time=True,
        current_policy_source_at_inspection=(
            gate.get("selection_policy_source")
            if isinstance(gate, dict) else None
        ),
        current_policy_is_not_capture_time_authority=True,
    )
