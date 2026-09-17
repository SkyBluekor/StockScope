from __future__ import annotations

import math
import re
from typing import Any

from app.backtest.target1_audit import build_current_target1_audit


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _status_value(value: Any) -> str | None:
    raw = _get(value, "value", value)
    return None if raw is None else str(raw)


def _krx_tick_size(value: float | None) -> float | None:
    """Return the display tick used for ordinary KRX equity prices.

    This helper is presentation-only. Strategy/Risk calculations continue to use
    the original unrounded numeric values.
    """
    if value is None or value < 0:
        return None
    if value < 2_000:
        return 1.0
    if value < 5_000:
        return 5.0
    if value < 20_000:
        return 10.0
    if value < 50_000:
        return 50.0
    if value < 200_000:
        return 100.0
    if value < 500_000:
        return 500.0
    return 1_000.0


def _krx_display_price(value: float | None) -> float | None:
    if value is None:
        return None
    tick = _krx_tick_size(value)
    if tick is None or tick <= 0:
        return value
    # Avoid Python's bankers-rounding; this is only a nearest-tick UI value.
    rounded = int(value / tick + 0.5) * tick
    return float(rounded)


def _display_price_rule(rule: dict[str, Any]) -> dict[str, Any]:
    result = dict(rule)
    result["display_range_low"] = _krx_display_price(_number(rule.get("range_low")))
    result["display_range_high"] = _krx_display_price(_number(rule.get("range_high")))
    result["display_trigger_price"] = _krx_display_price(_number(rule.get("trigger_price")))
    result["display_reference_price"] = _krx_display_price(_number(rule.get("reference_price")))
    return result




def _price_rule_semantics(rule: dict[str, Any]) -> dict[str, Any]:
    """Describe what the strategy-derived price rule means to a user.

    v0.21.4-B.2.3.2a: RANGE rules are qualification/observation bands derived from
    strategy conditions. They are not executable buy ranges and must not be compared
    to the RiskEngine stop zone as if both belonged to the same execution step.
    """
    result = dict(rule)
    kind = str(result.get("kind") or "UNAVAILABLE")
    if kind == "RANGE":
        result["semantic_role"] = "STRATEGY_CONDITION_BAND"
        result["user_label"] = "전략 조건 가격대"
        result["executable_entry_range"] = False
        result["semantic_note"] = (
            "전략 조건 충족 여부를 보기 위해 기준선을 가격대로 환산한 범위입니다. "
            "이 구간 전체가 매수 가능한 가격 범위를 뜻하지 않습니다."
        )
    elif kind in {"ABOVE", "AT_OR_BELOW"}:
        result["semantic_role"] = "STRATEGY_CONDITION_THRESHOLD"
        result["user_label"] = "전략 조건 기준가"
        result["executable_entry_range"] = False
        result["semantic_note"] = "전략 조건 충족 여부를 확인하는 기준가격이며 자동 주문 가격이 아닙니다."
    else:
        result["semantic_role"] = "STRATEGY_REFERENCE"
        result["user_label"] = "전략 가격 기준"
        result["executable_entry_range"] = False
        result["semantic_note"] = "전략 판단을 설명하기 위한 참고가격입니다."
    return result


def _range_overlap(low_a: float | None, high_a: float | None, low_b: float | None, high_b: float | None) -> dict[str, float | None]:
    if None in {low_a, high_a, low_b, high_b}:
        return {"low": None, "high": None, "width": None, "ratio_pct": None}
    left = max(float(low_a), float(low_b))
    right = min(float(high_a), float(high_b))
    if right < left:
        return {"low": None, "high": None, "width": 0.0, "ratio_pct": 0.0}
    width = max(0.0, right - left)
    base_width = max(0.0, float(high_a) - float(low_a))
    ratio = width / base_width * 100.0 if base_width > 0 else (100.0 if width == 0 else None)
    return {
        "low": left,
        "high": right,
        "width": width,
        "ratio_pct": None if ratio is None else round(ratio, 2),
    }

def _sorted_pair(low: Any, high: Any) -> tuple[float | None, float | None]:
    first = _number(low)
    second = _number(high)
    if first is None and second is None:
        return None, None
    if first is None:
        return second, second
    if second is None:
        return first, first
    return (first, second) if first <= second else (second, first)


def _issue(code: str, severity: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "detail": detail}


