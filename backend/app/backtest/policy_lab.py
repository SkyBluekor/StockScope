from __future__ import annotations

from typing import Any

from app.backtest.audit import WIDE_STOP_PCT

POLICY_CURRENT = "CURRENT"
POLICY_BLOCK_ALL_CAUTION = "BLOCK_ALL_CAUTION"
POLICY_BLOCK_WIDE_STOP = "BLOCK_WIDE_STOP"
POLICY_NEAREST_VALID_ANCHOR = "NEAREST_VALID_ANCHOR"

POLICY_DEFINITIONS: dict[str, dict[str, str]] = {
    POLICY_CURRENT: {
        "label": "현재 방식",
        "short": "CAUTION도 진입",
        "description": "현재 StockScope 규칙을 그대로 사용합니다. reference_only만 제외하고 CAUTION은 실제 가상거래에 포함합니다.",
        "problem_target": "비교 기준",
    },
    POLICY_BLOCK_ALL_CAUTION: {
        "label": "CAUTION 전체 제외",
        "short": "경고 거래 모두 차단",
        "description": "Risk Engine이 CAUTION으로 표시한 거래는 이유와 관계없이 모두 진입하지 않습니다.",
        "problem_target": "위험 경고 무시 문제",
    },
    POLICY_BLOCK_WIDE_STOP: {
        "label": "과도한 손절만 제외",
        "short": f"손절거리 {WIDE_STOP_PCT:.0f}% 이상 차단",
        "description": f"현재 Risk Engine의 기존 경고 기준인 진입가 대비 손절거리 {WIDE_STOP_PCT:.0f}% 이상 거래만 제외합니다. 새 임계값을 최적화해서 만든 것이 아닙니다.",
        "problem_target": "지나치게 먼 손절 문제",
    },
    POLICY_NEAREST_VALID_ANCHOR: {
        "label": "더 가까운 유효 지지 사용",
        "short": "주요 지지와 MA20 중 가까운 값",
        "description": "눌림목에서 주요 지지 후보와 MA20이 둘 다 유효하면 진입가에 더 가까운 지지 기준으로 Risk Plan을 다시 계산합니다. 진입 신호 자체를 버리지는 않습니다.",
        "problem_target": "먼 구조적 지지 우선 문제",
    },
}


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _delta(candidate: Any, baseline: Any) -> float | None:
    left = _as_float(candidate)
    right = _as_float(baseline)
    if left is None or right is None:
        return None
    return round(left - right, 3)


def _pct_change_text(value: float | None, unit: str = "%p") -> str:
    if value is None:
        return "비교 불가"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}{unit}"


