"""S7.5: read-only real Scanner Capture to existing TypeSafe V4 readiness.

No real-market data is sent to TypeSafe. This is diagnostic only: an
inspectable local V4 projection is NOT rights, timing, horizon or model approval.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
from app.jev.scanner_lineage_s7_4 import diagnose_prepared
from app.jev.scanner_shadow_s7 import load_frozen_candidates
from app.jev.scanner_shadow_s7_3 import (
    prepare_shadow_candidate, preflight_shadow_candidate,
)
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import (
    route_typesafe_state_v4, project_typesafe_state_v4,
)

VERSION = "JEV_ACT2_S7_5_SCANNER_V4_READINESS_V1"


def diagnose_candidate(capture: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    """Audit a canonical immutable Scanner sample without constructing a provider."""
    prepared = prepare_shadow_candidate(capture, sample)
    integrity = assess_frozen_candidate(capture, sample)
    lineage = diagnose_prepared(prepared)
    category = integrity["category"]
    reasons = set(integrity["codes"])
    reasons.update(lineage["reason_codes"])
    local_status = "BLOCKED_INTEGRITY"
    v4_status = None
    state_hash = None
    state_bytes = None

    if category == "REFERENCE_ONLY":
        # A non-entry sample is not a V4 semantic-skip verdict.
        local_status = "REFERENCE_ONLY"
        reasons.add("NOT_ENTRY_CANDIDATE")
    elif category == "INVALID" or lineage["lineage_analysis_status"] != "COMPLETE":
        if lineage["lineage_analysis_status"] != "COMPLETE":
            reasons.add("S7_4_LINEAGE_NOT_COMPLETE")
    else:
        # Only verified legacy/original Scanner samples reach the V4 route.
        horizon = str(capture.get("horizon_intent") or "")
        if horizon not in ("SHORT", "MEDIUM"):
            local_status = "BLOCKED_HORIZON"
            reasons.add("V4_HORIZON_UNSUPPORTED")
        else:
            try:
                # V4 expects the *original* Prospective snapshot and its own
                # semantic relation contract, never a translated S7.3 Choice.
                v4_sample = {
                    **sample, "horizon_intent": horizon,
                }
                route = route_typesafe_state_v4(v4_sample)
                v4_status = route.local_status
                if not route.provider_eligible:
                    local_status = "SKIPPED_LOCAL"
                    reasons.add(route.reason_code)
                else:
                    projection = project_typesafe_state_v4(v4_sample)
                    local_status = "LOCAL_V4_PROJECTABLE"
                    state_hash = projection.state_hash
                    state_bytes = projection.state_bytes
            except TypeSafeStateProjectionError as exc:
                local_status = "BLOCKED_SEMANTIC_SOURCE"
                reasons.add(str(exc))

    preflight = preflight_shadow_candidate(prepared)
    reasons.update(preflight["blocking_reasons"])
    return {
        "version": VERSION,
        "identity": prepared["identity"],
        "category": category,
        "integrity_status": prepared["status"],
        "local_v4_status": local_status,
        "v4_local_semantic_status": v4_status,
        "v4_state_hash": state_hash,
        "v4_state_bytes": state_bytes,
        "capture_snapshot_hash": sample.get("snapshot_hash"),
        "s73_packet_hash": prepared.get("packet_hash"),
        "lineage_analysis_status": lineage["lineage_analysis_status"],
        "s73_lineage_field_count": lineage["field_count"],
        "s73_lineage_unclassified_fields": lineage["unclassified_fields"],
        # S7.4 enumerates the old Choice packet, NOT the TypeSafe V4 body.
        "v4_outbound_lineage_status": (
            "NOT_AUDITED" if local_status == "LOCAL_V4_PROJECTABLE"
            else "NOT_APPLICABLE"
        ),
        "v4_wire_contract_verified": False,
        "integrity_reason_codes": integrity["codes"],
        "reason_codes": sorted(reasons),
        "provider_status": "PROVIDER_HOLD",
        "provider_blocking_reasons": preflight["blocking_reasons"],
        "real_provider_eligible": False,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def diagnose_capture(
    simulation_db: Path, *, capture_id: str | None, limit: int = 60,
    sample_index: int | None = None,
) -> dict[str, Any]:
    if not capture_id:
        raise DecisionReviewContractError("S7_5_CAPTURE_ID_REQUIRED")
    if sample_index is not None and (
        type(sample_index) is not int or not 0 <= sample_index <= 500
    ):
        raise DecisionReviewContractError("S7_5_SAMPLE_INDEX_INVALID")
    pairs = load_frozen_candidates(simulation_db, capture_id=capture_id, limit=limit)
    if sample_index is not None:
        pairs = [(c, s) for c, s in pairs if s["sample_index"] == sample_index]
        if not pairs:
            raise DecisionReviewContractError("S7_5_SAMPLE_NOT_FOUND")
    records = [diagnose_candidate(capture, sample) for capture, sample in pairs]
    categories = ("LOCAL_V4_PROJECTABLE", "SKIPPED_LOCAL", "REFERENCE_ONLY", "BLOCKED_INTEGRITY",
                  "BLOCKED_HORIZON", "BLOCKED_SEMANTIC_SOURCE")
    return {
        "version": VERSION,
        "status": "V4_READINESS_PROVIDER_HOLD",
        "capture_id": pairs[0][0]["id"] if pairs else capture_id,
        "total_records": len(records),
        "entry_candidates": sum(r["category"] != "REFERENCE_ONLY" for r in records),
        "counts": {name: sum(r["local_v4_status"] == name for r in records)
                   for name in categories},
        "records": records,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }
