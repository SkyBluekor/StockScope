from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any, Callable

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
from app.backtest.scanner_quality.strategy_search_audit import StrategySearchAuditor

KST = timezone(timedelta(hours=9), name="KST")
AUDIT_VERSION = "v0.21.4-B.2.3.4c.3a"
BASELINE = "BASELINE_PREPOOL_TOP3"
EXPANDED = "PREPOOL_ALL_STRATEGIES"


@dataclass(frozen=True)
class PrepoolStrategyVariant:
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
    lval = _float(left)
    rval = _float(right)
    if lval is None or rval is None:
        return None
    return round(lval - rval, 6)


def _forward(candidate: dict[str, Any] | None, horizon: int) -> dict[str, Any]:
    if not candidate:
        return {}
    return ((((candidate.get("outcome") or {}).get("forward") or {}).get(str(horizon))) or {})


def _event(candidate: dict[str, Any] | None, horizon: int) -> str | None:
    status = ((_forward(candidate, horizon).get("event") or {}).get("status"))
    return str(status) if status else None


def _status(candidate: dict[str, Any] | None) -> str | None:
    if not candidate:
        return None
    value = candidate.get("candidate_state") or candidate.get("action")
    return str(value) if value else None


def _risk_status(candidate: dict[str, Any] | None) -> str | None:
    if not candidate:
        return None
    value = (candidate.get("risk") or {}).get("status")
    return str(value) if value else None


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


def _selected_initial_rank(trace: list[dict[str, Any]], strategy: Any) -> int | None:
    wanted = str(strategy or "")
    for record in trace:
        if str(record.get("strategy") or "") == wanted:
            try:
                return int(record.get("initial_rank"))
            except (TypeError, ValueError):
                return None
    return None


