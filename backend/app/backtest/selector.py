from __future__ import annotations

from typing import Any

from app.strategy.models import StrategyName


STRATEGY_LABELS: dict[StrategyName, str] = {
    StrategyName.TREND_FOLLOWING: "추세 추종",
    StrategyName.PULLBACK: "눌림목",
    StrategyName.BREAKOUT: "돌파",
    StrategyName.SUPPORT_BOUNCE: "지지 반등",
    StrategyName.OVERSOLD_BOUNCE: "과매도 반등",
    StrategyName.RANGE_TRADING: "박스권 매매",
    StrategyName.MOMENTUM_CONTINUATION: "모멘텀 지속",
    StrategyName.VOLATILITY_SQUEEZE: "변동성 수축",
    StrategyName.MA20_REBOUND: "20일선 반등",
    StrategyName.TREND_RECOVERY: "추세 회복",
}


STRATEGY_GUIDES: dict[StrategyName, dict[str, str]] = {
    StrategyName.TREND_FOLLOWING: {
        "easy_name": "꾸준한 상승 흐름 따라가기",
        "description": "주가가 일정 기간 꾸준히 오르는 흐름을 유지할 때 그 방향을 따라가는 방법입니다.",
        "when_to_use": "단기·중기 평균 가격이 함께 오르고 최근 고점과 저점도 높아지는 흐름에서 주로 확인합니다.",
    },
    StrategyName.PULLBACK: {
        "easy_name": "오르다 잠깐 쉰 뒤 다시 오를 때 노리기",
        "description": "상승하던 주가가 잠시 내려오거나 쉬었다가 다시 올라가는지를 확인하는 방법입니다.",
        "when_to_use": "큰 상승 흐름은 살아 있지만 주가가 지지 구간이나 20일 평균 가격 근처로 잠시 내려왔을 때 확인합니다.",
    },
    StrategyName.BREAKOUT: {
        "easy_name": "막혀 있던 가격을 뚫을 때 노리기",
        "description": "여러 번 넘지 못했던 가격대를 거래량과 함께 위로 뚫는지를 확인하는 방법입니다.",
        "when_to_use": "주가가 최근 고점이나 저항 가격에 가까워지고 거래량도 함께 늘어날 때 확인합니다.",
    },
    StrategyName.SUPPORT_BOUNCE: {
        "easy_name": "잘 버티던 가격에서 다시 오를 때 노리기",
        "description": "과거에 주가가 여러 번 버텼던 가격 근처에서 다시 반등하는지를 확인하는 방법입니다.",
        "when_to_use": "주가가 주요 지지 가격에 가까우면서 하락이 멈추고 다시 위로 움직일 여지가 있을 때 확인합니다.",
    },
    StrategyName.OVERSOLD_BOUNCE: {
        "easy_name": "너무 많이 떨어진 뒤 반등 노리기",
        "description": "짧은 기간에 많이 떨어진 주가가 기술적으로 되돌아 오르는지를 확인하는 방법입니다.",
        "when_to_use": "최근 하락이 과도했고 지지 가격이 가까우며 시장 전체가 급락 상태는 아닐 때 확인합니다.",
    },
    StrategyName.RANGE_TRADING: {
        "easy_name": "일정한 가격 범위에서 기회 찾기",
        "description": "주가가 뚜렷한 상승·하락 없이 일정한 범위 안에서 움직일 때 아래쪽 가격대의 반등을 노리는 방법입니다.",
        "when_to_use": "시장과 종목이 횡보하고, 지지 가격은 가깝고 위쪽 저항까지는 여유가 있을 때 확인합니다.",
    },
    StrategyName.MOMENTUM_CONTINUATION: {
        "easy_name": "강한 상승 힘이 계속될 때 따라가기",
        "description": "이미 강하게 오르고 있는 주식이 힘을 잃지 않고 상승을 이어가는지를 확인하는 방법입니다.",
        "when_to_use": "가격 상승이 이어지고 거래량과 상대적인 강세가 함께 유지될 때 확인합니다.",
    },
    StrategyName.VOLATILITY_SQUEEZE: {
        "easy_name": "조용해진 뒤 큰 움직임 기다리기",
        "description": "주가 움직임이 한동안 작아진 뒤 다시 큰 방향 움직임이 시작되는지를 확인하는 방법입니다.",
        "when_to_use": "최근 변동폭이 줄어들고 거래가 압축된 상태에서 새로운 방향 신호가 나타날 때 확인합니다.",
    },
    StrategyName.MA20_REBOUND: {
        "easy_name": "20일 평균 가격에서 다시 오를 때 노리기",
        "description": "상승 흐름 속에서 주가가 최근 20일 평균 가격 근처까지 내려왔다가 다시 올라가는지를 확인하는 방법입니다.",
        "when_to_use": "20일 평균 가격이 상승 중이고 주가가 그 근처를 지지한 뒤 반등하려 할 때 확인합니다.",
    },
    StrategyName.TREND_RECOVERY: {
        "easy_name": "약해졌던 상승 흐름이 다시 살아날 때 노리기",
        "description": "한동안 약해졌던 상승 흐름이 다시 회복되는지를 확인하는 방법입니다.",
        "when_to_use": "주가가 다시 주요 평균 가격 위로 올라오고 고점·저점 구조가 회복되기 시작할 때 확인합니다.",
    },
}


