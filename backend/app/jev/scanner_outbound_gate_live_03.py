"""LIVE-03: actual Scanner candidate outbound inventory; NEVER an authority to send.

This is a read-only, pre-transport inspection of frozen Scanner snapshots.
S7.4 describes *expected* producers, not authenticated per-row provenance.
No caller-supplied rights flags, hashes, signatures or receipts can create an
ALLOW.  Future LIVE-04 must require a separately vetted, trusted resolver and
one-time execution approval bound to the exact HTTP bytes before any request.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import httpx

from app.jev.scanner_eligibility_s8 import diagnose_candidate as diagnose_s8_candidate
from app.jev.scanner_eligibility_s8 import hash_local_outbound_candidate, REQUIRED_TIME_EVENTS
from app.jev.typesafe_provider import TYPESAFE_SYSTEM_ONE_URL
from app.jev.typesafe_questions_v4 import (
    JEV_TYPESAFE_QUESTION_SET_HASH_V4, build_typesafe_questions_v4,
)
from app.jev.typesafe_state_v4 import (
    JEV_TYPESAFE_PROJECTOR_HASH_V4, project_typesafe_state_v4,
)
from app.jev.typesafe_state import TypeSafeStateProjectionError

VERSION = "JEV_LIVE03_OUTBOUND_BOUNDARY_V1"
CANONICALIZATION = "STRICT_SORTED_JSON_UTF8_V1"
RECIPIENT = "TYPESAFE_SYSTEM_ONE"
PURPOSE = "SCANNER_RESIDUAL_RELATION_REVIEW"
DEFAULT_MODEL = "jev-1.14.0"  # pinned local candidate, not model/rights approval

# All V4 sections have to be inventoried, including the conditions that
# become natural-language statements.  Textual paraphrases inherit sources.
PARENT_CLASSES = {
    "strategy_intent": ("INTERNAL_STRATEGY_ORIGIN_UNVERIFIED",),
    "term_definitions": ("INTERNAL_CONCEPT_ORIGIN_UNVERIFIED",),
    "authored_relations": ("INTERNAL_RELATION_ORIGIN_UNVERIFIED",),
    "passed_condition_meanings": (
        "KRX_STOCK_DAILY", "KRX_INDEX_DAILY", "SCANNER_ENGINE_PASS",
    ),
    "questions": ("JEV_FROZEN_QUESTION_CONTRACT",),
    "model": ("TYPESAFE_MODEL_CONFIG",),
}
CONTRACT_SECTIONS = tuple(PARENT_CLASSES)
SENSITIVE_FRAGMENTS = (
    "authorization:", "bearer ", "jev_api_key", "krx_api_key",
    "dart_api_key", "kis_app_secret", "naver_client_secret",
)
UNKNOWN_EVIDENCE = (
    "SOURCE_RIGHTS_UNVERIFIED",
    "SOURCE_RELEASE_TIME_UNVERIFIED",
    "SOURCE_ORIGIN_UNVERIFIED",
    "REVISION_ASOF_UNPROVEN",
    "TYPESAFE_ACCOUNT_POLICY_UNVERIFIED",
    "RIGHTS_AUTHENTICITY_UNVERIFIED",
    "V4_OUTBOUND_PARENT_BINDING_UNVERIFIED",
    "EXECUTION_APPROVAL_NOT_GRANTED",
)


class OutboundGateError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _leaves(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{path}[{index}]")
    else:
        yield path


def _section(path: str) -> str:
    return path.partition(".")[0].split("[", 1)[0]


def _wire_body(state: dict[str, Any], model_id: str) -> dict[str, Any]:
    if (
        not isinstance(model_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", model_id)
        or model_id.upper() == "UNFROZEN"
    ):
        raise OutboundGateError("LIVE03_MODEL_NOT_PINNED")
    return {"state": state, "questions": build_typesafe_questions_v4(), "model": model_id}


def inspect_wire_body(body: dict[str, Any]) -> dict[str, Any]:
    """Examine the *httpx json= transport representation*, without sending.

    The sorted canonical hash and the actual httpx JSON bytes have different
    encodings. Never call the canonical hash the exact HTTP body digest.
    """
    try:
        canonical_hash = hash_local_outbound_candidate(body)
    except (ValueError, TypeError, KeyError) as exc:
        raise OutboundGateError("LIVE03_V4_WIRE_SHAPE_INVALID") from exc
    request = httpx.Request("POST", TYPESAFE_SYSTEM_ONE_URL, json=body)
    raw = request.content
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise OutboundGateError("LIVE03_HTTP_JSON_INVALID") from exc
    if decoded != body or not isinstance(body.get("model"), str):
        raise OutboundGateError("LIVE03_HTTP_BODY_CHANGED")
    if any(fragment in raw.decode("utf-8").lower() for fragment in SENSITIVE_FRAGMENTS):
        raise OutboundGateError("LIVE03_SENSITIVE_OUTBOUND_CONTENT")

    fields = []
    for path in _leaves(body):
        section = _section(path)
        # root "state" is a container; classify its descendants by V4 section.
        if section == "state":
            child = path.partition(".")[2].split(".", 1)[0].split("[", 1)[0]
            parent = PARENT_CLASSES.get(child)
        else:
            parent = PARENT_CLASSES.get(section)
        if parent is None:
            raise OutboundGateError("LIVE03_UNKNOWN_OUTBOUND_FIELD")
        fields.append({
            "path": path, "expected_parents": list(parent),
            "origin_verified": False,
            "rights_status": "UNVERIFIED" if section == "state" else "INTERNAL_CONTRACT_ONLY",
            "time_status": "UNKNOWN" if section == "state" else "NOT_APPLICABLE",
        })
    if len(fields) > 256:
        raise OutboundGateError("LIVE03_TOO_MANY_OUTBOUND_FIELDS")
    return {
        "canonicalization": CANONICALIZATION,
        "outbound_projection_hash": canonical_hash,
        "http_body_sha256": hashlib.sha256(raw).hexdigest(),
        "http_body_bytes": len(raw),
        "model_id": body["model"],
        "question_hash": JEV_TYPESAFE_QUESTION_SET_HASH_V4,
        "recipient": RECIPIENT,
        "endpoint": TYPESAFE_SYSTEM_ONE_URL,
        "method": "POST",
        "field_verdicts": fields,
        "field_count": len(fields),
        "all_actual_parent_revisions_verified": False,
        "body_was_transmitted": False,
    }


def verify_http_request_binding(
    audit: dict[str, Any], request: httpx.Request, *, expected_model: str,
) -> None:
    """Reusable future adapter guard: byte-exact and target-bound, not a grant.

    This proves request identity only; caller must independently verify
    rights and a one-use approval before invoking HTTP transport.
    """
    if not isinstance(request, httpx.Request) or not audit:
        raise OutboundGateError("LIVE03_HTTP_REQUEST_INVALID")
    if (
        request.method != "POST"
        or str(request.url) != TYPESAFE_SYSTEM_ONE_URL
        or audit.get("recipient") != RECIPIENT
        or audit.get("method") != "POST"
        or audit.get("endpoint") != TYPESAFE_SYSTEM_ONE_URL
        or audit.get("model_id") != expected_model
        or hashlib.sha256(request.content).hexdigest() != audit.get("http_body_sha256")
        or len(request.content) != audit.get("http_body_bytes")
    ):
        raise OutboundGateError("LIVE03_HTTP_BINDING_MISMATCH")
    try:
        payload = json.loads(request.content)
        actual_hash = hash_local_outbound_candidate(payload)
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise OutboundGateError("LIVE03_HTTP_BODY_INVALID") from exc
    if payload.get("model") != expected_model or actual_hash != audit.get("outbound_projection_hash"):
        raise OutboundGateError("LIVE03_HTTP_BINDING_MISMATCH")
    # A successful match is not approval to send.


def diagnose_outbound_candidate(
    capture: dict[str, Any], sample: dict[str, Any], *, model_id: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """No network, source refresh, evidence-file trust, writes or provider."""
    s8 = diagnose_s8_candidate(capture, sample)
    identity = s8["identity"]
    local = s8["v4_local_status"]
    skip = local in ("REFERENCE_ONLY", "SKIPPED_LOCAL")
    codes = set(s8["reason_codes"])
    wire = None
    if local == "LOCAL_V4_PROJECTABLE":
        try:
            projected = project_typesafe_state_v4({
                **sample, "horizon_intent": capture.get("horizon_intent"),
            })
            wire = inspect_wire_body(_wire_body(projected.state, model_id))
        except (TypeSafeStateProjectionError, OutboundGateError) as exc:
            codes.add(getattr(exc, "code", "LIVE03_WIRE_PROJECTION_FAILED"))
            wire = None
    if not skip:
        codes.update(UNKNOWN_EVIDENCE)
        if wire is None:
            codes.add("OUTBOUND_BODY_NOT_VERIFIABLE")
    decision = "NOT_APPLICABLE" if skip else "HOLD"

    # This read-only boundary does not accept a caller-supplied rights receipt.
    # An actual ALLOW needs RA01~RA10 from a separately trusted resolver.
    return {
        "version": VERSION,
        "identity": identity,
        "decision": decision,
        "data_eligibility": "NOT_APPLICABLE" if skip else "HOLD_UNVERIFIED",
        "execution_status": "NOT_AUTHORIZED",
        "evaluation_mode": "RETROSPECTIVE_RESEARCH_ONLY",
        "v4_local_status": local,
        "recipient": RECIPIENT,
        "purpose": PURPOSE,
        "requested_model": model_id,
        "wire_audit": wire,
        "wire_ready": wire is not None,
        "lineage_source": "S7_4_EXPECTED_PRODUCERS_ONLY",
        "rights_source": "S8_UNVERIFIED_ACCOUNT_AND_DERIVED_RIGHTS",
        "rights_verification": "NOT_VERIFIED",
        "time_events_required": list(REQUIRED_TIME_EVENTS),
        "time_authenticity": "UNVERIFIED",
        "trusted_rights_resolver": "NOT_CONFIGURED",
        "required_rights_checks": [f"RA{i:02}" for i in range(1, 11)],
        "reason_codes": sorted(codes),
        "provider_eligible": False,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }
