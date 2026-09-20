from __future__ import annotations

from typing import Any

from app.risk.models import RiskPlan, RiskPlanStatus
from app.risk.target1_policy import select_target1
from app.strategy.models import StrategyInput, StrategyName


class RiskEngine:
    """Builds explanatory risk structures only.

    This engine never sends or prepares brokerage orders. All output is a reference
    scenario for decision support, and is especially conservative when a Risk Gate
    is already active.
    """

    BUFFER_BY_STRATEGY: dict[StrategyName, float] = {
        StrategyName.TREND_FOLLOWING: 0.75,
        StrategyName.PULLBACK: 0.50,
        StrategyName.BREAKOUT: 0.50,
        StrategyName.SUPPORT_BOUNCE: 0.40,
        StrategyName.OVERSOLD_BOUNCE: 0.35,
        StrategyName.RANGE_TRADING: 0.30,
        StrategyName.MOMENTUM_CONTINUATION: 0.75,
        StrategyName.VOLATILITY_SQUEEZE: 0.50,
        StrategyName.MA20_REBOUND: 0.50,
        StrategyName.TREND_RECOVERY: 0.50,
    }

    @staticmethod
    def _round_price(value: float | None) -> float | None:
        if value is None:
            return None
        # KRX 종목마다 호가단위가 다르므로 v0.10에서는 임의 호가단위 보정을 하지 않습니다.
        return round(float(value), 2)

    @staticmethod
    def _valid_below(entry: float, value: float | None) -> float | None:
        if value is None:
            return None
        value_f = float(value)
        return value_f if 0 < value_f < entry else None

    @staticmethod
    def _valid_above(entry: float, value: float | None) -> float | None:
        if value is None:
            return None
        value_f = float(value)
        return value_f if value_f > entry else None

    def _anchor(
        self,
        data: StrategyInput,
        strategy: StrategyName,
        technical: dict[str, Any],
    ) -> tuple[float | None, str | None]:
        entry = float(data.current_price)
        support = self._valid_below(entry, data.support_price)
        ma20 = self._valid_below(entry, data.ma20)
        low20 = self._valid_below(entry, technical.get("low20"))
        high20 = self._valid_below(entry, technical.get("high20"))

        if strategy in {StrategyName.PULLBACK, StrategyName.SUPPORT_BOUNCE, StrategyName.RANGE_TRADING}:
            if support is not None:
                return support, "주요 지지 후보"
            if ma20 is not None:
                return ma20, "20일 이동평균선"

        if strategy == StrategyName.MA20_REBOUND:
            if ma20 is not None:
                return ma20, "20일 이동평균선"
            if support is not None:
                return support, "주요 지지 후보"

        if strategy in {StrategyName.BREAKOUT, StrategyName.VOLATILITY_SQUEEZE}:
            # 돌파 뒤에는 이전 20일 고점이 지지로 바뀌는지 보는 것이 중요합니다.
            if high20 is not None:
                return high20, "이전 20일 고점(돌파 기준선)"
            if ma20 is not None:
                return ma20, "20일 이동평균선"
            if support is not None:
                return support, "주요 지지 후보"

        if strategy == StrategyName.OVERSOLD_BOUNCE:
            candidates = [(support, "주요 지지 후보"), (low20, "최근 20일 저점")]
            valid = [(value, label) for value, label in candidates if value is not None]
            if valid:
                return max(valid, key=lambda item: item[0])

        if strategy in {
            StrategyName.TREND_FOLLOWING,
            StrategyName.MOMENTUM_CONTINUATION,
            StrategyName.TREND_RECOVERY,
        }:
            candidates = [(support, "주요 지지 후보"), (ma20, "20일 이동평균선")]
            valid = [(value, label) for value, label in candidates if value is not None]
            if valid:
                return max(valid, key=lambda item: item[0])

        if support is not None:
            return support, "주요 지지 후보"
        if ma20 is not None:
            return ma20, "20일 이동평균선"
        if low20 is not None:
            return low20, "최근 20일 저점"
        return None, None

    @staticmethod
    def _structure_rating(rr1: float | None, rr2: float | None, risk_pct: float | None) -> str:
        if risk_pct is None:
            return "판단 불가"
        if risk_pct >= 12:
            return "불리함"
        if rr2 is not None and rr2 >= 2.0 and rr1 is not None and rr1 >= 1.0:
            return "양호"
        if rr2 is not None and rr2 >= 1.5:
            return "주의"
        return "불리함"

    def build_plan(
        self,
        *,
        data: StrategyInput,
        strategy: StrategyName,
        technical: dict[str, Any],
        risk_gate_active: bool,
        risk_gate_reasons: list[str],
        basis: str,
    ) -> RiskPlan:
        entry = float(data.current_price)
        atr_pct = data.atr_pct
        atr_value = entry * float(atr_pct) / 100 if atr_pct is not None and atr_pct > 0 else None
        anchor, anchor_label = self._anchor(data, strategy, technical)

        assumptions = [
            "기준가격은 실제 주문가격이 아니라 분석용 참고가격입니다.",
            "손절·목표 가격은 자동 주문으로 전송되지 않습니다.",
        ]
        warnings = list(risk_gate_reasons)

        if atr_value is None or anchor is None:
            return RiskPlan(
                strategy=strategy.value,
                status=RiskPlanStatus.UNAVAILABLE,
                reference_only=True,
                basis=basis,
                entry_price=entry,
                structural_anchor=anchor,
                structural_anchor_label=anchor_label,
                invalidation_price=None,
                stop_zone_low=None,
                stop_zone_high=None,
                target1_price=None,
                target1_basis=None,
                target2_price=None,
                target2_basis=None,
                risk_pct=None,
                reward1_pct=None,
                reward2_pct=None,
                rr1=None,
                rr2=None,
                structure_rating="판단 불가",
                summary="ATR 또는 구조적 지지 기준이 부족해 손익 구조를 억지로 계산하지 않았습니다.",
                reasons=[],
                warnings=warnings,
                assumptions=assumptions,
            )

        buffer_factor = self.BUFFER_BY_STRATEGY.get(strategy, 0.5)
        invalidation = anchor - atr_value * buffer_factor
        if invalidation <= 0 or invalidation >= entry:
            return RiskPlan(
                strategy=strategy.value,
                status=RiskPlanStatus.UNAVAILABLE,
                reference_only=True,
                basis=basis,
                entry_price=entry,
                structural_anchor=anchor,
                structural_anchor_label=anchor_label,
                invalidation_price=None,
                stop_zone_low=None,
                stop_zone_high=None,
                target1_price=None,
                target1_basis=None,
                target2_price=None,
                target2_basis=None,
                risk_pct=None,
                reward1_pct=None,
                reward2_pct=None,
                rr1=None,
                rr2=None,
                structure_rating="판단 불가",
                summary="현재 가격과 구조적 지지 기준의 관계가 비정상적이라 리스크 가격을 계산하지 않았습니다.",
                reasons=[],
                warnings=warnings,
                assumptions=assumptions,
            )

        risk_amount = entry - invalidation
        risk_pct = risk_amount / entry * 100
        stop_zone_low = invalidation - atr_value * 0.15
        stop_zone_high = invalidation + atr_value * 0.15

        resistance = self._valid_above(entry, data.resistance_price)
        high20 = self._valid_above(entry, technical.get("high20"))
        structural_targets: list[tuple[float, str, str]] = []
        if resistance is not None:
            structural_targets.append((resistance, "최근 저항 후보", "RESISTANCE"))
        if high20 is not None:
            structural_targets.append((high20, "최근 20일 고점", "HIGH20"))

        target1_decision = select_target1(
            entry=entry,
            risk_amount=risk_amount,
            structural_candidates=structural_targets,
        )
        target1 = target1_decision.target1_price
        target1_basis = target1_decision.target1_basis

        # Target1만 현실성 상한을 적용합니다. Target2는 기존 Production 정의를
        # 보존하기 위해 cap 전 legacy Target1을 기준으로 계산합니다.
        legacy_target1 = target1_decision.legacy_target1_price
        target2_r = entry + risk_amount * 2.0
        target2 = max(target2_r, legacy_target1 + risk_amount * 0.5)
        target2_basis = "2R 이상 확장 시나리오"

        reward1 = target1 - entry
        reward2 = target2 - entry
        reward1_pct = reward1 / entry * 100
        reward2_pct = reward2 / entry * 100
        rr1 = reward1 / risk_amount if risk_amount > 0 else None
        rr2 = reward2 / risk_amount if risk_amount > 0 else None
        rating = self._structure_rating(rr1, rr2, risk_pct)

        reasons = [
            f"{anchor_label} {anchor:,.0f}원을 전략 무효화의 구조적 기준으로 사용했습니다.",
            f"ATR({atr_pct:.2f}%)를 이용해 단순 지지선 바로 아래가 아닌 변동성 여유를 반영했습니다.",
            f"1차 목표는 {target1_basis}을 기준으로 잡았습니다.",
            "2차 목표는 기존 Production 확장 시나리오를 그대로 유지합니다.",
        ]
        if target1_decision.cap_applied and target1_decision.structural_target1_price is not None:
            reasons.append(
                f"구조 목표 {target1_decision.structural_target1_price:,.0f}원이 1.5R보다 멀어 "
                "1차 목표에만 현실성 상한을 적용했습니다."
            )

        if risk_pct >= 12:
            warnings.append("현재 가격에서 무효화 기준까지 거리가 12% 이상으로 넓어 신규 진입 리스크가 큽니다.")
        if rr1 is not None and rr1 < 1.0:
            warnings.append("가까운 1차 목표 기준 Risk:Reward가 1:1 미만입니다.")
        if data.extreme_move:
            warnings.append("급격한 가격 변동 상태이므로 이 가격 계획은 참고 시나리오로만 보세요.")
        if data.data_stale:
            warnings.append("확정 EOD 이후 가격 괴리가 커 기존 구조의 신뢰도가 낮아졌습니다.")

        reference_only = bool(risk_gate_active or data.extreme_move or data.data_stale)
        if reference_only:
            status = RiskPlanStatus.HOLD
            summary = "Risk Gate 또는 데이터 괴리가 있어 신규 진입 계획으로 사용하지 않고 참고 구조로만 표시합니다."
        elif rating == "불리함":
            status = RiskPlanStatus.CAUTION
            summary = "현재 가격에서는 위험 대비 목표 여유가 부족하거나 손절 폭이 넓습니다."
        elif rating == "주의":
            status = RiskPlanStatus.CAUTION
            summary = "2차 목표까지는 손익 구조가 열려 있지만 가까운 저항과 손절 폭을 함께 확인해야 합니다."
        else:
            status = RiskPlanStatus.READY
            summary = "현재 전략 기준으로 손절 폭과 목표 여유가 비교 가능한 구조입니다."

        return RiskPlan(
            strategy=strategy.value,
            status=status,
            reference_only=reference_only,
            basis=basis,
            entry_price=self._round_price(entry) or entry,
            structural_anchor=self._round_price(anchor),
            structural_anchor_label=anchor_label,
            invalidation_price=self._round_price(invalidation),
            stop_zone_low=self._round_price(stop_zone_low),
            stop_zone_high=self._round_price(stop_zone_high),
            target1_price=self._round_price(target1),
            target1_basis=target1_basis,
            target2_price=self._round_price(target2),
            target2_basis=target2_basis,
            risk_pct=round(risk_pct, 2),
            reward1_pct=round(reward1_pct, 2),
            reward2_pct=round(reward2_pct, 2),
            rr1=round(rr1, 2) if rr1 is not None else None,
            rr2=round(rr2, 2) if rr2 is not None else None,
            structure_rating=rating,
            summary=summary,
            reasons=reasons,
            warnings=warnings,
            assumptions=assumptions,
            structural_target1_price=self._round_price(target1_decision.structural_target1_price),
            structural_target1_basis=target1_decision.structural_target1_basis,
            target1_cap_price=self._round_price(target1_decision.cap_price),
            target1_cap_applied=target1_decision.cap_applied,
            target1_fallback_used=target1_decision.fallback_used,
        )