CONDITION_GUIDES: dict[str, tuple[str, str]] = {
    "현재가가 20일 이동평균선 위": ("주가가 최근 20일 평균 가격 위로 올라서기", "최근 가격 흐름이 다시 위쪽에 있는지 확인합니다."),
    "20일선이 60일선 위": ("단기 흐름이 중기 흐름보다 강해지기", "20일 평균 가격이 60일 평균 가격보다 위에 있어야 합니다."),
    "60일선이 120일선 위": ("중기 상승 흐름이 장기 흐름보다 강하게 유지되기", "60일 평균 가격이 120일 평균 가격보다 위에 있어야 합니다."),
    "20일 이동평균 기울기 상승": ("최근 20일 평균 가격이 다시 위쪽으로 기울기", "최근 평균 가격 자체가 상승 방향인지 확인합니다."),
    "20일선 기울기 상승": ("최근 20일 평균 가격이 다시 위쪽으로 기울기", "최근 평균 가격 자체가 상승 방향인지 확인합니다."),
    "고점 상승 구조": ("최근 고점이 이전 고점보다 높아지기", "상승 흐름이 실제 가격 구조에서도 이어지는지 확인합니다."),
    "저점 상승 구조": ("최근 저점이 이전 저점보다 높아지기", "조정이 와도 이전보다 높은 가격에서 버티는지 확인합니다."),
    "저점 상승 구조 유지": ("최근 저점이 이전보다 높게 유지되기", "상승 흐름이 무너지지 않고 있는지 확인합니다."),
    "저점 상승 또는 유지": ("최근 저점이 무너지지 않기", "지지 가격 아래로 흐름이 무너지는지 확인합니다."),
    "시장 대비 상대강도 양호": ("종목 흐름이 시장보다 약하지 않게 유지되기", "전체 시장보다 이 종목이 상대적으로 강한지 확인합니다."),
    "업종 대비 상대강도 양호": ("같은 업종 종목보다 흐름이 약하지 않기", "업종 안에서도 상대적으로 힘이 유지되는지 확인합니다."),
    "시장 국면이 상승 추세": ("전체 시장이 상승 흐름이기", "종목뿐 아니라 시장 환경도 같은 방향인지 확인합니다."),
    "상승 시장": ("전체 시장이 상승 흐름이기", "종목뿐 아니라 시장 환경도 같은 방향인지 확인합니다."),
    "상승 시장 또는 중립 시장": ("시장 환경이 급격한 하락 상태가 아니기", "상승 또는 횡보 환경인지 확인합니다."),
    "시장 급락 아님": ("전체 시장이 급격히 무너지는 상태가 아니기", "개별 종목 반등보다 시장 급락 위험이 더 큰 상황인지 먼저 확인합니다."),
    "시장 PANIC 아님": ("시장 전체가 패닉 상태가 아니기", "급격한 시장 충격이 없는지 확인합니다."),
    "시장 국면이 횡보": ("시장 흐름이 일정한 범위 안에서 움직이기", "뚜렷한 상승·하락보다 횡보에 가까운 환경인지 확인합니다."),
    "거래량 증가": ("평소보다 거래가 활발해지기", "가격 움직임에 실제 거래 참여가 함께 늘어나는지 확인합니다."),
    "거래량이 평균 이상": ("거래량이 평소 수준 이상으로 늘기", "반등에 참여하는 거래가 충분한지 확인합니다."),
    "최근 저점 구조가 완전히 붕괴하지 않음": ("최근 저점이 완전히 무너지지 않기", "반등을 기대할 수 있는 최소한의 가격 구조가 남아 있는지 확인합니다."),
    "현재가가 20일선 위": ("주가가 최근 20일 평균 가격 위에 있기", "현재 가격이 최근 20일 평균보다 위에 있는지 StockScope가 확인합니다."),
    "현재가가 20일선 위로 회복": ("주가가 최근 20일 평균 가격 위로 다시 올라오기", "약해졌던 흐름이 회복되고 있는지 StockScope가 확인합니다."),
    "현재가가 20일선과 2.5% 이내": ("주가가 최근 20일 평균 가격 가까이에 있기", "20일 평균 가격을 지지선처럼 활용할 수 있는 위치인지 확인합니다."),
    "20일선 기울기 0.8% 이상": ("최근 평균 가격이 뚜렷하게 상승하기", "20일 평균 가격이 충분한 상승 기울기를 유지하는지 확인합니다."),
    "20일선 기울기가 ±0.3% 이내": ("최근 평균 가격이 거의 옆으로 움직이기", "뚜렷한 상승·하락보다 횡보에 가까운 흐름인지 확인합니다."),
    "20일선 기울기 하락 아님": ("최근 평균 가격이 아래로 기울지 않기", "압축 뒤 상승을 기대하려면 평균 가격 흐름이 무너지지 않아야 합니다."),
    "20일선 기울기가 급락 아님": ("최근 평균 가격의 하락세가 진정되기", "하락 속도가 둔화돼 회복을 시도할 수 있는지 확인합니다."),
    "RSI 과열 전 구간": ("상승 힘은 있지만 지나치게 과열되지는 않기", "최근 상승 속도가 너무 빠른 상태인지 StockScope가 RSI로 확인합니다."),
    "RSI 35 이하": ("최근 하락이 과도했던 구간에 들어오기", "짧은 기간 많이 떨어진 상태인지 StockScope가 RSI로 확인합니다."),
    "RSI 35~60": ("상승·하락 속도가 반등에 적당한 범위가 되기", "너무 약하거나 과열되지 않은 범위인지 StockScope가 확인합니다."),
    "RSI 40~65": ("상승 흐름을 이어가기 적당한 속도가 되기", "너무 약하거나 과열되지 않은 범위인지 StockScope가 확인합니다."),
    "RSI 40~60": ("회복을 시도하기 적당한 가격 흐름이 되기", "하락에서 회복되는 과정에 맞는 범위인지 StockScope가 확인합니다."),
    "RSI 55~75": ("상승 힘이 충분하지만 과열 직전 범위를 유지하기", "강한 상승세가 이어지면서도 과열이 지나치지 않은지 확인합니다."),
    "ATR 변동성이 과도하지 않음": ("하루 가격 흔들림이 지나치게 크지 않기", "갑작스러운 급등락 위험이 너무 큰 상태인지 StockScope가 확인합니다."),
    "ATR 4% 이하": ("하루 가격 흔들림이 비교적 안정적이기", "박스권 전략을 쓰기 어려울 정도로 변동이 커지지 않았는지 확인합니다."),
    "ATR 7% 이하": ("하루 가격 흔들림이 위험 수준까지 커지지 않기", "반등을 노리기에는 변동성이 지나치게 큰 상태인지 확인합니다."),
    "ATR 3.5% 이하": ("가격 움직임이 충분히 조용해지기", "큰 움직임 전 압축 구간처럼 변동폭이 줄어들었는지 확인합니다."),
    "거래량 20일 평균의 1.2배 이상": ("평소보다 거래가 20% 이상 활발해지기", "최근 20일 평균보다 거래 참여가 충분히 늘었는지 StockScope가 자동 계산합니다."),
    "거래량이 20일 평균의 1.5배 이상": ("평소보다 거래가 50% 이상 활발해지기", "돌파에 실제 거래 참여가 동반되는지 StockScope가 자동 계산합니다."),
    "거래량이 20일 평균 이하": ("거래량이 평소보다 줄어든 압축 상태가 되기", "가격과 거래가 조용해진 상태인지 StockScope가 자동 계산합니다."),
    "거래량 1.3배 이하": ("조정 중 거래량이 평소보다 너무 커지지 않기", "매도 압력이 과도한 조정인지 StockScope가 자동 계산합니다."),
    "20일 시장 대비 상대강도 양호": ("최근 흐름이 전체 시장보다 약하지 않기", "같은 기간 시장보다 종목의 힘이 상대적으로 강한지 확인합니다."),
    "20일 업종 대비 상대강도 양호": ("최근 흐름이 같은 업종보다 약하지 않기", "같은 업종 안에서도 종목의 힘이 유지되는지 확인합니다."),
    "최근 저점 상승": ("최근 저점이 이전보다 높아지기", "약세가 멈추고 가격의 바닥이 조금씩 높아지는지 확인합니다."),
    "전략별 핵심 조건이 아직 충분히 모이지 않았습니다.": ("현재 전략의 핵심 조건이 더 모이기", "다음 분석에서 10가지 전략의 조건을 다시 계산해 더 적합한 방법이 생겼는지 확인합니다."),
}