def _scenario_interpretation(row: dict[str, Any], baseline: dict[str, Any]) -> dict[str, str]:
    policy_id = str(row.get("id") or "")
    metrics = row.get("metrics") or {}
    baseline_metrics = baseline.get("metrics") or {}
    blocked = _as_int(row.get("blocked_by_policy"))
    trades = _as_int(metrics.get("trades"))
    baseline_trades = max(_as_int(baseline_metrics.get("trades")), 1)
    retained = trades / baseline_trades
    expectancy_delta = _delta(metrics.get("expectancy_pct"), baseline_metrics.get("expectancy_pct"))
    mdd_delta = _delta(metrics.get("max_drawdown_pct"), baseline_metrics.get("max_drawdown_pct"))

    if policy_id == POLICY_CURRENT:
        return {
            "status": "BASELINE",
            "headline": "현재 규칙의 비교 기준입니다.",
            "meaning": "다른 정책이 손실 구조를 실제로 줄였는지 판단할 때 이 결과와 비교합니다.",
        }

    if policy_id == POLICY_BLOCK_ALL_CAUTION:
        if blocked > 0 and retained < 0.5:
            return {
                "status": "TOO_AGGRESSIVE",
                "headline": "위험 경고는 줄지만 거래를 너무 많이 없앨 수 있습니다.",
                "meaning": f"현재 방식 대비 거래가 {trades}건으로 줄었습니다. 결과가 좋아져도 CAUTION 전체 차단 효과인지 단순 표본 축소 효과인지 분리해야 합니다.",
            }
        if blocked > 0 and ((expectancy_delta or 0) > 0 or (mdd_delta or 0) > 0):
            return {
                "status": "RESEARCH_CANDIDATE",
                "headline": "CAUTION 차단이 손실 구조를 줄이는 방향은 보입니다.",
                "meaning": f"거래당 평균 변화 {_pct_change_text(expectancy_delta)}, MDD 변화 {_pct_change_text(mdd_delta)}입니다. 다만 어떤 CAUTION 이유가 실제 문제였는지 더 좁혀야 합니다.",
            }
        return {
            "status": "NO_CLEAR_GAIN",
            "headline": "CAUTION 전체 차단만으로는 뚜렷한 해결이 확인되지 않았습니다.",
            "meaning": "경고 거래를 모두 없애는 것보다 문제 원인을 더 좁힌 정책이 필요한지 확인합니다.",
        }

    if policy_id == POLICY_BLOCK_WIDE_STOP:
        if blocked <= 0:
            return {
                "status": "NOT_TRIGGERED",
                "headline": f"{WIDE_STOP_PCT:.0f}% 이상 손절 거래가 없어 이 정책은 결과를 바꾸지 않았습니다.",
                "meaning": "이 종목·기간에서는 과도한 손절거리 자체가 핵심 원인이 아니었다는 뜻입니다.",
            }
        if (expectancy_delta or 0) > 0 or (mdd_delta or 0) > 0:
            return {
                "status": "DIRECT_CANDIDATE",
                "headline": "과도한 손절 거래만 제거했을 때 손실 구조가 개선됐습니다.",
                "meaning": f"{blocked}건만 차단했고 거래당 평균 변화 {_pct_change_text(expectancy_delta)}, MDD 변화 {_pct_change_text(mdd_delta)}입니다. 현재 발견된 -17%형 문제를 가장 직접적으로 겨냥한 비교입니다.",
            }
        return {
            "status": "PROBLEM_REMOVED_BUT_NO_GAIN",
            "headline": "과도한 손절 거래는 제거됐지만 전체 성과 개선은 확인되지 않았습니다.",
            "meaning": "큰 손절 한 건만 막는 것으로 전략의 다른 손실 원인까지 해결되지는 않았습니다.",
        }

    if policy_id == POLICY_NEAREST_VALID_ANCHOR:
        changed = _as_int(row.get("anchor_changed_trades"))
        if changed <= 0:
            return {
                "status": "NOT_TRIGGERED",
                "headline": "더 가까운 MA20으로 바뀔 거래가 없어 결과가 달라지지 않았습니다.",
                "meaning": "현재 표본에서는 주요 지지 우선순위가 실제 문제를 만들지 않았습니다.",
            }
        if (expectancy_delta or 0) > 0 or (mdd_delta or 0) > 0:
            return {
                "status": "DIRECT_CANDIDATE",
                "headline": "신호를 버리지 않고 손절 구조를 가까운 지지 기준으로 바꿨을 때 개선이 보입니다.",
                "meaning": f"{changed}건의 구조적 기준이 바뀌었고 거래당 평균 변화 {_pct_change_text(expectancy_delta)}, MDD 변화 {_pct_change_text(mdd_delta)}입니다. 손절 기준 선택 로직을 검증할 가치가 있습니다.",
            }
        return {
            "status": "NO_CLEAR_GAIN",
            "headline": "가까운 지지를 사용해도 전체 성과가 좋아지지는 않았습니다.",
            "meaning": "손절거리를 줄이는 것만으로는 진입 품질 문제를 해결하지 못했을 가능성이 있습니다.",
        }

    return {"status": "INFO", "headline": "비교 결과", "meaning": "현재 방식과 차이를 확인합니다."}


