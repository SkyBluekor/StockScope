from __future__ import annotations

from statistics import fmean
from typing import Any


class TechnicalAnalyzer:
    @staticmethod
    def _values(rows: list[dict[str, Any]], key: str) -> list[float]:
        return [float(row[key]) for row in rows if row.get(key) is not None]

    @staticmethod
    def _sma(values: list[float], period: int) -> float | None:
        if len(values) < period:
            return None
        return fmean(values[-period:])

    @staticmethod
    def _rsi14(closes: list[float]) -> float | None:
        if len(closes) < 15:
            return None
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        recent = deltas[-14:]
        gains = [max(delta, 0.0) for delta in recent]
        losses = [max(-delta, 0.0) for delta in recent]
        avg_gain = fmean(gains)
        avg_loss = fmean(losses)
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr14(rows: list[dict[str, Any]]) -> float | None:
        if len(rows) < 15:
            return None
        trs: list[float] = []
        for index in range(1, len(rows)):
            high = rows[index].get("high")
            low = rows[index].get("low")
            prev_close = rows[index - 1].get("close")
            if high is None or low is None or prev_close is None:
                continue
            high_f, low_f, prev_f = float(high), float(low), float(prev_close)
            trs.append(max(high_f - low_f, abs(high_f - prev_f), abs(low_f - prev_f)))
        if len(trs) < 14:
            return None
        return fmean(trs[-14:])

    @staticmethod
    def _nearest_levels(rows: list[dict[str, Any]], current: float) -> tuple[float | None, float | None]:
        sample = rows[-20:]
        if not sample:
            return None, None

        pivot_lows: list[float] = []
        pivot_highs: list[float] = []

        for i in range(2, len(sample) - 2):
            lows = [sample[j].get("low") for j in range(i - 2, i + 3)]
            highs = [sample[j].get("high") for j in range(i - 2, i + 3)]
            if any(v is None for v in lows + highs):
                continue
            low = float(sample[i]["low"])
            high = float(sample[i]["high"])
            if low == min(float(v) for v in lows):
                pivot_lows.append(low)
            if high == max(float(v) for v in highs):
                pivot_highs.append(high)

        all_lows = [float(row["low"]) for row in sample if row.get("low") is not None]
        all_highs = [float(row["high"]) for row in sample if row.get("high") is not None]

        supports = [value for value in pivot_lows if value <= current]
        resistances = [value for value in pivot_highs if value >= current]

        support = max(supports) if supports else (min(all_lows) if all_lows else None)
        resistance = min(resistances) if resistances else (max(all_highs) if all_highs else None)
        return support, resistance

    def analyze(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        valid = [
            row
            for row in rows
            if row.get("close") is not None
            and row.get("high") is not None
            and row.get("low") is not None
        ]
        if len(valid) < 20:
            raise ValueError("기술 분석에는 최소 20거래일 OHLC 데이터가 필요합니다.")

        closes = [float(row["close"]) for row in valid]
        highs = [float(row["high"]) for row in valid]
        lows = [float(row["low"]) for row in valid]
        volumes = [float(row["volume"]) for row in valid if row.get("volume") is not None]

        current = closes[-1]
        ma5 = self._sma(closes, 5)
        ma20 = self._sma(closes, 20)
        ma60 = self._sma(closes, 60)
        ma120 = self._sma(closes, 120)

        ma20_slope_pct = None
        if len(closes) >= 25:
            now_ma20 = fmean(closes[-20:])
            prior_ma20 = fmean(closes[-25:-5])
            if prior_ma20:
                ma20_slope_pct = (now_ma20 / prior_ma20 - 1) * 100

        rsi14 = self._rsi14(closes)
        atr14 = self._atr14(valid)
        atr_pct = (atr14 / current * 100) if atr14 is not None and current else None

        volume_ratio_20 = None
        if len(volumes) >= 20:
            avg20 = fmean(volumes[-20:])
            if avg20:
                volume_ratio_20 = volumes[-1] / avg20

        high20 = max(highs[-20:])
        low20 = min(lows[-20:])
        distance_to_20d_high_pct = ((high20 - current) / current * 100) if current else None

        support, resistance = self._nearest_levels(valid, current)
        support_distance_pct = ((current - support) / current * 100) if support is not None and current else None
        resistance_distance_pct = ((resistance - current) / current * 100) if resistance is not None and current else None

        higher_high = None
        higher_low = None
        if len(valid) >= 20:
            previous = valid[-20:-10]
            recent = valid[-10:]
            prev_high = max(float(row["high"]) for row in previous)
            recent_high = max(float(row["high"]) for row in recent)
            prev_low = min(float(row["low"]) for row in previous)
            recent_low = min(float(row["low"]) for row in recent)
            higher_high = recent_high > prev_high
            higher_low = recent_low > prev_low

        return {
            "data_points": len(valid),
            "date_from": valid[0].get("date"),
            "date_to": valid[-1].get("date"),
            "current_price": current,
            "ma5": round(ma5, 2) if ma5 is not None else None,
            "ma20": round(ma20, 2) if ma20 is not None else None,
            "ma60": round(ma60, 2) if ma60 is not None else None,
            "ma120": round(ma120, 2) if ma120 is not None else None,
            "ma20_slope_pct": round(ma20_slope_pct, 3) if ma20_slope_pct is not None else None,
            "rsi14": round(rsi14, 2) if rsi14 is not None else None,
            "atr14": round(atr14, 2) if atr14 is not None else None,
            "atr_pct": round(atr_pct, 3) if atr_pct is not None else None,
            "volume_ratio_20": round(volume_ratio_20, 3) if volume_ratio_20 is not None else None,
            "high20": high20,
            "low20": low20,
            "distance_to_20d_high_pct": round(distance_to_20d_high_pct, 3) if distance_to_20d_high_pct is not None else None,
            "support": support,
            "resistance": resistance,
            "support_distance_pct": round(support_distance_pct, 3) if support_distance_pct is not None else None,
            "resistance_distance_pct": round(resistance_distance_pct, 3) if resistance_distance_pct is not None else None,
            "higher_high": higher_high,
            "higher_low": higher_low,
        }
    def preview_with_reference_price(
        self,
        rows: list[dict[str, Any]],
        reference_price: float,
        base_analysis: dict[str, Any] | None = None,
        reference_high: float | None = None,
        reference_low: float | None = None,
        reference_volume: float | None = None,
    ) -> dict[str, Any]:
        """Build an ephemeral current-reference scenario without mutating KRX history.

        reference_price is treated as a hypothetical current close only for indicators that
        can be updated from price. Optional high/low/volume inputs improve the provisional
        ATR and volume confirmation. None of these values are written into KRX EOD history.
        """
        if reference_price <= 0:
            raise ValueError("현재 참고가격은 0보다 커야 합니다.")
        if reference_high is not None and reference_high <= 0:
            raise ValueError("오늘 고가는 0보다 커야 합니다.")
        if reference_low is not None and reference_low <= 0:
            raise ValueError("오늘 저가는 0보다 커야 합니다.")
        if reference_volume is not None and reference_volume < 0:
            raise ValueError("현재 거래량은 0 이상이어야 합니다.")
        if reference_high is not None and reference_low is not None and reference_high < reference_low:
            raise ValueError("오늘 고가는 오늘 저가보다 작을 수 없습니다.")
        if reference_high is not None and reference_price > reference_high:
            raise ValueError("현재 참고가격은 입력한 오늘 고가보다 높을 수 없습니다.")
        if reference_low is not None and reference_price < reference_low:
            raise ValueError("현재 참고가격은 입력한 오늘 저가보다 낮을 수 없습니다.")

        valid = [row for row in rows if row.get("close") is not None]
        if len(valid) < 20:
            raise ValueError("현재 참고가격 미리보기에는 최소 20거래일 종가가 필요합니다.")

        base = base_analysis or self.analyze(rows)
        closes = [float(row["close"]) for row in valid]
        confirmed_close = closes[-1]
        gap_pct = (reference_price / confirmed_close - 1) * 100 if confirmed_close else 0.0

        estimated_ma20 = fmean(closes[-19:] + [float(reference_price)]) if len(closes) >= 19 else None
        estimated_rsi14 = self._rsi14(closes[-14:] + [float(reference_price)]) if len(closes) >= 14 else None

        high20 = base.get("high20")
        support = base.get("support")
        resistance = base.get("resistance")

        # Price-only distances are valid as a scenario because the historical levels remain fixed.
        distance_to_high = None
        if high20 is not None:
            distance_to_high = (float(high20) - reference_price) / reference_price * 100

        support_distance = None
        if support is not None:
            support_distance = (reference_price - float(support)) / reference_price * 100

        resistance_distance = None
        if resistance is not None:
            resistance_distance = (float(resistance) - reference_price) / reference_price * 100

        estimated_volume_ratio = None
        if reference_volume is not None:
            confirmed_volumes = [float(row["volume"]) for row in valid[-20:] if row.get("volume") is not None]
            if confirmed_volumes:
                avg_confirmed_20 = fmean(confirmed_volumes)
                if avg_confirmed_20:
                    estimated_volume_ratio = float(reference_volume) / avg_confirmed_20

        estimated_atr14 = None
        estimated_atr_pct = None
        if reference_high is not None and reference_low is not None and len(valid) >= 14:
            # Keep 13 confirmed true ranges and append a provisional current-day true range.
            confirmed_trs: list[float] = []
            for index in range(max(1, len(valid) - 13), len(valid)):
                high = valid[index].get("high")
                low = valid[index].get("low")
                prev_close = valid[index - 1].get("close")
                if high is None or low is None or prev_close is None:
                    continue
                high_f, low_f, prev_f = float(high), float(low), float(prev_close)
                confirmed_trs.append(max(high_f - low_f, abs(high_f - prev_f), abs(low_f - prev_f)))
            current_tr = max(
                float(reference_high) - float(reference_low),
                abs(float(reference_high) - confirmed_close),
                abs(float(reference_low) - confirmed_close),
            )
            trs = (confirmed_trs[-13:] + [current_tr])[-14:]
            if len(trs) == 14:
                estimated_atr14 = fmean(trs)
                estimated_atr_pct = estimated_atr14 / reference_price * 100 if reference_price else None

        atr_pct_for_threshold = estimated_atr_pct if estimated_atr_pct is not None else base.get("atr_pct")
        atr_value = float(atr_pct_for_threshold) if atr_pct_for_threshold is not None else 0.0
        stale_threshold = max(5.0, atr_value * 1.5)
        extreme_threshold = max(8.0, atr_value * 2.0)
        abs_gap = abs(gap_pct)

        if abs_gap >= extreme_threshold:
            status = "EXTREME_MOVE"
            message = "확정 종가와 현재 참고가격의 차이가 매우 커 기존 EOD 전략의 신뢰도가 낮습니다."
        elif abs_gap >= stale_threshold:
            status = "STALE"
            message = "현재 참고가격이 확정 종가에서 크게 벗어나 기존 EOD 분석을 그대로 적용하기 어렵습니다."
        else:
            status = "REFERENCE_UPDATED"
            message = "현재 참고가격을 반영해 계산 가능한 지표를 임시 재계산했습니다."

        supplied = {
            "price": True,
            "high": reference_high is not None,
            "low": reference_low is not None,
            "volume": reference_volume is not None,
        }
        if supplied["high"] and supplied["low"] and supplied["volume"]:
            input_mode = "PRICE_OHLCV"
        elif supplied["high"] and supplied["low"]:
            input_mode = "PRICE_OHLC"
        else:
            input_mode = "PRICE_ONLY"

        return {
            "source": "USER_INPUT",
            "status": status,
            "message": message,
            "input_mode": input_mode,
            "supplied": supplied,
            "confirmed_date": base.get("date_to"),
            "confirmed_close": confirmed_close,
            "reference_price": float(reference_price),
            "reference_high": float(reference_high) if reference_high is not None else None,
            "reference_low": float(reference_low) if reference_low is not None else None,
            "reference_volume": float(reference_volume) if reference_volume is not None else None,
            "gap_pct": round(gap_pct, 3),
            "stale_threshold_pct": round(stale_threshold, 3),
            "extreme_threshold_pct": round(extreme_threshold, 3),
            "is_stale": status in {"STALE", "EXTREME_MOVE"},
            "is_extreme_move": status == "EXTREME_MOVE",
            "estimated": {
                "ma20": round(estimated_ma20, 2) if estimated_ma20 is not None else None,
                "rsi14": round(estimated_rsi14, 2) if estimated_rsi14 is not None else None,
                "atr14": round(estimated_atr14, 2) if estimated_atr14 is not None else None,
                "atr_pct": round(estimated_atr_pct, 3) if estimated_atr_pct is not None else None,
                "volume_ratio_20": round(estimated_volume_ratio, 3) if estimated_volume_ratio is not None else None,
                "distance_to_20d_high_pct": round(distance_to_high, 3) if distance_to_high is not None else None,
                "support_distance_pct": round(support_distance, 3) if support_distance is not None else None,
                "resistance_distance_pct": round(resistance_distance, 3) if resistance_distance is not None else None,
            },
            "confirmed_only": {
                "ma20_slope_pct": base.get("ma20_slope_pct"),
                "higher_high": base.get("higher_high"),
                "higher_low": base.get("higher_low"),
                "atr_pct": base.get("atr_pct") if estimated_atr_pct is None else None,
                "volume_ratio_20": base.get("volume_ratio_20") if estimated_volume_ratio is None else None,
                "support": support,
                "resistance": resistance,
            },
        }