def strategy_label(strategy: StrategyName | str) -> str:
    try:
        key = strategy if isinstance(strategy, StrategyName) else StrategyName(strategy)
    except ValueError:
        return str(strategy)
    return STRATEGY_LABELS.get(key, key.value)


def strategy_guide(strategy: StrategyName | str) -> dict[str, str]:
    try:
        key = strategy if isinstance(strategy, StrategyName) else StrategyName(strategy)
    except ValueError:
        label = str(strategy)
        return {
            "easy_name": label,
            "professional_name": label,
            "description": "이 전략의 현재 조건을 과거 데이터와 함께 비교합니다.",
            "when_to_use": "현재 전략 조건이 충분히 갖춰졌는지 확인합니다.",
        }
    guide = STRATEGY_GUIDES.get(key) or {}
    return {
        "easy_name": guide.get("easy_name", strategy_label(key)),
        "professional_name": strategy_label(key),
        "description": guide.get("description", "현재 전략 조건을 과거 데이터와 함께 비교합니다."),
        "when_to_use": guide.get("when_to_use", "현재 전략 조건이 충분히 갖춰졌는지 확인합니다."),
    }


def plain_condition(condition: str) -> dict[str, str]:
    value = str(condition or "").strip()
    if not value:
        return {"raw": "", "label": "다음 확정 데이터에서 조건 다시 계산", "detail": "StockScope가 다음 분석 때 전체 조건을 다시 계산합니다."}
    direct = CONDITION_GUIDES.get(value)
    if direct:
        return {"raw": value, "label": direct[0], "detail": direct[1]}

    if "20일 고점" in value and "이내" in value:
        return {"raw": value, "label": "최근 고점 가까이 올라오기", "detail": f"기준: {value}. 막혀 있던 가격을 다시 시험할 위치인지 확인합니다."}
    if "주요 지지선" in value and "이내" in value:
        return {"raw": value, "label": "잘 버티던 가격 가까이 내려오기", "detail": f"기준: {value}. 너무 멀리 떨어진 상태가 아닌지 확인합니다."}
    if "지지선" in value and "이내" in value:
        return {"raw": value, "label": "지지 가격 가까이 위치하기", "detail": f"기준: {value}. 아래쪽 위험 기준을 잡을 수 있는 위치인지 확인합니다."}
    if "거래량" in value and ("배 이상" in value or "평균 이상" in value):
        return {"raw": value, "label": "평소보다 거래가 충분히 활발해지기", "detail": f"기준: {value}. 사용자가 계산할 필요 없이 StockScope가 자동으로 확인합니다."}
    if "거래량" in value and "배 이하" in value:
        return {"raw": value, "label": "조정 중 거래량이 과도하게 커지지 않기", "detail": f"기준: {value}. 매도 압력이 과도한 조정인지 확인합니다."}
    if "RSI" in value:
        return {"raw": value, "label": "최근 상승·하락 속도가 전략에 맞는 범위가 되기", "detail": f"전문 기준: {value}. RSI 계산은 StockScope가 자동으로 처리합니다."}
    if "ATR" in value:
        return {"raw": value, "label": "하루 가격 흔들림이 지나치게 크지 않기", "detail": f"전문 기준: {value}. 변동성 계산은 StockScope가 자동으로 처리합니다."}
    if "저항까지" in value:
        return {"raw": value, "label": "위쪽 목표 가격까지 충분한 여유가 생기기", "detail": f"기준: {value}. 들어가자마자 위쪽 가격에 막히는 상황을 피하기 위한 조건입니다."}
    if "20일선 기울기가" in value or "20일 이동평균 기울기" in value:
        return {"raw": value, "label": "최근 평균 가격 흐름이 전략에 맞는 방향이 되기", "detail": f"전문 기준: {value}. 이동평균 계산은 StockScope가 자동으로 처리합니다."}

    return {
        "raw": value,
        "label": value,
        "detail": "이 조건은 StockScope가 다음 분석에서 자동으로 다시 확인합니다.",
    }


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def historical_fit(metrics: dict[str, Any]) -> dict[str, Any]:
    trades = int(metrics.get("trades") or 0)
    expectancy = metrics.get("expectancy_pct")
    expectancy_f = None if expectancy is None else _number(expectancy)
    profit_factor = metrics.get("profit_factor")
    profit_factor_f = None if profit_factor is None else _number(profit_factor)
    mdd = _number(metrics.get("max_drawdown_pct"), 0.0)

    if trades < 5:
        status = "INSUFFICIENT"
        label = "근거 부족"
        summary = f"과거에 조건이 맞아 실제 거래로 이어진 사례가 {trades}건뿐이라 이 전략이 잘 맞는다고 단정하기 어렵습니다."
    elif expectancy_f is not None and expectancy_f > 0 and (profit_factor_f is None or profit_factor_f >= 1.2) and mdd > -20:
        status = "GOOD"
        label = "과거 근거 좋음"
        summary = "과거 거래에서 평균 결과가 양수였고 손익 구조와 큰 손실 구간도 비교 가능한 수준이었습니다."
    elif expectancy_f is not None and expectancy_f > 0 and mdd > -25:
        status = "FAIR"
        label = "과거 근거 보통"
        summary = "과거에는 평균적으로 플러스 결과가 있었지만 이 전략이 확실히 잘 맞는다고 보기에는 추가 검증이 필요합니다."
    else:
        status = "WEAK"
        label = "과거 근거 약함"
        summary = "현재 검증 기간에서는 평균 결과나 손실 위험이 이 전략을 적극적으로 쓰기에는 충분하지 않았습니다."

    # Internal comparison score only. It is never exposed as an upward probability.
    sample_score = min(trades, 20) / 20.0 * 20.0
    exp_score = 0.0 if expectancy_f is None else max(0.0, min(25.0, (expectancy_f + 2.0) / 4.0 * 25.0))
    if profit_factor_f is None:
        pf_score = 12.0 if expectancy_f is not None and expectancy_f > 0 else 0.0
    else:
        pf_score = max(0.0, min(20.0, profit_factor_f / 2.0 * 20.0))
    mdd_score = max(0.0, min(20.0, (30.0 - abs(mdd)) / 30.0 * 20.0))
    median = metrics.get("median_net_return_pct")
    median_f = None if median is None else _number(median)
    consistency_score = 0.0 if median_f is None else max(0.0, min(15.0, (median_f + 1.5) / 3.0 * 15.0))
    internal_score = round(sample_score + exp_score + pf_score + mdd_score + consistency_score, 2)

    return {
        "status": status,
        "label": label,
        "summary": summary,
        "internal_score": internal_score,
    }


