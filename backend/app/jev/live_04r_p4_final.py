"""P4 FINAL: local-only review of already-frozen SHORT Scanner captures.

Discovery is metadata-only; inspection is by *explicit* capture ID. Both are
read-only SQLite operations. Never executes Scanner, mutates a snapshot,
constructs a provider, or authorizes model transmission / numeric Horizons.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.horizon import HorizonPolicyError, resolve_horizon_context
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_shadow_s7 import _connect_readonly, load_frozen_candidates
from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
from app.jev.scanner_v4_readiness_s7_5 import diagnose_candidate as diagnose_v4
from app.jev.scanner_eligibility_s8 import diagnose_candidate as diagnose_s8
from app.strategy.semantic_source_v2 import verify_semantic_source_v2

VERSION = "JEV_LIVE_04R_P4_FROZEN_SHORT_V1"


def _request(row: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(row.get("request_json") or "{}")
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _capture_header(conn: sqlite3.Connection, capture_id: str) -> dict[str, Any]:
    try:
        row = conn.execute(
            "SELECT id,status,canonical_capture_id,source_job_id,created_at,"
            "completed_at,horizon_intent,horizon_policy_version,request_json "
            "FROM prospective_capture_run WHERE id=?", (capture_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise DecisionReviewContractError("P4_CAPTURE_SCHEMA_NOT_READY") from exc
    if row is None or row["status"] not in ("COMPLETE", "DUPLICATE"):
        raise DecisionReviewContractError("P4_CAPTURE_NOT_COMPLETE")
    return dict(row)


def find_stored_horizon_captures(
    simulation_db: Path, *, horizon_intent: str = "SHORT", limit: int = 10,
) -> dict[str, Any]:
    """List candidate capture IDs only; deliberately *no auto-selection*."""
    if horizon_intent not in ("SHORT", "MEDIUM"):
        raise ValueError("P4_UNSUPPORTED_DISCOVERY_HORIZON")
    if type(limit) is not int or not 1 <= limit <= 25:
        raise ValueError("P4_DISCOVERY_LIMIT_INVALID")
    try:
        with _connect_readonly(simulation_db) as conn:
            rows = conn.execute(
                "SELECT r.id,r.status,r.canonical_capture_id,r.source_job_id,"
                "r.created_at,r.horizon_intent,r.request_json,"
                "COUNT(s.sample_index) AS stored_samples,"
                "SUM(CASE WHEN s.action='ENTRY_CANDIDATE' THEN 1 ELSE 0 END) AS entries "
                "FROM prospective_capture_run r "
                "LEFT JOIN prospective_recommendation_sample s ON s.capture_run_id=r.id "
                "WHERE r.horizon_intent=? AND r.status IN ('COMPLETE','DUPLICATE') "
                "GROUP BY r.id ORDER BY r.created_at DESC,r.id DESC LIMIT ?",
                (horizon_intent, limit),
            ).fetchall()
    except sqlite3.Error as exc:
        raise DecisionReviewContractError("P4_CAPTURE_DISCOVERY_SCHEMA_NOT_READY") from exc
    captures = []
    for row in rows:
        request = _request(dict(row))
        captures.append({
            "capture_id": row["id"],
            "status": row["status"],
            "canonical_capture_id": row["canonical_capture_id"] or row["id"],
            "source_job_id": row["source_job_id"],
            "created_at": row["created_at"],
            "horizon_intent": row["horizon_intent"],
            "horizon_purpose": request.get("horizon_purpose", "UNRECORDED"),
            # DUPLICATE samples exist ONLY in the referenced canonical record.
            "stored_samples_on_this_row": int(row["stored_samples"] or 0),
            "entry_samples_on_this_row": int(row["entries"] or 0),
        })
    return {
        "version": VERSION,
        "read_only": True,
        "status": "FOUND" if captures else "NO_STORED_HORIZON_CAPTURE",
        "captures": captures,
        "selection_required": True,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def inspect_stored_horizon_capture(
    simulation_db: Path, *, capture_id: str, sample_index: int | None = None,
) -> dict[str, Any]:
    """Diagnose existing canonical evidence; not a fresh-run certification."""
    if not isinstance(capture_id, str) or not 0 < len(capture_id) <= 200:
        raise ValueError("P4_CAPTURE_ID_REQUIRED")
    if sample_index is not None and (
        type(sample_index) is not int or not 0 <= sample_index <= 499
    ):
        raise ValueError("P4_SAMPLE_INDEX_INVALID")
    with _connect_readonly(simulation_db) as conn:
        requested = _capture_header(conn, capture_id)
        canonical_id = (
            requested["canonical_capture_id"]
            if requested["status"] == "DUPLICATE" else capture_id
        )
        if not canonical_id:
            raise DecisionReviewContractError("P4_CANONICAL_CAPTURE_MISSING")
        canonical = _capture_header(conn, canonical_id)
        if canonical["status"] != "COMPLETE":
            raise DecisionReviewContractError("P4_CANONICAL_CAPTURE_NOT_COMPLETE")

    requested_contract = _request(requested)
    canonical_contract = _request(canonical)
    horizon = canonical.get("horizon_intent")
    if horizon not in ("SHORT", "MEDIUM"):
        raise ValueError("P4_CAPTURE_HORIZON_NOT_V4_SUPPORTED")
    # Do not silently treat a duplicate whose pinned horizon differs from its
    # source as the same review context.
    same_horizon = (
        requested.get("horizon_intent") == horizon
        and requested.get("horizon_policy_version") == canonical.get("horizon_policy_version")
        and requested_contract.get("horizon_purpose") == canonical_contract.get("horizon_purpose")
    )
    try:
        context = resolve_horizon_context(
            horizon, policy_version=canonical.get("horizon_policy_version"),
        )
        horizon_status, horizon_reason = context.support_status, context.reason_code
    except HorizonPolicyError as exc:
        context = None
        horizon_status, horizon_reason = "UNSUPPORTED", exc.code

    pairs = load_frozen_candidates(
        Path(simulation_db), capture_id=canonical_id, limit=500,
    )
    if sample_index is None:
        matches = [
            (capture, sample) for capture, sample in pairs
            if sample["action"] == "ENTRY_CANDIDATE"
        ]
        if not matches:
            raise ValueError("P4_NO_ENTRY_CANDIDATE")
        capture, sample = min(
            matches,
            key=lambda pair: (
                int(pair[1].get("rank") or 999999),
                int(pair[1]["sample_index"]),
            ),
        )
    else:
        matches = [
            (capture, sample) for capture, sample in pairs
            if sample["sample_index"] == sample_index
        ]
        if not matches:
            raise ValueError("P4_SAMPLE_NOT_FOUND")
        capture, sample = matches[0]
    integrity = assess_frozen_candidate(capture, sample)
    v4 = diagnose_v4(capture, sample)
    s8 = diagnose_s8(capture, sample)
    original = sample["snapshot"]
    v2_valid, v2_reason = verify_semantic_source_v2(original.get("semantic_source_v2"))
    checks = {
        name: {
            "status": integrity[name]["status"],
            "reason_code": integrity[name]["code"],
        }
        for name in ("rank", "policy", "strategy", "engine", "dates", "risk")
    }
    strategy_status = checks["strategy"]["status"]
    v4_status = v4["local_v4_status"]
    # Authority is deliberately *never* inferred from structure or from the
    # S7.5 internal route/provider_eligible flag.
    local_horizon_usable = (
        horizon in ("SHORT", "MEDIUM")
        and context is not None
        and canonical.get("horizon_policy_version") == context.policy_version
    )
    source_contract_matches = (
        canonical_contract.get("horizon_intent") == horizon
        and canonical_contract.get("horizon_policy_version") == canonical.get("horizon_policy_version")
    )
    if not same_horizon or not source_contract_matches:
        local_horizon_usable = False
    if not local_horizon_usable:
        local_result = "BLOCKED_CAPTURE_CONTEXT"
    elif not v2_valid and v4_status == "LOCAL_V4_PROJECTABLE":
        # Fail closed if separate source integrity disagrees with projection.
        local_result = "BLOCKED_SEMANTIC_SOURCE"
    else:
        local_result = v4_status
    local_reason = sorted(set(v4["reason_codes"]))
    if not same_horizon:
        local_reason.append("P4_CAPTURE_HORIZON_PURPOSE_DRIFT")
    if not source_contract_matches:
        local_reason.append("P4_FROZEN_REQUEST_HORIZON_MISMATCH")
    if not v2_valid:
        local_reason.append(v2_reason or "P4_SEMANTIC_V2_NOT_VERIFIED")
    return {
        "version": VERSION,
        "read_only": True,
        "selection": {
            "requested_capture_id": capture_id,
            "requested_capture_status": requested["status"],
            "canonical_capture_id": canonical_id,
            "source_job_id": requested["source_job_id"],
            "canonical_source_job_id": canonical["source_job_id"],
            "reused_canonical": requested["status"] == "DUPLICATE",
            "fresh_scan_independently_verified": False,
        },
        "candidate": {
            "sample_index": sample["sample_index"],
            "ticker": sample["ticker"],
            "market": sample["market"],
            "signal_date": sample["signal_date"],
            "rank": sample["rank"],
            "action": sample["action"],
            "snapshot_hash": sample["snapshot_hash"],
            "snapshot_hash_verified_by_loader": True,
        },
        "frozen_contract": {
            "horizon_intent": horizon,
            "horizon_purpose": canonical_contract.get("horizon_purpose", "UNRECORDED"),
            "horizon_policy_version": canonical.get("horizon_policy_version"),
            "request_horizon_matches_canonical": source_contract_matches,
            "requested_canonical_context_match": same_horizon,
            "selection_policy_id": canonical_contract.get("selection_policy_id"),
            "selection_policy_hash": canonical_contract.get("selection_policy_hash"),
            "semantic_source_v2_valid": v2_valid,
            "semantic_source_v2_reason": v2_reason,
        },
        "checks": checks,
        "local_v4": {
            "status": local_result,
            "source_v4_status": v4_status,
            "semantic_status": v4["v4_local_semantic_status"],
            "state_hash": v4["v4_state_hash"] if local_result == "LOCAL_V4_PROJECTABLE" else None,
            "lineage_status": v4["lineage_analysis_status"],
            "reason_codes": sorted(set(local_reason)),
        },
        "strategy_identity": {
            "status": strategy_status,
            "original_strategy_version_recorded": bool(original.get("strategy_version_id")),
            "original_strategy_definition_hash_recorded": bool(original.get("strategy_definition_hash")),
            "verified_original": strategy_status == "PASS" and checks["policy"]["status"] == "PASS",
            "legacy_derived_is_not_original": strategy_status == "LEGACY_DERIVED",
        },
        "horizon_execution": {
            "support_status": horizon_status,
            "reason_code": horizon_reason,
            "numeric_policy_approved": horizon_status == "SUPPORTED",
            "local_review_does_not_activate_policy": True,
        },
        "provider_authorization": {
            "decision": "HOLD",
            "source_rights_status": s8["rights_status"],
            "source_publication_status": s8["publication_time_status"],
            "source_revision_status": s8["source_revision_status"],
            "type_safe_account_approved": False,
            "actual_provider_calls": 0,
            "db_writes": 0,
        },
    }
