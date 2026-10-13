"""S7.5: connect frozen real Scanner candidates to the existing V4 local gate.

This is a read-only readiness diagnostic, NOT a market-data provider adapter.
S7.3 Choice packet lineage is diagnostic evidence, not V4 Noul wire lineage
or a grant to transmit derived market data to TypeSafe.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_lineage_s7_4 import diagnose_prepared
from app.jev.scanner_shadow_s7 import load_frozen_candidates
from app.jev.scanner_shadow_s7_3 import prepare_shadow_candidate
from app.jev.typesafe_questions_v4 import (
    JEV_TYPESAFE_QUESTION_IDS_V4,
    JEV_TYPESAFE_QUESTION_SET_HASH_V4,
)
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import (
    JEV_TYPESAFE_PROJECTOR_HASH_V4,
    JEV_TYPESAFE_STATE_CONTRACT_HASH_V4,
    project_typesafe_state_v4,
    route_typesafe_state_v4,
)

VERSION = "JEV_ACT2_S7_5_SCANNER_V4_LOCAL_READINESS_V1"
VALID_HORIZONS = frozenset({"SHORT", "MEDIUM"})
PROVIDER_BLOCKERS = (
    "V4_SOURCE_RIGHTS_UNVERIFIED",
    "V4_SOURCE_RELEASE_TIME_UNVERIFIED",
    "V4_SOURCE_LINEAGE_UNVERIFIED",
    "REAL_MARKET_PROVIDER_NOT_AUTHORIZED",
    "V4_MODEL_AND_BILLING_NOT_APPROVED",
    "EXPLICIT_EXECUTION_APPROVAL_MISSING",
)
V4_QUESTION_ID = JEV_TYPESAFE_QUESTION_IDS_V4[0]


def diagnose_candidate(
    capture: dict[str, Any], sample: dict[str, Any],
) -> dict[str, Any]:
    """Never infer a missing identity or mutate the canonical input."""
    # prepare_shadow_candidate runs the independent S7.1 integrity checker,
    # then the S7.3 engine-source bijection checks; no provider construction.
    prepared = prepare_shadow_candidate(capture, sample)
    lineage = diagnose_prepared(prepared)
    category = str(prepared["category"])
    integrity_codes = list(prepared.get("reason_codes") or [])
    stage = "BLOCKED_INTEGRITY"
    v4_local_status: str | None = None
    v4_route_reason: str | None = None
    state_hash: str | None = None
    state_bytes: int | None = None
    reasons: list[str] = []

    if category == "REFERENCE_ONLY":
        stage = "REFERENCE_ONLY"
        reasons = integrity_codes or ["NOT_ENTRY_CANDIDATE"]
    elif category == "INVALID" or prepared["status"] != "LOCAL_PACKET_READY":
        reasons = integrity_codes or ["LOCAL_INTEGRITY_NOT_VERIFIED"]
    elif (
        lineage["lineage_analysis_status"] != "COMPLETE"
        or lineage["unclassified_fields"] != 0
    ):
        reasons = ["S7_3_PACKET_LINEAGE_NOT_COMPLETE"] + [
            code for code in lineage["reason_codes"]
            if code in {"UNKNOWN_OUTBOUND_FIELD", "PACKET_HASH_MISMATCH"}
        ]
    elif str(capture.get("horizon_intent") or "") not in VALID_HORIZONS:
        stage = "BLOCKED_HORIZON"
        reasons = [
            "LEGACY_HORIZON_UNDEFINED"
            if capture.get("horizon_intent") == "LEGACY_UNSPECIFIED"
            else "OUT_OF_SCOPE_HORIZON"
        ]
    else:
        # Original snapshot only. Never project from the S7.3 Choice
        # packet or patch absent semantic relations/strategy identity.
        v4_sample = dict(sample)
        v4_sample["horizon_intent"] = capture["horizon_intent"]
        try:
            route = route_typesafe_state_v4(v4_sample)
            v4_local_status = route.local_status
            v4_route_reason = route.reason_code
            if route.provider_eligible:
                projected = project_typesafe_state_v4(v4_sample)
                stage = "LOCAL_V4_PROJECTABLE"
                state_hash = projected.state_hash
                state_bytes = projected.state_bytes
            else:
                stage = "SKIPPED_LOCAL"
                reasons = [route.reason_code]
        except TypeSafeStateProjectionError as exc:
            stage = "BLOCKED_SEMANTIC_SOURCE"
            reasons = [exc.code]

    return {
        "version": VERSION,
        "identity": dict(prepared["identity"]),
        "status": stage,
        "integrity_category": category,
        "integrity_status": prepared["status"],
        "integrity_reason_codes": integrity_codes,
        "reason_codes": sorted(set(reasons)),
        "s7_3_packet_lineage_status": lineage["lineage_analysis_status"],
        "s7_3_unclassified_fields": lineage["unclassified_fields"],
        "temporal_status": prepared.get("temporal_status"),
        "capture_horizon_intent": capture.get("horizon_intent"),
        "v4_local_status": v4_local_status,
        "v4_route_reason": v4_route_reason,
        "v4_state_hash": state_hash,
        "v4_state_bytes": state_bytes,
        "v4_projector_hash": JEV_TYPESAFE_PROJECTOR_HASH_V4,
        "v4_state_contract_hash": JEV_TYPESAFE_STATE_CONTRACT_HASH_V4,
        "v4_question_set_hash": JEV_TYPESAFE_QUESTION_SET_HASH_V4,
        "v4_question_id": V4_QUESTION_ID,
        # S7.4 classified S7.3 Choice packet fields only. V4's wire
        # has no per-source release time, certified lineage or rights.
        "v4_source_rights_status": "UNVERIFIED",
        "v4_source_release_time_status": "UNVERIFIED",
        "v4_source_lineage_status": "UNVERIFIED",
        "provider_status": "PROVIDER_HOLD",
        "provider_blocking_reasons": list(PROVIDER_BLOCKERS),
        "real_provider_eligible": False,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def diagnose_capture(
    simulation_db: Path, *, capture_id: str | None,
    limit: int = 60, sample_index: int | None = None,
) -> dict[str, Any]:
    """Inspect only canonical COMPLETE rows in SQLite query-only mode."""
    if not capture_id:
        raise DecisionReviewContractError("S7_5_CAPTURE_ID_REQUIRED")
    if sample_index is not None and (
        type(sample_index) is not int or not 0 <= sample_index <= 500
    ):
        raise DecisionReviewContractError("S7_5_SAMPLE_INDEX_INVALID")
    pairs = load_frozen_candidates(
        simulation_db, capture_id=capture_id, limit=limit,
    )
    if sample_index is not None:
        pairs = [(c, s) for c, s in pairs if s["sample_index"] == sample_index]
        if not pairs:
            raise DecisionReviewContractError("S7_5_SAMPLE_NOT_FOUND")
    records = [diagnose_candidate(capture, sample) for capture, sample in pairs]
    counts = Counter(item["status"] for item in records)
    return {
        "version": VERSION,
        "status": "SCANNER_V4_LOCAL_DIAGNOSTIC_PROVIDER_HOLD",
        "capture_id": pairs[0][0]["id"] if pairs else capture_id,
        "total_records": len(records),
        "entry_candidates": sum(r["status"] != "REFERENCE_ONLY" for r in records),
        "local_v4_projectable": counts["LOCAL_V4_PROJECTABLE"],
        "skipped_local": counts["SKIPPED_LOCAL"],
        "blocked_integrity": counts["BLOCKED_INTEGRITY"],
        "blocked_horizon": counts["BLOCKED_HORIZON"],
        "blocked_semantic_source": counts["BLOCKED_SEMANTIC_SOURCE"],
        "reference_only": counts["REFERENCE_ONLY"],
        "records": records,
        "v4_question_id": V4_QUESTION_ID,
        "v4_question_set_hash": JEV_TYPESAFE_QUESTION_SET_HASH_V4,
        "s7_3_packet_is_v4_wire": False,
        "real_provider_eligible": 0,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }
