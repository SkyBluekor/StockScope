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


CONDITION_SEMANTIC_MAPPING_VERSION = "CONDITION_SEMANTIC_MAPPING_V1"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


# Exact, repository-controlled meanings for StrategyEngine condition labels.
# These are semantic descriptions of already-computed PASS facts. They do not
# expose current numeric values or ask Jev to recompute thresholds.
_CONDITION_MEANINGS: dict[str, tuple[tuple[str, str], ...]] = {
    StrategyName.TREND_FOLLOWING.value: (
        ("현재가가 20일 이동평균선 위", "price is positioned above the 20-day moving-average reference"),
        ("20일선이 60일선 위", "the 20-day moving-average reference is above the 60-day reference"),
        ("60일선이 120일선 위", "the 60-day moving-average reference is above the 120-day reference"),
        ("20일 이동평균 기울기 상승", "the 20-day moving-average direction is rising"),
        ("고점 상승 구조", "recent highs preserve a higher-high structure"),
        ("저점 상승 구조", "recent lows preserve a higher-low structure"),
        ("시장 대비 상대강도 양호", "relative strength versus the broad market is supportive"),
        ("업종 대비 상대강도 양호", "relative strength versus the sector is supportive"),
        ("시장 국면이 상승 추세", "the broad market regime is classified as an uptrend"),
    ),
    StrategyName.PULLBACK.value: (
        ("20일선이 60일선 위", "the 20-day moving-average reference remains above the 60-day reference"),
        ("20일 이동평균 기울기 상승", "the 20-day moving-average direction is rising"),
        ("주요 지지선과 4% 이내", "price remains within the strategy-defined proximity to support"),
        ("RSI가 40~65 범위", "momentum is within the strategy's neutral-to-positive pullback range"),
        ("거래량이 20일 평균의 1.3배 이하", "pullback participation is not excessively elevated versus its recent average"),
        ("저점 상승 구조 유지", "the recent higher-low structure remains intact"),
        ("시장 대비 상대강도 양호", "relative strength versus the broad market is not negative"),
        ("업종 대비 상대강도 양호", "relative strength versus the sector is not negative"),
        ("상승 시장 또는 중립 시장", "the market regime is compatible with an uptrend or range environment"),
    ),
    StrategyName.BREAKOUT.value: (
        ("20일 고점과 2% 이내", "price is within the strategy-defined proximity to the recent high"),
        ("거래량이 20일 평균의 1.5배 이상", "breakout participation is elevated above its recent average"),
        ("현재가가 20일선 위", "price is positioned above the 20-day moving-average reference"),
        ("20일선 기울기 상승", "the 20-day moving-average direction is rising"),
        ("RSI 과열 전 구간", "momentum is positive while remaining below the strategy's overheating range"),
        ("20일 시장 대비 상대강도 양호", "recent relative strength versus the broad market is supportive"),
        ("20일 업종 대비 상대강도 양호", "recent relative strength versus the sector is supportive"),
        ("상승 시장", "the broad market regime is classified as an uptrend"),
    ),
    StrategyName.SUPPORT_BOUNCE.value: (
        ("주요 지지선과 2.5% 이내", "price remains within the strategy-defined proximity to support"),
        ("RSI가 35~60 범위", "momentum is within the strategy's bounded rebound range"),
        ("ATR 변동성이 과도하지 않음", "volatility remains below the strategy's excessive-volatility boundary"),
        ("거래량이 평균 이상", "rebound participation is at or above its recent average"),
        ("저점 상승 또는 유지", "the recent low structure is holding rather than breaking lower"),
        ("저항까지 최소 4% 여유", "the strategy records sufficient room before the next resistance reference"),
        ("시장 급락 아님", "the market regime is not classified as a downtrend or panic"),
    ),
    StrategyName.OVERSOLD_BOUNCE.value: (
        ("RSI 35 이하", "momentum is within the strategy's oversold range"),
        ("주요 지지선과 4% 이내", "price remains within the strategy-defined proximity to support"),
        ("거래량 증가", "rebound participation is elevated above the strategy's baseline"),
        ("저항까지 최소 5% 여유", "the strategy records sufficient room before the next resistance reference"),
        ("ATR 7% 이하", "volatility remains within the strategy's rebound risk boundary"),
        ("시장 PANIC 아님", "the broad market is not classified as panic"),
        ("최근 저점 구조가 완전히 붕괴하지 않음", "the recent low structure is not recorded as fully broken"),
    ),
    StrategyName.RANGE_TRADING.value: (
        ("시장 국면이 횡보", "the broad market regime is classified as range-bound"),
        ("20일선 기울기가 ±0.3% 이내", "the 20-day moving-average direction is approximately flat"),
        ("지지선과 3% 이내", "price remains within the strategy-defined proximity to support"),
        ("저항까지 최소 4% 여유", "the strategy records sufficient room before the next resistance reference"),
        ("RSI 35~60", "momentum is within the strategy's bounded range-trading interval"),
        ("ATR 4% 이하", "volatility remains within the strategy's range-trading boundary"),
    ),
    StrategyName.MOMENTUM_CONTINUATION.value: (
        ("현재가가 20일선 위", "price is positioned above the 20-day moving-average reference"),
        ("20일선 기울기 0.8% 이상", "the 20-day moving-average direction meets the strategy's strong-rise condition"),
        ("RSI 55~75", "momentum is strong while remaining within the strategy's continuation range"),
        ("거래량 20일 평균의 1.2배 이상", "continuation participation is elevated above its recent average"),
        ("고점 상승 구조", "recent highs preserve a higher-high structure"),
        ("저점 상승 구조", "recent lows preserve a higher-low structure"),
        ("20일 고점과 5% 이내", "price remains near the recent high under the continuation condition"),
        ("20일 시장 대비 상대강도 양호", "recent relative strength versus the broad market is supportive"),
        ("시장 급락 아님", "the market regime is not classified as a downtrend or panic"),
    ),
    StrategyName.VOLATILITY_SQUEEZE.value: (
        ("ATR 3.5% 이하", "volatility is compressed within the strategy's squeeze boundary"),
        ("거래량이 20일 평균 이하", "participation is compressed at or below its recent average"),
        ("20일 고점과 4% 이내", "price remains near the recent high while the setup is compressed"),
        ("현재가가 20일선 위", "price is positioned at or above the 20-day moving-average reference"),
        ("20일선 기울기 하락 아님", "the 20-day moving-average direction is not declining"),
        ("저항과 4% 이내", "price remains near the strategy's resistance reference"),
        ("시장 급락 아님", "the market regime is not classified as a downtrend or panic"),
    ),
    StrategyName.MA20_REBOUND.value: (
        ("현재가가 20일선과 2.5% 이내", "price remains within the strategy-defined proximity to the 20-day moving-average reference"),
        ("20일선 기울기 상승", "the 20-day moving-average direction is rising"),
        ("RSI 40~65", "momentum is within the strategy's rebound-compatible range"),
        ("저점 상승 구조", "recent lows preserve a higher-low structure"),
        ("거래량 1.3배 이하", "rebound participation is not excessively elevated versus its recent average"),
        ("시장 급락 아님", "the market regime is not classified as a downtrend or panic"),
    ),
    StrategyName.TREND_RECOVERY.value: (
        ("현재가가 20일선 위로 회복", "price has recovered to or above the 20-day moving-average reference"),
        ("20일선 기울기가 급락 아님", "the 20-day moving-average direction is no longer in a sharp decline"),
        ("RSI 40~60", "momentum is within the strategy's recovery-compatible range"),
        ("최근 저점 상승", "recent lows preserve a recovering higher-low structure"),
        ("지지선과 5% 이내", "price remains within the strategy-defined proximity to support"),
        ("시장 PANIC 아님", "the broad market is not classified as panic"),
    ),
}

