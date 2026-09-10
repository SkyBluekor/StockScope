from __future__ import annotations

from datetime import date
from typing import Any

from app.backtest.models import BacktestConfig


REGIME_LABELS = {
    "TREND_UP": "상승장",
    "RANGE": "횡보장",
    "TREND_DOWN": "하락장",
    "HIGH_VOLATILITY": "고변동성",
    "PANIC": "패닉",
    "UNKNOWN": "판단 보류",
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


def _fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{digits}f}%"


def _fmt_plain_pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}%"


def _period_years(start: str, end: str) -> float:
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError:
        return 0.0
    return max(0.0, (end_date - start_date).days / 365.2425)


def _confidence(trades: int) -> dict[str, str]:
    if trades < 10:
        return {
            "level": "VERY_LOW",
            "label": "매우 낮음",
            "reason": f"실제 규칙 거래가 {trades}건뿐이라 종목·기간별 우연의 영향을 크게 받을 수 있습니다.",
        }
    if trades < 30:
        return {
            "level": "LOW",
            "label": "낮음",
            "reason": f"실제 규칙 거래가 {trades}건으로 방향성은 볼 수 있지만 규칙을 바꿀 만큼 충분한 표본은 아닙니다.",
        }
    if trades < 60:
        return {
            "level": "MEDIUM",
            "label": "보통",
            "reason": f"실제 규칙 거래가 {trades}건으로 반복 패턴을 비교할 수 있는 수준입니다. 다른 기간·종목 검증은 여전히 필요합니다.",
        }
    return {
        "level": "HIGH",
        "label": "높음",
        "reason": f"실제 규칙 거래가 {trades}건으로 이 종목·기간 안에서는 비교적 충분한 표본입니다. 다른 기간·종목 재현 여부가 최종 확인 단계입니다.",
    }


def _performance(summary: dict[str, Any]) -> dict[str, str]:
    trades = _as_int(summary.get("trades"))
    expectancy = _as_float(summary.get("expectancy_pct"))
    profit_factor = _as_float(summary.get("profit_factor"))
    win_rate = _as_float(summary.get("win_rate_pct"))
    if trades == 0 or expectancy is None:
        return {
            "level": "UNKNOWN",
            "label": "판단 보류",
            "reason": "실제 진입 규칙으로 종료된 거래가 없어 성과를 평가할 수 없습니다.",
        }
    if expectancy > 0.5 and (profit_factor is None or profit_factor >= 1.2):
        return {
            "level": "GOOD",
            "label": "양호한 편",
            "reason": f"거래당 평균 Net {_fmt_pct(expectancy)}이고 승률은 {_fmt_plain_pct(win_rate, 1)}입니다. 표본 신뢰도와 함께 해석해야 합니다.",
        }
    if expectancy > 0 and (profit_factor is None or profit_factor >= 1.0):
        return {
            "level": "MIXED_POSITIVE",
            "label": "소폭 양호",
            "reason": f"거래당 평균 Net은 {_fmt_pct(expectancy)}로 양수지만 우위가 크지 않아 추가 검증이 필요합니다.",
        }
    if expectancy < 0 and (profit_factor is None or profit_factor < 1.0):
        pf_text = "-" if profit_factor is None else f"{profit_factor:.2f}"
        return {
            "level": "WEAK",
            "label": "부진",
            "reason": f"거래당 평균 Net {_fmt_pct(expectancy)}, Profit Factor {pf_text}로 현재 표본에서는 손실 쪽으로 기울었습니다.",
        }
    return {
        "level": "MIXED",
        "label": "혼합",
        "reason": "승률·평균손익·손익구조가 같은 방향을 가리키지 않아 한 지표만으로 결론내리기 어렵습니다.",
    }


