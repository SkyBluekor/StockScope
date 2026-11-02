"""STRATEGY-01: offline, read-only study of the frozen 10 strategies.

Never fetch market data, initialize a writable market store, or activate policies.
This output is retrospective evidence, not a production or horizon decision.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from collections import defaultdict
from contextlib import closing
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "backend"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app.backtest.models import BacktestConfig
from app.backtest.multi_strategy import MultiStrategyBacktestEngine, SUPPORTED_STRATEGIES
from app.backtest.production_exit_policy import ProductionExitPolicyEngine, ProductionExitPolicyRegistry
from app.horizon import EXPLICIT_HORIZONS, resolve_horizon_context
from tools.data.common import market_db_path

MARKETS = ("KOSPI", "KOSDAQ")
CONTRACT = "STOCKSCOPE_STRATEGY01_READONLY_V1"


class ReadOnlyExitRegistry(ProductionExitPolicyRegistry):
    def ensure_mapping(self):
        # Parent implementation may bootstrap a production file from a report.
        return self.load_mapping()


def open_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def common_sessions(conn, end: str, total: int) -> list[str]:
    rows = conn.execute(
        """SELECT bas_dd FROM day_status
           WHERE bas_dd<=? AND market IN ('KOSPI','KOSDAQ')
             AND kind IN ('stock','index') AND status='data'
           GROUP BY bas_dd
           HAVING COUNT(DISTINCT market || ':' || kind)=4
           ORDER BY bas_dd DESC LIMIT ?""", (end, total)
    ).fetchall()
    return sorted(str(row["bas_dd"]) for row in rows)


def checked_rows(conn, *, market: str, days: list[str],
                 code: str | None = None) -> list[dict] | None:
    if not days:
        return None
    table = "stock_daily" if code else "main_index_daily"
    placeholders = ",".join("?" for _ in days)
    query = f"SELECT bas_dd,row_json FROM {table} WHERE market=? AND bas_dd IN ({placeholders})"
    params = [market, *days]
    if code:
        query += " AND stock_code=?"
        params.append(code)
    query += " ORDER BY bas_dd"
    raw = conn.execute(query, params).fetchall()
    if [r["bas_dd"] for r in raw] != days:
        return None
    result = []
    for raw_row in raw:
        try:
            row = json.loads(raw_row["row_json"])
            dd = str(row["date"]).replace("-", "")
            if dd != raw_row["bas_dd"]:
                return None
            date.fromisoformat(dd[:4] + "-" + dd[4:6] + "-" + dd[6:])
            keys = ("open", "high", "low", "close", "trade_value") if code else ("close", "change_rate")
            values = {k: float(row[k]) for k in keys}
            if any(not math.isfinite(v) for v in values.values()) or values["close"] <= 0:
                return None
            if code and (values["open"] <= 0 or values["low"] <= 0
                         or values["low"] > min(values["open"], values["close"])
                         or values["high"] < max(values["open"], values["close"])
                         or values["trade_value"] < 0):
                return None
        except (ValueError, TypeError, KeyError, OverflowError):
            return None
        result.append(row)
    return result


def candidates(conn, market: str, days: list[str], limit: int) -> list[str]:
    placeholders = ",".join("?" for _ in days)
    rows = conn.execute(
        f"""SELECT stock_code,COUNT(*) n FROM stock_daily
            WHERE market=? AND bas_dd IN ({placeholders})
            GROUP BY stock_code ORDER BY n DESC,stock_code ASC LIMIT ?""",
        [market, *days, max(100, limit * 15)],
    ).fetchall()
    return [str(r["stock_code"]) for r in rows]


def _summary(trades: list[dict]) -> dict:
    returns = [float(t["net_return_pct"]) for t in trades]
    winners = [x for x in returns if x > 0]
    losses = [x for x in returns if x < 0]
    return {
        "closed_trades": len(returns),
        "win_rate_pct": round(len(winners) / len(returns) * 100, 3) if returns else None,
        "expectancy_pct": round(statistics.fmean(returns), 3) if returns else None,
        "median_net_return_pct": round(statistics.median(returns), 3) if returns else None,
        "profit_factor": round(sum(winners) / abs(sum(losses)), 3) if losses else None,
        "mean_holding_days": round(statistics.fmean(float(t["holding_days"]) for t in trades), 2) if trades else None,
    }


def study(conn, *, end: str, days: int = 40, warmup: int = 120,
          per_market: int = 2, cost: float = 0.3, max_hold: int = 20,
          check_only: bool = False, market: str = "ALL", ticker: str | None = None) -> dict:
    if not 20 <= days <= 240 or not 120 <= warmup <= 300 or not 1 <= per_market <= 10:
        raise ValueError("days=20..240, warmup=120..300, per-market=1..10")
    if not 1 <= max_hold <= 120 or not math.isfinite(cost) or not 0 <= cost <= 5:
        raise ValueError("max-holding-days=1..120, cost-pct=0..5")
    if ticker and (market == "ALL" or len(ticker) != 6 or not ticker.isdecimal()):
        raise ValueError("--ticker requires one market and six numeric digits")
    common = common_sessions(conn, end, days + warmup)
    result = {
        "contract": CONTRACT, "status": "DATA_INSUFFICIENT", "reason": None,
        "source": "EXISTING_KRX_DB_ONLY", "end": end,
        "required_common_sessions": days + warmup, "available_common_sessions": len(common),
        "assumptions": {"warmup_sessions": warmup, "evaluation_sessions": days,
                        "round_trip_cost_pct_assumed": cost,
                        "max_holding_days_research_only": max_hold,
                        "candidate_selection": "EX_POST_COVERAGE_BIASED",
                        "entry": "NEXT_TRADING_DAY_OPEN",
                        "same_day_stop_target": "STOP_FIRST_CONSERVATIVE",
                        "source_asof": "KRX_EOD_DATE_ONLY_NOT_PIT_VERIFIED"},
        "horizons": {h: resolve_horizon_context(h).to_dict() for h in EXPLICIT_HORIZONS},
        "production_decision_approved": False, "horizon_policy_approved": False,
        "network_requests": 0, "db_writes": 0, "policy_activation": False,
    }
    if len(common) < days + warmup:
        result["reason"] = "INSUFFICIENT_COMMON_WARMUP_AND_EVALUATION_SESSIONS"
        return result
    start, final = common[warmup], common[-1]
    result["window"] = {"warmup_start": common[0], "evaluation_start": start,
                        "evaluation_end": final}
    partial = conn.execute(
        "SELECT DISTINCT bas_dd FROM day_status WHERE bas_dd>=? AND bas_dd<=?",
        (common[0], final),
    ).fetchall()
    gap = sorted({r["bas_dd"] for r in partial} - set(common))
    if gap:
        result["reason"] = "PARTIAL_KRX_MARKET_DAYS"
        result["partial_dates_sample"] = gap[:10]
        return result
    selected = []
    excluded = []
    for m in MARKETS if market == "ALL" else (market,):
        index = checked_rows(conn, market=m, days=common)
        if index is None:
            excluded.append({"market": m, "reason": "INDEX_INCOMPLETE"})
            continue
        pool = [ticker] if ticker else candidates(conn, m, common, per_market)
        for code in pool:
            if sum(x["market"] == m for x in selected) >= per_market:
                break
            stock = checked_rows(conn, market=m, days=common, code=code)
            if stock is None:
                excluded.append({"market": m, "code": code, "reason": "STOCK_INCOMPLETE"})
                continue
            selected.append({"market": m, "code": code, "stock": stock, "index": index})
    result["sample"] = {
        "selected": [{"market": x["market"], "code": x["code"]} for x in selected],
        "exclusions": excluded[:20], "selection_is_population_representative": False,
    }
    if not selected:
        result["reason"] = "NO_COMPLETE_SYMBOL_SAMPLE"
        return result
    if check_only:
        result["status"] = "READY_TO_RESEARCH"
        return result
    engine = MultiStrategyBacktestEngine()
    engine.production_exit = ProductionExitPolicyEngine(engine.base, ReadOnlyExitRegistry())
    registry = engine.production_exit.registry
    result["exit_policy_cache_token"] = registry.cache_token()
    result["exit_mapping_present"] = registry.load_mapping() is not None
    by_strategy = defaultdict(list)
    evaluated = []
    split = common[warmup + days // 2 - 1]
    for item in selected:
        cfg = BacktestConfig(
            code=item["code"], market=item["market"],
            start_date=date.fromisoformat(start[:4] + "-" + start[4:6] + "-" + start[6:]).isoformat(),
            end_date=date.fromisoformat(final[:4] + "-" + final[4:6] + "-" + final[6:]).isoformat(),
            round_trip_cost_pct=cost, max_holding_days=max_hold,
        )
        snapshots = []
        for i in range(warmup, len(common)):
            snapshot = engine.base._signal_snapshot(
                stock_rows=item["stock"], index_rows=item["index"], index=i, config=cfg
            )
            if snapshot is not None:
                if (snapshot.get("audit_context") or {}).get("future_data_used"):
                    raise ValueError("FUTURE_FEATURE_USED")
                snapshots.append(snapshot)
        if len(snapshots) < 2:
            excluded.append({"market": item["market"], "code": item["code"],
                             "reason": "NO_SIGNAL_SNAPSHOTS"})
            continue
        evaluated.append({"market": item["market"], "code": item["code"],
                          "signal_snapshots": len(snapshots)})
        for strategy in SUPPORTED_STRATEGIES:
            row = engine._run_strategy(
                strategy=strategy, snapshots=snapshots,
                stock_rows=item["stock"], config=cfg, include_trade_history=True,
            )
            by_strategy[strategy.value].append((item["market"], row))
    result["sample"]["evaluated"] = evaluated
    result["sample"]["markets_evaluated"] = sorted({x["market"] for x in evaluated})
    result["sample"]["both_markets_covered"] = {x["market"] for x in evaluated} == set(MARKETS)
    result["sample"]["exclusions"] = excluded[:20]
    if not evaluated:
        result["reason"] = "NO_EVALUABLE_STOCK"
        return result
    output = []
    for strategy in SUPPORTED_STRATEGIES:
        records = by_strategy[strategy.value]
        trades = [(m, t) for m, row in records for t in row["trade_history"]]
        closed = [(m, t) for m, t in trades if t["exit_reason"] != "END_OF_DATA"]
        earlier = [t for _, t in closed if str(t["exit_date"]).replace("-", "") <= split]
        later = [t for _, t in closed if str(t["entry_date"]).replace("-", "") > split]
        output.append({
            "strategy": strategy.value,
            "status": (
                "NOT_EVALUABLE" if not closed
                else "INSUFFICIENT_TRADES" if len(closed) < 5
                else "DESCRIPTIVE_ONLY"
            ),
            "exit_policies_used": sorted({r["exit_policy"]["policy_id"] for _, r in records}),
            "max_single_stock_consecutive_losses": max(
                (int(r["historical_metrics"]["max_consecutive_losses"])
                 for _, r in records), default=0,
            ),
            "signals": sum(int(r["signal_count"]) for _, r in records),
            "risk_blocked_signals": sum(int(r["risk_blocked_signals"]) for _, r in records),
            "simulated_trades": len(trades),
            "end_of_data_censored": len(trades) - len(closed),
            "closed_metrics": _summary([t for _, t in closed]),
            "by_market": {m: _summary([t for market_name, t in closed if market_name == m])
                          for m in MARKETS},
            "worst_single_stock_engine_mtm_mdd_pct": (
                min(float(r["historical_metrics"]["max_drawdown_pct"]) for _, r in records)
                if records else None
            ),
            "mdd_caution": "ENGINE_MTM_INCLUDES_OPEN_END_OF_DATA_NOT_PORTFOLIO_MDD",
            "temporal_split": {
                "split_date": split,
                "earlier_fully_closed": _summary(earlier),
                "later_entered": _summary(later),
                "cross_boundary_excluded": len(closed) - len(earlier) - len(later),
                "status": "DESCRIPTIVE_NOT_OOS",
            },
        })
    result["status"] = "RESEARCH_DESCRIPTIVE_ONLY"
    result["reason"] = "PIT_AND_INDEPENDENT_OUT_OF_SAMPLE_UNVERIFIED"
    result["strategy_results"] = output
    result["limitations"] = [
        "EX_POST_COVERAGE_SURVIVORSHIP_SELECTION",
        "SOURCE_EOD_AVAILABILITY_NOT_HISTORICALLY_VERIFIED",
        "END_OF_DATA_EXCLUDED_FROM_CLOSED_TRADES",
        "WORST_SINGLE_STOCK_MDD_NOT_PORTFOLIO_DRAWDOWN",
        "TIME_SPLIT_IS_NOT_INDEPENDENT_OOS",
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline read-only STRATEGY-01 existing ten strategies")
    parser.add_argument("--end", default="2026-10-30", help="YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=40)
    parser.add_argument("--warmup", type=int, default=120)
    parser.add_argument("--per-market", type=int, default=2)
    parser.add_argument("--market", choices=("ALL", *MARKETS), default="ALL")
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--cost-pct", type=float, default=0.3)
    parser.add_argument("--max-holding-days", type=int, default=20)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        date.fromisoformat(args.end)
        with closing(open_readonly(market_db_path())) as conn:
            report = study(conn, end=args.end.replace("-", ""), days=args.days,
                           warmup=args.warmup, per_market=args.per_market,
                           cost=args.cost_pct, max_hold=args.max_holding_days,
                           check_only=args.check_only, market=args.market, ticker=args.ticker)
    except (ValueError, FileNotFoundError, sqlite3.Error) as exc:
        print(json.dumps({"contract": CONTRACT, "status": "UNAVAILABLE",
                          "reason": type(exc).__name__,
                          "detail": str(exc) if isinstance(exc, ValueError) else None,
                          "network_requests": 0, "db_writes": 0}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"READY_TO_RESEARCH", "RESEARCH_DESCRIPTIVE_ONLY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
