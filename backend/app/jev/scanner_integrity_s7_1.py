"""S7.1 independent integrity checks for immutable Scanner snapshots.

Diagnostics are non-authoritative: never substitute for S3 strict projection,
invent missing rankings, change a capture or enable a real TypeSafe provider.
"""
from __future__ import annotations

from datetime import date
import json
from typing import Any

from app.jev.decision_reviewer_offline import (
    BLOCKED_RISK_STATUSES, DecisionReviewContractError,
    build_scanner_review_input,
)
from app.strategy.semantic_identity_bridge import ENGINE_VERIFIED_SOURCE
from app.strategy.semantic_policy_provenance import VERIFIED_POLICY
from app.strategy.semantic_source_v2 import verify_semantic_source_v2

VERSION = "JEV_ACT2_S7_1_INTEGRITY_V1"

EXPLAIN = {
    "RANK_MISSING": "저장 순위 또는 원본 Scanner 순위를 확인할 수 없습니다.",
    "RANK_VALUE_MISMATCH": "저장 순위와 원본 Scanner 순위가 서로 다릅니다.",
    "RANK_TYPE_INVALID": "추천 순위가 올바른 양의 정수가 아닙니다.",
    "RANK_REPRO_CONFLICT": "원본 Snapshot의 두 순위 표현이 충돌합니다.",
    "STRATEGY_IDENTITY_MISSING": "최상위 전략 버전 또는 정의 해시가 없습니다.",
    "STRATEGY_IDENTITY_MISMATCH": "원본 전략 버전과 의미 분석용 전략 버전이 다릅니다.",
    "STRATEGY_DERIVATION_UNVERIFIED": "레거시 전략의 유도된 식별 정보를 충분히 입증하지 못했습니다.",
    "LEGACY_DERIVED_IDENTITY": "레거시 전략의 별도 유도 식별 정보는 있으나 원본에는 없습니다.",
    "POLICY_PROVENANCE_UNVERIFIED": "실행 당시 Selection Policy 연결 증거가 부족합니다.",
    "POLICY_PIN_MISMATCH": "실행 요청과 Selection Policy의 식별 정보가 일치하지 않습니다.",
    "SEMANTIC_SOURCE_MISSING": "조건의 의미 분석 원본이 없습니다.",
    "ENGINE_EVIDENCE_INCOMPLETE": "실제 엔진 통과 조건 증거가 부족합니다.",
    "DATE_MISSING": "추천 당시의 날짜 근거가 누락되었습니다.",
    "DATE_MISMATCH": "추천 시점과 원본 데이터 날짜가 일치하지 않습니다.",
    "RISK_INFORMATION_INVALID": "위험 상태 정보가 누락되거나 형식이 맞지 않습니다.",
    "RISK_BLOCKED_OUT_OF_SCOPE": "원래 위험 차단된 후보이므로 평가 대상이 아닙니다.",
    "S3_CONTRACT_UNSATISFIED": "기존 엄격한 JEV 입력 계약을 통과하지 못했습니다.",
}


