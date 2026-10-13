"""Read-only inventory of frozen evidence for an *additional* local JEV reviewer.

An existing Scanner PASS, its local semantic composition, entry-role check or
Risk verdict is not new independent evidence. This inventory deliberately
produces no review opinion, provider request, or evaluation row.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app.prospective.models import digest_json

from .decision_reviewer_offline import DecisionReviewContractError
from .scanner_integrity_s7_1 import assess_frozen_candidate
from .scanner_shadow_s7 import load_frozen_candidates


VERSION = "JEV_LOCAL_INDEPENDENT_EVIDENCE_AUDIT_V1"

# A dimension already evaluated by the baseline cannot count as an
# incremental reviewer discovery merely because JEV can also read it.
_BASELINE_DIMENSIONS = (
    ("passed_conditions", "SCANNER_ENGINE_AND_SEMANTIC_COMPOSITION"),
    ("entry_rule_role", "EXISTING_ENTRY_SEMANTICS"),
    ("risk_status_warning", "SCANNER_RISK"),
)


def diagnose_candidate(capture: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    """Inventory only; do not interpret uncontracted fields as new evidence."""
    identity = {
        "capture_id": capture.get("id"),
        "sample_index": sample.get("sample_index"),
        "snapshot_hash": sample.get("snapshot_hash"),
    }
    snapshot = sample.get("snapshot")
    if sample.get("action") != "ENTRY_CANDIDATE":
        category = "REFERENCE_ONLY"
        reason = "NOT_ENTRY_CANDIDATE"
    elif (not isinstance(snapshot, dict) or not sample.get("snapshot_hash")
          or digest_json(snapshot) != sample["snapshot_hash"]):
        category = "INVALID"
        reason = "SNAPSHOT_HASH_MISMATCH"
    else:
        try:
            integrity = assess_frozen_candidate(capture, sample)
            category = integrity["category"]
            reason = (
                "INTEGRITY_NOT_VERIFIED" if category == "INVALID"
                else "NO_INDEPENDENT_FROZEN_EVIDENCE_CONTRACT"
            )
        except (DecisionReviewContractError, KeyError, TypeError, ValueError):
            category = "INVALID"
            reason = "INTEGRITY_NOT_VERIFIED"

    axes: list[dict[str, Any]] = []
    if category in {"LOCAL_VALIDATED", "LEGACY_LIMITED"} and isinstance(snapshot, dict):
        source = snapshot.get("semantic_source_v2")
        source = source if isinstance(source, dict) else {}
        conditions = source.get("conditions")
        readiness = source.get("readiness")
        axes = [
            {
                "dimension": _BASELINE_DIMENSIONS[0][0],
                "baseline_owner": _BASELINE_DIMENSIONS[0][1],
                "frozen_available": isinstance(conditions, dict)
                and bool(conditions.get("items")),
                "incremental_evidence": False,
            },
            {
                "dimension": _BASELINE_DIMENSIONS[1][0],
                "baseline_owner": _BASELINE_DIMENSIONS[1][1],
                "frozen_available": isinstance(readiness, dict)
                and readiness.get("q2_status") == "COMPLETE",
                "incremental_evidence": False,
            },
            {
                "dimension": _BASELINE_DIMENSIONS[2][0],
                "baseline_owner": _BASELINE_DIMENSIONS[2][1],
                "frozen_available": isinstance(snapshot.get("risk"), dict),
                "incremental_evidence": False,
            },
        ]

    usable = category in {"LOCAL_VALIDATED", "LEGACY_LIMITED"}
    return {
        "version": VERSION,
        "identity": identity,
        "category": category,
        "status": (
            "NO_INDEPENDENT_REVIEW_EVIDENCE" if usable
            else "REFERENCE_ONLY" if category == "REFERENCE_ONLY"
            else "BLOCKED_INTEGRITY"
        ),
        "reason_code": reason,
        "baseline_evidence_axes": axes,
        "new_independent_evidence_count": 0,
        "review_decision": None,
        "shadow_evaluation_eligible": False,
        "type_safe_v4_unchanged": True,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def diagnose_capture(
    simulation_db: Path, *, capture_id: str | None,
    limit: int = 60, sample_index: int | None = None,
) -> dict[str, Any]:
    if not capture_id:
        raise DecisionReviewContractError("LOCAL_EVIDENCE_CAPTURE_ID_REQUIRED")
    if sample_index is not None and (
        type(sample_index) is not int or not 0 <= sample_index <= 500
    ):
        raise DecisionReviewContractError("LOCAL_EVIDENCE_SAMPLE_INDEX_INVALID")
    pairs = load_frozen_candidates(simulation_db, capture_id=capture_id, limit=limit)
    if sample_index is not None:
        pairs = [(c, s) for c, s in pairs if s["sample_index"] == sample_index]
        if not pairs:
            raise DecisionReviewContractError("LOCAL_EVIDENCE_SAMPLE_NOT_FOUND")
    records = [diagnose_candidate(c, s) for c, s in pairs]
    counts = Counter(row["status"] for row in records)
    return {
        "version": VERSION,
        "status": "LOCAL_REVIEW_EVIDENCE_DIAGNOSTIC_ONLY",
        "capture_id": pairs[0][0]["id"] if pairs else capture_id,
        "total_records": len(records),
        "counts": dict(sorted(counts.items())),
        "independent_evidence_ready": 0,
        "review_opinions_created": 0,
        "records": records,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
    }