CONDITION_SEMANTIC_MAPPING_HASH = _digest(
    {
        "version": CONDITION_SEMANTIC_MAPPING_VERSION,
        "strategy_conditions": {
            key: [{"source": raw, "meaning": meaning} for raw, meaning in rows]
            for key, rows in sorted(_CONDITION_MEANINGS.items())
        },
    }
)


@dataclass(frozen=True, slots=True)
class ConditionSemanticProjection:
    status: str
    reason_codes: tuple[str, ...]
    items: tuple[dict[str, str], ...]
    mapping_version: str = CONDITION_SEMANTIC_MAPPING_VERSION
    mapping_hash: str = CONDITION_SEMANTIC_MAPPING_HASH


def condition_sources(strategy_key: str) -> tuple[str, ...]:
    key = str(strategy_key or "").strip().lower()
    return tuple(raw for raw, _ in _CONDITION_MEANINGS.get(key, ()))


def project_passed_condition_meanings(
    *,
    strategy_key: str,
    conditions_summary: dict[str, Any] | None,
) -> ConditionSemanticProjection:
    key = str(strategy_key or "").strip().lower()
    rows = _CONDITION_MEANINGS.get(key)
    if rows is None:
        return ConditionSemanticProjection(
            SEMANTIC_STATUS_UNSUPPORTED,
            ("Q1_CONDITION_MAPPING_UNSUPPORTED",),
            (),
        )
    if not isinstance(conditions_summary, dict):
        return ConditionSemanticProjection(
            SEMANTIC_STATUS_MISSING,
            ("Q1_CONDITION_SUMMARY_MISSING",),
            (),
        )
    try:
        passed = int(conditions_summary.get("passed") or 0)
        total = int(conditions_summary.get("total") or 0)
        missing = int(conditions_summary.get("missing") or 0)
    except (TypeError, ValueError):
        return ConditionSemanticProjection(
            SEMANTIC_STATUS_INVALID_BINDING,
            ("Q1_CONDITION_SUMMARY_INVALID",),
            (),
        )

    expected = len(rows)
    if total != expected:
        return ConditionSemanticProjection(
            SEMANTIC_STATUS_INVALID_BINDING,
            ("Q1_CONDITION_COUNT_CONTRACT_MISMATCH",),
            (),
        )
    if total <= 0 or missing != 0 or passed != total:
        return ConditionSemanticProjection(
            SEMANTIC_STATUS_MISSING,
            ("Q1_CONDITIONS_NOT_COMPLETE",),
            (),
        )

    items = tuple(
        {
            "condition_id": f"condition-{index:02d}",
            "source_condition": raw,
            "status": "PASS",
            "observed_meaning": meaning,
        }
        for index, (raw, meaning) in enumerate(rows, start=1)
    )
    return ConditionSemanticProjection(
        SEMANTIC_STATUS_COMPLETE,
        (),
        items,
    )