def _iso(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except (ValueError, TypeError):
        return False


def _item(status: str, code: str | None = None, **details: Any) -> dict[str, Any]:
    return {
        "status": status,
        "code": code,
        "message": EXPLAIN.get(code, code) if code else None,
        **details,
    }


def assess_frozen_candidate(
    capture: dict[str, Any], sample: dict[str, Any],
) -> dict[str, Any]:
    """Run independent diagnostics. Never modify input or historical data."""
    if sample.get("action") != "ENTRY_CANDIDATE":
        return {
            "version": VERSION, "category": "REFERENCE_ONLY",
            "rank": _item("NOT_APPLICABLE"),
            "strategy": _item("NOT_APPLICABLE"),
            "policy": _item("NOT_APPLICABLE"),
            "engine": _item("NOT_APPLICABLE"),
            "dates": _item("NOT_APPLICABLE"),
            "risk": _item("NOT_APPLICABLE"),
            "strict_s3": _item("NOT_APPLICABLE"),
            "codes": ["NOT_ENTRY_CANDIDATE"],
            "locally_validated": False,
            "external_provider_eligible": False,
        }
    snap = sample.get("snapshot")
    if not isinstance(snap, dict):
        raise DecisionReviewContractError("S7_SNAPSHOT_INVALID")
    issues: list[str] = []
    checks: dict[str, dict[str, Any]] = {}

    priority = snap.get("priority")
    snap_rank = priority.get("rank") if isinstance(priority, dict) else None
    stored_rank = sample.get("rank")
    direct_rank = snap.get("rank")
    snap_valid = type(snap_rank) is int and snap_rank > 0
    stored_valid = type(stored_rank) is int and stored_rank > 0
    if (
        direct_rank is not None and snap_rank is not None
        and str(direct_rank) != str(snap_rank)
    ):
        rank_code = "RANK_REPRO_CONFLICT"
    elif snap_rank is None or stored_rank is None:
        rank_code = "RANK_MISSING"
    elif not snap_valid or not stored_valid:
        rank_code = "RANK_TYPE_INVALID"
    elif stored_rank != snap_rank:
        rank_code = "RANK_VALUE_MISMATCH"
    else:
        rank_code = None
    checks["rank"] = _item(
        "PASS" if rank_code is None else "FAIL", rank_code,
        stored=stored_rank, snapshot_priority=snap_rank,
        snapshot_direct=direct_rank,
        # The writer's scanner_repro_candidate_key() returns an empty
        # identity when rank is absent or two representations conflict.
        writer_rank_key_available=(
            snap_valid and
            (direct_rank is None or str(direct_rank) == str(snap_rank))
        ),
    )
    if rank_code:
        issues.append(rank_code)

    policy = snap.get("semantic_policy_provenance")
    policy = policy if isinstance(policy, dict) else {}
    try:
        request = capture.get("request")
        if not isinstance(request, dict):
            request = json.loads(capture.get("request_json") or "{}")
    except (ValueError, TypeError):
        request = None
    if (
        not isinstance(request, dict)
        or policy.get("status") != VERIFIED_POLICY
        or not policy.get("policy_id") or not policy.get("policy_hash")
    ):
        policy_code = "POLICY_PROVENANCE_UNVERIFIED"
    elif (
        request.get("selection_policy_id") != policy.get("policy_id")
        or request.get("selection_policy_hash") != policy.get("policy_hash")
    ):
        policy_code = "POLICY_PIN_MISMATCH"
    else:
        policy_code = None
    checks["policy"] = _item(
        "PASS" if not policy_code else "FAIL", policy_code,
        source=policy.get("policy_source"),
        policy_id=policy.get("policy_id"),
    )
    if policy_code:
        issues.append(policy_code)

    source = snap.get("semantic_source_v2")
    good, semantic_reason = verify_semantic_source_v2(source)
    if not good:
        engine_code = semantic_reason or "SEMANTIC_SOURCE_MISSING"
    else:
        evidence = snap.get("semantic_condition_evidence")
        evidence = evidence if isinstance(evidence, dict) else {}
        rows = evidence.get("items")
        items = source.get("conditions", {}).get("items")
        if (
            (source.get("readiness") or {}).get("q2_status") != "COMPLETE"
            or not isinstance(rows, list) or not rows
            or not isinstance(items, list) or len(rows) != len(items)
            or any(
                not isinstance(x, dict) or x.get("status") != "PASS"
                or not x.get("source_condition") or not x.get("condition_id")
                for x in rows
            )
            or {r["source_condition"] for r in rows}
            != {i.get("source_condition") for i in items}
        ):
            engine_code = "ENGINE_EVIDENCE_INCOMPLETE"
        else:
            engine_code = None
    checks["engine"] = _item("PASS" if not engine_code else "FAIL", engine_code)
    if engine_code:
        issues.append(engine_code)

    source_strategy = source.get("strategy") if isinstance(source, dict) else None
    source_strategy = source_strategy if isinstance(source_strategy, dict) else {}
    derived = snap.get("semantic_strategy_identity")
    derived = derived if isinstance(derived, dict) else {}
    version = snap.get("strategy_version_id")
    definition_hash = snap.get("strategy_definition_hash")
    sv = source_strategy.get("strategy_version_id")
    sh = source_strategy.get("strategy_definition_hash")
    if version and definition_hash and version == sv and definition_hash == sh:
        strategy_status, strategy_code = "PASS", None
    elif version or definition_hash:
        strategy_status, strategy_code = "FAIL", "STRATEGY_IDENTITY_MISMATCH"
    elif (
        policy_code is None and engine_code is None
        and policy.get("policy_source") == "LEGACY_CURRENT_10_FALLBACK"
        and derived.get("source") == ENGINE_VERIFIED_SOURCE
        and derived.get("strategy_key") == sample.get("strategy")
        and derived.get("strategy_version_id")
        and derived.get("strategy_definition_hash")
        and sv == derived.get("strategy_version_id")
        and sh == derived.get("strategy_definition_hash")
        and derived.get("selection_policy_id") == policy.get("policy_id")
        and derived.get("selection_policy_hash") == policy.get("policy_hash")
    ):
        strategy_status, strategy_code = "LEGACY_DERIVED", "LEGACY_DERIVED_IDENTITY"
    elif sv or sh or derived:
        strategy_status, strategy_code = "FAIL", "STRATEGY_DERIVATION_UNVERIFIED"
    else:
        strategy_status, strategy_code = "FAIL", "STRATEGY_IDENTITY_MISSING"
    checks["strategy"] = _item(
        strategy_status, strategy_code,
        baseline_version=version, semantic_version=sv,
        semantic_identity_source=derived.get("source"),
    )
    if strategy_code:
        issues.append(strategy_code)

    signal = sample.get("signal_date")
    original = snap.get("data_date")
    actual = capture.get("actual_data_date")
    if not _iso(signal) or not _iso(original) or (actual and not _iso(actual)):
        date_code = "DATE_MISSING"
    elif signal != original or (actual and signal != actual):
        date_code = "DATE_MISMATCH"
    else:
        date_code = None
    checks["dates"] = _item(
        "PASS" if not date_code else "FAIL", date_code,
        signal=signal, snapshot_data_date=original, actual_data_date=actual,
    )
    if date_code:
        issues.append(date_code)

    risk = snap.get("risk")
    guide = snap.get("entry_risk_guide")
    if (
        not isinstance(risk, dict)
        or not isinstance(risk.get("status"), str)
        or not risk.get("status")
        or not isinstance(risk.get("warning"), bool)
        or not isinstance(guide, dict)
    ):
        risk_code = "RISK_INFORMATION_INVALID"
    elif risk["status"].upper() in BLOCKED_RISK_STATUSES or (
        isinstance(guide.get("action"), dict)
        and guide["action"].get("status") == "RISK_BLOCKED"
    ):
        risk_code = "RISK_BLOCKED_OUT_OF_SCOPE"
    else:
        risk_code = None
    checks["risk"] = _item("PASS" if not risk_code else "FAIL", risk_code)
    if risk_code:
        issues.append(risk_code)

    try:
        projection = build_scanner_review_input(
            capture, sample, protocol_id=VERSION,
        )
        if projection["status"] == "OFFLINE_INSPECTABLE_ONLY":
            strict_code = None
        else:
            strict_code = projection.get("reason_code") or "S3_CONTRACT_UNSATISFIED"
    except DecisionReviewContractError as exc:
        strict_code = exc.code
    checks["strict_s3"] = _item(
        "PASS" if strict_code is None else "FAIL", strict_code,
    )
    if strict_code:
        issues.append(strict_code)

    # A proven legacy-only derived strategy is diagnostically limited:
    # S3 is *supposed* to reject its missing original version. Do not
    # mark it as fully validated or bypass that strict contract.
    independent_failures = any(
        item["status"] == "FAIL"
        for key, item in checks.items() if key != "strict_s3"
    )
    if (
        not independent_failures
        and strategy_status == "LEGACY_DERIVED"
        and strict_code == "STRATEGY_IDENTITY_MISMATCH"
    ):
        category = "LEGACY_LIMITED"
    elif not independent_failures and strict_code is None:
        category = "LOCAL_VALIDATED"
    else:
        category = "INVALID"
    return {
        "version": VERSION, "category": category,
        **checks,
        "codes": sorted(set(issues)),
        "locally_validated": category == "LOCAL_VALIDATED",
        "external_provider_eligible": False,
    }
