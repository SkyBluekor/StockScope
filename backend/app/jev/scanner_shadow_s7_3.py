"""S7.3: real Scanner evidence -> local JEV Shadow packet, fail-closed preflight.

Unlike S5/S6, these are real captured market-derived facts. This module has
NO network/client/credential import, and does not accept a broad approval flag
as a substitute for legal transmission rights or exact evidence availability.
A future reviewed provider runner must consume independently verified rights,
timestamp and model-approval proofs; none exist in this release.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any

from app.horizon import resolve_horizon_context
from app.jev.decision_reviewer_offline import (
    ALLOWED_DECISIONS, DecisionReviewContractError,
)
from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
from app.prospective.models import digest_json
from app.strategy.semantic_identity_bridge import (
    ENGINE_CONDITION_SOURCE, ENGINE_VERIFIED_SOURCE,
)

VERSION = "JEV_ACT2_S7_3_REAL_SHADOW_PREP_V1"
PACKET_VERSION = "JEV_S7_3_REAL_LOCAL_PACKET_V1"
QUESTION_VERSION = "JEV_S7_3_REAL_REVIEW_QUESTION_V1"
SOURCE_TIME_PROOF = "SOURCE_RELEASE_TIMESTAMP_UNVERIFIED"
SCOPE = "REAL_SCANNER_SHADOW_LOCAL_ONLY"
MAX_ATTEMPTS = 5
MAX_TOTAL_RESERVATION_USD = Decimal("0.05")
MAX_PER_ATTEMPT_RESERVATION_USD = Decimal("0.01")
# Real trading/market input has no approved grant/rights manifest. In
# particular, this constant cannot be changed by a CLI option or user flag.
REAL_MARKET_PROVIDER_ENABLED = False
QUESTIONS = {
    "review_decision": {
        "type": "choice",
        "instructions": (
            "Review the supplied Scanner conditions and risk signals ONLY. "
            "Choose PASS_THROUGH if evidence is consistent, REVIEW_REQUIRED "
            "if an explicit material contradiction is supplied, or ABSTAIN "
            "if required evidence is insufficient or ambiguous. No returns, "
            "price prediction, trading advice, or invented facts."
        ),
        "criteria": {
            "PASS_THROUGH": "No explicit material contradiction in supplied facts.",
            "REVIEW_REQUIRED": "Specific supplied evidence materially conflicts.",
            "ABSTAIN": "Insufficient, unavailable or unresolved conflicting evidence.",
        },
    }
}
QUESTION_HASH = digest_json({"version": QUESTION_VERSION, "questions": QUESTIONS})

REASONS_KO = {
    "NOT_ENTRY_CANDIDATE": "실제 진입 후보가 아닙니다.",
    "LOCAL_INTEGRITY_NOT_VERIFIED": "원본 후보 정합성 검증을 통과하지 못했습니다.",
    "SOURCE_RELEASE_TIME_UNVERIFIED": "원천 정보가 외부에 공개된 정확한 시각이 확인되지 않았습니다.",
    "SOURCE_RIGHTS_UNVERIFIED": "원천 자료와 파생 신호의 외부 AI 전송 권한이 확인되지 않았습니다.",
    "HORIZON_NUMERIC_POLICY_NOT_APPROVED": "투자 기간 수치 정책이 승인되지 않았습니다.",
    "LEGACY_HORIZON_UNDEFINED": "추천 당시 투자 기간이 정의되지 않았습니다.",
    "REAL_MARKET_PROVIDER_NOT_AUTHORIZED": "실제 종목 TypeSafe 전송 기능이 승인·활성화되지 않았습니다.",
    "PINNED_MODEL_AND_BILLING_NOT_VERIFIED": "실제 모델 버전과 계정별 요금이 검증되지 않았습니다.",
    "EXPLICIT_EXECUTION_APPROVAL_MISSING": "이 실험의 정확한 대상·모델·비용에 대한 별도 실행 승인이 없습니다.",
    "RETROSPECTIVE_CAPTURE": "추천 기준일 이후에 생성된 기록이므로 당시 예측 성능으로 평가할 수 없습니다.",
    "SOURCE_TIME_INCONSISTENT": "입력 근거의 시점 관계가 유효하지 않습니다.",
}


def _candidate_identity(capture: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "capture_id": capture["id"],
        "sample_index": sample["sample_index"],
        "snapshot_hash": sample["snapshot_hash"],
        "signal_date": sample["signal_date"],
        "ticker": sample.get("ticker"),
        "name": sample.get("name"),
    }


def _valid_aware_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _historical_capture_status(capture: dict[str, Any], sample: dict[str, Any]) -> str:
    completed = _valid_aware_time(capture.get("completed_at"))
    try:
        signal = date.fromisoformat(sample["signal_date"])
    except (TypeError, ValueError):
        return "TIME_UNVERIFIED"
    if completed is None:
        return "TIME_UNVERIFIED"
    return "RETROSPECTIVE_CAPTURE" if completed.date() > signal else "TEMPORAL_ORDER_UNVERIFIED"


def _local_packet(capture: dict[str, Any], sample: dict[str, Any],
                  category: str) -> dict[str, Any]:
    snapshot = sample["snapshot"]
    semantic = snapshot["semantic_source_v2"]
    policy = snapshot["semantic_policy_provenance"]
    engine = snapshot["semantic_condition_evidence"]
    strategy_semantic = semantic["strategy"]
    strategy_derived = snapshot.get("semantic_strategy_identity")
    if category == "LEGACY_LIMITED":
        if (
            snapshot.get("strategy_version_id") is not None
            or snapshot.get("strategy_definition_hash") is not None
            or not isinstance(strategy_derived, dict)
            or strategy_derived.get("source") != ENGINE_VERIFIED_SOURCE
        ):
            raise DecisionReviewContractError("S7_3_LEGACY_ORIGIN_MISMATCH")
    evidence = []
    # The local contract transfers only independently checked condition
    # meanings; these remain real market-derived *restricted* information.
    items = semantic.get("conditions", {}).get("items")
    if not isinstance(items, list) or not items:
        raise DecisionReviewContractError("S7_3_ENGINE_ITEMS_MISSING")
    proofs = engine.get("items")
    if not isinstance(proofs, list) or len(proofs) != len(items):
        raise DecisionReviewContractError("S7_3_ENGINE_PASS_PROOF_MISSING")
    if (
        category == "LEGACY_LIMITED"
        and (
            engine.get("source") != ENGINE_CONDITION_SOURCE
            or engine.get("strategy_key") != sample["strategy"]
        )
    ):
        raise DecisionReviewContractError("S7_3_ENGINE_PASS_PROOF_MISMATCH")
    # The semantic mapper issues *its own* condition-01/condition-02 IDs,
    # whereas the Scanner repro audit carries original engine condition IDs.
    # They represent distinct ID namespaces; source_condition is the shared
    # contract key. Require a strict one-to-one bijection, a separate unique
    # nonempty ID in each namespace and actual PASS for each source.
    semantic_sources: list[str] = []
    semantic_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise DecisionReviewContractError("S7_3_ENGINE_ITEM_INVALID")
        source = item.get("source_condition")
        cid = item.get("condition_id")
        if (
            not isinstance(source, str) or not source.strip()
            or not isinstance(cid, str) or not cid.strip()
            or not isinstance(item.get("observed_meaning"), str)
            or not item["observed_meaning"].strip()
        ):
            raise DecisionReviewContractError("S7_3_ENGINE_ITEM_INVALID")
        semantic_sources.append(source)
        semantic_ids.append(cid)
    if (
        len(set(semantic_sources)) != len(items)
        or len(set(semantic_ids)) != len(items)
    ):
        raise DecisionReviewContractError("S7_3_ENGINE_PASS_PROOF_MISMATCH")
    proof_by_source: dict[str, dict[str, Any]] = {}
    proof_ids: set[str] = set()
    for proof in proofs:
        if not isinstance(proof, dict):
            raise DecisionReviewContractError("S7_3_ENGINE_PASS_PROOF_MISMATCH")
        source = proof.get("source_condition")
        cid = proof.get("condition_id")
        if (
            proof.get("status") != "PASS"
            or not isinstance(source, str) or not source.strip()
            or not isinstance(cid, str) or not cid.strip()
            or source in proof_by_source or cid in proof_ids
        ):
            raise DecisionReviewContractError("S7_3_ENGINE_PASS_PROOF_MISMATCH")
        proof_by_source[source] = proof
        proof_ids.add(cid)
    if set(proof_by_source) != set(semantic_sources):
        raise DecisionReviewContractError("S7_3_ENGINE_PASS_PROOF_MISMATCH")
    for n, item in enumerate(items):
        # Engine PASS is associated by the verified original condition name,
        # never by assuming two independently generated IDs are identical.
        proof = proof_by_source[item["source_condition"]]
        evidence.append({
            "id": f"condition-{n+1}", "source": "SCANNER_ENGINE_DERIVED",
            "statement": item["observed_meaning"],
            "source_available_at": None, "source_release_proof": SOURCE_TIME_PROOF,
            "external_transmission_rights": "UNVERIFIED",
        })
    risk = snapshot["risk"]
    evidence.append({
        "id": "risk-1", "source": "SCANNER_RISK_DERIVED",
        "statement": f"Scanner risk status={risk['status']}; warning={risk['warning']}.",
        "source_available_at": None, "source_release_proof": SOURCE_TIME_PROOF,
        "external_transmission_rights": "UNVERIFIED",
    })
    body = {
        "version": PACKET_VERSION,
        "review_scope": SCOPE,
        "question_hash": QUESTION_HASH,
        "source": {
            "capture_id": capture["id"],
            "sample_index": sample["sample_index"],
            "snapshot_hash": sample["snapshot_hash"],
            "scanner_version": capture.get("scanner_version"),
            "signal_date": sample["signal_date"],
            "known_to_system_at": capture.get("completed_at"),
            "source_available_at": None,
            "source_time_proof": SOURCE_TIME_PROOF,
        },
        "baseline": {
            "strategy": sample["strategy"],
            "entry_action": "ENTRY_CANDIDATE",
            "rank": sample["rank"],
            "conditions": {
                k: snapshot["conditions"].get(k) for k in ("passed", "total", "missing")
            },
            "risk": {
                "status": risk["status"], "warning": risk["warning"],
            },
            "strategy_identity": {
                "origin": "ORIGINAL" if category == "LOCAL_VALIDATED" else "LEGACY_DERIVED",
                "original_version": snapshot.get("strategy_version_id"),
                "original_definition_hash": snapshot.get("strategy_definition_hash"),
                "derived_version": (
                    strategy_semantic.get("strategy_version_id")
                    if category == "LEGACY_LIMITED" else None
                ),
                "derived_definition_hash": (
                    strategy_semantic.get("strategy_definition_hash")
                    if category == "LEGACY_LIMITED" else None
                ),
                "derived_evidence_source": (
                    strategy_derived.get("source") if category == "LEGACY_LIMITED" else None
                ),
            },
            "policy_id": policy["policy_id"],
            "policy_hash": policy["policy_hash"],
            "horizon_intent": capture.get("horizon_intent"),
            "horizon_policy_version": capture.get("horizon_policy_version"),
        },
        "evidence": evidence,
        "limitations": [
            "REAL_MARKET_DERIVED_DATA",
            "NO_SOURCE_RELEASE_TIMESTAMP_VERIFIED",
            "EXTERNAL_TRANSMISSION_UNVERIFIED",
            "NO_REAL_MARKET_JEV_MODEL_USE",
        ] + (["ORIGINAL_STRATEGY_IDENTITY_ABSENT"]
             if category == "LEGACY_LIMITED" else []),
    }
    body["input_hash"] = digest_json(body)
    return body


def prepare_shadow_candidate(capture: dict[str, Any],
                             sample: dict[str, Any]) -> dict[str, Any]:
    """Frozen actual candidate -> restricted LOCAL packet. No broker/API I/O."""
    if (
        capture.get("status") != "COMPLETE"
        or sample.get("capture_run_id") != capture.get("id")
        or not isinstance(sample.get("snapshot"), dict)
        or sample.get("snapshot_hash") != digest_json(sample["snapshot"])
    ):
        raise DecisionReviewContractError("S7_3_ORIGINAL_CAPTURE_INVALID")
    identity = _candidate_identity(capture, sample)
    integrity = assess_frozen_candidate(capture, sample)
    category = integrity["category"]
    temporal = _historical_capture_status(capture, sample)
    if category not in ("LOCAL_VALIDATED", "LEGACY_LIMITED"):
        return {
            "version": VERSION, "identity": identity, "category": category,
            "status": "REFERENCE_ONLY" if category == "REFERENCE_ONLY" else "LOCAL_HOLD",
            "reason_codes": integrity["codes"] or ["LOCAL_INTEGRITY_NOT_VERIFIED"],
            "packet": None, "temporal_status": temporal,
            "real_provider_eligible": False,
        }
    packet = _local_packet(capture, sample, category)
    return {
        "version": VERSION, "identity": identity, "category": category,
        "status": "LOCAL_PACKET_READY",
        "reason_codes": ["ORIGINAL_STRATEGY_IDENTITY_ABSENT"]
                        if category == "LEGACY_LIMITED" else [],
        "packet": packet,
        "packet_hash": packet["input_hash"],
        "temporal_status": temporal, "real_provider_eligible": False,
    }


def preflight_shadow_candidate(prepared: dict[str, Any]) -> dict[str, Any]:
    """No switch/flag/approval string can satisfy missing legal proof."""
    codes = []
    packet = prepared.get("packet")
    if prepared.get("status") != "LOCAL_PACKET_READY" or not isinstance(packet, dict):
        codes.append("LOCAL_INTEGRITY_NOT_VERIFIED")
    else:
        copied = dict(packet)
        supplied_hash = copied.pop("input_hash", None)
        if (
            supplied_hash != digest_json(copied)
            or supplied_hash != prepared.get("packet_hash")
            or packet.get("question_hash") != QUESTION_HASH
            or packet.get("version") != PACKET_VERSION
        ):
            codes.append("LOCAL_INTEGRITY_NOT_VERIFIED")
        else:
            source = packet["source"]
            evidence = packet["evidence"]
            # Do not use captured_at as proof of source release.
            if (
                source.get("source_time_proof") != "SOURCE_RELEASE_TIMESTAMP_VERIFIED"
                or not source.get("source_available_at")
                or not all(e.get("source_available_at") for e in evidence)
            ):
                codes.append("SOURCE_RELEASE_TIME_UNVERIFIED")
            if not all(e.get("external_transmission_rights") == "VERIFIED_GRANTED"
                       for e in evidence):
                codes.append("SOURCE_RIGHTS_UNVERIFIED")
            scope = resolve_horizon_context(packet["baseline"].get("horizon_intent"))
            if not scope.is_activatable:
                codes.append(
                    "LEGACY_HORIZON_UNDEFINED" if scope.is_legacy
                    else "HORIZON_NUMERIC_POLICY_NOT_APPROVED"
                )
            # Prevent caller from modifying packet to claim rights: impossible
            # without breaking hash; even a forged whole packet cannot enable
            # provider, as the reviewed rights authority is not implemented.
    if not REAL_MARKET_PROVIDER_ENABLED:
        codes.append("REAL_MARKET_PROVIDER_NOT_AUTHORIZED")
    codes.extend([
        "PINNED_MODEL_AND_BILLING_NOT_VERIFIED",
        "EXPLICIT_EXECUTION_APPROVAL_MISSING",
    ])
    if prepared.get("temporal_status") == "RETROSPECTIVE_CAPTURE":
        # A retrospective sample may still be inspected locally, but its
        # outcome CANNOT be counted as precommitted forward model performance.
        temporal_note = "RETROSPECTIVE_CAPTURE"
    else:
        temporal_note = prepared.get("temporal_status", "TIME_UNVERIFIED")
    codes = sorted(set(codes))
    return {
        "version": VERSION, "status": "PROVIDER_HOLD",
        "identity": prepared["identity"], "category": prepared["category"],
        "input_hash": prepared.get("packet_hash"),
        "temporal_status": temporal_note,
        "blocking_reasons": codes,
        "blocking_explanations": {
            code: REASONS_KO.get(code, code) for code in codes
        },
        "eligible_for_real_market_provider": False,
        "execution_approval_required": True,
        "actual_provider_calls": 0, "paid_cost_usd": "0",
        "real_choice": None, "economic_uplift_proven": False,
    }


def prepare_capture(simulation_db: Path, *, capture_id: str,
                    limit: int = 60, sample_index: int | None = None,
                    include_preflight: bool = False) -> dict[str, Any]:
    """Existing canonical capture loader + verified local packets only."""
    from app.jev.scanner_shadow_s7 import load_frozen_candidates

    if not capture_id:
        raise DecisionReviewContractError("S7_3_CAPTURE_ID_REQUIRED")
    if sample_index is not None and (
        type(sample_index) is not int or not 0 <= sample_index <= 500
    ):
        raise DecisionReviewContractError("S7_3_SAMPLE_INDEX_INVALID")
    rows = load_frozen_candidates(simulation_db, capture_id=capture_id, limit=limit)
    if sample_index is not None:
        rows = [(c, s) for c, s in rows if s["sample_index"] == sample_index]
        if not rows:
            raise DecisionReviewContractError("S7_3_SAMPLE_NOT_FOUND")
    prepared = [prepare_shadow_candidate(c, s) for c, s in rows]
    categories = {name: sum(p["category"] == name for p in prepared)
                  for name in ("LOCAL_VALIDATED", "LEGACY_LIMITED", "INVALID", "REFERENCE_ONLY")}
    reports = [preflight_shadow_candidate(p) for p in prepared] if include_preflight else []
    return {
        "version": VERSION,
        "status": "REAL_MARKET_PREFLIGHT_PROVIDER_HOLD"
                  if include_preflight else "LOCAL_PREPARATION_READY_PROVIDER_HOLD",
        "capture_id": rows[0][0]["id"] if rows else capture_id,
        "total_records": len(prepared),
        "entry_candidates": sum(p["category"] != "REFERENCE_ONLY" for p in prepared),
        "local_packets_ready": sum(p["status"] == "LOCAL_PACKET_READY" for p in prepared),
        "local_validated": categories["LOCAL_VALIDATED"],
        "legacy_limited": categories["LEGACY_LIMITED"],
        "invalid": categories["INVALID"],
        "references": categories["REFERENCE_ONLY"],
        "real_provider_eligible": 0,
        "real_provider_calls": 0,
        "records": reports if include_preflight else prepared,
    }


class S73PreflightJournal:
    """Append-only preflight evidence stored beside, not inside, S7 observations."""
    def __init__(self, path: Path):
        self.path = Path(path)

    def record(self, report: dict[str, Any]) -> dict[str, int]:
        if report.get("version") != VERSION or not isinstance(report.get("records"), list):
            raise DecisionReviewContractError("S7_3_JOURNAL_INPUT_INVALID")
        if report.get("real_provider_calls") != 0 or report.get("real_provider_eligible") != 0:
            raise DecisionReviewContractError("S7_3_PROVIDER_RECORD_FORBIDDEN")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS jev_s7_3_preflight (
                evidence_hash TEXT PRIMARY KEY,
                capture_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                snapshot_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS jev_s7_3_no_update
            BEFORE UPDATE ON jev_s7_3_preflight
            BEGIN SELECT RAISE(ABORT,'S7.3 preflight immutable'); END;
            CREATE TRIGGER IF NOT EXISTS jev_s7_3_no_delete
            BEFORE DELETE ON jev_s7_3_preflight
            BEGIN SELECT RAISE(ABORT,'S7.3 preflight immutable'); END;
            """)
            inserted = reused = 0
            for row in report["records"]:
                if (
                    row.get("version") != VERSION
                    or row.get("status") != "PROVIDER_HOLD"
                    or row.get("actual_provider_calls") != 0
                    or row.get("real_choice") is not None
                    or row.get("eligible_for_real_market_provider") is not False
                ):
                    raise DecisionReviewContractError("S7_3_JOURNAL_FORGED_PROVIDER")
                key = digest_json(row)
                ident = row["identity"]
                existing = conn.execute(
                    "SELECT 1 FROM jev_s7_3_preflight WHERE evidence_hash=?", (key,),
                ).fetchone()
                if existing:
                    reused += 1
                    continue
                conn.execute(
                    "INSERT INTO jev_s7_3_preflight "
                    "(evidence_hash,capture_id,sample_index,snapshot_hash,payload_json,created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (key, ident["capture_id"], ident["sample_index"],
                     ident["snapshot_hash"], json.dumps(row, ensure_ascii=False, sort_keys=True),
                     datetime.now(timezone.utc).isoformat()),
                )
                inserted += 1
        return {"inserted": inserted, "reused": reused, "provider_calls": 0}