def _risk(summary: dict[str, Any]) -> dict[str, str]:
    mdd = _as_float(summary.get("max_drawdown_pct"))
    loss_streak = _as_int(summary.get("max_consecutive_losses"))
    if mdd is None:
        return {"level": "UNKNOWN", "label": "판단 보류", "reason": "최대 낙폭을 계산할 표본이 없습니다."}
    if mdd <= -20:
        label, level = "매우 높음", "VERY_HIGH"
    elif mdd <= -10:
        label, level = "높음", "HIGH"
    elif mdd <= -5:
        label, level = "보통", "MEDIUM"
    else:
        label, level = "낮은 편", "LOW"
    streak_text = f" 최대 연속 손실은 {loss_streak}회입니다." if loss_streak else ""
    return {
        "level": level,
        "label": label,
        "reason": f"일별 평가자산 기준 최대 낙폭은 {_fmt_pct(mdd)}입니다.{streak_text}",
    }


def _best_timing_candidate(rows: list[dict[str, Any]], actual_expectancy: float | None) -> dict[str, Any] | None:
    viable = []
    for row in rows:
        trades = _as_int(row.get("trades"))
        expectancy = _as_float(row.get("expectancy_pct"))
        profit_factor = _as_float(row.get("profit_factor"))
        if trades < 5 or expectancy is None:
            continue
        viable.append((expectancy, trades, profit_factor, row))
    if not viable:
        return None
    viable.sort(key=lambda item: (item[0], item[1]), reverse=True)
    expectancy, trades, profit_factor, row = viable[0]
    if expectancy <= 0:
        return None
    improvement = None if actual_expectancy is None else expectancy - actual_expectancy
    if actual_expectancy is not None and improvement < 0.75:
        return None
    return {
        "entry_timing": str(row.get("entry_timing") or ""),
        "trades": trades,
        "expectancy_pct": round(expectancy, 3),
        "profit_factor": profit_factor,
        "improvement_vs_actual_pctp": None if improvement is None else round(improvement, 3),
    }


