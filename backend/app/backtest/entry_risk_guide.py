from __future__ import annotations

import re
from typing import Any


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
    if number != number:
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
        "target1_price": target1,
        "display_target1_price": _krx_display_price(target1),
        "target2_price": target2,
        "display_target2_price": _krx_display_price(target2),
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
    price = _display_price_rule(_price_rule(strategy, data, technical, condition_state))
    volume = _volume_rule(data, condition_state)
    trend_strength = _trend_strength(data, condition_state)
    rebound = _rebound_rule(strategy, data, entry_timing)
    risk = _risk_payload(risk_plan, decision_reason=decision_reason)

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
