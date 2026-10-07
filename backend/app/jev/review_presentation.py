from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.strategy.semantic_composition import (
    LOCAL_AMBIGUOUS,
    LOCAL_CONFLICT,
    LOCAL_INCOMPLETE,
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
)
from app.strategy.semantic_source_v2 import build_semantic_source_v2


AI_REVIEW_PRESENTATION_VERSION = "AI_REVIEW_PRESENTATION_V1"


def _unique_texts(values: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def build_candidate_ai_review_presentation(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Build user-facing AI-review preparation text without calling a provider."""

    try:
        source = build_semantic_source_v2(candidate)
    except Exception:
        source = {}

    composition = (
        source.get("local_semantic_composition")
        if isinstance(source, dict)
        else None
    )
    local_status = (
        str(composition.get("status") or "")
        if isinstance(composition, dict)
        else ""
    )
    conditions = (
        source.get("conditions")
        if isinstance(source, dict)
        else None
    )
    items = (
        list(conditions.get("items") or [])
        if isinstance(conditions, dict)
        else []
    )

    strengths = _unique_texts(
        [
            str(item.get("source_condition") or "")
            for item in items
            if isinstance(item, dict)
            and str(item.get("stance") or "") == "SUPPORTS"
        ],
        limit=3,
    )
    if not strengths:
        priority = candidate.get("priority")
        strengths = _unique_texts(
            [
                str(item)
                for item in (
                    list(priority.get("strengths") or [])
                    if isinstance(priority, dict)
                    else []
                )
            ],
            limit=3,
        )

    state = "NOT_READY"
    summary = "AI 보조 검토에 필요한 의미 정보를 준비하지 못했습니다."
    review_points: list[str] = []

    if local_status == LOCAL_MATCH:
        state = "LOCAL_COMPLETE"
        summary = "핵심 조건의 의미가 현재 전략 의도와 자연스럽게 맞습니다."
    elif local_status == RESIDUAL_SEMANTIC_REVIEW:
        state = "AI_REVIEW_CANDIDATE"
        summary = "전략 의미 관계 일부는 AI가 한 번 더 확인할 대상으로 남아 있습니다."
        review_points = [
            "조건 자체는 통과했지만 의미 관계를 한 번 더 확인할 부분이 남아 있습니다."
        ]
    elif local_status == LOCAL_CONFLICT:
        state = "LOCAL_CONFLICT"
        summary = "전략 조건 의미 사이에 로컬에서 확인 가능한 충돌이 있습니다."
        review_points = [
            "이미 기본 분석에서 의미 충돌을 확인해 별도 AI 호출이 필요하지 않습니다."
        ]
    elif local_status == LOCAL_AMBIGUOUS:
        state = "NOT_READY"
        summary = "같은 의미를 가리키는 조건 해석이 서로 엇갈립니다."
        review_points = [
            "내부 의미가 정리되기 전에는 AI에게 추측시키지 않습니다."
        ]
    elif local_status == LOCAL_INCOMPLETE:
        state = "NOT_READY"
        summary = "AI 보조 검토에 필요한 의미 정보가 아직 충분하지 않습니다."
        review_points = [
            "필수 의미 정보가 준비된 뒤에만 추가 검토할 수 있습니다."
        ]

    return {
        "version": AI_REVIEW_PRESENTATION_VERSION,
        "state": state,
        "summary": summary,
        "strengths": strengths,
        "review_points": review_points,
        "provider_status": "NOT_REQUESTED",
        "provider_result": None,
    }


def enrich_scanner_result_with_ai_presentation(
    result: dict[str, Any],
) -> dict[str, Any]:
    total = 0
    local_checked = 0
    provider_required = 0
    not_ready = 0

    for bucket in ("candidates", "more_candidates"):
        raw_items = result.get(bucket)
        if not isinstance(raw_items, list):
            continue
        next_items: list[Any] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                next_items.append(raw)
                continue
            candidate = deepcopy(raw)
            presentation = build_candidate_ai_review_presentation(candidate)
            candidate["ai_review_presentation"] = presentation
            next_items.append(candidate)

            total += 1
            if presentation["state"] == "AI_REVIEW_CANDIDATE":
                local_checked += 1
                provider_required += 1
            elif presentation["state"] in {"LOCAL_COMPLETE", "LOCAL_CONFLICT"}:
                local_checked += 1
            else:
                not_ready += 1
        result[bucket] = next_items

    result["ai_review_progress"] = {
        "version": AI_REVIEW_PRESENTATION_VERSION,
        "stage": "SEMANTIC_READY",
        "total_candidates": total,
        "local_checked": local_checked,
        "provider_required": provider_required,
        "provider_completed": 0,
        "review_required_count": 0,
        "not_ready": not_ready,
        "completed": False,
    }
    return result
