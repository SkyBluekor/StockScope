from __future__ import annotations

from app.jev.review_presentation import (
    AI_REVIEW_PRESENTATION_VERSION,
    build_candidate_ai_review_presentation,
    enrich_scanner_result_with_ai_presentation,
)
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName


def _candidate(strategy_key: str = StrategyName.TREND_FOLLOWING.value) -> dict:
    binding = next(
        item
        for item in current_strategy_definitions()
        if item.strategy_key == strategy_key
    )
    total = len(condition_sources(strategy_key))
    return {
        "market": "KOSPI",
        "code": "000000",
        "name": "synthetic",
        "strategy": strategy_key,
        "strategy_version_id": binding.strategy_version_id,
        "strategy_definition_hash": binding.definition_hash,
        "action": "ENTRY_CANDIDATE",
        "conditions": {
            "passed": total,
            "total": total,
            "missing": 0,
            "top_missing": [],
        },
        "priority": {
            "strengths": ["기본 분석 강점"],
        },
    }


def test_ai_review_presentation_uses_repo_authored_pass_conditions() -> None:
    presentation = build_candidate_ai_review_presentation(_candidate())
    assert presentation["version"] == AI_REVIEW_PRESENTATION_VERSION
    assert presentation["state"] == "LOCAL_COMPLETE"
    assert presentation["provider_status"] == "NOT_REQUESTED"
    assert presentation["provider_result"] is None
    assert presentation["strengths"]
    assert "현재가가 20일 이동평균선 위" in presentation["strengths"]
    assert presentation["review_points"] == []


def test_scanner_ai_presentation_does_not_claim_provider_completion() -> None:
    result = {
        "candidates": [_candidate()],
        "more_candidates": [],
    }
    enriched = enrich_scanner_result_with_ai_presentation(result)
    candidate = enriched["candidates"][0]
    progress = enriched["ai_review_progress"]

    assert candidate["ai_review_presentation"]["provider_status"] == "NOT_REQUESTED"
    assert progress["stage"] == "SEMANTIC_READY"
    assert progress["total_candidates"] == 1
    assert progress["local_checked"] == 1
    assert progress["provider_required"] == 0
    assert progress["provider_completed"] == 0
    assert progress["review_required_count"] == 0
    assert progress["completed"] is False
