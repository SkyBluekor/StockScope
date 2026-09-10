from __future__ import annotations

from typing import Any

from app.backtest.models import BacktestConfig

WIDE_STOP_PCT = 12.0
TOLERANCE_PCT = 0.0002


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _close(a: float | None, b: float | None, tolerance: float = TOLERANCE_PCT) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tolerance


def _trade_audit(trade: dict[str, Any]) -> dict[str, Any]:
    metadata = trade.get("metadata") or {}
    audit = metadata.get("audit") if isinstance(metadata, dict) else None
    return audit if isinstance(audit, dict) else {}


def _flagged_trade(trade: dict[str, Any]) -> dict[str, Any]:
    audit = _trade_audit(trade)
    risk = audit.get("risk") if isinstance(audit.get("risk"), dict) else {}
    entry = audit.get("entry") if isinstance(audit.get("entry"), dict) else {}
    flags = audit.get("flags") if isinstance(audit.get("flags"), list) else []

    entry_price = _as_float(trade.get("entry_price"))
    stop_price = _as_float(trade.get("stop_price"))
    stop_distance = _as_float(risk.get("initial_stop_distance_pct"))
    anchor_distance = _as_float(risk.get("anchor_distance_from_entry_pct"))
    atr_buffer = _as_float(risk.get("atr_buffer_from_anchor_pct"))
    signal_ma20 = _as_float(risk.get("signal_ma20"))

    cause_parts: list[str] = []
    anchor_label = str(risk.get("structural_anchor_label") or "구조적 기준")
    if anchor_distance is not None:
        cause_parts.append(f"{anchor_label}이 진입가보다 약 {anchor_distance:.2f}% 아래에 있었습니다.")
    if atr_buffer is not None and atr_buffer > 0:
        cause_parts.append(f"여기에 ATR 변동성 여유 약 {atr_buffer:.2f}%가 추가됐습니다.")
    structural_anchor = _as_float(risk.get("structural_anchor"))
    if entry_price and structural_anchor is not None:
        if signal_ma20 is not None and 0 < signal_ma20 < entry_price and signal_ma20 > structural_anchor:
            ma20_distance = (entry_price - signal_ma20) / entry_price * 100.0
            cause_parts.append(
                f"신호일 MA20은 진입가보다 약 {ma20_distance:.2f}% 아래로 더 가까웠지만, 현재 눌림목 Risk Engine은 유효한 주요 지지 후보가 있으면 MA20보다 그 지지값을 우선합니다."
            )
    if str(trade.get("risk_plan_status") or "") == "CAUTION":
        cause_parts.append("Risk Engine은 이 구조를 CAUTION으로 표시했지만 현재 백테스트는 CAUTION 자체를 진입 차단 조건으로 사용하지 않습니다.")
    if not cause_parts:
        cause_parts.append("거래 상세의 신호·진입·Risk Engine 입력값을 확인해야 합니다.")

    return {
        "signal_date": trade.get("signal_date"),
        "entry_date": trade.get("entry_date"),
        "entry_price": entry_price,
        "signal_close": _as_float(entry.get("signal_close")),
        "entry_gap_pct": _as_float(entry.get("gap_from_signal_close_pct")),
        "stop_price": stop_price,
        "stop_distance_pct": stop_distance,
        "risk_plan_status": trade.get("risk_plan_status"),
        "structure_rating": risk.get("structure_rating"),
        "structural_anchor": _as_float(risk.get("structural_anchor")),
        "structural_anchor_label": risk.get("structural_anchor_label"),
        "signal_ma20": signal_ma20,
        "anchor_distance_from_entry_pct": anchor_distance,
        "atr_pct": _as_float(risk.get("atr_pct")),
        "atr_value_at_entry": _as_float(risk.get("atr_value_at_entry")),
        "buffer_factor": _as_float(risk.get("buffer_factor")),
        "flags": flags,
        "cause": " ".join(cause_parts),
    }