def validate_shadow_choice_response(raw: dict[str, Any], *,
                                    requested_model: str,
                                    pinned_returned_model: str) -> dict[str, Any]:
    """Vendor typed response for *future* reviewed real provider path.

    Unlike synthetic S5/S6, rolling aliases are not treated as pinned.
    This validator does not perform a call and does not unlock provider use.
    """
    if (
        not re.fullmatch(r"jev-\d+\.\d+\.\d+(?:[-.][A-Za-z0-9]+)*", requested_model)
        or requested_model != pinned_returned_model
        or not isinstance(raw, dict)
        or raw.get("model") != pinned_returned_model
    ):
        raise DecisionReviewContractError("S7_3_MODEL_REVISION_UNVERIFIED")
    answers = raw.get("answers")
    if not isinstance(answers, dict) or set(answers) != {"review_decision"}:
        raise DecisionReviewContractError("S7_3_RESPONSE_INVALID")
    item = answers["review_decision"]
    if not isinstance(item, dict) or set(item) != {"type", "choice", "confidence", "probabilities"}:
        raise DecisionReviewContractError("S7_3_RESPONSE_INVALID")
    probs = item["probabilities"]
    if (
        item["type"] != "choice" or item["choice"] not in ALLOWED_DECISIONS
        or not isinstance(probs, dict) or set(probs) != ALLOWED_DECISIONS
        or type(item["confidence"]) not in (float, int)
        or not math.isfinite(item["confidence"])
        or not 0 <= item["confidence"] <= 1
        or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
               for v in probs.values())
        or abs(sum(probs.values()) - 1) > 0.02
        or probs[item["choice"]] != max(probs.values())
    ):
        raise DecisionReviewContractError("S7_3_RESPONSE_INVALID")
    usage = raw.get("usage")
    if (not isinstance(usage, dict) or set(usage) != {"input_tokens", "output_tokens"}
        or any(type(v) is not int or v < 0 for v in usage.values())):
        raise DecisionReviewContractError("S7_3_RESPONSE_INVALID")
    return {
        "execution_origin": "ACTUAL_PROVIDER_NOT_YET_ACTIVATED",
        "choice": item["choice"], "confidence": float(item["confidence"]),
        "probabilities": dict(probs), "usage": dict(usage),
        "model_requested": requested_model, "model_returned": pinned_returned_model,
        "model_identity_status": "PINNED_NAME_MATCH_ONLY",
        "model_reasoning_provided": False,
    }


class S73DisabledActualProvider:
    """Future actual-provider interface: fail before API key/HTTP/DB access."""
    async def submit(self, prepared: dict[str, Any], *,
                     owner_approval: Any = None, api_key: str | None = None,
                     model: str | None = None) -> dict[str, Any]:
        inspection = preflight_shadow_candidate(prepared)
        # These documented reservation rules are not an approval themselves:
        # 5 calls × $0.01 = $0.05, sequential, zero retries.
        assert MAX_ATTEMPTS * MAX_PER_ATTEMPT_RESERVATION_USD == MAX_TOTAL_RESERVATION_USD
        raise DecisionReviewContractError(
            "S7_3_REAL_PROVIDER_HOLD_" + inspection["status"]
        )
