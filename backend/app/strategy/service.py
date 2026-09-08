from __future__ import annotations

import asyncio
from typing import Any

from app.market.event_risk import EventRiskAnalyzer
from app.market.providers import KrxProvider, OpenDartProvider
from app.market.technical import TechnicalAnalyzer
from app.risk import RiskEngine
from app.strategy.engine import StrategyEngine
from app.strategy.models import MarketRegime, StrategyInput, StrategyName


class StrategyAnalysisService:
    CURRENT_CONFIRMATION_REQUIREMENTS: dict[StrategyName, list[str]] = {
        StrategyName.TREND_FOLLOWING: [],
        StrategyName.PULLBACK: ["volume"],
        StrategyName.BREAKOUT: ["volume"],
        StrategyName.SUPPORT_BOUNCE: ["volume"],
        StrategyName.OVERSOLD_BOUNCE: ["volume"],
        StrategyName.RANGE_TRADING: [],
        StrategyName.MOMENTUM_CONTINUATION: ["volume"],
        StrategyName.VOLATILITY_SQUEEZE: ["high", "low", "volume"],
        StrategyName.MA20_REBOUND: [],
        StrategyName.TREND_RECOVERY: [],
    }

    def __init__(self, krx: KrxProvider, dart: OpenDartProvider | None = None) -> None:
        self.krx = krx
        self.dart = dart
        self.event = EventRiskAnalyzer(dart) if dart is not None else None
        self.technical = TechnicalAnalyzer()
        self.engine = StrategyEngine()
        self.risk = RiskEngine()

    @staticmethod
    def _regime_from_index(change_rate: float | None) -> MarketRegime:
        if change_rate is None:
            return MarketRegime.UNKNOWN
        if change_rate >= 1.0:
            return MarketRegime.TREND_UP
        if change_rate <= -1.0:
            return MarketRegime.TREND_DOWN
        return MarketRegime.RANGE

    @staticmethod
    def _risk_gate_payload(evaluations: list[Any]) -> dict[str, Any]:
        no_trade = next((item for item in evaluations if item.strategy == StrategyName.NO_TRADE), None)
        return {
            "active": bool(no_trade and no_trade.blockers),
            "decision": "HOLD" if no_trade else "EVALUATE",
            "reasons": list(no_trade.blockers) if no_trade else [],
            "message": (
                no_trade.reasons[0]
                if no_trade
                else "리스크 게이트가 활성화되지 않았습니다. 전략 적합도를 비교할 수 있습니다."
            ),
        }

    @staticmethod
    def _regular(evaluations: list[Any]) -> list[Any]:
        return [item for item in evaluations if item.strategy != StrategyName.NO_TRADE]

    @staticmethod
    def _best_regular(evaluations: list[Any]) -> Any | None:
        regular = StrategyAnalysisService._regular(evaluations)
        return regular[0] if regular else None

    def _input(
        self,
        *,
        code: str,
        market: str,
        technical: dict[str, Any],
        regime: MarketRegime,
        liquidity_ok: bool,
        price: float,
        ma20: float | None,
        rsi14: float | None,
        atr_pct: float | None,
        volume_ratio_20: float | None,
        distance_to_high: float | None,
        support_distance: float | None,
        resistance_distance: float | None,
        extreme_move: bool,
        data_stale: bool,
        source: str,
        index_rate: float | None,
        history_points: int,
        event_risk: bool = False,
    ) -> StrategyInput:
        return StrategyInput(
            code=code,
            market=market.upper(),
            current_price=price,
            ma20=ma20,
            ma60=technical.get("ma60"),
            ma120=technical.get("ma120"),
            ma20_slope_pct=technical.get("ma20_slope_pct"),
            rsi14=rsi14,
            atr_pct=atr_pct,
            volume_ratio_20=volume_ratio_20,
            distance_to_20d_high_pct=distance_to_high,
            support_distance_pct=support_distance,
            resistance_distance_pct=resistance_distance,
            support_price=technical.get("support"),
            resistance_price=technical.get("resistance"),
            higher_high=technical.get("higher_high"),
            higher_low=technical.get("higher_low"),
            relative_strength_market_pct=None,
            relative_strength_sector_pct=None,
            market_regime=regime,
            event_risk=event_risk,
            liquidity_ok=liquidity_ok,
            tradable=True,
            extreme_move=extreme_move,
            data_stale=data_stale,
            metadata={
                "market_index_change_rate": index_rate,
                "history_points": history_points,
                "price_source": source,
            },
        )

    def _risk_analysis(
        self,
        *,
        strategy_input: StrategyInput,
        evaluations: list[Any],
        technical: dict[str, Any],
        risk_gate: dict[str, Any],
        basis: str,
    ) -> dict[str, Any]:
        regular = [item for item in evaluations if item.strategy != StrategyName.NO_TRADE and item.score is not None]
        regular.sort(key=lambda item: item.score or 0, reverse=True)

        plans = [
            self.risk.build_plan(
                data=strategy_input,
                strategy=item.strategy,
                technical=technical,
                risk_gate_active=bool(risk_gate.get("active")),
                risk_gate_reasons=list(risk_gate.get("reasons") or []),
                basis=basis,
            )
            for item in regular[:3]
        ]

        selected = plans[0] if plans else None
        if selected is None:
            summary = "현재 계산 가능한 전략 리스크 구조가 없습니다."
            status = "UNAVAILABLE"
        else:
            summary = selected.summary
            status = selected.status.value

        return {
            "status": status,
            "basis": basis,
            "reference_only": bool(selected.reference_only) if selected else True,
            "selected_strategy": selected.strategy if selected else None,
            "selected_plan": selected.to_dict() if selected else None,
            "plans": [plan.to_dict() for plan in plans],
            "summary": summary,
            "policy": {
                "real_trading": False,
                "order_execution": False,
                "message": "손절·목표 가격은 분석 참고값이며 실제 증권사 주문으로 전송되지 않습니다.",
            },
        }

    def _comparison(
        self,
        eod_evaluations: list[Any],
        reference_evaluations: list[Any],
        supplied: dict[str, bool],
    ) -> list[dict[str, Any]]:
        eod_map = {item.strategy: item for item in self._regular(eod_evaluations)}
        ref_map = {item.strategy: item for item in self._regular(reference_evaluations)}
        rows: list[dict[str, Any]] = []
        for strategy, ref in ref_map.items():
            eod = eod_map.get(strategy)
            required = self.CURRENT_CONFIRMATION_REQUIREMENTS.get(strategy, [])
            missing = [field for field in required if not supplied.get(field, False)]
            if missing:
                current_data_status = "PARTIAL"
                current_data_message = "현재가 반영 완료 · " + ", ".join(missing) + " 미입력으로 일부 조건은 EOD 유지"
            else:
                current_data_status = "PRICE_UPDATED" if not required else "CONFIRMATION_UPDATED"
                current_data_message = "현재 참고정보로 이 전략의 핵심 가격 조건을 갱신했습니다."
            eod_score = eod.score if eod else None
            ref_score = ref.score
            delta = None if eod_score is None or ref_score is None else ref_score - eod_score
            rows.append({
                "strategy": strategy.value,
                "eod_score": eod_score,
                "reference_score": ref_score,
                "score_delta": delta,
                "reference_eligible": ref.eligible,
                "current_data_status": current_data_status,
                "current_data_message": current_data_message,
                "missing_current_inputs": missing,
            })
        rows.sort(key=lambda item: item.get("reference_score") or 0, reverse=True)
        return rows


    @staticmethod
    def _check(
        *,
        key: str,
        label: str,
        status: str,
        value: str,
        explanation: str,
        source: str,
    ) -> dict[str, str]:
        return {
            "key": key,
            "label": label,
            "status": status,
            "value": value,
            "explanation": explanation,
            "source": source,
        }

    @classmethod
    def _automatic_checks(
        cls,
        strategy: StrategyName,
        data: StrategyInput,
        technical: dict[str, Any],
        *,
        source: str,
    ) -> list[dict[str, str]]:
        checks: list[dict[str, str]] = []

        def percent(value: float | None) -> str:
            return "데이터 부족" if value is None else f"{value:.2f}%"

        def multiple(value: float | None) -> str:
            return "데이터 부족" if value is None else f"{value:.2f}배"

        def won(value: float | None) -> str:
            return "데이터 부족" if value is None else f"{value:,.0f}원"

        # 공통 추세 구조 점검
        if data.ma20 is None:
            checks.append(cls._check(key="price_ma20", label="20일선 위치", status="UNKNOWN", value="데이터 부족", explanation="20일 이동평균을 계산할 데이터가 부족합니다.", source=source))
        else:
            above = data.current_price >= data.ma20
            checks.append(cls._check(
                key="price_ma20",
                label="20일선 위치",
                status="PASS" if above else "FAIL",
                value=f"현재 {won(data.current_price)} / MA20 {won(data.ma20)}",
                explanation="현재 가격이 20일선 위에 있습니다." if above else "현재 가격이 20일선 아래에 있어 단기 추세가 약해진 상태입니다.",
                source=source,
            ))

        if data.ma20_slope_pct is None:
            checks.append(cls._check(key="ma20_slope", label="20일선 기울기", status="UNKNOWN", value="데이터 부족", explanation="20일선 기울기를 계산할 데이터가 부족합니다.", source="KRX_EOD"))
        else:
            slope = data.ma20_slope_pct
            status = "PASS" if slope > 0.3 else "WARN" if slope >= -0.3 else "FAIL"
            explanation = "20일선이 뚜렷하게 상승 중입니다." if status == "PASS" else "20일선이 거의 평평합니다." if status == "WARN" else "20일선이 하락 중입니다."
            checks.append(cls._check(key="ma20_slope", label="20일선 기울기", status=status, value=percent(slope), explanation=explanation, source="KRX_EOD"))

        if data.higher_low is None:
            checks.append(cls._check(key="recent_low", label="최근 저점 구조", status="UNKNOWN", value="데이터 부족", explanation="최근 저점 구조를 판정할 데이터가 부족합니다.", source="KRX_EOD"))
        else:
            checks.append(cls._check(
                key="recent_low",
                label="최근 저점 구조",
                status="PASS" if data.higher_low else "FAIL",
                value="저점 상승" if data.higher_low else "저점 하락",
                explanation="최근 저점이 이전 구간보다 높아 구조가 유지됩니다." if data.higher_low else "최근 저점이 이전 구간보다 낮아져 추세 훼손 신호가 있습니다.",
                source="KRX_EOD",
            ))

        if data.support_price is None or data.support_distance_pct is None:
            checks.append(cls._check(key="support", label="지지 구간", status="UNKNOWN", value="데이터 부족", explanation="지지 후보를 계산할 수 없습니다.", source="KRX_EOD"))
        else:
            distance = data.support_distance_pct
            if distance < 0:
                status = "FAIL"
                explanation = "현재 가격이 기존 지지 후보 아래에 있습니다."
            elif distance <= 3:
                status = "PASS"
                explanation = "현재 가격이 주요 지지 후보에 가깝습니다."
            elif distance <= 7:
                status = "WARN"
                explanation = "지지 후보와 다소 거리가 있습니다."
            else:
                status = "WARN"
                explanation = "지지 후보에서 많이 떨어져 있어 손절 기준이 멀어질 수 있습니다."
            checks.append(cls._check(key="support", label="지지 구간", status=status, value=f"{won(data.support_price)} · 거리 {percent(distance)}", explanation=explanation, source=source))

        if data.resistance_price is None or data.resistance_distance_pct is None:
            checks.append(cls._check(key="resistance", label="저항 구간", status="UNKNOWN", value="데이터 부족", explanation="저항 후보를 계산할 수 없습니다.", source="KRX_EOD"))
        else:
            distance = data.resistance_distance_pct
            if distance < 0:
                status = "PASS" if strategy in {StrategyName.BREAKOUT, StrategyName.MOMENTUM_CONTINUATION} else "WARN"
                explanation = "기존 저항 후보 위에 있습니다. 돌파 유지 여부를 확인합니다."
            elif distance < 2:
                status = "WARN"
                explanation = "저항이 매우 가까워 신규 진입 시 기대수익 공간이 짧을 수 있습니다."
            elif distance >= 5:
                status = "PASS"
                explanation = "다음 저항까지 가격 공간이 비교적 남아 있습니다."
            else:
                status = "WARN"
                explanation = "저항까지 남은 공간이 크지 않습니다."
            checks.append(cls._check(key="resistance", label="저항까지 여유", status=status, value=f"{won(data.resistance_price)} · 거리 {percent(distance)}", explanation=explanation, source=source))

        if data.volume_ratio_20 is None:
            checks.append(cls._check(key="volume", label="거래량", status="UNKNOWN", value="데이터 부족", explanation="현재 거래량을 입력하지 않았다면 확정 EOD 거래량 기준만 사용할 수 있습니다.", source="KRX_EOD"))
        else:
            ratio = data.volume_ratio_20
            if strategy in {StrategyName.BREAKOUT, StrategyName.MOMENTUM_CONTINUATION, StrategyName.SUPPORT_BOUNCE, StrategyName.OVERSOLD_BOUNCE}:
                status = "PASS" if ratio >= 1.5 else "WARN" if ratio >= 1.0 else "FAIL"
                explanation = "전략에 필요한 거래량 증가가 확인됩니다." if status == "PASS" else "거래량 증가가 충분하지 않습니다." if status == "WARN" else "거래량이 평균보다 낮아 강한 움직임 확인이 부족합니다."
            elif strategy == StrategyName.PULLBACK:
                status = "PASS" if ratio <= 1.3 else "WARN"
                explanation = "조정 구간 거래량이 과도하게 증가하지 않았습니다." if status == "PASS" else "조정 중 거래량이 커서 단순 눌림인지 확인이 필요합니다."
            else:
                status = "PASS" if 0.6 <= ratio <= 1.8 else "WARN"
                explanation = "거래량이 최근 평균 범위에 있습니다." if status == "PASS" else "거래량이 평소 범위와 크게 다릅니다."
            checks.append(cls._check(key="volume", label="거래량 상태", status=status, value=multiple(ratio), explanation=explanation, source=source))

        if data.rsi14 is None:
            checks.append(cls._check(key="rsi", label="RSI 상태", status="UNKNOWN", value="데이터 부족", explanation="RSI를 계산할 데이터가 부족합니다.", source=source))
        else:
            rsi = data.rsi14
            if strategy == StrategyName.OVERSOLD_BOUNCE:
                status = "PASS" if rsi <= 35 else "FAIL"
                explanation = "과매도 반등 조건에 가까운 RSI입니다." if status == "PASS" else "현재 RSI는 과매도 구간이 아닙니다."
            elif strategy in {StrategyName.BREAKOUT, StrategyName.MOMENTUM_CONTINUATION}:
                status = "PASS" if 50 <= rsi < 75 else "WARN" if rsi < 80 else "FAIL"
                explanation = "상승 모멘텀이 있으면서 과열 전 범위입니다." if status == "PASS" else "모멘텀 또는 과열 여부를 주의해서 봐야 합니다."
            else:
                status = "PASS" if 35 <= rsi <= 65 else "WARN"
                explanation = "중립적인 RSI 범위입니다." if status == "PASS" else "RSI가 일반적인 중립 범위를 벗어났습니다."
            checks.append(cls._check(key="rsi", label="RSI 상태", status=status, value=f"{rsi:.2f}", explanation=explanation, source=source))

        if strategy == StrategyName.BREAKOUT:
            distance = data.distance_to_20d_high_pct
            if distance is None:
                checks.append(cls._check(key="breakout_distance", label="20일 고점 접근", status="UNKNOWN", value="데이터 부족", explanation="20일 고점과의 거리를 계산할 수 없습니다.", source=source))
            else:
                status = "PASS" if distance <= 2 else "WARN" if distance <= 5 else "FAIL"
                checks.append(cls._check(key="breakout_distance", label="20일 고점 접근", status=status, value=percent(distance), explanation="돌파를 확인할 수 있는 가격대에 가깝습니다." if status == "PASS" else "아직 돌파 가격대와 거리가 있습니다.", source=source))

        if strategy == StrategyName.RANGE_TRADING:
            status = "PASS" if data.market_regime == MarketRegime.RANGE else "FAIL"
            checks.append(cls._check(key="market_regime", label="시장 국면", status=status, value=data.market_regime.value, explanation="횡보 전략에 맞는 시장 국면입니다." if status == "PASS" else "현재 시장 국면은 박스권 전략과 잘 맞지 않습니다.", source="KRX_INDEX"))

        return checks

    @classmethod
    def _evaluation_payloads(
        cls,
        evaluations: list[Any],
        data: StrategyInput,
        technical: dict[str, Any],
        *,
        source: str,
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for evaluation in evaluations:
            payload = evaluation.to_dict()
            payload["auto_checks"] = (
                []
                if evaluation.strategy == StrategyName.NO_TRADE
                else cls._automatic_checks(evaluation.strategy, data, technical, source=source)
            )
            payloads.append(payload)
        return payloads

    @staticmethod
    def _position_context(
        *,
        mode: str,
        average_price: float | None,
        quantity: float | None,
        analysis_price: float,
        strategy_input: StrategyInput,
        risk_analysis: dict[str, Any],
        risk_gate: dict[str, Any],
    ) -> dict[str, Any]:
        mode_key = mode.upper().strip()
        if mode_key not in {"NOT_HELD", "HOLDING"}:
            raise ValueError("position_mode는 NOT_HELD 또는 HOLDING이어야 합니다.")

        if mode_key == "NOT_HELD":
            return {
                "mode": "NOT_HELD",
                "label": "미보유",
                "analysis_price": analysis_price,
                "average_price": None,
                "quantity": None,
                "return_pct": None,
                "unrealized_pnl": None,
                "state": "NEW_ENTRY_VIEW",
                "summary": "현재 종목을 보유하지 않은 것으로 가정하여 신규 진입 관점으로 분석합니다.",
                "checks": [],
            }

        if average_price is None or average_price <= 0:
            raise ValueError("보유 중 분석에는 평균 매수가를 입력해야 합니다.")
        if quantity is not None and quantity <= 0:
            raise ValueError("보유 수량은 0보다 커야 합니다.")

        return_pct = (analysis_price / average_price - 1) * 100
        unrealized_pnl = None if quantity is None else (analysis_price - average_price) * quantity
        checks: list[dict[str, str]] = []

        checks.append({
            "key": "cost_basis",
            "label": "평균 매수가 대비",
            "status": "PASS" if return_pct >= 0 else "WARN",
            "value": f"{return_pct:+.2f}%",
            "explanation": "현재 분석가격이 평균 매수가보다 위에 있습니다." if return_pct >= 0 else "현재 분석가격이 평균 매수가보다 아래에 있습니다.",
        })

        if strategy_input.ma20 is None:
            checks.append({"key": "holding_ma20", "label": "20일선 유지", "status": "UNKNOWN", "value": "데이터 부족", "explanation": "20일선을 계산할 수 없습니다."})
        else:
            above = analysis_price >= strategy_input.ma20
            checks.append({
                "key": "holding_ma20",
                "label": "20일선 유지",
                "status": "PASS" if above else "FAIL",
                "value": f"현재 {analysis_price:,.0f}원 / MA20 {strategy_input.ma20:,.0f}원",
                "explanation": "현재 가격이 20일선 위에 있어 단기 구조가 유지됩니다." if above else "현재 가격이 20일선 아래로 내려가 단기 구조가 약해졌습니다.",
            })

        if strategy_input.support_price is None:
            checks.append({"key": "holding_support", "label": "지지 후보 유지", "status": "UNKNOWN", "value": "데이터 부족", "explanation": "지지 가격 후보를 계산할 수 없습니다."})
        else:
            above = analysis_price >= strategy_input.support_price
            checks.append({
                "key": "holding_support",
                "label": "지지 후보 유지",
                "status": "PASS" if above else "FAIL",
                "value": f"지지 후보 {strategy_input.support_price:,.0f}원",
                "explanation": "현재 가격이 지지 후보 위에 있습니다." if above else "현재 가격이 기존 지지 후보 아래에 있습니다.",
            })

        if strategy_input.higher_low is None:
            checks.append({"key": "holding_low", "label": "최근 저점 구조", "status": "UNKNOWN", "value": "데이터 부족", "explanation": "최근 저점 구조를 판정할 수 없습니다."})
        else:
            checks.append({
                "key": "holding_low",
                "label": "최근 저점 구조",
                "status": "PASS" if strategy_input.higher_low else "FAIL",
                "value": "저점 상승" if strategy_input.higher_low else "저점 하락",
                "explanation": "최근 저점 구조가 유지됩니다." if strategy_input.higher_low else "최근 저점 구조가 낮아져 추세 훼손 신호가 있습니다.",
            })

        selected_plan = risk_analysis.get("selected_plan") or {}
        invalidation = selected_plan.get("invalidation_price")
        invalidation_failed = False
        if invalidation is not None:
            invalidation_failed = analysis_price <= float(invalidation)
            distance = (analysis_price / float(invalidation) - 1) * 100 if invalidation else None
            checks.append({
                "key": "invalidation",
                "label": "전략 무효화 기준",
                "status": "FAIL" if invalidation_failed else "PASS",
                "value": f"{float(invalidation):,.0f}원" + ("" if distance is None else f" · 현재와 {distance:+.2f}%"),
                "explanation": "현재 가격이 전략 무효화 기준 아래에 있습니다." if invalidation_failed else "현재 가격은 전략 무효화 기준 위에 있습니다.",
            })

        if invalidation_failed:
            state = "STRATEGY_INVALIDATED"
            summary = "현재 가격이 선택 전략의 무효화 기준을 이미 이탈했습니다. 보유 포지션은 기존 전략이 유지된다고 가정하지 말고 다시 분석해야 합니다."
        elif risk_gate.get("active"):
            state = "RISK_REVIEW"
            summary = "신규 진입 리스크 게이트는 활성화되어 있지만, 보유 포지션은 별도 점검이 필요합니다. 아래 자동 점검과 전략 무효화 기준을 중심으로 현재 구조를 확인합니다."
        elif strategy_input.ma20 is not None and analysis_price < strategy_input.ma20 and strategy_input.higher_low is False:
            state = "WEAKENING"
            summary = "20일선과 최근 저점 구조가 동시에 약해져 보유 전략의 근거가 약해지는 상태입니다."
        else:
            state = "STRUCTURE_OK"
            summary = "현재 자동 점검상 보유 전략이 즉시 무효화된 상태는 아닙니다. 가격이 주요 지지·무효화 기준을 유지하는지 계속 관찰합니다."

        return {
            "mode": "HOLDING",
            "label": "보유 중",
            "analysis_price": analysis_price,
            "average_price": average_price,
            "quantity": quantity,
            "return_pct": round(return_pct, 3),
            "unrealized_pnl": None if unrealized_pnl is None else round(unrealized_pnl, 2),
            "state": state,
            "summary": summary,
            "checks": checks,
            "policy": "보유 상태 입력은 분석용 가정이며 실제 증권계좌와 연결하거나 주문을 전송하지 않습니다.",
        }


    @staticmethod
    def _position_action_guide(
        *,
        position_context: dict[str, Any],
        strategy_input: StrategyInput,
        risk_analysis: dict[str, Any],
        risk_gate: dict[str, Any],
        best_regular: Any | None,
        event_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """보유 상태 진단을 실제 대응 가이드로 변환합니다.

        실제 주문을 실행하지 않으며, BUY/SELL 명령 대신 조건부 대응 방향만 제공합니다.
        """
        if position_context.get("mode") != "HOLDING":
            return {
                "available": False,
                "primary_code": "NOT_APPLICABLE",
                "primary_label": "미보유",
                "headline": "보유 중인 포지션이 아닙니다.",
                "summary": "신규 진입 관점은 전략 카드의 신규 진입 가이드를 사용합니다.",
            }

        state = str(position_context.get("state") or "")
        return_pct = position_context.get("return_pct")
        analysis_price = float(position_context.get("analysis_price") or 0)
        ma20 = strategy_input.ma20
        support = strategy_input.support_price
        selected_plan = risk_analysis.get("selected_plan") or {}
        invalidation = selected_plan.get("invalidation_price")
        target1 = selected_plan.get("target1_price")
        target2 = selected_plan.get("target2_price")
        rating = selected_plan.get("structure_rating")
        rr2 = selected_plan.get("rr2")
        best_score = getattr(best_regular, "score", None) if best_regular is not None else None
        best_name = getattr(getattr(best_regular, "strategy", None), "value", None)

        ma20_distance = None
        if ma20 and analysis_price:
            ma20_distance = (analysis_price / float(ma20) - 1) * 100

        support_distance = strategy_input.support_distance_pct

        why: list[str] = []
        triggers: list[dict[str, str]] = []

        if invalidation is not None:
            triggers.append({
                "condition": f"{float(invalidation):,.0f}원 부근의 전략 무효화 기준을 하향 이탈",
                "effect": "기존 보유 논리를 유지하지 말고 포지션 축소·정리 여부를 재검토",
            })
        if ma20 is not None:
            triggers.append({
                "condition": f"20일선 {float(ma20):,.0f}원 위에서 회복·유지",
                "effect": "단기 추세 유지 여부를 계속 확인",
            })
        if target1 is not None:
            triggers.append({
                "condition": f"1차 목표 {float(target1):,.0f}원 접근",
                "effect": "일부 이익 보호 또는 목표 재설정 여부를 검토",
            })

        if state == "STRATEGY_INVALIDATED":
            primary_code = "EXIT_REVIEW"
            primary_label = "전략 종료·정리 검토"
            headline = "기존 보유 전략의 핵심 기준이 깨진 상태입니다."
            summary = "손실 여부와 무관하게 기존 전략을 그대로 유지할 근거가 약해졌습니다. 추가매수는 보류하고 포지션 축소·정리 여부를 우선 재검토하는 쪽이 합리적입니다."
            why.append("현재 가격이 선택 전략의 무효화 기준을 이탈했습니다.")
            hold = {
                "decision": "INVALIDATED",
                "label": "기존 전략 유지 비권장",
                "reason": "전략 무효화 기준이 이미 깨졌습니다.",
            }
            add = {
                "decision": "AVOID",
                "label": "추가매수 보류",
                "reason": "무효화된 전략에 손실만을 이유로 물타기하지 않습니다.",
            }
            reduce = {
                "decision": "REVIEW",
                "label": "리스크 축소·정리 검토",
                "reason": "기존 진입 논리가 깨졌으므로 보유 비중을 다시 판단할 시점입니다.",
            }

        elif bool((event_analysis or {}).get("risk_gate")):
            primary_code = "EVENT_REVIEW"
            primary_label = "공시 확인 우선"
            headline = "기술 구조보다 최근 중요 공시를 먼저 확인해야 하는 상태입니다."
            summary = "부정 가능성이 높은 HIGH 이벤트가 확인되어 추가매수와 신규 진입은 보류합니다. 보유 중이라면 공시 세부조건이 기존 보유 논리를 바꾸는지 먼저 확인한 뒤 비중 유지·축소 여부를 재평가합니다."
            high_events = [
                event for event in (event_analysis or {}).get("events", [])
                if event.get("impact_level", event.get("level")) == "HIGH"
                and event.get("direction") == "NEGATIVE"
            ]
            if high_events:
                why.append(f"최근 부정 HIGH 이벤트: {high_events[0].get('report_name')}")
            why.append("이벤트 리스크는 가격·이동평균보다 먼저 확인하는 Risk Gate입니다.")
            hold = {
                "decision": "EVENT_REVIEW",
                "label": "공시 조건 확인 후 보유 판단",
                "reason": "기술적 구조가 유지되더라도 중요한 기업행동은 기존 전략의 전제를 바꿀 수 있습니다.",
            }
            add = {
                "decision": "AVOID",
                "label": "추가매수 보류",
                "reason": "HIGH 공시 조건을 확인하기 전에는 손실 보전 목적 물타기나 비중 확대를 보류합니다.",
            }
            reduce = {
                "decision": "REVIEW",
                "label": "비중 재평가",
                "reason": "공시의 희석·재무·사업 영향이 크다면 기존 보유 비중을 줄일지 검토합니다.",
            }

        elif state == "WEAKENING":
            primary_code = "REDUCE_RISK_REVIEW"
            primary_label = "리스크 축소 검토"
            headline = "보유 근거가 약해지고 있습니다."
            summary = "즉시 매도를 의미하지는 않지만 20일선과 최근 저점 구조가 함께 약해졌습니다. 추가매수보다 기존 비중을 줄일지 검토하면서 회복 여부를 확인하는 단계입니다."
            why.extend([
                "20일선 또는 최근 저점 구조가 약해졌습니다.",
                "추가매수보다 구조 회복 확인이 우선입니다.",
            ])
            hold = {
                "decision": "CAUTION",
                "label": "조건부 보유",
                "reason": "회복 신호가 확인되는 동안 보유 근거를 재점검합니다.",
            }
            add = {
                "decision": "AVOID",
                "label": "물타기 보류",
                "reason": "추세 약화 상태에서 평균단가만 낮추는 추가매수는 근거가 부족합니다.",
            }
            reduce = {
                "decision": "REVIEW",
                "label": "비중 축소 검토",
                "reason": "20일선/저점 구조가 더 약해지면 손실 확대 전에 리스크 축소를 검토합니다.",
            }

        else:
            primary_code = "HOLD_OBSERVE"
            primary_label = "보유 관찰"
            if return_pct is not None and return_pct < 0:
                headline = "현재 손실 중이지만 보유 구조가 즉시 무효화된 상태는 아닙니다."
                summary = "평균 매수가보다 낮다는 이유만으로 물타기하거나 정리하지 않습니다. 20일선·지지선·전략 무효화 기준이 유지되는 동안은 관찰하되, 해당 기준이 깨지면 대응을 바꾸는 구조가 적절합니다."
                why.append(f"평균 매수가 대비 {float(return_pct):+.2f}%이지만 손실 자체는 매도/추가매수 신호가 아닙니다.")
            else:
                headline = "현재 자동 점검상 보유 논리가 유지되고 있습니다."
                summary = "주요 지지·20일선·전략 무효화 기준이 유지되는 동안은 보유 관찰이 기본입니다. 이익 중이라면 목표 구간 접근 시 이익 보호 기준을 같이 확인합니다."
                if return_pct is not None:
                    why.append(f"평균 매수가 대비 {float(return_pct):+.2f}% 상태입니다.")

            if ma20 is not None and analysis_price >= float(ma20):
                why.append("현재 가격이 20일선 위에 있습니다.")
            if support is not None and analysis_price >= float(support):
                why.append("현재 가격이 주요 지지 후보 위에 있습니다.")
            if invalidation is not None and analysis_price > float(invalidation):
                why.append("전략 무효화 가격 위에 있습니다.")

            hold = {
                "decision": "MAINTAIN",
                "label": "보유 관찰",
                "reason": "현재 구조가 유지되는 동안은 급하게 대응하기보다 핵심 기준 변화를 추적합니다.",
            }
            reduce = {
                "decision": "WATCH",
                "label": "축소 신호 없음",
                "reason": "현재 자동 점검만으로 즉시 비중을 줄여야 할 구조 훼손은 확인되지 않았습니다.",
            }

            near_support = (
                support_distance is not None
                and 0 <= float(support_distance) <= 4
            )
            near_ma20 = (
                ma20_distance is not None
                and 0 <= float(ma20_distance) <= 3
            )
            strategy_good = best_score is not None and float(best_score) >= 70
            rr_good = rr2 is not None and float(rr2) >= 1.5
            structure_good = rating in {"양호", "주의"}
            no_gate = not bool(risk_gate.get("active"))

            if no_gate and strategy_good and structure_good and rr_good and (near_support or near_ma20):
                add = {
                    "decision": "CONDITIONAL",
                    "label": "조건부 추가매수 검토",
                    "reason": "지지/20일선 근처에서 전략 적합도와 손익 구조가 함께 유지될 때만 분할 추가를 검토할 수 있습니다.",
                }
                why.append("추가매수는 손실 보전 목적이 아니라 지지·전략·손익비가 동시에 충족될 때만 검토합니다.")
            else:
                missing: list[str] = []
                if not no_gate:
                    missing.append("Risk Gate 해제")
                if not strategy_good:
                    missing.append("전략 적합도 70점 이상")
                if not (near_support or near_ma20):
                    missing.append("지지선/20일선 근접")
                if not rr_good:
                    missing.append("2차 목표 기준 R:R 1.5 이상")
                add = {
                    "decision": "WAIT",
                    "label": "추가매수 보류",
                    "reason": "현재는 " + ", ".join(missing[:3]) + " 조건이 부족합니다." if missing else "현재 추가매수 근거가 충분하지 않습니다.",
                }

        return {
            "available": True,
            "primary_code": primary_code,
            "primary_label": primary_label,
            "headline": headline,
            "summary": summary,
            "best_strategy": best_name,
            "best_strategy_score": best_score,
            "hold": hold,
            "add_position": add,
            "reduce_position": reduce,
            "why": why,
            "triggers": triggers,
            "levels": {
                "ma20": ma20,
                "support": support,
                "invalidation": invalidation,
                "target1": target1,
                "target2": target2,
            },
            "policy": "행동 가이드는 조건부 분석 참고이며 실제 매수·매도 주문을 실행하거나 전송하지 않습니다.",
        }

    async def analyze(
        self,
        code: str,
        market: str,
        as_of: str | None = None,
        history_points: int = 60,
        reference_price: float | None = None,
        reference_high: float | None = None,
        reference_low: float | None = None,
        reference_volume: float | None = None,
        position_mode: str = "NOT_HELD",
        average_price: float | None = None,
        quantity: float | None = None,
    ) -> dict[str, Any]:
        history = await self.krx.stock_history(
            market=market,
            code=code,
            as_of=as_of,
            points=history_points,
            lookback_days=max(60, history_points * 2),
        )
        technical = self.technical.analyze(history)
        latest_index = await self.krx.latest_index_daily(market, as_of)
        market_index = latest_index.get("main_index")
        index_rate = market_index.get("change_rate") if market_index else None
        regime = self._regime_from_index(index_rate)

        if self.event is not None:
            try:
                event_analysis = await self.event.analyze(
                    code,
                    position_mode=position_mode,
                    days=60,
                    detail_limit=4,
                    history=history,
                    reference_price=reference_price,
                    reference_volume=reference_volume,
                )
            except Exception as exc:  # DART 실패가 기술 분석 전체를 막지 않도록 격리
                event_analysis = {
                    "available": False,
                    "high_count": 0,
                    "medium_count": 0,
                    "low_count": 0,
                    "positive_count": 0,
                    "negative_count": 0,
                    "mixed_count": 0,
                    "risk_gate": False,
                    "message": f"공시 이벤트 분석 실패: {exc}",
                    "events": [],
                }
        else:
            event_analysis = {
                "available": False,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
                "positive_count": 0,
                "negative_count": 0,
                "mixed_count": 0,
                "risk_gate": False,
                "message": "OpenDART provider가 없어 이벤트 분석을 생략했습니다.",
                "events": [],
            }
        event_risk_active = bool(event_analysis.get("risk_gate"))

        latest = history[-1]
        trade_value = latest.get("trade_value")
        eod_liquidity_ok = trade_value is not None and float(trade_value) >= 1_000_000_000

        # 1) Locked EOD baseline: never altered by user input.
        eod_input = self._input(
            code=code,
            market=market,
            technical=technical,
            regime=regime,
            liquidity_ok=eod_liquidity_ok,
            price=float(technical["current_price"]),
            ma20=technical.get("ma20"),
            rsi14=technical.get("rsi14"),
            atr_pct=technical.get("atr_pct"),
            volume_ratio_20=technical.get("volume_ratio_20"),
            distance_to_high=technical.get("distance_to_20d_high_pct"),
            support_distance=technical.get("support_distance_pct"),
            resistance_distance=technical.get("resistance_distance_pct"),
            extreme_move=False,
            data_stale=False,
            source="KRX_EOD",
            index_rate=index_rate,
            history_points=len(history),
            event_risk=event_risk_active,
        )
        eod_evaluations = self.engine.evaluate_all(eod_input)

        reference_context = None
        reference_evaluations = eod_evaluations
        reference_input = eod_input

        if reference_price is not None:
            reference_context = self.technical.preview_with_reference_price(
                history,
                float(reference_price),
                technical,
                reference_high=reference_high,
                reference_low=reference_low,
                reference_volume=reference_volume,
            )
            estimated = reference_context["estimated"]
            current_trade_value = (
                float(reference_price) * float(reference_volume)
                if reference_volume is not None
                else None
            )
            reference_liquidity_ok = eod_liquidity_ok or bool(
                current_trade_value is not None and current_trade_value >= 1_000_000_000
            )

            reference_input = self._input(
                code=code,
                market=market,
                technical=technical,
                regime=regime,
                liquidity_ok=reference_liquidity_ok,
                price=float(reference_context["reference_price"]),
                ma20=estimated.get("ma20") or technical.get("ma20"),
                rsi14=estimated.get("rsi14") or technical.get("rsi14"),
                atr_pct=estimated.get("atr_pct") if estimated.get("atr_pct") is not None else technical.get("atr_pct"),
                volume_ratio_20=(
                    estimated.get("volume_ratio_20")
                    if estimated.get("volume_ratio_20") is not None
                    else technical.get("volume_ratio_20")
                ),
                distance_to_high=estimated.get("distance_to_20d_high_pct"),
                support_distance=estimated.get("support_distance_pct"),
                resistance_distance=estimated.get("resistance_distance_pct"),
                extreme_move=bool(reference_context.get("is_extreme_move")),
                data_stale=bool(reference_context.get("is_stale")),
                source="USER_INPUT",
                index_rate=index_rate,
                history_points=len(history),
                event_risk=event_risk_active,
            )
            reference_evaluations = self.engine.evaluate_all(reference_input)

        current_evaluations = reference_evaluations if reference_price is not None else eod_evaluations
        current_risk_gate = self._risk_gate_payload(current_evaluations)
        eod_risk_gate = self._risk_gate_payload(eod_evaluations)
        best_regular = self._best_regular(current_evaluations)

        comparison = []
        if reference_context is not None:
            comparison = self._comparison(
                eod_evaluations,
                reference_evaluations,
                reference_context.get("supplied", {}),
            )

        effective_atr = reference_input.atr_pct
        effective_volume = reference_input.volume_ratio_20

        risk_analysis = self._risk_analysis(
            strategy_input=reference_input,
            evaluations=current_evaluations,
            technical=technical,
            risk_gate=current_risk_gate,
            basis="MANUAL_REFERENCE" if reference_price is not None else "CONFIRMED_EOD",
        )

        current_source = "USER_INPUT" if reference_price is not None else "KRX_EOD"
        current_strategy_payloads = self._evaluation_payloads(
            current_evaluations, reference_input, technical, source=current_source
        )
        eod_strategy_payloads = self._evaluation_payloads(
            eod_evaluations, eod_input, technical, source="KRX_EOD"
        )
        reference_strategy_payloads = (
            self._evaluation_payloads(reference_evaluations, reference_input, technical, source="USER_INPUT")
            if reference_context is not None
            else None
        )
        position_context = self._position_context(
            mode=position_mode,
            average_price=average_price,
            quantity=quantity,
            analysis_price=reference_input.current_price,
            strategy_input=reference_input,
            risk_analysis=risk_analysis,
            risk_gate=current_risk_gate,
        )
        position_action_guide = self._position_action_guide(
            position_context=position_context,
            strategy_input=reference_input,
            risk_analysis=risk_analysis,
            risk_gate=current_risk_gate,
            best_regular=best_regular,
            event_analysis=event_analysis,
        )

        return {
            "code": code,
            "market": market.upper(),
            "real_trading": False,
            "data_date": latest.get("date"),
            "data_freshness": {
                "price_source": "USER_INPUT" if reference_price is not None else "KRX_EOD",
                "analysis_basis": "MANUAL_REFERENCE" if reference_price is not None else "CONFIRMED_EOD",
                "eod_date": latest.get("date"),
                "eod_close": technical.get("current_price"),
                "reference": reference_context,
            },
            "analysis_layers": {
                "confirmed_eod": {
                    "label": "확정 EOD 기준",
                    "immutable": True,
                    "price": technical.get("current_price"),
                    "ma20": technical.get("ma20"),
                    "rsi14": technical.get("rsi14"),
                    "atr_pct": technical.get("atr_pct"),
                    "volume_ratio_20": technical.get("volume_ratio_20"),
                    "risk_gate": eod_risk_gate,
                },
                "current_reference": None if reference_context is None else {
                    "label": "현재 참고가격 시나리오",
                    "temporary": True,
                    "input_mode": reference_context.get("input_mode"),
                    "price": reference_input.current_price,
                    "estimated_ma20": reference_input.ma20,
                    "estimated_rsi14": reference_input.rsi14,
                    "estimated_atr_pct": reference_context["estimated"].get("atr_pct"),
                    "effective_atr_pct": effective_atr,
                    "estimated_volume_ratio_20": reference_context["estimated"].get("volume_ratio_20"),
                    "effective_volume_ratio_20": effective_volume,
                    "risk_gate": current_risk_gate,
                },
            },
            "history_points": len(history),
            "first_load_note": (
                "첫 분석은 KRX 최근 거래일 캐시를 구축하므로 수초 걸릴 수 있습니다. "
                "이후 같은 시장 종목 분석은 날짜별 캐시를 재사용합니다."
            ),
            "technical": technical,
            "effective": {
                "price": reference_input.current_price,
                "ma20": reference_input.ma20,
                "rsi14": reference_input.rsi14,
                "support_distance_pct": reference_input.support_distance_pct,
                "resistance_distance_pct": reference_input.resistance_distance_pct,
                "distance_to_20d_high_pct": reference_input.distance_to_20d_high_pct,
                "atr_pct": effective_atr,
                "volume_ratio_20": effective_volume,
            },
            "market_context": {
                "regime": regime.value,
                "index_name": market_index.get("name") if market_index else None,
                "index_change_rate": index_rate,
            },
            "risk_gate": current_risk_gate,
            "event_risk": event_analysis,
            "risk_analysis": risk_analysis,
            "eod_risk_gate": eod_risk_gate,
            "position_context": position_context,
            "position_action_guide": position_action_guide,
            "strategies": current_strategy_payloads,
            "eod_strategies": eod_strategy_payloads,
            "reference_strategies": reference_strategy_payloads,
            "strategy_comparison": comparison,
            "top_strategy": current_strategy_payloads[0] if current_strategy_payloads else None,
            "best_regular_strategy": (
                next((item for item in current_strategy_payloads if item.get("strategy") == best_regular.strategy.value), None)
                if best_regular
                else None
            ),
            "history": history,
            "limitations": [
                "전략 점수는 수익 확률이 아니라 조건 적합도입니다.",
                "현재 참고가격 시나리오와 확정 EOD 전략을 별도 계산하여 비교합니다.",
                "현재가만 입력하면 예상 MA20/RSI와 가격 거리만 갱신되고, 당일 거래량/고저가는 확정할 수 없습니다.",
                "선택적으로 오늘 고가·저가·현재 거래량을 입력하면 예상 ATR과 거래량 조건까지 보완할 수 있습니다.",
                "사용자 입력값은 KRX 확정 일봉/캐시/DB에 저장하지 않습니다.",
                "보유 상태·평균 매수가·수량 입력은 현재 분석 요청에만 사용하는 가정값이며 실제 증권계좌와 연동되지 않습니다.",
                "OpenDART 최근 공시는 제목 분류 후 중요 공시에 대해 구조화 API 또는 원문 XML에서 세부조건을 보조 추출합니다.",
                "공시 자동요약은 원문을 대체하지 않으며 중요한 판단 전에는 DART 원문 확인이 필요합니다.",
                "업종 상대강도는 후속 단계에서 연결합니다.",
            ],
        }
