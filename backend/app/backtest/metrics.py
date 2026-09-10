from __future__ import annotations

from collections import defaultdict
from statistics import fmean, median
from typing import Any, Iterable

from app.backtest.models import BacktestTrade


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def summarize_trades(trades: list[BacktestTrade], initial_capital: float) -> dict[str, Any]:
    if not trades:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": None,
            "average_gross_return_pct": None,
            "average_net_return_pct": None,
            "median_net_return_pct": None,
            "average_win_pct": None,
            "average_loss_pct": None,
            "expectancy_pct": None,
            "profit_factor": None,
            "average_holding_days": None,
            "max_consecutive_losses": 0,
            "max_drawdown_pct": 0.0,
            "initial_capital": round(initial_capital, 2),
            "final_capital": round(initial_capital, 2),
            "total_net_return_pct": 0.0,
        }

    net_returns = [trade.net_return_pct for trade in trades]
    gross_returns = [trade.gross_return_pct for trade in trades]
    winners = [value for value in net_returns if value > 0]
    losers = [value for value in net_returns if value < 0]

    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    profit_factor = None if gross_loss == 0 else gross_profit / gross_loss

    capital = float(initial_capital)
    peak = capital
    max_drawdown = 0.0
    max_loss_streak = 0
    current_loss_streak = 0
    for value in net_returns:
        capital *= max(0.0, 1.0 + value / 100.0)
        peak = max(peak, capital)
        drawdown = 0.0 if peak <= 0 else (capital / peak - 1.0) * 100.0
        max_drawdown = min(max_drawdown, drawdown)
        if value < 0:
            current_loss_streak += 1
            max_loss_streak = max(max_loss_streak, current_loss_streak)
        else:
            current_loss_streak = 0

    return {
        "trades": len(trades),
        "wins": len(winners),
        "losses": len(losers),
        "win_rate_pct": _round(len(winners) / len(trades) * 100.0),
        "average_gross_return_pct": _round(fmean(gross_returns)),
        "average_net_return_pct": _round(fmean(net_returns)),
        "median_net_return_pct": _round(median(net_returns)),
        "average_win_pct": _round(fmean(winners)) if winners else None,
        "average_loss_pct": _round(fmean(losers)) if losers else None,
        "expectancy_pct": _round(fmean(net_returns)),
        "profit_factor": _round(profit_factor),
        "average_holding_days": _round(fmean(trade.holding_days for trade in trades), 2),
        "max_consecutive_losses": max_loss_streak,
        "max_drawdown_pct": _round(max_drawdown),
        "initial_capital": round(initial_capital, 2),
        "final_capital": round(capital, 2),
        "total_net_return_pct": _round((capital / initial_capital - 1.0) * 100.0) if initial_capital > 0 else None,
    }


def grouped_trade_metrics(
    trades: Iterable[BacktestTrade],
    *,
    key_fn,
    initial_capital: float = 1_000_000.0,
) -> list[dict[str, Any]]:
    groups: dict[str, list[BacktestTrade]] = defaultdict(list)
    for trade in trades:
        groups[str(key_fn(trade))].append(trade)
    rows: list[dict[str, Any]] = []
    for key, grouped in groups.items():
        summary = summarize_trades(grouped, initial_capital)
        rows.append({"key": key, **summary})
    return rows


def score_bucket(score: int) -> str:
    if score >= 90:
        return "90-100"
    if score >= 80:
        return "80-89"
    if score >= 70:
        return "70-79"
    return "55-69"
