from __future__ import annotations

from typing import Any


class RelativeStrengthAnalyzer:
    """Compare a stock's confirmed KRX EOD performance with its market index.

    Relative strength here means *performance relative to the benchmark*, not RSI.
    All calculations intentionally use confirmed EOD stock/index data only so a
    manually entered current stock price is never compared against a stale EOD index.
    """

    PERIODS = (5, 20, 60)

    @staticmethod
    def _close_by_date(rows: list[dict[str, Any]]) -> dict[str, float]:
        result: dict[str, float] = {}
        for row in rows:
            value = row.get("close")
            row_date = str(row.get("date") or "")
            if not row_date or value is None:
                continue
            try:
                close = float(value)
            except (TypeError, ValueError):
                continue
            if close > 0:
                result[row_date] = close
        return result

    @staticmethod
    def _period_label(excess: float) -> tuple[str, str]:
        if excess >= 5:
            return "STRONG", "강함"
        if excess >= 1:
            return "OUTPERFORM", "다소 강함"
        if excess > -1:
            return "NEUTRAL", "중립"
        if excess > -5:
            return "UNDERPERFORM", "다소 약함"
        return "WEAK", "약함"

    @staticmethod
    def _trend(relative_ratios: list[float]) -> tuple[str, str, str]:
        # Compare the latest 5-session relative-ratio move with the preceding
        # 5-session move. This avoids directly comparing cumulative 5d vs 20d returns.
        if len(relative_ratios) < 11:
            return "UNKNOWN", "판단 보류", "상대강도 추세를 비교할 데이터가 부족합니다."
        recent = (relative_ratios[-1] / relative_ratios[-6] - 1) * 100
        previous = (relative_ratios[-6] / relative_ratios[-11] - 1) * 100
        delta = recent - previous
        if delta >= 1.5:
            return "IMPROVING", "개선 중", f"최근 5거래일 상대 흐름이 직전 5거래일보다 {delta:+.2f}%p 개선됐습니다."
        if delta <= -1.5:
            return "DETERIORATING", "약화 중", f"최근 5거래일 상대 흐름이 직전 5거래일보다 {delta:+.2f}%p 약해졌습니다."
        return "STABLE", "유지", f"최근 상대강도 변화가 {delta:+.2f}%p로 큰 방향 변화는 없습니다."

    @staticmethod
    def _strategy_effects(primary_excess: float | None) -> list[dict[str, Any]]:
        specs = [
            ("trend_following", "추세추종", 6, lambda value: value > 0),
            ("pullback", "눌림목", 4, lambda value: value >= 0),
            ("breakout", "돌파", 10, lambda value: value > 0),
            ("momentum_continuation", "모멘텀 지속", 6, lambda value: value > 0),
        ]
        effects: list[dict[str, Any]] = []
        for strategy, label, weight, condition in specs:
            if primary_excess is None:
                effects.append({
                    "strategy": strategy,
                    "label": label,
                    "weight": weight,
                    "condition_met": None,
                    "direction": "NEUTRAL",
                    "message": "시장 대비 상대강도 데이터가 부족해 이 조건은 확인되지 않았습니다.",
                })
                continue
            met = bool(condition(primary_excess))
            effects.append({
                "strategy": strategy,
                "label": label,
                "weight": weight,
                "condition_met": met,
                "direction": "UP" if met else "DOWN",
                "message": (
                    f"20일 시장 대비 {primary_excess:+.2f}%p로 상대강도 조건을 충족합니다."
                    if met
                    else f"20일 시장 대비 {primary_excess:+.2f}%p로 상대강도 조건을 충족하지 못합니다."
                ),
            })
        return effects


    @staticmethod
    def _decision_result(
        *,
        periods: list[dict[str, Any]],
        trend: str,
        trend_label: str,
        benchmark: str,
        position_mode: str,
    ) -> dict[str, Any]:
        by_days = {int(row["days"]): row for row in periods if row.get("available")}
        p5 = by_days.get(5)
        p20 = by_days.get(20)
        p60 = by_days.get(60)

        def excess(row: dict[str, Any] | None) -> float | None:
            value = row.get("excess_return_pct") if row else None
            return float(value) if value is not None else None

        e5, e20, e60 = excess(p5), excess(p20), excess(p60)
        stock5 = float(p5["stock_return_pct"]) if p5 and p5.get("stock_return_pct") is not None else None

        if e20 is None:
            return {
                "archetype": "UNKNOWN",
                "label": "판단 보류",
                "headline": "시장 대비 우위를 판단할 데이터가 부족합니다.",
                "summary": "상대강도만으로 행동 우선순위를 바꾸지 않습니다.",
                "confidence": "LOW",
                "confidence_label": "낮음",
                "new_entry": {
                    "action": "다른 분석 근거 우선",
                    "summary": "기술적 구조·리스크·공시 분석을 우선 사용합니다.",
                },
                "holding": {
                    "action": "기존 보유 기준 유지",
                    "summary": "상대강도 데이터 부족만으로 보유 판단을 바꾸지 않습니다.",
                },
                "user_response": {
                    "perspective": "보유 관리" if position_mode == "HOLDING" else "신규 진입",
                    "action": "상대강도 판단 보류",
                    "summary": "충분한 공통 거래일 데이터가 생길 때까지 다른 분석 결과를 우선합니다.",
                },
                "preferred_strategies": [],
                "deprioritized_strategies": [],
                "why": ["20거래일 시장 대비 성과를 계산할 공통 데이터가 부족합니다."],
                "watch_points": ["공통 KRX EOD 데이터가 충분히 쌓인 뒤 다시 분석"],
                "short_term_heat": "UNKNOWN",
                "short_term_heat_label": "판단 보류",
            }

        strong_short = e5 is not None and e5 >= 5
        stock_hot = stock5 is not None and stock5 >= 10
        short_term_heat = "HIGH" if strong_short or stock_hot else "NORMAL"
        short_term_heat_label = "단기 추격 부담 있음" if short_term_heat == "HIGH" else "과도한 단기 확장 신호 없음"

        why: list[str] = []
        watch: list[str] = []
        preferred: list[str] = []
        deprioritized: list[str] = []

        if e20 >= 5:
            if e60 is not None and e60 < -1:
                archetype = "SHORT_TERM_RECOVERY"
                label = "단기 회복형 강세"
                headline = "최근에는 시장을 강하게 이기지만, 중기 추세 전환은 아직 확정되지 않았습니다."
                summary = (
                    f"20거래일 기준 {benchmark}보다 {e20:+.2f}%p 강하지만 "
                    f"60거래일 기준은 {e60:+.2f}%p입니다. 단기 힘은 강해졌지만 장기 약세를 완전히 뒤집었다고 보긴 이릅니다."
                )
                new_entry = {
                    "action": "추격보다 눌림·지지 확인 우선",
                    "summary": "강한 단기 흐름은 인정하되, 60일 상대강도까지 회복되는지 확인한 뒤 공격적으로 접근하는 편이 낫습니다.",
                }
                holding = {
                    "action": "보유 근거 개선 · 중기 전환 확인",
                    "summary": "최근 시장 대비 우위는 보유 논리를 보강하지만, 60일 상대강도가 아직 약해 재약화 여부를 같이 봅니다.",
                }
                preferred = ["추세 회복", "모멘텀 지속", "눌림목"]
                deprioritized = ["무리한 추격 돌파"]
                why.append(f"20일 상대성과가 {e20:+.2f}%p로 강합니다.")
                why.append(f"반면 60일 상대성과는 {e60:+.2f}%p로 아직 시장보다 약합니다.")
                watch += [
                    "60일 시장 대비 성과가 0%p 이상으로 회복하는지",
                    "20일 시장 대비 우위가 +1%p 아래로 다시 약해지는지",
                ]
            elif trend == "DETERIORATING":
                archetype = "STRONG_BUT_FADING"
                label = "강하지만 둔화"
                headline = "시장보다 강한 상태지만 상대강도 모멘텀이 약해지고 있습니다."
                summary = f"20거래일 시장 대비 {e20:+.2f}%p 우위지만 최근 상대 흐름은 {trend_label}입니다."
                new_entry = {
                    "action": "신규 추격 주의",
                    "summary": "강한 종목이라는 이유만으로 뒤늦게 따라가기보다 상대강도가 다시 개선되는지 확인합니다.",
                }
                holding = {
                    "action": "보유 관찰 · 상대강도 이탈 감시",
                    "summary": "현재 우위는 유지되지만 둔화가 이어지면 보유 근거가 약해질 수 있습니다.",
                }
                preferred = ["눌림목", "지지선 반등"]
                deprioritized = ["추격 돌파", "모멘텀 지속"]
                why += [
                    f"20일 시장 대비 성과는 {e20:+.2f}%p로 강합니다.",
                    "최근 상대강도 흐름은 약화 중입니다.",
                ]
                watch += [
                    "상대강도 흐름이 다시 개선으로 전환하는지",
                    "20일 시장 대비 성과가 +1%p 아래로 내려가는지",
                ]
            else:
                archetype = "MARKET_LEADER"
                label = "시장 주도형"
                headline = "현재 시장보다 확실히 강한 종목군에 속합니다."
                summary = f"20거래일 기준 {benchmark}를 {e20:+.2f}%p 이기고 있어 추세·모멘텀 계열 전략에 우호적입니다."
                new_entry = {
                    "action": "추세·돌파 후보 우선 검토",
                    "summary": "시장 대비 강도가 유지되는 종목이므로 다른 기술 조건까지 맞으면 우선순위를 높일 수 있습니다.",
                }
                holding = {
                    "action": "시장 대비 우위가 보유 논리 보강",
                    "summary": "상대강도가 유지되는 동안은 종목 자체 힘이 시장보다 강하다는 근거가 됩니다.",
                }
                preferred = ["추세추종", "돌파", "모멘텀 지속"]
                deprioritized = []
                why.append(f"20일 시장 대비 성과가 {e20:+.2f}%p입니다.")
                if e60 is not None:
                    why.append(f"60일 시장 대비 성과도 {e60:+.2f}%p입니다.")
                watch += [
                    "20일 시장 대비 성과가 +1%p 아래로 약해지는지",
                    "상대강도 흐름이 약화 중으로 바뀌는지",
                ]

        elif e20 >= 1:
            archetype = "OUTPERFORMING"
            label = "완만한 시장 우위"
            headline = "시장보다 강하지만 주도주라고 단정할 정도의 격차는 아닙니다."
            summary = f"20거래일 기준 {benchmark} 대비 {e20:+.2f}%p 우위입니다."
            if trend == "IMPROVING":
                new_action = "관심 우선순위 상향 · 추세 확인"
                new_summary = "상대강도가 개선 중이므로 기술적 진입 조건이 맞는지 이어서 확인할 가치가 있습니다."
                preferred = ["추세추종", "추세 회복"]
            else:
                new_action = "관찰 유지"
                new_summary = "시장 우위는 있으나 상대강도 하나만으로 적극적인 판단을 내릴 정도는 아닙니다."
                preferred = ["추세추종"]
            new_entry = {"action": new_action, "summary": new_summary}
            holding = {
                "action": "보유 근거 소폭 강화",
                "summary": "시장보다 조금 강하다는 점은 긍정적이지만 다른 구조적 근거와 함께 봅니다.",
            }
            why.append(f"20일 시장 대비 성과가 {e20:+.2f}%p입니다.")
            why.append(f"상대강도 흐름은 {trend_label}입니다.")
            watch += ["20일 시장 대비 격차가 +5%p 이상으로 확대되는지", "0%p 아래로 밀리는지"]

        elif e20 > -1:
            archetype = "MARKET_LIKE"
            label = "시장과 비슷"
            headline = "상대강도만으로는 이 종목을 우선할 근거가 없습니다."
            summary = f"20거래일 기준 {benchmark} 대비 차이가 {e20:+.2f}%p로 사실상 비슷한 흐름입니다."
            new_entry = {
                "action": "상대강도는 중립 · 다른 근거로 결정",
                "summary": "기술적 구조, 공시, 리스크, 가격 위치를 더 중요하게 봅니다.",
            }
            holding = {
                "action": "상대강도 영향 중립",
                "summary": "시장과 비슷하게 움직여 보유 논리를 강화하거나 약화시키는 신호가 아닙니다.",
            }
            preferred = []
            deprioritized = []
            why.append(f"20일 시장 대비 차이가 {e20:+.2f}%p에 불과합니다.")
            watch += ["시장 대비 +1%p 이상 우위가 생기는지", "-1%p 아래로 약해지는지"]

        else:
            if trend == "IMPROVING" and e5 is not None and e5 > 0:
                archetype = "RECOVERY_ATTEMPT"
                label = "약세 회복 시도"
                headline = "아직 시장보다 약하지만 단기 상대강도는 회복을 시도하고 있습니다."
                summary = f"20일 기준 {benchmark}보다 {e20:+.2f}%p 약하지만 최근 흐름은 개선되고 있습니다."
                new_entry = {
                    "action": "추세 전환 확인 전 우선순위 낮음",
                    "summary": "회복 조짐만으로 선행 진입하기보다 20일 상대성과가 0%p를 넘어서는지 확인합니다.",
                }
                holding = {
                    "action": "회복 여부 관찰",
                    "summary": "단기 개선은 긍정적이지만 아직 시장보다 약한 상태라 보유 근거를 강하게 보강하진 못합니다.",
                }
                preferred = ["추세 회복", "지지선 반등"]
                deprioritized = ["추세추종", "돌파"]
                why += [
                    f"20일 시장 대비 성과는 {e20:+.2f}%p로 약합니다.",
                    "최근 상대강도 흐름은 개선 중입니다.",
                ]
                watch += ["20일 시장 대비 성과가 0%p 이상으로 회복하는지", "최근 개선 흐름이 다시 꺾이는지"]
            else:
                archetype = "MARKET_LAGGARD"
                label = "시장 소외형"
                headline = "현재 시장보다 약한 종목이라 추세·돌파 후보 우선순위를 낮추는 편이 합리적입니다."
                summary = f"20거래일 기준 {benchmark}보다 {abs(e20):.2f}%p 뒤처졌습니다."
                new_entry = {
                    "action": "추세·돌파 신규 후보 우선순위 낮춤",
                    "summary": "시장보다 약한 종목을 굳이 먼저 고르기보다 상대강도가 회복되는 종목을 우선 비교합니다.",
                }
                holding = {
                    "action": "보유 근거 재점검 요소",
                    "summary": "상대강도 약세가 계속되면 다른 보유 근거가 충분한지 함께 재확인할 필요가 있습니다.",
                }
                preferred = ["과매도 반등", "추세 회복"]
                deprioritized = ["추세추종", "돌파", "모멘텀 지속"]
                why.append(f"20일 시장 대비 성과가 {e20:+.2f}%p로 약합니다.")
                if e60 is not None:
                    why.append(f"60일 시장 대비 성과는 {e60:+.2f}%p입니다.")
                watch += ["20일 시장 대비 성과가 0%p 이상으로 회복하는지", "상대강도 흐름이 개선으로 전환하는지"]

        if short_term_heat == "HIGH":
            why.append("최근 5거래일 상대강도 또는 절대 상승폭이 커 단기 추격 부담이 있을 수 있습니다.")
            watch.append("5거래일 급등 이후 지지구간이 새로 형성되는지")

        user_response = holding if position_mode == "HOLDING" else new_entry
        confidence = "HIGH" if all(value is not None for value in (e5, e20, e60)) else "MEDIUM"

        return {
            "archetype": archetype,
            "label": label,
            "headline": headline,
            "summary": summary,
            "confidence": confidence,
            "confidence_label": "높음" if confidence == "HIGH" else "보통",
            "new_entry": new_entry,
            "holding": holding,
            "user_response": {
                "perspective": "보유 관리" if position_mode == "HOLDING" else "신규 진입",
                "action": user_response["action"],
                "summary": user_response["summary"],
            },
            "preferred_strategies": preferred,
            "deprioritized_strategies": deprioritized,
            "why": why,
            "watch_points": list(dict.fromkeys(watch)),
            "short_term_heat": short_term_heat,
            "short_term_heat_label": short_term_heat_label,
        }

    def analyze(
        self,
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
        *,
        market: str,
        benchmark_name: str | None = None,
        position_mode: str = "NOT_HELD",
    ) -> dict[str, Any]:
        stock = self._close_by_date(stock_rows)
        benchmark = self._close_by_date(index_rows)
        common_dates = sorted(set(stock) & set(benchmark))

        if len(common_dates) < 2:
            return {
                "available": False,
                "source": "KRX_EOD",
                "price_basis": "CONFIRMED_EOD",
                "benchmark": {"market": market.upper(), "name": benchmark_name or market.upper()},
                "as_of": common_dates[-1] if common_dates else None,
                "aligned_points": len(common_dates),
                "primary_period": None,
                "primary_excess_pct": None,
                "status": "UNKNOWN",
                "label": "데이터 부족",
                "trend": "UNKNOWN",
                "trend_label": "판단 보류",
                "trend_message": "종목과 시장 지수의 공통 거래일 데이터가 부족합니다.",
                "summary": "시장 대비 상대강도를 계산할 공통 KRX 확정 데이터가 부족합니다.",
                "periods": [],
                "strategy_effects": self._strategy_effects(None),
                "decision": self._decision_result(
                    periods=[],
                    trend="UNKNOWN",
                    trend_label="판단 보류",
                    benchmark=benchmark_name or market.upper(),
                    position_mode=position_mode,
                ),
                "note": "수동 현재가는 실시간 시장지수와 시점이 맞지 않으므로 상대강도 계산에 사용하지 않습니다.",
            }

        stock_values = [stock[d] for d in common_dates]
        market_values = [benchmark[d] for d in common_dates]
        relative_ratios = [s / m for s, m in zip(stock_values, market_values, strict=True) if m > 0]

        period_rows: list[dict[str, Any]] = []
        by_period: dict[int, dict[str, Any]] = {}
        for days in self.PERIODS:
            if len(common_dates) < days + 1:
                row = {
                    "days": days,
                    "available": False,
                    "stock_return_pct": None,
                    "market_return_pct": None,
                    "excess_return_pct": None,
                    "status": "UNKNOWN",
                    "label": "데이터 부족",
                }
            else:
                stock_start = stock_values[-(days + 1)]
                stock_end = stock_values[-1]
                market_start = market_values[-(days + 1)]
                market_end = market_values[-1]
                stock_return = (stock_end / stock_start - 1) * 100
                market_return = (market_end / market_start - 1) * 100
                excess = stock_return - market_return
                status, label = self._period_label(excess)
                row = {
                    "days": days,
                    "available": True,
                    "stock_return_pct": round(stock_return, 3),
                    "market_return_pct": round(market_return, 3),
                    "excess_return_pct": round(excess, 3),
                    "status": status,
                    "label": label,
                }
            period_rows.append(row)
            by_period[days] = row

        primary = by_period[20] if by_period[20]["available"] else by_period[5]
        primary_excess = primary.get("excess_return_pct") if primary.get("available") else None
        if primary_excess is None:
            status, label = "UNKNOWN", "데이터 부족"
        else:
            status, label = self._period_label(float(primary_excess))

        trend, trend_label, trend_message = self._trend(relative_ratios)
        benchmark_display = benchmark_name or market.upper()

        if primary_excess is None:
            summary = "시장 대비 상대강도를 계산할 데이터가 충분하지 않습니다."
        elif primary_excess >= 1:
            summary = f"최근 20거래일 기준 종목이 {benchmark_display}보다 {primary_excess:+.2f}%p 강했습니다. 절대 상승률보다 시장을 이겼는지까지 함께 확인할 수 있습니다."
        elif primary_excess <= -1:
            summary = f"최근 20거래일 기준 종목이 {benchmark_display}보다 {primary_excess:+.2f}%p 약했습니다. 종목이 상승했더라도 시장보다 덜 올랐다면 상대적으로 약한 흐름입니다."
        else:
            summary = f"최근 20거래일 기준 {benchmark_display} 대비 차이가 {primary_excess:+.2f}%p로 비슷한 흐름입니다."

        return {
            "available": primary_excess is not None,
            "source": "KRX_EOD",
            "price_basis": "CONFIRMED_EOD",
            "benchmark": {"market": market.upper(), "name": benchmark_display},
            "as_of": common_dates[-1],
            "aligned_points": len(common_dates),
            "primary_period": int(primary["days"]) if primary.get("available") else None,
            "primary_excess_pct": primary_excess,
            "status": status,
            "label": label,
            "trend": trend,
            "trend_label": trend_label,
            "trend_message": trend_message,
            "summary": summary,
            "periods": period_rows,
            "strategy_effects": self._strategy_effects(float(primary_excess) if primary_excess is not None else None),
            "decision": self._decision_result(
                periods=period_rows,
                trend=trend,
                trend_label=trend_label,
                benchmark=benchmark_display,
                position_mode=position_mode,
            ),
            "note": "상대강도는 KRX 확정 EOD 종목·시장지수의 같은 거래일끼리 비교합니다. 사용자가 입력한 현재가는 실시간 시장지수와 시점이 맞지 않아 여기에는 섞지 않습니다.",
        }
