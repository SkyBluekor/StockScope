from __future__ import annotations

import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from app.backtest.candidate_priority import rank_candidates
from app.backtest.scanner_quality.early_pruning_audit import (
    _candidate_snapshot,
    _compact,
    _float,
    _future_metrics,
    _mean,
    _median,
    _row_date,
    _safe_json,
    _trimmed_mean,
)
from app.backtest.scanner_quality.models import AuditHorizons

KST = timezone(timedelta(hours=9), name="KST")
AUDIT_VERSION = "v0.21.4-B.2.3.4c.3"


@dataclass(frozen=True)
class StrategySearchVariant:
    name: str
    strategy_limit: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "strategy_limit": self.strategy_limit,
            "strategy_limit_label": "ALL" if self.strategy_limit is None else int(self.strategy_limit),
        }


def _pct(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 4) if denominator else None


def _delta(left: Any, right: Any) -> float | None:
    left_value = _float(left)
    right_value = _float(right)
    if left_value is None or right_value is None:
        return None
    return round(left_value - right_value, 6)


def _status(candidate: dict[str, Any] | None) -> str | None:
    if not candidate:
        return None
    return str(candidate.get("candidate_state") or candidate.get("action") or "") or None


def _risk_status(candidate: dict[str, Any] | None) -> str | None:
    if not candidate:
        return None
    return str((candidate.get("risk") or {}).get("status") or "") or None


def _missing(candidate: dict[str, Any] | None) -> int | None:
    if not candidate:
        return None
    state = candidate.get("conditions") or {}
    value = state.get("missing")
    if value is None:
        total = int(state.get("total") or 0)
        passed = int(state.get("passed") or 0)
        value = max(0, total - passed)
    return int(value)


def _forward(candidate: dict[str, Any] | None, horizon: int) -> dict[str, Any]:
    if not candidate:
        return {}
    return ((((candidate.get("outcome") or {}).get("forward") or {}).get(str(horizon))) or {})


def _event(candidate: dict[str, Any] | None, horizon: int) -> str | None:
    return str((_forward(candidate, horizon).get("event") or {}).get("status") or "") or None