def build_risk_policy_comparison(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn risk-policy simulations into a problem-solving comparison.

    The function intentionally does *not* pick a production rule by highest return.
    One stock/period can overfit. It only identifies what each controlled experiment
    solved and which candidate deserves broader validation next.
    """

    baseline = next((row for row in scenarios if row.get("id") == POLICY_CURRENT), None)
    if baseline is None:
        return {
            "version": "0.19.5",
            "status": "UNAVAILABLE",
            "headline": "위험 정책 비교 기준을 만들 수 없습니다.",
            "summary": "현재 방식 결과가 없어 대안 정책과 비교하지 않았습니다.",
            "scenarios": scenarios,
            "next_validation_candidate": None,
            "guardrail": "정책 비교는 연구용이며 실제 진입 규칙을 자동 변경하지 않습니다.",
        }

    enriched: list[dict[str, Any]] = []
    baseline_metrics = baseline.get("metrics") or {}
    for row in scenarios:
        metrics = row.get("metrics") or {}
        definition = POLICY_DEFINITIONS.get(str(row.get("id") or ""), {})
        item = {
            **row,
            "label": definition.get("label", str(row.get("id") or "")),
            "short": definition.get("short", ""),
            "description": definition.get("description", ""),
            "problem_target": definition.get("problem_target", ""),
            "delta": {
                "trades": _as_int(metrics.get("trades")) - _as_int(baseline_metrics.get("trades")),
                "expectancy_pctp": _delta(metrics.get("expectancy_pct"), baseline_metrics.get("expectancy_pct")),
                "total_net_return_pctp": _delta(metrics.get("total_net_return_pct"), baseline_metrics.get("total_net_return_pct")),
                "max_drawdown_pctp": _delta(metrics.get("max_drawdown_pct"), baseline_metrics.get("max_drawdown_pct")),
            },
        }
        item["interpretation"] = _scenario_interpretation(item, baseline)
        enriched.append(item)

    baseline_wide = _as_int(baseline.get("wide_stop_trades"))
    baseline_caution = _as_int(baseline.get("caution_trades"))
    candidate: dict[str, Any] | None = None

    by_id = {str(row.get("id")): row for row in enriched}
    wide = by_id.get(POLICY_BLOCK_WIDE_STOP)
    nearest = by_id.get(POLICY_NEAREST_VALID_ANCHOR)
    all_caution = by_id.get(POLICY_BLOCK_ALL_CAUTION)

    # Prefer the narrowest experiment that directly addresses the observed issue.
    for row in [wide, nearest, all_caution]:
        if row is None:
            continue
        status = str((row.get("interpretation") or {}).get("status") or "")
        if status in {"DIRECT_CANDIDATE", "RESEARCH_CANDIDATE"}:
            candidate = {
                "policy_id": row["id"],
                "label": row["label"],
                "reason": (row.get("interpretation") or {}).get("headline"),
                "next_step": "이 종목에 즉시 적용하지 않고 다른 기간·다른 종목에서도 같은 문제 개선이 반복되는지 교차 검증합니다.",
            }
            break

    if baseline_wide > 0:
        headline = "넓은 손절 문제가 실제 손실을 키웠는지 정책별로 분리 비교했습니다."
        summary = (
            f"현재 방식에는 {baseline_wide}건의 과도한 손절 거래와 {baseline_caution}건의 CAUTION 거래가 포함됐습니다. "
            "CAUTION 전체를 지우는 방식과, 문제 거래만 좁혀서 다루는 방식을 같은 신호 데이터로 비교합니다."
        )
    elif baseline_caution > 0:
        headline = "CAUTION 경고를 어느 수준까지 실제 진입에 반영할지 비교했습니다."
        summary = f"현재 방식에는 CAUTION 거래 {baseline_caution}건이 포함됐습니다. 전체 차단과 선택적 차단의 영향을 분리해서 확인합니다."
    else:
        headline = "현재 표본에서는 Risk Engine 경고 거래가 핵심 문제로 나타나지 않았습니다."
        summary = "대안 정책을 같은 조건으로 계산했지만, 위험 경고 차단이 필요한 근거가 있는지 먼저 확인합니다."

    if candidate is None:
        decision = "현재 비교만으로 특정 Risk 정책을 채택할 근거가 부족합니다."
    else:
        decision = f"다음 교차검증 후보는 ‘{candidate['label']}’입니다. 성과가 가장 높아서가 아니라 현재 발견된 문제를 더 좁게 해결했는지를 기준으로 골랐습니다."

    return {
        "version": "0.19.5",
        "status": "COMPARE_ONLY",
        "headline": headline,
        "summary": summary,
        "decision": decision,
        "baseline_problem": {
            "caution_trades": baseline_caution,
            "wide_stop_trades": baseline_wide,
            "wide_stop_threshold_pct": WIDE_STOP_PCT,
        },
        "scenarios": enriched,
        "next_validation_candidate": candidate,
        "guardrail": "이 비교는 정책 후보를 찾는 연구 단계입니다. 한 종목·한 기간에서 수익률이 가장 높다는 이유만으로 실제 Risk 규칙을 자동 변경하지 않습니다.",
    }
