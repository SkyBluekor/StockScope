from __future__ import annotations

from typing import Any
import re

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
        "easy_name": "상승 흐름 따라가기",
        "description": "주가가 일정 기간 꾸준히 오르는 흐름을 유지할 때 그 방향을 따라가는 방법입니다.",
        "when_to_use": "단기·중기 평균 가격이 함께 오르고 최근 고점과 저점도 높아지는 흐름에서 주로 확인합니다.",
    },
    StrategyName.PULLBACK: {
        "easy_name": "쉬어간 뒤 다시 오를 때 노리기",
        "description": "상승하던 주가가 잠시 내려오거나 쉬었다가 다시 올라가는지를 확인하는 방법입니다.",
        "when_to_use": "큰 상승 흐름은 살아 있지만 주가가 지지 구간이나 20일 평균 가격 근처로 잠시 내려왔을 때 확인합니다.",
    },
    StrategyName.BREAKOUT: {
        "easy_name": "막힌 가격 돌파 노리기",
        "description": "여러 번 넘지 못했던 가격대를 거래량과 함께 위로 뚫는지를 확인하는 방법입니다.",
        "when_to_use": "주가가 최근 고점이나 저항 가격에 가까워지고 거래량도 함께 늘어날 때 확인합니다.",
    },
    StrategyName.SUPPORT_BOUNCE: {
        "easy_name": "지지 가격에서 반등 노리기",
        "description": "과거에 주가가 여러 번 버텼던 가격 근처에서 다시 반등하는지를 확인하는 방법입니다.",
        "when_to_use": "주가가 주요 지지 가격에 가까우면서 하락이 멈추고 다시 위로 움직일 여지가 있을 때 확인합니다.",
    },
    StrategyName.OVERSOLD_BOUNCE: {
        "easy_name": "과도한 하락 뒤 반등 노리기",
        "description": "짧은 기간에 많이 떨어진 주가가 기술적으로 되돌아 오르는지를 확인하는 방법입니다.",
        "when_to_use": "최근 하락이 과도했고 지지 가격이 가까우며 시장 전체가 급락 상태는 아닐 때 확인합니다.",
    },
    StrategyName.RANGE_TRADING: {
        "easy_name": "일정 가격 범위에서 노리기",
        "description": "주가가 뚜렷한 상승·하락 없이 일정한 범위 안에서 움직일 때 아래쪽 가격대의 반등을 노리는 방법입니다.",
        "when_to_use": "시장과 종목이 횡보하고, 지지 가격은 가깝고 위쪽 저항까지는 여유가 있을 때 확인합니다.",
    },
    StrategyName.MOMENTUM_CONTINUATION: {
        "easy_name": "강한 상승 이어가기",
        "description": "이미 강하게 오르고 있는 주식이 힘을 잃지 않고 상승을 이어가는지를 확인하는 방법입니다.",
        "when_to_use": "가격 상승이 이어지고 거래량과 상대적인 강세가 함께 유지될 때 확인합니다.",
    },
    StrategyName.VOLATILITY_SQUEEZE: {
        "easy_name": "큰 움직임 전 조용한 구간 찾기",
        "description": "주가 움직임이 한동안 작아진 뒤 다시 큰 방향 움직임이 시작되는지를 확인하는 방법입니다.",
        "when_to_use": "최근 변동폭이 줄어들고 거래가 압축된 상태에서 새로운 방향 신호가 나타날 때 확인합니다.",
    },
    StrategyName.MA20_REBOUND: {
        "easy_name": "20일선 반등 노리기",
        "description": "상승 흐름 속에서 주가가 최근 20일 평균 가격 근처까지 내려왔다가 다시 올라가는지를 확인하는 방법입니다.",
        "when_to_use": "20일 평균 가격이 상승 중이고 주가가 그 근처를 지지한 뒤 반등하려 할 때 확인합니다.",
    },
    StrategyName.TREND_RECOVERY: {
        "easy_name": "상승 흐름 회복 노리기",
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
    "저점 상승 구조": ("가격이 이전보다 더 낮은 곳까지 밀리지 않기", "최근 저점이 이전 저점보다 높거나 같은지 확인합니다."),
    "저점 상승 구조 유지": ("가격이 이전보다 더 낮은 곳까지 밀리지 않기", "최근 저점이 이전 저점보다 높거나 같은지 확인합니다."),
    "저점 상승 또는 유지": ("최근 저점이 무너지지 않기", "지지 가격 아래로 흐름이 무너지는지 확인합니다."),
    "시장 대비 상대강도 양호": ("시장보다 약하게 움직이지 않기", "같은 기간 전체 시장보다 덜 떨어지거나 더 강하게 오르는지 확인합니다."),
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
    "20일 시장 대비 상대강도 양호": ("최근 20일 동안 시장보다 약하게 움직이지 않기", "같은 기간 전체 시장보다 덜 떨어지거나 더 강하게 오르는지 확인합니다."),
    "20일 업종 대비 상대강도 양호": ("최근 흐름이 같은 업종보다 약하지 않기", "같은 업종 안에서도 종목의 힘이 유지되는지 확인합니다."),
    "최근 저점 상승": ("가격이 이전보다 더 낮은 곳까지 밀리지 않기", "최근 저점이 이전 저점보다 높거나 같은지 확인합니다."),
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


def _fmt_number(value: Any, digits: int = 1) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not (number == number):
        return None
    rendered = f"{number:,.{digits}f}"
    if digits > 0:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _fmt_price(value: Any) -> str | None:
    rendered = _fmt_number(value, 0)
    return f"{rendered}원" if rendered is not None else None


def _fmt_pct(value: Any, digits: int = 1) -> str | None:
    rendered = _fmt_number(value, digits)
    return f"{rendered}%" if rendered is not None else None


def _fmt_ratio(value: Any, digits: int = 2) -> str | None:
    rendered = _fmt_number(value, digits)
    return f"{rendered}배" if rendered is not None else None


def _market_label(value: Any) -> str:
    raw = getattr(value, "value", value)
    labels = {
        "TREND_UP": "상승장",
        "TREND_DOWN": "하락장",
        "RANGE": "횡보장",
        "HIGH_VOLATILITY": "고변동성",
        "PANIC": "패닉",
        "UNKNOWN": "판단 보류",
    }
    return labels.get(str(raw), str(raw or "판단 보류"))


def _condition_measurement(condition: str, data: Any | None, technical: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    """Return (current_value, required_value, metric_key) for beginner-facing evidence.

    Values are derived only from the same StrategyInput/technical snapshot used by the
    strategy engine. If a condition cannot be measured safely, it stays descriptive
    instead of inventing a number.
    """
    if data is None:
        return None, None, None

    current_price = getattr(data, "current_price", None)
    ma20 = getattr(data, "ma20", None)
    ma60 = getattr(data, "ma60", None)
    ma120 = getattr(data, "ma120", None)
    slope = getattr(data, "ma20_slope_pct", None)
    rsi = getattr(data, "rsi14", None)
    atr = getattr(data, "atr_pct", None)
    volume_ratio = getattr(data, "volume_ratio_20", None)
    high_distance = getattr(data, "distance_to_20d_high_pct", None)
    support_distance = getattr(data, "support_distance_pct", None)
    resistance_distance = getattr(data, "resistance_distance_pct", None)
    support_price = getattr(data, "support_price", None)
    resistance_price = getattr(data, "resistance_price", None)
    rel_market = getattr(data, "relative_strength_market_pct", None)
    rel_sector = getattr(data, "relative_strength_sector_pct", None)
    higher_high = getattr(data, "higher_high", None)
    higher_low = getattr(data, "higher_low", None)
    regime = getattr(data, "market_regime", None)
    high20 = (technical or {}).get("high20")

    if condition in {"현재가가 20일 이동평균선 위", "현재가가 20일선 위", "현재가가 20일선 위로 회복"}:
        current = f"현재 {_fmt_price(current_price) or '-'} · 20일 평균 {_fmt_price(ma20) or '-'}"
        required = f"종가가 {_fmt_price(ma20) or '20일 평균 가격'} 이상"
        return current, required, "price_vs_ma20"
    if condition == "20일선이 60일선 위":
        return f"20일 {_fmt_price(ma20) or '-'} · 60일 {_fmt_price(ma60) or '-'}", "20일 평균 > 60일 평균", "ma20_vs_ma60"
    if condition == "60일선이 120일선 위":
        return f"60일 {_fmt_price(ma60) or '-'} · 120일 {_fmt_price(ma120) or '-'}", "60일 평균 > 120일 평균", "ma60_vs_ma120"

    if "20일선 기울기 0.8% 이상" in condition:
        return _fmt_pct(slope), "0.8% 이상", "ma20_slope"
    if "20일선 기울기가 ±0.3% 이내" in condition:
        return _fmt_pct(slope), "-0.3% ~ +0.3%", "ma20_slope"
    if condition in {"20일 이동평균 기울기 상승", "20일선 기울기 상승"}:
        return _fmt_pct(slope), "0% 초과", "ma20_slope"
    if "20일선 기울기 하락 아님" in condition:
        return _fmt_pct(slope), "0% 이상", "ma20_slope"
    if "20일선 기울기가 급락 아님" in condition:
        return _fmt_pct(slope), "-0.3% 이상", "ma20_slope"

    if condition in {"고점 상승 구조"}:
        return "높아짐" if higher_high is True else "아직 아님" if higher_high is False else "계산 불가", "최근 고점 > 이전 고점", "higher_high"
    if condition in {"저점 상승 구조", "저점 상승 구조 유지", "최근 저점 상승"}:
        return "높아짐" if higher_low is True else "아직 아님" if higher_low is False else "계산 불가", "최근 저점 ≥ 이전 저점", "higher_low"
    if condition == "저점 상승 또는 유지":
        return "유지/상승" if higher_low is True else "낮아짐" if higher_low is False else "계산 불가", "최근 저점이 무너지지 않음", "higher_low"
    if condition == "최근 저점 구조가 완전히 붕괴하지 않음":
        return "붕괴" if higher_low is False else "유지", "최근 저점 구조 유지", "higher_low"

    if "시장 대비 상대강도" in condition or "20일 시장 대비 상대강도" in condition:
        return _fmt_pct(rel_market), "0% 이상 (시장보다 약하지 않음)", "relative_strength_market"
    if "업종 대비 상대강도" in condition or "20일 업종 대비 상대강도" in condition:
        return _fmt_pct(rel_sector), "0% 이상 (업종보다 약하지 않음)", "relative_strength_sector"

    if condition in {"시장 국면이 상승 추세", "상승 시장"}:
        return _market_label(regime), "상승장", "market_regime"
    if condition == "시장 국면이 횡보":
        return _market_label(regime), "횡보장", "market_regime"
    if condition == "상승 시장 또는 중립 시장":
        return _market_label(regime), "상승장 또는 횡보장", "market_regime"
    if condition == "시장 급락 아님":
        return _market_label(regime), "하락장·패닉이 아님", "market_regime"
    if condition == "시장 PANIC 아님":
        return _market_label(regime), "패닉이 아님", "market_regime"

    if "거래량" in condition:
        current = _fmt_ratio(volume_ratio)
        if "1.5배 이상" in condition:
            return current, "1.50배 이상", "volume_ratio_20"
        if "1.2배 이상" in condition or condition == "거래량 증가":
            return current, "1.20배 이상", "volume_ratio_20"
        if "평균 이상" in condition:
            return current, "1.00배 이상", "volume_ratio_20"
        if "20일 평균 이하" in condition:
            return current, "1.00배 이하", "volume_ratio_20"
        if "1.3배 이하" in condition or "1.3배 이하" in condition.replace("20일 평균의 ", ""):
            return current, "1.30배 이하", "volume_ratio_20"

    if "RSI" in condition:
        current = _fmt_number(rsi, 1)
        if "35 이하" in condition:
            return current, "35 이하", "rsi14"
        if "35~60" in condition or "35~60 범위" in condition:
            return current, "35 ~ 60", "rsi14"
        if "40~65" in condition or "40~65 범위" in condition:
            return current, "40 ~ 65", "rsi14"
        if "40~60" in condition:
            return current, "40 ~ 60", "rsi14"
        if "55~75" in condition:
            return current, "55 ~ 75", "rsi14"
        if "과열 전 구간" in condition:
            return current, "50 이상 75 미만", "rsi14"

    if "ATR" in condition:
        current = _fmt_pct(atr)
        if "3.5% 이하" in condition:
            return current, "3.5% 이하", "atr_pct"
        if "4% 이하" in condition:
            return current, "4.0% 이하", "atr_pct"
        if "7% 이하" in condition:
            return current, "7.0% 이하", "atr_pct"
        if "과도하지 않음" in condition:
            return current, "5.0% 이하", "atr_pct"

    support_match = re.search(r"(?:주요 )?지지선과 ([0-9.]+)% 이내", condition)
    if support_match:
        threshold = support_match.group(1)
        current_parts = []
        if support_distance is not None:
            current_parts.append(f"지지선까지 {_fmt_pct(support_distance)}")
        if support_price is not None:
            current_parts.append(f"지지선 {_fmt_price(support_price)}")
        return " · ".join(current_parts) or None, f"지지선과 {threshold}% 이내", "support_distance"

    resistance_min = re.search(r"저항까지 최소 ([0-9.]+)% 여유", condition)
    if resistance_min:
        threshold = resistance_min.group(1)
        current_parts = []
        if resistance_distance is not None:
            current_parts.append(f"여유 {_fmt_pct(resistance_distance)}")
        if resistance_price is not None:
            current_parts.append(f"저항 {_fmt_price(resistance_price)}")
        return " · ".join(current_parts) or None, f"{threshold}% 이상 여유", "resistance_distance"

    resistance_within = re.search(r"저항과 ([0-9.]+)% 이내", condition)
    if resistance_within:
        threshold = resistance_within.group(1)
        current_parts = []
        if resistance_distance is not None:
            current_parts.append(f"저항까지 {_fmt_pct(resistance_distance)}")
        if resistance_price is not None:
            current_parts.append(f"저항 {_fmt_price(resistance_price)}")
        return " · ".join(current_parts) or None, f"저항과 {threshold}% 이내", "resistance_distance"

    high_match = re.search(r"20일 고점과 ([0-9.]+)% 이내", condition)
    if high_match:
        threshold = high_match.group(1)
        current_parts = []
        if current_price is not None:
            current_parts.append(f"종가 {_fmt_price(current_price)}")
        if high20 is not None:
            current_parts.append(f"20일 고점 {_fmt_price(high20)}")
        if high_distance is not None:
            current_parts.append(f"고점까지 {_fmt_pct(high_distance)}")
        return " · ".join(current_parts) or None, f"20일 고점과 {threshold}% 이내", "distance_to_20d_high"

    if condition == "현재가가 20일선과 2.5% 이내":
        distance = None
        try:
            if current_price and ma20 is not None:
                distance = abs(float(current_price) - float(ma20)) / float(current_price) * 100
        except (TypeError, ValueError, ZeroDivisionError):
            distance = None
        current_parts = []
        if distance is not None:
            current_parts.append(f"거리 {_fmt_pct(distance)}")
        if current_price is not None:
            current_parts.append(f"종가 {_fmt_price(current_price)}")
        if ma20 is not None:
            current_parts.append(f"20일 평균 {_fmt_price(ma20)}")
        return " · ".join(current_parts) or None, "20일 평균과 2.5% 이내", "distance_to_ma20"

    return None, None, None


def plain_condition(
    condition: str,
    *,
    data: Any | None = None,
    technical: dict[str, Any] | None = None,
    status: str = "UNKNOWN",
) -> dict[str, Any]:
    value = str(condition or "").strip()
    if not value:
        return {
            "raw": "",
            "label": "다음 확정 데이터에서 조건 다시 계산",
            "detail": "StockScope가 다음 분석 때 전체 조건을 다시 계산합니다.",
            "status": status,
            "current_value": None,
            "required_value": None,
            "metric_key": None,
        }
    direct = CONDITION_GUIDES.get(value)
    if direct:
        label, detail = direct
    elif "20일 고점" in value and "이내" in value:
        label, detail = "최근 고점 가까이 올라오기", f"기준: {value}. 막혀 있던 가격을 다시 시험할 위치인지 확인합니다."
    elif "주요 지지선" in value and "이내" in value:
        label, detail = "잘 버티던 가격 가까이 내려오기", f"기준: {value}. 너무 멀리 떨어진 상태가 아닌지 확인합니다."
    elif "지지선" in value and "이내" in value:
        label, detail = "지지 가격 가까이 위치하기", f"기준: {value}. 아래쪽 위험 기준을 잡을 수 있는 위치인지 확인합니다."
    elif "거래량" in value and ("배 이상" in value or "평균 이상" in value):
        label, detail = "평소보다 거래가 충분히 활발해지기", f"기준: {value}. 사용자가 계산할 필요 없이 StockScope가 자동으로 확인합니다."
    elif "거래량" in value and "배 이하" in value:
        label, detail = "조정 중 거래량이 과도하게 커지지 않기", f"기준: {value}. 매도 압력이 과도한 조정인지 확인합니다."
    elif "RSI" in value:
        label, detail = "최근 상승·하락 속도가 전략에 맞는 범위가 되기", f"전문 기준: {value}. RSI 계산은 StockScope가 자동으로 처리합니다."
    elif "ATR" in value:
        label, detail = "하루 가격 흔들림이 지나치게 크지 않기", f"전문 기준: {value}. 변동성 계산은 StockScope가 자동으로 처리합니다."
    elif "저항까지" in value:
        label, detail = "위쪽 목표 가격까지 충분한 여유가 생기기", f"기준: {value}. 들어가자마자 위쪽 가격에 막히는 상황을 피하기 위한 조건입니다."
    elif "20일선 기울기가" in value or "20일 이동평균 기울기" in value:
        label, detail = "최근 평균 가격 흐름이 전략에 맞는 방향이 되기", f"전문 기준: {value}. 이동평균 계산은 StockScope가 자동으로 처리합니다."
    else:
        label, detail = value, "이 조건은 StockScope가 다음 분석에서 자동으로 다시 확인합니다."

    current_value, required_value, metric_key = _condition_measurement(value, data, technical)
    return {
        "raw": value,
        "label": label,
        "detail": detail,
        "status": status,
        "current_value": current_value,
        "required_value": required_value,
        "metric_key": metric_key,
    }


def build_condition_state(
    evaluation: Any,
    *,
    data: Any | None = None,
    technical: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one canonical condition snapshot from StrategyEvaluation.

    The strategy engine is the source of truth for PASS/FAIL. Counts and beginner
    details are derived from the same reasons/unmet lists so the UI cannot display
    e.g. 7/9 while only exposing a different number of actual conditions.
    """
    passed_raw = list(getattr(evaluation, "reasons", None) or [])
    missing_raw = list(getattr(evaluation, "unmet", None) or [])

    passed_details: list[dict[str, Any]] = []
    for index, condition in enumerate(passed_raw, start=1):
        detail = plain_condition(condition, data=data, technical=technical, status="PASS")
        detail["condition_id"] = f"pass-{index}"
        passed_details.append(detail)

    missing_details: list[dict[str, Any]] = []
    for index, condition in enumerate(missing_raw, start=1):
        detail = plain_condition(condition, data=data, technical=technical, status="FAIL")
        detail["condition_id"] = f"fail-{index}"
        missing_details.append(detail)

    details = [*passed_details, *missing_details]
    detail_passed = len(passed_details)
    detail_missing = len(missing_details)
    detail_total = len(details)
    engine_passed = int(getattr(evaluation, "passed", 0) or 0)
    engine_total = int(getattr(evaluation, "total", 0) or 0)
    engine_missing = max(0, engine_total - engine_passed)
    consistency_ok = (
        engine_passed == detail_passed
        and engine_missing == detail_missing
        and engine_total == detail_total
    )

    return {
        "passed": detail_passed,
        "missing": detail_missing,
        "total": detail_total,
        "passed_details": passed_details,
        "missing_details": missing_details,
        "conditions": details,
        "consistency": {
            "ok": consistency_ok,
            "engine_passed": engine_passed,
            "engine_missing": engine_missing,
            "engine_total": engine_total,
            "detail_passed": detail_passed,
            "detail_missing": detail_missing,
            "detail_total": detail_total,
        },
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


def current_readiness(
    *,
    evaluation: Any,
    risk_plan: Any | None,
    condition_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    score = int(evaluation.score or 0)
    eligible = bool(evaluation.eligible)
    state = condition_state or build_condition_state(evaluation)
    passed = int(state.get("passed") or 0)
    total = int(state.get("total") or 0)
    missing = int(state.get("missing") or 0)
    unmet = [detail.get("raw", "") for detail in (state.get("missing_details") or []) if detail.get("raw")]
    blockers = list(getattr(evaluation, "blockers", None) or [])
    risk_status = getattr(getattr(risk_plan, "status", None), "value", None) if risk_plan is not None else None
    reference_only = bool(getattr(risk_plan, "reference_only", False)) if risk_plan is not None else True
    risk_warning = bool(reference_only or risk_status == "CAUTION" or blockers)
    conditions_complete = total > 0 and missing == 0

    warnings: list[str] = []
    if blockers:
        warnings.append("리스크 게이트가 활성화되어 있습니다: " + ", ".join(blockers))
    if reference_only:
        warnings.append("현재 손절·목표 구조는 참고용으로만 사용할 수 있습니다.")
    elif risk_status == "CAUTION":
        warnings.append("손절 폭이나 목표 여유 같은 위험 구조에 경고가 있습니다.")

    # Primary reason follows the product rule: missing strategy conditions are shown
    # first. Risk warnings stay visible as secondary warnings instead of replacing
    # the reason why entry is not ready.
    if missing > 0:
        status = "NOT_READY" if (not eligible or score < 55) else "WATCH"
        label = "아직 진입 조건 부족"
        summary = f"현재 전략 조건 {total}개 중 {missing}개가 아직 부족합니다."
        if risk_warning:
            summary += " 추가로 손절·목표 위험에도 경고가 있습니다."
        decision_reason = "ENTRY_CONDITIONS_MISSING"
    elif blockers or reference_only:
        status = "BLOCKED"
        label = "위험 때문에 진입 보류"
        summary = "전략 조건은 갖춰졌지만 현재 위험 구조 때문에 신규 진입 후보로 사용하지 않습니다."
        decision_reason = "RISK_BLOCKED"
    elif risk_status == "CAUTION":
        status = "CAUTION"
        label = "위험 때문에 진입 보류"
        summary = "전략 조건은 갖춰졌지만 손절 폭이나 목표 여유 같은 위험 구조에 경고가 있습니다."
        decision_reason = "RISK_BLOCKED"
    elif risk_status == "READY" and score >= 70 and conditions_complete:
        status = "READY"
        label = "진입 후보"
        summary = "현재 전략 조건과 손절·목표 위험 기준이 모두 진입 후보로 다시 검토할 수 있는 수준입니다."
        decision_reason = "ENTRY_CANDIDATE"
    elif not eligible or score < 55:
        status = "NOT_READY"
        label = "아직 진입 조건 부족"
        summary = "현재는 이 방법에 필요한 핵심 조건이 충분히 모이지 않았습니다."
        decision_reason = "ENTRY_CONDITIONS_MISSING"
    else:
        status = "WATCH"
        label = "아직 진입 조건 부족"
        summary = "현재 전략 조건이 완전히 준비되지 않았습니다."
        decision_reason = "ENTRY_CONDITIONS_MISSING"

    ratio = 0.0 if total <= 0 else passed / total
    risk_bonus = 15.0 if risk_status == "READY" and not reference_only else 6.0 if risk_status == "CAUTION" and not reference_only else 0.0
    internal_score = round(min(100.0, score * 0.8 + ratio * 5.0 + risk_bonus), 2)
    return {
        "status": status,
        "label": label,
        "summary": summary,
        "score": score,
        "passed": passed,
        "missing": missing,
        "total": total,
        "risk_status": risk_status,
        "reference_only": reference_only,
        "risk_warning": risk_warning,
        "warnings": warnings,
        "decision_reason": decision_reason,
        "conditions_complete": conditions_complete,
        "condition_consistency": state.get("consistency") or {},
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
            "user_task": "신규 진입하지 않기",
            "title": "지금은 신규 진입하지 마세요.",
            "detail": "현재 사용자가 따로 계산하거나 차트를 확인할 것은 없습니다. 과거 사례가 더 필요한 상태입니다.",
            "has_immediate_task": False,
            "stockscope_title": "StockScope가 다음 분석에서 할 일",
            "stockscope_detail": "최신 확정 데이터를 포함해 과거 표본과 현재 조건을 다시 계산합니다.",
            "next_transition": "과거 근거가 충분해지고 현재 진입 조건까지 맞으면 진입 후보로 다시 평가합니다.",
        }
    if action == "NO_TRADE":
        return {
            "user_task": "신규 진입하지 않기",
            "title": "지금은 신규 진입하지 마세요.",
            "detail": "현재 사용자가 따로 확인하거나 계산할 것은 없습니다.",
            "has_immediate_task": False,
            "stockscope_title": "StockScope가 다음 분석에서 할 일",
            "stockscope_detail": "최신 확정 데이터로 과거 근거, 현재 조건, 손절·목표 위험을 다시 계산합니다.",
            "next_transition": "다른 전략이 더 적합해지거나 이 전략의 근거가 개선되면 추천을 다시 바꿉니다.",
        }
    return {
        "user_task": "신규 진입하지 않기",
        "title": "지금은 신규 진입하지 마세요.",
        "detail": "현재 사용자가 따로 계산하거나 차트를 확인할 것은 없습니다.",
        "has_immediate_task": False,
        "stockscope_title": "StockScope가 다음 분석에서 확인할 것",
        "stockscope_detail": "다음 분석 실행 시 최신 확정 데이터로 남은 조건과 손절·목표 위험을 자동으로 다시 계산합니다.",
        "next_transition": "남은 조건이 맞아도 바로 매수로 바꾸지 않습니다. 전략 조건, 시장 상황, 손절·목표 위험을 다시 확인하고 모두 적절하면 진입 후보로 변경합니다.",
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
            "decision_reason": "INSUFFICIENT_DATA",
            "additional_warnings": [],
            "change_conditions": [],
            "change_condition_details": [],
            "user_action": payload,
            "recheck_mode": "ON_NEXT_ANALYSIS",
            "recheck_label": "최신 확정 데이터가 나온 뒤 다시 분석",
            "as_of_date": as_of_date,
            "market_regime": market_regime,
        }

    top = ranked[0]
    hist_status = top["historical_fit"]["status"]
    current = top["current"]
    readiness = current["status"]
    label = top["label"]
    guide = strategy_guide(top["strategy"])
    unmet = list(current.get("unmet") or [])
    enriched_unmet = list(current.get("unmet_details") or [])
    change_details = enriched_unmet or [plain_condition(condition, status="FAIL") for condition in unmet]
    if current.get("missing") is not None:
        missing = int(current.get("missing") or 0)
    elif unmet:
        missing = len(unmet)
    else:
        missing = max(0, int(current.get("total") or 0) - int(current.get("passed") or 0))
    total = int(current.get("total") or (int(current.get("passed") or 0) + missing))
    risk_warning = bool(current.get("risk_warning"))
    warnings = list(current.get("warnings") or [])

    if hist_status == "INSUFFICIENT":
        action = "NEEDS_VALIDATION"
        action_label = "추가 검증 필요"
        headline = f"{guide['easy_name']} 방법이 가장 앞서지만 과거 사례가 아직 부족합니다."
        reason = "현재 조건은 비교할 수 있지만 과거 거래 사례가 충분하지 않아 이 전략이 실제로 더 낫다고 확정하지 않습니다."
        decision_reason = "INSUFFICIENT_DATA"
    elif hist_status == "WEAK":
        action = "NO_TRADE"
        action_label = "현재 진입하지 않음"
        headline = f"{guide['easy_name']} 방법이 상대적으로 앞서도 지금 적극적으로 사용할 근거는 부족합니다."
        reason = "가장 높은 후보라도 과거 검증 결과가 충분히 좋지 않아 현재 신규 진입 전략으로 추천하지 않습니다."
        decision_reason = "HISTORICAL_EVIDENCE_WEAK"
    elif missing > 0:
        action = "WAIT"
        action_label = "아직 진입 조건 부족"
        headline = f"{guide['easy_name']} 방법이 가장 적합하지만 현재 {total}개 조건 중 {missing}개가 아직 부족합니다."
        reason = f"현재 전략 조건이 {int(current.get('passed') or 0)}/{total}만 충족되어 아직 신규 진입 후보가 아닙니다."
        if risk_warning:
            reason += " 추가로 손절·목표 위험에도 경고가 있어 다음 분석에서 함께 다시 확인합니다."
        decision_reason = "ENTRY_CONDITIONS_MISSING"
    elif readiness in {"BLOCKED", "CAUTION"} or risk_warning:
        action = "WAIT"
        action_label = "위험 때문에 진입 보류"
        headline = f"{guide['easy_name']} 전략 조건은 갖춰졌지만 현재 위험 구조 때문에 진입을 보류합니다."
        reason = current.get("summary") or "손절 폭이나 목표 여유 같은 위험 구조가 아직 적절하지 않습니다."
        decision_reason = "RISK_BLOCKED"
    elif readiness == "READY":
        action = "ENTRY_CANDIDATE"
        action_label = "진입 후보"
        headline = f"현재는 {guide['easy_name']} 방법을 가장 먼저 검토할 수 있습니다."
        reason = "과거 근거와 현재 조건, 손절·목표 위험을 함께 봤을 때 다른 방법보다 우선순위가 높습니다."
        decision_reason = "ENTRY_CANDIDATE"
    else:
        action = "WAIT"
        action_label = "아직 진입 조건 부족"
        headline = f"{guide['easy_name']} 방법이 가장 적합하지만 아직 진입 준비가 완성되지 않았습니다."
        reason = current.get("summary") or "다음 확정 데이터에서 현재 조건과 위험을 다시 확인합니다."
        decision_reason = current.get("decision_reason") or "ENTRY_CONDITIONS_MISSING"

    additional_warnings: list[str] = []
    if decision_reason != "RISK_BLOCKED":
        additional_warnings.extend(warnings)

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
        "decision_reason": decision_reason,
        "additional_warnings": additional_warnings,
        "change_conditions": unmet,
        "change_condition_details": change_details,
        "user_action": action_payload,
        "recheck_mode": "ON_NEXT_ANALYSIS",
        "recheck_label": "최신 확정 데이터가 나온 뒤 다시 분석",
        "as_of_date": as_of_date,
        "market_regime": market_regime,
        "guardrail": "조건 하나가 충족됐다고 바로 매수 판단으로 바꾸지 않습니다. StockScope가 다른 조건과 손절·목표 위험을 다시 종합 평가하며, 이 결과는 미래 수익 확률이 아닙니다.",
    }