def _price_plan_consistency(price_rule: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
    """Validate execution-risk prices while keeping strategy condition prices semantically separate.

    The strategy price rule is a qualification/observation condition. RiskEngine uses its own
    entry reference (the current analysis price for the live Scanner) to build invalidation,
    stop and targets. A visual overlap between those two independent layers is therefore not,
    by itself, an invalid trade plan.
    """
    kind = str(price_rule.get("kind") or "UNAVAILABLE")
    semantic_role = str(price_rule.get("semantic_role") or ("STRATEGY_CONDITION_BAND" if kind == "RANGE" else "STRATEGY_CONDITION_THRESHOLD" if kind in {"ABOVE", "AT_OR_BELOW"} else "STRATEGY_REFERENCE"))
    raw_entry_low = _number(price_rule.get("range_low"))
    raw_entry_high = _number(price_rule.get("range_high"))
    raw_stop_low = _number(risk.get("stop_zone_low"))
    raw_stop_high = _number(risk.get("stop_zone_high"))
    entry_low, entry_high = _sorted_pair(raw_entry_low, raw_entry_high)
    display_entry_low, display_entry_high = _sorted_pair(
        price_rule.get("display_range_low"), price_rule.get("display_range_high")
    )
    entry_reference = _number(risk.get("entry_reference_price"))
    invalidation = _number(risk.get("invalidation_price"))
    stop_low, stop_high = _sorted_pair(raw_stop_low, raw_stop_high)
    target1 = _number(risk.get("target1_price"))
    target2 = _number(risk.get("target2_price"))

    display_stop_low, display_stop_high = _sorted_pair(
        _krx_display_price(stop_low), _krx_display_price(stop_high)
    )
    display_invalidation = _krx_display_price(invalidation)

    issues: list[dict[str, str]] = []
    comparable = False
    relation_message: str | None = None
    raw_overlap = False
    semantic_overlap = False
    display_overlap_only = False
    classification = "NOT_APPLICABLE"

    raw_named_values = {
        "전략 가격대 하단": entry_low,
        "전략 가격대 상단": entry_high,
        "Risk 진입 기준": entry_reference,
        "전략 무효화": invalidation,
        "손절 구간 하단": stop_low,
        "손절 구간 상단": stop_high,
        "1차 목표": target1,
        "2차 목표": target2,
    }
    for label, value in raw_named_values.items():
        if value is not None and value <= 0:
            issues.append(_issue("NON_POSITIVE_PRICE", "INVALID", f"{label} 가격이 0 이하입니다."))

    if raw_entry_low is not None and raw_entry_high is not None and raw_entry_low > raw_entry_high:
        issues.append(_issue("CONDITION_RANGE_REVERSED", "INVALID", "전략 조건 가격대의 상·하단이 뒤바뀌었습니다."))
    if raw_stop_low is not None and raw_stop_high is not None and raw_stop_low > raw_stop_high:
        issues.append(_issue("STOP_ZONE_REVERSED", "INVALID", "손절 참고 구간의 상·하단이 뒤바뀌었습니다."))

    # Execution-risk self consistency is the actual validity check.
    if entry_reference is not None:
        comparable = True
        if invalidation is not None and invalidation >= entry_reference:
            issues.append(_issue("INVALIDATION_AT_OR_ABOVE_RISK_ENTRY", "INVALID", "전략 무효화 가격이 리스크 계산 기준가보다 낮지 않습니다."))
        if stop_high is not None and stop_high >= entry_reference:
            issues.append(_issue("STOP_AT_OR_ABOVE_RISK_ENTRY", "INVALID", "손절 참고 구간이 리스크 계산 기준가보다 낮지 않습니다."))
        if target1 is not None and target1 <= entry_reference:
            issues.append(_issue("TARGET1_AT_OR_BELOW_RISK_ENTRY", "INVALID", "1차 목표가가 리스크 계산 기준가보다 높지 않습니다."))
    if target1 is not None and target2 is not None:
        comparable = True
        if target2 < target1:
            issues.append(_issue("TARGET2_BELOW_TARGET1", "INVALID", "2차 목표가가 1차 목표가보다 낮습니다."))

    overlap = _range_overlap(entry_low, entry_high, stop_low, stop_high)
    if kind == "RANGE" and entry_low is not None and entry_high is not None:
        comparable = True
        if overlap["low"] is not None and overlap["high"] is not None:
            raw_overlap = True
            if semantic_role == "STRATEGY_CONDITION_BAND":
                semantic_overlap = True
                issues.append(_issue(
                    "CONDITION_BAND_STOP_OVERLAP",
                    "INFO",
                    "전략 조건 가격대와 손절 참고구간이 겹치지만 두 값은 서로 다른 계산 단계의 기준입니다.",
                ))
                relation_message = (
                    f"전략 조건 가격대와 손절 참고구간이 {overlap['low']:,.0f}~{overlap['high']:,.0f}원에서 겹칩니다. "
                    "전략 가격대는 조건 충족 범위이고 매수 가능 범위가 아니며, 손절은 리스크 계산 기준가에서 별도로 계산됩니다."
                )
            else:
                issues.append(_issue("ENTRY_STOP_OVERLAP", "WARNING", "실제 진입 가격대와 손절 참고 구간이 겹칩니다."))
        elif stop_high is not None and stop_high < entry_low:
            gap = entry_low - stop_high
            gap_pct = gap / entry_low * 100.0 if entry_low > 0 else None
            relation_message = (
                f"손절 참고 상단은 전략 조건 가격대 하단보다 {gap:,.0f}원"
                + (f" ({gap_pct:.2f}%)" if gap_pct is not None else "")
                + " 아래입니다."
            )
        elif stop_low is not None and stop_low > entry_high:
            # Still not an execution conflict for a strategy-condition band; it means the
            # qualification band sits below the hypothetical stop calculated from current price.
            semantic_overlap = semantic_role == "STRATEGY_CONDITION_BAND"
            if semantic_overlap:
                issues.append(_issue(
                    "CONDITION_BAND_BELOW_STOP_ZONE",
                    "INFO",
                    "전략 조건 가격대 전체가 손절 참고구간보다 아래에 있습니다. 서로 다른 기준이므로 자동 오류로 처리하지 않습니다.",
                ))
                relation_message = "전략 조건 가격대는 현재 리스크 계획보다 아래에 있습니다. 이 가격대는 매수 가능 범위가 아니라 전략 조건 기준입니다."
            else:
                issues.append(_issue("STOP_ZONE_ABOVE_ENTRY_RANGE", "INVALID", "손절 참고 구간이 실제 진입 가격대보다 위에 있습니다."))

        # Invalidation touching a strategy condition band is also semantic context, not an
        # execution contradiction, as long as invalidation remains below RiskEngine entry.
        if invalidation is not None and entry_low <= invalidation <= entry_high:
            if semantic_role == "STRATEGY_CONDITION_BAND":
                semantic_overlap = True
                issues.append(_issue("CONDITION_BAND_INVALIDATION_OVERLAP", "INFO", "전략 조건 가격대 안에 전략 무효화 기준이 위치합니다. 두 기준의 역할을 구분해 표시합니다."))
            else:
                issues.append(_issue("ENTRY_INVALIDATION_OVERLAP", "WARNING", "실제 진입 가격대와 전략 무효화 가격이 겹칩니다."))

        if (
            not raw_overlap
            and display_entry_low is not None
            and display_stop_high is not None
            and display_stop_high >= display_entry_low
        ):
            display_overlap_only = True
            issues.append(_issue("DISPLAY_ROUNDING_TOUCH", "INFO", "KRX 표시 단위 반올림 후 전략 가격대와 손절 가격이 같거나 겹쳐 보입니다."))

    elif entry_reference is not None:
        if stop_high is not None and stop_high < entry_reference:
            gap = entry_reference - stop_high
            gap_pct = gap / entry_reference * 100.0 if entry_reference > 0 else None
            relation_message = (
                f"손절 참고 상단은 리스크 계산 기준가보다 {gap:,.0f}원"
                + (f" ({gap_pct:.2f}%)" if gap_pct is not None else "")
                + " 아래입니다."
            )
        elif invalidation is not None and invalidation < entry_reference:
            gap = entry_reference - invalidation
            gap_pct = gap / entry_reference * 100.0 if entry_reference > 0 else None
            relation_message = (
                f"전략 무효화 가격은 리스크 계산 기준가보다 {gap:,.0f}원"
                + (f" ({gap_pct:.2f}%)" if gap_pct is not None else "")
                + " 아래입니다."
            )

    severities = {item["severity"] for item in issues}
    if "INVALID" in severities:
        status = "INVALID"
        classification = "RISK_PLAN_INVALID"
        message = "가격 계획을 다시 확인해야 합니다. 리스크 계산 기준가·손절·목표 가격 관계에 맞지 않는 값이 있습니다."
    elif "WARNING" in severities:
        status = "WARNING"
        classification = "EXECUTION_PRICE_CONFLICT"
        message = "가격 계획을 다시 확인해야 합니다. 실제 실행 가격 관계에 충돌 가능성이 있습니다."
    elif semantic_overlap:
        status = "OK"
        classification = "STRATEGY_CONDITION_BAND_OVERLAP"
        message = "전략 조건 가격대와 손절 참고구간은 서로 다른 목적의 값입니다. 겹침 자체는 리스크 계산 오류가 아닙니다."
    elif display_overlap_only:
        status = "OK"
        classification = "DISPLAY_ROUNDING_TOUCH"
        message = "표시 반올림 후 가격이 닿아 보이지만 내부 계산값은 분리되어 있습니다."
    elif comparable:
        status = "OK"
        classification = "SEPARATED"
        message = relation_message or "리스크 계산 기준가·손절·목표 가격 관계에 충돌이 없습니다."
    else:
        status = "NOT_APPLICABLE"
        classification = "NOT_APPLICABLE"
        message = "현재 전략에서는 가격 관계를 안전하게 비교할 기준이 충분하지 않습니다."

    root_summary = None
    if classification == "STRATEGY_CONDITION_BAND_OVERLAP":
        root_summary = (
            "전략 가격대는 Strategy 조건을 환산한 범위이고 RiskEngine은 별도의 진입 기준가로 손절을 계산합니다. "
            "따라서 두 범위는 수학적으로 겹칠 수 있으며 같은 매매 단계의 가격으로 해석하면 안 됩니다."
        )
    elif classification == "RISK_PLAN_INVALID":
        root_summary = "RiskEngine 내부의 진입 기준가·손절·목표 관계 자체를 다시 확인해야 합니다."
    elif classification == "DISPLAY_ROUNDING_TOUCH":
        root_summary = "원시 계산값은 분리되어 있으나 KRX 표시단위 반올림 때문에 화면에서 닿아 보입니다."

    return {
        "status": status,
        "classification": classification,
        "has_conflict": status in {"WARNING", "INVALID"},
        "message": message,
        "relation_message": relation_message,
        "root_cause_summary": root_summary,
        "issue_codes": [item["code"] for item in issues],
        "issues": issues,
        "raw_overlap": raw_overlap,
        "semantic_overlap": semantic_overlap,
        "display_overlap_only": display_overlap_only,
        "overlap": overlap,
        "raw": {
            "condition_range_low": entry_low,
            "condition_range_high": entry_high,
            # Compatibility aliases retained for older frontend/debug tools.
            "entry_range_low": entry_low,
            "entry_range_high": entry_high,
            "risk_entry_reference": entry_reference,
            "invalidation_price": invalidation,
            "stop_zone_low": stop_low,
            "stop_zone_high": stop_high,
            "target1_price": target1,
            "target2_price": target2,
        },
        "display": {
            "condition_range_low": display_entry_low,
            "condition_range_high": display_entry_high,
            "entry_range_low": display_entry_low,
            "entry_range_high": display_entry_high,
            "invalidation_price": display_invalidation,
            "stop_zone_low": display_stop_low,
            "stop_zone_high": display_stop_high,
        },
        "sources": {
            "strategy_price": str(price_rule.get("basis") or price_rule.get("label") or kind),
            "entry": "RiskEngine entry_price (실행 리스크 기준가)",
            "risk_entry": "RiskEngine entry_price (실행 리스크 기준가)",
            "stop": str(risk.get("structural_anchor_label") or risk.get("basis_label") or "RiskEngine stop zone"),
            "invalidation": "RiskEngine invalidation_price",
            "targets": "RiskEngine target prices",
        },
    }


def _pct_gap(current: float | None, target: float | None) -> float | None:
    if current is None or target is None or current == 0:
        return None
    return round((target - current) / current * 100.0, 2)


def _conditions(condition_state: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list((condition_state or {}).get("conditions") or [])


def _pick_detail(condition_state: dict[str, Any] | None, predicate) -> dict[str, Any] | None:
    details = _conditions(condition_state)
    failed = [item for item in details if str(item.get("status")) == "FAIL" and predicate(item)]
    if failed:
        return failed[0]
    matched = [item for item in details if predicate(item)]
    return matched[0] if matched else None


def _support_rule(detail: dict[str, Any], data: Any, technical: dict[str, Any]) -> dict[str, Any] | None:
    raw = str(detail.get("raw") or "")
    match = re.search(r"(?:주요 )?지지선과 ([0-9.]+)% 이내", raw)
    if not match:
        return None
    threshold = float(match.group(1))
    support = _number(_get(data, "support_price"))
    if support is None:
        support = _number(technical.get("support"))
    current = _number(_get(data, "current_price"))
    if support is None or threshold >= 100:
        return None
    low = support
    high = support / (1.0 - threshold / 100.0)
    if current is None:
        gap = None
    elif current < low:
        gap = _pct_gap(current, low)
    elif current > high:
        gap = _pct_gap(current, high)
    else:
        gap = 0.0
    return {
        "kind": "RANGE",
        "label": "지지 가격 근처 진입 구간",
        "status": detail.get("status") or "UNKNOWN",
        "basis": raw,
        "range_low": round(low, 4),
        "range_high": round(high, 4),
        "trigger_price": None,
        "reference_price": round(support, 4),
        "gap_pct": gap,
        "message": f"기존 전략 조건인 지지선과 {threshold:g}% 이내 범위를 실제 가격으로 환산했습니다.",
    }


def _high_rule(
    detail: dict[str, Any],
    data: Any,
    technical: dict[str, Any],
    *,
    exact_reference: bool = False,
) -> dict[str, Any] | None:
    raw = str(detail.get("raw") or "")
    match = re.search(r"20일 고점과 ([0-9.]+)% 이내", raw)
    if not match:
        return None
    threshold = float(match.group(1))
    high20 = _number(technical.get("high20"))
    current = _number(_get(data, "current_price"))
    if high20 is None:
        return None
    if exact_reference:
        return {
            "kind": "ABOVE",
            "label": "20일 고점 돌파 확인 가격",
            "status": detail.get("status") or "UNKNOWN",
            "basis": raw,
            "range_low": None,
            "range_high": None,
            "trigger_price": round(high20, 4),
            "reference_price": round(high20, 4),
            "gap_pct": 0.0 if current is not None and current >= high20 else _pct_gap(current, high20),
            "message": (
                f"전략 엔진은 20일 고점과 {threshold:g}% 이내인지 평가하고, "
                "화면에는 그 기준점인 20일 고점을 돌파 확인 참고가격으로 표시합니다."
            ),
        }

    low = high20 / (1.0 + threshold / 100.0)
    high = high20
    if current is None:
        gap = None
    elif current < low:
        gap = _pct_gap(current, low)
    elif current > high:
        gap = _pct_gap(current, high)
    else:
        gap = 0.0
    return {
        "kind": "RANGE",
        "label": "최근 고점 접근 구간",
        "status": detail.get("status") or "UNKNOWN",
        "basis": raw,
        "range_low": round(low, 4),
        "range_high": round(high, 4),
        "trigger_price": None,
        "reference_price": round(high20, 4),
        "gap_pct": gap,
        "message": f"기존 전략 조건인 20일 고점과 {threshold:g}% 이내를 실제 가격 구간으로 환산했습니다.",
    }


def _ma20_rule(detail: dict[str, Any], data: Any) -> dict[str, Any] | None:
    raw = str(detail.get("raw") or "")
    ma20 = _number(_get(data, "ma20"))
    current = _number(_get(data, "current_price"))
    if ma20 is None:
        return None
    within = re.search(r"현재가가 20일선과 ([0-9.]+)% 이내", raw)
    if within:
        threshold = float(within.group(1))
        low = ma20 / (1.0 + threshold / 100.0)
        high = ma20 / (1.0 - threshold / 100.0)
        if current is None:
            gap = None
        elif current < low:
            gap = _pct_gap(current, low)
        elif current > high:
            gap = _pct_gap(current, high)
        else:
            gap = 0.0
        return {
            "kind": "RANGE",
            "label": "20일 평균 가격 근처 구간",
            "status": detail.get("status") or "UNKNOWN",
            "basis": raw,
            "range_low": round(low, 4),
            "range_high": round(high, 4),
            "trigger_price": None,
            "reference_price": round(ma20, 4),
            "gap_pct": gap,
            "message": f"20일 평균 가격과 {threshold:g}% 이내라는 기존 조건을 실제 가격 구간으로 환산했습니다.",
        }
    if raw in {"현재가가 20일 이동평균선 위", "현재가가 20일선 위", "현재가가 20일선 위로 회복"}:
        return {
            "kind": "ABOVE",
            "label": "20일 평균 가격 위 유지",
            "status": detail.get("status") or "UNKNOWN",
            "basis": raw,
            "range_low": None,
            "range_high": None,
            "trigger_price": round(ma20, 4),
            "reference_price": round(ma20, 4),
            "gap_pct": 0.0 if current is not None and current > ma20 else _pct_gap(current, ma20),
            "message": "기존 전략 조건의 20일 평균 가격을 진입 타이밍 참고선으로 표시합니다.",
        }
    return None


def _resistance_rule(detail: dict[str, Any], data: Any, technical: dict[str, Any]) -> dict[str, Any] | None:
    raw = str(detail.get("raw") or "")
    match = re.search(r"저항까지 최소 ([0-9.]+)% 여유", raw)
    if not match:
        return None
    threshold = float(match.group(1))
    resistance = _number(_get(data, "resistance_price"))
    if resistance is None:
        resistance = _number(technical.get("resistance"))
    current = _number(_get(data, "current_price"))
    if resistance is None:
        return None
    maximum = resistance / (1.0 + threshold / 100.0)
    return {
        "kind": "AT_OR_BELOW",
        "label": "목표 여유를 남길 수 있는 최대 참고가격",
        "status": detail.get("status") or "UNKNOWN",
        "basis": raw,
        "range_low": None,
        "range_high": None,
        "trigger_price": round(maximum, 4),
        "reference_price": round(resistance, 4),
        "gap_pct": 0.0 if current is not None and current <= maximum else _pct_gap(current, maximum),
        "message": f"저항까지 최소 {threshold:g}% 여유라는 기존 조건을 만족하는 최대 가격을 환산했습니다.",
    }


def _price_rule(strategy: Any, data: Any, technical: dict[str, Any], condition_state: dict[str, Any] | None) -> dict[str, Any]:
    value = str(_get(strategy, "value", strategy) or "")
    categories: dict[str, tuple[str, ...]] = {
        "breakout": ("high", "ma20", "resistance", "support"),
        "momentum_continuation": ("high", "ma20", "resistance", "support"),
        "volatility_squeeze": ("high", "ma20", "resistance", "support"),
        "pullback": ("support", "ma20", "resistance", "high"),
        "support_bounce": ("support", "resistance", "ma20", "high"),
        "oversold_bounce": ("support", "resistance", "ma20", "high"),
        "range_trading": ("support", "resistance", "ma20", "high"),
        "ma20_rebound": ("ma20", "support", "resistance", "high"),
        "trend_recovery": ("ma20", "high", "support", "resistance"),
        "trend_following": ("ma20", "high", "support", "resistance"),
    }
    order = categories.get(value, ("high", "support", "ma20", "resistance"))
    all_details = _conditions(condition_state)

    def matched(kind: str, item: dict[str, Any]) -> bool:
        raw = str(item.get("raw") or "")
        if kind == "high":
            return bool(re.search(r"20일 고점과 [0-9.]+% 이내", raw))
        if kind == "support":
            return bool(re.search(r"(?:주요 )?지지선과 [0-9.]+% 이내", raw))
        if kind == "ma20":
            return raw in {"현재가가 20일 이동평균선 위", "현재가가 20일선 위", "현재가가 20일선 위로 회복"} or bool(re.search(r"현재가가 20일선과 [0-9.]+% 이내", raw))
        if kind == "resistance":
            return bool(re.search(r"저항까지 최소 [0-9.]+% 여유", raw))
        return False

    for status_first in ("FAIL", None):
        for kind in order:
            candidates = [d for d in all_details if matched(kind, d) and (status_first is None or str(d.get("status")) == status_first)]
            for detail in candidates:
                rule = None
                if kind == "high":
                    rule = _high_rule(
                        detail,
                        data,
                        technical,
                        exact_reference=value in {"breakout", "volatility_squeeze"},
                    )
                elif kind == "support":
                    rule = _support_rule(detail, data, technical)
                elif kind == "ma20":
                    rule = _ma20_rule(detail, data)
                elif kind == "resistance":
                    rule = _resistance_rule(detail, data, technical)
                if rule:
                    return rule

    return {
        "kind": "UNAVAILABLE",
        "label": "가격 기준 계산 불가",
        "status": "UNKNOWN",
        "basis": None,
        "range_low": None,
        "range_high": None,
        "trigger_price": None,
        "reference_price": None,
        "gap_pct": None,
        "message": "현재 Strategy Engine 결과에 직접 환산할 가격 조건이 없어 임의의 진입 가격을 만들지 않습니다.",
    }


def _volume_rule(data: Any, condition_state: dict[str, Any] | None) -> dict[str, Any]:
    detail = _pick_detail(condition_state, lambda item: item.get("metric_key") == "volume_ratio_20" or "거래량" in str(item.get("raw") or ""))
    current = _number(_get(data, "volume_ratio_20"))
    if detail is None:
        return {
            "available": False,
            "status": "NOT_USED",
            "current_ratio": current,
            "required_ratio": None,
            "comparator": None,
            "gap_pct": None,
            "basis": None,
            "message": "이 전략의 현재 핵심 조건에는 별도의 거래량 배수 기준이 없습니다.",
        }
    raw = str(detail.get("raw") or "")
    comparator = None
    required = None
    match = re.search(r"([0-9.]+)배 이상", raw)
    if match:
        comparator = "AT_LEAST"
        required = float(match.group(1))
    match = match or re.search(r"([0-9.]+)배 이하", raw)
    if match and comparator is None:
        comparator = "AT_MOST"
        required = float(match.group(1))
    if required is None and ("평균 이상" in raw):
        comparator, required = "AT_LEAST", 1.0
    if required is None and ("20일 평균 이하" in raw):
        comparator, required = "AT_MOST", 1.0
    if required is None and raw == "거래량 증가":
        comparator, required = "AT_LEAST", 1.2

    gap = None
    if current is not None and required is not None and current > 0:
        if comparator == "AT_LEAST":
            gap = round(max(0.0, required / current - 1.0) * 100.0, 1)
        elif comparator == "AT_MOST":
            gap = round(max(0.0, current / required - 1.0) * 100.0, 1)
    return {
        "available": required is not None,
        "status": detail.get("status") or "UNKNOWN",
        "current_ratio": current,
        "required_ratio": required,
        "comparator": comparator,
        "gap_pct": gap,
        "basis": raw,
        "message": detail.get("detail") or "StockScope가 최근 20일 평균 거래량과 비교합니다.",
    }


def _trend_strength(data: Any, condition_state: dict[str, Any] | None) -> dict[str, Any]:
    detail = _pick_detail(condition_state, lambda item: item.get("metric_key") == "ma20_slope")
    if detail is not None:
        return {
            "available": True,
            "label": "상승 흐름 강도(20일 평균 가격 기울기)",
            "current_value": _number(_get(data, "ma20_slope_pct")),
            "required_value": detail.get("required_value"),
            "status": detail.get("status") or "UNKNOWN",
            "metric_key": "ma20_slope",
            "message": "단순 며칠 상승률을 새로 만들지 않고, 실제 전략이 쓰는 20일 평균 가격의 기울기를 보여줍니다.",
        }
    return {
        "available": False,
        "label": "직접 상승률 기준 없음",
        "current_value": None,
        "required_value": None,
        "status": "NOT_USED",
        "metric_key": None,
        "message": "이 전략은 단순히 ‘몇 % 오르면 진입’이라는 별도 상승률 기준을 사용하지 않습니다. 가격 위치와 다른 실제 전략 조건을 함께 봅니다.",
    }



_ENTRY_TIMING_RELEVANT = {"pullback", "support_bounce", "ma20_rebound", "trend_recovery"}


def _entry_timing_check(entry_timing: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    for bucket in ("confirmed_checks", "failed_checks", "pending_checks"):
        for item in list((entry_timing or {}).get(bucket) or []):
            if str(item.get("key") or "") == key:
                return item
    return None


def _rebound_rule(strategy: Any, data: Any, entry_timing: dict[str, Any] | None) -> dict[str, Any]:
    value = str(_get(strategy, "value", strategy) or "")
    if value not in _ENTRY_TIMING_RELEVANT or not entry_timing:
        return {
            "available": False,
            "status": "NOT_USED",
            "trigger_price": None,
            "gap_pct": None,
            "basis": None,
            "message": "이 전략에서는 Pullback Entry Timing의 반등 확인 가격을 핵심 기준으로 사용하지 않습니다.",
        }

    levels = dict(entry_timing.get("levels") or {})
    rules = dict(entry_timing.get("rules") or {})
    trigger = _number(levels.get("rebound_confirmation"))
    current = _number(_get(data, "current_price"))
    check = _entry_timing_check(entry_timing, "rebound_candle") or {}
    if trigger is None:
        return {
            "available": False,
            "status": str(check.get("status") or "UNKNOWN"),
            "trigger_price": None,
            "gap_pct": None,
            "basis": rules.get("price_rebound"),
            "message": "Entry Timing 엔진이 반등 확인 가격을 계산하지 못해 임의 가격을 만들지 않습니다.",
        }

    return {
        "available": True,
        "status": str(check.get("status") or "UNKNOWN"),
        "trigger_price": round(trigger, 4),
        "gap_pct": 0.0 if current is not None and current >= trigger else _pct_gap(current, trigger),
        "basis": rules.get("price_rebound"),
        "message": str(check.get("explanation") or "기존 Entry Timing 엔진이 관측 가격으로 계산한 반등 확인 기준입니다."),
    }

def _risk_payload(risk_plan: Any, *, decision_reason: str | None) -> dict[str, Any]:
    status = _status_value(_get(risk_plan, "status"))
    reference_only = bool(_get(risk_plan, "reference_only", True)) if risk_plan is not None else True
    invalidation = _number(_get(risk_plan, "invalidation_price"))
    entry = _number(_get(risk_plan, "entry_price"))
    target1 = _number(_get(risk_plan, "target1_price"))
    target2 = _number(_get(risk_plan, "target2_price"))
    risk_pct = _number(_get(risk_plan, "risk_pct"))
    reward1 = _number(_get(risk_plan, "reward1_pct"))
    reward2 = _number(_get(risk_plan, "reward2_pct"))
    final_candidate = decision_reason == "ENTRY_CANDIDATE" and status == "READY" and not reference_only
    return {
        "available": risk_plan is not None and invalidation is not None,
        "status": status,
        "reference_only": reference_only,
        "entry_reference_price": entry,
        "structural_anchor": _number(_get(risk_plan, "structural_anchor")),
        "structural_anchor_label": _get(risk_plan, "structural_anchor_label"),
        "invalidation_price": invalidation,
        "display_invalidation_price": _krx_display_price(invalidation),
        "stop_zone_low": _number(_get(risk_plan, "stop_zone_low")),
        "stop_zone_high": _number(_get(risk_plan, "stop_zone_high")),
        "display_stop_zone_low": _krx_display_price(_number(_get(risk_plan, "stop_zone_low"))),
        "display_stop_zone_high": _krx_display_price(_number(_get(risk_plan, "stop_zone_high"))),
        "target1_price": target1,
        "display_target1_price": _krx_display_price(target1),
        "target1_basis": _get(risk_plan, "target1_basis"),
        "target2_price": target2,
        "display_target2_price": _krx_display_price(target2),
        "target2_basis": _get(risk_plan, "target2_basis"),
        "risk_pct": risk_pct,
        "reward1_pct": reward1,
        "reward2_pct": reward2,
        "rr1": _number(_get(risk_plan, "rr1")),
        "rr2": _number(_get(risk_plan, "rr2")),
        "structure_rating": _get(risk_plan, "structure_rating"),
        "summary": _get(risk_plan, "summary"),
        "warnings": list(_get(risk_plan, "warnings", []) or []),
        "needs_recheck": not final_candidate,
        "basis_label": "현재 조건상 진입 후보 기준" if final_candidate else "현재 확정 종가 기준 참고값",
        "recheck_message": None if final_candidate else "가격·거래량 등 남은 조건이 바뀌면 손절과 목표도 다시 계산해야 합니다.",
    }


def build_entry_risk_guide(
    *,
    strategy: Any,
    data: Any,
    technical: dict[str, Any] | None,
    condition_state: dict[str, Any] | None,
    risk_plan: Any,
    current_state: dict[str, Any] | None,
    historical_verified: bool | None = None,
    historical_status: str | None = None,
    as_of_date: str | None = None,
    entry_timing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    technical = technical or {}
    current_state = current_state or {}
    current_price = _number(_get(data, "current_price"))
    decision_reason = str(current_state.get("decision_reason") or "") or None
    price = _price_rule_semantics(_display_price_rule(_price_rule(strategy, data, technical, condition_state)))
    volume = _volume_rule(data, condition_state)
    trend_strength = _trend_strength(data, condition_state)
    rebound = _rebound_rule(strategy, data, entry_timing)
    risk = _risk_payload(risk_plan, decision_reason=decision_reason)
    risk["target1_audit"] = build_current_target1_audit(
        risk_plan=risk_plan,
        data=data,
        technical=technical,
    )
    price_consistency = _price_plan_consistency(price, risk)
    price_consistency["trace_context"] = {
        "strategy": str(_get(strategy, "value", strategy) or ""),
        "analysis_date": as_of_date,
        "decision_reason": decision_reason,
        "current_price": current_price,
        "strategy_rule_status": price.get("status"),
        "strategy_rule_basis": price.get("basis"),
        "strategy_rule_role": price.get("semantic_role"),
        "risk_status": risk.get("status"),
        "risk_reference_only": risk.get("reference_only"),
        "risk_entry_reference": risk.get("entry_reference_price"),
        "risk_structural_anchor": risk.get("structural_anchor"),
        "risk_structural_anchor_label": risk.get("structural_anchor_label"),
    }

    if decision_reason == "ENTRY_CANDIDATE":
        action_status = "ENTRY_CANDIDATE"
        action_title = "현재 조건상 진입 후보로 검토할 수 있습니다."
        if historical_verified is False:
            action_detail = "현재 전략 조건과 Risk 기준은 통과했습니다. 과거 근거는 아직 검증 전입니다."
        elif historical_status == "INSUFFICIENT":
            action_detail = "현재 전략 조건과 Risk 기준은 통과했지만 과거 검증 표본이 부족합니다. 현재 조건과 과거 근거를 분리해서 판단하세요."
        elif historical_status == "WEAK":
            action_detail = "현재 전략 조건과 Risk 기준은 통과했지만 과거 근거가 약합니다. 현재 조건과 과거 근거를 분리해서 판단하세요."
        elif historical_status == "FAIR":
            action_detail = "현재 전략 조건과 Risk 기준은 통과했습니다. 과거 근거는 혼재되어 있으므로 세부 결과를 함께 확인하세요."
        else:
            action_detail = "현재 전략 조건과 Risk 기준을 통과했습니다. 실제 주문은 자동 실행하지 않습니다."
    elif decision_reason == "RISK_BLOCKED":
        action_status = "RISK_BLOCKED"
        action_title = "조건이 맞아도 현재는 위험 때문에 진입을 보류합니다."
        action_detail = "손절 폭이나 목표 여유가 적절하지 않습니다. 위험 구조가 개선된 뒤 다시 계산합니다."
    else:
        action_status = "WAIT"
        action_title = "지금은 신규 진입하지 마세요."
        action_detail = "아래의 부족한 전략 조건이 바뀐 뒤 StockScope가 전략과 Risk를 다시 계산합니다."

    if historical_verified is True:
        if historical_status == "INSUFFICIENT":
            historical_message = "과거 검증은 실행했지만 표본이 부족합니다."
        elif historical_status == "WEAK":
            historical_message = "과거 검증 결과 근거가 약합니다."
        elif historical_status == "FAIR":
            historical_message = "과거 검증 결과가 혼재되어 있습니다."
        else:
            historical_message = "과거 근거까지 확인했습니다."
    elif historical_verified is False:
        historical_message = "현재 조건 기준 결과이며 과거 근거는 아직 검증 전입니다."
    else:
        historical_message = "과거 검증 상태를 별도로 확인하세요."

    return {
        "strategy": str(_get(strategy, "value", strategy) or ""),
        "as_of_date": as_of_date,
        "current_price": current_price,
        "display_current_price": _krx_display_price(current_price),
        "price_rule": price,
        "volume_rule": volume,
        "trend_strength": trend_strength,
        "rebound_rule": rebound,
        "risk": risk,
        "price_consistency": price_consistency,
        "action": {
            "status": action_status,
            "title": action_title,
            "detail": action_detail,
        },
        "historical_verification": {
            "verified": historical_verified,
            "status": historical_status,
            "message": historical_message,
        },
        "historical_policy": {
            "policy_id": "TARGET1_FULL_EXIT_V1",
            "label": "1차 목표 도달 시 전량 종료",
            "target1_is_exit": True,
            "target2_included": False,
            "target2_label": "2차 확장 목표",
        },
        "guardrail": "표시 가격은 EOD 확정 데이터와 기존 Strategy/Risk Engine을 사람이 이해하기 쉽게 환산한 참고 기준입니다. 자동 주문 가격이 아니며 조건이 바뀌면 다시 계산합니다.",
    }