def current_readiness(*, evaluation: Any, risk_plan: Any | None) -> dict[str, Any]:
    score = int(evaluation.score or 0)
    eligible = bool(evaluation.eligible)
    passed = int(evaluation.passed or 0)
    total = int(evaluation.total or 0)
    unmet = list(evaluation.unmet or [])
    risk_status = getattr(getattr(risk_plan, "status", None), "value", None) if risk_plan is not None else None
    reference_only = bool(getattr(risk_plan, "reference_only", False)) if risk_plan is not None else True

    if not eligible or score < 55:
        status = "NOT_READY"
        label = "아직 진입 조건 부족"
        summary = "현재는 이 방법에 필요한 핵심 조건이 충분히 모이지 않았습니다."
    elif reference_only:
        status = "BLOCKED"
        label = "현재 진입 보류"
        summary = "조건이 일부 맞아도 현재 손절 폭이나 목표 여유 같은 위험 구조 때문에 신규 진입 후보로 사용하지 않습니다."
    elif risk_status == "READY" and score >= 70:
        status = "READY"
        label = "진입 후보"
        summary = "현재 조건과 손절·목표 위험 기준이 모두 진입 후보로 다시 검토할 수 있는 수준입니다."
    elif risk_status == "CAUTION":
        status = "CAUTION"
        label = "위험 때문에 진입 보류"
        summary = "조건은 일부 맞지만 손절 폭이나 목표 여유 같은 위험 구조에 경고가 있습니다."
    else:
        status = "WATCH"
        label = "아직 진입 조건 미완성"
        summary = "유력한 방법이지만 현재 진입 조건이 모두 완성되지는 않았습니다."

    ratio = 0.0 if total <= 0 else passed / total
    risk_bonus = 15.0 if risk_status == "READY" and not reference_only else 6.0 if risk_status == "CAUTION" and not reference_only else 0.0
    internal_score = round(min(100.0, score * 0.8 + ratio * 5.0 + risk_bonus), 2)
    return {
        "status": status,
        "label": label,
        "summary": summary,
        "score": score,
        "passed": passed,
        "total": total,
        "risk_status": risk_status,
        "unmet": unmet,
        "internal_score": internal_score,
    }