class PrepoolStrategyAuditor:
    """Offline audit of Top3-vs-All strategy evaluation *before* Quick18 selection.

    Baseline quick items come directly from production ``_quick_current_candidate``.
    Expanded quick items reuse the c.3 strategy evaluator with ``strategy_limit=None``.
    Market pre-filter, Quick18 limit, current-candidate conversion and final ranking are unchanged.
    """

    def __init__(self, scanner: Any, market_store: Any) -> None:
        self.scanner = scanner
        self.market_store = market_store
        self.strategy_helper = StrategySearchAuditor(scanner, market_store)

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
            if not codes:
                continue
            series_map = self.market_store.stock_series_many(market, sorted(codes), start, end)
            for code, series in series_map.items():
                result[(market, code)] = sorted(
                    (dict(row) for row in series.rows.values()),
                    key=_row_date,
                )
        return result

    @staticmethod
    def _aggregate_top_metrics(candidates: list[dict[str, Any]], horizons: tuple[int, ...]) -> dict[str, Any]:
        result: dict[str, Any] = {"count": len(candidates), "horizons": {}}
        for horizon in horizons:
            returns: list[float] = []
            mfes: list[float] = []
            maes: list[float] = []
            rs: list[float] = []
            target_first = 0
            stop_first = 0
            complete = 0
            for candidate in candidates:
                metric = _forward(candidate, horizon)
                if not metric.get("complete"):
                    continue
                complete += 1
                for bucket, key in ((returns, "return_pct"), (mfes, "mfe_pct"), (maes, "mae_pct"), (rs, "event_r")):
                    value = _float(metric.get(key))
                    if value is not None:
                        bucket.append(value)
                status = str((metric.get("event") or {}).get("status") or "")
                target_first += int(status == "TARGET1_FIRST")
                stop_first += int(status == "STOP_FIRST")
            result["horizons"][str(horizon)] = {
                "complete": complete,
                "mean_return_pct": _mean(returns),
                "median_return_pct": _median(returns),
                "mean_mfe_pct": _mean(mfes),
                "mean_mae_pct": _mean(maes),
                "mean_event_r": _mean(rs),
                "median_event_r": _median(rs),
                "target1_first_pct": _pct(target_first, complete),
                "stop_first_pct": _pct(stop_first, complete),
            }
        return result

    def run_date(
        self,
        *,
        as_of: date,
        market_scope: str = "ALL",
        horizons: AuditHorizons = AuditHorizons(),
        market_limit: int | None = None,
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

        market_limit_value = int(market_limit or self.scanner.QUICK_LIMIT_PER_MARKET)
        quick_limit_value = int(quick_limit or self.scanner.DEEP_LIMIT)
        fast_start = as_of - timedelta(days=int(self.scanner.FAST_HISTORY_CALENDAR_DAYS))
        latest_key = _compact(as_of)
        horizons_tuple = horizons.normalized()

        index_rows_by_market: dict[str, list[dict[str, Any]]] = {}
        row_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        history_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        baseline_quick_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        all_quick_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        trace: dict[tuple[str, str], dict[str, Any]] = {}
        special_excluded = 0
        liquidity_filtered = 0
        data_insufficient = 0
        baseline_seconds = 0.0
        all_seconds = 0.0
        baseline_eval_count = 0
        all_strategy_eval_count = 0

        for market in markets:
            ordinary: list[dict[str, Any]] = []
            for raw_row in self.market_store.stock_day_rows(market, latest_key):
                row = dict(raw_row)
                code = str(row.get("code") or "")
                reason = self.scanner._special_reason(row)  # noqa: SLF001
                if reason is not None:
                    special_excluded += 1
                    continue
                if float(row.get("trade_value") or 0.0) < self.scanner.engine.LIQUIDITY_THRESHOLD:
                    liquidity_filtered += 1
                    continue
                ordinary.append(row)
            ordinary.sort(
                key=lambda item: (float(item.get("trade_value") or 0.0), float(item.get("market_cap") or 0.0)),
                reverse=True,
            )
            prefiltered = ordinary[:market_limit_value]
            index_series = self.market_store.index_series(market, _compact(fast_start), latest_key)
            index_rows = sorted((dict(row) for row in index_series.rows.values()), key=_row_date)
            index_rows_by_market[market] = index_rows
            series_map = self.market_store.stock_series_many(
                market,
                [str(row.get("code") or "") for row in prefiltered],
                _compact(fast_start),
                latest_key,
            )
            for market_rank, row in enumerate(prefiltered, start=1):
                code = str(row.get("code") or "")
                key = (market, code)
                series = series_map.get(code)
                stock_rows = sorted(
                    (dict(item) for item in ((series.rows.values()) if series is not None else [])),
                    key=_row_date,
                )
                row_by_key[key] = row
                history_by_key[key] = stock_rows

                base_started = time.perf_counter()
                baseline_quick = self.scanner._quick_current_candidate(  # noqa: SLF001
                    market=market,
                    latest_date=latest_key,
                    row=row,
                    stock_rows=stock_rows,
                    index_rows=index_rows,
                )
                baseline_seconds += time.perf_counter() - base_started
                baseline_eval_count += 1

                all_started = time.perf_counter()
                all_quick, all_trace, _ = self.strategy_helper._evaluate_strategy_search(  # noqa: SLF001
                    market=market,
                    latest_date=latest_key,
                    row=row,
                    stock_rows=stock_rows,
                    index_rows=index_rows,
                    strategy_limit=None,
                )
                all_seconds += time.perf_counter() - all_started
                all_strategy_eval_count += sum(1 for record in all_trace if record.get("current_evaluated"))

                if baseline_quick is not None:
                    baseline_quick_by_key[key] = baseline_quick
                if all_quick is not None:
                    all_quick_by_key[key] = all_quick
                if baseline_quick is None and all_quick is None:
                    data_insufficient += 1

                baseline_strategy = None if baseline_quick is None else baseline_quick.get("quick_strategy")
                baseline_initial_rank = _selected_initial_rank(all_trace, baseline_strategy)
                all_initial_rank = None if all_quick is None else all_quick.get("_audit_initial_strategy_rank")
                trace[key] = {
                    "market_rank": market_rank,
                    "trade_value": row.get("trade_value"),
                    "market_cap": row.get("market_cap"),
                    "baseline": {
                        "quick_score": None if baseline_quick is None else baseline_quick.get("quick_score"),
                        "selected_strategy": baseline_strategy,
                        "selected_initial_rank": baseline_initial_rank,
                    },
                    "all": {
                        "quick_score": None if all_quick is None else all_quick.get("quick_score"),
                        "selected_strategy": None if all_quick is None else all_quick.get("quick_strategy"),
                        "selected_initial_rank": all_initial_rank,
                    },
                }

        def ordered(items: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
            result = list(items.values())
            result.sort(
                key=lambda item: (float(item.get("quick_score") or 0.0), float(item.get("trade_value") or 0.0)),
                reverse=True,
            )
            return result

        baseline_quick = ordered(baseline_quick_by_key)
        all_quick = ordered(all_quick_by_key)
        baseline_rank = {
            (str(item.get("market") or ""), str(item.get("code") or "")): index
            for index, item in enumerate(baseline_quick, start=1)
        }
        all_rank = {
            (str(item.get("market") or ""), str(item.get("code") or "")): index
            for index, item in enumerate(all_quick, start=1)
        }
        baseline_selected = baseline_quick[:quick_limit_value]
        all_selected = all_quick[:quick_limit_value]
        baseline_selected_keys = {(str(item.get("market") or ""), str(item.get("code") or "")) for item in baseline_selected}
        all_selected_keys = {(str(item.get("market") or ""), str(item.get("code") or "")) for item in all_selected}
        entrants = all_selected_keys - baseline_selected_keys
        dropped = baseline_selected_keys - all_selected_keys

        for key, state in trace.items():
            state["baseline"]["quick_rank"] = baseline_rank.get(key)
            state["baseline"]["quick_pool"] = key in baseline_selected_keys
            state["all"]["quick_rank"] = all_rank.get(key)
            state["all"]["quick_pool"] = key in all_selected_keys
            state["pool_changed"] = (key in baseline_selected_keys) != (key in all_selected_keys)
            state["rescued"] = (
                key in entrants
                and isinstance(state["all"].get("selected_initial_rank"), int)
                and int(state["all"]["selected_initial_rank"]) >= 4
            )

        variants = {
            BASELINE: (PrepoolStrategyVariant(BASELINE, 3), baseline_selected),
            EXPANDED: (PrepoolStrategyVariant(EXPANDED, None), all_selected),
        }
        current_by_variant: dict[str, dict[tuple[str, str], dict[str, Any]]] = {BASELINE: {}, EXPANDED: {}}
        ranked_by_variant: dict[str, list[dict[str, Any]]] = {}
        ranking_changes_by_variant: dict[str, list[dict[str, Any]]] = {}
        outcome_codes: dict[str, set[str]] = {market: set() for market in markets}

        for variant_name, (_, selected) in variants.items():
            for quick in selected:
                key = (str(quick.get("market") or ""), str(quick.get("code") or ""))
                current = self.scanner._current_candidate(quick)  # noqa: SLF001
                if current is None:
                    continue
                initial_rank = (trace.get(key) or {}).get("all" if variant_name == EXPANDED else "baseline", {}).get(
                    "selected_initial_rank"
                )
                current["_audit_initial_strategy_rank"] = initial_rank
                current_by_variant[variant_name][key] = current
                outcome_codes.setdefault(key[0], set()).add(key[1])
            actionable = [
                candidate
                for candidate in current_by_variant[variant_name].values()
                if candidate.get("candidate_state") in {"READY", "WATCH", "VALIDATION"}
            ]
            ranked, ranking_changes = rank_candidates(actionable)
            ranked_by_variant[variant_name] = ranked
            ranking_changes_by_variant[variant_name] = ranking_changes

        future_rows = self._future_rows_many(
            codes_by_market=outcome_codes,
            as_of=as_of,
            max_horizon=max(horizons_tuple),
        )

        # Attach outcome to every selected current candidate so Quick18 replacement pairs can be evaluated
        # even when one of them does not survive to final Top5.
        outcome_by_variant: dict[str, dict[tuple[str, str], dict[str, Any]]] = {BASELINE: {}, EXPANDED: {}}
        for variant_name, current_map in current_by_variant.items():
            for key, candidate in current_map.items():
                outcome_by_variant[variant_name][key] = _future_metrics(
                    candidate=candidate,
                    future_rows=future_rows.get(key, []),
                    horizons=horizons_tuple,
                )

        variant_results: dict[str, Any] = {}
        final_rank_by_variant: dict[str, dict[tuple[str, str], int]] = {}
        for variant_name, (variant, selected) in variants.items():
            ranked = ranked_by_variant[variant_name]
            snapshots: list[dict[str, Any]] = []
            rank_map: dict[tuple[str, str], int] = {}
            for final_rank_value, candidate in enumerate(ranked, start=1):
                key = (str(candidate.get("market") or ""), str(candidate.get("code") or ""))
                rank_map[key] = final_rank_value
                snap = _candidate_snapshot(candidate, rank=final_rank_value)
                snap["initial_strategy_rank"] = candidate.get("_audit_initial_strategy_rank")
                snap["quick_rank"] = baseline_rank.get(key) if variant_name == BASELINE else all_rank.get(key)
                snap["outcome"] = outcome_by_variant[variant_name].get(key) or {}
                snapshots.append(snap)
            final_rank_by_variant[variant_name] = rank_map
            variant_results[variant_name] = {
                "config": variant.to_dict(),
                "quick_candidate_count": len(baseline_quick if variant_name == BASELINE else all_quick),
                "quick_selected_count": len(selected),
                "actionable_count": len(ranked),
                "candidates": snapshots,
                "ranking_changes": _safe_json(ranking_changes_by_variant[variant_name]),
                "top5_metrics": self._aggregate_top_metrics(snapshots[:5], horizons_tuple),
                "prepool_evaluation_seconds": round(baseline_seconds if variant_name == BASELINE else all_seconds, 6),
            }

        baseline_top5 = set(list(final_rank_by_variant[BASELINE].keys())[:0])
        # rank maps are dicts; derive actual Top5 sets from ranked sequence instead.
        baseline_top5 = {
            (str(item.get("market") or ""), str(item.get("code") or ""))
            for item in variant_results[BASELINE]["candidates"][:5]
        }
        all_top5 = {
            (str(item.get("market") or ""), str(item.get("code") or ""))
            for item in variant_results[EXPANDED]["candidates"][:5]
        }

        rescued_keys = [key for key in entrants if bool((trace.get(key) or {}).get("rescued"))]
        rescued_ready_count = sum(1 for key in rescued_keys if _status(current_by_variant[EXPANDED].get(key)) == "READY")
        rescued_top5_count = sum(1 for key in rescued_keys if key in all_top5)

        # Deterministic replacement pairing. Entrants are ordered by expanded quick rank;
        # displaced baseline names are ordered from the weakest baseline Quick18 boundary upward.
        entrant_keys = sorted(entrants, key=lambda key: (all_rank.get(key, 10**9), key))
        dropped_keys = sorted(dropped, key=lambda key: (-baseline_rank.get(key, -1), key))
        replacement_pairs: list[dict[str, Any]] = []
        for entrant, displaced in zip_longest(entrant_keys, dropped_keys):
            entrant_state = trace.get(entrant) if entrant is not None else None
            dropped_state = trace.get(displaced) if displaced is not None else None
            entrant_current = current_by_variant[EXPANDED].get(entrant) if entrant is not None else None
            dropped_current = current_by_variant[BASELINE].get(displaced) if displaced is not None else None
            entrant_outcome = outcome_by_variant[EXPANDED].get(entrant, {}) if entrant is not None else {}
            dropped_outcome = outcome_by_variant[BASELINE].get(displaced, {}) if displaced is not None else {}
            pair = {
                "analysis_date": as_of.isoformat(),
                "entrant_market": None if entrant is None else entrant[0],
                "entrant_code": None if entrant is None else entrant[1],
                "entrant_name": None if entrant is None else (row_by_key.get(entrant) or {}).get("name"),
                "entrant_baseline_quick_rank": None if entrant is None else baseline_rank.get(entrant),
                "entrant_all_quick_rank": None if entrant is None else all_rank.get(entrant),
                "entrant_baseline_quick_score": None if not entrant_state else (entrant_state.get("baseline") or {}).get("quick_score"),
                "entrant_all_quick_score": None if not entrant_state else (entrant_state.get("all") or {}).get("quick_score"),
                "entrant_baseline_strategy": None if not entrant_state else (entrant_state.get("baseline") or {}).get("selected_strategy"),
                "entrant_all_strategy": None if not entrant_state else (entrant_state.get("all") or {}).get("selected_strategy"),
                "entrant_all_initial_rank": None if not entrant_state else (entrant_state.get("all") or {}).get("selected_initial_rank"),
                "rescued": bool(entrant_state and entrant_state.get("rescued")),
                "entrant_state": _status(entrant_current),
                "entrant_risk": _risk_status(entrant_current),
                "entrant_missing": _missing(entrant_current),
                "entrant_final_rank": None if entrant is None else final_rank_by_variant[EXPANDED].get(entrant),
                "displaced_market": None if displaced is None else displaced[0],
                "displaced_code": None if displaced is None else displaced[1],
                "displaced_name": None if displaced is None else (row_by_key.get(displaced) or {}).get("name"),
                "displaced_baseline_quick_rank": None if displaced is None else baseline_rank.get(displaced),
                "displaced_all_quick_rank": None if displaced is None else all_rank.get(displaced),
                "displaced_state": _status(dropped_current),
                "displaced_risk": _risk_status(dropped_current),
                "displaced_missing": _missing(dropped_current),
                "displaced_final_rank": None if displaced is None else final_rank_by_variant[BASELINE].get(displaced),
                "entrant_in_top5": bool(entrant is not None and entrant in all_top5),
                "displaced_in_top5": bool(displaced is not None and displaced in baseline_top5),
            }
            for horizon in horizons_tuple:
                entrant_metric = (((entrant_outcome.get("forward") or {}).get(str(horizon))) or {})
                displaced_metric = (((dropped_outcome.get("forward") or {}).get(str(horizon))) or {})
                pair[f"return_{horizon}d_delta"] = _delta(
                    entrant_metric.get("return_pct"), displaced_metric.get("return_pct")
                )
                pair[f"r_{horizon}d_delta"] = _delta(entrant_metric.get("event_r"), displaced_metric.get("event_r"))
                pair[f"entrant_event_{horizon}d"] = str((entrant_metric.get("event") or {}).get("status") or "") or None
                pair[f"displaced_event_{horizon}d"] = str((displaced_metric.get("event") or {}).get("status") or "") or None
            replacement_pairs.append(pair)

        common_keys = set(baseline_rank) & set(all_rank)
        rank_changes = [all_rank[key] - baseline_rank[key] for key in common_keys]
        abs_changes = [abs(value) for value in rank_changes]
        rank_up_count = sum(1 for value in rank_changes if value < 0)
        rank_down_count = sum(1 for value in rank_changes if value > 0)
        all_new_rank_distribution: dict[str, int] = {}
        rescued_rank_distribution: dict[str, int] = {}
        for key in entrants:
            rank_value = (trace.get(key) or {}).get("all", {}).get("selected_initial_rank")
            if rank_value is not None:
                rank_key = str(rank_value)
                all_new_rank_distribution[rank_key] = all_new_rank_distribution.get(rank_key, 0) + 1
        for key in rescued_keys:
            rank_value = (trace.get(key) or {}).get("all", {}).get("selected_initial_rank")
            if rank_value is not None:
                rank_key = str(rank_value)
                rescued_rank_distribution[rank_key] = rescued_rank_distribution.get(rank_key, 0) + 1

        return {
            "analysis_date": as_of.isoformat(),
            "status": "OK",
            "market_scope": market_scope.upper(),
            "fast_history_start": fast_start.isoformat(),
            "universe_total": sum(len(self.market_store.stock_day_rows(market, latest_key)) for market in markets),
            "special_excluded": special_excluded,
            "liquidity_filtered": liquidity_filtered,
            "data_insufficient": data_insufficient,
            "market_limit": market_limit_value,
            "quick_limit": quick_limit_value,
            "variants": variant_results,
            "quick_pool_changed": bool(entrants or dropped),
            "quick_pool_replacement_count": max(len(entrants), len(dropped)),
            "quick_pool_overlap_count": len(baseline_selected_keys & all_selected_keys),
            "entrant_count": len(entrants),
            "dropped_count": len(dropped),
            "rescued_candidate_count": len(rescued_keys),
            "rescued_ready_count": rescued_ready_count,
            "rescued_top5_count": rescued_top5_count,
            "top5_changed": baseline_top5 != all_top5,
            "top5_replacement_count": max(len(all_top5 - baseline_top5), len(baseline_top5 - all_top5)),
            "rank_movement": {
                "common_count": len(common_keys),
                "mean_absolute_rank_change": _mean([float(v) for v in abs_changes]),
                "median_absolute_rank_change": _median([float(v) for v in abs_changes]),
                "rank_up_count": rank_up_count,
                "rank_down_count": rank_down_count,
                "rank_up_ge_5": sum(1 for value in rank_changes if value <= -5),
                "rank_up_ge_10": sum(1 for value in rank_changes if value <= -10),
                "rank_up_into_top18": len(entrants),
                "rank_down_out_of_top18": len(dropped),
            },
            "new_pool_strategy_rank_distribution": all_new_rank_distribution,
            "rescued_strategy_rank_distribution": rescued_rank_distribution,
            "runtime": {
                "baseline_prepool_seconds": round(baseline_seconds, 6),
                "all_prepool_seconds": round(all_seconds, 6),
                "baseline_symbol_evaluations": baseline_eval_count,
                "all_current_strategy_evaluations": all_strategy_eval_count,
            },
            "replacement_pairs": replacement_pairs,
            "trace": {f"{market}:{code}": _safe_json(value) for (market, code), value in sorted(trace.items())},
            "runtime_seconds": round(time.perf_counter() - started, 6),
        }

    def run_dates(
        self,
        *,
        dates: list[date],
        market_scope: str = "ALL",
        horizons: AuditHorizons = AuditHorizons(),
        market_limit: int | None = None,
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
                market_limit=market_limit,
                quick_limit=quick_limit,
            )
            runs.append(run)
            if progress_callback is not None:
                progress_callback(index, len(dates), as_of, run)

        valid = [run for run in runs if run.get("status") == "OK"]
        horizons_tuple = horizons.normalized()
        variants = (BASELINE, EXPANDED)

        aggregate: dict[str, Any] = {}
        for variant in variants:
            daily_returns: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
            daily_rs: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
            target_total: dict[str, int] = {str(h): 0 for h in horizons_tuple}
            stop_total: dict[str, int] = {str(h): 0 for h in horizons_tuple}
            complete_total: dict[str, int] = {str(h): 0 for h in horizons_tuple}
            prepool_seconds: list[float] = []
            for run in valid:
                result = ((run.get("variants") or {}).get(variant) or {})
                prepool_seconds.append(float(result.get("prepool_evaluation_seconds") or 0.0))
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
                "mean_prepool_evaluation_seconds": _mean(prepool_seconds),
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

        changed_dates = [run["analysis_date"] for run in valid if run.get("quick_pool_changed")]
        top5_changed_dates = [run["analysis_date"] for run in valid if run.get("top5_changed")]
        replacement_pairs = [pair for run in valid for pair in (run.get("replacement_pairs") or [])]
        rescued_pairs = [pair for pair in replacement_pairs if pair.get("rescued")]
        total_replacements = sum(int(run.get("quick_pool_replacement_count") or 0) for run in valid)
        rescued_count = sum(int(run.get("rescued_candidate_count") or 0) for run in valid)
        rescued_ready = sum(int(run.get("rescued_ready_count") or 0) for run in valid)
        rescued_top5 = sum(int(run.get("rescued_top5_count") or 0) for run in valid)
        rescued_dates = [run["analysis_date"] for run in valid if int(run.get("rescued_candidate_count") or 0) > 0]

        date_deltas: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
        r_deltas: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
        stop_deltas: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
        target_deltas: dict[str, list[float]] = {str(h): [] for h in horizons_tuple}
        for run in valid:
            base = (((run.get("variants") or {}).get(BASELINE) or {}).get("top5_metrics") or {}).get("horizons") or {}
            expanded = (((run.get("variants") or {}).get(EXPANDED) or {}).get("top5_metrics") or {}).get("horizons") or {}
            for horizon in horizons_tuple:
                key = str(horizon)
                for bucket, metric in (
                    (date_deltas, "mean_return_pct"),
                    (r_deltas, "mean_event_r"),
                    (stop_deltas, "stop_first_pct"),
                    (target_deltas, "target1_first_pct"),
                ):
                    value = _delta((expanded.get(key) or {}).get(metric), (base.get(key) or {}).get(metric))
                    if value is not None:
                        bucket[key].append(value)

        paired_summary: dict[str, Any] = {}
        rescued_paired_summary: dict[str, Any] = {}
        for horizon in horizons_tuple:
            key = str(horizon)
            for target, pairs in ((paired_summary, replacement_pairs), (rescued_paired_summary, rescued_pairs)):
                return_values = [_float(pair.get(f"return_{horizon}d_delta")) for pair in pairs]
                r_values = [_float(pair.get(f"r_{horizon}d_delta")) for pair in pairs]
                return_values = [value for value in return_values if value is not None]
                r_values = [value for value in r_values if value is not None]
                target[key] = {
                    "count": len(return_values),
                    "mean_return_delta_pct": _mean(return_values),
                    "median_return_delta_pct": _median(return_values),
                    "trimmed_mean_return_delta_pct": _trimmed_mean(return_values),
                    "mean_r_delta": _mean(r_values),
                    "median_r_delta": _median(r_values),
                    "trimmed_mean_r_delta": _trimmed_mean(r_values),
                    "positive_r_count": sum(1 for value in r_values if value > 0),
                    "negative_r_count": sum(1 for value in r_values if value < 0),
                }

        base_runtime = _float((aggregate.get(BASELINE) or {}).get("mean_prepool_evaluation_seconds")) or 0.0
        all_runtime = _float((aggregate.get(EXPANDED) or {}).get("mean_prepool_evaluation_seconds")) or 0.0
        runtime_ratio = (all_runtime / base_runtime) if base_runtime > 0 else None

        rescued_rank_distribution: dict[int, int] = {}
        for run in valid:
            for rank, count in (run.get("rescued_strategy_rank_distribution") or {}).items():
                rescued_rank_distribution[int(rank)] = rescued_rank_distribution.get(int(rank), 0) + int(count)
        rank4_5_count = sum(count for rank, count in rescued_rank_distribution.items() if rank in {4, 5})
        rank4_5_share = (rank4_5_count / rescued_count) if rescued_count else 0.0

        top5_20_base = (((aggregate.get(BASELINE) or {}).get("top5") or {}).get("20") or {})
        top5_20_all = (((aggregate.get(EXPANDED) or {}).get("top5") or {}).get("20") or {})
        top5_r20_delta = _delta(top5_20_all.get("mean_of_daily_mean_event_r"), top5_20_base.get("mean_of_daily_mean_event_r"))
        top5_return20_delta = _delta(top5_20_all.get("mean_of_daily_mean_return_pct"), top5_20_base.get("mean_of_daily_mean_return_pct"))
        top5_stop20_delta = _delta(top5_20_all.get("stop_first_pct"), top5_20_base.get("stop_first_pct"))
        rescued_r20 = _float((rescued_paired_summary.get("20") or {}).get("mean_r_delta"))

        if not changed_dates and rescued_count == 0:
            verdict = "KEEP_TOP3_PREPOOL"
            reasons = ["Top3 and All produced the same Quick18 pool on every valid date."]
        elif rescued_count == 0:
            verdict = "INCONCLUSIVE"
            reasons = ["Quick18 changed, but no change was caused by an outside-Top3 selected strategy."]
        elif rescued_count < 3 or len(rescued_dates) < 3:
            verdict = "INCONCLUSIVE"
            reasons = ["Outside-Top3 rescues exist, but too few dates/cases were observed for a stable policy change."]
        elif (
            rescued_top5 > 0
            and rescued_r20 is not None
            and rescued_r20 > 0.05
            and top5_r20_delta is not None
            and top5_r20_delta >= 0.0
            and (top5_stop20_delta is None or top5_stop20_delta <= 0.5)
        ):
            if runtime_ratio is not None and runtime_ratio > 1.8 and rank4_5_share >= 0.8:
                verdict = "CONSIDER_EXPANDED_K"
                reasons = ["Pre-pool outside-Top3 rescues add value, but most useful rescues are ranks 4-5 and All is materially slower."]
            else:
                verdict = "CONSIDER_ALL_PREPOOL"
                reasons = ["Outside-Top3 pre-pool rescues repeatedly reach Quick18/Top5 with positive paired 20D R and no material stop penalty."]
        elif (
            rescued_r20 is not None
            and rescued_r20 <= 0.0
            and top5_r20_delta is not None
            and top5_r20_delta <= 0.0
        ):
            verdict = "KEEP_TOP3_PREPOOL"
            reasons = ["Pre-pool rescues did not improve paired or Top5 20D outcomes."]
        else:
            verdict = "INCONCLUSIVE"
            reasons = ["Pre-pool changes exist, but quality deltas are not consistently strong enough for a production change."]

        rank_movement_values = [run.get("rank_movement") or {} for run in valid]
        baseline_strategy_evals = sum(int((run.get("runtime") or {}).get("baseline_symbol_evaluations") or 0) for run in valid)
        all_strategy_evals = sum(int((run.get("runtime") or {}).get("all_current_strategy_evaluations") or 0) for run in valid)

        return {
            "audit_version": AUDIT_VERSION,
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "scanner_version": str(getattr(self.scanner, "VERSION", "unknown")),
            "market_scope": market_scope.upper(),
            "evaluation_dates": [value.isoformat() for value in dates],
            "valid_date_count": len(valid),
            "skipped_date_count": len(runs) - len(valid),
            "policy": {
                "market_limit": int(market_limit or self.scanner.QUICK_LIMIT_PER_MARKET),
                "quick_limit": int(quick_limit or self.scanner.DEEP_LIMIT),
            },
            "variants": [
                PrepoolStrategyVariant(BASELINE, 3).to_dict(),
                PrepoolStrategyVariant(EXPANDED, None).to_dict(),
            ],
            "aggregate": aggregate,
            "prepool_strategy_validation": {
                "valid_dates": len(valid),
                "quick_pool_changed_date_count": len(changed_dates),
                "quick_pool_changed_rate_pct": _pct(len(changed_dates), len(valid)),
                "quick_pool_changed_dates": changed_dates,
                "total_quick_pool_replacements": total_replacements,
                "average_replacements_per_changed_date": round(total_replacements / len(changed_dates), 6) if changed_dates else 0.0,
                "max_replacements_on_one_date": max((int(run.get("quick_pool_replacement_count") or 0) for run in valid), default=0),
                "rescued_candidate_count": rescued_count,
                "rescued_candidate_date_count": len(rescued_dates),
                "rescued_candidate_rate_per_replacement_pct": _pct(rescued_count, total_replacements),
                "rescued_ready_count": rescued_ready,
                "rescued_top5_count": rescued_top5,
                "top5_changed_date_count": len(top5_changed_dates),
                "top5_changed_rate_pct": _pct(len(top5_changed_dates), len(valid)),
                "top5_changed_dates": top5_changed_dates,
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
                "replacement_paired_outcome": paired_summary,
                "rescued_paired_outcome": rescued_paired_summary,
                "rescued_strategy_rank_distribution": rescued_rank_distribution,
                "rescued_rank4_5_share": round(rank4_5_share, 4),
                "rank_movement": {
                    "mean_of_daily_mean_absolute_rank_change": _mean([
                        _float(item.get("mean_absolute_rank_change")) for item in rank_movement_values
                        if _float(item.get("mean_absolute_rank_change")) is not None
                    ]),
                    "mean_rank_up_ge_5_per_date": _mean([float(item.get("rank_up_ge_5") or 0) for item in rank_movement_values]),
                    "mean_rank_up_ge_10_per_date": _mean([float(item.get("rank_up_ge_10") or 0) for item in rank_movement_values]),
                },
                "runtime": {
                    "baseline_mean_prepool_seconds": base_runtime,
                    "all_mean_prepool_seconds": all_runtime,
                    "all_minus_baseline_seconds": None if runtime_ratio is None else round(all_runtime - base_runtime, 6),
                    "all_over_baseline_ratio": None if runtime_ratio is None else round(runtime_ratio, 4),
                    "baseline_symbol_evaluations": baseline_strategy_evals,
                    "all_current_strategy_evaluations": all_strategy_evals,
                },
                "verdict": verdict,
                "verdict_reasons": reasons,
                "headline_20d": {
                    "top5_return_delta_pct": top5_return20_delta,
                    "top5_r_delta": top5_r20_delta,
                    "top5_stop_first_delta_pct": top5_stop20_delta,
                    "rescued_pair_mean_r_delta": rescued_r20,
                },
            },
            "replacement_pairs": replacement_pairs,
            "runs": runs,
            "runtime_seconds": round(time.perf_counter() - started, 6),
        }


def compact_prepool_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist only trace rows that explain a pool change/rescue; keep all metrics and pairs."""
    compact = dict(payload)
    compact_runs: list[dict[str, Any]] = []
    for run in payload.get("runs") or []:
        item = dict(run)
        raw_trace = item.get("trace") or {}
        item["trace"] = {
            key: value
            for key, value in raw_trace.items()
            if bool(value.get("pool_changed")) or bool(value.get("rescued"))
        }
        compact_runs.append(item)
    compact["runs"] = compact_runs
    return compact


def write_prepool_outputs(payload: dict[str, Any], *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"scanner-prepool-strategy-audit_{stamp}.json"
    signals_path = output_dir / f"scanner-prepool-strategy-signals_{stamp}.csv"
    pairs_path = output_dir / f"scanner-prepool-strategy-pairs_{stamp}.csv"
    md_path = output_dir / f"scanner-prepool-strategy-summary_{stamp}.md"

    json_path.write_text(json.dumps(_safe_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    signal_fields = [
        "analysis_date", "variant", "rank", "market", "code", "name", "strategy", "initial_strategy_rank",
        "quick_rank", "candidate_state", "risk_status", "missing_conditions",
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
                        "strategy": candidate.get("strategy"),
                        "initial_strategy_rank": candidate.get("initial_strategy_rank"),
                        "quick_rank": candidate.get("quick_rank"),
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
        "analysis_date", "entrant_market", "entrant_code", "entrant_name",
        "entrant_baseline_quick_rank", "entrant_all_quick_rank",
        "entrant_baseline_quick_score", "entrant_all_quick_score",
        "entrant_baseline_strategy", "entrant_all_strategy", "entrant_all_initial_rank", "rescued",
        "entrant_state", "entrant_risk", "entrant_missing", "entrant_final_rank", "entrant_in_top5",
        "displaced_market", "displaced_code", "displaced_name",
        "displaced_baseline_quick_rank", "displaced_all_quick_rank",
        "displaced_state", "displaced_risk", "displaced_missing", "displaced_final_rank", "displaced_in_top5",
        "return_5d_delta", "r_5d_delta", "entrant_event_5d", "displaced_event_5d",
        "return_10d_delta", "r_10d_delta", "entrant_event_10d", "displaced_event_10d",
        "return_20d_delta", "r_20d_delta", "entrant_event_20d", "displaced_event_20d",
    ]
    with pairs_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_fields)
        writer.writeheader()
        for pair in payload.get("replacement_pairs") or []:
            writer.writerow({key: pair.get(key) for key in pair_fields})

    validation = payload.get("prepool_strategy_validation") or {}
    runtime = validation.get("runtime") or {}
    delta = validation.get("date_level_delta") or {}
    rescued = validation.get("rescued_paired_outcome") or {}
    lines = [
        f"# Scanner Pre-Pool Strategy Search Audit — {payload.get('audit_version')}",
        "",
        f"- Scanner version: `{payload.get('scanner_version')}`",
        f"- Market scope: `{payload.get('market_scope')}`",
        f"- Valid dates: **{payload.get('valid_date_count')}** / {len(payload.get('evaluation_dates') or [])}",
        f"- Quick18 changed dates: **{validation.get('quick_pool_changed_date_count')}** ({validation.get('quick_pool_changed_rate_pct')}%)",
        f"- Rescued candidates: **{validation.get('rescued_candidate_count')}** across **{validation.get('rescued_candidate_date_count')}** dates",
        f"- Rescued READY: **{validation.get('rescued_ready_count')}**",
        f"- Rescued Top5: **{validation.get('rescued_top5_count')}**",
        f"- Top5 changed dates: **{validation.get('top5_changed_date_count')}** ({validation.get('top5_changed_rate_pct')}%)",
        f"- Verdict: **{validation.get('verdict')}**",
        "",
        "## Top5 date-level delta (All pre-pool - Top3 pre-pool)",
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
        "## Rescued-candidate paired outcome",
        "",
        "| Horizon | Pair count | Mean return Δ | Median return Δ | Mean R Δ | Median R Δ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for horizon in (5, 10, 20):
        item = rescued.get(str(horizon)) or {}
        lines.append(
            f"| {horizon}D | {item.get('count')} | {item.get('mean_return_delta_pct')} | "
            f"{item.get('median_return_delta_pct')} | {item.get('mean_r_delta')} | {item.get('median_r_delta')} |"
        )
    lines += [
        "",
        "## Runtime cost",
        "",
        f"- Top3 pre-pool mean: **{runtime.get('baseline_mean_prepool_seconds')}s**",
        f"- All pre-pool mean: **{runtime.get('all_mean_prepool_seconds')}s**",
        f"- All / Top3: **{runtime.get('all_over_baseline_ratio')}x**",
        f"- Baseline symbol evaluations: **{runtime.get('baseline_symbol_evaluations')}**",
        f"- All current-strategy evaluations: **{runtime.get('all_current_strategy_evaluations')}**",
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
