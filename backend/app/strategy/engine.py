from __future__ import annotations

from collections.abc import Callable

from .models import (
    MarketRegime,
    StrategyEvaluation,
    StrategyInput,
    StrategyName,
)

Condition = tuple[str, int, Callable[[StrategyInput], bool]]


class StrategyEngine:
    """Rule-based strategy suitability engine.

    score is a suitability score, NOT a probability of future profit.
    """

    def evaluate_all(self, data: StrategyInput) -> list[StrategyEvaluation]:
        risk_blockers = self._risk_gate(data)
        evaluations = [
            self._trend_following(data),
            self._pullback(data),
            self._breakout(data),
            self._support_bounce(data),
            self._oversold_bounce(data),
            self._range_trading(data),
            self._momentum_continuation(data),
            self._volatility_squeeze(data),
            self._ma20_rebound(data),
            self._trend_recovery(data),
        ]
        evaluations.sort(key=lambda item: item.score or 0, reverse=True)

        if risk_blockers:
            for item in evaluations:
                item.eligible = False
            return [
                self._no_trade(
                    data,
                    risk_blockers,
                    "리스크 게이트가 활성화되어 신규 진입을 보류합니다. 아래 전략 점수는 참고용으로만 확인하세요.",
                ),
                *evaluations,
            ]

        if not evaluations or (evaluations[0].score or 0) < 55:
            evaluations.insert(
                0,
                self._no_trade(
                    data,
                    [],
                    "어느 전략도 최소 적합도 55점을 넘지 못했습니다.",
                ),
            )
        return evaluations

    @staticmethod
    def _risk_gate(data: StrategyInput) -> list[str]:
        blockers: list[str] = []
        if not data.tradable:
            blockers.append("정상 거래가 불가능한 종목")
        if not data.liquidity_ok:
            blockers.append("유동성 기준 미충족")
        if data.event_risk:
            blockers.append("중요 이벤트/공시 리스크 존재")
        if data.market_regime == MarketRegime.PANIC:
            blockers.append("시장 PANIC 국면")
        if data.extreme_move:
            blockers.append("확정 종가 대비 급격한 가격 변동으로 EOD 전략 신뢰도 저하")
        return blockers

    @staticmethod
    def _won(value: float | None) -> str:
        if value is None:
            return "아직 계산되지 않음"
        return f"{value:,.0f}원"

    @classmethod
    def _action_plan(cls, strategy: StrategyName, d: StrategyInput) -> dict[str, list[str] | str]:
        support = cls._won(d.support_price)
        resistance = cls._won(d.resistance_price)
        ma20 = cls._won(d.ma20)

        plans: dict[StrategyName, dict[str, list[str] | str]] = {
            StrategyName.TREND_FOLLOWING: {
                "new_entry": [
                    "신규 진입을 검토한다면 급등 직후 추격보다 20일선 또는 직전 지지구간까지의 눌림을 먼저 확인합니다.",
                    "고점과 저점이 계속 높아지는지, 거래량이 급격히 고갈되지 않는지 확인합니다.",
                ],
                "holding": [
                    f"보유 중이라면 {ma20} 부근과 최근 지지 후보 {support}가 유지되는지 관찰합니다.",
                    "상승 추세가 유지되는 동안에는 하루 변동보다 고점·저점 구조가 무너지는지를 더 중요하게 봅니다.",
                ],
                "avoid": ["장대양봉이나 급등 직후 한 번에 추격하는 행동", "추세가 꺾였는데 평균단가를 낮추기 위해 무조건 추가매수하는 행동"],
                "watch": ["20일 이동평균", "최근 저점", "거래량 감소 여부"],
                "invalidation": f"종가 기준으로 20일선({ma20})과 주요 지지 후보({support})를 연속적으로 이탈하면 추세 전략이 약해진 것으로 봅니다.",
            },
            StrategyName.PULLBACK: {
                "new_entry": [
                    "상단의 '눌림·지지 자동 확인' 결과가 지지 테스트 중인지, 반등 확인인지 먼저 봅니다.",
                    "앱이 지지 유지·RSI 회복·반등 거래량을 자동 점검하므로 사용자가 차트를 보고 같은 조건을 다시 판정할 필요는 없습니다.",
                ],
                "holding": [
                    "눌림·지지 자동 확인이 '지지 실패'로 바뀌는지 우선 봅니다.",
                    f"지지 후보 {support}와 20일선 {ma20}이 유지되면 정상 조정 시나리오가 유지되는 쪽입니다.",
                ],
                "avoid": ["앱이 지지 실패/미확정으로 판단했는데 손실만을 이유로 추가매수", "하락 추세 종목을 단순히 싸졌다는 이유로 눌림목으로 오해"],
                "watch": ["앱의 눌림·지지 상태", "지지 실패 여부", "RSI·거래량 반등 자동 점검"],
                "invalidation": f"주요 지지 후보 {support}를 종가 기준 뚜렷하게 이탈하고 회복하지 못하면 눌림목 시나리오를 다시 평가합니다.",
            },
            StrategyName.BREAKOUT: {
                "new_entry": [
                    f"저항 후보 {resistance}를 실제로 넘어선 뒤 종가가 위에서 유지되는지 확인합니다.",
                    "돌파 시 거래량이 최근 평균보다 의미 있게 증가하는지 확인하고, 장중 잠깐 넘겼다가 밀리는 가짜 돌파를 구분합니다.",
                ],
                "holding": [f"돌파 후 보유 중이라면 이전 저항 {resistance}가 새로운 지지 역할을 하는지 확인합니다.", "돌파 뒤 거래량과 가격이 동시에 약해지면 수익 보호 관점의 재평가가 필요합니다."],
                "avoid": ["저항을 넘기 전에 돌파를 미리 확정해서 큰 비중으로 진입", "거래량 없는 돌파를 동일하게 취급"],
                "watch": ["저항 돌파 종가", "거래량 20일 평균 대비 비율", "돌파 후 재지지"],
                "invalidation": f"돌파했다고 판단한 뒤 다시 저항 후보 {resistance} 아래로 밀리고 회복하지 못하면 실패 돌파 가능성을 봅니다.",
            },
            StrategyName.SUPPORT_BOUNCE: {
                "new_entry": [f"지지 후보 {support} 부근에서 하락이 멈추는지와 반등 캔들이 나타나는지를 확인합니다.", "지지선에 닿았다는 사실만으로 반등을 확정하지 않고 거래량과 저점 유지 여부를 함께 봅니다."],
                "holding": [f"보유 중이라면 {support}가 실제로 방어되는지 확인합니다.", "반등 후 저항까지 공간이 충분한지 확인하고, 저항에 매우 가까우면 기대수익이 제한될 수 있습니다."],
                "avoid": ["지지선을 이미 크게 이탈했는데 과거 지지 가격만 믿고 버티기", "반등 확인 없이 낙폭만 보고 진입"],
                "watch": ["지지 가격", "반등 거래량", "최근 저점"],
                "invalidation": f"지지 후보 {support}가 종가 기준 무너지고 빠르게 회복하지 못하면 지지선 반등 논리가 훼손됩니다.",
            },
            StrategyName.OVERSOLD_BOUNCE: {
                "new_entry": ["과매도는 '싸다'가 아니라 '짧은 기간 많이 하락했다'는 뜻이므로 반등 확인을 우선합니다.", "추세 반전이 아닌 단기 반등일 수 있으므로 다른 추세 전략보다 보수적으로 관찰합니다."],
                "holding": ["반등이 나오더라도 장기 상승 추세 복귀로 바로 해석하지 않습니다.", f"최근 지지 후보 {support}와 저점 재이탈 여부를 계속 확인합니다."],
                "avoid": ["RSI가 낮다는 이유만으로 계속 물타기", "하락 추세에서 목표를 지나치게 길게 잡기"],
                "watch": ["RSI 30~40 회복", "최근 저점", "반등 거래량"],
                "invalidation": f"최근 저점/지지 후보 {support}를 다시 크게 이탈하면 단기 반등 시나리오의 근거가 약해집니다.",
            },
            StrategyName.RANGE_TRADING: {
                "new_entry": [f"박스 하단에 가까운 지지 후보 {support}에서만 진입 검토 가치가 커지고, 중앙에서는 손익비가 나빠질 수 있습니다.", f"상단 저항 후보 {resistance}까지 남은 공간을 확인합니다."],
                "holding": ["박스 중앙에서는 방향성이 약하므로 상·하단 가격대를 기준으로 관리합니다.", f"저항 후보 {resistance} 근처에서는 추가 상승 여지가 줄어드는지 확인합니다."],
                "avoid": ["박스 상단에서 뒤늦게 추격", "박스 하단 이탈 후에도 횡보 전략이 그대로 유효하다고 가정"],
                "watch": ["박스 하단 지지", "박스 상단 저항", "ATR 확대 여부"],
                "invalidation": f"지지 {support} 또는 저항 {resistance}을 강한 거래량과 함께 벗어나면 박스권 전략보다 새로운 추세/돌파 전략으로 다시 분석합니다.",
            },
            StrategyName.MOMENTUM_CONTINUATION: {
                "new_entry": ["가격·거래량·추세가 동시에 강한지 확인하되 이미 너무 멀리 오른 자리에서는 추격 리스크를 먼저 봅니다.", "강한 흐름이 유지될 때 짧은 조정 후 재상승하는지를 관찰합니다."],
                "holding": ["보유 중이라면 상승 속도가 둔화되는지와 거래량이 급격히 줄어드는지 확인합니다.", f"20일선 {ma20}에서 지나치게 멀어졌다가 급격히 되돌리는지 주의합니다."],
                "avoid": ["급등률만 보고 모멘텀이라고 판단", "거래량이 꺾였는데 가격만 보고 추격"],
                "watch": ["거래량 증가", "RSI 과열 접근", "고점 갱신 지속"],
                "invalidation": f"고점 갱신이 멈추고 20일선 {ma20} 아래로 빠르게 밀리면 모멘텀 지속 전략이 약해집니다.",
            },
            StrategyName.VOLATILITY_SQUEEZE: {
                "new_entry": ["변동폭과 거래량이 줄어드는 동안 미리 방향을 단정하지 않고 압축 구간의 상단 돌파를 기다립니다.", f"저항 후보 {resistance} 돌파와 거래량 증가가 함께 나타나는지 확인합니다."],
                "holding": ["보유 중이라면 압축 구간을 어느 방향으로 벗어나는지 확인합니다.", "상방 돌파 없이 변동성만 커지는 경우 전략을 다시 평가합니다."],
                "avoid": ["변동성 축소만 보고 상승 돌파를 확정", "압축 구간 안에서 잦은 추격 매매"],
                "watch": ["ATR", "거래량 감소", "20일 고점/저항 돌파"],
                "invalidation": f"압축 구간 하단 또는 지지 후보 {support}를 먼저 이탈하면 상방 스퀴즈 시나리오가 약해집니다.",
            },
            StrategyName.MA20_REBOUND: {
                "new_entry": [f"현재가가 20일선 {ma20} 근처에서 실제 지지를 받는지 확인합니다.", "20일선에 닿은 것 자체보다 반등과 저점 유지가 중요합니다."],
                "holding": [f"20일선 {ma20} 위에서 회복하는 동안 단기 추세가 유지되는지 봅니다.", "20일선 이탈 뒤 즉시 회복하는지, 아래에서 머무는지가 중요합니다."],
                "avoid": ["하락 기울기의 20일선을 무조건 지지선으로 간주", "20일선 아래에서 계속 평균단가 낮추기"],
                "watch": ["20일선 재지지", "20일선 기울기", "최근 저점"],
                "invalidation": f"20일선 {ma20}을 이탈하고 지지 후보 {support}까지 무너지면 20일선 반등 전략의 근거가 약해집니다.",
            },
            StrategyName.TREND_RECOVERY: {
                "new_entry": ["하락/조정 뒤 처음 나타난 반등은 가짜 반등일 수 있으므로 20일선 회복과 저점 상승을 함께 확인합니다.", "완전한 상승 추세보다 불확실성이 높으므로 확인 신호가 더 필요합니다."],
                "holding": ["회복 과정에서는 전고점보다 먼저 저점이 높아지는지를 봅니다.", f"지지 후보 {support}가 유지되면서 20일선 {ma20} 위에서 버티는지 확인합니다."],
                "avoid": ["첫 양봉 하나만 보고 추세 전환 확정", "하락 추세가 계속되는 동안 반등마다 무조건 추가매수"],
                "watch": ["20일선 회복", "higher low", "RSI 40~60 회복"],
                "invalidation": f"회복 후 다시 20일선 {ma20}과 지지 후보 {support} 아래로 밀리면 추세 회복 시나리오를 재검토합니다.",
            },
            StrategyName.NO_TRADE: {
                "new_entry": ["현재는 새 진입보다 관찰 우선입니다.", "조건이 좋아질 때까지 가격 알림이나 관심종목으로 관리하는 편이 논리적입니다."],
                "holding": ["이미 보유 중이라면 신규 전략 점수가 낮다는 이유만으로 즉시 정리한다는 뜻은 아닙니다.", f"보유 근거와 지지 후보 {support}, 20일선 {ma20} 훼손 여부를 별도로 확인합니다."],
                "avoid": ["매매할 이유가 없는데 억지로 전략 하나를 선택", "낮은 적합도 점수를 상승확률로 오해"],
                "watch": ["전략 조건 변화", "시장 국면", "지지/저항 접근"],
                "invalidation": "NO TRADE는 하나의 진입 전략이 아니라 '현재 조건에서는 관찰'이라는 상태입니다. 조건이 바뀌면 다시 분석합니다.",
            },
        }
        return plans[strategy]

    @classmethod
    def _no_trade(
        cls,
        data: StrategyInput,
        blockers: list[str],
        reason: str,
    ) -> StrategyEvaluation:
        return StrategyEvaluation(
            strategy=StrategyName.NO_TRADE,
            score=None,
            eligible=True,
            passed=0,
            total=0,
            reasons=[reason],
            unmet=[] if blockers else ["전략별 핵심 조건이 아직 충분히 모이지 않았습니다."],
            blockers=blockers,
            note="조건이 불명확하거나 위험요인이 있어 신규 진입보다 관찰이 우선입니다.",
            action_plan=cls._action_plan(StrategyName.NO_TRADE, data),
        )

    @classmethod
    def _evaluate(
        cls,
        strategy: StrategyName,
        data: StrategyInput,
        conditions: list[Condition],
        blockers: list[str] | None = None,
        note: str = "",
    ) -> StrategyEvaluation:
        reasons: list[str] = []
        unmet: list[str] = []
        passed = 0
        max_score = sum(weight for _, weight, _ in conditions)
        score = 0

        for label, weight, predicate in conditions:
            ok = False
            try:
                ok = bool(predicate(data))
            except (TypeError, ValueError):
                ok = False
            if ok:
                passed += 1
                score += weight
                reasons.append(label)
            else:
                unmet.append(label)

        normalized_score = round(score / max_score * 100) if max_score else 0
        blockers = blockers or []
        return StrategyEvaluation(
            strategy=strategy,
            score=normalized_score,
            eligible=not blockers and normalized_score >= 40,
            passed=passed,
            total=len(conditions),
            reasons=reasons,
            unmet=unmet,
            blockers=blockers,
            note=note,
            action_plan=cls._action_plan(strategy, data),
        )

    def _trend_following(self, d: StrategyInput) -> StrategyEvaluation:
        return self._evaluate(StrategyName.TREND_FOLLOWING, d, [
            ("현재가가 20일 이동평균선 위", 18, lambda x: x.ma20 is not None and x.current_price > x.ma20),
            ("20일선이 60일선 위", 18, lambda x: x.ma20 is not None and x.ma60 is not None and x.ma20 > x.ma60),
            ("60일선이 120일선 위", 12, lambda x: x.ma60 is not None and x.ma120 is not None and x.ma60 > x.ma120),
            ("20일 이동평균 기울기 상승", 15, lambda x: x.ma20_slope_pct is not None and x.ma20_slope_pct > 0),
            ("고점 상승 구조", 10, lambda x: x.higher_high is True),
            ("저점 상승 구조", 10, lambda x: x.higher_low is True),
            ("시장 대비 상대강도 양호", 6, lambda x: x.relative_strength_market_pct is not None and x.relative_strength_market_pct > 0),
            ("업종 대비 상대강도 양호", 4, lambda x: (x.relative_strength_sector_pct > 0) if x.relative_strength_sector_pct is not None else (x.relative_strength_market_pct is not None and x.relative_strength_market_pct > 0)),
            ("시장 국면이 상승 추세", 7, lambda x: x.market_regime == MarketRegime.TREND_UP),
        ], note="상승 추세가 이미 확인된 종목을 따라가는 전략입니다.")

    def _pullback(self, d: StrategyInput) -> StrategyEvaluation:
        return self._evaluate(StrategyName.PULLBACK, d, [
            ("20일선이 60일선 위", 20, lambda x: x.ma20 is not None and x.ma60 is not None and x.ma20 > x.ma60),
            ("20일 이동평균 기울기 상승", 15, lambda x: x.ma20_slope_pct is not None and x.ma20_slope_pct > 0),
            ("주요 지지선과 4% 이내", 20, lambda x: x.support_distance_pct is not None and 0 <= x.support_distance_pct <= 4),
            ("RSI가 40~65 범위", 12, lambda x: x.rsi14 is not None and 40 <= x.rsi14 <= 65),
            ("거래량이 20일 평균의 1.3배 이하", 10, lambda x: x.volume_ratio_20 is not None and x.volume_ratio_20 <= 1.3),
            ("저점 상승 구조 유지", 10, lambda x: x.higher_low is True),
            ("시장 대비 상대강도 양호", 4, lambda x: x.relative_strength_market_pct is not None and x.relative_strength_market_pct >= 0),
            ("업종 대비 상대강도 양호", 4, lambda x: (x.relative_strength_sector_pct >= 0) if x.relative_strength_sector_pct is not None else (x.relative_strength_market_pct is not None and x.relative_strength_market_pct >= 0)),
            ("상승 시장 또는 중립 시장", 5, lambda x: x.market_regime in {MarketRegime.TREND_UP, MarketRegime.RANGE}),
        ], note="상승 추세 안에서 지지구간 조정을 이용하는 전략입니다.")

    def _breakout(self, d: StrategyInput) -> StrategyEvaluation:
        return self._evaluate(StrategyName.BREAKOUT, d, [
            ("20일 고점과 2% 이내", 20, lambda x: x.distance_to_20d_high_pct is not None and 0 <= x.distance_to_20d_high_pct <= 2),
            ("거래량이 20일 평균의 1.5배 이상", 20, lambda x: x.volume_ratio_20 is not None and x.volume_ratio_20 >= 1.5),
            ("현재가가 20일선 위", 15, lambda x: x.ma20 is not None and x.current_price > x.ma20),
            ("20일선 기울기 상승", 12, lambda x: x.ma20_slope_pct is not None and x.ma20_slope_pct > 0),
            ("RSI 과열 전 구간", 10, lambda x: x.rsi14 is not None and 50 <= x.rsi14 < 75),
            ("20일 시장 대비 상대강도 양호", 10, lambda x: x.relative_strength_market_pct is not None and x.relative_strength_market_pct > 0),
            ("20일 업종 대비 상대강도 양호", 8, lambda x: (x.relative_strength_sector_pct > 0) if x.relative_strength_sector_pct is not None else (x.relative_strength_market_pct is not None and x.relative_strength_market_pct > 0)),
            ("상승 시장", 5, lambda x: x.market_regime == MarketRegime.TREND_UP),
        ], note="주요 고점 부근에서 거래량이 동반되는 돌파 후보를 평가합니다.")

    def _support_bounce(self, d: StrategyInput) -> StrategyEvaluation:
        return self._evaluate(StrategyName.SUPPORT_BOUNCE, d, [
            ("주요 지지선과 2.5% 이내", 25, lambda x: x.support_distance_pct is not None and 0 <= x.support_distance_pct <= 2.5),
            ("RSI가 35~60 범위", 15, lambda x: x.rsi14 is not None and 35 <= x.rsi14 <= 60),
            ("ATR 변동성이 과도하지 않음", 12, lambda x: x.atr_pct is not None and x.atr_pct <= 5),
            ("거래량이 평균 이상", 10, lambda x: x.volume_ratio_20 is not None and x.volume_ratio_20 >= 1.0),
            ("저점 상승 또는 유지", 15, lambda x: x.higher_low is True),
            ("저항까지 최소 4% 여유", 13, lambda x: x.resistance_distance_pct is not None and x.resistance_distance_pct >= 4),
            ("시장 급락 아님", 10, lambda x: x.market_regime not in {MarketRegime.TREND_DOWN, MarketRegime.PANIC}),
        ], note="명확한 지지구간에서 반등 여력이 있는지를 평가합니다.")

    def _oversold_bounce(self, d: StrategyInput) -> StrategyEvaluation:
        return self._evaluate(StrategyName.OVERSOLD_BOUNCE, d, [
            ("RSI 35 이하", 28, lambda x: x.rsi14 is not None and x.rsi14 <= 35),
            ("주요 지지선과 4% 이내", 20, lambda x: x.support_distance_pct is not None and 0 <= x.support_distance_pct <= 4),
            ("거래량 증가", 12, lambda x: x.volume_ratio_20 is not None and x.volume_ratio_20 >= 1.2),
            ("저항까지 최소 5% 여유", 15, lambda x: x.resistance_distance_pct is not None and x.resistance_distance_pct >= 5),
            ("ATR 7% 이하", 10, lambda x: x.atr_pct is not None and x.atr_pct <= 7),
            ("시장 PANIC 아님", 10, lambda x: x.market_regime != MarketRegime.PANIC),
            ("최근 저점 구조가 완전히 붕괴하지 않음", 5, lambda x: x.higher_low is not False),
        ], note="과매도 상태에서 기술적 반등 가능성을 평가하는 역추세 전략입니다.")

    def _range_trading(self, d: StrategyInput) -> StrategyEvaluation:
        return self._evaluate(StrategyName.RANGE_TRADING, d, [
            ("시장 국면이 횡보", 25, lambda x: x.market_regime == MarketRegime.RANGE),
            ("20일선 기울기가 ±0.3% 이내", 20, lambda x: x.ma20_slope_pct is not None and abs(x.ma20_slope_pct) <= 0.3),
            ("지지선과 3% 이내", 18, lambda x: x.support_distance_pct is not None and 0 <= x.support_distance_pct <= 3),
            ("저항까지 최소 4% 여유", 15, lambda x: x.resistance_distance_pct is not None and x.resistance_distance_pct >= 4),
            ("RSI 35~60", 12, lambda x: x.rsi14 is not None and 35 <= x.rsi14 <= 60),
            ("ATR 4% 이하", 10, lambda x: x.atr_pct is not None and x.atr_pct <= 4),
        ], note="뚜렷한 추세가 없는 박스권에서 지지/저항 범위를 활용합니다.")

    def _momentum_continuation(self, d: StrategyInput) -> StrategyEvaluation:
        return self._evaluate(StrategyName.MOMENTUM_CONTINUATION, d, [
            ("현재가가 20일선 위", 15, lambda x: x.ma20 is not None and x.current_price > x.ma20),
            ("20일선 기울기 0.8% 이상", 15, lambda x: x.ma20_slope_pct is not None and x.ma20_slope_pct >= 0.8),
            ("RSI 55~75", 15, lambda x: x.rsi14 is not None and 55 <= x.rsi14 <= 75),
            ("거래량 20일 평균의 1.2배 이상", 15, lambda x: x.volume_ratio_20 is not None and x.volume_ratio_20 >= 1.2),
            ("고점 상승 구조", 10, lambda x: x.higher_high is True),
            ("저점 상승 구조", 10, lambda x: x.higher_low is True),
            ("20일 고점과 5% 이내", 5, lambda x: x.distance_to_20d_high_pct is not None and x.distance_to_20d_high_pct <= 5),
            ("20일 시장 대비 상대강도 양호", 10, lambda x: x.relative_strength_market_pct is not None and x.relative_strength_market_pct > 0),
            ("시장 급락 아님", 5, lambda x: x.market_regime not in {MarketRegime.TREND_DOWN, MarketRegime.PANIC}),
        ], note="강한 가격·거래량 흐름이 계속 이어질 가능성이 있는 구간을 평가합니다.")

    def _volatility_squeeze(self, d: StrategyInput) -> StrategyEvaluation:
        return self._evaluate(StrategyName.VOLATILITY_SQUEEZE, d, [
            ("ATR 3.5% 이하", 20, lambda x: x.atr_pct is not None and x.atr_pct <= 3.5),
            ("거래량이 20일 평균 이하", 15, lambda x: x.volume_ratio_20 is not None and x.volume_ratio_20 <= 1.0),
            ("20일 고점과 4% 이내", 20, lambda x: x.distance_to_20d_high_pct is not None and x.distance_to_20d_high_pct <= 4),
            ("현재가가 20일선 위", 15, lambda x: x.ma20 is not None and x.current_price >= x.ma20),
            ("20일선 기울기 하락 아님", 10, lambda x: x.ma20_slope_pct is not None and x.ma20_slope_pct >= 0),
            ("저항과 4% 이내", 10, lambda x: x.resistance_distance_pct is not None and x.resistance_distance_pct <= 4),
            ("시장 급락 아님", 10, lambda x: x.market_regime not in {MarketRegime.TREND_DOWN, MarketRegime.PANIC}),
        ], note="가격 변동과 거래량이 줄어든 뒤 방향성 돌파를 준비하는 압축 구간을 평가합니다.")

    def _ma20_rebound(self, d: StrategyInput) -> StrategyEvaluation:
        return self._evaluate(StrategyName.MA20_REBOUND, d, [
            ("현재가가 20일선과 2.5% 이내", 25, lambda x: x.ma20 is not None and abs(x.current_price - x.ma20) / x.current_price * 100 <= 2.5),
            ("20일선 기울기 상승", 20, lambda x: x.ma20_slope_pct is not None and x.ma20_slope_pct > 0),
            ("RSI 40~65", 15, lambda x: x.rsi14 is not None and 40 <= x.rsi14 <= 65),
            ("저점 상승 구조", 15, lambda x: x.higher_low is True),
            ("거래량 1.3배 이하", 10, lambda x: x.volume_ratio_20 is not None and x.volume_ratio_20 <= 1.3),
            ("시장 급락 아님", 15, lambda x: x.market_regime not in {MarketRegime.TREND_DOWN, MarketRegime.PANIC}),
        ], note="상승 중인 20일 이동평균선 부근에서 다시 지지받는지를 평가합니다.")

    def _trend_recovery(self, d: StrategyInput) -> StrategyEvaluation:
        return self._evaluate(StrategyName.TREND_RECOVERY, d, [
            ("현재가가 20일선 위로 회복", 20, lambda x: x.ma20 is not None and x.current_price >= x.ma20),
            ("20일선 기울기가 급락 아님", 15, lambda x: x.ma20_slope_pct is not None and x.ma20_slope_pct >= -0.3),
            ("RSI 40~60", 15, lambda x: x.rsi14 is not None and 40 <= x.rsi14 <= 60),
            ("최근 저점 상승", 20, lambda x: x.higher_low is True),
            ("지지선과 5% 이내", 15, lambda x: x.support_distance_pct is not None and x.support_distance_pct <= 5),
            ("시장 PANIC 아님", 15, lambda x: x.market_regime != MarketRegime.PANIC),
        ], note="조정이나 약세 뒤 20일선과 저점 구조를 회복하는 초기 추세 전환 후보를 평가합니다.")
