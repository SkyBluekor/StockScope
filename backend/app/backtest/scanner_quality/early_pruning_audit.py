from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from app.backtest.candidate_priority import build_candidate_priority, priority_sort_key, rank_candidates
from app.backtest.scanner_quality.models import AuditHorizons, PruningVariant

KST = timezone(timedelta(hours=9), name="KST")
AUDIT_VERSION = "v0.21.4-B.2.3.4c.2"


def _compact(value: date) -> str:
    return value.strftime("%Y%m%d")


def _iso(compact: str) -> str:
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}" if len(compact) == 8 else compact


def _row_date(row: dict[str, Any]) -> str:
    return str(row.get("date") or row.get("bas_dd") or "").replace("-", "")


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _mean(values: Iterable[float | None]) -> float | None:
    normalized = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return round(statistics.fmean(normalized), 6) if normalized else None


def _median(values: Iterable[float | None]) -> float | None:
    normalized = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return round(statistics.median(normalized), 6) if normalized else None


def _trimmed_mean(values: Iterable[float | None], fraction: float = 0.05) -> float | None:
    normalized = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not normalized:
        return None
    trim = int(len(normalized) * max(0.0, min(float(fraction), 0.45)))
    if trim > 0 and len(normalized) > trim * 2:
        normalized = normalized[trim:-trim]
    return round(statistics.fmean(normalized), 6) if normalized else None


def _delta(left: Any, right: Any) -> float | None:
    left_value = _float(left)
    right_value = _float(right)
    if left_value is None or right_value is None:
        return None
    return round(left_value - right_value, 6)


def _pct(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 4) if denominator else None


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 8) if math.isfinite(value) else None
    return value


