from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from app.backtest.engine import BacktestEngine
from app.backtest.metrics import summarize_trades
from app.backtest.entry_risk_guide import build_entry_risk_guide
from app.backtest.models import BacktestConfig, BacktestTrade
from app.backtest.selector import build_condition_state, current_readiness, historical_fit, select_strategy, strategy_guide, strategy_label
from app.strategy.models import StrategyEvaluation, StrategyName


SUPPORTED_STRATEGIES: tuple[StrategyName, ...] = (
    StrategyName.TREND_FOLLOWING,
    StrategyName.PULLBACK,
    StrategyName.BREAKOUT,
    StrategyName.SUPPORT_BOUNCE,
    StrategyName.OVERSOLD_BOUNCE,
    StrategyName.RANGE_TRADING,
    StrategyName.MOMENTUM_CONTINUATION,
    StrategyName.VOLATILITY_SQUEEZE,
    StrategyName.MA20_REBOUND,
    StrategyName.TREND_RECOVERY,
)


class MultiStrategyBacktestEngine:
    """Compare every StockScope strategy on one shared historical data window.

    Technical/market snapshots are calculated once per trading day. Every strategy
    then consumes the same snapshot and the same execution framework: next trading
    day open, RiskEngine invalidation/Target1, conservative same-day stop priority,
    configured max holding period, and no overlapping position inside each strategy.
    """

    def __init__(self, base: BacktestEngine | None = None) -> None:
        self.base = base or BacktestEngine()

    @staticmethod
    def _evaluation(snapshot: dict[str, Any], strategy: StrategyName) -> StrategyEvaluation | None:
        evaluations = snapshot.get("evaluations") or {}
        return evaluations.get(strategy.value)

    @staticmethod
    def _qualifies(evaluation: StrategyEvaluation | None, snapshot: dict[str, Any], config: BacktestConfig) -> bool:
        if evaluation is None or evaluation.score is None:
            return False
        if not evaluation.eligible or int(evaluation.score) < config.minimum_strategy_score:
            return False
        if bool(snapshot.get("risk_gate_active")):
            return False
        return True

    @staticmethod
    def _strategy_signal(snapshot: dict[str, Any], evaluation: StrategyEvaluation) -> dict[str, Any]:
        cloned = dict(snapshot)
        cloned["strategy_score"] = int(evaluation.score or 0)
        cloned["strategy_eligible"] = bool(evaluation.eligible)
        cloned["entry_timing_state"] = "STRATEGY_SIGNAL"
        cloned["entry_timing_passed"] = int(evaluation.passed or 0)
        cloned["entry_timing_total"] = int(evaluation.total or 0)
        return cloned

    def _current_risk_plan(self, snapshot: dict[str, Any], strategy: StrategyName) -> Any | None:
        evaluation = self._evaluation(snapshot, strategy)
        if evaluation is None:
            return None
        data = snapshot["strategy_input"]
        try:
            return self.base.risk.build_plan(
                data=replace(data, current_price=float(data.current_price)),
                strategy=strategy,
                technical=snapshot["technical"],
                risk_gate_active=bool(snapshot.get("risk_gate_active")),
                risk_gate_reasons=list(snapshot.get("risk_gate_reasons") or []),
                basis="BACKTEST_END_EOD",
            )
        except Exception:
            return None

    def _run_strategy(
        self,
        *,
        strategy: StrategyName,
        snapshots: list[dict[str, Any]],
        stock_rows: list[dict[str, Any]],
        config: BacktestConfig,
        include_trade_history: bool = False,
    ) -> dict[str, Any]:
        trades: list[BacktestTrade] = []
        occupied_until = -1
        signal_count = 0
        blocked_risk = 0
        armed = True

        for snapshot in snapshots:
            evaluation = self._evaluation(snapshot, strategy)
            qualified = self._qualifies(evaluation, snapshot, config)
            if not qualified:
                armed = True
                continue

            # One entry per continuous qualification episode. This prevents a
            # strategy from immediately re-entering every day while one condition
            # cluster remains unchanged.
            if not armed:
                continue
            armed = False
            signal_index = int(snapshot["signal_index"])
            if signal_index <= occupied_until:
                continue

            signal_count += 1
            signal = self._strategy_signal(snapshot, evaluation)
            trade, exit_index = self.base._simulate_trade(
                signal=signal,
                stock_rows=stock_rows,
                config=config,
                research_only=False,
                strategy=strategy,
            )
            if trade is None or exit_index is None:
                blocked_risk += 1
                continue
            trades.append(trade)
            occupied_until = exit_index

        metrics = summarize_trades(trades, config.initial_capital)
        metrics["closed_trade_max_drawdown_pct"] = metrics["max_drawdown_pct"]
        metrics["max_drawdown_pct"] = self.base._mark_to_market_max_drawdown(
            trades=trades,
            stock_rows=stock_rows,
            initial_capital=config.initial_capital,
            round_trip_cost_pct=config.round_trip_cost_pct,
        )
        metrics["max_drawdown_basis"] = "DAILY_CLOSE_MARK_TO_MARKET"
        fit = historical_fit(metrics)

        latest = snapshots[-1] if snapshots else None
        evaluation = self._evaluation(latest, strategy) if latest is not None else None
        risk_plan = self._current_risk_plan(latest, strategy) if latest is not None else None
        if evaluation is None:
            current = {
                "status": "NOT_READY",
                "label": "판단 불가",
                "summary": "검증 종료시점의 전략 상태를 계산하지 못했습니다.",
                "score": 0,
                "passed": 0,
                "total": 0,
                "risk_status": None,
                "unmet": [],
                "internal_score": 0.0,
                "reasons": [],
            }
        else:
            latest_data = latest["strategy_input"]
            latest_technical = latest["technical"]
            condition_state = build_condition_state(
                evaluation,
                data=latest_data,
                technical=latest_technical,
            )
            current = current_readiness(
                evaluation=evaluation,
                risk_plan=risk_plan,
                condition_state=condition_state,
            )
            current["reasons"] = list(evaluation.reasons or [])
            current["reason_details"] = condition_state["passed_details"]
            current["unmet_details"] = condition_state["missing_details"]
            current["conditions"] = condition_state["conditions"]
            current["condition_consistency"] = condition_state["consistency"]
            current["suitability"] = evaluation.suitability
            current["eligible"] = bool(evaluation.eligible)
            current["entry_risk_guide"] = build_entry_risk_guide(
                strategy=strategy,
                data=latest_data,
                technical=latest_technical,
                condition_state=condition_state,
                risk_plan=risk_plan,
                current_state=current,
                historical_verified=True,
                historical_status=fit.get("status"),
                as_of_date=str(latest.get("signal_date") or "") or None,
                entry_timing=latest.get("entry_timing") or None,
            )

        recent_trades = [trade.to_dict() for trade in trades[-5:]]
        result = {
            "strategy": strategy.value,
            "label": strategy_label(strategy),
            "guide": strategy_guide(strategy),
            "historical_fit": fit,
            "historical_metrics": metrics,
            "signal_count": signal_count,
            "risk_blocked_signals": blocked_risk,
            "current": current,
            "recent_trades": recent_trades,
        }
        if include_trade_history:
            # Internal v0.21.2 evidence path only. Default multi-strategy API payload stays unchanged.
            result["trade_history"] = [trade.to_dict() for trade in trades]
        return result

    def run(
        self,
        *,
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
        config: BacktestConfig,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        rows = sorted(stock_rows, key=self.base._date)
        indices = sorted(index_rows, key=self.base._date)
        start = config.start_date.replace("-", "")
        end = config.end_date.replace("-", "")
        target_indices = [i for i, row in enumerate(rows) if start <= self.base._date(row) <= end]

        snapshots: list[dict[str, Any]] = []
        for position, index in enumerate(target_indices, start=1):
            snapshot = self.base._signal_snapshot(
                stock_rows=rows,
                index_rows=indices,
                index=index,
                config=config,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
            if progress_callback is not None and (position == 1 or position % 5 == 0 or position == len(target_indices)):
                progress_callback({
                    "stage": "strategy_snapshot",
                    "message": "10개 전략에 공통으로 사용할 과거 상태 계산 중",
                    "current": position,
                    "total": max(len(target_indices), 1),
                    "details": {"snapshots": len(snapshots)},
                })

        strategy_rows: list[dict[str, Any]] = []
        for position, strategy in enumerate(SUPPORTED_STRATEGIES, start=1):
            if progress_callback is not None:
                progress_callback({
                    "stage": "strategy_comparison",
                    "message": f"{strategy_label(strategy)} 전략 과거 검증 중",
                    "current": position - 1,
                    "total": len(SUPPORTED_STRATEGIES),
                    "details": {"strategy": strategy.value},
                })
            strategy_rows.append(
                self._run_strategy(
                    strategy=strategy,
                    snapshots=snapshots,
                    stock_rows=rows,
                    config=config,
                )
            )

        as_of_date = str(snapshots[-1]["signal_date"]) if snapshots else end
        market_regime = str(snapshots[-1].get("market_regime") or "UNKNOWN") if snapshots else "UNKNOWN"
        recommendation = select_strategy(strategy_rows, as_of_date=as_of_date, market_regime=market_regime)
        recommended_strategy = recommendation.get("strategy")
        recommended_row = next((row for row in strategy_rows if row.get("strategy") == recommended_strategy), None)
        recommendation["entry_risk_guide"] = (recommended_row or {}).get("current", {}).get("entry_risk_guide")
        # Recompute the same internal ordering for the serializable rows. The raw
        # selector score is kept only as a diagnostic field and is not presented as
        # an upward probability in the UI.
        ranked_rows = []
        for row in strategy_rows:
            hist = float(row["historical_fit"].get("internal_score") or 0.0)
            cur = float(row["current"].get("internal_score") or 0.0)
            penalty = 20.0 if row["historical_fit"].get("status") == "INSUFFICIENT" else 8.0 if row["historical_fit"].get("status") == "WEAK" else 0.0
            ranked_rows.append({**row, "selector_score": round(hist * 0.55 + cur * 0.45 - penalty, 2)})
        ranked_rows.sort(key=lambda item: (item["selector_score"], item["historical_metrics"].get("trades") or 0), reverse=True)
        for rank, row in enumerate(ranked_rows, start=1):
            row["rank"] = rank
            row["historical_fit"].pop("internal_score", None)
            row["current"].pop("internal_score", None)

        if progress_callback is not None:
            progress_callback({
                "stage": "strategy_selector",
                "message": "과거 근거와 현재 상태를 종합해 전략 우선순위 계산 중",
                "current": 1,
                "total": 1,
                "details": {"recommended_strategy": recommendation.get("strategy") or "NO_TRADE"},
            })

        return {
            "version": "0.21.1",
            "code": config.code,
            "market": config.market,
            "period": {"start": config.start_date, "end": config.end_date},
            "as_of_date": as_of_date,
            "market_regime": market_regime,
            "recommendation": recommendation,
            "strategies": ranked_rows,
            "historical_policy": {
                "policy_id": "TARGET1_FULL_EXIT_V1",
                "label": "1차 목표 도달 시 전량 종료",
                "target1_is_exit": True,
                "target2_included": False,
                "target2_label": "2차 확장 목표",
            },
            "config": {
                "minimum_strategy_score": config.minimum_strategy_score,
                "entry_policy": "각 전략 적합도 기준 충족이 새로 시작된 첫 거래일",
                "entry_price_policy": "NEXT_TRADING_DAY_OPEN",
                "risk_exit_framework": "COMMON_RISK_ENGINE_FRAMEWORK",
                "same_day_stop_target_policy": "STOP_FIRST_CONSERVATIVE",
                "target_policy": "TARGET_1_FULL_EXIT",
                "max_holding_days": config.max_holding_days,
                "round_trip_cost_pct": config.round_trip_cost_pct,
                "overlapping_positions": "전략별 기존 거래 종료 전 재진입 금지",
            },
            "methodology": {
                "comparison": "10개 전략은 동일한 KRX 과거 데이터와 동일한 다음 거래일 시가/비용/보유기간 프레임으로 비교합니다.",
                "signal": "각 전략의 기존 StrategyEngine 조건을 사용하며 적합도 55점 이상인 새로운 조건 구간에서만 진입을 시도합니다.",
                "risk": "청산은 모두 기존 RiskEngine을 사용합니다. 전략별 구조적 기준은 RiskEngine의 기존 규칙을 따르므로 손절 가격 자체는 전략마다 달라질 수 있습니다.",
                "selector": "추천은 수익률 1등만 고르지 않고 표본, 거래당 평균, Profit Factor, MDD, 현재 전략 조건과 Risk 상태를 함께 봅니다.",
                "guardrail": "전략 선택 결과와 내부 비교 점수는 상승 확률이 아니며 미래 수익을 보장하지 않습니다.",
            },
        }
