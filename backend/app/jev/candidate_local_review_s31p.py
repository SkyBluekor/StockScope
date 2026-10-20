"""S31-P actual captured Scanner candidate -> local TypeSafe JEV routing.

This is the first user-invokable path in Scanner for the *existing* V4 local
semantic engine. Local routing MAY find real semantic contradictions, but is
NOT a JEV model response. No provider, network, journal, settings, writes,
model billing, or implicit rights grant. Market-derived source stays local.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

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

    service = JevManualReviewService(Path(simulation_db))
    sample, reference, error = service._load_sample(capture_id, sample_index)
    if error or sample is None:
        response["reason_code"] = error or "CAPTURE_SAMPLE_NOT_FOUND"
        return response
    if sample.get("market") != market or sample.get("ticker") != ticker:
        response["reason_code"] = "CAPTURE_CANDIDATE_IDENTITY_MISMATCH"
        return response

    response["capture_id"] = str(reference.get("capture_id") or capture_id)
    response["snapshot_hash"] = reference.get("snapshot_hash")
    try:
        local = route_typesafe_state_v4(sample)
    except (TypeSafeStateProjectionError, ValueError, KeyError, TypeError) as exc:
        # Only stable codes, never echo embedded strategy/market text to API.
        response["reason_code"] = (
            str(exc) if isinstance(exc, TypeSafeStateProjectionError)
            else "LOCAL_SEMANTIC_SOURCE_INVALID"
        )
        response["headline"] = "이 후보는 로컬 JEV 의미검사 입력이 준비되지 않았어요."
        response["explanation"] = "원본 캡처의 전략 정의와 의미 근거를 확인하세요."
        return response

    title, explanation = MESSAGES[local.local_status]
    response.update({
        "status": "LOCAL_CHECK_COMPLETE",
        "reason_code": local.reason_code,
        "local_semantic_status": local.local_status,
        "headline": title, "explanation": explanation,
        "provider_review_suggested_by_local_state": local.provider_eligible,
    })
    return response
