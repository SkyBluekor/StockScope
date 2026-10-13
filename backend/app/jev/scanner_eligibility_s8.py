"""S8: read-only KRX source, rights and time eligibility for JEV V4.

Policy is deliberately non-authorizing. Public KRX terms are not account grants;
locally generated hashes or caller-supplied receipts do not prove permission.
No provider, credential, market API, runtime write, or source-data export.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_lineage_s7_4 import CONTRACT_REF, DEFAULT_SOURCE_PRODUCTS
from app.jev.scanner_shadow_s7 import load_frozen_candidates
from app.jev.scanner_v4_readiness_s7_5 import diagnose_candidate as diagnose_v4_candidate
from app.jev.typesafe_questions_v4 import build_typesafe_questions_v4

VERSION = "JEV_ACT2_S8_RIGHTS_TIME_ELIGIBILITY_V1"
KRX_TERMS_URL = "https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp"
KRX_TERMS_EFFECTIVE = "2025-12-26"
# The public OPEN API §11(2) restricts disclosing received information to third
# parties. Whether derived Scanner decisions can be processed by TypeSafe is NOT
# determined by that sentence: do not infer a license for derived information.
RIGHTS_ACTIONS = {
    "KRX_OPEN_API_RAW_THIRD_PARTY": "VERIFIED_PROHIBITED_PUBLIC_TERMS",
    "KRX_OPEN_API_DERIVED_TYPESAFE_AI": "UNVERIFIED",
    "TYPESAFE_ACCOUNT_PROCESSING_CONDITIONS": "UNVERIFIED",
}
REQUIRED_TIME_EVENTS = (
    "source_published_at", "source_available_at", "request_started_at",
    "retrieved_at", "known_to_system_at", "scanner_input_frozen_at",
)
NEXT_EVIDENCE = (
    "KRX: 실제 계정·주식/지수 상품의 승인서 및 적용 약관/별도 계약",
    "KRX: 조건 PASS·Risk·순위 등 파생정보를 TypeSafe에 전송·처리·보관할 수 있는지 공식 답변",
    "TypeSafe: 해당 계정의 보관·처리지역·로그·재위탁 조건과 적용 계약",
    "수집 경계: 사용된 개별 응답/revision의 digest·최초 획득·공개/가용 시각 증거",
    "Scanner: 동결 시각과 정확히 사용한 원천 revision·비교 모집단의 결합 증거",
)


def _aware(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("TIME_EVIDENCE_MISSING")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("TIME_EVIDENCE_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMEZONE_UNVERIFIED")
    return parsed.astimezone(timezone.utc)


def inspect_temporal_chain(events: dict[str, Any]) -> dict[str, Any]:
    """Check logical order only, NEVER source authenticity or a time grant.

    A valid observed sequence is not proof of first publication or the
    consumer's historical point-in-time input. No caller value can authorize.
    """
    if not isinstance(events, dict):
        raise ValueError("TIME_EVIDENCE_INVALID")
    parsed: dict[str, datetime] = {}
    codes: set[str] = set()
    for name in REQUIRED_TIME_EVENTS:
        raw = events.get(name)
        if raw is None:
            codes.add("SOURCE_TIME_EVENT_MISSING")
            continue
        try:
            parsed[name] = _aware(raw)
        except ValueError as exc:
            codes.add(str(exc))
    # The two receive events belong to one request. A retry/retrieval later
    # than the first known receipt needs its own event chain.
    for before, after in (
        ("source_published_at", "source_available_at"),
        ("source_available_at", "retrieved_at"),
        ("request_started_at", "retrieved_at"),
        ("retrieved_at", "known_to_system_at"),
        ("known_to_system_at", "scanner_input_frozen_at"),
    ):
        if before in parsed and after in parsed and parsed[before] > parsed[after]:
            codes.add("SOURCE_TIME_INCONSISTENT")
    # A subject binding and independently verified original events do not
    # exist in historical KRX rows; validation of order cannot manufacture it.
    if not events.get("revision_binding_verified"):
        codes.add("REVISION_ASOF_UNPROVEN")
    if not events.get("trusted_event_evidence_ref"):
        codes.add("SOURCE_TIME_AUTHENTICITY_UNVERIFIED")
    return {
        "sequence": "CONSISTENT_ONLY" if not codes else "INCOMPLETE_OR_INCONSISTENT",
        "reason_codes": sorted(codes),
        "authenticity_verified": False,
        "source_release_verified": False,
        "forward_asof_verified": False,
    }


def _validate_json_value(value: Any, depth: int = 0) -> None:
    if depth > 16:
        raise ValueError("OUTBOUND_BODY_DEPTH_EXCEEDED")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("OUTBOUND_BODY_NONFINITE")
        return
    if isinstance(value, list):
        if len(value) > 512:
            raise ValueError("OUTBOUND_BODY_TOO_LARGE")
        for item in value:
            _validate_json_value(item, depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 512 or any(not isinstance(key, str) for key in value):
            raise ValueError("OUTBOUND_BODY_INVALID")
        for item in value.values():
            _validate_json_value(item, depth + 1)
        return
    raise ValueError("OUTBOUND_BODY_INVALID")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("OUTBOUND_BODY_DUPLICATE_KEY")
        result[key] = value
    return result


def hash_local_outbound_candidate(body: dict[str, Any] | str) -> str:
    """Hash an exact syntactically-valid V4 body; NEVER grant transmission.

    Used for isolated synthetic/locally constructed comparisons only. The
    actual wire bytes and transport model binding are outside this gate.
    """
    if isinstance(body, str):
        if len(body.encode("utf-8")) > 32768:
            raise ValueError("OUTBOUND_BODY_TOO_LARGE")
        body = json.loads(
            body,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("OUTBOUND_BODY_NONFINITE")
            ),
        )
    if not isinstance(body, dict) or set(body) != {"state", "questions", "model"}:
        raise ValueError("OUTBOUND_BODY_INVALID")
    if not isinstance(body["state"], dict) or not isinstance(body["questions"], dict):
        raise ValueError("OUTBOUND_BODY_INVALID")
    if not body["questions"] or not isinstance(body["model"], str) or not body["model"].strip():
        raise ValueError("OUTBOUND_BODY_INVALID")
    if body["model"].strip().upper() == "UNFROZEN":
        raise ValueError("OUTBOUND_BODY_MODEL_UNFROZEN")
    # Reject non-JSON objects and nonfinite numbers before attempting any
    # semantic/contract comparisons on attacker-controlled structures.
    _validate_json_value(body)
    # A generic JSON object with a model string is not a TypeSafe V4 request.
    # This is strictly a shape/contract check, NOT a rights or wire approval.
    if body["questions"] != build_typesafe_questions_v4():
        raise ValueError("OUTBOUND_V4_QUESTION_CONTRACT_MISMATCH")
    if set(body["state"]) != {
        "strategy_intent", "term_definitions", "authored_relations",
        "passed_condition_meanings",
    }:
        raise ValueError("OUTBOUND_V4_STATE_SHAPE_INVALID")
    if (not isinstance(body["state"]["strategy_intent"], dict)
        or not isinstance(body["state"]["strategy_intent"].get("text"), str)
        or any(not isinstance(body["state"][key], list) or not body["state"][key]
               for key in ("term_definitions", "authored_relations", "passed_condition_meanings"))):
        raise ValueError("OUTBOUND_V4_STATE_SHAPE_INVALID")
    payload = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if len(payload) > 32768:
        raise ValueError("OUTBOUND_BODY_TOO_LARGE")
    return hashlib.sha256(payload).hexdigest()


def diagnose_candidate(capture: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    """Assess existing frozen data only. Neither public terms nor hash is a grant."""
    v4 = diagnose_v4_candidate(capture, sample)
    # S7.5 already performed the S7.3 preparation + lineage enumeration;
    # never rerun the source and confuse its Choice packet with a V4 wire audit.
    reference = v4["local_v4_status"] == "REFERENCE_ONLY"
    local_skip = v4["local_v4_status"] == "SKIPPED_LOCAL"
    needs_provider = not (reference or local_skip)
    blockers = set(v4["reason_codes"])
    if needs_provider:
        blockers.update({
            "SOURCE_RIGHTS_UNVERIFIED", "SOURCE_RELEASE_TIME_UNVERIFIED",
            "SOURCE_ORIGIN_UNVERIFIED", "REVISION_ASOF_UNPROVEN",
            "RIGHTS_AUTHENTICITY_UNVERIFIED", "TYPESAFE_ACCOUNT_POLICY_UNVERIFIED",
            "OUTBOUND_BODY_NOT_APPROVED",
        })
        if v4["lineage_analysis_status"] != "COMPLETE":
            blockers.add("LINEAGE_INCOMPLETE")
        if v4["s73_lineage_unclassified_fields"]:
            blockers.add("UNCLASSIFIED_OUTBOUND_FIELD")
        if v4["v4_outbound_lineage_status"] == "NOT_AUDITED":
            blockers.add("V4_OUTBOUND_LINEAGE_NOT_AUDITED")
        if not v4["v4_wire_contract_verified"]:
            blockers.add("V4_WIRE_CONTRACT_UNVERIFIED")
    return {
        "identity": v4["identity"],
        "category": v4["category"],
        "v4_local_status": v4["local_v4_status"],
        "v4_state_hash": v4["v4_state_hash"],
        "lineage_analysis_status": v4["lineage_analysis_status"],
        "lineage_field_count": v4["s73_lineage_field_count"],
        "unclassified_fields": v4["s73_lineage_unclassified_fields"],
        "v4_outbound_lineage_status": v4["v4_outbound_lineage_status"],
        "v4_wire_contract_verified": v4["v4_wire_contract_verified"],
        "source_origin_status": "NOT_APPLICABLE" if reference else "UNVERIFIED",
        "source_revision_status": "NOT_APPLICABLE" if reference else "UNVERIFIED",
        "publication_time_status": "NOT_APPLICABLE" if reference else "UNKNOWN",
        "acquisition_time_status": "NOT_APPLICABLE" if reference else "UNKNOWN",
        "rights_status": "NOT_APPLICABLE" if reference else "UNVERIFIED",
        "data_eligibility": "NOT_APPLICABLE" if not needs_provider else "HOLD_UNVERIFIED",
        "transmission_decision": (
            "NOT_APPLICABLE" if reference else ("NOT_REQUIRED" if local_skip else "NO_GO")
        ),
        "reason_codes": sorted(blockers),
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def diagnose_capture(
    simulation_db: Path, *, capture_id: str | None, limit: int = 60,
    sample_index: int | None = None,
) -> dict[str, Any]:
    if not capture_id:
        raise DecisionReviewContractError("S8_CAPTURE_ID_REQUIRED")
    if sample_index is not None and (
        type(sample_index) is not int or not 0 <= sample_index <= 500
    ):
        raise DecisionReviewContractError("S8_SAMPLE_INDEX_INVALID")
    pairs = load_frozen_candidates(simulation_db, capture_id=capture_id, limit=limit)
    if sample_index is not None:
        pairs = [(c, s) for c, s in pairs if s["sample_index"] == sample_index]
        if not pairs:
            raise DecisionReviewContractError("S8_SAMPLE_NOT_FOUND")
    records = [diagnose_candidate(c, s) for c, s in pairs]
    entry = [r for r in records if r["category"] != "REFERENCE_ONLY"]
    return {
        "version": VERSION,
        "status": "S8_SOURCE_RIGHTS_TIME_PROVIDER_HOLD",
        "capture_id": pairs[0][0]["id"] if pairs else capture_id,
        "total_records": len(records),
        "entry_candidates": len(entry),
        "reference_count": len(records) - len(entry),
        "v4_projectable_count": sum(r["v4_local_status"] == "LOCAL_V4_PROJECTABLE" for r in entry),
        "v4_outbound_lineage_unverified_count": sum(
            r["v4_outbound_lineage_status"] == "NOT_AUDITED" for r in entry
        ),
        "v4_local_skipped_count": sum(r["v4_local_status"] == "SKIPPED_LOCAL" for r in entry),
        "origin_unverified_count": sum(r["source_origin_status"] == "UNVERIFIED" for r in entry),
        "rights_unverified_count": sum(r["rights_status"] == "UNVERIFIED" for r in entry),
        "source_time_unverified_count": sum(r["publication_time_status"] == "UNKNOWN" for r in entry),
        "no_go_count": sum(r["transmission_decision"] == "NO_GO" for r in entry),
        "raw_disclosure_public_terms": RIGHTS_ACTIONS["KRX_OPEN_API_RAW_THIRD_PARTY"],
        "derived_typesafe_rights": RIGHTS_ACTIONS["KRX_OPEN_API_DERIVED_TYPESAFE_AI"],
        "rights_by_action": RIGHTS_ACTIONS.copy(),
        "source_products": [
            {"source_id": sid, "code_path_endpoint": endpoint, "product": name,
             "row_origin_verified": False}
            for sid, endpoint, name in DEFAULT_SOURCE_PRODUCTS
        ],
        "public_terms": {
            "url": KRX_TERMS_URL,
            "effective_date": KRX_TERMS_EFFECTIVE,
            "clause": "KRX_OPEN_API_11_2",
            "account_specific_approval_verified": False,
        },
        "next_evidence": list(NEXT_EVIDENCE),
        "contract_ref": CONTRACT_REF,
        "decision": (
            "NO_GO_CURRENT_REQUEST" if any(r["transmission_decision"] == "NO_GO" for r in entry)
            else ("NOT_REQUIRED" if entry else "NOT_APPLICABLE")
        ),
        "data_eligibility": (
            "HOLD_UNVERIFIED" if any(r["data_eligibility"] == "HOLD_UNVERIFIED" for r in entry)
            else "NOT_APPLICABLE"
        ),
        "records": records,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
    }
