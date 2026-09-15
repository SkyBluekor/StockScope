from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from app.backtest.audit import WIDE_STOP_PCT, build_accuracy_audit
from app.backtest.metrics import grouped_trade_metrics, score_bucket, summarize_trades
from app.backtest.models import BacktestConfig, BacktestTrade
from app.backtest.policy_lab import (
    POLICY_BLOCK_ALL_CAUTION,
    POLICY_BLOCK_WIDE_STOP,
    POLICY_CURRENT,
    POLICY_NEAREST_VALID_ANCHOR,
    build_risk_policy_comparison,
)
from app.market.pullback_confirmation import PullbackConfirmationAnalyzer
from app.market.relative_strength import RelativeStrengthAnalyzer
from app.market.technical import TechnicalAnalyzer
from app.strategy.context import build_strategy_input, regime_from_index
from app.strategy.engine import StrategyEngine
from app.strategy.models import StrategyInput, StrategyName


class BacktestEngine:
    """Historical Pullback backtest using the same analysis engines as StockScope.

    Signal-day calculations only receive rows whose date is <= signal date. Future
    rows are passed only to the execution simulator after a signal has been frozen.
    """

    LIVE_HISTORY_POINTS = 60
    RELATIVE_STRENGTH_POINTS = 61
    LIQUIDITY_THRESHOLD = 1_000_000_000
    RESEARCH_STATES = {
        "PULLBACK_IN_PROGRESS",
        "SUPPORT_APPROACH",
        "SUPPORT_TESTING",
        "REBOUND_WAITING",
        "REBOUND_CONFIRMED",
    }

    def __init__(
        self,
        *,
        technical: TechnicalAnalyzer | None = None,
        strategy: StrategyEngine | None = None,
        risk: Any | None = None,
        pullback: PullbackConfirmationAnalyzer | None = None,
        relative_strength: RelativeStrengthAnalyzer | None = None,
    ) -> None:
        self.technical = technical or TechnicalAnalyzer()
        self.strategy = strategy or StrategyEngine()
        if risk is None:
            # Lazy import avoids the pre-existing strategy <-> risk package import cycle.
            from app.risk.engine import RiskEngine

            risk = RiskEngine()
        self.risk = risk
        self.pullback = pullback or PullbackConfirmationAnalyzer()
        self.relative_strength = relative_strength or RelativeStrengthAnalyzer()

    @staticmethod
    def _date(row: dict[str, Any]) -> str:
        return str(row.get("date") or "").replace("-", "")

    @staticmethod
    def _pullback_evaluation(evaluations: list[Any]) -> Any | None:
        return next((item for item in evaluations if item.strategy == StrategyName.PULLBACK), None)

    @staticmethod
    def _risk_gate_active(evaluations: list[Any]) -> tuple[bool, list[str]]:
        no_trade = next((item for item in evaluations if item.strategy == StrategyName.NO_TRADE), None)
        blockers = list(no_trade.blockers) if no_trade and no_trade.blockers else []
        return bool(blockers), blockers

    @staticmethod
    def _index_row_for_date(index_rows: list[dict[str, Any]], signal_date: str) -> dict[str, Any] | None:
        return next((row for row in reversed(index_rows) if BacktestEngine._date(row) == signal_date), None)

    def _signal_snapshot(
        self,
        *,
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
        index: int,
        config: BacktestConfig,
    ) -> dict[str, Any] | None:
        signal_row = stock_rows[index]
        signal_date = self._date(signal_row)
        if not signal_date:
            return None

        # Keep the live analysis window identical: 60 rows for technical/pullback,
        # plus one extra row only for 60-day relative-strength returns.
        history = stock_rows[max(0, index - self.LIVE_HISTORY_POINTS + 1) : index + 1]
        if len(history) < self.LIVE_HISTORY_POINTS:
            return None
        extended_history = stock_rows[max(0, index - self.RELATIVE_STRENGTH_POINTS + 1) : index + 1]

        technical = self.technical.analyze(history)
        index_until = [row for row in index_rows if self._date(row) <= signal_date]
        index_history = index_until[-self.RELATIVE_STRENGTH_POINTS :]
        index_row = self._index_row_for_date(index_rows, signal_date)
        index_rate = index_row.get("change_rate") if index_row else None
        regime = regime_from_index(float(index_rate) if index_rate is not None else None)

        relative = self.relative_strength.analyze(
            extended_history,
            index_history,
            market=config.market,
            benchmark_name=config.market,
            position_mode="NOT_HELD",
        )
        relative_market = (
            relative.get("primary_excess_pct")
            if relative.get("primary_period") == 20
            else None
        )

        trade_value = signal_row.get("trade_value")
        liquidity_ok = trade_value is not None and float(trade_value) >= self.LIQUIDITY_THRESHOLD
        strategy_input = build_strategy_input(
            code=config.code,
            market=config.market,
            technical=technical,
            regime=regime,
            liquidity_ok=liquidity_ok,
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
            index_rate=float(index_rate) if index_rate is not None else None,
            history_points=len(history),
            event_risk=False,
            relative_strength_market_pct=(float(relative_market) if relative_market is not None else None),
            relative_strength_sector_pct=None,
            relative_strength_context=relative,
            sector_relative_strength_context=None,
        )
        evaluations = self.strategy.evaluate_all(strategy_input)
        evaluation_map = {item.strategy.value: item for item in evaluations if item.strategy != StrategyName.NO_TRADE}
        evaluation = self._pullback_evaluation(evaluations)
        if evaluation is None or evaluation.score is None:
            return None
        risk_gate_active, risk_gate_reasons = self._risk_gate_active(evaluations)

        confirmation = self.pullback.analyze(
            history=history,
            technical=technical,
            current_price=strategy_input.current_price,
            current_ma20=strategy_input.ma20,
            current_rsi14=strategy_input.rsi14,
            current_volume_ratio=strategy_input.volume_ratio_20,
            source="KRX_EOD",
            position_mode="NOT_HELD",
        )
        entry_timing = confirmation.get("entry_timing") or {}
        progress = entry_timing.get("progress") or {}

        stock_history_start = self._date(history[0]) if history else None
        stock_history_end = self._date(history[-1]) if history else None
        index_history_end = self._date(index_history[-1]) if index_history else None
        future_data_used = bool(
            (stock_history_end and stock_history_end > signal_date)
            or (index_history_end and index_history_end > signal_date)
        )

        return {
            "signal_index": index,
            "signal_date": signal_date,
            "technical": technical,
            "strategy_input": strategy_input,
            "strategy_score": int(evaluation.score),
            "strategy_eligible": bool(evaluation.eligible),
            "evaluations": evaluation_map,
            "risk_gate_active": risk_gate_active,
            "risk_gate_reasons": risk_gate_reasons,
            "entry_timing_state": str(entry_timing.get("state") or confirmation.get("state") or "UNKNOWN"),
            "entry_timing_passed": int(progress.get("passed") or confirmation.get("passed") or 0),
            "entry_timing_total": int(progress.get("total") or confirmation.get("total_checks") or 7),
            "market_regime": regime.value,
            "relative_strength_market_pct": relative_market,
            "audit_context": {
                "stock_history_start_date": stock_history_start,
                "stock_history_end_date": stock_history_end,
                "index_history_end_date": index_history_end,
                "market_regime_source_date": signal_date if index_row is not None else None,
                "future_data_used": future_data_used,
                "signal_close": float(strategy_input.current_price),
                "signal_support": strategy_input.support_price,
                "signal_ma20": strategy_input.ma20,
                "signal_rsi14": strategy_input.rsi14,
                "signal_atr_pct": strategy_input.atr_pct,
                "technical_low20": technical.get("low20"),
                "technical_high20": technical.get("high20"),
            },
        }

    @staticmethod
    def _valid_anchor_below(entry_price: float, value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if 0 < number < entry_price else None

    def _build_risk_plan_for_policy(
        self,
        *,
        signal: dict[str, Any],
        entry_price: float,
        risk_policy: str,
        strategy: StrategyName = StrategyName.PULLBACK,
    ) -> tuple[Any, dict[str, Any]]:
        """Build a Risk Plan for a controlled policy experiment.

        Production RiskEngine rules are not mutated. The nearest-anchor scenario
        only changes the input used for this backtest research cohort.
        """

        base_input: StrategyInput = signal["strategy_input"]
        entry_input = replace(base_input, current_price=entry_price)

        def build(data: StrategyInput) -> Any:
            return self.risk.build_plan(
                data=data,
                strategy=strategy,
                technical=signal["technical"],
                risk_gate_active=bool(signal["risk_gate_active"]),
                risk_gate_reasons=list(signal["risk_gate_reasons"]),
                basis="BACKTEST_NEXT_OPEN",
            )

        baseline_plan = build(entry_input)
        selected_plan = baseline_plan
        anchor_changed = False

        if risk_policy == POLICY_NEAREST_VALID_ANCHOR:
            support = self._valid_anchor_below(entry_price, entry_input.support_price)
            ma20 = self._valid_anchor_below(entry_price, entry_input.ma20)
            # Current Pullback RiskEngine prioritizes support whenever it exists.
            # The research scenario changes only cases where MA20 is a valid and
            # strictly closer downside anchor.
            if support is not None and ma20 is not None and ma20 > support:
                alternative_input = replace(entry_input, support_price=None)
                alternative_plan = build(alternative_input)
                if (
                    not alternative_plan.reference_only
                    and alternative_plan.invalidation_price is not None
                    and alternative_plan.target1_price is not None
                ):
                    selected_plan = alternative_plan
                    anchor_changed = (
                        alternative_plan.structural_anchor != baseline_plan.structural_anchor
                        or alternative_plan.structural_anchor_label != baseline_plan.structural_anchor_label
                    )

        baseline_stop_distance = None
        if baseline_plan.invalidation_price is not None:
            baseline_stop = float(baseline_plan.invalidation_price)
            if 0 < baseline_stop < entry_price:
                baseline_stop_distance = (entry_price - baseline_stop) / entry_price * 100.0

        selected_stop_distance = None
        if selected_plan.invalidation_price is not None:
            selected_stop = float(selected_plan.invalidation_price)
            if 0 < selected_stop < entry_price:
                selected_stop_distance = (entry_price - selected_stop) / entry_price * 100.0

        return selected_plan, {
            "policy_id": risk_policy,
            "anchor_changed": anchor_changed,
            "baseline_anchor": baseline_plan.structural_anchor,
            "baseline_anchor_label": baseline_plan.structural_anchor_label,
            "selected_anchor": selected_plan.structural_anchor,
            "selected_anchor_label": selected_plan.structural_anchor_label,
            "baseline_stop_distance_pct": None if baseline_stop_distance is None else round(baseline_stop_distance, 4),
            "selected_stop_distance_pct": None if selected_stop_distance is None else round(selected_stop_distance, 4),
            "baseline_status": baseline_plan.status.value,
            "selected_status": selected_plan.status.value,
        }

    def _simulate_trade(
        self,
        *,
        signal: dict[str, Any],
        stock_rows: list[dict[str, Any]],
        config: BacktestConfig,
        research_only: bool,
        risk_policy: str = POLICY_CURRENT,
        policy_meta: dict[str, Any] | None = None,
        strategy: StrategyName = StrategyName.PULLBACK,
    ) -> tuple[BacktestTrade | None, int | None]:
        signal_index = int(signal["signal_index"])
        entry_index = signal_index + 1
        if entry_index >= len(stock_rows):
            return None, None

        entry_row = stock_rows[entry_index]
        entry_price_raw = entry_row.get("open")
        if entry_price_raw is None or float(entry_price_raw) <= 0:
            return None, None
        entry_price = float(entry_price_raw)

        base_input: StrategyInput = signal["strategy_input"]
        plan, policy_trace = self._build_risk_plan_for_policy(
            signal=signal,
            entry_price=entry_price,
            risk_policy=risk_policy,
            strategy=strategy,
        )
        if policy_meta is not None:
            policy_meta.update(policy_trace)

        if plan.reference_only or plan.invalidation_price is None or plan.target1_price is None:
            if policy_meta is not None:
                policy_meta.update({"outcome": "UNUSABLE_RISK_PLAN", "blocked_reason": "REFERENCE_OR_MISSING_PLAN"})
            return None, None

        stop_price = float(plan.invalidation_price)
        target1 = float(plan.target1_price)
        target2 = None if plan.target2_price is None else float(plan.target2_price)
        if stop_price <= 0 or stop_price >= entry_price or target1 <= entry_price:
            if policy_meta is not None:
                policy_meta.update({"outcome": "UNUSABLE_RISK_PLAN", "blocked_reason": "INVALID_PRICE_GEOMETRY"})
            return None, None

        initial_stop_distance_pct = (entry_price - stop_price) / entry_price * 100.0
        if risk_policy == POLICY_BLOCK_ALL_CAUTION and plan.status.value == "CAUTION":
            if policy_meta is not None:
                policy_meta.update({"outcome": "BLOCKED_POLICY", "blocked_reason": "CAUTION", "selected_stop_distance_pct": round(initial_stop_distance_pct, 4)})
            return None, None
        if risk_policy == POLICY_BLOCK_WIDE_STOP and initial_stop_distance_pct >= WIDE_STOP_PCT:
            if policy_meta is not None:
                policy_meta.update({"outcome": "BLOCKED_POLICY", "blocked_reason": "WIDE_STOP", "selected_stop_distance_pct": round(initial_stop_distance_pct, 4)})
            return None, None

        signal_audit = signal.get("audit_context") or {}
        signal_close = float(base_input.current_price) if base_input.current_price is not None else None
        entry_gap_pct = (entry_price / signal_close - 1.0) * 100.0 if signal_close and signal_close > 0 else None
        atr_pct = float(base_input.atr_pct) if base_input.atr_pct is not None else None
        atr_value_at_entry = entry_price * atr_pct / 100.0 if atr_pct is not None and atr_pct > 0 else None
        structural_anchor = float(plan.structural_anchor) if plan.structural_anchor is not None else None
        anchor_distance_pct = (entry_price - structural_anchor) / entry_price * 100.0 if structural_anchor is not None else None
        atr_buffer_from_anchor_pct = (structural_anchor - stop_price) / entry_price * 100.0 if structural_anchor is not None else None
        buffer_factor = None
        if structural_anchor is not None and atr_value_at_entry is not None and atr_value_at_entry > 0:
            buffer_factor = (structural_anchor - stop_price) / atr_value_at_entry

        audit_flags: list[str] = []
        if initial_stop_distance_pct >= 12.0:
            audit_flags.append("WIDE_STOP")
        if plan.status.value == "CAUTION":
            audit_flags.append("CAUTION_RISK_PLAN")
        if plan.structure_rating == "불리함":
            audit_flags.append("UNFAVORABLE_RISK_STRUCTURE")
        if entry_gap_pct is not None and abs(entry_gap_pct) >= 10.0:
            audit_flags.append("LARGE_NEXT_OPEN_GAP")

        last_index = min(len(stock_rows) - 1, entry_index + config.max_holding_days - 1)
        exit_index = last_index
        exit_price: float | None = None
        exit_reason: str | None = None

        for row_index in range(entry_index, last_index + 1):
            row = stock_rows[row_index]
            day_open = row.get("open")
            day_high = row.get("high")
            day_low = row.get("low")

            # Gap handling uses the opening price because a stop/target cannot be
            # executed at a price that the market skipped over overnight.
            if row_index > entry_index and day_open is not None:
                open_f = float(day_open)
                if open_f <= stop_price:
                    exit_index, exit_price, exit_reason = row_index, open_f, "STOP_GAP"
                    break
                if open_f >= target1:
                    exit_index, exit_price, exit_reason = row_index, open_f, "TARGET_1_GAP"
                    break

            low_hit = day_low is not None and float(day_low) <= stop_price
            target_hit = day_high is not None and float(day_high) >= target1
            if low_hit and target_hit:
                # With daily OHLC the intraday order is unknowable. The approved
                # conservative policy assumes the stop was reached first.
                exit_index, exit_price, exit_reason = row_index, stop_price, "STOP_SAME_DAY_PRIORITY"
                break
            if low_hit:
                exit_index, exit_price, exit_reason = row_index, stop_price, "STOP"
                break
            if target_hit:
                exit_index, exit_price, exit_reason = row_index, target1, "TARGET_1"
                break

        if exit_price is None:
            final_row = stock_rows[last_index]
            close = final_row.get("close")
            if close is None:
                return None, None
            exit_price = float(close)
            exit_reason = (
                "TIME_EXIT"
                if last_index - entry_index + 1 >= config.max_holding_days
                else "END_OF_DATA"
            )

        gross_return = (exit_price / entry_price - 1.0) * 100.0
        net_return = gross_return - config.round_trip_cost_pct
        holding_days = exit_index - entry_index + 1
        exit_row = stock_rows[exit_index]
        next_open_verified = bool(
            entry_index == signal_index + 1
            and self._date(entry_row) > str(signal["signal_date"])
            and entry_row.get("open") is not None
            and abs(float(entry_row["open"]) - entry_price) < 1e-9
        )
        trade = BacktestTrade(
            signal_date=str(signal["signal_date"]),
            entry_date=self._date(stock_rows[entry_index]),
            entry_price=entry_price,
            exit_date=self._date(stock_rows[exit_index]),
            exit_price=exit_price,
            exit_reason=str(exit_reason),
            holding_days=holding_days,
            strategy_score=int(signal["strategy_score"]),
            entry_timing_passed=int(signal["entry_timing_passed"]),
            entry_timing_total=int(signal["entry_timing_total"]),
            entry_timing_state=str(signal["entry_timing_state"]),
            market_regime=str(signal["market_regime"]),
            stop_price=stop_price,
            target1_price=target1,
            target2_price=target2,
            gross_return_pct=gross_return,
            net_return_pct=net_return,
            risk_plan_status=plan.status.value,
            research_only=research_only,
            metadata={
                "strategy": strategy.value,
                "relative_strength_market_pct": signal.get("relative_strength_market_pct"),
                "target_policy": "TARGET_1_FULL_EXIT",
                "stop_policy": "RISK_ENGINE_INVALIDATION_PRICE",
                "risk_policy_experiment": risk_policy,
                "policy_trace": policy_trace,
                "audit": {
                    "signal_boundary": {
                        "stock_history_start_date": signal_audit.get("stock_history_start_date"),
                        "stock_history_end_date": signal_audit.get("stock_history_end_date"),
                        "index_history_end_date": signal_audit.get("index_history_end_date"),
                        "market_regime_source_date": signal_audit.get("market_regime_source_date"),
                        "future_data_used": bool(signal_audit.get("future_data_used")),
                    },
                    "entry": {
                        "signal_close": signal_close,
                        "entry_date": self._date(entry_row),
                        "entry_open": entry_price,
                        "gap_from_signal_close_pct": None if entry_gap_pct is None else round(entry_gap_pct, 4),
                        "next_trading_day_open_verified": next_open_verified,
                    },
                    "risk": {
                        "source": "RISK_ENGINE_INVALIDATION_PRICE",
                        "signal_support": signal_audit.get("signal_support"),
                        "signal_ma20": signal_audit.get("signal_ma20"),
                        "technical_low20": signal_audit.get("technical_low20"),
                        "structural_anchor": structural_anchor,
                        "structural_anchor_label": plan.structural_anchor_label,
                        "atr_pct": atr_pct,
                        "atr_value_at_entry": None if atr_value_at_entry is None else round(atr_value_at_entry, 4),
                        "buffer_factor": None if buffer_factor is None else round(buffer_factor, 4),
                        "formula": "구조적 기준 - (다음 거래일 진입가 기준 ATR × 전략별 buffer)",
                        "invalidation_price": stop_price,
                        "initial_stop_distance_pct": round(initial_stop_distance_pct, 4),
                        "anchor_distance_from_entry_pct": None if anchor_distance_pct is None else round(anchor_distance_pct, 4),
                        "atr_buffer_from_anchor_pct": None if atr_buffer_from_anchor_pct is None else round(atr_buffer_from_anchor_pct, 4),
                        "risk_plan_status": plan.status.value,
                        "reference_only": bool(plan.reference_only),
                        "structure_rating": plan.structure_rating,
                        "summary": plan.summary,
                        "warnings": list(plan.warnings),
                        "reasons": list(plan.reasons),
                    },
                    "execution": {
                        "exit_date": self._date(exit_row),
                        "exit_open": exit_row.get("open"),
                        "exit_high": exit_row.get("high"),
                        "exit_low": exit_row.get("low"),
                        "exit_close": exit_row.get("close"),
                        "exit_trigger": str(exit_reason),
                        "gross_formula": "(청산가 / 진입가 - 1) × 100",
                        "gross_return_pct": round(gross_return, 4),
                        "round_trip_cost_pct": config.round_trip_cost_pct,
                        "net_return_pct": round(net_return, 4),
                    },
                    "flags": audit_flags,
                },
            },
        )
        if policy_meta is not None:
            policy_meta.update({
                "outcome": "EXECUTED",
                "blocked_reason": None,
                "selected_stop_distance_pct": round(initial_stop_distance_pct, 4),
                "executed_risk_status": plan.status.value,
            })
        return trade, exit_index

    @staticmethod
    def _qualifies_actual_rule(signal: dict[str, Any], config: BacktestConfig) -> bool:
        if signal["entry_timing_state"] != "REBOUND_CONFIRMED":
            return False
        if not signal["strategy_eligible"] or int(signal["strategy_score"]) < config.minimum_strategy_score:
            return False
        if signal["risk_gate_active"]:
            return False
        return True

    def _simulate_risk_policy_scenario(
        self,
        *,
        signals: list[dict[str, Any]],
        stock_rows: list[dict[str, Any]],
        config: BacktestConfig,
        risk_policy: str,
    ) -> dict[str, Any]:
        trades: list[BacktestTrade] = []
        occupied_until = -1
        eligible_attempts = 0
        blocked_by_policy = 0
        unusable_risk_plan = 0
        anchor_changed_signals = 0
        anchor_changed_trades = 0
        blocked_reasons: dict[str, int] = {}

        for signal in signals:
            signal_index = int(signal["signal_index"])
            if signal_index <= occupied_until:
                continue
            if not self._qualifies_actual_rule(signal, config):
                continue

            eligible_attempts += 1
            policy_meta: dict[str, Any] = {}
            trade, exit_index = self._simulate_trade(
                signal=signal,
                stock_rows=stock_rows,
                config=config,
                research_only=True,
                risk_policy=risk_policy,
                policy_meta=policy_meta,
            )
            if bool(policy_meta.get("anchor_changed")):
                anchor_changed_signals += 1

            if trade is None or exit_index is None:
                outcome = str(policy_meta.get("outcome") or "UNUSABLE_RISK_PLAN")
                reason = str(policy_meta.get("blocked_reason") or "UNKNOWN")
                if outcome == "BLOCKED_POLICY":
                    blocked_by_policy += 1
                    blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
                else:
                    unusable_risk_plan += 1
                continue

            trades.append(trade)
            if bool(policy_meta.get("anchor_changed")):
                anchor_changed_trades += 1
            occupied_until = exit_index

        summary = summarize_trades(trades, config.initial_capital)
        summary["closed_trade_max_drawdown_pct"] = summary["max_drawdown_pct"]
        summary["max_drawdown_pct"] = self._mark_to_market_max_drawdown(
            trades=trades,
            stock_rows=stock_rows,
            initial_capital=config.initial_capital,
            round_trip_cost_pct=config.round_trip_cost_pct,
        )
        summary["max_drawdown_basis"] = "DAILY_CLOSE_MARK_TO_MARKET"

        caution_trades = sum(1 for trade in trades if trade.risk_plan_status == "CAUTION")
        wide_stop_trades = 0
        stop_distances: list[float] = []
        for trade in trades:
            audit = trade.metadata.get("audit") if isinstance(trade.metadata, dict) else None
            risk = audit.get("risk") if isinstance(audit, dict) and isinstance(audit.get("risk"), dict) else {}
            stop_distance = risk.get("initial_stop_distance_pct")
            if stop_distance is None and trade.entry_price > 0:
                stop_distance = (trade.entry_price - trade.stop_price) / trade.entry_price * 100.0
            try:
                distance_f = float(stop_distance)
            except (TypeError, ValueError):
                continue
            stop_distances.append(distance_f)
            if distance_f >= WIDE_STOP_PCT:
                wide_stop_trades += 1

        return {
            "id": risk_policy,
            "metrics": summary,
            "eligible_attempts": eligible_attempts,
            "blocked_by_policy": blocked_by_policy,
            "blocked_reasons": blocked_reasons,
            "unusable_risk_plan": unusable_risk_plan,
            "caution_trades": caution_trades,
            "wide_stop_trades": wide_stop_trades,
            "average_initial_stop_distance_pct": (
                None if not stop_distances else round(sum(stop_distances) / len(stop_distances), 3)
            ),
            "anchor_changed_signals": anchor_changed_signals,
            "anchor_changed_trades": anchor_changed_trades,
        }

    @classmethod
    def _mark_to_market_max_drawdown(
        cls,
        *,
        trades: list[BacktestTrade],
        stock_rows: list[dict[str, Any]],
        initial_capital: float,
        round_trip_cost_pct: float,
    ) -> float:
        """Daily-close equity MDD for the single-position/full-capital MVP.

        While a trade is open, the full configured round-trip cost is reserved in
        the mark-to-market value. On the exit date the actually realized net return
        is used, including intraday stop/target exits.
        """
        if not trades or initial_capital <= 0:
            return 0.0

        date_to_index = {cls._date(row): i for i, row in enumerate(stock_rows)}
        capital = float(initial_capital)
        peak = capital
        max_drawdown = 0.0

        for trade in sorted(trades, key=lambda item: item.entry_date):
            entry_index = date_to_index.get(trade.entry_date)
            exit_index = date_to_index.get(trade.exit_date)
            if entry_index is None or exit_index is None or exit_index < entry_index:
                continue

            base_capital = capital
            for row_index in range(entry_index, exit_index + 1):
                if row_index == exit_index:
                    equity = base_capital * max(0.0, 1.0 + trade.net_return_pct / 100.0)
                else:
                    close = stock_rows[row_index].get("close")
                    if close is None or trade.entry_price <= 0:
                        continue
                    mark_return_pct = (float(close) / trade.entry_price - 1.0) * 100.0 - round_trip_cost_pct
                    equity = base_capital * max(0.0, 1.0 + mark_return_pct / 100.0)

                peak = max(peak, equity)
                if peak > 0:
                    max_drawdown = min(max_drawdown, (equity / peak - 1.0) * 100.0)

            capital = base_capital * max(0.0, 1.0 + trade.net_return_pct / 100.0)

        return round(max_drawdown, 3)

    @staticmethod
    def _assessment(summary: dict[str, Any]) -> dict[str, str]:
        trades = int(summary.get("trades") or 0)
        expectancy = summary.get("expectancy_pct")
        if trades < 10:
            return {
                "status": "LOW_SAMPLE",
                "label": "표본 부족",
                "summary": "거래 수가 10회 미만이라 전략 유효성을 강하게 판단하지 않습니다.",
            }
        if expectancy is not None and float(expectancy) > 0:
            return {
                "status": "POSITIVE_SAMPLE",
                "label": "양(+)의 표본 성과",
                "summary": "선택 기간에서 비용 반영 거래당 평균 성과가 양수였습니다. 미래 수익을 보장하는 의미는 아닙니다.",
            }
        return {
            "status": "WEAK_SAMPLE",
            "label": "재검토 필요",
            "summary": "선택 기간에서 비용 반영 거래당 평균 성과가 양수로 확인되지 않았습니다.",
        }

    def run(
        self,
        *,
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
        config: BacktestConfig,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        actual_trade_simulator: Callable[..., tuple[BacktestTrade | None, int | None]] | None = None,
    ) -> dict[str, Any]:
        rows = sorted(stock_rows, key=self._date)
        indices = sorted(index_rows, key=self._date)
        start = config.start_date.replace("-", "")
        end = config.end_date.replace("-", "")

        target_indices = [
            i for i, row in enumerate(rows)
            if start <= self._date(row) <= end
        ]
        total_signal_days = len(target_indices)
        signals: list[dict[str, Any]] = []
        for position, i in enumerate(target_indices, start=1):
            snapshot = self._signal_snapshot(
                stock_rows=rows,
                index_rows=indices,
                index=i,
                config=config,
            )
            if snapshot is not None:
                signals.append(snapshot)
            if progress_callback is not None and (position == 1 or position % 5 == 0 or position == total_signal_days):
                progress_callback({
                    "stage": "strategy_calculation",
                    "message": "과거 거래일별 눌림목 신호 재현 중",
                    "current": position,
                    "total": max(total_signal_days, 1),
                    "details": {"signals_found": len(signals)},
                })

        if progress_callback is not None:
            progress_callback({
                "stage": "trade_simulation",
                "message": "진입·손절·목표가·보유기간 시뮬레이션 중",
                "current": 0,
                "total": max(len(signals), 1),
                "details": {"signals_found": len(signals)},
            })

        actual_trades: list[BacktestTrade] = []
        occupied_until = -1
        qualifying_signals = 0
        skipped_risk = 0
        for signal_position, signal in enumerate(signals, start=1):
            signal_index = int(signal["signal_index"])
            if progress_callback is not None and (signal_position == 1 or signal_position % 10 == 0 or signal_position == len(signals)):
                progress_callback({
                    "stage": "trade_simulation",
                    "message": "진입·손절·목표가·보유기간 시뮬레이션 중",
                    "current": signal_position,
                    "total": max(len(signals), 1),
                    "details": {"closed_trades": len(actual_trades)},
                })
            if signal_index <= occupied_until:
                continue
            if signal["entry_timing_state"] != "REBOUND_CONFIRMED":
                continue
            if not signal["strategy_eligible"] or int(signal["strategy_score"]) < config.minimum_strategy_score:
                continue
            if signal["risk_gate_active"]:
                continue
            qualifying_signals += 1
            if actual_trade_simulator is None:
                trade, exit_index = self._simulate_trade(
                    signal=signal,
                    stock_rows=rows,
                    config=config,
                    research_only=False,
                )
            else:
                trade, exit_index = actual_trade_simulator(
                    signal=signal,
                    stock_rows=rows,
                    config=config,
                )
            if trade is None or exit_index is None:
                skipped_risk += 1
                continue
            actual_trades.append(trade)
            occupied_until = exit_index

        research_by_entry_timing: list[dict[str, Any]] = []
        research_windows: dict[str, list[tuple[int, int]]] = {}
        for passed_count in range(3, 8):
            cohort_trades: list[BacktestTrade] = []
            cohort_occupied_until = -1
            cohort_signals = 0
            for signal in signals:
                signal_index = int(signal["signal_index"])
                if signal_index <= cohort_occupied_until:
                    continue
                if int(signal["entry_timing_total"]) != 7 or int(signal["entry_timing_passed"]) != passed_count:
                    continue
                if signal["entry_timing_state"] not in self.RESEARCH_STATES:
                    continue
                if not signal["strategy_eligible"] or int(signal["strategy_score"]) < config.minimum_strategy_score:
                    continue
                if signal["risk_gate_active"]:
                    continue
                cohort_signals += 1
                trade, exit_index = self._simulate_trade(
                    signal=signal,
                    stock_rows=rows,
                    config=config,
                    research_only=True,
                )
                if trade is None or exit_index is None:
                    continue
                cohort_trades.append(trade)
                cohort_occupied_until = exit_index
            cohort_label = f"{passed_count}/7"
            research_windows[cohort_label] = []
            row_index_by_date = {self._date(row): idx for idx, row in enumerate(rows)}
            for cohort_trade in cohort_trades:
                entry_i = row_index_by_date.get(cohort_trade.entry_date)
                exit_i = row_index_by_date.get(cohort_trade.exit_date)
                if entry_i is not None and exit_i is not None:
                    research_windows[cohort_label].append((entry_i, exit_i))
            research_by_entry_timing.append({
                "entry_timing": cohort_label,
                "signals": cohort_signals,
                **summarize_trades(cohort_trades, config.initial_capital),
            })

        research_overlap_pairs = 0
        cohort_labels = list(research_windows)
        for left_index, left_label in enumerate(cohort_labels):
            for right_label in cohort_labels[left_index + 1 :]:
                for left_start, left_end in research_windows[left_label]:
                    for right_start, right_end in research_windows[right_label]:
                        if max(left_start, right_start) <= min(left_end, right_end):
                            research_overlap_pairs += 1

        risk_policy_ids = [
            POLICY_CURRENT,
            POLICY_BLOCK_ALL_CAUTION,
            POLICY_BLOCK_WIDE_STOP,
            POLICY_NEAREST_VALID_ANCHOR,
        ]
        risk_policy_scenarios: list[dict[str, Any]] = []
        for policy_index, risk_policy in enumerate(risk_policy_ids, start=1):
            if progress_callback is not None:
                progress_callback({
                    "stage": "risk_policy_comparison",
                    "message": "Risk 정책 대안 비교 중",
                    "current": policy_index - 1,
                    "total": len(risk_policy_ids),
                    "details": {"policy": risk_policy},
                })
            risk_policy_scenarios.append(
                self._simulate_risk_policy_scenario(
                    signals=signals,
                    stock_rows=rows,
                    config=config,
                    risk_policy=risk_policy,
                )
            )
        risk_policy_comparison = build_risk_policy_comparison(risk_policy_scenarios)
        if progress_callback is not None:
            progress_callback({
                "stage": "risk_policy_comparison",
                "message": "Risk 정책 대안 비교 완료",
                "current": len(risk_policy_ids),
                "total": len(risk_policy_ids),
                "details": {
                    "candidate": (risk_policy_comparison.get("next_validation_candidate") or {}).get("policy_id"),
                },
            })

        if progress_callback is not None:
            progress_callback({
                "stage": "metrics",
                "message": "성과 지표 집계 중",
                "current": 0,
                "total": 1,
                "details": {"closed_trades": len(actual_trades)},
            })

        summary = summarize_trades(actual_trades, config.initial_capital)
        summary["closed_trade_max_drawdown_pct"] = summary["max_drawdown_pct"]
        summary["max_drawdown_pct"] = self._mark_to_market_max_drawdown(
            trades=actual_trades,
            stock_rows=rows,
            initial_capital=config.initial_capital,
            round_trip_cost_pct=config.round_trip_cost_pct,
        )
        summary["max_drawdown_basis"] = "DAILY_CLOSE_MARK_TO_MARKET"
        by_score = grouped_trade_metrics(
            actual_trades,
            key_fn=lambda trade: score_bucket(trade.strategy_score),
            initial_capital=config.initial_capital,
        )
        score_order = {"55-69": 0, "70-79": 1, "80-89": 2, "90-100": 3}
        by_score.sort(key=lambda row: score_order.get(str(row["key"]), 99))
        by_regime = grouped_trade_metrics(
            actual_trades,
            key_fn=lambda trade: trade.market_regime,
            initial_capital=config.initial_capital,
        )
        by_regime.sort(key=lambda row: str(row["key"]))

        signal_boundary_violations = sum(
            1
            for signal in signals
            if bool((signal.get("audit_context") or {}).get("future_data_used"))
        )

        result = {
            "version": "0.19",
            "strategy": "pullback",
            "code": config.code,
            "market": config.market,
            "period": {"start": config.start_date, "end": config.end_date},
            "config": {
                "initial_capital": config.initial_capital,
                "max_holding_days": config.max_holding_days,
                "round_trip_cost_pct": config.round_trip_cost_pct,
                "minimum_strategy_score": config.minimum_strategy_score,
                "entry_policy": "REBOUND_CONFIRMED",
                "entry_price_policy": "NEXT_TRADING_DAY_OPEN",
                "same_day_stop_target_policy": "STOP_FIRST",
                "stop_policy": "RISK_ENGINE_INVALIDATION_PRICE",
                "target_policy": "TARGET_1_FULL_EXIT",
                "overlapping_positions": False,
                "position_sizing": "FULL_CAPITAL_SINGLE_POSITION",
            },
            "summary": summary,
            "assessment": self._assessment(summary),
            "diagnostics": {
                "stock_rows": len(rows),
                "index_rows": len(indices),
                "evaluated_signal_days": len(signals),
                "qualifying_rebound_signals": qualifying_signals,
                "skipped_for_unusable_risk_plan": skipped_risk,
            },
            "score_performance": by_score,
            "entry_timing_research": research_by_entry_timing,
            "market_regime_performance": by_regime,
            "risk_policy_comparison": risk_policy_comparison,
            "trades": [trade.to_dict() for trade in actual_trades],
            "methodology": {
                "future_data_leakage": "신호일 계산에는 해당 거래일까지의 KRX 데이터만 전달합니다.",
                "entry": "신호는 장 마감 후 확정되며 실제 가상 진입은 다음 거래일 시가로 처리합니다.",
                "same_day_ambiguity": "일봉에서 손절과 목표가가 같은 날 모두 닿으면 순서를 알 수 없어 보수적으로 손절 우선 처리합니다.",
                "holding_period": "최대 보유기간은 사용자가 선택하며 진입일을 1거래일째로 계산합니다.",
                "cost": "Net 성과는 사용자가 입력한 왕복 비용률을 Gross 수익률에서 차감한 단순 가정입니다.",
                "fundamental": "v0.19.1 눌림목 전략 백테스트는 OpenDART/재무/공시 데이터를 진입판정에 사용하지 않습니다.",
                "relative_strength": "KRX 종목과 대표 시장지수의 같은 거래일 데이터로 시장 상대강도는 재현합니다. 업종 상대강도는 제외합니다.",
                "target": "부분청산 규칙을 임의로 만들지 않기 위해 MVP는 Risk Engine의 1차 목표가 도달 시 전량 가상청산합니다. 2차 목표가는 참고값으로만 저장합니다.",
                "drawdown": "전체 최대낙폭은 단일 포지션·전액 가정의 일별 종가 평가자산 기준입니다. 포지션 보유 중에는 입력한 왕복 비용률을 미리 반영하고, 청산일에는 실제 Stop/Target/기간종료 결과를 반영합니다.",
                "score_note": "전략 점수와 Entry Timing 조건 수는 상승확률이 아닙니다.",
                "research_note": "3/7~7/7 비교는 조건 개수별 가상 연구 코호트이며 실제 기본 진입 규칙과 분리해 표시합니다.",
                "risk_policy_research": f"현재 정책, CAUTION 전체 제외, 기존 {WIDE_STOP_PCT:.0f}% 이상 손절거리 제외, 주요 지지와 MA20 중 더 가까운 유효 지지 사용을 같은 신호 데이터로 별도 비교하며 실제 Risk 규칙은 자동 변경하지 않습니다.",
            },
        }
        result["accuracy_audit"] = build_accuracy_audit(
            result,
            config,
            signal_boundary_violations=signal_boundary_violations,
            research_overlap_pairs=research_overlap_pairs,
        )
        return result
