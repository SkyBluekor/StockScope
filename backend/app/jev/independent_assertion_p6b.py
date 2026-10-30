"""P6-B: evidence-bound *operator-authored* local assertions.

Neither a headline nor an as-of reference by itself is a contradiction.
No endpoint accepts client-authored assertions. An optional local JSON registry
is read from STOCKSCOPE_JEV_P6_ASSERTIONS_FILE (absent by default); even a
matching registry never permits market-data transmission, prediction or trades.
Approval labels in local JSON are not third-party cryptographic attestations.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from app.event_evidence.asof import EventEvidenceAsOfReader
from app.event_evidence.errors import EventEvidenceContractError
from app.event_evidence.policy import EvidenceCapability, policy_for_event_source
from app.jev.independent_event_reference_p6 import (
    _aware_utc, classify_event_reference, inspect_frozen_event_reference,
)
from app.jev.scanner_shadow_s7 import load_frozen_candidates
from app.strategy.semantic_source_v2 import verify_semantic_source_v2

VERSION = "JEV_P6_INDEPENDENT_EVENT_ASSERTION_V1"
MANIFEST_VERSION = "JEV_P6_LOCAL_ASSERTION_REGISTRY_V1"
VALID_RELATIONS = {"CONTRADICTS", "SUPPORTS", "UNRESOLVED"}
ALL_STATUSES = {
    "NO_INDEPENDENT_EVIDENCE", "EVIDENCE_CONFLICT", "EVIDENCE_COMPATIBLE",
    "EVIDENCE_UNCERTAIN", "EVIDENCE_NOT_USABLE",
}


def _digest(body: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _stamp(value: Any) -> str | None:
    return _aware_utc(value)


def _base(reference: dict[str, Any]) -> dict[str, Any]:
    return {
        **reference,
        "version": VERSION,
        "assertion_contract_version": VERSION,
        "assertion_status": "NOT_EVALUATED",
        "approved_assertion_count": 0,
        "reviewed_event_count": 0,
        "retrospective_assertion_count": 0,
        "assessment_origin": "OPERATOR_AUTHORED_LOCAL_ONLY",
        "local_review_required": False,
        "independent_review_candidate": False,
        "independent_conflict_proven": False,
        "review_needed": False,
        "model_review_executed": False,
        "external_model_call_allowed": False,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def _registry() -> tuple[list[dict[str, Any]], str | None]:
    path = os.getenv("STOCKSCOPE_JEV_P6_ASSERTIONS_FILE")
    if not path:
        return [], None
    try:
        file = Path(path)
        if not file.is_file() or file.stat().st_size > 1_048_576:
            return [], "P6B_ASSERTION_REGISTRY_UNAVAILABLE"
        document = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("version") != MANIFEST_VERSION:
            return [], "P6B_ASSERTION_REGISTRY_INVALID"
        records = document.get("assertions")
        if not isinstance(records, list) or len(records) > 500:
            return [], "P6B_ASSERTION_REGISTRY_INVALID"
        if not all(isinstance(record, dict) for record in records):
            return [], "P6B_ASSERTION_REGISTRY_INVALID"
        return records, None
    except (OSError, UnicodeError, ValueError):
        return [], "P6B_ASSERTION_REGISTRY_INVALID"


def _real_source_rights(
    source_kinds: Iterable[str], *, naver_provider_kind: str | None,
) -> bool:
    """A persisted derived assertion needs separate source retention rights."""
    for kind in source_kinds:
        try:
            p = policy_for_event_source(
                kind,
                provider_kind=naver_provider_kind if kind == "NAVER_NEWS" else None,
            )
        except EventEvidenceContractError:
            return False
        if not p.allows(EvidenceCapability.DERIVED_RETENTION):
            return False
    return True


def evaluate_local_assertions(
    *,
    reference: dict[str, Any],
    projection: dict[str, Any],
    source_v2: dict[str, Any] | None,
    records: list[dict[str, Any]],
    naver_provider_kind: str | None = None,
    enforce_source_retention: bool = True,
) -> dict[str, Any]:
    """Evaluate pinned reviewed claims without reinterpreting market facts.

    The source_v2 contract defines which strategy claims exist. The verified
    internal as-of pins define what historical event revisions were observed.
    Hash-matching author records are *local attestations*, not legal rights.
    """
    result = _base(reference)
    result["assertion_status"] = "REFERENCE_ONLY"
    reasons = set(result["reason_codes"])
    status = reference["status"]
    if status != "EVIDENCE_UNCERTAIN":
        result["status"] = status
        result["assertion_status"] = "NO_ASOF_REFERENCE"
        return result

    pins = projection.get("_internal_pins")
    if not isinstance(pins, list) or len(pins) != len(projection.get("event_evidence", {}).get("items", [])):
        reasons.add("P6B_REFERENCE_PINS_UNAVAILABLE")
        result.update(status="EVIDENCE_NOT_USABLE", assertion_status="INVALID_REFERENCE_PINS",
                      reason_codes=sorted(reasons))
        return result
    ok, err = verify_semantic_source_v2(source_v2)
    relations = source_v2.get("relations", {}) if isinstance(source_v2, dict) else {}
    strategy = source_v2.get("strategy", {}) if isinstance(source_v2, dict) else {}
    if not ok or not isinstance(relations, dict) or not isinstance(strategy, dict):
        reasons.add(err or "P6B_STRATEGY_SOURCE_NOT_VERIFIED")
        result.update(status="EVIDENCE_UNCERTAIN", assertion_status="NO_VERIFIED_STRATEGY_BINDING",
                      reason_codes=sorted(reasons))
        return result
    claim_ids = {
        c.get("concept_id") for c in relations.get("concepts", [])
        if isinstance(c, dict)
    }
    if not claim_ids or not relations.get("relation_contract_hash"):
        reasons.add("P6B_NO_AUTHORED_STRATEGY_CLAIMS")
        result.update(status="EVIDENCE_UNCERTAIN", assertion_status="NO_AUTHORED_STRATEGY_CLAIMS",
                      reason_codes=sorted(reasons))
        return result

    cutoff = _stamp(reference.get("decision_cutoff"))
    if cutoff is None or projection.get("projection_hash") != reference.get("projection_hash"):
        reasons.add("P6B_PROJECTION_IDENTITY_MISMATCH")
        result.update(status="EVIDENCE_NOT_USABLE", assertion_status="INVALID_PROJECTION",
                      reason_codes=sorted(reasons))
        return result

    verified: dict[tuple[str, int], tuple[dict[str, Any], dict[str, Any]]] = {}
    for item, pin in zip(projection["event_evidence"]["items"], pins):
        if not isinstance(item, dict) or not isinstance(pin, dict):
            reasons.add("P6B_INVALID_PIN_SHAPE")
            continue
        key = (str(pin.get("event_id")), pin.get("event_version"))
        if item.get("quality_state") != "USABLE":
            continue
        if item.get("revision_state") not in {"ORIGINAL", "CORRECTED"}:
            continue
        verified[key] = (item, pin)

    selected: dict[tuple[str, int], str] = {}
    retrospective_count = 0
    invalid_count = 0
    for raw in records:
        if raw.get("capture_id") != reference["capture_id"] or raw.get("sample_index") != reference["sample_index"]:
            continue
        if raw.get("snapshot_hash") != reference["snapshot_hash"] or raw.get("market") != reference["market"] or raw.get("ticker") != reference["ticker"]:
            invalid_count += 1
            reasons.add("P6B_ASSERTION_CANDIDATE_IDENTITY_MISMATCH")
            continue
        body = dict(raw)
        given_hash = body.pop("assertion_hash", None)
        try:
            authentic = isinstance(given_hash, str) and given_hash == _digest(body)
        except (TypeError, ValueError):
            authentic = False
        if not authentic or raw.get("contract_version") != VERSION:
            invalid_count += 1
            reasons.add("P6B_ASSERTION_HASH_OR_CONTRACT_INVALID")
            continue
        event_id = raw.get("event_id")
        event_version = raw.get("event_version")
        if not isinstance(event_id, str) or type(event_version) is not int:
            invalid_count += 1
            reasons.add("P6B_ASSERTION_EVENT_IDENTITY_INVALID")
            continue
        key = (event_id, event_version)
        observed = verified.get(key)
        if observed is None:
            invalid_count += 1
            reasons.add("P6B_ASSERTION_EVENT_REVISION_NOT_PINNED")
            continue
        event, pin = observed
        sources = pin.get("source_refs", [])
        source_match = any(
            src.get("source_ref_id") == raw.get("source_ref_id")
            and src.get("source_ref_hash") == raw.get("source_ref_hash")
            and src.get("content_hash") == raw.get("content_hash")
            for src in sources if isinstance(src, dict)
        )
        if not source_match or raw.get("event_hash") != pin.get("event_hash") or raw.get("quality_hash") != pin.get("quality_hash") or raw.get("projection_hash") != reference.get("projection_hash"):
            invalid_count += 1
            reasons.add("P6B_ASSERTION_EVIDENCE_PIN_MISMATCH")
            continue
        relation = raw.get("relation")
        claim_id = raw.get("claim_id")
        if (
            not isinstance(claim_id, str)
            or not isinstance(relation, str)
            or raw.get("strategy_source_hash") != source_v2.get("source_snapshot_hash")
            or raw.get("strategy_key") != relations.get("strategy_key")
            or claim_id not in claim_ids
            or relation not in VALID_RELATIONS
        ):
            invalid_count += 1
            reasons.add("P6B_ASSERTION_STRATEGY_BINDING_INVALID")
            continue
        approved = _stamp(raw.get("approved_at"))
        created = _stamp(raw.get("created_at"))
        if (
            raw.get("approval_state") != "APPROVED"
            or not str(raw.get("approved_by") or "").strip()
            or not str(raw.get("fact_statement") or "").strip()
            or not str(raw.get("review_note") or "").strip()
            or not approved or not created or created > approved
        ):
            invalid_count += 1
            reasons.add("P6B_ASSERTION_APPROVAL_NOT_VERIFIED")
            continue
        if approved > cutoff or created > cutoff:
            retrospective_count += 1
            reasons.add("P6B_RETROSPECTIVE_ASSERTION_EXCLUDED")
            continue
        if enforce_source_retention and not _real_source_rights(
            event.get("source_kinds", []),
            naver_provider_kind=naver_provider_kind,
        ):
            invalid_count += 1
            reasons.add("P6B_SOURCE_DERIVED_RETENTION_NOT_APPROVED")
            continue
        # All claims for the same canonical event must agree, otherwise fail to
        # ambiguous; multiple sources of one event are never multiple votes.
        canonical = str(pin.get("sample_identity") or pin["event_id"])
        event_key = (canonical, int(pin["event_version"]))
        existing = selected.get(event_key)
        selected[event_key] = relation if existing is None or existing == relation else "UNRESOLVED"

    vals = set(selected.values())
    if invalid_count:
        status, assessment = "EVIDENCE_NOT_USABLE", "ASSERTION_INTEGRITY_OR_RIGHTS_BLOCKED"
    elif not selected:
        status, assessment = "EVIDENCE_UNCERTAIN", "NO_APPROVED_PROSPECTIVE_ASSERTIONS"
        reasons.add("P6B_NO_VALID_LOCAL_ASSERTION")
    elif "UNRESOLVED" in vals or len(vals) > 1:
        status, assessment = "EVIDENCE_UNCERTAIN", "MIXED_OR_UNRESOLVED"
    elif vals == {"CONTRADICTS"}:
        status, assessment = "EVIDENCE_CONFLICT", "LOCALLY_REVIEWED_CONFLICT"
    elif vals == {"SUPPORTS"}:
        status, assessment = "EVIDENCE_COMPATIBLE", "LOCALLY_REVIEWED_COMPATIBLE"
    else:
        status, assessment = "EVIDENCE_UNCERTAIN", "NO_DECISIVE_RELATION"
    result.update(
        status=status,
        assertion_status=assessment,
        reason_codes=sorted(reasons),
        approved_assertion_count=len(selected),
        reviewed_event_count=len(selected),
        retrospective_assertion_count=retrospective_count,
        local_review_required=status in {"EVIDENCE_CONFLICT", "EVIDENCE_UNCERTAIN"} and bool(selected),
        independent_review_candidate=status == "EVIDENCE_UNCERTAIN" and bool(selected),
        independent_conflict_proven=False,  # local operator note, not independent proof
        review_needed=status in {"EVIDENCE_CONFLICT", "EVIDENCE_UNCERTAIN"} and bool(selected),
    )
    return result


def inspect_frozen_event_assertions(
    simulation_db: Path, *, capture_id: str, sample_index: int,
    naver_provider_kind: str | None = None,
) -> dict[str, Any]:
    """Read canonical snapshot, source as-of pins, optional local registry; no writes."""
    db = Path(simulation_db)
    reference = inspect_frozen_event_reference(
        db, capture_id=capture_id, sample_index=sample_index,
        naver_provider_kind=naver_provider_kind,
    )
    result = _base(reference)
    if reference["status"] != "EVIDENCE_UNCERTAIN":
        result["assertion_status"] = "NO_ASOF_REFERENCE"
        return result
    pairs = load_frozen_candidates(db, capture_id=capture_id, limit=500)
    pair = next(((c, s) for c, s in pairs if int(s["sample_index"]) == sample_index), None)
    if pair is None or pair[1]["snapshot_hash"] != reference["snapshot_hash"]:
        result.update(status="EVIDENCE_NOT_USABLE", assertion_status="FROZEN_IDENTITY_MISMATCH",
                      reason_codes=["P6B_FROZEN_IDENTITY_MISMATCH"])
        return result
    try:
        projection = EventEvidenceAsOfReader(db).stock_reference_as_of(
            str(pair[1]["ticker"]), str(pair[1]["market"]),
            str(reference["decision_cutoff"]), limit=8, include_internal_pins=True,
        )
        prior = classify_event_reference(
            projection, code=reference["ticker"], market=reference["market"],
            cutoff=reference["decision_cutoff"],
            naver_provider_kind=naver_provider_kind,
        )
    except EventEvidenceContractError as exc:
        result.update(status="EVIDENCE_NOT_USABLE", assertion_status="REFERENCE_CHANGED",
                      reason_codes=[exc.code])
        return result
    if (
        prior["status"] != reference["status"]
        or prior["projection_hash"] != reference["projection_hash"]
    ):
        result.update(status="EVIDENCE_NOT_USABLE", assertion_status="REFERENCE_CHANGED",
                      reason_codes=["P6B_REFERENCE_CHANGED_BETWEEN_READS"])
        return result
    records, error = _registry()
    if error:
        result.update(status="EVIDENCE_NOT_USABLE", assertion_status="REGISTRY_INVALID",
                      reason_codes=sorted(set(reference["reason_codes"] + [error])))
        return result
    return evaluate_local_assertions(
        reference=reference, projection=projection,
        source_v2=pair[1]["snapshot"].get("semantic_source_v2"),
        records=records, naver_provider_kind=naver_provider_kind,
    )