def _regime_signal(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = []
    for row in rows:
        trades = _as_int(row.get("trades"))
        expectancy = _as_float(row.get("expectancy_pct"))
        if trades < 1 or expectancy is None:
            continue
        usable.append((expectancy, trades, row))
    if not usable:
        return None
    worst = min(usable, key=lambda item: item[0])
    best = max(usable, key=lambda item: item[0])
    if worst[0] >= 0:
        return None
    if best[0] - worst[0] < 2.0:
        return None
    return {
        "best": {
            "regime": str(best[2].get("key") or "UNKNOWN"),
            "label": REGIME_LABELS.get(str(best[2].get("key") or "UNKNOWN"), str(best[2].get("key") or "UNKNOWN")),
            "trades": best[1],
            "expectancy_pct": round(best[0], 3),
        },
        "worst": {
            "regime": str(worst[2].get("key") or "UNKNOWN"),
            "label": REGIME_LABELS.get(str(worst[2].get("key") or "UNKNOWN"), str(worst[2].get("key") or "UNKNOWN")),
            "trades": worst[1],
            "expectancy_pct": round(worst[0], 3),
        },
    }


def _stop_signal(trades: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(trades) < 3:
        return None
    stop_trades = [trade for trade in trades if str(trade.get("exit_reason") or "").startswith("STOP")]
    if len(stop_trades) / len(trades) < 0.6:
        return None
    distances: list[float] = []
    for trade in stop_trades:
        entry = _as_float(trade.get("entry_price"))
        stop = _as_float(trade.get("stop_price"))
        if entry and stop and entry > 0 and 0 < stop < entry:
            distances.append((entry - stop) / entry * 100.0)
    avg_distance = sum(distances) / len(distances) if distances else None
    return {
        "stop_trades": len(stop_trades),
        "total_trades": len(trades),
        "stop_rate_pct": round(len(stop_trades) / len(trades) * 100.0, 1),
        "average_initial_stop_distance_pct": None if avg_distance is None else round(avg_distance, 2),
    }


def build_problem_solver(result: dict[str, Any], config: BacktestConfig) -> dict[str, Any]:
    summary = result.get("summary") or {}
    actual_trades = _as_int(summary.get("trades"))
    expectancy = _as_float(summary.get("expectancy_pct"))
    confidence = _confidence(actual_trades)
    performance = _performance(summary)
    risk = _risk(summary)
    period_years = _period_years(config.start_date, config.end_date)
    timing = _best_timing_candidate(result.get("entry_timing_research") or [], expectancy)
    regime = _regime_signal(result.get("market_regime_performance") or [])
    stop = _stop_signal(result.get("trades") or [])
    risk_policy_comparison = result.get("risk_policy_comparison") or {}
    risk_policy_candidate = risk_policy_comparison.get("next_validation_candidate") or None
    risk_policy_scenarios = {
        str(item.get("id") or ""): item
        for item in (risk_policy_comparison.get("scenarios") or [])
        if isinstance(item, dict)
    }

    problems: list[dict[str, Any]] = []
    next_actions: list[dict[str, Any]] = []

    if actual_trades < 10:
        target_years = 3 if period_years < 2.75 else 5
        problems.append({
            "id": "LOW_SAMPLE",
            "priority": 1,
            "severity": "HIGH",
            "title": "거래 표본이 너무 적습니다",
            "evidence": f"현재 실제 규칙 거래는 {actual_trades}건입니다.",
            "meaning": "몇 번의 우연한 성공·실패가 전체 결과를 크게 흔들 수 있어 전략 자체의 좋고 나쁨을 판단하기 어렵습니다.",
            "solution": f"같은 규칙을 약 {target_years}년으로 넓혀 더 많은 시장 상황과 진입 사례에서 다시 검증합니다.",
        })
        next_actions.append({
            "id": "EXPAND_PERIOD",
            "type": "RERUN_PERIOD",
            "label": f"{target_years}년으로 다시 검증",
            "description": "현재 설정은 그대로 두고 검증 기간만 자동으로 넓힙니다.",
            "years": target_years,
            "priority": 1,
        })

    if actual_trades > 0 and performance["level"] == "WEAK":
        problems.append({
            "id": "NEGATIVE_EXPECTANCY",
            "priority": 2,
            "severity": "HIGH" if actual_trades >= 10 else "MEDIUM",
            "title": "현재 진입 규칙의 손익 구조가 좋지 않습니다",
            "evidence": f"거래당 평균 Net은 {_fmt_pct(expectancy)}, 승률은 {_fmt_plain_pct(_as_float(summary.get('win_rate_pct')), 1)}입니다.",
            "meaning": "현재 종목·기간에서는 이 규칙을 그대로 반복했을 때 평균적으로 유리했다고 보기 어렵습니다.",
            "solution": "진입 타이밍과 시장환경 중 어느 조건에서 손실이 줄어드는지 분리해서 비교한 뒤 개선 후보를 좁힙니다.",
        })

    if stop is not None:
        distance_text = ""
        if stop.get("average_initial_stop_distance_pct") is not None:
            distance_text = f" 평균 초기 손절 거리는 약 {stop['average_initial_stop_distance_pct']:.2f}%였습니다."

        if risk_policy_candidate is not None:
            candidate_id = str(risk_policy_candidate.get("policy_id") or "")
            candidate_row = risk_policy_scenarios.get(candidate_id) or {}
            delta = candidate_row.get("delta") or {}
            expectancy_delta = _as_float(delta.get("expectancy_pctp"))
            mdd_delta = _as_float(delta.get("max_drawdown_pctp"))
            policy_label = str(risk_policy_candidate.get("label") or "위험 정책 후보")
            problems.append({
                "id": "RISK_POLICY_CANDIDATE",
                "priority": 3,
                "severity": "MEDIUM",
                "title": "손절 문제를 줄일 정책 후보를 실제 비교로 좁혔습니다",
                "evidence": (
                    f"실제 거래 {stop['total_trades']}건 중 {stop['stop_trades']}건({stop['stop_rate_pct']:.1f}%)이 손절 계열 종료였습니다.{distance_text} "
                    f"'{policy_label}' 실험은 현재 방식 대비 거래당 평균 {_fmt_pct(expectancy_delta)}p, MDD {_fmt_pct(mdd_delta)}p 변화를 보였습니다."
                ),
                "meaning": "단순히 손절이 많다고 끝내지 않고, CAUTION 전체 차단·과도한 손절만 차단·더 가까운 지지 사용을 같은 신호에 적용해 어떤 정책이 문제를 직접 줄이는지 비교했습니다.",
                "solution": str(risk_policy_candidate.get("next_step") or "한 종목 결과로 즉시 규칙을 바꾸지 않고 다른 기간·종목에서 재현성을 확인합니다."),
            })
            next_actions.append({
                "id": "VIEW_RISK_POLICY",
                "type": "VIEW_SECTION",
                "section": "risk-policy-analysis",
                "label": "손절 정책 비교 보기",
                "description": "어떤 위험 정책이 손실 문제를 실제로 줄였는지 비교합니다.",
                "priority": 2,
            })
        else:
            problems.append({
                "id": "STOP_DOMINANCE",
                "priority": 3,
                "severity": "MEDIUM",
                "title": "손절 종료가 반복되고 있습니다",
                "evidence": f"실제 거래 {stop['total_trades']}건 중 {stop['stop_trades']}건({stop['stop_rate_pct']:.1f}%)이 손절 계열 종료였습니다.{distance_text}",
                "meaning": "진입이 반등 확인보다 늦거나, 현재 무효화 기준과 이 종목의 변동성이 맞지 않을 가능성을 먼저 의심할 수 있습니다.",
                "solution": "우선 진입 타이밍 연구 결과를 비교하고, 같은 현상이 충분한 표본에서도 반복되면 손절 거리별 별도 검증을 다음 실험으로 진행합니다.",
            })

    if timing is not None:
        caveat = "표본이 아직 작아 규칙 변경이 아니라 추가 검증 후보입니다." if timing["trades"] < 20 or actual_trades < 30 else "반복 표본이 있어 별도 후보 규칙 백테스트를 진행할 가치가 있습니다."
        problems.append({
            "id": "TIMING_CANDIDATE",
            "priority": 4,
            "severity": "INFO",
            "title": "진입 시점을 다시 검증할 후보가 있습니다",
            "evidence": f"{timing['entry_timing']} 연구 코호트는 {timing['trades']}건에서 거래당 평균 {_fmt_pct(timing['expectancy_pct'])}였습니다.",
            "meaning": "현재 반등 확인 진입보다 일부 조건 단계에서 결과가 나았을 가능성이 보입니다.",
            "solution": caveat,
        })
        next_actions.append({
            "id": "VIEW_TIMING",
            "type": "VIEW_SECTION",
            "section": "entry-timing-analysis",
            "label": "진입 시점 근거 보기",
            "description": "3/7~7/7 결과가 실제 규칙과 어떻게 달랐는지 확인합니다.",
            "priority": 2,
        })

    if regime is not None:
        weak_sample = regime["best"]["trades"] < 3 or regime["worst"]["trades"] < 3
        problems.append({
            "id": "REGIME_SENSITIVITY",
            "priority": 5,
            "severity": "INFO",
            "title": "시장환경에 따라 결과 차이가 큽니다",
            "evidence": (
                f"{regime['best']['label']}은 {regime['best']['trades']}건에서 평균 {_fmt_pct(regime['best']['expectancy_pct'])}, "
                f"{regime['worst']['label']}은 {regime['worst']['trades']}건에서 평균 {_fmt_pct(regime['worst']['expectancy_pct'])}였습니다."
            ),
            "meaning": "눌림목 전략을 모든 시장에서 똑같이 쓰기보다 시장 국면 필터가 필요한지 검증할 근거입니다.",
            "solution": "현재 표본이 작으므로 시장 필터를 즉시 추가하지 않고, 기간 확대 후 같은 차이가 반복되는지 먼저 확인합니다." if weak_sample or actual_trades < 30 else "같은 차이가 충분한 표본에서도 반복되므로 시장 국면 필터를 후보 규칙으로 별도 검증합니다.",
        })
        next_actions.append({
            "id": "VIEW_REGIME",
            "type": "VIEW_SECTION",
            "section": "market-regime-analysis",
            "label": "시장환경 근거 보기",
            "description": "어떤 시장에서 손익이 달라졌는지 확인합니다.",
            "priority": 3,
        })

    problems.sort(key=lambda item: (int(item.get("priority") or 99), str(item.get("id") or "")))
    next_actions.sort(key=lambda item: (int(item.get("priority") or 99), str(item.get("id") or "")))

    if actual_trades < 10:
        status = "NEEDS_MORE_EVIDENCE"
        label = "이 종목에서 전략 근거 부족"
        headline = "지금은 전략을 고치는 것보다 표본을 먼저 늘리는 것이 우선입니다."
        summary_text = f"실제 거래가 {actual_trades}건뿐이라 현재 결과만으로 눌림목 전략 자체를 좋다/나쁘다 판단하지 않습니다."
    elif performance["level"] == "WEAK":
        status = "NEEDS_IMPROVEMENT"
        label = "이 종목에서 전략 개선 필요"
        headline = "현재 규칙을 그대로 쓰기보다 손실이 발생하는 조건부터 좁혀야 합니다."
        summary_text = "진입 타이밍·시장환경·손절 종료 패턴을 분리해 어떤 조건을 바꿔야 하는지 검증합니다."
    elif performance["level"] in {"GOOD", "MIXED_POSITIVE"}:
        status = "PROMISING"
        label = "이 종목에서 검증 가치 있음"
        headline = "현재 표본에서는 긍정적인 결과가 보이지만 다른 기간·종목에서도 반복되는지 확인해야 합니다."
        summary_text = "좋은 결과를 그대로 채택하지 않고 재현성 검증을 다음 단계로 둡니다."
    else:
        status = "MIXED"
        label = "추가 원인 분석 필요"
        headline = "성과 지표가 한 방향을 가리키지 않아 문제 원인을 더 분리해서 봐야 합니다."
        summary_text = "진입 타이밍과 시장환경 결과를 함께 비교해 다음 검증 대상을 정합니다."

    candidate: dict[str, Any] | None = None
    if (
        actual_trades >= 30
        and timing is not None
        and timing["trades"] >= 20
        and timing["expectancy_pct"] > 0
        and (timing.get("profit_factor") is None or float(timing["profit_factor"]) >= 1.2)
    ):
        candidate = {
            "status": "RESEARCH_CANDIDATE",
            "title": f"진입 타이밍 {timing['entry_timing']} 후보 규칙",
            "reason": f"{timing['trades']}건에서 평균 {_fmt_pct(timing['expectancy_pct'])}로 반복 표본이 확인됐습니다.",
            "next_validation": "현재 규칙을 즉시 바꾸지 말고 다른 기간·다른 종목에서도 같은 후보가 재현되는지 별도 백테스트합니다.",
        }

    return {
        "status": status,
        "label": label,
        "headline": headline,
        "summary": summary_text,
        "confidence": confidence,
        "performance": performance,
        "risk": risk,
        "problems": problems,
        "next_actions": next_actions,
        "strategy_candidate": candidate,
        "guardrail": "이 결과는 선택한 종목·기간·설정에 대한 검증입니다. 한 종목의 결과를 눌림목 전략 전체의 성패로 확대해석하지 않습니다.",
    }