def _action_payload(action: str, *, label: str, change_details: list[dict[str, str]]) -> dict[str, Any]:
    if action == "ENTRY_CANDIDATE":
        return {
            "user_task": "진입 여부를 결정하세요",
            "title": "진입을 고려할 수 있는 후보 상태입니다.",
            "detail": "조건 계산은 StockScope가 끝냈습니다. 실제 주문은 자동으로 실행하지 않으므로, 제시된 위험 수준과 손절 기준을 확인한 뒤 진입 여부를 직접 결정하세요.",
            "has_immediate_task": True,
            "stockscope_title": "StockScope가 이미 확인한 것",
            "stockscope_detail": "현재 조건과 손절 폭·목표 여유 같은 위험 기준을 함께 확인해 진입 후보로 분류했습니다.",
            "next_transition": "조건이나 위험 구조가 나빠지면 다음 분석에서 다시 대기 또는 관망으로 변경합니다.",
        }
    if action == "NEEDS_VALIDATION":
        return {
            "user_task": "현재 할 일 없음",
            "title": "지금은 이 방법으로 진입하지 마세요.",
            "detail": "현재 사용자가 따로 계산하거나 차트를 확인할 것은 없습니다. 과거 사례가 더 필요한 상태입니다.",
            "has_immediate_task": False,
            "stockscope_title": "StockScope가 다음 분석에서 할 일",
            "stockscope_detail": "최신 확정 데이터를 포함해 과거 표본과 현재 조건을 다시 계산합니다.",
            "next_transition": "과거 근거가 충분해지고 현재 진입 조건까지 맞으면 진입 후보로 다시 평가합니다.",
        }
    if action == "NO_TRADE":
        return {
            "user_task": "현재 할 일 없음",
            "title": "현재는 새로 진입하지 마세요.",
            "detail": "현재 사용자가 따로 확인하거나 계산할 것은 없습니다.",
            "has_immediate_task": False,
            "stockscope_title": "StockScope가 다음 분석에서 할 일",
            "stockscope_detail": "최신 확정 데이터로 과거 근거, 현재 조건, 손절·목표 위험을 다시 계산합니다.",
            "next_transition": "다른 전략이 더 적합해지거나 이 전략의 근거가 개선되면 추천을 다시 바꿉니다.",
        }
    return {
        "user_task": "현재 할 일 없음",
        "title": "지금은 진입하지 마세요.",
        "detail": "현재 사용자가 따로 계산하거나 차트를 확인할 것은 없습니다.",
        "has_immediate_task": False,
        "stockscope_title": "StockScope가 다음 분석에서 확인할 것",
        "stockscope_detail": "다음 분석 실행 시 최신 확정 데이터로 남은 조건과 손절·목표 위험을 자동으로 다시 계산합니다.",
        "next_transition": "남은 조건이 충족돼도 바로 매수 판단으로 바꾸지 않고 다른 조건과 손절·목표 위험까지 다시 종합 평가합니다.",
    }