def build_accuracy_audit(
    result: dict[str, Any],
    config: BacktestConfig,
    *,
    signal_boundary_violations: int = 0,
    research_overlap_pairs: int = 0,
) -> dict[str, Any]:
    """Audit the backtest execution without changing any trading rule.

    v0.19.4 is deliberately diagnostic. A warning here never changes entry, stop,
    target, position sizing, or an already simulated trade.
    """

    trades = list(result.get("trades") or [])
    checks: list[dict[str, Any]] = []

    # 1) Historical signal boundary: this is gathered while snapshots are frozen.
    checks.append({
        "id": "FUTURE_DATA_BOUNDARY",
        "status": "PASS" if signal_boundary_violations == 0 else "FAIL",
        "title": "신호 계산에 미래 데이터가 섞였는가?",
        "detail": (
            "모든 신호 계산 구간의 마지막 날짜가 신호일을 넘지 않았습니다."
            if signal_boundary_violations == 0
            else f"신호일 이후 데이터가 포함된 계산 구간 {signal_boundary_violations}건을 발견했습니다."
        ),
    })

    next_open_mismatches = 0
    return_math_mismatches = 0
    reference_only_trades = 0
    wide_stop_trades: list[dict[str, Any]] = []
    caution_trades: list[dict[str, Any]] = []
    gap_stop_trades = 0
    same_day_conflicts = 0

    for trade in trades:
        audit = _trade_audit(trade)
        entry = audit.get("entry") if isinstance(audit.get("entry"), dict) else {}
        execution = audit.get("execution") if isinstance(audit.get("execution"), dict) else {}
        risk = audit.get("risk") if isinstance(audit.get("risk"), dict) else {}

        if not bool(entry.get("next_trading_day_open_verified")):
            next_open_mismatches += 1

        entry_price = _as_float(trade.get("entry_price"))
        exit_price = _as_float(trade.get("exit_price"))
        gross = _as_float(trade.get("gross_return_pct"))
        net = _as_float(trade.get("net_return_pct"))
        if entry_price and exit_price and entry_price > 0:
            expected_gross = (exit_price / entry_price - 1.0) * 100.0
            expected_net = expected_gross - float(config.round_trip_cost_pct)
            if not _close(gross, expected_gross) or not _close(net, expected_net):
                return_math_mismatches += 1
        else:
            return_math_mismatches += 1

        if bool(risk.get("reference_only")):
            reference_only_trades += 1

        stop_distance = _as_float(risk.get("initial_stop_distance_pct"))
        if stop_distance is not None and stop_distance >= WIDE_STOP_PCT:
            wide_stop_trades.append(trade)

        if str(trade.get("risk_plan_status") or "") == "CAUTION":
            caution_trades.append(trade)

        reason = str(trade.get("exit_reason") or "")
        if reason == "STOP_GAP":
            gap_stop_trades += 1
        if reason == "STOP_SAME_DAY_PRIORITY":
            same_day_conflicts += 1

    checks.append({
        "id": "NEXT_TRADING_DAY_OPEN",
        "status": "PASS" if next_open_mismatches == 0 else "FAIL",
        "title": "진입 가격은 다음 거래일 시가인가?",
        "detail": (
            "실제 규칙 거래는 모두 신호 다음 거래일의 시가로 진입했습니다."
            if next_open_mismatches == 0
            else f"다음 거래일 시가 규칙과 일치하지 않는 거래가 {next_open_mismatches}건 있습니다."
        ),
    })

    checks.append({
        "id": "RETURN_MATH",
        "status": "PASS" if return_math_mismatches == 0 else "FAIL",
        "title": "Gross/Net 손익 계산이 맞는가?",
        "detail": (
            f"모든 거래에서 (청산가 ÷ 진입가 - 1)과 왕복 비용 {config.round_trip_cost_pct:.3f}% 차감 계산이 일치했습니다."
            if return_math_mismatches == 0
            else f"손익 재계산과 일치하지 않는 거래가 {return_math_mismatches}건 있습니다."
        ),
    })

    checks.append({
        "id": "REFERENCE_ONLY_BLOCK",
        "status": "PASS" if reference_only_trades == 0 else "FAIL",
        "title": "참고용 Risk Plan이 실제 거래에 들어갔는가?",
        "detail": (
            "reference_only로 표시된 Risk Plan은 실제 규칙 거래에 포함되지 않았습니다."
            if reference_only_trades == 0
            else f"reference_only Risk Plan이 포함된 거래가 {reference_only_trades}건 있습니다."
        ),
    })

    checks.append({
        "id": "WIDE_STOP",
        "status": "WARN" if wide_stop_trades else "PASS",
        "title": "손절 기준이 지나치게 먼 거래가 있는가?",
        "detail": (
            f"진입가 대비 손절 거리가 {WIDE_STOP_PCT:.0f}% 이상인 거래가 {len(wide_stop_trades)}건 있습니다. 계산 오류인지, 구조적 지지선이 너무 먼 것인지 거래별 근거를 확인해야 합니다."
            if wide_stop_trades
            else f"실제 규칙 거래 중 진입가 대비 {WIDE_STOP_PCT:.0f}% 이상 떨어진 손절 기준은 없었습니다."
        ),
    })

    checks.append({
        "id": "CAUTION_PLAN_EXECUTION",
        "status": "WARN" if caution_trades else "PASS",
        "title": "Risk Engine이 경고한 구조도 진입했는가?",
        "detail": (
            f"Risk Engine 상태가 CAUTION인 거래가 {len(caution_trades)}건 실제 거래에 포함됐습니다. 현재 백테스트는 reference_only만 차단하고 CAUTION은 진입을 허용하는 정책입니다."
            if caution_trades
            else "실제 규칙 거래에는 CAUTION Risk Plan이 포함되지 않았습니다."
        ),
    })

    checks.append({
        "id": "ENTRY_TIMING_RESEARCH_INDEPENDENCE",
        "status": "INFO",
        "title": "3/7~7/7 연구 표본은 서로 독립적인가?",
        "detail": (
            f"각 조건 수는 별도 가상 전략으로 계산하며, 서로 다른 코호트 사이에서 보유 구간이 겹친 사례가 {research_overlap_pairs}쌍 있습니다. 따라서 3/7~7/7 결과를 서로 독립 표본처럼 합쳐 해석하면 안 됩니다."
            if research_overlap_pairs > 0
            else "3/7~7/7은 서로 다른 가상 진입 규칙의 비교 코호트입니다. 표본 수를 서로 합쳐 하나의 독립 표본처럼 해석하지 않습니다."
        ),
    })

    checks.append({
        "id": "EXIT_EDGE_CASES",
        "status": "INFO",
        "title": "일봉만으로 체결 순서를 알 수 없는 경우는 어떻게 처리했나?",
        "detail": f"갭 하락 손절 {gap_stop_trades}건, 같은 일봉에서 손절·목표가가 모두 닿아 손절 우선 처리한 거래 {same_day_conflicts}건입니다.",
    })

    hard_failures = [check for check in checks if check["status"] == "FAIL"]
    warnings = [check for check in checks if check["status"] == "WARN"]
    flagged = []
    seen: set[tuple[Any, Any]] = set()
    for trade in [*wide_stop_trades, *caution_trades]:
        key = (trade.get("signal_date"), trade.get("entry_date"))
        if key in seen:
            continue
        seen.add(key)
        flagged.append(_flagged_trade(trade))

    if hard_failures:
        status = "FAILED"
        label = "정확성 오류 발견"
        headline = "백테스트 계산 경로에서 수정이 필요한 오류를 발견했습니다."
        summary = "전략 개선보다 계산 오류 수정이 먼저입니다. v0.19.4는 오류를 숨기거나 거래 규칙을 자동 변경하지 않습니다."
    elif warnings:
        status = "REVIEW_REQUIRED"
        label = "정책 검토 필요"
        if wide_stop_trades:
            headline = f"손절 기준이 비정상적으로 넓은 거래 {len(wide_stop_trades)}건의 원인을 확인해야 합니다."
        else:
            headline = "계산은 일관되지만 Risk Engine 경고와 백테스트 진입 정책 사이를 검토해야 합니다."
        summary = "산술 오류로 단정할 상태는 아니며, 구조적 지지·ATR·Risk Plan 상태가 어떻게 실제 진입으로 이어졌는지 거래별 계산 근거를 확인합니다."
    else:
        status = "PASS"
        label = "계산 경로 이상 없음"
        headline = "현재 거래 표본에서는 백테스트 실행 규칙과 손익 계산의 불일치를 찾지 못했습니다."
        summary = "이 결과는 전략이 좋다는 뜻이 아니라, 현재 구현이 정한 백테스트 규칙대로 계산됐다는 뜻입니다."

    return {
        "version": "0.19.4",
        "status": status,
        "label": label,
        "headline": headline,
        "summary": summary,
        "checks": checks,
        "flagged_trades": flagged,
        "policy_observation": (
            "현재 실제 거래 생성은 reference_only Risk Plan을 제외하지만 CAUTION 상태 자체는 차단하지 않습니다. "
            "따라서 구조적으로 손절 폭이 매우 넓어 Risk Engine이 경고한 경우에도 가상 거래가 생성될 수 있습니다."
        ),
        "research_observation": (
            "3/7~7/7은 대안 진입 규칙을 각각 따로 시뮬레이션한 연구 코호트입니다. "
            "서로 같은 시장 구간을 공유할 수 있으므로 결과를 합쳐 독립 표본처럼 취급하지 않습니다."
        ),
        "guardrail": "v0.19.4는 진단 전용입니다. 손절 상한, 진입 조건, 시장 필터, Strategy Score 공식은 변경하지 않았습니다.",
        "counts": {
            "trades": len(trades),
            "wide_stop_trades": len(wide_stop_trades),
            "caution_plan_trades": len(caution_trades),
            "future_data_boundary_violations": signal_boundary_violations,
            "next_open_mismatches": next_open_mismatches,
            "return_math_mismatches": return_math_mismatches,
            "research_overlap_pairs": research_overlap_pairs,
        },
    }
