from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.strategy.models import StrategyName
from app.strategy.semantic_contract import (
    SEMANTIC_STATUS_COMPLETE,
    SEMANTIC_STATUS_INVALID_BINDING,
    SEMANTIC_STATUS_MISSING,
    SEMANTIC_STATUS_UNSUPPORTED,
)


CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION = (
    "CONDITION_SEMANTIC_ASSERTION_MAPPING_V1"
)

STANCE_SUPPORTS = "SUPPORTS"
STANCE_WEAKENS = "WEAKENS"
STANCE_CONTRADICTS = "CONTRADICTS"
STANCE_NEUTRAL = "NEUTRAL"
STANCE_UNRESOLVED = "UNRESOLVED"
ALLOWED_ASSERTION_STANCES = frozenset(
    {
        STANCE_SUPPORTS,
        STANCE_WEAKENS,
        STANCE_CONTRADICTS,
        STANCE_NEUTRAL,
        STANCE_UNRESOLVED,
    }
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


# These bindings describe what an already-PASS condition supports in the
# authored semantic contract. They do not re-evaluate numeric market data.
_ASSERTIONS: dict[str, dict[str, tuple[tuple[str, ...], str]]] = {
    StrategyName.TREND_FOLLOWING.value: {
        "현재가가 20일 이동평균선 위": (("trend_structure",), STANCE_SUPPORTS),
        "20일선이 60일선 위": (("trend_structure",), STANCE_SUPPORTS),
        "60일선이 120일선 위": (("trend_structure",), STANCE_SUPPORTS),
        "20일 이동평균 기울기 상승": (("trend_structure",), STANCE_SUPPORTS),
        "고점 상승 구조": (("trend_structure",), STANCE_SUPPORTS),
        "저점 상승 구조": (("trend_structure",), STANCE_SUPPORTS),
        "시장 대비 상대강도 양호": (("relative_strength",), STANCE_SUPPORTS),
        "업종 대비 상대강도 양호": (("relative_strength",), STANCE_SUPPORTS),
        "시장 국면이 상승 추세": (("trend_structure",), STANCE_SUPPORTS),
    },
    StrategyName.PULLBACK.value: {
        "20일선이 60일선 위": (("trend_structure",), STANCE_SUPPORTS),
        "20일 이동평균 기울기 상승": (("trend_structure",), STANCE_SUPPORTS),
        "주요 지지선과 4% 이내": (("support_integrity",), STANCE_SUPPORTS),
        "RSI가 40~65 범위": (("trend_structure",), STANCE_SUPPORTS),
        "거래량이 20일 평균의 1.3배 이하": (("trend_structure",), STANCE_SUPPORTS),
        "저점 상승 구조 유지": (
            ("trend_structure", "support_integrity"),
            STANCE_SUPPORTS,
        ),
        "시장 대비 상대강도 양호": (("trend_structure",), STANCE_SUPPORTS),
        "업종 대비 상대강도 양호": (("trend_structure",), STANCE_SUPPORTS),
        "상승 시장 또는 중립 시장": (("trend_structure",), STANCE_SUPPORTS),
    },
    StrategyName.BREAKOUT.value: {
        "20일 고점과 2% 이내": (("trend_structure",), STANCE_SUPPORTS),
        "거래량이 20일 평균의 1.5배 이상": (("participation",), STANCE_SUPPORTS),
        "현재가가 20일선 위": (("trend_structure",), STANCE_SUPPORTS),
        "20일선 기울기 상승": (("trend_structure",), STANCE_SUPPORTS),
        "RSI 과열 전 구간": (("trend_structure",), STANCE_SUPPORTS),
        "20일 시장 대비 상대강도 양호": (("trend_structure",), STANCE_SUPPORTS),
        "20일 업종 대비 상대강도 양호": (("trend_structure",), STANCE_SUPPORTS),
        "상승 시장": (("trend_structure",), STANCE_SUPPORTS),
    },
    StrategyName.SUPPORT_BOUNCE.value: {
        "주요 지지선과 2.5% 이내": (("support_integrity",), STANCE_SUPPORTS),
        "RSI가 35~60 범위": (("mean_reversion_scope",), STANCE_SUPPORTS),
        "ATR 변동성이 과도하지 않음": (("mean_reversion_scope",), STANCE_SUPPORTS),
        "거래량이 평균 이상": (("mean_reversion_scope",), STANCE_SUPPORTS),
        "저점 상승 또는 유지": (("support_integrity",), STANCE_SUPPORTS),
        "저항까지 최소 4% 여유": (("mean_reversion_scope",), STANCE_SUPPORTS),
        "시장 급락 아님": (("mean_reversion_scope",), STANCE_SUPPORTS),
    },
    StrategyName.OVERSOLD_BOUNCE.value: {
        "RSI 35 이하": (("mean_reversion_scope",), STANCE_SUPPORTS),
        "주요 지지선과 4% 이내": (("support_integrity",), STANCE_SUPPORTS),
        "거래량 증가": (("mean_reversion_scope",), STANCE_SUPPORTS),
        "저항까지 최소 5% 여유": (("mean_reversion_scope",), STANCE_SUPPORTS),
        "ATR 7% 이하": (("mean_reversion_scope",), STANCE_SUPPORTS),
        "시장 PANIC 아님": (("mean_reversion_scope",), STANCE_SUPPORTS),
        "최근 저점 구조가 완전히 붕괴하지 않음": (
            ("support_integrity",),
            STANCE_SUPPORTS,
        ),
    },
    StrategyName.RANGE_TRADING.value: {
        "시장 국면이 횡보": (("range_structure",), STANCE_SUPPORTS),
        "20일선 기울기가 ±0.3% 이내": (("range_structure",), STANCE_SUPPORTS),
        "지지선과 3% 이내": (("support_integrity",), STANCE_SUPPORTS),
        "저항까지 최소 4% 여유": (("range_structure",), STANCE_SUPPORTS),
        "RSI 35~60": (("range_structure",), STANCE_SUPPORTS),
        "ATR 4% 이하": (("range_structure",), STANCE_SUPPORTS),
    },
    StrategyName.MOMENTUM_CONTINUATION.value: {
        "현재가가 20일선 위": (("trend_structure",), STANCE_SUPPORTS),
        "20일선 기울기 0.8% 이상": (("trend_structure",), STANCE_SUPPORTS),
        "RSI 55~75": (("trend_structure",), STANCE_SUPPORTS),
        "거래량 20일 평균의 1.2배 이상": (("participation",), STANCE_SUPPORTS),
        "고점 상승 구조": (("trend_structure",), STANCE_SUPPORTS),
        "저점 상승 구조": (("trend_structure",), STANCE_SUPPORTS),
        "20일 고점과 5% 이내": (("trend_structure",), STANCE_SUPPORTS),
        "20일 시장 대비 상대강도 양호": (
            ("relative_strength",),
            STANCE_SUPPORTS,
        ),
        "시장 급락 아님": (("trend_structure",), STANCE_SUPPORTS),
    },
    StrategyName.VOLATILITY_SQUEEZE.value: {
        "ATR 3.5% 이하": (("compression",), STANCE_SUPPORTS),
        "거래량이 20일 평균 이하": (("compression",), STANCE_SUPPORTS),
        "20일 고점과 4% 이내": (("trend_structure",), STANCE_SUPPORTS),
        "현재가가 20일선 위": (("trend_structure",), STANCE_SUPPORTS),
        "20일선 기울기 하락 아님": (("trend_structure",), STANCE_SUPPORTS),
        "저항과 4% 이내": (("compression",), STANCE_SUPPORTS),
        "시장 급락 아님": (("trend_structure",), STANCE_SUPPORTS),
    },
    StrategyName.MA20_REBOUND.value: {
        "현재가가 20일선과 2.5% 이내": (
            ("trend_structure", "support_integrity"),
            STANCE_SUPPORTS,
        ),
        "20일선 기울기 상승": (("trend_structure",), STANCE_SUPPORTS),
        "RSI 40~65": (("trend_structure",), STANCE_SUPPORTS),
        "저점 상승 구조": (
            ("trend_structure", "support_integrity"),
            STANCE_SUPPORTS,
        ),
        "거래량 1.3배 이하": (("trend_structure",), STANCE_SUPPORTS),
        "시장 급락 아님": (("trend_structure",), STANCE_SUPPORTS),
    },
    StrategyName.TREND_RECOVERY.value: {
        "현재가가 20일선 위로 회복": (("recovery_structure",), STANCE_SUPPORTS),
        "20일선 기울기가 급락 아님": (("recovery_structure",), STANCE_SUPPORTS),
        "RSI 40~60": (("recovery_structure",), STANCE_SUPPORTS),
        "최근 저점 상승": (
            ("recovery_structure", "support_integrity"),
            STANCE_SUPPORTS,
        ),
        "지지선과 5% 이내": (("support_integrity",), STANCE_SUPPORTS),
        "시장 PANIC 아님": (("recovery_structure",), STANCE_SUPPORTS),
    },
}


CONDITION_SEMANTIC_ASSERTION_MAPPING_HASH = _digest(
    {
        "version": CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION,
        "strategy_assertions": {
            strategy: [
                {
                    "source": source,
                    "concept_refs": list(refs),
                    "stance": stance,
                }
                for source, (refs, stance) in sorted(rows.items())
            ]
            for strategy, rows in sorted(_ASSERTIONS.items())
        },
    }
)


@dataclass(frozen=True, slots=True)
class ConditionSemanticAssertionProjection:
    status: str
    reason_codes: tuple[str, ...]
    items: tuple[dict[str, Any], ...]
    mapping_version: str = CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION
    mapping_hash: str = CONDITION_SEMANTIC_ASSERTION_MAPPING_HASH


def assertion_sources(strategy_key: str) -> tuple[str, ...]:
    key = str(strategy_key or "").strip().lower()
    return tuple(_ASSERTIONS.get(key, {}).keys())


def project_passed_condition_assertions(
    *,
    strategy_key: str,
    condition_items: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> ConditionSemanticAssertionProjection:
    key = str(strategy_key or "").strip().lower()
    mapping = _ASSERTIONS.get(key)
    if mapping is None:
        return ConditionSemanticAssertionProjection(
            SEMANTIC_STATUS_UNSUPPORTED,
            ("CONDITION_ASSERTION_STRATEGY_UNSUPPORTED",),
            (),
        )
    if not condition_items:
        return ConditionSemanticAssertionProjection(
            SEMANTIC_STATUS_MISSING,
            ("CONDITION_ASSERTION_SOURCE_MISSING",),
            (),
        )

    projected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in condition_items:
        if not isinstance(item, dict) or str(item.get("status") or "") != "PASS":
            return ConditionSemanticAssertionProjection(
                SEMANTIC_STATUS_INVALID_BINDING,
                ("CONDITION_ASSERTION_SOURCE_INVALID",),
                (),
            )
        source = str(item.get("source_condition") or "")
        condition_id = str(item.get("condition_id") or "")
        meaning = str(item.get("observed_meaning") or "")
        if not source or not condition_id or not meaning or source in seen:
            return ConditionSemanticAssertionProjection(
                SEMANTIC_STATUS_INVALID_BINDING,
                ("CONDITION_ASSERTION_SOURCE_INVALID",),
                (),
            )
        binding = mapping.get(source)
        if binding is None:
            return ConditionSemanticAssertionProjection(
                SEMANTIC_STATUS_INVALID_BINDING,
                ("CONDITION_ASSERTION_BINDING_MISSING",),
                (),
            )
        refs, stance = binding
        if not refs or stance not in ALLOWED_ASSERTION_STANCES:
            return ConditionSemanticAssertionProjection(
                SEMANTIC_STATUS_INVALID_BINDING,
                ("CONDITION_ASSERTION_BINDING_INVALID",),
                (),
            )
        seen.add(source)
        projected.append(
            {
                "condition_id": condition_id,
                "source_condition": source,
                "concept_refs": list(refs),
                "stance": stance,
                "observed_meaning": meaning,
            }
        )

    if seen != set(mapping):
        return ConditionSemanticAssertionProjection(
            SEMANTIC_STATUS_MISSING,
            ("CONDITION_ASSERTION_SET_INCOMPLETE",),
            (),
        )

    return ConditionSemanticAssertionProjection(
        SEMANTIC_STATUS_COMPLETE,
        (),
        tuple(projected),
    )
