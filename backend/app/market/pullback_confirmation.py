from __future__ import annotations

from statistics import fmean
from typing import Any

from app.core.auto_check import build_auto_check_summary


class PullbackConfirmationAnalyzer:
    """Turn vague 'check pullback support' advice into explicit program checks.

    The analyzer never emits an order. It classifies the current pullback/support state
    using confirmed KRX EOD data and, when supplied, the user's temporary intraday inputs.
    """

    @staticmethod
    def _rsi14(closes: list[float]) -> float | None:
        if len(closes) < 15:
            return None
        gains: list[float] = []
        losses: list[float] = []
        for prev, current in zip(closes[-15:-1], closes[-14:], strict=False):
            diff = current - prev
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))
        avg_gain = fmean(gains)
        avg_loss = fmean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    @staticmethod
    def _check(
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

    @staticmethod
    def _pct_distance(price: float, level: float | None) -> float | None:
        if level is None or price <= 0:
            return None
        return (price - level) / price * 100

    @classmethod
    def analyze(
        cls,
        *,
        history: list[dict[str, Any]],
        technical: dict[str, Any],
        current_price: float,
        current_ma20: float | None,
        current_rsi14: float | None,
        current_volume_ratio: float | None,
        source: str,
        position_mode: str,
        reference_low: float | None = None,
        reference_high: float | None = None,
        reference_volume: float | None = None,
    ) -> dict[str, Any]:
        valid = [row for row in history if row.get("close") is not None]
        latest = valid[-1] if valid else {}
        closes = [float(row["close"]) for row in valid]
        is_manual = source == "USER_INPUT"
        # For confirmed EOD, compare today's RSI with the previous trading day's RSI.
        # For intraday preview, compare the estimated current RSI with the latest confirmed EOD RSI.
        rsi_reference_closes = closes if is_manual else closes[:-1]
        previous_rsi = cls._rsi14(rsi_reference_closes) if len(rsi_reference_closes) >= 15 else None

        support = technical.get("support")
        ma20 = current_ma20
        distance_to_high = technical.get("distance_to_20d_high_pct")
        ma20_slope = technical.get("ma20_slope_pct")
        higher_low = technical.get("higher_low")

        anchors: list[tuple[str, float]] = []
        if ma20 is not None and ma20 > 0:
            anchors.append(("20일선", float(ma20)))
        if support is not None and support > 0:
            anchors.append(("주요 지지선", float(support)))

        anchor_name: str | None = None
        anchor_price: float | None = None
        anchor_distance: float | None = None
        if anchors:
            anchor_name, anchor_price = min(
                anchors,
                key=lambda item: abs((current_price - item[1]) / current_price),
            )
            anchor_distance = cls._pct_distance(current_price, anchor_price)

        current_low = reference_low if is_manual else latest.get("low")
        current_high = reference_high if is_manual else latest.get("high")
        current_open = None if is_manual else latest.get("open")
        current_close = current_price
        price_source = "USER_INPUT" if is_manual else "KRX_EOD"

        checks: list[dict[str, str]] = []

        # 1) Existing uptrend / structure
        if ma20_slope is None and higher_low is None:
            trend_status = "UNKNOWN"
            trend_explanation = "20일선 기울기와 최근 저점 구조를 충분히 계산할 수 없습니다."
        elif (ma20_slope is not None and ma20_slope > 0) and higher_low is not False:
            trend_status = "PASS"
            trend_explanation = "20일선이 상승 중이고 최근 저점 구조도 크게 훼손되지 않았습니다."
        elif (ma20_slope is not None and ma20_slope <= 0) and higher_low is False:
            trend_status = "FAIL"
            trend_explanation = "20일선 기울기와 최근 저점 구조가 모두 약해 눌림목의 전제인 상승 추세가 부족합니다."
        else:
            trend_status = "WARN"
            trend_explanation = "상승 추세 조건이 일부만 유지됩니다."
        checks.append(cls._check(
            "uptrend",
            "기존 상승 추세",
            trend_status,
            f"20일선 기울기 {ma20_slope:+.2f}%" if ma20_slope is not None else "기울기 데이터 부족",
            trend_explanation,
            "KRX_EOD",
        ))

        # 2) Actual pullback from the recent high
        if distance_to_high is None:
            pullback_status = "UNKNOWN"
            pullback_explanation = "최근 20일 고점과의 거리를 계산할 수 없습니다."
        elif 2 <= float(distance_to_high) <= 12:
            pullback_status = "PASS"
            pullback_explanation = "최근 고점에서 적당한 폭의 조정이 나와 눌림 구간으로 볼 수 있습니다."
        elif 0 <= float(distance_to_high) < 2:
            pullback_status = "WARN"
            pullback_explanation = "최근 고점과 너무 가까워 아직 뚜렷한 눌림이라고 보기 어렵습니다."
        else:
            pullback_status = "WARN"
            pullback_explanation = "최근 고점과 거리가 커 정상적인 단기 눌림인지 추가 구조 확인이 필요합니다."
        checks.append(cls._check(
            "pullback_depth",
            "최근 고점에서 조정",
            pullback_status,
            "-" if distance_to_high is None else f"고점 대비 -{float(distance_to_high):.2f}%",
            pullback_explanation,
            "KRX_EOD",
        ))

        # 3) Near a support area
        if anchor_price is None or anchor_distance is None:
            near_status = "UNKNOWN"
            near_explanation = "20일선 또는 주요 지지 가격을 계산할 수 없습니다."
            near_value = "지지 기준 없음"
        else:
            absolute_distance = abs(anchor_distance)
            if absolute_distance <= 2.5:
                near_status = "PASS"
                near_explanation = f"현재가가 {anchor_name}과 가까워 실제 지지 여부를 판정할 수 있는 구간입니다."
            elif absolute_distance <= 5:
                near_status = "WARN"
                near_explanation = f"{anchor_name}에 접근 중이지만 아직 바로 지지 테스트 구간은 아닙니다."
            else:
                near_status = "WARN"
                near_explanation = f"현재가는 {anchor_name}에서 아직 멀어 지지 확인 단계가 아닙니다."
            near_value = f"{anchor_name} {anchor_price:,.0f}원 · 현재와 {anchor_distance:+.2f}%"
        checks.append(cls._check(
            "near_support",
            "지지구간 접근",
            near_status,
            near_value,
            near_explanation,
            price_source,
        ))

        # 4) Did price actually hold / recover the support?
        support_hold_status = "UNKNOWN"
        support_hold_explanation = "장중 저가가 없어 지지선을 실제로 시험했는지는 확정할 수 없습니다."
        support_hold_value = "저가 미입력"
        if anchor_price is not None:
            fail_threshold = anchor_price * 0.99
            if current_price < fail_threshold:
                support_hold_status = "FAIL"
                support_hold_value = f"현재 {current_price:,.0f}원 / {anchor_name} {anchor_price:,.0f}원"
                support_hold_explanation = "현재 가격이 지지 기준을 약 1% 이상 하향 이탈해 지지 실패 쪽으로 판단합니다."
            elif current_low is not None:
                low_f = float(current_low)
                support_hold_value = f"저가 {low_f:,.0f}원 / {anchor_name} {anchor_price:,.0f}원"
                if low_f <= anchor_price * 1.02 and current_price >= anchor_price:
                    support_hold_status = "PASS"
                    support_hold_explanation = "가격이 지지구간을 시험한 뒤 현재/종가가 다시 지지 기준 위에 있어 실제 방어 흔적이 확인됩니다."
                elif low_f < fail_threshold and current_price < anchor_price:
                    support_hold_status = "FAIL"
                    support_hold_explanation = "저가가 지지선을 크게 깨고 현재/종가도 회복하지 못해 지지 실패로 봅니다."
                elif current_price >= anchor_price:
                    support_hold_status = "WARN"
                    support_hold_explanation = "지지 기준 위에는 있지만 저가가 실제 지지구간을 충분히 시험했다고 보기 어렵습니다."
                else:
                    support_hold_status = "WARN"
                    support_hold_explanation = "지지 기준 근처에서 움직이고 있어 종가 회복 여부를 더 봐야 합니다."
            elif current_price >= anchor_price:
                support_hold_status = "WARN"
                support_hold_value = f"현재 {current_price:,.0f}원 / {anchor_name} {anchor_price:,.0f}원"
                support_hold_explanation = "현재가는 지지 기준 위지만 오늘 저가가 없어 실제 지지 테스트 여부는 아직 미확정입니다."
        checks.append(cls._check(
            "support_hold",
            "실제 지지 유지",
            support_hold_status,
            support_hold_value,
            support_hold_explanation,
            "USER_INPUT" if is_manual and reference_low is not None else "KRX_EOD" if not is_manual else "USER_INPUT",
        ))

        # 5) Price rebound. The threshold is derived from observed prices only.
        # Confirmed EOD: close must finish above the open and not below the support anchor.
        # Intraday preview: when today's low is supplied, price must recover from the tested
        # support area back above the anchor. We do not invent an extra percentage target.
        rebound_confirmation_price: float | None = None
        if current_open is None:
            if anchor_price is not None and reference_low is not None:
                low_f = float(reference_low)
                rebound_confirmation_price = float(anchor_price)
                candle_value = f"저가 {low_f:,.0f}원 → 현재 {current_close:,.0f}원"
                if low_f <= anchor_price * 1.02 and current_close >= anchor_price and current_close > low_f:
                    candle_status = "PASS"
                    candle_explanation = "오늘 저가가 지지구간을 시험한 뒤 현재가가 지지 기준 위로 회복해 가격 반등 흔적이 확인됩니다."
                else:
                    candle_status = "WARN"
                    candle_explanation = "오늘 저가와 현재가를 보면 지지구간 회복이 아직 충분히 확인되지 않았습니다."
            else:
                candle_status = "UNKNOWN"
                candle_value = "오늘 저가 미입력" if reference_low is None else "지지 기준 없음"
                candle_explanation = "장중 Preview에서는 오늘 저가와 지지 기준이 있어야 가격 반등을 자동 판정할 수 있습니다."
        else:
            open_f = float(current_open)
            rebound_confirmation_price = max(open_f, float(anchor_price)) if anchor_price is not None else open_f
            candle_value = f"시가 {open_f:,.0f}원 → 종가 {current_close:,.0f}원"
            if current_close > open_f and (anchor_price is None or current_close >= anchor_price):
                candle_status = "PASS"
                candle_explanation = "종가가 시가보다 높고 지지 기준 위에서 마감해 가격 반등 신호가 확인됩니다."
            elif current_close < open_f:
                candle_status = "WARN"
                candle_explanation = "종가가 시가보다 낮아 당일 가격 반등은 아직 확인되지 않았습니다."
            else:
                candle_status = "WARN"
                candle_explanation = "가격 반등 신호가 뚜렷하지 않습니다."
        checks.append(cls._check(
            "rebound_candle",
            "가격 반등 신호",
            candle_status,
            candle_value,
            candle_explanation,
            "KRX_EOD" if not is_manual else "USER_INPUT",
        ))

        # 6) RSI turn
        if current_rsi14 is None:
            rsi_status = "UNKNOWN"
            rsi_value = "RSI 데이터 부족"
            rsi_explanation = "RSI 반등 여부를 계산할 수 없습니다."
        elif previous_rsi is None:
            rsi_status = "WARN"
            rsi_value = f"RSI {float(current_rsi14):.2f}"
            rsi_explanation = "비교할 이전 RSI가 부족해 회복 방향을 확정하지 않습니다."
        else:
            current_rsi = float(current_rsi14)
            rsi_value = f"{previous_rsi:.2f} → {current_rsi:.2f}"
            if current_rsi >= 40 and current_rsi >= previous_rsi + 1.0:
                rsi_status = "PASS"
                rsi_explanation = (
                    "장중 예상 RSI가 최신 확정 RSI보다 1p 이상 회복했습니다."
                    if is_manual
                    else "RSI가 전일보다 1p 이상 회복되어 반등 힘이 생기는 흐름입니다."
                )
            elif current_rsi >= 40:
                rsi_status = "WARN"
                rsi_explanation = "RSI는 적정 범위지만 이전 기준보다 1p 이상 회복하는 조건은 아직 충족하지 못했습니다."
            else:
                rsi_status = "WARN"
                rsi_explanation = "RSI가 40 아래라 아직 반등 힘의 회복을 확인하기 어렵습니다."
        checks.append(cls._check(
            "rsi_turn",
            "RSI 반등",
            rsi_status,
            rsi_value,
            rsi_explanation,
            price_source,
        ))

        # 7) Volume recovery
        if current_volume_ratio is None:
            volume_status = "UNKNOWN"
            volume_value = "거래량 데이터 부족"
            volume_explanation = "반등 시 거래량 회복 여부를 계산할 수 없습니다."
        else:
            ratio = float(current_volume_ratio)
            volume_value = f"20일 평균의 {ratio:.2f}배"
            if ratio >= 1.0:
                volume_status = "PASS"
                volume_explanation = "평균 이상의 거래가 들어와 반등 확인에 힘을 보탭니다."
            elif ratio >= 0.7:
                volume_status = "WARN"
                volume_explanation = "거래량이 크게 부족하진 않지만 강한 반등 확인 수준은 아닙니다."
            else:
                volume_status = "WARN"
                volume_explanation = "거래량이 평균보다 많이 적어 반등의 힘을 확인하기 어렵습니다."
        checks.append(cls._check(
            "volume_recovery",
            "반등 거래량",
            volume_status,
            volume_value,
            volume_explanation,
            "USER_INPUT" if is_manual and reference_volume is not None else "KRX_EOD",
        ))

        statuses = {item["key"]: item["status"] for item in checks}
        near_support = statuses["near_support"] == "PASS"
        support_failed = statuses["support_hold"] == "FAIL"
        support_held = statuses["support_hold"] == "PASS"
        rebound_signal = statuses["rebound_candle"] == "PASS" or statuses["rsi_turn"] == "PASS"
        volume_ok = statuses["volume_recovery"] in {"PASS", "UNKNOWN"}
        trend_ok = statuses["uptrend"] == "PASS"
        pullback_ok = statuses["pullback_depth"] == "PASS"

        if support_failed:
            state = "SUPPORT_FAILED"
            label = "지지 실패"
            headline = "눌림목 지지 기준이 깨진 상태입니다."
            summary = "가격이 핵심 지지 기준 아래로 밀려 기존 눌림목 시나리오를 그대로 유지하기 어렵습니다."
        elif trend_status == "FAIL":
            state = "NOT_PULLBACK"
            label = "눌림목 아님"
            headline = "현재는 정상적인 상승 추세 속 눌림목으로 보기 어렵습니다."
            summary = "눌림목은 원래 상승 추세가 살아 있어야 하는데 현재는 추세 기반이 약합니다."
        elif near_support and support_held and rebound_signal and volume_ok:
            state = "REBOUND_CONFIRMED"
            label = "반등 확인"
            headline = "프로그램 자동 점검상 지지 후 반등 신호가 확인됐습니다."
            summary = "지지구간을 실제로 시험하고 회복한 흔적과 반등 신호가 함께 확인되어 눌림목 조건이 이전보다 좋아졌습니다."
        elif near_support and support_held:
            state = "REBOUND_WAITING"
            label = "반등 신호 대기"
            headline = "지지 유지까지는 확인됐지만 반등 신호가 아직 충분하지 않습니다."
            summary = "가격은 핵심 지지 기준을 지켰습니다. 이제 RSI·가격 반등·거래량 같은 회복 신호가 더 확인되는지 앱이 자동으로 봅니다."
        elif near_support and statuses["support_hold"] in {"WARN", "UNKNOWN"}:
            state = "SUPPORT_TESTING"
            label = "지지 테스트 중"
            headline = "지지구간에는 도착했지만 실제 지지 유지가 아직 확정되지 않았습니다."
            summary = "가격 위치는 눌림목 확인 구간에 들어왔지만 실제 저가 방어와 반등 신호 중 일부 확인이 더 필요합니다."
        elif anchor_distance is not None and abs(anchor_distance) <= 5:
            state = "SUPPORT_APPROACH"
            label = "지지구간 접근"
            headline = "주가가 주요 지지구간으로 접근하고 있습니다."
            summary = "아직 실제 지지 테스트는 아니므로 앱이 지지 여부를 확정하지 않습니다."
        elif pullback_ok and trend_status in {"PASS", "WARN"}:
            state = "PULLBACK_IN_PROGRESS"
            label = "눌림 진행 중"
            headline = "상승 흐름 안에서 조정이 진행 중입니다."
            summary = "조정 자체는 눌림 범위지만 지지구간까지의 거리와 반등 신호가 아직 충분하지 않습니다."
        else:
            state = "NOT_PULLBACK"
            label = "눌림목 아님"
            headline = "현재 위치는 눌림목 진입 판단 구간으로 보기 어렵습니다."
            summary = "최근 고점과 지지구간의 위치를 함께 보면 아직 눌림목 조건이 뚜렷하지 않습니다."

        passed = sum(item["status"] == "PASS" for item in checks)
        failed = sum(item["status"] == "FAIL" for item in checks)
        known = sum(item["status"] != "UNKNOWN" for item in checks)

        if state == "REBOUND_CONFIRMED":
            new_entry = "눌림목 후보 우선 검토"
            new_summary = "자동 확인 조건이 좋아졌습니다. Risk Gate와 손익 구조까지 문제없을 때 눌림목 전략을 우선 비교할 수 있습니다."
            holding = "보유 근거 개선"
            holding_summary = "지지 후 반등 흔적이 확인되어 정상 조정 후 회복 시나리오에 힘이 실립니다."
        elif state == "SUPPORT_FAILED":
            new_entry = "눌림목 신규 판단 보류"
            new_summary = "지지 실패 상태에서 떨어지는 가격을 눌림목으로 간주하지 않습니다."
            holding = "보유 논리 재평가"
            holding_summary = "기존 지지 기준이 깨져 눌림목·지지반등 시나리오를 다시 평가해야 합니다."
        elif state == "REBOUND_WAITING":
            new_entry = "반등 신호 대기"
            new_summary = "지지 유지까지는 앱이 확인했습니다. RSI·가격 반등·거래량 중 남은 회복 조건을 다음 데이터에서 자동 판정합니다."
            holding = "지지 유지 · 반등 확인 대기"
            holding_summary = "핵심 지지는 유지됐지만 반등 완료로 보기에는 신호가 부족합니다. 남은 회복 조건을 자동 점검합니다."
        elif state == "SUPPORT_TESTING":
            new_entry = "신규 진입 대기"
            new_summary = "지지구간에는 도착했지만 실제 방어가 아직 확정되지 않았습니다. 앱이 저가 방어와 반등 신호를 자동으로 확인합니다."
            holding = "지지 테스트 관찰"
            holding_summary = "핵심 지지구간에서 버티는지 자동 확인 중입니다. 아직 지지 실패로 판정된 상태는 아닙니다."
        elif state == "SUPPORT_APPROACH":
            new_entry = "지지구간 도달 대기"
            new_summary = "주가가 지지 후보에 접근 중입니다. 실제 지지 테스트 구간에 들어오면 앱이 방어 여부를 자동 판정합니다."
            holding = "지지구간 접근 관찰"
            holding_summary = "지지 후보에 가까워지고 있어 다음 가격 위치를 자동 확인합니다."
        elif state == "PULLBACK_IN_PROGRESS":
            new_entry = "눌림 조건 형성 대기"
            new_summary = "조정은 진행 중이지만 아직 핵심 지지구간이 아닙니다. 지지구간 접근 여부를 앱이 자동으로 추적합니다."
            holding = "정상 조정 여부 관찰"
            holding_summary = "상승 흐름 속 조정으로 볼 여지는 있지만 아직 지지 확인 단계는 아닙니다."
        else:
            new_entry = "다른 전략 우선"
            new_summary = "현재는 눌림목 조건이 뚜렷하지 않아 다른 전략 결과를 우선 비교합니다."
            holding = "눌림목 근거로 사용하지 않음"
            holding_summary = "현재 상태를 눌림목이라는 이유로 보유 근거에 추가하지 않습니다."

        user_response = (
            {"perspective": "보유 관리", "action": holding, "summary": holding_summary}
            if position_mode == "HOLDING"
            else {"perspective": "신규 진입", "action": new_entry, "summary": new_summary}
        )

        waiting_for: list[str] = []
        if statuses["support_hold"] in {"WARN", "UNKNOWN"}:
            waiting_for.append("지지구간을 실제로 시험한 뒤 기준 위에서 회복하는지")
        if statuses["rebound_candle"] != "PASS":
            waiting_for.append("가격 반등 신호")
        if statuses["rsi_turn"] != "PASS":
            waiting_for.append("RSI 회복")
        if statuses["volume_recovery"] != "PASS":
            waiting_for.append("반등 거래량 회복")
        if statuses["uptrend"] != "PASS":
            waiting_for.append("20일선 상승·저점 구조 회복")

        input_hints: list[dict[str, str]] = []
        if is_manual and reference_low is None:
            input_hints.append({
                "field": "reference_low",
                "label": "오늘 저가",
                "reason": "장중에 지지선을 실제로 시험했는지 더 정확하게 판정할 수 있습니다.",
            })
        if is_manual and reference_volume is None:
            input_hints.append({
                "field": "reference_volume",
                "label": "현재 누적 거래량",
                "reason": "장중 반등에 거래량이 실리는지 더 정확하게 판정할 수 있습니다.",
            })

        basis = "INTRADAY_PREVIEW" if is_manual else "CONFIRMED_EOD"
        next_data_note = (
            "장 마감 후 다음 KRX 확정 EOD가 들어오면 가격 반등·RSI·거래량을 다시 자동 판정합니다."
            if is_manual
            else "다음 KRX 확정 거래일 데이터가 들어오면 같은 조건을 자동으로 다시 판정합니다."
        )
        auto_check = build_auto_check_summary(
            checks=checks,
            basis=basis,
            input_hints=input_hints,
            next_data_note=next_data_note,
        )

        waiting_states = {"PULLBACK_IN_PROGRESS", "SUPPORT_APPROACH", "SUPPORT_TESTING", "REBOUND_WAITING"}
        if state == "REBOUND_CONFIRMED":
            timing_status = "READY"
        elif state == "SUPPORT_FAILED":
            timing_status = "INVALIDATED"
        elif state == "NOT_PULLBACK":
            timing_status = "NOT_APPLICABLE"
        else:
            timing_status = "WAIT"

        if position_mode == "HOLDING":
            if state == "SUPPORT_FAILED":
                timing_action = "보유 논리 재평가"
                timing_next = "무효화 기준과 다른 전략 근거를 다시 비교"
                timing_avoid = "지지 실패를 무시한 추가매수"
            elif state == "REBOUND_CONFIRMED":
                timing_action = "보유 관찰"
                timing_next = "Risk Engine 기준과 함께 보유 근거 유지 여부 검토"
                timing_avoid = "반등 확인만으로 비중 확대 확정"
            elif state in waiting_states:
                timing_action = "보유 관찰"
                timing_next = "반등 확인 시 보유 근거 개선 여부 검토"
                timing_avoid = "반등 미확인 상태의 추가매수"
            else:
                timing_action = "현재 전략 근거 재검토"
                timing_next = "다른 전략 후보와 함께 자동 재평가"
                timing_avoid = "눌림목 근거만으로 보유 판단 강화"
        else:
            if state == "SUPPORT_FAILED":
                timing_action = "신규 진입 보류"
                timing_next = "지지 구조가 새로 형성되거나 다른 전략 조건이 우세해질 때 재검토"
                timing_avoid = "깨진 지지선에서의 추격 진입"
            elif state == "REBOUND_CONFIRMED":
                timing_action = "신규 후보 검토 가능"
                timing_next = "Risk Gate와 무효화·손익 구조를 함께 비교"
                timing_avoid = "반등 확인 하나만으로 즉시 진입 확정"
            elif state in waiting_states:
                timing_action = "신규 추격 대기"
                timing_next = "반등 확인 시 후보 검토"
                timing_avoid = "반등 확인 전 추격 진입"
            else:
                timing_action = "다른 전략 우선"
                timing_next = "눌림 조건이 형성되면 자동 재평가"
                timing_avoid = "현재 위치를 억지로 눌림목으로 해석"

        priority_order = {
            "support_hold": 0,
            "rebound_candle": 1,
            "rsi_turn": 2,
            "volume_recovery": 3,
            "near_support": 4,
            "pullback_depth": 5,
            "uptrend": 6,
        }
        unresolved = list(auto_check.get("failed_checks") or []) + list(auto_check.get("pending_checks") or [])
        unresolved.sort(key=lambda item: priority_order.get(str(item.get("key") or ""), 99))
        most_missing = [str(item.get("label") or "") for item in unresolved if item.get("label")][:3]

        price_rule = (
            "종가가 시가보다 높고 지지 기준 이상에서 마감"
            if not is_manual
            else "오늘 저가가 지지구간을 시험한 뒤 현재가가 지지 기준 위로 회복"
        )
        entry_timing = {
            "version": "0.18.2",
            "status": timing_status,
            "state": state,
            "label": label,
            "headline": headline,
            "summary": summary,
            "basis": basis,
            "basis_label": "장중 Preview" if is_manual else "KRX 확정 EOD",
            "progress": {
                "passed": auto_check["passed"],
                "failed": auto_check["failed"],
                "pending": auto_check["pending"],
                "total": auto_check["total"],
                "percent": auto_check["progress_pct"],
                "label": auto_check["progress_label"],
            },
            "confirmed_checks": auto_check.get("passed_checks") or [],
            "failed_checks": auto_check.get("failed_checks") or [],
            "pending_checks": auto_check.get("pending_checks") or [],
            "most_missing": most_missing,
            "action": {
                "perspective": "보유 관리" if position_mode == "HOLDING" else "신규 진입",
                "primary": timing_action,
                "next": timing_next,
                "avoid": timing_avoid,
                "recheck_note": next_data_note,
            },
            "levels": {
                "current_price": current_price,
                "ma20": None if ma20 is None else float(ma20),
                "support": None if support is None else float(support),
                "anchor": None if anchor_price is None else float(anchor_price),
                "rebound_confirmation": None if rebound_confirmation_price is None else float(rebound_confirmation_price),
            },
            "rules": {
                "price_rebound": price_rule,
                "rsi_recovery": "현재 RSI가 40 이상이면서 직전 확정 RSI보다 1p 이상 회복",
                "volume_recovery": "현재 거래량비가 최근 20일 평균 거래량의 1.0배 이상",
            },
            "policy": "조건 확인 개수는 상승확률이 아니며 계산 가능한 가격만 표시합니다.",
        }

        return {
            "available": True,
            "version": "0.18.2",
            "state": state,
            "label": label,
            "headline": headline,
            "summary": summary,
            "basis": basis,
            "basis_label": "장중 Preview" if is_manual else "KRX 확정 EOD",
            "confirmed": not is_manual and state in {"REBOUND_CONFIRMED", "SUPPORT_FAILED"},
            "anchor": {
                "name": anchor_name,
                "price": anchor_price,
                "distance_pct": None if anchor_distance is None else round(anchor_distance, 3),
            },
            "checks": checks,
            "passed": auto_check["passed"],
            "failed": auto_check["failed"],
            "known_checks": auto_check["known"],
            "total_checks": auto_check["total"],
            "auto_check": auto_check,
            "entry_timing": entry_timing,
            "user_response": user_response,
            "new_entry": {"action": new_entry, "summary": new_summary},
            "holding": {"action": holding, "summary": holding_summary},
            "waiting_for": list(dict.fromkeys(waiting_for)),
            "policy": (
                "앱이 계산 가능한 지지·반등 조건은 자동 판정합니다. "
                "장중 현재가만 입력한 경우 오늘 저가·시가·거래량이 없으므로 일부 항목은 미확정으로 남깁니다."
            ),
        }
