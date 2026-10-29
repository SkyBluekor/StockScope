"""LIVE-04R-P3: one real *frozen* Scanner capture, local-only evidence audit.

No Scanner execution, market provider, TypeSafe transport, credential loading,
database migration or file writes. Uses the same immutable read-only Scanner
and V4 diagnostics as the user-facing API. Never grants outbound permission.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from app.horizon import HorizonPolicyError, resolve_horizon_context
from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
from app.jev.scanner_shadow_s7 import _connect_readonly, load_frozen_candidates
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_v4_readiness_s7_5 import diagnose_candidate as diagnose_v4
from app.jev.scanner_eligibility_s8 import diagnose_candidate as diagnose_s8
from app.strategy.semantic_source_v2 import verify_semantic_source_v2


def _utc_timestamp(raw: str | None) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def discover_new_capture_ids(
    simulation_db: Path, *, captured_after: str, limit: int = 10,
) -> list[dict[str, str]]:
    """List metadata for new COMPLETE captures, never automatically choose one.

    Explicitly supply an id to the separate inspector. No market rows, raw
    payloads, account keys or timestamps from external sources are exported.
    """
    after = _utc_timestamp(captured_after)
    if after is None:
        raise ValueError("P3_CAPTURED_AFTER_REQUIRES_TIMEZONE")
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("P3_DISCOVERY_LIMIT_INVALID")
    try:
        with _connect_readonly(simulation_db) as conn:
            rows = conn.execute(
                "SELECT r.id, r.source_job_id, r.created_at "
                "FROM prospective_capture_run r "
                "WHERE r.status='COMPLETE' AND EXISTS ("
                "SELECT 1 FROM prospective_recommendation_sample s "
                "WHERE s.capture_run_id=r.id AND s.action='ENTRY_CANDIDATE') "
                "ORDER BY r.created_at DESC LIMIT 100"
            ).fetchall()
    except sqlite3.Error as exc:
        raise DecisionReviewContractError("P3_CAPTURE_DISCOVERY_SCHEMA_UNAVAILABLE") from exc
    output = []
    for row in rows:
        created = _utc_timestamp(row["created_at"])
        if created is None or created < after:
            continue
        output.append({
            "capture_id": row["id"],
            "created_at": row["created_at"],
            "source_job_id": row["source_job_id"],
        })
        if len(output) == limit:
            break
    return output


def _first_blocker(
    *, fresh: bool, sample: dict[str, Any], checks: dict[str, Any],
    v2_ok: bool, v2_reason: str | None, v4: dict[str, Any],
    horizon_status: str, horizon_code: str | None,
) -> dict[str, str] | None:
    """Return the earliest *actual* recorded gap, never a guessed fix."""
    if not fresh:
        return {"stage": "FRESH_CAPTURE", "code": "P3_NEW_CAPTURE_TIME_NOT_VERIFIED"}
    if sample.get("action") != "ENTRY_CANDIDATE":
        return {"stage": "CANDIDATE_ACTION", "code": "NOT_ENTRY_CANDIDATE"}
    for stage in ("rank", "policy", "strategy", "engine", "dates", "risk"):
        item = checks[stage]
        if item["status"] != "PASS":
            return {
                "stage": stage.upper(),
                "code": str(item.get("code") or f"P3_{stage.upper()}_NOT_VERIFIED"),
            }
    if not v2_ok:
        return {"stage": "SEMANTIC_SOURCE_V2", "code": v2_reason or "V2_NOT_VERIFIED"}
    if v4["local_v4_status"] != "LOCAL_V4_PROJECTABLE":
        return {
            "stage": "LOCAL_V4",
            "code": str(v4["local_v4_status"]),
        }
    if horizon_status != "SUPPORTED":
        return {
            "stage": "HORIZON_POLICY",
            "code": horizon_code or "HORIZON_POLICY_NOT_APPROVED",
        }
    return None


def inspect_one_capture(
    simulation_db: Path,
    *,
    capture_id: str,
    captured_after: str,
    sample_index: int | None = None,
) -> dict[str, Any]:
    """Inspect only one explicitly named COMPLETE canonical capture.

    `captured_after` must be timezone-aware and recorded BEFORE starting the
    *new* Scanner run. It prevents stale historical captures from being called
    fresh. Even a matching timestamp does not independently prove scan origin.
    """
    reference = _utc_timestamp(captured_after)
    if reference is None:
        raise ValueError("P3_CAPTURED_AFTER_REQUIRES_TIMEZONE")
    if not capture_id or len(capture_id) > 200:
        raise ValueError("P3_CAPTURE_ID_REQUIRED")
    if sample_index is not None and (
        type(sample_index) is not int or not 0 <= sample_index <= 499
    ):
        raise ValueError("P3_SAMPLE_INDEX_INVALID")
    pairs = load_frozen_candidates(
        Path(simulation_db), capture_id=capture_id, limit=500,
    )
    if sample_index is None:
        entries = [
            (cap, sample) for cap, sample in pairs
            if sample["action"] == "ENTRY_CANDIDATE"
        ]
        if not entries:
            raise ValueError("P3_NO_ENTRY_CANDIDATE")
        capture, sample = min(
            entries,
            key=lambda pair: (int(pair[1]["rank"] or 9999), pair[1]["sample_index"]),
        )
    else:
        matches = [
            (cap, sample) for cap, sample in pairs
            if sample["sample_index"] == sample_index
        ]
        if not matches:
            raise ValueError("P3_SAMPLE_NOT_FOUND")
        capture, sample = matches[0]

    created = _utc_timestamp(capture.get("created_at"))
    # A completed-at timestamp cannot substitute for *begin* time.
    fresh = created is not None and created >= reference
    integrity = assess_frozen_candidate(capture, sample)
    v4 = diagnose_v4(capture, sample)
    s8 = diagnose_s8(capture, sample)
    snapshot = sample["snapshot"]
    v2 = snapshot.get("semantic_source_v2")
    v2_ok, v2_reason = verify_semantic_source_v2(v2)

    request = capture.get("request")
    if not isinstance(request, dict):
        import json
        try:
            request = json.loads(capture.get("request_json") or "{}")
        except (TypeError, ValueError):
            request = {}
    if not isinstance(request, dict):
        request = {}
    try:
        horizon = resolve_horizon_context(
            capture.get("horizon_intent"),
            policy_version=capture.get("horizon_policy_version"),
        )
        horizon_status = horizon.support_status
        horizon_reason = horizon.reason_code
    except HorizonPolicyError as exc:
        horizon_status, horizon_reason = "UNSUPPORTED", exc.code

    provenance = snapshot.get("semantic_policy_provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    engine_evidence = snapshot.get("semantic_condition_evidence")
    if not isinstance(engine_evidence, dict):
        engine_evidence = {}
    evidence_items = engine_evidence.get("items")
    evidence_count = len(evidence_items) if isinstance(evidence_items, list) else 0
    check_names = ("rank", "policy", "strategy", "engine", "dates", "risk")
    checks = {
        name: {
            "status": integrity[name]["status"],
            "reason_code": integrity[name].get("code"),
        }
        for name in check_names
    }
    first = _first_blocker(
        fresh=fresh, sample=sample, checks=checks, v2_ok=v2_ok,
        v2_reason=v2_reason, v4=v4, horizon_status=horizon_status,
        horizon_code=horizon_reason,
    )
    return {
        "version": "JEV_LIVE_04R_P3_ONE_CAPTURE_V1",
        "read_only": True,
        "source_kind": "NOT_INDEPENDENTLY_ATTESTED",
        "capture": {
            "requested_capture_id": capture_id,
            "canonical_capture_id": capture["id"],
            "source_job_id": capture.get("source_job_id"),
            "status": capture["status"],
            "created_at": capture.get("created_at"),
            "completed_at": capture.get("completed_at"),
            "freshness_after": captured_after,
            "freshness_time_consistent": fresh,
            "fresh_scanner_audit_independently_verified": False,
        },
        "candidate": {
            "sample_index": sample["sample_index"],
            "ticker": sample["ticker"],
            "market": sample["market"],
            "signal_date": sample["signal_date"],
            "rank": sample["rank"],
            "action": sample["action"],
            "snapshot_hash": sample["snapshot_hash"],
        },
        "evidence": {
            "selection_policy_id": request.get("selection_policy_id"),
            "selection_policy_hash": request.get("selection_policy_hash"),
            "policy_binding_status": integrity["policy"]["status"],
            "recorded_policy_provenance": provenance.get("status", "UNVERIFIED"),
            "original_strategy_version_recorded": bool(snapshot.get("strategy_version_id")),
            "original_strategy_hash_recorded": bool(snapshot.get("strategy_definition_hash")),
            "strategy_integrity_status": integrity["strategy"]["status"],
            "engine_audit_status": integrity["engine"]["status"],
            "engine_passed_condition_count": evidence_count,
            "source_v2_hash_valid": v2_ok,
            "source_v2_hash_reason": v2_reason,
            "horizon_intent": capture.get("horizon_intent"),
            "horizon_policy_version": capture.get("horizon_policy_version"),
            "horizon_support": horizon_status,
            "horizon_reason": horizon_reason,
            "source_publication_time_verified": False,
        },
        "checks": checks,
        "v4": {
            "local_status": v4["local_v4_status"],
            "semantic_status": v4["v4_local_semantic_status"],
            "local_state_hash": v4["v4_state_hash"],
            "lineage_status": v4["lineage_analysis_status"],
        },
        "first_blocker": first,
        "horizon_execution_blocked": horizon_status != "SUPPORTED",
        "outbound": {
            "decision": "HOLD",
            "source_rights_status": s8["rights_status"],
            "source_time_status": s8["publication_time_status"],
            "actual_provider_calls": 0,
            "db_writes": 0,
        },
        "p3_local_status": (
            "PROJECTABLE_BUT_EXTERNAL_AND_POLICY_GATES_REMAIN"
            if fresh and v4["local_v4_status"] == "LOCAL_V4_PROJECTABLE"
            else "EVIDENCE_INCOMPLETE_OR_NOT_NEW"
        ),
    }
