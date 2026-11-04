"""P5: batch classify one already-frozen SHORT Scanner capture, no provider.

The P4 inspector remains the source of truth for every original immutable
sample and independently reports local V4, policy, provenance and rights.
This module adds ONLY aggregate routing/summary, not a new semantic engine.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.jev.live_04r_p4_final import inspect_stored_horizon_capture
from app.jev.scanner_shadow_s7 import load_frozen_candidates

VERSION = "JEV_LIVE_04R_P5_ENTRY_ROUTING_V1"
ROUTES = (
    "LOCAL_MATCH", "LOCAL_CONFLICT", "LOCAL_INCOMPLETE", "LOCAL_AMBIGUOUS",
    "RESIDUAL_READY", "RESIDUAL_BLOCKED", "BLOCKED_EVIDENCE",
)
SEMANTIC_ROUTES = {
    "LOCAL_MATCH": "LOCAL_MATCH",
    "LOCAL_CONFLICT": "LOCAL_CONFLICT",
    "LOCAL_INCOMPLETE": "LOCAL_INCOMPLETE",
    "LOCAL_AMBIGUOUS": "LOCAL_AMBIGUOUS",
}


def _route_one(report: dict[str, Any]) -> str:
    semantic = report["local_v4"]["semantic_status"]
    v4_status = report["local_v4"]["status"]
    valid = (
        report["frozen_contract"]["request_horizon_matches_canonical"]
        and report["frozen_contract"]["requested_canonical_context_match"]
        and report["frozen_contract"]["semantic_source_v2_valid"]
    )
    if not valid:
        return "BLOCKED_EVIDENCE"
    if v4_status == "SKIPPED_LOCAL" and semantic in SEMANTIC_ROUTES:
        return SEMANTIC_ROUTES[semantic]
    if semantic == "RESIDUAL_SEMANTIC_REVIEW":
        return "RESIDUAL_READY" if v4_status == "LOCAL_V4_PROJECTABLE" else "RESIDUAL_BLOCKED"
    return "BLOCKED_EVIDENCE"


def inspect_frozen_entry_batch(
    simulation_db: Path, *, capture_id: str,
) -> dict[str, Any]:
    """Analyze all ENTRY samples from one explicit canonical COMPLETE capture.

    Never constructs synthetic market samples or infers unsupported original
    strategy identities. A DUPLICATE is mapped to its canonical COMPLETE.
    """
    if not isinstance(capture_id, str) or not 0 < len(capture_id) <= 200:
        raise ValueError("P5_CAPTURE_ID_REQUIRED")
    pairs = load_frozen_candidates(
        Path(simulation_db), capture_id=capture_id, limit=500,
    )
    entries = sorted(
        (sample for _, sample in pairs if sample["action"] == "ENTRY_CANDIDATE"),
        key=lambda sample: (int(sample["rank"] or 999999), int(sample["sample_index"])),
    )
    rows = []
    for sample in entries:
        index = int(sample["sample_index"])
        report = inspect_stored_horizon_capture(
            Path(simulation_db), capture_id=capture_id, sample_index=index,
        )
        route = _route_one(report)
        rows.append({
            "sample_index": index,
            "market": sample["market"],
            "ticker": sample["ticker"],
            "rank": sample["rank"],
            "snapshot_hash": sample["snapshot_hash"],
            "routing": route,
            "semantic_status": report["local_v4"]["semantic_status"],
            "local_v4_status": report["local_v4"]["status"],
            "v4_state_hash": report["local_v4"]["state_hash"] if route == "RESIDUAL_READY" else None,
            "strategy_identity": report["strategy_identity"]["status"],
            "source_v2_valid": report["frozen_contract"]["semantic_source_v2_valid"],
            "provider_decision": report["provider_authorization"]["decision"],
            "reason_codes": report["local_v4"]["reason_codes"],
        })
    counts = {route: sum(row["routing"] == route for row in rows) for route in ROUTES}
    return {
        "version": VERSION,
        "read_only": True,
        "capture_id": capture_id,
        "canonical_capture_id": pairs[0][0]["id"] if pairs else None,
        "status": "COMPLETE" if entries else "NO_ENTRY_CANDIDATE",
        "entry_count": len(entries),
        "counts": counts,
        "rows": rows,
        "review_eligible_count": counts["RESIDUAL_READY"],
        "external_model_call_allowed": False,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }
