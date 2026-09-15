from __future__ import annotations

from statistics import fmean
from typing import Any

from app.backtest.exit_policy_catalog import ExitPolicySpec
from app.backtest.models import BacktestConfig, BacktestTrade
from app.backtest.policy_lab import POLICY_CURRENT
from app.strategy.models import StrategyName


class ExitPolicySimulator:
    """Shared Target2 -> profit-protection simulator used by research and production.

    The protection line is evaluated on confirmed daily close data. The line that
    existed before today's bar is checked first; today's data may only raise the line
    for the next trading day. This keeps research and production backtests free of
    same-candle look-ahead.
    """

    def __init__(self, base: Any) -> None:
        self.base = base

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

    def protection_candidate(
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
    def trade_path_metrics(
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
        giveback_ratio = None if peak_return <= 0 else giveback_points / peak_return * 100.0
        return {
            "peak_close": round(peak_close, 4),
            "peak_return_pct": round(peak_return, 4),
            "profit_giveback_pct_points": round(giveback_points, 4),
            "profit_giveback_of_peak_pct": None if giveback_ratio is None else round(giveback_ratio, 4),
        }

    def simulate_profit_protection_trade(
        self,
        *,
        signal: dict[str, Any],
        stock_rows: list[dict[str, Any]],
        config: BacktestConfig,
        strategy: StrategyName,
        policy: ExitPolicySpec,
        post_target2_days: int,
        extend_after_target2: bool,
        research_only: bool,
        metadata_key: str,
        metadata_version: str,
        horizon_exit_reason: str,
    ) -> tuple[BacktestTrade | None, int | None]:
        signal_index = int(signal["signal_index"])
        entry_index = signal_index + 1
        if entry_index >= len(stock_rows):
            return None, None

        entry_open = self._number(stock_rows[entry_index].get("open"))
        if entry_open is None or entry_open <= 0:
            return None, None
        entry_price = float(entry_open)

        plan, _ = self.base._build_risk_plan_for_policy(  # noqa: SLF001
            signal=signal,
            entry_price=entry_price,
            risk_policy=POLICY_CURRENT,
            strategy=strategy,
        )
        if plan.reference_only or plan.invalidation_price is None or plan.target1_price is None or plan.target2_price is None:
            return None, None

        stop_price = float(plan.invalidation_price)
        target1 = float(plan.target1_price)
        target2 = float(plan.target2_price)
        if stop_price <= 0 or stop_price >= entry_price or target1 <= entry_price or target2 <= target1:
            return None, None

        pre_target_limit = min(len(stock_rows) - 1, entry_index + config.max_holding_days - 1)
        target1_reached = False
        target2_reached = False
        target2_index: int | None = None
        protection_price = stop_price
        final_limit = pre_target_limit
        exit_index: int | None = None
        exit_price: float | None = None
        exit_reason: str | None = None
        last_protection_source: float | None = None

        row_index = entry_index
        while row_index <= final_limit:
            row = stock_rows[row_index]
            day_open = self._number(row.get("open"))
            day_high = self._number(row.get("high"))
            day_low = self._number(row.get("low"))
            day_close = self._number(row.get("close"))

            if row_index > entry_index and day_open is not None and day_open <= stop_price:
                exit_index, exit_price, exit_reason = row_index, day_open, "STOP_GAP"
                break

            stop_hit = day_low is not None and day_low <= stop_price
            target2_hit = (day_open is not None and day_open >= target2) or (day_high is not None and day_high >= target2)
            if stop_hit and target2_hit and not target2_reached:
                exit_index, exit_price, exit_reason = row_index, stop_price, "STOP_SAME_DAY_PRIORITY"
                break
            if stop_hit:
                exit_index, exit_price, exit_reason = row_index, stop_price, "STOP"
                break

            if (day_open is not None and day_open >= target1) or (day_high is not None and day_high >= target1):
                target1_reached = True

            if not target2_reached and target2_hit:
                target2_reached = True
                target1_reached = True
                target2_index = row_index
                source = self.protection_candidate(
                    policy=policy,
                    rows=stock_rows,
                    end_index=row_index,
                    entry_index=entry_index,
                    target2_index=target2_index,
                )
                if source is not None and source > 0:
                    protection_price = max(protection_price, source)
                    last_protection_source = source
                if extend_after_target2:
                    final_limit = min(len(stock_rows) - 1, target2_index + post_target2_days)
                else:
                    final_limit = pre_target_limit
                    if row_index >= final_limit:
                        if day_close is None:
                            return None, None
                        exit_index, exit_price, exit_reason = row_index, day_close, "HARD_MAX_HOLD_EXIT"
                        break
                row_index += 1
                continue

            if target2_reached:
                # Check the line that existed before today's completed bar first.
                if day_close is not None and day_close < protection_price:
                    exit_index, exit_price, exit_reason = row_index, day_close, "TRAILING_CLOSE_EXIT"
                    break

                assert target2_index is not None
                source = self.protection_candidate(
                    policy=policy,
                    rows=stock_rows,
                    end_index=row_index,
                    entry_index=entry_index,
                    target2_index=target2_index,
                )
                if source is not None and source > 0:
                    protection_price = max(protection_price, source)
                    last_protection_source = source

                if row_index >= final_limit:
                    if day_close is None:
                        return None, None
                    exit_index, exit_price, exit_reason = (
                        row_index,
                        day_close,
                        horizon_exit_reason if extend_after_target2 else "HARD_MAX_HOLD_EXIT",
                    )
                    break
            elif row_index >= pre_target_limit:
                if day_close is None:
                    return None, None
                exit_index, exit_price, exit_reason = row_index, day_close, "TIME_EXIT_PRE_TARGET2"
                break

            row_index += 1

        if exit_index is None or exit_price is None or exit_reason is None:
            fallback_index = min(final_limit, len(stock_rows) - 1)
            close = self._number(stock_rows[fallback_index].get("close"))
            if close is None:
                return None, None
            exit_index, exit_price, exit_reason = fallback_index, close, "END_OF_DATA"

        gross_return = (exit_price / entry_price - 1.0) * 100.0
        net_return = gross_return - config.round_trip_cost_pct
        holding_days = exit_index - entry_index + 1
        path = self.trade_path_metrics(
            rows=stock_rows,
            entry_index=entry_index,
            exit_index=exit_index,
            entry_price=entry_price,
            exit_price=exit_price,
        )
        trade = BacktestTrade(
            signal_date=str(signal["signal_date"]),
            entry_date=self.base._date(stock_rows[entry_index]),
            entry_price=entry_price,
            exit_date=self.base._date(stock_rows[exit_index]),
            exit_price=exit_price,
            exit_reason=exit_reason,
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
                metadata_key: {
                    "version": metadata_version,
                    "policy_id": policy.id,
                    "policy_family": policy.family,
                    "target1_reached": target1_reached,
                    "target2_reached": target2_reached,
                    "target2_date": None if target2_index is None else self.base._date(stock_rows[target2_index]),
                    "trailing_activated": target2_reached,
                    "final_protection_price": round(protection_price, 4),
                    "last_protection_source": None if last_protection_source is None else round(last_protection_source, 4),
                    "protection_never_decreases": True,
                    "exit_basis": policy.exit_basis,
                    "post_target2_holding_policy": "TRAILING_HORIZON_AFTER_TARGET2" if extend_after_target2 else "HARD_MAX_HOLD",
                    **path,
                },
            },
        )
        return trade, exit_index
