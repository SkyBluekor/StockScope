"""S31-P actual captured Scanner candidate -> local TypeSafe JEV routing.

This is the first user-invokable path in Scanner for the *existing* V4 local
semantic engine. Local routing MAY find real semantic contradictions, but is
NOT a JEV model response. No provider, network, journal, settings, writes,
model billing, or implicit rights grant. Market-derived source stays local.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.prospective.models import digest_json
from app.jev.review_service import JevManualReviewService
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import route_typesafe_state_v4

VERSION = "JEV_ACT2_S31P_LOCAL_SCANNER_CHECK_V1"

MESSAGES: dict[str, tuple[str, str]] = {
    "LOCAL_MATCH": (
        "입력된 전략 근거 사이에 알려진 의미 충돌이 없어요.",
        "이는 가격 상승 예측이나 JEV 모델의 검토 결과가 아닙니다.",
    ),
    "LOCAL_CONFLICT": (
        "전략 근거 사이에서 로컬 의미 충돌이 발견됐어요.",
        "충돌한 전략 의미를 확인해야 합니다. AI가 투자 손익을 예측한 결과는 아닙니다.",
    ),
    "LOCAL_INCOMPLETE": (
        "전략의 의미 근거가 부족해 판단을 보류했어요.",
        "조건 정의·관계 등 누락된 자료를 확인하세요.",
    ),
    "LOCAL_AMBIGUOUS": (
        "전략 의미가 모호해 로컬 판단을 확정하지 못했어요.",
        "근거를 명확히 한 뒤 다시 점검하세요.",
    ),
    "RESIDUAL_SEMANTIC_REVIEW": (
        "로컬 검사만으로 해결하지 못한 의미 문제를 발견했어요.",
        "JEV 모델의 추가 검토가 유용할 수 있지만 실제 모델 호출은 비활성입니다.",
    ),
}


# S31-Q. Never backfill a missing period, reinterpret LONG as SHORT, or
# enable any provider path. Diagnostic provenance comes from the original
# Prospective capture metadata after verifying the candidate snapshot hash.
def _horizon_diagnostic(raw: Any) -> tuple[str, bool, str, str, str]:
    if raw == "SHORT":
        return ("SHORT", True, "LOCAL_V4_IN_SCOPE",
                "단기(SHORT)로 기록된 후보입니다.",
                "투자 기간 입력 조건은 충족했습니다. 이어서 전략 의미 근거를 확인합니다.")
    if raw == "MEDIUM":
        return ("MEDIUM", True, "LOCAL_V4_IN_SCOPE",
                "중기(MEDIUM)로 기록된 후보입니다.",
                "투자 기간 입력 조건은 충족했습니다. 이어서 전략 의미 근거를 확인합니다.")
    if raw == "LEGACY_UNSPECIFIED":
        return ("LEGACY_UNSPECIFIED", False, "LEGACY_HORIZON_UNSPECIFIED",
                "이전 Scanner 캡처에 투자 기간이 지정되지 않았어요.",
                "원본에 없던 기간을 임의로 채울 수 없습니다. 현재 일반 Scanner는 SHORT·MEDIUM을 "
                "명시한 새 분석도 기간 수치 정책 미승인으로 차단합니다. 사용자 설정 변경으로 "
                "해결되지 않으며 별도 정책 검증이 필요합니다. 기존 캡처는 그대로 둡니다.")
    if raw == "LONG":
        return ("LONG", False, "LONG_OUTSIDE_LOCAL_V4",
                "장기(LONG) 분석은 현재 로컬 V4 의미검사 범위가 아니에요.",
                "장기 전략을 단기·중기로 바꿔 판정하면 안 됩니다. 장기용 의미검사는 별도 검증이 필요하고, "
                "현재 일반 Scanner에서 명시적 투자 기간을 선택해 다시 분석하는 경로도 정책상 차단돼 있습니다.")
    return ("UNKNOWN", False, "CAPTURE_HORIZON_UNKNOWN",
            "저장된 분석의 투자 기간을 확인할 수 없어요.",
            "캡처의 원본 투자 기간 기록을 확인하세요. 기간을 자동으로 추정하거나 바꾸지 않습니다.")


def inspect_captured_candidate_local(
    simulation_db: Path,
    *,
    capture_id: str,
    sample_index: int,
    market: str,
    ticker: str,
) -> dict[str, Any]:
    """Read authentic local capture only, not client-provided candidate state."""
    response: dict[str, Any] = {
        "version": VERSION, "capture_id": capture_id,
        "sample_index": sample_index, "market": market, "ticker": ticker,
        "status": "HOLD", "reason_code": None, "local_semantic_status": None,
        "capture_horizon_intent": None, "capture_horizon_policy_version": None,
        "local_v4_horizon_supported": False,
        "horizon_diagnostic_status": "NOT_CHECKED",
        "check_stage": "REQUEST_VALIDATION",
        "next_action": "원본 캡처와 분석 입력 상태를 확인하세요.",
        "headline": "검토 근거를 확인할 수 없어요.",
        "explanation": "실제 모델 검토 결과는 없습니다.",
        "snapshot_hash": None,
        "provider_review_suggested_by_local_state": False,
        "provider_call_authorized": False,
        "rights_for_real_market_transmission_verified": False,
        "model_result_available": False,
        "baseline_candidate_changed": False,
        "review_kind": "LOCAL_SEMANTIC_CHECK_NOT_JEV_MODEL",
        "jev_model_calls": 0, "external_requests": 0,
        "orders": 0, "db_writes": 0,
    }
    if (
        not isinstance(capture_id, str) or not capture_id.strip()
        or not isinstance(sample_index, int) or isinstance(sample_index, bool)
        or sample_index < 0 or sample_index > 100
        or market not in {"KOSPI", "KOSDAQ"}
        or not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit()
    ):
        response["reason_code"] = "LOCAL_REVIEW_REQUEST_INVALID"
        return response

    response["check_stage"] = "CAPTURE_LOOKUP"
    service = JevManualReviewService(Path(simulation_db))
    sample, reference, error = service._load_sample(capture_id, sample_index)
    if error or sample is None:
        response["reason_code"] = error or "CAPTURE_SAMPLE_NOT_FOUND"
        return response
    if sample.get("market") != market or sample.get("ticker") != ticker:
        response["reason_code"] = "CAPTURE_CANDIDATE_IDENTITY_MISMATCH"
        return response
    response["check_stage"] = "CAPTURE_INTEGRITY"
    snapshot = sample.get("snapshot")
    original_hash = sample.get("snapshot_hash")
    if (not isinstance(snapshot, dict) or not isinstance(original_hash, str)
        or not original_hash or digest_json(snapshot) != original_hash
        or original_hash != reference.get("snapshot_hash")):
        response["reason_code"] = "CAPTURE_SNAPSHOT_HASH_MISMATCH"
        return response

    response["capture_id"] = str(reference.get("capture_id") or capture_id)
    response["snapshot_hash"] = reference.get("snapshot_hash")
    (captured_horizon, horizon_supported, horizon_status,
     horizon_headline, horizon_next) = _horizon_diagnostic(
        sample.get("horizon_intent")
    )
    response.update({
        "capture_horizon_intent": captured_horizon,
        "capture_horizon_policy_version": (
            sample.get("horizon_policy_version")
            if isinstance(sample.get("horizon_policy_version"), str)
            else None
        ),
        "local_v4_horizon_supported": horizon_supported,
        "horizon_diagnostic_status": horizon_status,
        "check_stage": "HORIZON_SCOPE",
    })
    try:
        local = route_typesafe_state_v4(sample)
    except (TypeSafeStateProjectionError, ValueError, KeyError, TypeError) as exc:
        # Only stable codes, never echo embedded strategy/market text to API.
        response["reason_code"] = (
            str(exc) if isinstance(exc, TypeSafeStateProjectionError)
            else "LOCAL_SEMANTIC_SOURCE_INVALID"
        )
        if response["reason_code"] == "OUT_OF_SCOPE_HORIZON":
            response["headline"] = horizon_headline
            response["explanation"] = (
                "실패 원인은 전략 조건 부족이 아니라, 저장된 투자 기간이 "
                "이 로컬 검사 범위에 해당하지 않기 때문입니다."
            )
            response["next_action"] = horizon_next
        elif response["reason_code"] == "OUT_OF_SCOPE_ACTION":
            response["check_stage"] = "ACTION_SCOPE"
            response["headline"] = "이 종목은 진입 후보용 의미검사 대상이 아니에요."
            response["explanation"] = "원본 Scanner의 분석 행동이 ENTRY_CANDIDATE가 아닙니다."
            response["next_action"] = "원본 후보 상태를 확인하세요. 임의로 진입 후보로 바꾸지 마세요."
        else:
            response["check_stage"] = "SEMANTIC_INPUT"
            response["headline"] = "이 후보의 전략 의미 근거를 검증할 수 없어요."
            response["explanation"] = "투자 기간 제한이 아니라 전략·조건 의미 근거를 확인해야 합니다."
            response["next_action"] = "원본 캡처의 전략 정의·조건 관계를 확인하세요."
        return response

    title, explanation = MESSAGES[local.local_status]
    response.update({
        "check_stage": "COMPLETE",
        "next_action": (
            "로컬 의미검사 결과를 참고하되, 외부 JEV 모델 검토나 "
            "현재의 신규 매수 허가로 사용하지 마세요."
        ),
        "status": "LOCAL_CHECK_COMPLETE",
        "reason_code": local.reason_code,
        "local_semantic_status": local.local_status,
        "headline": title, "explanation": explanation,
        "provider_review_suggested_by_local_state": local.provider_eligible,
    })
    return response