class StrategySearchAuditor:
    """Offline Top3-vs-All strategy-search audit.

    The stock universe, market pre-filter, quick pool and production ranking stay fixed.
    Only the number of strategies that receive current-readiness / Risk evaluation changes.
    """

    def __init__(self, scanner: Any, market_store: Any) -> None:
        self.scanner = scanner
        self.market_store = market_store

    @staticmethod
    def _markets(scope: str) -> list[str]:
        normalized = scope.upper().strip()
        if normalized == "ALL":
            return ["KOSPI", "KOSDAQ"]
        if normalized in {"KOSPI", "KOSDAQ"}:
            return [normalized]
        raise ValueError("market_scope은 ALL, KOSPI, KOSDAQ 중 하나여야 합니다.")

    def _exact_day_available(self, markets: list[str], as_of: date) -> bool:
        key = _compact(as_of)
        return all(
            self.market_store.latest_complete_date(market, "stock", key) == key
            and self.market_store.latest_complete_date(market, "index", key) == key
            for market in markets
        )

    def _future_rows_many(
        self,
        *,
        codes_by_market: dict[str, set[str]],
        as_of: date,
        max_horizon: int,
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        result: dict[tuple[str, str], list[dict[str, Any]]] = {}
        start = _compact(as_of + timedelta(days=1))
        end = _compact(as_of + timedelta(days=max(45, max_horizon * 3)))
        for market, codes in codes_by_market.items():
            series_map = self.market_store.stock_series_many(market, sorted(codes), start, end)
            for code, series in series_map.items():
                rows = sorted((dict(row) for row in series.rows.values()), key=_row_date)
                result[(market, code)] = rows
        return result

    def _evaluate_strategy_search(
        self,
        *,
        market: str,
        latest_date: str,
        row: dict[str, Any],
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
        strategy_limit: int | None,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], float]:
        """Return a quick-item compatible with production plus per-strategy trace.

        Tests may supply a scanner hook to avoid importing the full strategy stack.
        Production projects use the exact same snapshot/current-readiness helpers as Scanner.
        """
        hook = getattr(self.scanner, "_strategy_search_audit_evaluate", None)
        if callable(hook):
            return hook(
                market=market,
                latest_date=latest_date,
                row=row,
                stock_rows=stock_rows,
                index_rows=index_rows,
                strategy_limit=strategy_limit,
            )

        if len(stock_rows) < int(self.scanner.MIN_HISTORY_ROWS):
            return None, [], 0.0

        from app.backtest.entry_risk_guide import build_entry_risk_guide
        from app.backtest.models import BacktestConfig
        from app.backtest.selector import build_condition_state, current_readiness, strategy_guide

        rows = sorted(stock_rows, key=_row_date)
        indices = sorted(index_rows, key=_row_date)
        config = BacktestConfig(
            code=str(row.get("code") or ""),
            market=market,
            start_date=self.scanner._iso(latest_date),  # noqa: SLF001 - same helper as production
            end_date=self.scanner._iso(latest_date),  # noqa: SLF001
            initial_capital=10_000_000,
            max_holding_days=20,
            round_trip_cost_pct=0.0,
        )
        snapshot = self.scanner.engine._signal_snapshot(  # noqa: SLF001
            stock_rows=rows,
            index_rows=indices,
            index=len(rows) - 1,
            config=config,
        )
        if snapshot is None:
            return None, [], 0.0

        evaluations = list((snapshot.get("evaluations") or {}).values())
        evaluations.sort(
            key=lambda item: (bool(getattr(item, "eligible", False)), int(getattr(item, "score", 0) or 0)),
            reverse=True,
        )
        limit = len(evaluations) if strategy_limit is None else max(0, min(int(strategy_limit), len(evaluations)))
        chosen_pool = evaluations[:limit]
        trace: list[dict[str, Any]] = []
        trace_by_strategy: dict[str, dict[str, Any]] = {}
        for rank, evaluation in enumerate(evaluations, start=1):
            strategy_name = str(getattr(getattr(evaluation, "strategy", None), "value", getattr(evaluation, "strategy", "")))
            record = {
                "initial_rank": rank,
                "strategy": strategy_name,
                "initial_score": int(getattr(evaluation, "score", 0) or 0),
                "eligible": bool(getattr(evaluation, "eligible", False)),
                "current_evaluated": rank <= limit,
            }
            trace.append(record)
            trace_by_strategy[strategy_name] = record

        best: dict[str, Any] | None = None
        current_started = time.perf_counter()
        for evaluation in chosen_pool:
            strategy = evaluation.strategy
            strategy_name = str(getattr(strategy, "value", strategy))
            condition_state = build_condition_state(
                evaluation,
                data=snapshot.get("strategy_input"),
                technical=snapshot.get("technical") or {},
            )
            risk_plan = self.scanner.multi._current_risk_plan(snapshot, strategy)  # noqa: SLF001
            current = current_readiness(
                evaluation=evaluation,
                risk_plan=risk_plan,
                condition_state=condition_state,
            )
            record = trace_by_strategy.get(strategy_name)
            if record is not None:
                record.update(
                    {
                        "current_internal_score": _float(current.get("internal_score")),
                        "current_status": current.get("status"),
                        "passed": int(current.get("passed") or 0),
                        "total": int(current.get("total") or 0),
                        "missing": int(current.get("missing") or 0),
                        "risk_warning": bool(current.get("risk_warning")),
                    }
                )
            score = float(current.get("internal_score") or 0.0)
            if best is None or score > float(best["current"].get("internal_score") or 0.0):
                best = {
                    "strategy": strategy_name,
                    "guide": strategy_guide(strategy),
                    "current": current,
                    "condition_state": condition_state,
                    "risk_plan": risk_plan,
                    "strategy_input": snapshot.get("strategy_input"),
                    "technical": snapshot.get("technical") or {},
                    "entry_timing": snapshot.get("entry_timing") or None,
                }
        current_elapsed = time.perf_counter() - current_started
        if best is None:
            return None, trace, current_elapsed

        current = best["current"]
        total = int(current.get("total") or 0)
        passed = int(current.get("passed") or 0)
        ratio = passed / total if total else 0.0
        risk_penalty = 18.0 if current.get("risk_warning") else 0.0
        quick_score = float(current.get("internal_score") or 0.0) + ratio * 20.0 - risk_penalty
        entry_risk_guide = build_entry_risk_guide(
            strategy=best["strategy"],
            data=best.get("strategy_input"),
            technical=best.get("technical") or {},
            condition_state=best.get("condition_state") or {},
            risk_plan=best.get("risk_plan"),
            current_state=current,
            historical_verified=False,
            historical_status="NOT_RUN",
            as_of_date=str(latest_date or "") or None,
            entry_timing=best.get("entry_timing"),
        )
        quick_exit_resolution = self.scanner.multi.production_exit.registry.resolve(best["strategy"])
        entry_risk_guide["historical_policy"] = self.scanner.multi.production_exit.historical_policy_metadata(
            quick_exit_resolution
        )
        selected_rank = next(
            (int(item["initial_rank"]) for item in trace if item.get("strategy") == best["strategy"]),
            None,
        )
        for item in trace:
            item["selected"] = item.get("strategy") == best["strategy"]

        quick_item = {
            "code": str(row.get("code") or ""),
            "name": str(row.get("name") or ""),
            "market": market,
            "latest_date": latest_date,
            "current_price": row.get("close"),
            "trade_value": row.get("trade_value"),
            "market_cap": row.get("market_cap"),
            "history_points": len(rows),
            "quick_strategy": best["strategy"],
            "quick_guide": best["guide"],
            "quick_current": current,
            "quick_condition_state": best.get("condition_state") or {},
            "quick_entry_risk_guide": entry_risk_guide,
            "quick_score": round(quick_score, 4),
            "_audit_initial_strategy_rank": selected_rank,
        }
        return quick_item, trace, current_elapsed

    def run_date(
        self,
        *,
        as_of: date,
        market_scope: str = "ALL",
        horizons: AuditHorizons = AuditHorizons(),
        quick_limit: int | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        markets = self._markets(market_scope)
        if not self._exact_day_available(markets, as_of):
            return {
                "analysis_date": as_of.isoformat(),
                "status": "SKIPPED_INSUFFICIENT_DATA",
                "reason": "analysis_date_stock_or_index_missing",
                "runtime_seconds": round(time.perf_counter() - started, 6),
            }

        market_limit = int(self.scanner.QUICK_LIMIT_PER_MARKET)
        selected_limit = int(quick_limit or self.scanner.DEEP_LIMIT)
        fast_start = as_of - timedelta(days=int(self.scanner.FAST_HISTORY_CALENDAR_DAYS))
        latest_key = _compact(as_of)
        index_rows_by_market: dict[str, list[dict[str, Any]]] = {}
        row_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        history_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        baseline_quick: list[dict[str, Any]] = []
        special_excluded = 0
        liquidity_filtered = 0
        data_insufficient = 0

        for market in markets:
            ordinary: list[dict[str, Any]] = []
            for row in self.market_store.stock_day_rows(market, latest_key):
                if self.scanner._special_reason(row) is not None:  # noqa: SLF001
                    special_excluded += 1
                    continue
                if float(row.get("trade_value") or 0) < self.scanner.engine.LIQUIDITY_THRESHOLD:
                    liquidity_filtered += 1
                    continue
                ordinary.append(dict(row))
            ordinary.sort(
                key=lambda item: (float(item.get("trade_value") or 0), float(item.get("market_cap") or 0)),
                reverse=True,
            )
            prefiltered = ordinary[:market_limit]
            index_series = self.market_store.index_series(market, _compact(fast_start), latest_key)
            index_rows = sorted((dict(row) for row in index_series.rows.values()), key=_row_date)
            index_rows_by_market[market] = index_rows
            series_map = self.market_store.stock_series_many(
                market,
                [str(row.get("code") or "") for row in prefiltered],
                _compact(fast_start),
                latest_key,
            )
            for row in prefiltered:
                code = str(row.get("code") or "")
                key = (market, code)
                series = series_map.get(code)
                stock_rows = sorted(
                    (dict(item) for item in ((series.rows.values()) if series is not None else [])),
                    key=_row_date,
                )
                row_by_key[key] = row
                history_by_key[key] = stock_rows
                quick = self.scanner._quick_current_candidate(  # noqa: SLF001 - production pool selection
                    market=market,
                    latest_date=latest_key,
                    row=row,
                    stock_rows=stock_rows,
                    index_rows=index_rows,
                )
                if quick is None:
                    data_insufficient += 1
                    continue
                baseline_quick.append(quick)

        baseline_quick.sort(
            key=lambda item: (float(item.get("quick_score") or 0), float(item.get("trade_value") or 0)),
            reverse=True,
        )
        selected_quick = baseline_quick[:selected_limit]
        selected_keys = [(str(item.get("market") or ""), str(item.get("code") or "")) for item in selected_quick]
        baseline_quick_by_key = {
            (str(item.get("market") or ""), str(item.get("code") or "")): item for item in selected_quick
        }

        variants = [
            StrategySearchVariant("BASELINE_TOP3", 3),
            StrategySearchVariant("ALL_STRATEGIES", None),
        ]
        variant_candidates: dict[str, list[dict[str, Any]]] = {variant.name: [] for variant in variants}
        strategy_trace: dict[str, dict[str, Any]] = {}
        variant_eval_seconds: dict[str, float] = {variant.name: 0.0 for variant in variants}
        baseline_parity_mismatches = 0

        for market, code in selected_keys:
            key = (market, code)
            row = row_by_key[key]
            stock_rows = history_by_key[key]
            per_symbol: dict[str, Any] = {
                "market": market,
                "code": code,
                "name": row.get("name"),
                "variants": {},
            }
            for variant in variants:
                quick_item, trace, eval_elapsed = self._evaluate_strategy_search(
                    market=market,
                    latest_date=latest_key,
                    row=row,
                    stock_rows=stock_rows,
                    index_rows=index_rows_by_market.get(market, []),
                    strategy_limit=variant.strategy_limit,
                )
                variant_eval_seconds[variant.name] += eval_elapsed
                current_candidate = self.scanner._current_candidate(quick_item) if quick_item is not None else None  # noqa: SLF001
                if current_candidate is not None:
                    current_candidate["_audit_initial_strategy_rank"] = quick_item.get("_audit_initial_strategy_rank")
                    variant_candidates[variant.name].append(current_candidate)
                per_symbol["variants"][variant.name] = {
                    "selected_strategy": None if quick_item is None else quick_item.get("quick_strategy"),
                    "selected_initial_rank": None if quick_item is None else quick_item.get("_audit_initial_strategy_rank"),
                    "current_candidate_state": _status(current_candidate),
                    "risk_status": _risk_status(current_candidate),
                    "missing_conditions": _missing(current_candidate),
                    "quick_score": None if quick_item is None else quick_item.get("quick_score"),
                    "strategy_trace": _safe_json(trace),
                }
            production_strategy = (baseline_quick_by_key.get(key) or {}).get("quick_strategy")
            audit_top3_strategy = per_symbol["variants"]["BASELINE_TOP3"].get("selected_strategy")
            if production_strategy != audit_top3_strategy:
                baseline_parity_mismatches += 1
            per_symbol["production_quick_strategy"] = production_strategy
            per_symbol["baseline_parity"] = production_strategy == audit_top3_strategy
            strategy_trace[f"{market}:{code}"] = per_symbol

        ranked_by_variant: dict[str, list[dict[str, Any]]] = {}
        ranking_changes_by_variant: dict[str, list[dict[str, Any]]] = {}
        outcome_codes: dict[str, set[str]] = {market: set() for market in markets}
        for variant in variants:
            actionable = [
                candidate
                for candidate in variant_candidates[variant.name]
                if candidate.get("candidate_state") in {"READY", "WATCH", "VALIDATION"}
            ]
            ranked, ranking_changes = rank_candidates(actionable)
            ranked_by_variant[variant.name] = ranked
            ranking_changes_by_variant[variant.name] = ranking_changes
            for candidate in ranked:
                outcome_codes.setdefault(str(candidate.get("market") or ""), set()).add(str(candidate.get("code") or ""))

        horizons_tuple = horizons.normalized()
        future_rows = self._future_rows_many(
            codes_by_market=outcome_codes,
            as_of=as_of,
            max_horizon=max(horizons_tuple),
        )
        variant_results: dict[str, Any] = {}
        for variant in variants:
            ranked = ranked_by_variant[variant.name]
            snapshots: list[dict[str, Any]] = []
            for rank, candidate in enumerate(ranked, start=1):
                snap = _candidate_snapshot(candidate, rank=rank)
                key = (str(candidate.get("market") or ""), str(candidate.get("code") or ""))
                snap["initial_strategy_rank"] = candidate.get("_audit_initial_strategy_rank")
                snap["outcome"] = _future_metrics(
                    candidate=candidate,
                    future_rows=future_rows.get(key, []),
                    horizons=horizons_tuple,
                )
                snapshots.append(snap)
            variant_results[variant.name] = {
                "config": variant.to_dict(),
                "selected_stock_count": len(selected_quick),
                "actionable_count": len(ranked),
                "candidates": snapshots,
                "ranking_changes": _safe_json(ranking_changes_by_variant[variant.name]),
                "current_evaluation_seconds": round(variant_eval_seconds[variant.name], 6),
                "top5_metrics": self._aggregate_top_metrics(snapshots[:5], horizons_tuple),
            }

        baseline_map = {
            (str(item.get("market") or ""), str(item.get("code") or "")): item
            for item in variant_results["BASELINE_TOP3"]["candidates"]
        }
        all_map = {
            (str(item.get("market") or ""), str(item.get("code") or "")): item
            for item in variant_results["ALL_STRATEGIES"]["candidates"]
        }
        strategy_pairs: list[dict[str, Any]] = []
        outside_top3 = 0
        top3_outside_ready = 0
        tier_improvements = 0
        strategy_changed_signals = 0
        for market, code in selected_keys:
            trace = strategy_trace.get(f"{market}:{code}") or {}
            baseline_info = ((trace.get("variants") or {}).get("BASELINE_TOP3") or {})
            all_info = ((trace.get("variants") or {}).get("ALL_STRATEGIES") or {})
            baseline_strategy = baseline_info.get("selected_strategy")
            all_strategy = all_info.get("selected_strategy")
            initial_rank = all_info.get("selected_initial_rank")
            if isinstance(initial_rank, int) and initial_rank > 3:
                outside_top3 += 1
                if str(all_info.get("current_candidate_state") or "") == "READY":
                    top3_outside_ready += 1
            if baseline_strategy != all_strategy:
                strategy_changed_signals += 1
                baseline_candidate = baseline_map.get((market, code))
                all_candidate = all_map.get((market, code))
                baseline_state = baseline_info.get("current_candidate_state")
                all_state = all_info.get("current_candidate_state")
                tier_order = {"READY": 0, "WATCH": 1, "VALIDATION": 2, "EXCLUDED": 3, None: 4}
                if tier_order.get(all_state, 4) < tier_order.get(baseline_state, 4):
                    tier_improvements += 1
                pair = {
                    "analysis_date": as_of.isoformat(),
                    "market": market,
                    "code": code,
                    "name": trace.get("name"),
                    "baseline_strategy": baseline_strategy,
                    "all_strategy": all_strategy,
                    "all_initial_rank": initial_rank,
                    "baseline_state": baseline_state,
                    "all_state": all_state,
                    "baseline_risk": baseline_info.get("risk_status"),
                    "all_risk": all_info.get("risk_status"),
                    "baseline_missing": baseline_info.get("missing_conditions"),
                    "all_missing": all_info.get("missing_conditions"),
                }
                for horizon in horizons_tuple:
                    baseline_forward = _forward(baseline_candidate, horizon)
                    all_forward = _forward(all_candidate, horizon)
                    pair[f"return_{horizon}d_delta"] = _delta(all_forward.get("return_pct"), baseline_forward.get("return_pct"))
                    pair[f"r_{horizon}d_delta"] = _delta(all_forward.get("event_r"), baseline_forward.get("event_r"))
                    pair[f"baseline_event_{horizon}d"] = _event(baseline_candidate, horizon)
                    pair[f"all_event_{horizon}d"] = _event(all_candidate, horizon)
                strategy_pairs.append(pair)

        baseline_top5 = [
            (str(item.get("market") or ""), str(item.get("code") or ""))
            for item in variant_results["BASELINE_TOP3"]["candidates"][:5]
        ]
        all_top5 = [
            (str(item.get("market") or ""), str(item.get("code") or ""))
            for item in variant_results["ALL_STRATEGIES"]["candidates"][:5]
        ]
        top5_changed = baseline_top5 != all_top5
        top5_replacements = len(set(all_top5) - set(baseline_top5))

        return {
            "analysis_date": as_of.isoformat(),
            "status": "OK",
            "market_scope": market_scope.upper(),
            "fast_history_start": fast_start.isoformat(),
            "universe_total": sum(len(self.market_store.stock_day_rows(market, latest_key)) for market in markets),
            "special_excluded": special_excluded,
            "liquidity_filtered": liquidity_filtered,
            "data_insufficient": data_insufficient,
            "market_limit": market_limit,
            "quick_limit": selected_limit,
            "production_quick_pool_count": len(selected_quick),
            "baseline_parity_mismatches": baseline_parity_mismatches,
            "variants": variant_results,
            "strategy_trace": strategy_trace,
            "strategy_pairs": strategy_pairs,
            "strategy_changed_signal_count": strategy_changed_signals,
            "outside_top3_selected_count": outside_top3,
            "outside_top3_ready_count": top3_outside_ready,
            "tier_improvement_count": tier_improvements,
            "top5_changed": top5_changed,
            "top5_replacement_count": top5_replacements,
            "runtime_seconds": round(time.perf_counter() - started, 6),
        }

    @staticmethod
    def _aggregate_top_metrics(candidates: list[dict[str, Any]], horizons: tuple[int, ...]) -> dict[str, Any]:
        result: dict[str, Any] = {"count": len(candidates), "horizons": {}}
        for horizon in horizons:
            returns: list[float] = []
            rs: list[float] = []
            mfes: list[float] = []
            maes: list[float] = []
            target_first = 0
            stop_first = 0
            complete = 0
            for candidate in candidates:
                metric = _forward(candidate, horizon)
                if not metric.get("complete"):
                    continue
                complete += 1
                for target, key in ((returns, "return_pct"), (rs, "event_r"), (mfes, "mfe_pct"), (maes, "mae_pct")):
                    value = _float(metric.get(key))
                    if value is not None:
                        target.append(value)
                status = _event(candidate, horizon)
                target_first += int(status == "TARGET1_FIRST")
                stop_first += int(status == "STOP_FIRST")
            result["horizons"][str(horizon)] = {
                "complete": complete,
                "mean_return_pct": _mean(returns),
                "median_return_pct": _median(returns),
                "mean_event_r": _mean(rs),
                "median_event_r": _median(rs),
                "mean_mfe_pct": _mean(mfes),
                "mean_mae_pct": _mean(maes),
                "target1_first_pct": _pct(target_first, complete),
                "stop_first_pct": _pct(stop_first, complete),
            }
        return result

    def run_dates(
        self,
        *,
        dates: list[date],
        market_scope: str = "ALL",
        horizons: AuditHorizons = AuditHorizons(),
        quick_limit: int | None = None,
        progress_callback: Callable[[int, int, date, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        runs: list[dict[str, Any]] = []
        for index, as_of in enumerate(dates, start=1):
            run = self.run_date(
                as_of=as_of,
                market_scope=market_scope,
                horizons=horizons,
                quick_limit=quick_limit,
            )
            runs.append(run)
            if progress_callback is not None:
                progress_callback(index, len(dates), as_of, run)
        valid = [run for run in runs if run.get("status") == "OK"]
        horizons_tuple = horizons.normalized()
        variants = ("BASELINE_TOP3", "ALL_STRATEGIES")

        aggregate: dict[str, Any] = {}
        for variant in variants:
            daily_returns: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
            daily_rs: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
            target_total: dict[str, int] = {str(h): 0 for h in horizons_tuple}
            stop_total: dict[str, int] = {str(h): 0 for h in horizons_tuple}
            complete_total: dict[str, int] = {str(h): 0 for h in horizons_tuple}
            eval_seconds: list[float] = []
            strategy_distribution: dict[str, int] = {}
            initial_rank_distribution: dict[str, int] = {}
            for run in valid:
                result = ((run.get("variants") or {}).get(variant) or {})
                eval_seconds.append(float(result.get("current_evaluation_seconds") or 0.0))
                for candidate in result.get("candidates") or []:
                    strategy = str(candidate.get("strategy") or "UNKNOWN")
                    strategy_distribution[strategy] = strategy_distribution.get(strategy, 0) + 1
                    rank = candidate.get("initial_strategy_rank")
                    if rank is not None:
                        key = str(rank)
                        initial_rank_distribution[key] = initial_rank_distribution.get(key, 0) + 1
                metrics = ((result.get("top5_metrics") or {}).get("horizons") or {})
                for horizon in horizons_tuple:
                    key = str(horizon)
                    item = metrics.get(key) or {}
                    value = _float(item.get("mean_return_pct"))
                    if value is not None:
                        daily_returns[key].append(value)
                    value = _float(item.get("mean_event_r"))
                    if value is not None:
                        daily_rs[key].append(value)
                    complete = int(item.get("complete") or 0)
                    complete_total[key] += complete
                    target_total[key] += round((float(item.get("target1_first_pct") or 0.0) / 100.0) * complete)
                    stop_total[key] += round((float(item.get("stop_first_pct") or 0.0) / 100.0) * complete)
            aggregate[variant] = {
                "valid_dates": len(valid),
                "mean_current_evaluation_seconds": _mean(eval_seconds),
                "strategy_distribution": strategy_distribution,
                "selected_initial_rank_distribution": initial_rank_distribution,
                "top5": {
                    key: {
                        "mean_of_daily_mean_return_pct": _mean(daily_returns[key]),
                        "median_of_daily_mean_return_pct": _median(daily_returns[key]),
                        "trimmed_mean_of_daily_mean_return_pct": _trimmed_mean(daily_returns[key]),
                        "mean_of_daily_mean_event_r": _mean(daily_rs[key]),
                        "median_of_daily_mean_event_r": _median(daily_rs[key]),
                        "trimmed_mean_of_daily_mean_event_r": _trimmed_mean(daily_rs[key]),
                        "target1_first_pct": _pct(target_total[key], complete_total[key]),
                        "stop_first_pct": _pct(stop_total[key], complete_total[key]),
                        "complete_signals": complete_total[key],
                    }
                    for key in daily_returns
                },
            }

        strategy_pairs = [pair for run in valid for pair in (run.get("strategy_pairs") or [])]
        changed_dates = [run["analysis_date"] for run in valid if int(run.get("strategy_changed_signal_count") or 0) > 0]
        top5_changed_dates = [run["analysis_date"] for run in valid if bool(run.get("top5_changed"))]
        total_selected = sum(int(run.get("production_quick_pool_count") or 0) for run in valid)
        outside_top3 = sum(int(run.get("outside_top3_selected_count") or 0) for run in valid)
        outside_top3_ready = sum(int(run.get("outside_top3_ready_count") or 0) for run in valid)
        tier_improvements = sum(int(run.get("tier_improvement_count") or 0) for run in valid)
        parity_mismatches = sum(int(run.get("baseline_parity_mismatches") or 0) for run in valid)

        date_deltas: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
        r_deltas: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
        stop_deltas: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
        target_deltas: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
        for run in valid:
            base = (((run.get("variants") or {}).get("BASELINE_TOP3") or {}).get("top5_metrics") or {}).get("horizons") or {}
            allv = (((run.get("variants") or {}).get("ALL_STRATEGIES") or {}).get("top5_metrics") or {}).get("horizons") or {}
            for horizon in horizons_tuple:
                key = str(horizon)
                for bucket, metric_key in (
                    (date_deltas, "mean_return_pct"),
                    (r_deltas, "mean_event_r"),
                    (stop_deltas, "stop_first_pct"),
                    (target_deltas, "target1_first_pct"),
                ):
                    value = _delta((allv.get(key) or {}).get(metric_key), (base.get(key) or {}).get(metric_key))
                    if value is not None:
                        bucket[key].append(value)

        pair_summary: dict[str, Any] = {}
        for horizon in horizons_tuple:
            key = str(horizon)
            r_values = [_float(pair.get(f"r_{horizon}d_delta")) for pair in strategy_pairs]
            return_values = [_float(pair.get(f"return_{horizon}d_delta")) for pair in strategy_pairs]
            r_values = [value for value in r_values if value is not None]
            return_values = [value for value in return_values if value is not None]
            pair_summary[key] = {
                "count": len(r_values),
                "mean_r_delta": _mean(r_values),
                "median_r_delta": _median(r_values),
                "trimmed_mean_r_delta": _trimmed_mean(r_values),
                "mean_return_delta_pct": _mean(return_values),
                "median_return_delta_pct": _median(return_values),
                "positive_r_count": sum(1 for value in r_values if value > 0),
                "negative_r_count": sum(1 for value in r_values if value < 0),
            }

        baseline_runtime = _float((aggregate.get("BASELINE_TOP3") or {}).get("mean_current_evaluation_seconds")) or 0.0
        all_runtime = _float((aggregate.get("ALL_STRATEGIES") or {}).get("mean_current_evaluation_seconds")) or 0.0
        runtime_ratio = (all_runtime / baseline_runtime) if baseline_runtime > 0 else None
        top5_20_base = (((aggregate.get("BASELINE_TOP3") or {}).get("top5") or {}).get("20") or {})
        top5_20_all = (((aggregate.get("ALL_STRATEGIES") or {}).get("top5") or {}).get("20") or {})
        top5_r_delta = _delta(top5_20_all.get("mean_of_daily_mean_event_r"), top5_20_base.get("mean_of_daily_mean_event_r"))
        top5_return_delta = _delta(top5_20_all.get("mean_of_daily_mean_return_pct"), top5_20_base.get("mean_of_daily_mean_return_pct"))
        top5_stop_delta = _delta(top5_20_all.get("stop_first_pct"), top5_20_base.get("stop_first_pct"))
        pair_r20 = _float((pair_summary.get("20") or {}).get("mean_r_delta"))

        all_rank_distribution = (aggregate.get("ALL_STRATEGIES") or {}).get("selected_initial_rank_distribution") or {}
        outside_rank_counts = {int(rank): int(count) for rank, count in all_rank_distribution.items() if int(rank) > 3}
        outside_low_k = sum(count for rank, count in outside_rank_counts.items() if rank <= 5)
        outside_low_k_share = (outside_low_k / outside_top3) if outside_top3 else 0.0

        if outside_top3 == 0 and not strategy_pairs:
            verdict = "KEEP_TOP3"
            reasons = ["No selected strategy came from outside the initial Top3."]
        elif outside_top3 < 3 or len(strategy_pairs) < 5:
            verdict = "INCONCLUSIVE"
            reasons = ["Too few outside-Top3 or changed-strategy cases for a stable policy decision."]
        elif (
            (pair_r20 is not None and pair_r20 > 0.05)
            and (top5_r_delta is not None and top5_r_delta >= 0.0)
            and (top5_stop_delta is None or top5_stop_delta <= 0.5)
            and len(changed_dates) >= 5
        ):
            if runtime_ratio is not None and runtime_ratio > 1.8 and outside_low_k_share >= 0.8:
                verdict = "CONSIDER_EXPANDED_K"
                reasons = ["Outside-Top3 strategies add value, but most useful reversals are ranks 4-5 and All is materially slower."]
            else:
                verdict = "CONSIDER_ALL"
                reasons = ["Outside-Top3 selections show repeated paired-R improvement without a material Top5 stop-rate penalty."]
        elif (
            (pair_r20 is not None and pair_r20 <= 0.0)
            and (top5_r_delta is not None and top5_r_delta <= 0.0)
        ):
            verdict = "KEEP_TOP3"
            reasons = ["Expanded strategy search did not improve paired or Top5 20D R outcomes."]
        else:
            verdict = "INCONCLUSIVE"
            reasons = ["Strategy-search changes exist, but quality deltas are not consistently strong enough for a production policy change."]

        return {
            "audit_version": AUDIT_VERSION,
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "scanner_version": str(getattr(self.scanner, "VERSION", "unknown")),
            "market_scope": market_scope.upper(),
            "evaluation_dates": [value.isoformat() for value in dates],
            "valid_date_count": len(valid),
            "skipped_date_count": len(runs) - len(valid),
            "quick_policy": {
                "market_limit": int(self.scanner.QUICK_LIMIT_PER_MARKET),
                "quick_limit": int(quick_limit or self.scanner.DEEP_LIMIT),
            },
            "variants": [
                StrategySearchVariant("BASELINE_TOP3", 3).to_dict(),
                StrategySearchVariant("ALL_STRATEGIES", None).to_dict(),
            ],
            "aggregate": aggregate,
            "strategy_search_validation": {
                "valid_dates": len(valid),
                "total_selected_signals": total_selected,
                "strategy_changed_date_count": len(changed_dates),
                "strategy_changed_dates": changed_dates,
                "strategy_changed_signal_count": len(strategy_pairs),
                "strategy_changed_signal_rate_pct": _pct(len(strategy_pairs), total_selected),
                "outside_top3_selected_count": outside_top3,
                "outside_top3_selected_rate_pct": _pct(outside_top3, total_selected),
                "outside_top3_ready_count": outside_top3_ready,
                "tier_improvement_count": tier_improvements,
                "top5_changed_date_count": len(top5_changed_dates),
                "top5_changed_date_rate_pct": _pct(len(top5_changed_dates), len(valid)),
                "top5_changed_dates": top5_changed_dates,
                "baseline_parity_mismatches": parity_mismatches,
                "date_level_delta": {
                    key: {
                        "mean_return_delta_pct": _mean(date_deltas[key]),
                        "median_return_delta_pct": _median(date_deltas[key]),
                        "trimmed_mean_return_delta_pct": _trimmed_mean(date_deltas[key]),
                        "mean_r_delta": _mean(r_deltas[key]),
                        "median_r_delta": _median(r_deltas[key]),
                        "trimmed_mean_r_delta": _trimmed_mean(r_deltas[key]),
                        "mean_stop_first_delta_pct": _mean(stop_deltas[key]),
                        "mean_target1_first_delta_pct": _mean(target_deltas[key]),
                    }
                    for key in date_deltas
                },
                "paired_strategy_outcome": pair_summary,
                "runtime": {
                    "top3_mean_current_evaluation_seconds": baseline_runtime,
                    "all_mean_current_evaluation_seconds": all_runtime,
                    "all_minus_top3_seconds": None if runtime_ratio is None else round(all_runtime - baseline_runtime, 6),
                    "all_over_top3_ratio": None if runtime_ratio is None else round(runtime_ratio, 4),
                },
                "outside_top3_rank_distribution": outside_rank_counts,
                "outside_rank4_5_share": round(outside_low_k_share, 4),
                "verdict": verdict,
                "verdict_reasons": reasons,
            },
            "strategy_pairs": strategy_pairs,
            "runs": runs,
            "runtime_seconds": round(time.perf_counter() - started, 6),
        }


def compact_strategy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep evidence needed for review without repeating full strategy traces twice."""
    compact = dict(payload)
    compact_runs: list[dict[str, Any]] = []
    for run in payload.get("runs") or []:
        item = dict(run)
        trace = item.pop("strategy_trace", None)
        if trace:
            # Keep only changed or outside-Top3 symbols in the persistent JSON.
            reduced: dict[str, Any] = {}
            for key, record in trace.items():
                variants = record.get("variants") or {}
                base = variants.get("BASELINE_TOP3") or {}
                allv = variants.get("ALL_STRATEGIES") or {}
                if (
                    base.get("selected_strategy") != allv.get("selected_strategy")
                    or int(allv.get("selected_initial_rank") or 0) > 3
                    or not bool(record.get("baseline_parity", True))
                ):
                    reduced[key] = record
            item["strategy_trace"] = reduced
        compact_runs.append(item)
    compact["runs"] = compact_runs
    return compact


def write_strategy_outputs(payload: dict[str, Any], *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"scanner-strategy-audit_{stamp}.json"
    signals_path = output_dir / f"scanner-strategy-signals_{stamp}.csv"
    pairs_path = output_dir / f"scanner-strategy-pairs_{stamp}.csv"
    md_path = output_dir / f"scanner-strategy-summary_{stamp}.md"

    json_path.write_text(json.dumps(_safe_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    signal_fields = [
        "analysis_date", "variant", "rank", "market", "code", "name", "selected_strategy",
        "initial_strategy_rank", "candidate_state", "risk_status", "missing_conditions",
        "return_5d", "r_5d", "event_5d", "return_10d", "r_10d", "event_10d",
        "return_20d", "r_20d", "event_20d",
    ]
    with signals_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=signal_fields)
        writer.writeheader()
        for run in payload.get("runs") or []:
            if run.get("status") != "OK":
                continue
            for variant_name, variant in (run.get("variants") or {}).items():
                for candidate in variant.get("candidates") or []:
                    row = {
                        "analysis_date": run.get("analysis_date"),
                        "variant": variant_name,
                        "rank": candidate.get("rank"),
                        "market": candidate.get("market"),
                        "code": candidate.get("code"),
                        "name": candidate.get("name"),
                        "selected_strategy": candidate.get("strategy"),
                        "initial_strategy_rank": candidate.get("initial_strategy_rank"),
                        "candidate_state": candidate.get("candidate_state"),
                        "risk_status": (candidate.get("risk") or {}).get("status"),
                        "missing_conditions": (candidate.get("conditions") or {}).get("missing"),
                    }
                    for horizon in (5, 10, 20):
                        metric = _forward(candidate, horizon)
                        row[f"return_{horizon}d"] = metric.get("return_pct")
                        row[f"r_{horizon}d"] = metric.get("event_r")
                        row[f"event_{horizon}d"] = _event(candidate, horizon)
                    writer.writerow(row)

    pair_fields = [
        "analysis_date", "market", "code", "name", "baseline_strategy", "all_strategy", "all_initial_rank",
        "baseline_state", "all_state", "baseline_risk", "all_risk", "baseline_missing", "all_missing",
        "return_5d_delta", "r_5d_delta", "baseline_event_5d", "all_event_5d",
        "return_10d_delta", "r_10d_delta", "baseline_event_10d", "all_event_10d",
        "return_20d_delta", "r_20d_delta", "baseline_event_20d", "all_event_20d",
    ]
    with pairs_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_fields)
        writer.writeheader()
        for pair in payload.get("strategy_pairs") or []:
            writer.writerow({key: pair.get(key) for key in pair_fields})

    validation = payload.get("strategy_search_validation") or {}
    runtime = validation.get("runtime") or {}
    delta = validation.get("date_level_delta") or {}
    pair = validation.get("paired_strategy_outcome") or {}
    lines = [
        f"# Scanner Strategy Search Audit — {payload.get('audit_version')}",
        "",
        f"- Scanner version: `{payload.get('scanner_version')}`",
        f"- Market scope: `{payload.get('market_scope')}`",
        f"- Valid dates: **{payload.get('valid_date_count')}** / {len(payload.get('evaluation_dates') or [])}",
        f"- Strategy-changed dates: **{validation.get('strategy_changed_date_count')}**",
        f"- Strategy-changed signals: **{validation.get('strategy_changed_signal_count')}** ({validation.get('strategy_changed_signal_rate_pct')}%)",
        f"- Outside Top3 selected: **{validation.get('outside_top3_selected_count')}** ({validation.get('outside_top3_selected_rate_pct')}%)",
        f"- Top5 changed dates: **{validation.get('top5_changed_date_count')}** ({validation.get('top5_changed_date_rate_pct')}%)",
        f"- Baseline parity mismatches: **{validation.get('baseline_parity_mismatches')}**",
        f"- Verdict: **{validation.get('verdict')}**",
        "",
        "## Top5 date-level delta (All - Top3)",
        "",
        "| Horizon | Mean return Δ | Median return Δ | Trimmed return Δ | Mean R Δ | Stop-first Δ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for horizon in (5, 10, 20):
        item = delta.get(str(horizon)) or {}
        lines.append(
            f"| {horizon}D | {item.get('mean_return_delta_pct')} | {item.get('median_return_delta_pct')} | "
            f"{item.get('trimmed_mean_return_delta_pct')} | {item.get('mean_r_delta')} | {item.get('mean_stop_first_delta_pct')} |"
        )
    lines += [
        "",
        "## Changed-strategy paired outcome",
        "",
        "| Horizon | Pair count | Mean R Δ | Median R Δ | Mean return Δ |",
        "|---|---:|---:|---:|---:|",
    ]
    for horizon in (5, 10, 20):
        item = pair.get(str(horizon)) or {}
        lines.append(
            f"| {horizon}D | {item.get('count')} | {item.get('mean_r_delta')} | {item.get('median_r_delta')} | {item.get('mean_return_delta_pct')} |"
        )
    lines += [
        "",
        "## Runtime cost",
        "",
        f"- Top3 current-eval mean: **{runtime.get('top3_mean_current_evaluation_seconds')}s**",
        f"- All current-eval mean: **{runtime.get('all_mean_current_evaluation_seconds')}s**",
        f"- All / Top3: **{runtime.get('all_over_top3_ratio')}x**",
        "",
        "## Verdict reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in (validation.get("verdict_reasons") or []))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "json": str(json_path),
        "csv": str(signals_path),
        "pairs_csv": str(pairs_path),
        "markdown": str(md_path),
    }
