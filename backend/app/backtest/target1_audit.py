from __future__ import annotations

from collections import defaultdict
from math import isfinite
from statistics import mean, median
from typing import Any


TARGET1_POLICY_BASELINE = "BASELINE_STRUCTURAL"
TARGET1_POLICY_CAP_1_5R = "CAP_AT_1_5R"
TARGET1_POLICY_FIXED_1_5R = "FIXED_1_5R"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _compact_date(value: Any) -> str:
    return str(value or "").replace("-", "")


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


def _pct_distance(entry: float | None, target: float | None) -> float | None:
    if entry is None or target is None or entry <= 0:
        return None
    return (target / entry - 1.0) * 100.0


def _risk_multiple(entry: float | None, stop: float | None, target: float | None) -> float | None:
    if entry is None or stop is None or target is None:
        return None
    risk = entry - stop
    if risk <= 0:
        return None
    return (target - entry) / risk


def normalize_target1_basis(value: Any) -> str:
    text = str(value or "").strip()
    if "저항" in text:
        return "RESISTANCE"
    if "20일" in text and "고점" in text:
        return "HIGH20"
    if "1.5R" in text or "1.5" in text and "손익" in text:
        return "RISK_1_5R"
    return "OTHER" if text else "UNKNOWN"


def build_current_target1_audit(*, risk_plan: Any, data: Any, technical: dict[str, Any] | None) -> dict[str, Any]:
    """Independently reconstruct the current RiskEngine Target1 decision.

    This is an audit/trace layer only. It does not mutate the RiskPlan or change the
    production Target1 policy.
    """

    technical = technical or {}
    entry = _number(_get(risk_plan, "entry_price"))
    stop = _number(_get(risk_plan, "invalidation_price"))
    actual = _number(_get(risk_plan, "target1_price"))
    actual_basis_raw = _get(risk_plan, "target1_basis")
    target2 = _number(_get(risk_plan, "target2_price"))

    if entry is None or stop is None or actual is None or entry <= 0 or stop <= 0 or stop >= entry:
        return {
            "available": False,
            "formula_status": "UNAVAILABLE",
            "message": "진입 기준가·손절 기준·1차 목표 중 일부가 없어 Target1 공식을 재검산하지 못했습니다.",
            "entry_reference_price": entry,
            "target1_price": actual,
            "target1_basis": actual_basis_raw,
            "target1_basis_code": normalize_target1_basis(actual_basis_raw),
            "target1_gain_pct": _round(_pct_distance(entry, actual)),
            "target1_r_multiple": _round(_risk_multiple(entry, stop, actual)),
        }

    risk_amount = entry - stop
    one_r = entry + risk_amount
    one_half_r = entry + risk_amount * 1.5
    two_r = entry + risk_amount * 2.0

    resistance = _number(_get(data, "resistance_price"))
    high20 = _number(technical.get("high20"))
    structural: list[tuple[float, str, str]] = []
    if resistance is not None and resistance > entry:
        structural.append((resistance, "최근 저항 후보", "RESISTANCE"))
    if high20 is not None and high20 > entry:
        structural.append((high20, "최근 20일 고점", "HIGH20"))
    structural.sort(key=lambda item: item[0])

    if structural:
        expected, expected_basis, expected_code = structural[0]
    else:
        expected, expected_basis, expected_code = one_half_r, "1.5R 손익 구조 참고", "RISK_1_5R"

    tolerance = max(0.02, abs(expected) * 1e-9)
    price_match = abs(actual - expected) <= tolerance
    basis_code = normalize_target1_basis(actual_basis_raw)
    basis_match = basis_code in {expected_code, "UNKNOWN"}
    formula_status = "MATCH" if price_match and basis_match else "MISMATCH"

    candidates = [
        {
            "kind": code,
            "label": label,
            "price": _round(price),
            "gain_pct": _round(_pct_distance(entry, price)),
            "r_multiple": _round(_risk_multiple(entry, stop, price)),
            "selected": abs(price - actual) <= tolerance,
        }
        for price, label, code in structural
    ]
    candidates.append({
        "kind": "RISK_1_5R",
        "label": "1.5R 손익 구조 참고",
        "price": _round(one_half_r),
        "gain_pct": _round(_pct_distance(entry, one_half_r)),
        "r_multiple": 1.5,
        "selected": not structural and abs(one_half_r - actual) <= tolerance,
    })

    return {
        "available": True,
        "formula_status": formula_status,
        "message": (
            f"현재 Target1은 Risk Engine 공식과 일치합니다. 기준: {expected_basis}."
            if formula_status == "MATCH"
            else f"현재 Target1이 재계산 결과와 다릅니다. 예상 {expected:,.2f}, 실제 {actual:,.2f}."
        ),
        "entry_reference_price": _round(entry),
        "stop_reference_price": _round(stop),
        "risk_amount": _round(risk_amount),
        "risk_pct": _round(risk_amount / entry * 100.0),
        "one_r_price": _round(one_r),
        "one_half_r_price": _round(one_half_r),
        "two_r_price": _round(two_r),
        "target1_price": _round(actual),
        "target1_basis": actual_basis_raw,
        "target1_basis_code": basis_code,
        "target1_gain_pct": _round(_pct_distance(entry, actual)),
        "target1_r_multiple": _round(_risk_multiple(entry, stop, actual)),
        "target2_price": _round(target2),
        "target2_gain_pct": _round(_pct_distance(entry, target2)),
        "target2_r_multiple": _round(_risk_multiple(entry, stop, target2)),
        "expected_target1_price": _round(expected),
        "expected_target1_basis": expected_basis,
        "expected_target1_basis_code": expected_code,
        "structural_candidates": candidates,
        "policy": "가까운 유효 저항/20일 고점을 우선하고, 구조 목표가 없을 때만 1.5R을 사용합니다.",
        "guardrail": "이 감사값은 Target1 계산 근거를 설명하기 위한 진단값이며 Production 목표가격을 변경하지 않습니다.",
    }