def select_strategy(strategy_rows: list[dict[str, Any]], *, as_of_date: str, market_regime: str) -> dict[str, Any]:
    ranked: list[dict[str, Any]] = []
    for row in strategy_rows:
        hist = row["historical_fit"]
        current = row["current"]
        history_score = float(hist.get("internal_score") or 0.0)
        current_score = float(current.get("internal_score") or 0.0)
        sample_penalty = 20.0 if hist.get("status") == "INSUFFICIENT" else 8.0 if hist.get("status") == "WEAK" else 0.0
        selector_score = history_score * 0.55 + current_score * 0.45 - sample_penalty
        ranked.append({**row, "selector_score": round(selector_score, 2)})

    ranked.sort(key=lambda item: (item["selector_score"], item["historical_metrics"].get("trades") or 0), reverse=True)
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank

    if not ranked:
        payload = _action_payload("NO_TRADE", label="관망", change_details=[])
        return {
            "strategy": None,
            "strategy_label": None,
            "strategy_easy_name": None,
            "strategy_description": None,
            "strategy_when_to_use": None,
            "action": "NO_TRADE",
            "action_label": "현재 진입하지 않음",
            "headline": "현재 추천할 전략을 찾지 못했습니다.",
            "reason": "비교 가능한 전략 결과가 없습니다.",
            "change_conditions": [],
            "change_condition_details": [],
            "user_action": payload,
            "recheck_mode": "ON_NEXT_ANALYSIS",
            "recheck_label": "다음 분석 실행 시 자동 재평가",
            "as_of_date": as_of_date,
            "market_regime": market_regime,
        }

    top = ranked[0]
    hist_status = top["historical_fit"]["status"]
    readiness = top["current"]["status"]
    label = top["label"]
    guide = strategy_guide(top["strategy"])
    unmet = list(top["current"].get("unmet") or [])[:4]
    change_details = [plain_condition(condition) for condition in unmet]

    if hist_status == "INSUFFICIENT":
        action = "NEEDS_VALIDATION"
        action_label = "추가 검증 필요"
        headline = f"{guide['easy_name']} 방법이 가장 앞서지만 과거 사례가 아직 부족합니다."
        reason = "현재 조건은 비교할 수 있지만 과거 거래 사례가 충분하지 않아 이 전략이 실제로 더 낫다고 확정하지 않습니다."
    elif hist_status == "WEAK":
        action = "NO_TRADE"
        action_label = "현재 진입하지 않음"
        headline = f"{guide['easy_name']} 방법이 상대적으로 앞서도 지금 적극적으로 사용할 근거는 부족합니다."
        reason = "가장 높은 후보라도 과거 검증 결과가 충분히 좋지 않아 현재 신규 진입 전략으로 추천하지 않습니다."
    elif readiness == "READY":
        action = "ENTRY_CANDIDATE"
        action_label = "진입 후보"
        headline = f"현재는 {guide['easy_name']} 방법을 가장 먼저 검토할 수 있습니다."
        reason = "과거 근거와 현재 조건, 손절·목표 위험을 함께 봤을 때 다른 방법보다 우선순위가 높습니다."
    else:
        action = "WAIT"
        action_label = "아직 진입하지 않음"
        headline = f"{guide['easy_name']} 방법이 가장 적합하지만 아직 진입 조건이 모두 완성되지 않았습니다."
        reason = top["current"]["summary"]

    action_payload = _action_payload(action, label=label, change_details=change_details)
    return {
        "strategy": top["strategy"],
        "strategy_label": label,
        "strategy_easy_name": guide["easy_name"],
        "strategy_description": guide["description"],
        "strategy_when_to_use": guide["when_to_use"],
        "action": action,
        "action_label": action_label,
        "headline": headline,
        "reason": reason,
        "change_conditions": unmet,
        "change_condition_details": change_details,
        "user_action": action_payload,
        "recheck_mode": "ON_NEXT_ANALYSIS",
        "recheck_label": "다음 분석 실행 시 최신 확정 데이터로 자동 재평가",
        "as_of_date": as_of_date,
        "market_regime": market_regime,
        "guardrail": "조건 하나가 충족됐다고 바로 매수 판단으로 바꾸지 않습니다. StockScope가 다른 조건과 손절·목표 위험을 다시 종합 평가하며, 이 결과는 미래 수익 확률이 아닙니다.",
    }
