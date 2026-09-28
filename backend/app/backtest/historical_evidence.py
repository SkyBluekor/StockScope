from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.backtest.models import BacktestConfig
from app.backtest.multi_strategy import MultiStrategyBacktestEngine
from app.backtest.target1_audit import build_historical_target1_audit
from app.strategy.models import StrategyName


EVIDENCE_YEARS = 3
MIN_SAMPLE_FOR_EVALUATION = 10
WARMUP_TRADING_ROWS = 120
MAX_END_LAG_DAYS = 10


def validation_start_for_years(validation_end: date, years: int = EVIDENCE_YEARS) -> date:
    """Return the same calendar date N years earlier, handling Feb 29 safely."""
    target_year = validation_end.year - years
    try:
        return validation_end.replace(year=target_year)
    except ValueError:
        # Feb 29 -> Feb 28 in a non-leap target year.
        return validation_end.replace(year=target_year, month=2, day=28)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _compact(value: Any) -> str:
    return str(value or "").replace("-", "")


def _iso(compact: str) -> str:
    text = _compact(compact)
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) == 8 else text


def _date_value(row: dict[str, Any]) -> str:
    return _compact(row.get("date"))


def _period_rows(rows: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    return [row for row in rows if start <= _date_value(row) <= end]


def _warmup_rows(rows: list[dict[str, Any]], start: str) -> int:
    return sum(1 for row in rows if _date_value(row) < start)


def data_readiness(
    *,
    stock_rows: list[dict[str, Any]],
    index_rows: list[dict[str, Any]],
    validation_start: date,
    validation_end: date,
) -> dict[str, Any]:
    """Check whether the local Market Store can support a real three-year validation.

    No network fetch is performed here. The validation needs enough pre-period rows for
    MA120/technical warmup and data close to the requested end date. Missing history is
    reported to the UI instead of silently shrinking the requested three-year period.
    """

    start_key = validation_start.strftime("%Y%m%d")
    end_key = validation_end.strftime("%Y%m%d")
    stocks = sorted(stock_rows, key=_date_value)
    indices = sorted(index_rows, key=_date_value)
    stock_period = _period_rows(stocks, start_key, end_key)
    index_period = _period_rows(indices, start_key, end_key)

    stock_warmup = _warmup_rows(stocks, start_key)
    index_warmup = _warmup_rows(indices, start_key)
    stock_last = _date_value(stock_period[-1]) if stock_period else ""
    index_last = _date_value(index_period[-1]) if index_period else ""

    def end_is_recent(last_key: str) -> bool:
        if len(last_key) != 8:
            return False
        try:
            last = date(int(last_key[:4]), int(last_key[4:6]), int(last_key[6:8]))
        except ValueError:
            return False
        return (validation_end - last).days <= MAX_END_LAG_DAYS

    # Three calendar years are requested. Requiring the first available validation row
    # near the requested start avoids labeling a one-year local cache as a three-year test.
    def starts_near_requested(rows_in_period: list[dict[str, Any]]) -> bool:
        if not rows_in_period:
            return False
        first_key = _date_value(rows_in_period[0])
        try:
            first = date(int(first_key[:4]), int(first_key[4:6]), int(first_key[6:8]))
        except (ValueError, IndexError):
            return False
        return (first - validation_start).days <= 35

    reasons: list[str] = []
    if stock_warmup < WARMUP_TRADING_ROWS:
        reasons.append("종목 기술지표 워밍업 데이터 부족")
    if index_warmup < WARMUP_TRADING_ROWS:
        reasons.append("시장지수 기술지표 워밍업 데이터 부족")
    if not starts_near_requested(stock_period):
        reasons.append("종목 3년 시작구간 데이터 부족")
    if not starts_near_requested(index_period):
        reasons.append("시장지수 3년 시작구간 데이터 부족")
    if not end_is_recent(stock_last):
        reasons.append("종목 최신구간 데이터 부족")
    if not end_is_recent(index_last):
        reasons.append("시장지수 최신구간 데이터 부족")

    return {
        "ready": not reasons,
        "reasons": reasons,
        "validation_start": validation_start.isoformat(),
        "validation_end": validation_end.isoformat(),
        "stock_rows": len(stock_period),
        "index_rows": len(index_period),
        "stock_warmup_rows": stock_warmup,
        "index_warmup_rows": index_warmup,
    }


def _exit_counts(trades: list[dict[str, Any]]) -> dict[str, int]:
    stop = target = trailing = time_exit = other = 0
    for trade in trades:
        reason = str(trade.get("exit_reason") or "")
        if reason.startswith("STOP"):
            stop += 1
        elif reason.startswith("TARGET_1"):
            target += 1
        elif reason == "TRAILING_CLOSE_EXIT":
            trailing += 1
        elif reason in {"TIME_EXIT", "TIME_EXIT_PRE_TARGET2", "HARD_MAX_HOLD_EXIT", "PRODUCTION_HORIZON_EXIT"}:
            time_exit += 1
        else:
            other += 1
    return {"stop": stop, "target1": target, "trailing": trailing, "time_exit": time_exit, "other": other}


def _regime_summary(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        net = _number(trade.get("net_return_pct"))
        if net is None:
            continue
        grouped[str(trade.get("market_regime") or "UNKNOWN")].append(net)
    rows: list[dict[str, Any]] = []
    for regime, returns in grouped.items():
        rows.append({
            "regime": regime,
            "trades": len(returns),
            "average_net_return_pct": round(sum(returns) / len(returns), 3),
            "wins": sum(1 for value in returns if value > 0),
            "losses": sum(1 for value in returns if value < 0),
        })
    rows.sort(key=lambda item: int(item["trades"]), reverse=True)
    return rows


def evaluate_historical_evidence(
    *,
    metrics: dict[str, Any],
    trades: list[dict[str, Any]],
    validation_start: str,
    validation_end: str,
) -> dict[str, Any]:
    sample_count = int(metrics.get("trades") or 0)
    wins = int(metrics.get("wins") or 0)
    losses = int(metrics.get("losses") or 0)
    avg_net = _number(metrics.get("average_net_return_pct"))
    median_net = _number(metrics.get("median_net_return_pct"))
    expectancy = _number(metrics.get("expectancy_pct"))
    profit_factor = _number(metrics.get("profit_factor"))
    mdd = _number(metrics.get("max_drawdown_pct"))
    win_rate = _number(metrics.get("win_rate_pct"))
    avg_win = _number(metrics.get("average_win_pct"))
    avg_loss = _number(metrics.get("average_loss_pct"))

    if sample_count == 0:
        status = "NO_CASES"
        label = "과거 사례 없음"
        summary = "3년 검증 기간에 같은 전략 조건으로 실제 거래까지 이어진 사례가 없었습니다."
    elif sample_count < MIN_SAMPLE_FOR_EVALUATION:
        status = "INSUFFICIENT"
        label = "표본 부족"
        summary = f"3년 동안 유사 거래가 {sample_count}건이라 성과가 좋아 보여도 판단 근거로 쓰기에는 표본이 부족합니다."
    elif expectancy is not None and expectancy > 0 and (profit_factor is None or profit_factor >= 1.2) and (mdd is None or mdd > -20):
        status = "GOOD"
        label = "과거 근거 양호"
        summary = "표본이 10건 이상이고 평균 결과·손익 구조·큰 손실 구간이 함께 비교 가능한 수준이었습니다."
    elif expectancy is not None and expectancy > 0 and (mdd is None or mdd > -25):
        status = "FAIR"
        label = "과거 근거 보통"
        summary = "표본은 확보됐고 평균 결과도 플러스였지만, 적극적인 근거로 보기에는 손익 구조나 변동성이 더 확인돼야 합니다."
    else:
        status = "WEAK"
        label = "과거 근거 약함"
        summary = "표본은 확보됐지만 평균 결과나 손실 위험이 현재 전략을 강하게 뒷받침하지 못했습니다."

    regimes = _regime_summary(trades)
    warnings: list[str] = []
    for row in regimes:
        if int(row["trades"]) >= 3 and float(row["average_net_return_pct"]) < 0:
            names = {
                "TREND_UP": "상승장",
                "TREND_DOWN": "하락장",
                "RANGE": "횡보장",
                "HIGH_VOLATILITY": "고변동성",
                "PANIC": "패닉",
                "UNKNOWN": "시장국면 미분류",
            }
            warnings.append(
                f"{names.get(str(row['regime']), str(row['regime']))}에서 {row['trades']}건의 평균 순수익이 "
                f"{float(row['average_net_return_pct']):+.2f}%였습니다."
            )
    if sample_count < MIN_SAMPLE_FOR_EVALUATION and sample_count > 0:
        warnings.insert(0, f"유사 거래가 {sample_count}건뿐이라 승률이나 평균수익을 미래 확률처럼 해석하면 안 됩니다.")

    return {
        "status": status,
        "label": label,
        "summary": summary,
        "verified": True,
        "unavailable_reason": None,
        "preparation_available": False,
        "sample_sufficient": sample_count >= MIN_SAMPLE_FOR_EVALUATION,
        "minimum_sample": MIN_SAMPLE_FOR_EVALUATION,
        "validation_years": EVIDENCE_YEARS,
        "period": {"start": validation_start, "end": validation_end},
        "sample_count": sample_count,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "average_net_return_pct": avg_net,
        "median_net_return_pct": median_net,
        "expectancy_pct": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown_pct": mdd,
        "average_win_pct": avg_win,
        "average_loss_pct": avg_loss,
        "exit_counts": _exit_counts(trades),
        "market_regime_summary": regimes,
        "warnings": warnings,
        "guardrail": "과거 유사조건 결과는 미래 상승 확률이 아니며 미래 수익을 보장하지 않습니다.",
    }


def unavailable_historical_evidence(
    *,
    validation_start: date,
    validation_end: date,
    reasons: list[str],
    unavailable_reason: str = "MISSING_HISTORY",
    preparation_available: bool = True,
) -> dict[str, Any]:
    return {
        "status": "DATA_UNAVAILABLE",
        "label": "3년 검증 데이터 부족",
        "summary": "저장된 Market Store만으로 3년 검증을 완료할 수 없습니다. Scanner가 대량 KRX 다운로드를 자동으로 시작하지는 않습니다.",
        "verified": False,
        "unavailable_reason": unavailable_reason,
        "preparation_available": preparation_available,
        "sample_sufficient": False,
        "minimum_sample": MIN_SAMPLE_FOR_EVALUATION,
        "validation_years": EVIDENCE_YEARS,
        "period": {"start": validation_start.isoformat(), "end": validation_end.isoformat()},
        "sample_count": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_pct": None,
        "average_net_return_pct": None,
        "median_net_return_pct": None,
        "expectancy_pct": None,
        "profit_factor": None,
        "max_drawdown_pct": None,
        "average_win_pct": None,
        "average_loss_pct": None,
        "exit_counts": {"stop": 0, "target1": 0, "time_exit": 0, "other": 0},
        "market_regime_summary": [],
        "warnings": reasons,
        "target1_audit": {
            "available": False,
            "sample_count": 0,
            "guardrail": "3년 검증 데이터가 준비되지 않아 Target1 현실성 감사도 실행하지 않았습니다.",
        },
        "guardrail": "과거 검증 미완료를 현재 전략 조건 실패로 취급하지 않습니다.",
    }


def build_historical_evidence(
    *,
    engine: MultiStrategyBacktestEngine,
    strategy: str,
    code: str,
    market: str,
    stock_rows: list[dict[str, Any]],
    index_rows: list[dict[str, Any]],
    validation_start: date,
    validation_end: date,
    round_trip_cost_pct: float = 0.0,
) -> dict[str, Any]:
    readiness = data_readiness(
        stock_rows=stock_rows,
        index_rows=index_rows,
        validation_start=validation_start,
        validation_end=validation_end,
    )
    if not readiness["ready"]:
        return unavailable_historical_evidence(
            validation_start=validation_start,
            validation_end=validation_end,
            reasons=list(readiness["reasons"]),
        )

    try:
        strategy_name = StrategyName(strategy)
    except ValueError:
        return unavailable_historical_evidence(
            validation_start=validation_start,
            validation_end=validation_end,
            reasons=[f"지원하지 않는 전략: {strategy}"],
            unavailable_reason="UNSUPPORTED_STRATEGY",
            preparation_available=False,
        )

    rows = sorted(stock_rows, key=lambda row: _date_value(row))
    indices = sorted(index_rows, key=lambda row: _date_value(row))
    start_key = validation_start.strftime("%Y%m%d")
    end_key = validation_end.strftime("%Y%m%d")
    config = BacktestConfig(
        code=code,
        market=market,
        start_date=validation_start.isoformat(),
        end_date=validation_end.isoformat(),
        initial_capital=10_000_000,
        max_holding_days=20,
        round_trip_cost_pct=round_trip_cost_pct,
    )

    snapshots: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        row_date = _date_value(row)
        if row_date < start_key or row_date > end_key:
            continue
        snapshot = engine.base._signal_snapshot(  # noqa: SLF001 - reuse the same audited backtest snapshot path
            stock_rows=rows,
            index_rows=indices,
            index=index,
            config=config,
        )
        if snapshot is not None:
            snapshots.append(snapshot)

    strategy_row = engine._run_strategy(  # noqa: SLF001 - one-strategy evidence, same execution engine as multi-strategy backtest
        strategy=strategy_name,
        snapshots=snapshots,
        stock_rows=rows,
        config=config,
        include_trade_history=True,
    )
    trades = list(strategy_row.pop("trade_history", []) or [])
    metrics = dict(strategy_row.get("historical_metrics") or {})
    evidence = evaluate_historical_evidence(
        metrics=metrics,
        trades=trades,
        validation_start=validation_start.isoformat(),
        validation_end=validation_end.isoformat(),
    )
    evidence["signal_count"] = int(strategy_row.get("signal_count") or 0)
    evidence["risk_blocked_signals"] = int(strategy_row.get("risk_blocked_signals") or 0)
    evidence["strategy"] = strategy_name.value
    evidence["exit_policy"] = dict(strategy_row.get("exit_policy") or {})
    evidence["historical_policy"] = dict((strategy_row.get("exit_policy") or {}).get("historical_policy") or {})
    evidence["target1_audit"] = build_historical_target1_audit(
        trades=trades,
        stock_rows=rows,
        max_holding_days=config.max_holding_days,
        round_trip_cost_pct=config.round_trip_cost_pct,
    )
    return evidence