def _target_metadata(trade: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(trade.get("metadata") or {})
    audit = dict(metadata.get("audit") or {})
    target = dict(audit.get("target1") or {})
    if not target:
        target = {
            "basis": metadata.get("target1_basis"),
            "price": trade.get("target1_price"),
        }
    return target


def _target_basis_for_trade(trade: dict[str, Any]) -> tuple[str, str]:
    target = _target_metadata(trade)
    raw = str(target.get("basis") or "")
    return normalize_target1_basis(raw), raw or "근거 기록 없음"


def _simulate_exit(
    *,
    rows: list[dict[str, Any]],
    entry_index: int,
    entry_price: float,
    stop_price: float,
    target_price: float,
    max_holding_days: int,
    round_trip_cost_pct: float,
) -> dict[str, Any] | None:
    if not (entry_price > 0 and 0 < stop_price < entry_price < target_price):
        return None
    last_index = min(len(rows) - 1, entry_index + max_holding_days - 1)
    exit_index = last_index
    exit_price: float | None = None
    exit_reason: str | None = None

    for row_index in range(entry_index, last_index + 1):
        row = rows[row_index]
        day_open = _number(row.get("open"))
        day_high = _number(row.get("high"))
        day_low = _number(row.get("low"))

        if row_index > entry_index and day_open is not None:
            if day_open <= stop_price:
                exit_index, exit_price, exit_reason = row_index, day_open, "STOP_GAP"
                break
            if day_open >= target_price:
                exit_index, exit_price, exit_reason = row_index, day_open, "TARGET_1_GAP"
                break

        low_hit = day_low is not None and day_low <= stop_price
        target_hit = day_high is not None and day_high >= target_price
        if low_hit and target_hit:
            exit_index, exit_price, exit_reason = row_index, stop_price, "STOP_SAME_DAY_PRIORITY"
            break
        if low_hit:
            exit_index, exit_price, exit_reason = row_index, stop_price, "STOP"
            break
        if target_hit:
            exit_index, exit_price, exit_reason = row_index, target_price, "TARGET_1"
            break

    if exit_price is None:
        close = _number(rows[last_index].get("close"))
        if close is None:
            return None
        exit_price = close
        exit_reason = "TIME_EXIT" if last_index - entry_index + 1 >= max_holding_days else "END_OF_DATA"

    holding_days = exit_index - entry_index + 1
    gross = (exit_price / entry_price - 1.0) * 100.0
    net = gross - round_trip_cost_pct
    return {
        "exit_index": exit_index,
        "exit_date": _compact_date(rows[exit_index].get("date")),
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "holding_days": holding_days,
        "gross_return_pct": gross,
        "net_return_pct": net,
        "target_hit": str(exit_reason).startswith("TARGET_1"),
        "stop_first": str(exit_reason).startswith("STOP"),
        "time_exit": str(exit_reason) in {"TIME_EXIT", "END_OF_DATA"},
    }


def _policy_metrics(results: list[dict[str, Any]], policy_id: str, label: str) -> dict[str, Any]:
    if not results:
        return {
            "policy_id": policy_id,
            "label": label,
            "sample_count": 0,
            "target_hit_count": 0,
            "target_hit_pct": None,
            "stop_first_count": 0,
            "time_exit_count": 0,
            "average_net_return_pct": None,
            "median_net_return_pct": None,
            "profit_factor": None,
            "closed_trade_max_drawdown_pct": None,
            "average_holding_days": None,
            "average_target_hit_days": None,
        }

    nets = [float(item["net_return_pct"]) for item in results]
    positive = sum(value for value in nets if value > 0)
    negative = abs(sum(value for value in nets if value < 0))
    profit_factor = positive / negative if negative > 0 else None

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for value in nets:
        equity *= 1.0 + value / 100.0
        peak = max(peak, equity)
        drawdown = (equity / peak - 1.0) * 100.0
        max_dd = min(max_dd, drawdown)

    target_hits = [item for item in results if item["target_hit"]]
    return {
        "policy_id": policy_id,
        "label": label,
        "sample_count": len(results),
        "target_hit_count": len(target_hits),
        "target_hit_pct": round(len(target_hits) / len(results) * 100.0, 3),
        "stop_first_count": sum(1 for item in results if item["stop_first"]),
        "time_exit_count": sum(1 for item in results if item["time_exit"]),
        "average_net_return_pct": round(mean(nets), 4),
        "median_net_return_pct": round(median(nets), 4),
        "profit_factor": None if profit_factor is None else round(profit_factor, 4),
        "closed_trade_max_drawdown_pct": round(max_dd, 4),
        "average_holding_days": round(mean(float(item["holding_days"]) for item in results), 3),
        "average_target_hit_days": None if not target_hits else round(mean(float(item["holding_days"]) for item in target_hits), 3),
    }


def build_historical_target1_audit(
    *,
    trades: list[dict[str, Any]],
    stock_rows: list[dict[str, Any]],
    max_holding_days: int = 20,
    round_trip_cost_pct: float = 0.0,
) -> dict[str, Any]:
    """Analyze Target1 distance and replay research-only 1.5R alternatives.

    Alternative policy comparison intentionally reuses the *same observed entries and
    stops*. It does not claim full strategy parity because a different exit date can
    change later signal/occupancy availability. Production policy is never changed.
    """

    rows = sorted(stock_rows, key=lambda row: _compact_date(row.get("date")))
    row_index = {_compact_date(row.get("date")): idx for idx, row in enumerate(rows)}

    distances: list[float] = []
    multiples: list[float] = []
    bases: dict[str, dict[str, Any]] = defaultdict(lambda: {"sample_count": 0, "distances": [], "multiples": []})
    bins = {
        "0~5%": 0,
        "5~10%": 0,
        "10~15%": 0,
        "15% 이상": 0,
    }
    replay: dict[str, list[dict[str, Any]]] = {
        TARGET1_POLICY_BASELINE: [],
        TARGET1_POLICY_CAP_1_5R: [],
        TARGET1_POLICY_FIXED_1_5R: [],
    }
    skipped = 0

    for trade in trades:
        entry = _number(trade.get("entry_price"))
        stop = _number(trade.get("stop_price"))
        baseline_target = _number(trade.get("target1_price"))
        entry_date = _compact_date(trade.get("entry_date"))
        idx = row_index.get(entry_date)
        if entry is None or stop is None or baseline_target is None or idx is None or not (0 < stop < entry < baseline_target):
            skipped += 1
            continue

        distance = _pct_distance(entry, baseline_target)
        multiple = _risk_multiple(entry, stop, baseline_target)
        if distance is not None:
            distances.append(distance)
            if distance < 5:
                bins["0~5%"] += 1
            elif distance < 10:
                bins["5~10%"] += 1
            elif distance < 15:
                bins["10~15%"] += 1
            else:
                bins["15% 이상"] += 1
        if multiple is not None:
            multiples.append(multiple)

        basis_code, basis_label = _target_basis_for_trade(trade)
        group = bases[basis_code]
        group["label"] = basis_label
        group["sample_count"] += 1
        if distance is not None:
            group["distances"].append(distance)
        if multiple is not None:
            group["multiples"].append(multiple)

        risk = entry - stop
        one_half_r = entry + risk * 1.5
        policy_targets = {
            TARGET1_POLICY_BASELINE: baseline_target,
            TARGET1_POLICY_CAP_1_5R: min(baseline_target, one_half_r),
            TARGET1_POLICY_FIXED_1_5R: one_half_r,
        }
        for policy_id, target in policy_targets.items():
            result = _simulate_exit(
                rows=rows,
                entry_index=idx,
                entry_price=entry,
                stop_price=stop,
                target_price=target,
                max_holding_days=max_holding_days,
                round_trip_cost_pct=round_trip_cost_pct,
            )
            if result is not None:
                result.update({
                    "entry_date": entry_date,
                    "entry_price": entry,
                    "stop_price": stop,
                    "target1_price": target,
                    "target1_distance_pct": _pct_distance(entry, target),
                    "target1_r_multiple": _risk_multiple(entry, stop, target),
                })
                replay[policy_id].append(result)

    basis_summary: list[dict[str, Any]] = []
    for code, group in bases.items():
        group_distances = list(group["distances"])
        group_multiples = list(group["multiples"])
        basis_summary.append({
            "basis_code": code,
            "label": group.get("label"),
            "sample_count": int(group["sample_count"]),
            "average_target_distance_pct": None if not group_distances else round(mean(group_distances), 4),
            "average_target_r_multiple": None if not group_multiples else round(mean(group_multiples), 4),
        })
    basis_summary.sort(key=lambda item: int(item["sample_count"]), reverse=True)

    baseline_results = replay[TARGET1_POLICY_BASELINE]
    baseline_hits = [item for item in baseline_results if item["target_hit"]]
    hit_counts = {
        "within_5_days": sum(1 for item in baseline_hits if int(item["holding_days"]) <= 5),
        "within_10_days": sum(1 for item in baseline_hits if int(item["holding_days"]) <= 10),
        "within_20_days": sum(1 for item in baseline_hits if int(item["holding_days"]) <= 20),
    }

    policy_comparison = [
        _policy_metrics(replay[TARGET1_POLICY_BASELINE], TARGET1_POLICY_BASELINE, "기존 구조적 Target1"),
        _policy_metrics(replay[TARGET1_POLICY_CAP_1_5R], TARGET1_POLICY_CAP_1_5R, "구조 목표와 1.5R 중 가까운 값"),
        _policy_metrics(replay[TARGET1_POLICY_FIXED_1_5R], TARGET1_POLICY_FIXED_1_5R, "1.5R 고정 1차 목표"),
    ]

    return {
        "available": bool(baseline_results),
        "sample_count": len(baseline_results),
        "skipped_trades": skipped,
        "max_holding_days": max_holding_days,
        "average_target_distance_pct": None if not distances else round(mean(distances), 4),
        "median_target_distance_pct": None if not distances else round(median(distances), 4),
        "average_target_r_multiple": None if not multiples else round(mean(multiples), 4),
        "median_target_r_multiple": None if not multiples else round(median(multiples), 4),
        "target_hit_count": len(baseline_hits),
        "target_hit_pct": None if not baseline_results else round(len(baseline_hits) / len(baseline_results) * 100.0, 3),
        "target_hit_days": hit_counts,
        "average_target_hit_days": None if not baseline_hits else round(mean(float(item["holding_days"]) for item in baseline_hits), 3),
        "median_target_hit_days": None if not baseline_hits else round(median(float(item["holding_days"]) for item in baseline_hits), 3),
        "stop_first_count": sum(1 for item in baseline_results if item["stop_first"]),
        "time_exit_count": sum(1 for item in baseline_results if item["time_exit"]),
        "distance_bins": [{"label": label, "sample_count": count} for label, count in bins.items()],
        "basis_summary": basis_summary,
        "policy_comparison": policy_comparison,
        "comparison_mode": "SAME_ENTRY_SAME_STOP_REPLAY",
        "comparison_limitations": [
            "대안 정책은 동일 진입일·동일 진입가·동일 손절을 고정한 연구용 재생입니다.",
            "목표가 변경으로 청산일이 달라지면 이후 신규 신호의 진입 가능 시점도 달라질 수 있으므로 Production 정책 선택용 완전 백테스트와 동일하지 않습니다.",
            "Target1 도달 비율은 과거 관측값이며 미래 성공 확률이 아닙니다.",
        ],
        "guardrail": "Target1 현실성 감사는 기존 Production Target1 공식을 자동 변경하지 않습니다.",
    }