def _git_info(project_root: Path) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            completed = subprocess.run(
                ["git", "-C", str(project_root), *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return completed.stdout.strip()

    commit = run("rev-parse", "HEAD")
    branch = run("rev-parse", "--abbrev-ref", "HEAD")
    status = run("status", "--porcelain", "--untracked-files=no")
    return {
        "available": commit is not None,
        "branch": branch,
        "commit": commit,
        "dirty": bool(status) if status is not None else None,
        "dirty_scope": "tracked_files_only",
    }


def _candidate_snapshot(candidate: dict[str, Any], rank: int | None = None) -> dict[str, Any]:
    priority = build_candidate_priority(candidate)
    sort_candidate = dict(candidate)
    sort_candidate["priority"] = priority
    sort_key = list(priority_sort_key(sort_candidate))
    priority_sort = dict(priority.get("_sort") or {})
    guide = candidate.get("entry_risk_guide") or {}
    risk_plan = guide.get("risk") or candidate.get("price_plan") or {}
    return {
        "rank": rank,
        "code": str(candidate.get("code") or ""),
        "name": str(candidate.get("name") or ""),
        "market": str(candidate.get("market") or ""),
        "strategy": candidate.get("strategy"),
        "candidate_state": candidate.get("candidate_state"),
        "action": candidate.get("action"),
        "current_price": candidate.get("current_price"),
        "conditions": _safe_json(candidate.get("conditions") or {}),
        "risk": _safe_json(candidate.get("risk") or {}),
        "entry_gap_pct": priority.get("entry_gap_pct"),
        "entry_gap_basis": priority.get("entry_gap_basis"),
        "priority_tier": priority.get("tier"),
        "strategy_fit_score": candidate.get("_strategy_fit_score"),
        "internal_rank": candidate.get("internal_rank"),
        "final_sort_key": _safe_json(sort_key),
        "price_plan": {
            "entry_reference_price": risk_plan.get("entry_reference_price"),
            "invalidation_price": risk_plan.get("invalidation_price"),
            "stop_zone_low": risk_plan.get("stop_zone_low"),
            "stop_zone_high": risk_plan.get("stop_zone_high"),
            "target1_price": risk_plan.get("target1_price"),
            "target2_price": risk_plan.get("target2_price"),
            "rr1": risk_plan.get("rr1"),
            "rr2": risk_plan.get("rr2"),
        },
    }


def _first_event(
    future_rows: list[dict[str, Any]],
    *,
    target: float | None,
    stop: float | None,
    max_rows: int,
) -> dict[str, Any]:
    if target is None or stop is None or target <= stop:
        return {"status": "UNAVAILABLE", "day": None}
    for index, row in enumerate(future_rows[:max_rows], start=1):
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        if high is None:
            high = _float(row.get("close"))
        if low is None:
            low = _float(row.get("close"))
        hit_target = high is not None and high >= target
        hit_stop = low is not None and low <= stop
        if hit_target and hit_stop:
            return {"status": "AMBIGUOUS_SAME_DAY", "day": index}
        if hit_target:
            return {"status": "TARGET1_FIRST", "day": index}
        if hit_stop:
            return {"status": "STOP_FIRST", "day": index}
    return {"status": "NO_EVENT", "day": None}


def _future_metrics(
    *,
    candidate: dict[str, Any],
    future_rows: list[dict[str, Any]],
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    entry = _float(candidate.get("current_price"))
    guide = candidate.get("entry_risk_guide") or {}
    risk_plan = guide.get("risk") or candidate.get("price_plan") or {}
    entry_reference = _float(risk_plan.get("entry_reference_price")) or entry
    stop = _float(risk_plan.get("invalidation_price"))
    target1 = _float(risk_plan.get("target1_price"))
    rr1 = _float(risk_plan.get("rr1"))
    if entry_reference is None or entry_reference <= 0:
        return {"available": False, "reason": "entry_price_unavailable"}

    result: dict[str, Any] = {
        "available": bool(future_rows),
        "entry_reference_price": entry_reference,
        "stop_reference_price": stop,
        "stop_reference_basis": "invalidation_price" if stop is not None else None,
        "target1_price": target1,
        "forward": {},
    }
    for horizon in horizons:
        sample = future_rows[:horizon]
        if len(sample) < horizon:
            result["forward"][str(horizon)] = {
                "complete": False,
                "rows": len(sample),
                "return_pct": None,
                "mfe_pct": None,
                "mae_pct": None,
                "event": {"status": "INSUFFICIENT_FUTURE_DATA", "day": None},
                "event_r": None,
            }
            continue
        closes = [_float(row.get("close")) for row in sample]
        highs = [(_float(row.get("high")) or _float(row.get("close"))) for row in sample]
        lows = [(_float(row.get("low")) or _float(row.get("close"))) for row in sample]
        final_close = closes[-1]
        return_pct = None if final_close is None else (final_close / entry_reference - 1.0) * 100.0
        valid_highs = [value for value in highs if value is not None]
        valid_lows = [value for value in lows if value is not None]
        mfe = (max(valid_highs) / entry_reference - 1.0) * 100.0 if valid_highs else None
        mae = (min(valid_lows) / entry_reference - 1.0) * 100.0 if valid_lows else None
        event = _first_event(sample, target=target1, stop=stop, max_rows=horizon)
        risk_amount = entry_reference - stop if stop is not None else None
        if event["status"] == "TARGET1_FIRST":
            event_r = rr1
        elif event["status"] == "STOP_FIRST":
            event_r = -1.0
        elif event["status"] == "NO_EVENT" and final_close is not None and risk_amount and risk_amount > 0:
            event_r = (final_close - entry_reference) / risk_amount
        else:
            event_r = None
        result["forward"][str(horizon)] = {
            "complete": True,
            "rows": len(sample),
            "return_pct": None if return_pct is None else round(return_pct, 6),
            "mfe_pct": None if mfe is None else round(mfe, 6),
            "mae_pct": None if mae is None else round(mae, 6),
            "event": event,
            "event_r": None if event_r is None else round(event_r, 6),
        }
    return result


class EarlyPruningAuditor:
    def __init__(self, scanner: Any, market_store: Any) -> None:
        self.scanner = scanner
        self.market_store = market_store

    def _markets(self, scope: str) -> list[str]:
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

    def run_date(
        self,
        *,
        as_of: date,
        variants: list[PruningVariant],
        market_scope: str = "ALL",
        horizons: AuditHorizons = AuditHorizons(),
    ) -> dict[str, Any]:
        started = time.perf_counter()
        if not variants:
            raise ValueError("최소 1개의 pruning variant가 필요합니다.")
        markets = self._markets(market_scope)
        if not self._exact_day_available(markets, as_of):
            return {
                "analysis_date": as_of.isoformat(),
                "status": "SKIPPED_INSUFFICIENT_DATA",
                "reason": "analysis_date_stock_or_index_missing",
                "variants": {},
                "runtime_seconds": round(time.perf_counter() - started, 6),
            }

        fast_start = as_of - timedelta(days=int(self.scanner.FAST_HISTORY_CALENDAR_DAYS))
        max_market_limit = max(variant.market_limit for variant in variants)
        horizons_tuple = horizons.normalized()
        max_horizon = max(horizons_tuple)

        market_rows: dict[str, list[dict[str, Any]]] = {}
        index_rows_by_market: dict[str, list[dict[str, Any]]] = {}
        max_prefiltered: dict[str, list[dict[str, Any]]] = {}
        market_rank: dict[tuple[str, str], int] = {}
        trace: dict[tuple[str, str], dict[str, Any]] = {}
        special_excluded = 0
        liquidity_filtered = 0

        for market in markets:
            key = _compact(as_of)
            day_rows = self.market_store.stock_day_rows(market, key)
            market_rows[market] = day_rows
            ordinary: list[dict[str, Any]] = []
            for row in day_rows:
                code = str(row.get("code") or "")
                reason = self.scanner._special_reason(row)  # noqa: SLF001 - audit must reuse production rule
                if reason is not None:
                    special_excluded += 1
                    trace[(market, code)] = {"drop_stage": "SPECIAL", "drop_reason": reason}
                    continue
                if float(row.get("trade_value") or 0) < self.scanner.engine.LIQUIDITY_THRESHOLD:
                    liquidity_filtered += 1
                    trace[(market, code)] = {"drop_stage": "LIQUIDITY", "drop_reason": "below_threshold"}
                    continue
                ordinary.append(row)
            ordinary.sort(
                key=lambda row: (float(row.get("trade_value") or 0), float(row.get("market_cap") or 0)),
                reverse=True,
            )
            for rank, row in enumerate(ordinary, start=1):
                code = str(row.get("code") or "")
                market_rank[(market, code)] = rank
                trace[(market, code)] = {
                    "market_rank": rank,
                    "trade_value": row.get("trade_value"),
                    "market_cap": row.get("market_cap"),
                }
            max_prefiltered[market] = ordinary[:max_market_limit]
            index_series = self.market_store.index_series(market, _compact(fast_start), key)
            index_rows_by_market[market] = sorted(index_series.rows.values(), key=_row_date)

        quick_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        data_insufficient = 0
        for market, rows in max_prefiltered.items():
            key = _compact(as_of)
            series_map = self.market_store.stock_series_many(
                market,
                [str(row.get("code") or "") for row in rows],
                _compact(fast_start),
                key,
            )
            for row in rows:
                code = str(row.get("code") or "")
                series = series_map.get(code)
                stock_rows = list(series.rows.values()) if series is not None else []
                quick = self.scanner._quick_current_candidate(  # noqa: SLF001
                    market=market,
                    latest_date=key,
                    row=row,
                    stock_rows=stock_rows,
                    index_rows=index_rows_by_market.get(market, []),
                )
                state = trace.setdefault((market, code), {})
                state["quick_evaluated"] = True
                if quick is None:
                    data_insufficient += 1
                    state["drop_stage"] = "DATA_INSUFFICIENT"
                    continue
                quick_by_key[(market, code)] = quick
                state["quick_score"] = quick.get("quick_score")

        # Variant quality is measured with the same quick snapshots, but current evaluation
        # is executed only for each variant's selected pool. This keeps 18-vs-36 runtime
        # measurement meaningful instead of precomputing every current candidate once.
        variant_results: dict[str, Any] = {}
        union_outcome_codes: dict[str, set[str]] = {market: set() for market in markets}
        for variant in variants:
            variant_started = time.perf_counter()
            quick_candidates = [
                item
                for key, item in quick_by_key.items()
                if market_rank.get(key, 10**9) <= variant.market_limit
            ]
            quick_candidates.sort(
                key=lambda item: (float(item.get("quick_score") or 0), float(item.get("trade_value") or 0)),
                reverse=True,
            )
            for index, item in enumerate(quick_candidates, start=1):
                state = trace.setdefault((str(item.get("market") or ""), str(item.get("code") or "")), {})
                state.setdefault("quick_ranks", {})[variant.name] = index
            selected = quick_candidates[: variant.quick_limit]
            current_by_key: dict[tuple[str, str], dict[str, Any]] = {}
            deep_results: list[dict[str, Any]] = []
            for item in selected:
                key = (str(item.get("market") or ""), str(item.get("code") or ""))
                current = self.scanner._current_candidate(item)  # noqa: SLF001
                if current is not None:
                    current_by_key[key] = current
                    deep_results.append(current)
                    union_outcome_codes.setdefault(key[0], set()).add(key[1])
            deep_results.sort(key=lambda item: float(item.get("internal_rank") or 0.0), reverse=True)
            actionable = [
                item
                for item in deep_results
                if item.get("candidate_state") in {"READY", "WATCH", "VALIDATION"}
            ]
            ranked, ranking_changes = rank_candidates(actionable)
            snapshots = [_candidate_snapshot(item, rank=index) for index, item in enumerate(ranked, start=1)]
            selected_keys = {(str(item.get("market") or ""), str(item.get("code") or "")) for item in selected}
            ranked_keys = {
                (str(item.get("market") or ""), str(item.get("code") or "")): index
                for index, item in enumerate(ranked, start=1)
            }
            quick_rank_map = {
                (str(item.get("market") or ""), str(item.get("code") or "")): index
                for index, item in enumerate(quick_candidates, start=1)
            }
            current_keys = set(current_by_key)
            for key, state in trace.items():
                rank_in_market = market_rank.get(key)
                if rank_in_market is None or rank_in_market > max_market_limit:
                    continue
                market_pass = rank_in_market <= variant.market_limit
                quick_rank = quick_rank_map.get(key) if market_pass else None
                quick_pass = key in selected_keys
                final_rank = ranked_keys.get(key)
                if not market_pass:
                    drop_stage = "MARKET_PREFILTER"
                elif key not in quick_by_key:
                    drop_stage = "DATA_INSUFFICIENT"
                elif not quick_pass:
                    drop_stage = "QUICK_POOL"
                elif key not in current_keys:
                    drop_stage = "CURRENT_EVAL"
                elif final_rank is None:
                    drop_stage = "NON_ACTIONABLE"
                else:
                    drop_stage = "INCLUDED"
                state.setdefault("variants", {})[variant.name] = {
                    "market_prefilter_pass": market_pass,
                    "quick_rank": quick_rank,
                    "quick_pool_pass": quick_pass,
                    "final_evaluation": quick_pass and key in current_keys,
                    "final_rank": final_rank,
                    "drop_stage": drop_stage,
                }
            variant_results[variant.name] = {
                "config": variant.to_dict(),
                "quick_pool_count": len(quick_candidates),
                "deep_selected_count": len(selected),
                "actionable_count": len(ranked),
                "candidates": snapshots,
                "ranking_changes": ranking_changes,
                "evaluation_runtime_seconds": round(time.perf_counter() - variant_started, 6),
            }

        future_rows = self._future_rows_many(
            codes_by_market=union_outcome_codes,
            as_of=as_of,
            max_horizon=max_horizon,
        )
        for variant_name, result in variant_results.items():
            for candidate_snapshot in result["candidates"]:
                key = (candidate_snapshot["market"], candidate_snapshot["code"])
                metrics = _future_metrics(
                    candidate=candidate_snapshot,
                    future_rows=future_rows.get(key, []),
                    horizons=horizons_tuple,
                )
                candidate_snapshot["outcome"] = metrics
            result["top5_metrics"] = self._aggregate_top_metrics(result["candidates"][:5], horizons_tuple)
            result["all_metrics"] = self._aggregate_top_metrics(result["candidates"], horizons_tuple)

        baseline_name = variants[0].name
        baseline_codes = {
            (item["market"], item["code"])
            for item in variant_results[baseline_name]["candidates"]
        }
        baseline_top5 = {
            (item["market"], item["code"])
            for item in variant_results[baseline_name]["candidates"][:5]
        }
        comparisons: dict[str, Any] = {}
        for variant in variants[1:]:
            candidates = variant_results[variant.name]["candidates"]
            codes = {(item["market"], item["code"]) for item in candidates}
            top5 = {(item["market"], item["code"]) for item in candidates[:5]}
            new_candidates = codes - baseline_codes
            newly_top5 = top5 - baseline_top5
            target_hits_20 = 0
            positive_20 = 0
            complete_20 = 0
            returns_20: list[float] = []
            for item in candidates:
                key = (item["market"], item["code"])
                if key not in new_candidates:
                    continue
                outcome = ((item.get("outcome") or {}).get("forward") or {}).get("20") or {}
                if not outcome.get("complete"):
                    continue
                complete_20 += 1
                value = _float(outcome.get("return_pct"))
                if value is not None:
                    returns_20.append(value)
                    if value > 0:
                        positive_20 += 1
                if ((outcome.get("event") or {}).get("status")) == "TARGET1_FIRST":
                    target_hits_20 += 1
            comparisons[variant.name] = {
                "new_candidate_count": len(new_candidates),
                "new_top5_count": len(newly_top5),
                "top5_overlap_count": len(top5 & baseline_top5),
                "new_candidates_complete_20d": complete_20,
                "new_candidates_positive_20d": positive_20,
                "new_candidates_target1_first_20d": target_hits_20,
                "new_candidates_mean_return_20d": _mean(returns_20),
                "new_candidates_median_return_20d": _median(returns_20),
            }

        return {
            "analysis_date": as_of.isoformat(),
            "status": "OK",
            "market_scope": market_scope.upper(),
            "fast_history_start": fast_start.isoformat(),
            "universe_total": sum(len(rows) for rows in market_rows.values()),
            "special_excluded": special_excluded,
            "liquidity_filtered": liquidity_filtered,
            "data_insufficient": data_insufficient,
            "variants": variant_results,
            "baseline_comparisons": comparisons,
            "runtime_seconds": round(time.perf_counter() - started, 6),
            "trace": {
                f"{market}:{code}": _safe_json(value)
                for (market, code), value in sorted(trace.items())
                if value.get("market_rank", 10**9) <= max_market_limit
            },
        }

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
            ambiguous = 0
            complete = 0
            for candidate in candidates:
                metric = (((candidate.get("outcome") or {}).get("forward") or {}).get(str(horizon)) or {})
                if not metric.get("complete"):
                    continue
                complete += 1
                for target, key in ((returns, "return_pct"), (mfes, "mfe_pct"), (maes, "mae_pct"), (rs, "event_r")):
                    value = _float(metric.get(key))
                    if value is not None:
                        target.append(value)
                status = str((metric.get("event") or {}).get("status") or "")
                target_first += int(status == "TARGET1_FIRST")
                stop_first += int(status == "STOP_FIRST")
                ambiguous += int(status == "AMBIGUOUS_SAME_DAY")
            result["horizons"][str(horizon)] = {
                "complete": complete,
                "mean_return_pct": _mean(returns),
                "median_return_pct": _median(returns),
                "mean_mfe_pct": _mean(mfes),
                "mean_mae_pct": _mean(maes),
                "mean_event_r": _mean(rs),
                "median_event_r": _median(rs),
                "target1_first_count": target_first,
                "target1_first_pct": _pct(target_first, complete),
                "stop_first_count": stop_first,
                "stop_first_pct": _pct(stop_first, complete),
                "ambiguous_same_day_count": ambiguous,
            }
        return result

    def run_dates(
        self,
        *,
        dates: list[date],
        variants: list[PruningVariant],
        market_scope: str = "ALL",
        horizons: AuditHorizons = AuditHorizons(),
        progress_callback: Callable[[int, int, date, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        runs: list[dict[str, Any]] = []
        total = len(dates)
        for index, as_of in enumerate(dates, start=1):
            run = self.run_date(as_of=as_of, variants=variants, market_scope=market_scope, horizons=horizons)
            runs.append(run)
            if progress_callback is not None:
                progress_callback(index, total, as_of, run)
        valid = [run for run in runs if run.get("status") == "OK"]
        aggregate: dict[str, Any] = {}
        for variant in variants:
            top5_returns: dict[str, list[float]] = {str(h): [] for h in horizons.normalized()}
            top5_rs: dict[str, list[float]] = {str(h): [] for h in horizons.normalized()}
            target_counts: dict[str, int] = {str(h): 0 for h in horizons.normalized()}
            stop_counts: dict[str, int] = {str(h): 0 for h in horizons.normalized()}
            complete_counts: dict[str, int] = {str(h): 0 for h in horizons.normalized()}
            for run in valid:
                metrics = (((run.get("variants") or {}).get(variant.name) or {}).get("top5_metrics") or {}).get("horizons") or {}
                for horizon in horizons.normalized():
                    key = str(horizon)
                    item = metrics.get(key) or {}
                    complete_counts[key] += int(item.get("complete") or 0)
                    target_counts[key] += int(item.get("target1_first_count") or 0)
                    stop_counts[key] += int(item.get("stop_first_count") or 0)
                    value = _float(item.get("mean_return_pct"))
                    if value is not None:
                        top5_returns[key].append(value)
                    value = _float(item.get("mean_event_r"))
                    if value is not None:
                        top5_rs[key].append(value)
            aggregate[variant.name] = {
                "config": variant.to_dict(),
                "valid_dates": len(valid),
                "top5": {
                    key: {
                        "mean_of_daily_mean_return_pct": _mean(top5_returns[key]),
                        "median_of_daily_mean_return_pct": _median(top5_returns[key]),
                        "mean_of_daily_mean_event_r": _mean(top5_rs[key]),
                        "target1_first_pct": _pct(target_counts[key], complete_counts[key]),
                        "stop_first_pct": _pct(stop_counts[key], complete_counts[key]),
                        "complete_signals": complete_counts[key],
                    }
                    for key in top5_returns
                },
            }

        return {
            "audit_version": AUDIT_VERSION,
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "scanner_version": str(getattr(self.scanner, "VERSION", "unknown")),
            "market_scope": market_scope.upper(),
            "evaluation_dates": [value.isoformat() for value in dates],
            "valid_date_count": len(valid),
            "skipped_date_count": len(runs) - len(valid),
            "variants": [variant.to_dict() for variant in variants],
            "aggregate": aggregate,
            "runs": runs,
            "runtime_seconds": round(time.perf_counter() - started, 6),
        }


def discover_evaluation_dates(
    market_store: Any,
    *,
    market_scope: str,
    sample_size: int,
    future_buffer_calendar_days: int = 35,
) -> list[date]:
    markets = ["KOSPI", "KOSDAQ"] if market_scope.upper() == "ALL" else [market_scope.upper()]
    latest_values: list[str] = []
    for market in markets:
        for kind in ("stock", "index"):
            value = market_store.latest_complete_date(market, kind)
            if not value:
                return []
            latest_values.append(str(value))
    latest = date.fromisoformat(_iso(min(latest_values)))
    cursor = latest - timedelta(days=future_buffer_calendar_days)
    result: list[date] = []
    while cursor >= latest - timedelta(days=900) and len(result) < sample_size:
        key = _compact(cursor)
        if all(
            market_store.latest_complete_date(market, "stock", key) == key
            and market_store.latest_complete_date(market, "index", key) == key
            for market in markets
        ):
            result.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(result)



def _evenly_sample_dates(values: list[date], sample_size: int) -> list[date]:
    ordered = sorted(set(values))
    sample_size = max(1, int(sample_size))
    if len(ordered) <= sample_size:
        return ordered
    if sample_size == 1:
        return [ordered[len(ordered) // 2]]
    indices = [round(index * (len(ordered) - 1) / (sample_size - 1)) for index in range(sample_size)]
    return [ordered[index] for index in dict.fromkeys(indices)]


def _common_complete_dates(
    market_store: Any,
    *,
    market_scope: str,
    lookback_calendar_days: int = 2000,
) -> list[date]:
    markets = ["KOSPI", "KOSDAQ"] if market_scope.upper() == "ALL" else [market_scope.upper()]
    latest_values: list[str] = []
    for market in markets:
        for kind in ("stock", "index"):
            value = market_store.latest_complete_date(market, kind)
            if not value:
                return []
            latest_values.append(str(value))
    latest = date.fromisoformat(_iso(min(latest_values)))
    start = latest - timedelta(days=max(120, int(lookback_calendar_days)))

    common: set[str] | None = None
    if hasattr(market_store, "day_status_range"):
        for market in markets:
            statuses = market_store.day_status_range(market, _compact(start), _compact(latest))
            stock_dates = {bas_dd for (bas_dd, kind), status in statuses.items() if kind == "stock" and status == "data"}
            index_dates = {bas_dd for (bas_dd, kind), status in statuses.items() if kind == "index" and status == "data"}
            market_dates = stock_dates & index_dates
            common = market_dates if common is None else common & market_dates
    else:
        common = set()
        cursor = start
        while cursor <= latest:
            key = _compact(cursor)
            if all(
                market_store.latest_complete_date(market, "stock", key) == key
                and market_store.latest_complete_date(market, "index", key) == key
                for market in markets
            ):
                common.add(key)
            cursor += timedelta(days=1)
    return [date.fromisoformat(_iso(value)) for value in sorted(common or set())]


def discover_temporal_evaluation_dates(
    market_store: Any,
    *,
    market_scope: str,
    sample_size: int = 80,
    min_date_gap: int = 3,
    future_horizon_trading_days: int = 20,
    min_required_dates: int = 60,
    lookback_calendar_days: int = 2000,
) -> tuple[list[date], dict[str, Any]]:
    """Deterministically spread evaluation dates over the locally complete market-wide period.

    `min_date_gap` is a preferred gap in common trading dates. If that preference makes the
    minimum validation target impossible, the gap is relaxed one step at a time and recorded.
    """
    common = _common_complete_dates(
        market_store,
        market_scope=market_scope,
        lookback_calendar_days=lookback_calendar_days,
    )
    horizon = max(1, int(future_horizon_trading_days))
    eligible = common[:-horizon] if len(common) > horizon else []
    requested_gap = max(1, int(min_date_gap))
    requested_size = max(1, int(sample_size))
    minimum_target = min(max(1, int(min_required_dates)), requested_size, len(eligible))

    selected: list[date] = []
    effective_gap = requested_gap
    for gap in range(requested_gap, 0, -1):
        thinned = eligible[::gap]
        candidate = _evenly_sample_dates(thinned, requested_size)
        selected = candidate
        effective_gap = gap
        if len(candidate) >= minimum_target:
            break

    metadata = {
        "common_complete_date_count": len(common),
        "eligible_date_count": len(eligible),
        "requested_sample_size": requested_size,
        "selected_sample_size": len(selected),
        "requested_min_date_gap": requested_gap,
        "effective_min_date_gap": effective_gap,
        "future_horizon_trading_days": horizon,
        "min_required_dates": int(min_required_dates),
        "first_eligible_date": eligible[0].isoformat() if eligible else None,
        "last_eligible_date": eligible[-1].isoformat() if eligible else None,
        "first_selected_date": selected[0].isoformat() if selected else None,
        "last_selected_date": selected[-1].isoformat() if selected else None,
    }
    return selected, metadata


def _candidate_key(candidate: dict[str, Any]) -> str:
    return f"{candidate.get('market')}:{candidate.get('code')}"


def _forward(candidate: dict[str, Any], horizon: int) -> dict[str, Any]:
    return (((candidate.get("outcome") or {}).get("forward") or {}).get(str(horizon)) or {})


def _event_status(candidate: dict[str, Any], horizon: int) -> str | None:
    return (_forward(candidate, horizon).get("event") or {}).get("status")


def _metric_from_top5(run: dict[str, Any], variant_name: str, horizon: int) -> dict[str, Any]:
    return (((run.get("variants") or {}).get(variant_name) or {}).get("top5_metrics") or {}).get("horizons", {}).get(str(horizon), {})


def build_temporal_validation(
    payload: dict[str, Any],
    *,
    baseline_name: str = "BASELINE",
    expanded_name: str = "QUICK_EXPANDED",
    trim_fraction: float = 0.05,
    minimum_valid_dates: int = 60,
) -> dict[str, Any]:
    horizons = (5, 10, 20)
    valid_runs = [run for run in payload.get("runs") or [] if run.get("status") == "OK"]
    changed_dates: list[str] = []
    unchanged_dates: list[str] = []
    replacement_pairs: list[dict[str, Any]] = []
    date_level: list[dict[str, Any]] = []
    replacement_counts: list[int] = []

    for run in valid_runs:
        variants = run.get("variants") or {}
        baseline_candidates = list((variants.get(baseline_name) or {}).get("candidates") or [])[:5]
        expanded_candidates = list((variants.get(expanded_name) or {}).get("candidates") or [])[:5]
        baseline_map = {_candidate_key(item): item for item in baseline_candidates}
        expanded_map = {_candidate_key(item): item for item in expanded_candidates}
        baseline_keys = list(baseline_map)
        expanded_keys = list(expanded_map)
        removed_keys = [key for key in baseline_keys if key not in expanded_map]
        added_keys = [key for key in expanded_keys if key not in baseline_map]
        changed = bool(removed_keys or added_keys)
        analysis_date = str(run.get("analysis_date") or "")
        (changed_dates if changed else unchanged_dates).append(analysis_date)
        replacement_counts.append(max(len(removed_keys), len(added_keys)))

        date_record: dict[str, Any] = {
            "analysis_date": analysis_date,
            "changed": changed,
            "removed_count": len(removed_keys),
            "added_count": len(added_keys),
            "horizons": {},
        }
        for horizon in horizons:
            baseline_metric = _metric_from_top5(run, baseline_name, horizon)
            expanded_metric = _metric_from_top5(run, expanded_name, horizon)
            date_record["horizons"][str(horizon)] = {
                "baseline_mean_return_pct": baseline_metric.get("mean_return_pct"),
                "expanded_mean_return_pct": expanded_metric.get("mean_return_pct"),
                "return_delta_pct": _delta(expanded_metric.get("mean_return_pct"), baseline_metric.get("mean_return_pct")),
                "baseline_mean_event_r": baseline_metric.get("mean_event_r"),
                "expanded_mean_event_r": expanded_metric.get("mean_event_r"),
                "event_r_delta": _delta(expanded_metric.get("mean_event_r"), baseline_metric.get("mean_event_r")),
                "mfe_delta_pct": _delta(expanded_metric.get("mean_mfe_pct"), baseline_metric.get("mean_mfe_pct")),
                "mae_delta_pct": _delta(expanded_metric.get("mean_mae_pct"), baseline_metric.get("mean_mae_pct")),
                "target1_first_delta_pct": _delta(expanded_metric.get("target1_first_pct"), baseline_metric.get("target1_first_pct")),
                "stop_first_delta_pct": _delta(expanded_metric.get("stop_first_pct"), baseline_metric.get("stop_first_pct")),
            }
        date_level.append(date_record)

        max_pairs = max(len(removed_keys), len(added_keys))
        for pair_index in range(max_pairs):
            removed = baseline_map.get(removed_keys[pair_index]) if pair_index < len(removed_keys) else None
            added = expanded_map.get(added_keys[pair_index]) if pair_index < len(added_keys) else None
            pair: dict[str, Any] = {
                "analysis_date": analysis_date,
                "pair_index": pair_index + 1,
                "removed": None if removed is None else {
                    "key": _candidate_key(removed), "market": removed.get("market"), "code": removed.get("code"),
                    "name": removed.get("name"), "rank": removed.get("rank"), "strategy": removed.get("strategy"),
                },
                "added": None if added is None else {
                    "key": _candidate_key(added), "market": added.get("market"), "code": added.get("code"),
                    "name": added.get("name"), "rank": added.get("rank"), "strategy": added.get("strategy"),
                },
                "horizons": {},
            }
            for horizon in horizons:
                removed_metric = _forward(removed or {}, horizon)
                added_metric = _forward(added or {}, horizon)
                pair["horizons"][str(horizon)] = {
                    "removed_return_pct": removed_metric.get("return_pct"),
                    "added_return_pct": added_metric.get("return_pct"),
                    "return_delta_pct": _delta(added_metric.get("return_pct"), removed_metric.get("return_pct")),
                    "removed_event_r": removed_metric.get("event_r"),
                    "added_event_r": added_metric.get("event_r"),
                    "event_r_delta": _delta(added_metric.get("event_r"), removed_metric.get("event_r")),
                    "removed_event": _event_status(removed or {}, horizon),
                    "added_event": _event_status(added or {}, horizon),
                }
            replacement_pairs.append(pair)

    horizon_summary: dict[str, Any] = {}
    for horizon in horizons:
        key = str(horizon)
        all_return_deltas = [_float((item.get("horizons") or {}).get(key, {}).get("return_delta_pct")) for item in date_level]
        changed_return_deltas = [
            _float((item.get("horizons") or {}).get(key, {}).get("return_delta_pct"))
            for item in date_level if item.get("changed")
        ]
        all_r_deltas = [_float((item.get("horizons") or {}).get(key, {}).get("event_r_delta")) for item in date_level]
        changed_r_deltas = [
            _float((item.get("horizons") or {}).get(key, {}).get("event_r_delta"))
            for item in date_level if item.get("changed")
        ]
        stop_deltas = [_float((item.get("horizons") or {}).get(key, {}).get("stop_first_delta_pct")) for item in date_level]
        target_deltas = [_float((item.get("horizons") or {}).get(key, {}).get("target1_first_delta_pct")) for item in date_level]
        pair_return_deltas = [_float((pair.get("horizons") or {}).get(key, {}).get("return_delta_pct")) for pair in replacement_pairs]
        pair_r_deltas = [_float((pair.get("horizons") or {}).get(key, {}).get("event_r_delta")) for pair in replacement_pairs]
        normalized = [value for value in all_return_deltas if value is not None]
        horizon_summary[key] = {
            "all_dates": {
                "mean_return_delta_pct": _mean(normalized),
                "median_return_delta_pct": _median(normalized),
                "trimmed_mean_return_delta_pct": _trimmed_mean(normalized, trim_fraction),
                "mean_event_r_delta": _mean(all_r_deltas),
                "median_event_r_delta": _median(all_r_deltas),
                "mean_stop_first_delta_pct": _mean(stop_deltas),
                "mean_target1_first_delta_pct": _mean(target_deltas),
                "improved_dates": sum(1 for value in normalized if value > 1e-9),
                "worse_dates": sum(1 for value in normalized if value < -1e-9),
                "equal_dates": sum(1 for value in normalized if abs(value) <= 1e-9),
            },
            "changed_dates": {
                "mean_return_delta_pct": _mean(changed_return_deltas),
                "median_return_delta_pct": _median(changed_return_deltas),
                "trimmed_mean_return_delta_pct": _trimmed_mean(changed_return_deltas, trim_fraction),
                "mean_event_r_delta": _mean(changed_r_deltas),
                "median_event_r_delta": _median(changed_r_deltas),
            },
            "replacement_pairs": {
                "count": len([value for value in pair_return_deltas if value is not None]),
                "mean_return_delta_pct": _mean(pair_return_deltas),
                "median_return_delta_pct": _median(pair_return_deltas),
                "mean_event_r_delta": _mean(pair_r_deltas),
                "median_event_r_delta": _median(pair_r_deltas),
            },
        }

    runtime_baseline = [
        _float((((run.get("variants") or {}).get(baseline_name) or {}).get("evaluation_runtime_seconds")))
        for run in valid_runs
    ]
    runtime_expanded = [
        _float((((run.get("variants") or {}).get(expanded_name) or {}).get("evaluation_runtime_seconds")))
        for run in valid_runs
    ]
    baseline_mean_runtime = _mean(runtime_baseline)
    expanded_mean_runtime = _mean(runtime_expanded)
    runtime_delta = _delta(expanded_mean_runtime, baseline_mean_runtime)
    runtime_ratio = None
    if baseline_mean_runtime and expanded_mean_runtime is not None and baseline_mean_runtime > 0:
        runtime_ratio = round(expanded_mean_runtime / baseline_mean_runtime, 4)

    valid_count = len(valid_runs)
    changed_count = len(changed_dates)
    change_rate = _pct(changed_count, valid_count)
    h10 = horizon_summary.get("10", {})
    h20 = horizon_summary.get("20", {})
    all10 = h10.get("all_dates") or {}
    all20 = h20.get("all_dates") or {}
    changed20 = h20.get("changed_dates") or {}
    pair20 = h20.get("replacement_pairs") or {}

    if valid_count < int(minimum_valid_dates):
        verdict = "INCONCLUSIVE"
        verdict_reasons = [f"valid_dates {valid_count} < minimum {minimum_valid_dates}"]
    elif changed_count <= 2:
        verdict = "KEEP_18"
        verdict_reasons = ["Top5 change is concentrated in at most two dates."]
    else:
        consider_checks = [
            (_float(all10.get("mean_return_delta_pct")) or 0) > 0,
            (_float(all20.get("mean_return_delta_pct")) or 0) > 0,
            (_float(all20.get("trimmed_mean_return_delta_pct")) or 0) > 0,
            (_float(changed20.get("median_return_delta_pct")) or 0) > 0,
            (_float(all20.get("mean_event_r_delta")) or 0) > 0,
            (_float(all20.get("mean_stop_first_delta_pct")) or 0) <= 0,
            (_float(pair20.get("median_return_delta_pct")) or 0) > 0,
        ]
        if all(consider_checks):
            verdict = "CONSIDER_36"
            verdict_reasons = ["Quick36 improvement survives temporal, paired, trimmed, R and stop checks."]
        elif (
            (_float(all20.get("trimmed_mean_return_delta_pct")) or 0) <= 0
            or (_float(changed20.get("median_return_delta_pct")) or 0) <= 0
            or (_float(all20.get("mean_event_r_delta")) or 0) <= 0
            or (_float(all20.get("mean_stop_first_delta_pct")) or 0) > 0
        ):
            verdict = "KEEP_18"
            verdict_reasons = ["Quick36 does not show robust 20D quality improvement after stability checks."]
        else:
            verdict = "INCONCLUSIVE"
            verdict_reasons = ["Signals are mixed across return, R, stop or paired checks."]

    return {
        "baseline_variant": baseline_name,
        "expanded_variant": expanded_name,
        "valid_dates": valid_count,
        "changed_dates": changed_dates,
        "unchanged_dates": unchanged_dates,
        "changed_date_count": changed_count,
        "unchanged_date_count": len(unchanged_dates),
        "change_rate_pct": change_rate,
        "average_replacements_per_changed_date": _mean(
            [float(value) for value, record in zip(replacement_counts, date_level) if record.get("changed")]
        ),
        "max_replacements_on_one_date": max(replacement_counts, default=0),
        "date_level": date_level,
        "replacement_pairs": replacement_pairs,
        "horizons": horizon_summary,
        "runtime": {
            "baseline_mean_evaluation_seconds": baseline_mean_runtime,
            "expanded_mean_evaluation_seconds": expanded_mean_runtime,
            "expanded_minus_baseline_seconds": runtime_delta,
            "expanded_over_baseline_ratio": runtime_ratio,
        },
        "trim_fraction": trim_fraction,
        "verdict": verdict,
        "verdict_reasons": verdict_reasons,
    }


def compact_temporal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop per-symbol trace in temporal mode; pair/date diagnostics retain the needed evidence."""
    for run in payload.get("runs") or []:
        run.pop("trace", None)
    return payload

def add_audit_metadata(payload: dict[str, Any], *, market_store: Any, project_root: Path) -> dict[str, Any]:
    result = dict(payload)
    result["git"] = _git_info(project_root)
    dates = [date.fromisoformat(raw) for raw in result.get("evaluation_dates") or []]
    if dates and hasattr(market_store, "reproducibility_snapshot"):
        start = min(dates) - timedelta(days=220)
        end = max(dates)
        fingerprints: dict[str, Any] = {}
        markets = ["KOSPI", "KOSDAQ"] if result.get("market_scope") == "ALL" else [result.get("market_scope")]
        for market in markets:
            fingerprints[str(market)] = market_store.reproducibility_snapshot(
                str(market), _compact(start), _compact(end)
            )
        canonical = json.dumps(_safe_json(fingerprints), sort_keys=True, separators=(",", ":"))
        result["data_fingerprint"] = {
            "combined_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "markets": _safe_json(fingerprints),
        }
    return result


def write_outputs(payload: dict[str, Any], *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"scanner-pruning-audit_{stamp}.json"
    csv_path = output_dir / f"scanner-pruning-signals_{stamp}.csv"
    md_path = output_dir / f"scanner-pruning-summary_{stamp}.md"

    json_path.write_text(json.dumps(_safe_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = [
        "analysis_date", "variant", "rank", "market", "code", "name", "strategy", "candidate_state",
        "baseline_included", "pruning_stage",
        "return_5d_pct", "return_10d_pct", "return_20d_pct", "mfe_20d_pct", "mae_20d_pct",
        "event_20d", "event_r_20d",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for run in payload.get("runs") or []:
            if run.get("status") != "OK":
                continue
            baseline_codes = {
                f"{item.get('market')}:{item.get('code')}"
                for item in (((run.get("variants") or {}).get("BASELINE") or {}).get("candidates") or [])
            }
            trace = run.get("trace") or {}
            for variant_name, result in (run.get("variants") or {}).items():
                for candidate in result.get("candidates") or []:
                    forward = ((candidate.get("outcome") or {}).get("forward") or {})
                    row20 = forward.get("20") or {}
                    key = f"{candidate.get('market')}:{candidate.get('code')}"
                    pruning_stage = ((((trace.get(key) or {}).get("variants") or {}).get(variant_name) or {}).get("drop_stage"))
                    if pruning_stage is None:
                        pruning_stage = "INCLUDED"
                    writer.writerow({
                        "analysis_date": run.get("analysis_date"),
                        "variant": variant_name,
                        "rank": candidate.get("rank"),
                        "market": candidate.get("market"),
                        "code": candidate.get("code"),
                        "name": candidate.get("name"),
                        "strategy": candidate.get("strategy"),
                        "candidate_state": candidate.get("candidate_state"),
                        "baseline_included": key in baseline_codes,
                        "pruning_stage": pruning_stage,
                        "return_5d_pct": (forward.get("5") or {}).get("return_pct"),
                        "return_10d_pct": (forward.get("10") or {}).get("return_pct"),
                        "return_20d_pct": row20.get("return_pct"),
                        "mfe_20d_pct": row20.get("mfe_pct"),
                        "mae_20d_pct": row20.get("mae_pct"),
                        "event_20d": (row20.get("event") or {}).get("status"),
                        "event_r_20d": row20.get("event_r"),
                    })

    paths: dict[str, str] = {"json": str(json_path), "csv": str(csv_path)}
    temporal = payload.get("temporal_validation") or {}
    if temporal:
        pairs_path = output_dir / f"scanner-pruning-pairs_{stamp}.csv"
        pair_fields = [
            "analysis_date", "pair_index",
            "removed_market", "removed_code", "removed_name", "removed_rank",
            "added_market", "added_code", "added_name", "added_rank",
            "return_5d_delta", "return_10d_delta", "return_20d_delta", "event_r_20d_delta",
            "removed_event_20d", "added_event_20d",
        ]
        with pairs_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=pair_fields)
            writer.writeheader()
            for pair in temporal.get("replacement_pairs") or []:
                removed = pair.get("removed") or {}
                added = pair.get("added") or {}
                horizons = pair.get("horizons") or {}
                writer.writerow({
                    "analysis_date": pair.get("analysis_date"),
                    "pair_index": pair.get("pair_index"),
                    "removed_market": removed.get("market"),
                    "removed_code": removed.get("code"),
                    "removed_name": removed.get("name"),
                    "removed_rank": removed.get("rank"),
                    "added_market": added.get("market"),
                    "added_code": added.get("code"),
                    "added_name": added.get("name"),
                    "added_rank": added.get("rank"),
                    "return_5d_delta": (horizons.get("5") or {}).get("return_delta_pct"),
                    "return_10d_delta": (horizons.get("10") or {}).get("return_delta_pct"),
                    "return_20d_delta": (horizons.get("20") or {}).get("return_delta_pct"),
                    "event_r_20d_delta": (horizons.get("20") or {}).get("event_r_delta"),
                    "removed_event_20d": (horizons.get("20") or {}).get("removed_event"),
                    "added_event_20d": (horizons.get("20") or {}).get("added_event"),
                })
        paths["pairs_csv"] = str(pairs_path)

    if temporal:
        sampling = payload.get("sampling") or {}
        h5 = ((temporal.get("horizons") or {}).get("5") or {}).get("all_dates") or {}
        h10 = ((temporal.get("horizons") or {}).get("10") or {}).get("all_dates") or {}
        h20 = ((temporal.get("horizons") or {}).get("20") or {}).get("all_dates") or {}
        changed20 = ((temporal.get("horizons") or {}).get("20") or {}).get("changed_dates") or {}
        runtime = temporal.get("runtime") or {}
        lines = [
            f"# Scanner Temporal Quick-Pool Validation — {payload.get('audit_version')}",
            "",
            f"- Scanner version: `{payload.get('scanner_version')}`",
            f"- Market scope: `{payload.get('market_scope')}`",
            f"- Valid dates: **{payload.get('valid_date_count', 0)}** / {len(payload.get('evaluation_dates') or [])}",
            f"- Selected range: `{sampling.get('first_selected_date')}` ~ `{sampling.get('last_selected_date')}`",
            f"- Requested/effective trading-date gap: **{sampling.get('requested_min_date_gap')} / {sampling.get('effective_min_date_gap')}**",
            f"- Changed Top5 dates: **{temporal.get('changed_date_count')}** ({temporal.get('change_rate_pct')}%)",
            f"- Runtime: **{payload.get('runtime_seconds')}s**",
            f"- Verdict: **{temporal.get('verdict')}**",
            "",
            "## 18 vs 36 date-level delta",
            "",
            "| Horizon | Mean return Δ | Median return Δ | Trimmed mean Δ | Mean R Δ | Stop-first Δ |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for horizon, values in (("5D", h5), ("10D", h10), ("20D", h20)):
            lines.append(
                f"| {horizon} | {values.get('mean_return_delta_pct')} | {values.get('median_return_delta_pct')} | "
                f"{values.get('trimmed_mean_return_delta_pct')} | {values.get('mean_event_r_delta')} | "
                f"{values.get('mean_stop_first_delta_pct')} |"
            )
        lines += [
            "",
            "## Changed-date / paired check",
            "",
            f"- 20D changed-date median return Δ: **{changed20.get('median_return_delta_pct')}**",
            f"- Average replacements per changed date: **{temporal.get('average_replacements_per_changed_date')}**",
            f"- Max replacements on one date: **{temporal.get('max_replacements_on_one_date')}**",
            "",
            "## Runtime cost",
            "",
            f"- Quick18 current-eval mean: **{runtime.get('baseline_mean_evaluation_seconds') if runtime.get('baseline_mean_evaluation_seconds') is not None else 'N/A'}**",
            f"- Quick36 current-eval mean: **{runtime.get('expanded_mean_evaluation_seconds') if runtime.get('expanded_mean_evaluation_seconds') is not None else 'N/A'}**",
            f"- Quick36 / Quick18: **{runtime.get('expanded_over_baseline_ratio') if runtime.get('expanded_over_baseline_ratio') is not None else 'N/A'}**",
            "",
            "## Verdict reasons",
            "",
        ]
        lines.extend(f"- {reason}" for reason in temporal.get("verdict_reasons") or [])
    else:
        lines = [
            f"# Scanner Early Pruning Audit — {payload.get('audit_version')}",
            "",
            f"- Scanner version: `{payload.get('scanner_version')}`",
            f"- Market scope: `{payload.get('market_scope')}`",
            f"- Valid dates: **{payload.get('valid_date_count', 0)}** / {len(payload.get('evaluation_dates') or [])}",
            f"- Runtime: **{payload.get('runtime_seconds')}s**",
            "",
            "## Variant summary",
            "",
            "| Variant | Market limit | Quick limit | Top5 20D avg return | Top5 20D mean R | T1 first | Stop first |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for variant_name, aggregate in (payload.get("aggregate") or {}).items():
            config = aggregate.get("config") or {}
            m20 = ((aggregate.get("top5") or {}).get("20") or {})
            lines.append(
                f"| {variant_name} | {config.get('market_limit')} | {config.get('quick_limit')} | "
                f"{m20.get('mean_of_daily_mean_return_pct')} | {m20.get('mean_of_daily_mean_event_r')} | "
                f"{m20.get('target1_first_pct')}% | {m20.get('stop_first_pct')}% |"
            )
        lines += [
            "",
            "## Interpretation guardrail",
            "",
            "이 결과는 과거 데이터 기반 감사이며 매수 추천이 아니다. Variant 간 차이가 여러 평가일에서 반복되는지 확인한 뒤 Production 정책 변경 여부를 결정한다.",
        ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    paths["markdown"] = str(md_path)
    return paths

