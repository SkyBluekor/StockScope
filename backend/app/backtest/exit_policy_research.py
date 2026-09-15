from __future__ import annotations

from statistics import fmean, median
from typing import Any, Callable

from app.backtest.engine import BacktestEngine
from app.backtest.exit_policy_catalog import (
    ExitPolicySpec,
    POLICY_ATR_15,
    POLICY_ATR_20,
    POLICY_ATR_25,
    POLICY_MA20,
    POLICY_SWING_LOW,
    POLICY_TARGET1_FULL_EXIT,
    RESEARCH_POLICIES,
)
from app.backtest.exit_policy_simulator import ExitPolicySimulator
from app.backtest.metrics import summarize_trades
from app.backtest.models import BacktestConfig, BacktestTrade
from app.backtest.multi_strategy import SUPPORTED_STRATEGIES
from app.backtest.policy_lab import POLICY_CURRENT
from app.strategy.models import StrategyEvaluation, StrategyName


EXIT_RESEARCH_VERSION = "0.21.4-A"
MIN_RESEARCH_SAMPLE = 10
DEFAULT_POST_TARGET2_RESEARCH_DAYS = 60


class ExitPolicyResearchEngine:
    """Research-only comparison of post-entry exit policies.

    Production Strategy/Risk/Scanner behavior is intentionally untouched. Every
    candidate uses the same StockScope strategy qualification and next-day-open
    entry framework. Profit-protection candidates keep the original hard stop,
    treat Target1/Target2 as milestones, and activate a monotonic EOD protection
    line only after Target2 has been observed.
    """

    def __init__(self, base: BacktestEngine | None = None) -> None:
        self.base = base or BacktestEngine()
        self.simulator = ExitPolicySimulator(self.base)

    @staticmethod
    def _evaluation(snapshot: dict[str, Any], strategy: StrategyName) -> StrategyEvaluation | None:
        return (snapshot.get("evaluations") or {}).get(strategy.value)

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

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _ma20(cls, rows: list[dict[str, Any]], end_index: int) -> float | None:
        closes: list[float] = []
        for row in rows[max(0, end_index - 19) : end_index + 1]:
            value = cls._number(row.get("close"))
            if value is None:
                return None
            closes.append(value)
        return fmean(closes) if len(closes) == 20 else None

    @classmethod
    def _latest_confirmed_swing_low(
        cls,
        rows: list[dict[str, Any]],
        *,
        end_index: int,
        entry_index: int,
    ) -> float | None:
        # Same 2-left/2-right pivot concept already used by TechnicalAnalyzer.
        # A pivot is usable only after the two right-side bars have closed.
        latest: float | None = None
        scan_start = max(2, entry_index - 2)
        scan_end = end_index - 2
        if scan_end < scan_start:
            return None
        for index in range(scan_start, scan_end + 1):
            sample = rows[index - 2 : index + 3]
            lows = [cls._number(row.get("low")) for row in sample]
            if len(lows) != 5 or any(value is None for value in lows):
                continue
            center = lows[2]
            assert center is not None
            if center == min(value for value in lows if value is not None):
                latest = center
        return latest

    def _protection_candidate(
        self,
        *,
        policy: ExitPolicySpec,
        rows: list[dict[str, Any]],
        end_index: int,
        entry_index: int,
        target2_index: int,
    ) -> float | None:
        if end_index < target2_index:
            return None
        if policy.family == "ATR_TRAIL":
            history = rows[: end_index + 1]
            atr14 = self.base.technical._atr14(history)  # noqa: SLF001 - same TechnicalAnalyzer formula
            if atr14 is None or policy.atr_multiplier is None:
                return None
            closes = [
                float(row["close"])
                for row in rows[target2_index : end_index + 1]
                if row.get("close") is not None
            ]
            if not closes:
                return None
            return max(closes) - float(atr14) * policy.atr_multiplier
        if policy.family == "MA20":
            return self._ma20(rows, end_index)
        if policy.family == "SWING_LOW":
            return self._latest_confirmed_swing_low(
                rows,
                end_index=end_index,
                entry_index=entry_index,
            )
        return None

    @classmethod
    def _trade_path_metrics(
        cls,
        *,
        rows: list[dict[str, Any]],
        entry_index: int,
        exit_index: int,
        entry_price: float,
        exit_price: float,
    ) -> dict[str, Any]:
        closes = [
            float(row["close"])
            for row in rows[entry_index : exit_index + 1]
            if row.get("close") is not None
        ]
        peak_close = max(closes) if closes else exit_price
        peak_return = (peak_close / entry_price - 1.0) * 100.0
        realized = (exit_price / entry_price - 1.0) * 100.0
        giveback_points = max(0.0, peak_return - realized)
        giveback_ratio = None
        if peak_return > 0:
            giveback_ratio = giveback_points / peak_return * 100.0
        return {
            "peak_close": round(peak_close, 4),
            "peak_return_pct": round(peak_return, 4),
            "profit_giveback_pct_points": round(giveback_points, 4),
            "profit_giveback_of_peak_pct": None if giveback_ratio is None else round(giveback_ratio, 4),
        }

    def _enrich_baseline_trade(
        self,
        trade: BacktestTrade,
        *,
        rows: list[dict[str, Any]],
        policy: ExitPolicySpec,
    ) -> BacktestTrade:
        entry_index = next((i for i, row in enumerate(rows) if self.base._date(row) == trade.entry_date), -1)
        exit_index = next((i for i, row in enumerate(rows) if self.base._date(row) == trade.exit_date), -1)
        if entry_index >= 0 and exit_index >= entry_index:
            path = self.simulator.trade_path_metrics(
                rows=rows,
                entry_index=entry_index,
                exit_index=exit_index,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
            )
        else:
            path = {
                "peak_close": trade.exit_price,
                "peak_return_pct": trade.gross_return_pct,
                "profit_giveback_pct_points": 0.0,
                "profit_giveback_of_peak_pct": 0.0 if trade.gross_return_pct > 0 else None,
            }
        trade.metadata = {
            **dict(trade.metadata or {}),
            "exit_policy_research": {
                "version": EXIT_RESEARCH_VERSION,
                "policy_id": policy.id,
                "target1_reached": str(trade.exit_reason).startswith("TARGET_1"),
                "target2_reached": False,
                "trailing_activated": False,
                "final_protection_price": None,
                **path,
            },
        }
        trade.research_only = True
        return trade

    def _simulate_profit_protection_trade(
        self,
        *,
        signal: dict[str, Any],
        stock_rows: list[dict[str, Any]],
        config: BacktestConfig,
        strategy: StrategyName,
        policy: ExitPolicySpec,
        post_target2_research_days: int,
        extend_after_target2: bool = True,
    ) -> tuple[BacktestTrade | None, int | None]:
        # Keep the research seam patchable for existing tests while delegating the
        # actual state machine to the same simulator used by Production.
        self.simulator.protection_candidate = self._protection_candidate  # type: ignore[method-assign]
        return self.simulator.simulate_profit_protection_trade(
            signal=signal,
            stock_rows=stock_rows,
            config=config,
            strategy=strategy,
            policy=policy,
            post_target2_days=post_target2_research_days,
            extend_after_target2=extend_after_target2,
            research_only=True,
            metadata_key="exit_policy_research",
            metadata_version=EXIT_RESEARCH_VERSION,
            horizon_exit_reason="RESEARCH_HORIZON_EXIT",
        )

    @staticmethod
    def _research_metrics(trades: list[BacktestTrade]) -> dict[str, Any]:
        peak_returns: list[float] = []
        givebacks: list[float] = []
        giveback_ratios: list[float] = []
        target1_count = 0
        target2_count = 0
        trailing_exits = 0
        pre_target_time_exits = 0
        research_horizon_exits = 0
        hard_max_hold_exits = 0

        for trade in trades:
            research = (trade.metadata or {}).get("exit_policy_research") or {}
            peak = ExitPolicyResearchEngine._number(research.get("peak_return_pct"))
            giveback = ExitPolicyResearchEngine._number(research.get("profit_giveback_pct_points"))
            ratio = ExitPolicyResearchEngine._number(research.get("profit_giveback_of_peak_pct"))
            if peak is not None:
                peak_returns.append(peak)
            if giveback is not None:
                givebacks.append(giveback)
            if ratio is not None:
                giveback_ratios.append(ratio)
            target1_count += int(bool(research.get("target1_reached")))
            target2_count += int(bool(research.get("target2_reached")))
            trailing_exits += int(trade.exit_reason == "TRAILING_CLOSE_EXIT")
            pre_target_time_exits += int(trade.exit_reason == "TIME_EXIT_PRE_TARGET2")
            research_horizon_exits += int(trade.exit_reason == "RESEARCH_HORIZON_EXIT")
            hard_max_hold_exits += int(trade.exit_reason == "HARD_MAX_HOLD_EXIT")

        return {
            "average_peak_return_pct": None if not peak_returns else round(fmean(peak_returns), 3),
            "average_profit_giveback_pct_points": None if not givebacks else round(fmean(givebacks), 3),
            "median_profit_giveback_pct_points": None if not givebacks else round(median(givebacks), 3),
            "average_profit_giveback_of_peak_pct": None if not giveback_ratios else round(fmean(giveback_ratios), 3),
            "target1_reached_trades": target1_count,
            "target2_reached_trades": target2_count,
            "trailing_exit_trades": trailing_exits,
            "time_exit_before_target2_trades": pre_target_time_exits,
            "research_horizon_exit_trades": research_horizon_exits,
            "hard_max_hold_exit_trades": hard_max_hold_exits,
        }

    @staticmethod
    def _aggregation_primitives(trades: list[BacktestTrade]) -> dict[str, Any]:
        net_returns = [float(trade.net_return_pct) for trade in trades]
        givebacks: list[float] = []
        for trade in trades:
            research = (trade.metadata or {}).get("exit_policy_research") or {}
            value = ExitPolicyResearchEngine._number(research.get("profit_giveback_pct_points"))
            if value is not None:
                givebacks.append(value)
        return {
            "trades": len(trades),
            "wins": sum(1 for value in net_returns if value > 0),
            "net_return_sum_pct": round(sum(net_returns), 6),
            "positive_net_sum_pct": round(sum(value for value in net_returns if value > 0), 6),
            "negative_net_abs_sum_pct": round(abs(sum(value for value in net_returns if value < 0)), 6),
            "holding_days_sum": sum(int(trade.holding_days) for trade in trades),
            "giveback_sum_pct_points": round(sum(givebacks), 6),
            "giveback_observations": len(givebacks),
        }

    @classmethod
    def _regime_aggregation_primitives(cls, trades: list[BacktestTrade]) -> dict[str, Any]:
        grouped: dict[str, list[BacktestTrade]] = {}
        for trade in trades:
            grouped.setdefault(str(trade.market_regime or "UNKNOWN"), []).append(trade)
        result: dict[str, Any] = {}
        for regime, regime_trades in grouped.items():
            primitive = cls._aggregation_primitives(regime_trades)
            result[regime] = {
                key: primitive[key]
                for key in (
                    "trades",
                    "wins",
                    "net_return_sum_pct",
                    "positive_net_sum_pct",
                    "negative_net_abs_sum_pct",
                )
            }
        return result

    def _run_policy(
        self,
        *,
        policy: ExitPolicySpec,
        strategy: StrategyName,
        snapshots: list[dict[str, Any]],
        stock_rows: list[dict[str, Any]],
        config: BacktestConfig,
        post_target2_research_days: int,
        extend_after_target2: bool = True,
    ) -> dict[str, Any]:
        trades: list[BacktestTrade] = []
        occupied_until = -1
        armed = True
        signal_count = 0
        unusable = 0

        for snapshot in snapshots:
            evaluation = self._evaluation(snapshot, strategy)
            qualified = self._qualifies(evaluation, snapshot, config)
            if not qualified:
                armed = True
                continue
            if not armed:
                continue
            armed = False
            signal_index = int(snapshot["signal_index"])
            if signal_index <= occupied_until:
                continue
            assert evaluation is not None
            signal_count += 1
            signal = self._strategy_signal(snapshot, evaluation)

            if policy.id == POLICY_TARGET1_FULL_EXIT.id:
                trade, exit_index = self.base._simulate_trade(  # noqa: SLF001 - exact production baseline
                    signal=signal,
                    stock_rows=stock_rows,
                    config=config,
                    research_only=True,
                    strategy=strategy,
                )
                if trade is not None:
                    trade = self._enrich_baseline_trade(trade, rows=stock_rows, policy=policy)
            else:
                trade, exit_index = self._simulate_profit_protection_trade(
                    signal=signal,
                    stock_rows=stock_rows,
                    config=config,
                    strategy=strategy,
                    policy=policy,
                    post_target2_research_days=post_target2_research_days,
                    extend_after_target2=extend_after_target2,
                )

            if trade is None or exit_index is None:
                unusable += 1
                continue
            trades.append(trade)
            occupied_until = exit_index

        metrics = summarize_trades(trades, config.initial_capital)
        metrics["closed_trade_max_drawdown_pct"] = metrics["max_drawdown_pct"]
        metrics["max_drawdown_pct"] = self.base._mark_to_market_max_drawdown(  # noqa: SLF001
            trades=trades,
            stock_rows=stock_rows,
            initial_capital=config.initial_capital,
            round_trip_cost_pct=config.round_trip_cost_pct,
        )
        metrics["max_drawdown_basis"] = "DAILY_CLOSE_MARK_TO_MARKET"
        research_metrics = self._research_metrics(trades)
        sample_count = int(metrics.get("trades") or 0)
        return {
            "policy_id": policy.id,
            "label": policy.label,
            "family": policy.family,
            "activation": policy.activation,
            "exit_basis": policy.exit_basis,
            "atr_multiplier": policy.atr_multiplier,
            "signal_count": signal_count,
            "unusable_signals": unusable,
            "sample_sufficient": sample_count >= MIN_RESEARCH_SAMPLE,
            "minimum_sample": MIN_RESEARCH_SAMPLE,
            "metrics": metrics,
            "profit_protection_metrics": research_metrics,
            "aggregation_primitives": self._aggregation_primitives(trades),
            "regime_aggregation_primitives": self._regime_aggregation_primitives(trades),
            "holding_policy": (
                "TRAILING_HORIZON_AFTER_TARGET2" if extend_after_target2 else "HARD_MAX_HOLD"
            ),
            "recent_trades": [trade.to_dict() for trade in trades[-5:]],
        }

    @staticmethod
    def _metric_leader(rows: list[dict[str, Any]], path: tuple[str, str], *, lower_is_better: bool = False) -> str | None:
        candidates: list[tuple[str, float]] = []
        for row in rows:
            value = (row.get(path[0]) or {}).get(path[1])
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            candidates.append((str(row["policy_id"]), number))
        if not candidates:
            return None
        return (min if lower_is_better else max)(candidates, key=lambda item: item[1])[0]

    def run(
        self,
        *,
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
        config: BacktestConfig,
        strategies: tuple[StrategyName, ...] | None = None,
        post_target2_research_days: int = DEFAULT_POST_TARGET2_RESEARCH_DAYS,
        include_holding_policy_variants: bool = False,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if post_target2_research_days < 1 or post_target2_research_days > 240:
            raise ValueError("Target2 이후 연구 보유기간은 1~240 거래일 범위여야 합니다.")

        rows = sorted(stock_rows, key=self.base._date)
        indices = sorted(index_rows, key=self.base._date)
        start = config.start_date.replace("-", "")
        end = config.end_date.replace("-", "")
        target_indices = [i for i, row in enumerate(rows) if start <= self.base._date(row) <= end]

        snapshots: list[dict[str, Any]] = []
        for position, index in enumerate(target_indices, start=1):
            snapshot = self.base._signal_snapshot(  # noqa: SLF001 - same signal boundary as production backtest
                stock_rows=rows,
                index_rows=indices,
                index=index,
                config=config,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
            if progress_callback is not None and (position == 1 or position % 10 == 0 or position == len(target_indices)):
                progress_callback({
                    "stage": "exit_policy_snapshots",
                    "message": "Exit 정책 비교용 과거 상태 계산 중",
                    "current": position,
                    "total": max(len(target_indices), 1),
                    "details": {"snapshots": len(snapshots)},
                })

        selected_strategies = strategies or SUPPORTED_STRATEGIES
        strategy_results: list[dict[str, Any]] = []
        total_work = len(selected_strategies) * len(RESEARCH_POLICIES)
        completed = 0
        for strategy in selected_strategies:
            policy_rows: list[dict[str, Any]] = []
            for policy in RESEARCH_POLICIES:
                if progress_callback is not None:
                    progress_callback({
                        "stage": "exit_policy_comparison",
                        "message": f"{strategy.value} · {policy.label} 검증 중",
                        "current": completed,
                        "total": total_work,
                        "details": {"strategy": strategy.value, "policy": policy.id},
                    })
                policy_rows.append(
                    self._run_policy(
                        policy=policy,
                        strategy=strategy,
                        snapshots=snapshots,
                        stock_rows=rows,
                        config=config,
                        post_target2_research_days=post_target2_research_days,
                    )
                )
                completed += 1

            metric_leaders = {
                "average_net_return_pct": self._metric_leader(policy_rows, ("metrics", "average_net_return_pct")),
                "profit_factor": self._metric_leader(policy_rows, ("metrics", "profit_factor")),
                "max_drawdown_pct": self._metric_leader(policy_rows, ("metrics", "max_drawdown_pct")),
                "average_profit_giveback_pct_points": self._metric_leader(
                    policy_rows,
                    ("profit_protection_metrics", "average_profit_giveback_pct_points"),
                    lower_is_better=True,
                ),
                "average_holding_days": self._metric_leader(
                    policy_rows,
                    ("metrics", "average_holding_days"),
                    lower_is_better=True,
                ),
            }
            holding_policy_variants: list[dict[str, Any]] = []
            if include_holding_policy_variants:
                for policy in RESEARCH_POLICIES:
                    if policy.id == POLICY_TARGET1_FULL_EXIT.id:
                        continue
                    holding_policy_variants.append(
                        self._run_policy(
                            policy=policy,
                            strategy=strategy,
                            snapshots=snapshots,
                            stock_rows=rows,
                            config=config,
                            post_target2_research_days=post_target2_research_days,
                            extend_after_target2=False,
                        )
                    )

            strategy_results.append({
                "strategy": strategy.value,
                "policies": policy_rows,
                "holding_policy_variants": holding_policy_variants,
                "metric_leaders": metric_leaders,
                "review_status": (
                    "ENOUGH_SAMPLE_TO_REVIEW"
                    if any(bool(row.get("sample_sufficient")) for row in policy_rows)
                    else "SAMPLE_INSUFFICIENT"
                ),
            })

        return {
            "version": EXIT_RESEARCH_VERSION,
            "research_only": True,
            "code": config.code,
            "market": config.market,
            "period": {"start": config.start_date, "end": config.end_date},
            "strategies": strategy_results,
            "policy_catalog": [
                {
                    "id": policy.id,
                    "label": policy.label,
                    "family": policy.family,
                    "activation": policy.activation,
                    "exit_basis": policy.exit_basis,
                    "atr_multiplier": policy.atr_multiplier,
                }
                for policy in RESEARCH_POLICIES
            ],
            "config": {
                "entry_price_policy": "NEXT_TRADING_DAY_OPEN",
                "initial_stop_policy": "EXISTING_RISK_ENGINE_INVALIDATION",
                "same_day_stop_target2_policy": "STOP_FIRST_CONSERVATIVE",
                "pre_target2_max_holding_days": config.max_holding_days,
                "post_target2_research_days": post_target2_research_days,
                "trailing_activation": "TARGET2_REACHED",
                "trailing_exit_confirmation": "DAILY_CLOSE",
                "protection_update_policy": "AFTER_CLOSE_FOR_NEXT_TRADING_DAY_ONLY",
                "protection_direction": "NON_DECREASING",
                "round_trip_cost_pct": config.round_trip_cost_pct,
                "holding_policy_variants_included": include_holding_policy_variants,
            },
            "methodology": {
                "purpose": "Production Exit 정책을 바꾸기 전에 Target1 종료와 여러 Profit Protection 후보를 같은 전략 신호/데이터 경계에서 비교합니다.",
                "atr_grid": "ATR 배수는 1.5/2.0/2.5를 동시에 비교하며 이번 단계에서 한 값을 정답으로 고정하지 않습니다.",
                "ma20": "MA20은 전 거래일까지 확정된 20일 종가 평균을 다음 거래일 보호 후보로 사용합니다.",
                "swing_low": "Swing Low는 좌우 2개 봉으로 이미 확정된 최근 pivot low만 사용합니다.",
                "lookahead_guard": "오늘 종가가 기존 보호선을 지켰을 때만 오늘 데이터로 내일 보호선을 올립니다. 오늘 새 고점으로 오늘의 이탈을 취소하지 않습니다.",
                "target_policy": "Profit Protection 후보에서 Target1/Target2는 milestone이며 Target2 이후부터 trailing을 활성화합니다.",
                "max_hold": "Target2 이전에는 기존 max holding을 유지하고, Target2 이후는 별도 research horizon으로 연장합니다. 이는 연구용이며 Production 정책이 아닙니다.",
                "selection_guardrail": "이 결과는 정책 자동 확정이 아닙니다. 전략별 표본과 Net/PF/MDD/Giveback/보유기간을 함께 검토한 뒤 v0.21.4-B 정책을 결정합니다.",
            },
            "guardrail": "Exit Policy Research 결과는 미래 수익 확률이 아니며 현재 StockScope의 실제 청산 정책을 변경하지 않습니다.",
        }
