"""P6-A: independent event *reference* for a frozen Scanner sample.

This is not a strategy conflict verdict or a new TypeSafe input. EventEvidence
as-of is a reference-only product, and existing Naver/OpenDART policies do not
permit AI transformation. All reads are local; no migrations or providers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.event_evidence.asof import EventEvidenceAsOfReader
from app.event_evidence.errors import EventEvidenceContractError
from app.event_evidence.policy import EvidenceCapability, policy_for_event_source
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_shadow_s7 import load_frozen_candidates

VERSION = "JEV_LIVE_04R_P6_INDEPENDENT_EVENT_REFERENCE_V1"
NO_EVIDENCE = "NO_INDEPENDENT_EVIDENCE"
UNCERTAIN = "EVIDENCE_UNCERTAIN"
NOT_USABLE = "EVIDENCE_NOT_USABLE"


def _aware_utc(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def _base(capture: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": VERSION,
        "read_only": True,
        "capture_id": str(capture["id"]),
        "sample_index": int(sample["sample_index"]),
        "snapshot_hash": str(sample["snapshot_hash"]),
        "market": str(sample["market"]),
        "ticker": str(sample["ticker"]),
        "status": NOT_USABLE,
        "reason_codes": [],
        "decision_cutoff": None,
        "cutoff_source": "CAPTURE_CREATED_AT_NOT_MARKET_PUBLICATION",
        "event_reference_status": "NOT_READ",
        "projection_hash": None,
        "reference_count": 0,
        "source_kinds": [],
        "ai_input_rights": "NOT_APPROVED",
        "independent_conflict_proven": False,
        "review_needed": False,
        "model_review_executed": False,
        "external_model_call_allowed": False,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def classify_event_reference(
    projection: dict[str, Any],
    *, code: str, market: str, cutoff: str,
    naver_provider_kind: str | None = None,
) -> dict[str, Any]:
    """Fail-closed reference classification. No event text or sentiment inference.

    In particular, an independent *reference* is not a reviewed negative claim:
    the current as-of contract has no independently approved contradiction
    assertion. Therefore it cannot emit EVIDENCE_CONFLICT or COMPATIBLE.
    """
    reasons: set[str] = set()
    status = NOT_USABLE
    kinds: set[str] = set()
    count = 0
    event_status = "INVALID_REFERENCE"
    expected = _aware_utc(cutoff)
    temporal = projection.get("temporal_projection") or {}
    section = projection.get("event_evidence") or {}
    rows = section.get("items") or []

    if (
        expected is None
        or projection.get("code") != code
        or projection.get("market") != market
        or _aware_utc(projection.get("decision_cutoff")) != expected
        or temporal.get("mode") != "SYSTEM_OBSERVED_AS_OF"
        or temporal.get("decision_cutoff") != projection.get("decision_cutoff")
        or not isinstance(rows, list)
        or projection.get("governance", {}).get("claim_scope")
        != "REFERENCE_CONTEXT_AS_OF_ONLY"
    ):
        reasons.add("P6_REFERENCE_IDENTITY_OR_ASOF_INVALID")
    else:
        event_status = str(section.get("status") or "UNKNOWN")
        if event_status == "EVIDENCE_BLOCKED":
            reasons.add("P6_EVENT_INTEGRITY_BLOCKED")
        elif event_status in {"REFERENCE_AVAILABLE", "REFERENCE_LIMITED"}:
            if not rows:
                reasons.add("P6_REFERENCE_ITEMS_MISSING")
            else:
                for item in rows:
                    if not isinstance(item, dict):
                        reasons.add("P6_REFERENCE_ITEM_INVALID")
                        break
                    if (
                        _aware_utc(item.get("available_at")) is None
                        or _aware_utc(item.get("assessment_as_of")) is None
                        or _aware_utc(item.get("available_at")) > expected
                        or _aware_utc(item.get("assessment_as_of")) > expected
                        or item.get("quality_state") not in {"USABLE", "LIMITED"}
                        or item.get("revision_state") not in {"ORIGINAL", "CORRECTED"}
                    ):
                        reasons.add("P6_REFERENCE_TIME_OR_QUALITY_INVALID")
                        break
                    sources = item.get("source_kinds")
                    if not isinstance(sources, list) or not sources:
                        reasons.add("P6_REFERENCE_SOURCE_INVALID")
                        break
                    kinds.update(str(source) for source in sources)
                if not reasons:
                    status = UNCERTAIN
                    count = len(rows)
                    reasons.add("P6_REFERENCE_NOT_INDEPENDENT_CONFLICT_ASSESSMENT")
        elif event_status in {"NO_VALIDATED_EVIDENCE", "NO_OBSERVED_ENTITY_BY_CUTOFF"}:
            status = NO_EVIDENCE
            reasons.add("P6_NO_OBSERVED_REFERENCE_BY_CUTOFF")
        else:
            reasons.add("P6_EVENT_REFERENCE_STATUS_UNSUPPORTED")

    # An event's presence and its AI-transmission rights are separate questions.
    # Existing Naver and OpenDART policies explicitly disable AI_TRANSFORM.
    for kind in sorted(kinds):
        try:
            policy = policy_for_event_source(
                kind,
                provider_kind=naver_provider_kind if kind == "NAVER_NEWS" else None,
            )
            if not policy.allows(EvidenceCapability.AI_TRANSFORM):
                reasons.add("P6_SOURCE_AI_USE_NOT_APPROVED")
        except EventEvidenceContractError:
            reasons.add("P6_SOURCE_POLICY_UNVERIFIED")
    return {
        "status": status,
        "reason_codes": sorted(reasons),
        "event_reference_status": event_status,
        "reference_count": count,
        "source_kinds": sorted(kinds),
        "ai_input_rights": "NOT_APPROVED",
        "independent_conflict_proven": False,
        "review_needed": False,
        "projection_hash": projection.get("projection_hash") if status != NOT_USABLE else None,
    }


def inspect_frozen_event_reference(
    simulation_db: Path, *, capture_id: str, sample_index: int,
    naver_provider_kind: str | None = None,
) -> dict[str, Any]:
    """One exact sample, canonical COMPLETE only, no network or DB mutations."""
    if not isinstance(capture_id, str) or not 0 < len(capture_id) <= 200:
        raise ValueError("P6_CAPTURE_ID_INVALID")
    if type(sample_index) is not int or not 0 <= sample_index <= 499:
        raise ValueError("P6_SAMPLE_INDEX_INVALID")

    pairs = load_frozen_candidates(Path(simulation_db), capture_id=capture_id, limit=500)
    match = next(
        ((capture, sample) for capture, sample in pairs
         if int(sample["sample_index"]) == sample_index),
        None,
    )
    if match is None:
        raise ValueError("P6_SAMPLE_NOT_FOUND")
    capture, sample = match
    report = _base(capture, sample)
    if sample["action"] != "ENTRY_CANDIDATE":
        report["reason_codes"] = ["P6_NOT_ENTRY_CANDIDATE"]
        return report

    # Capture creation is the only known independent local observation cutoff,
    # NOT proof of original market publication or scanner signal-date availability.
    cutoff = _aware_utc(capture.get("created_at"))
    if cutoff is None:
        report["reason_codes"] = ["P6_CAPTURE_CUTOFF_UNVERIFIED"]
        return report
    report["decision_cutoff"] = cutoff
    try:
        projection = EventEvidenceAsOfReader(Path(simulation_db)).stock_reference_as_of(
            str(sample["ticker"]), str(sample["market"]), cutoff, limit=8,
        )
    except EventEvidenceContractError as exc:
        report["reason_codes"] = [exc.code]
        return report

    report.update(classify_event_reference(
        projection, code=str(sample["ticker"]), market=str(sample["market"]),
        cutoff=cutoff, naver_provider_kind=naver_provider_kind,
    ))
    return report
