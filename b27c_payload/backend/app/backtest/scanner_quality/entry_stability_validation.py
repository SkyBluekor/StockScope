from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from app.backtest.scanner_quality.entry_stability_audit import compute_entry_stability_features

AUDIT_VERSION = "v0.21.4-B.2.7-C"
EXPECTED_SCANNER_VERSION = "0.21.3.7"
CURRENT = "CURRENT"
RULE_VOLUME_LOW = "VOLUME_LOW_GUARD"
RULE_RETURN_STD_HIGH = "RETURN_STD_HIGH_GUARD"
RULE_MA20_GAP_HIGH = "MA20_GAP_CHANGE_HIGH_GUARD"
RULE_ORDER = (RULE_VOLUME_LOW, RULE_RETURN_STD_HIGH, RULE_MA20_GAP_HIGH)

OVERALL_MULTIPLE = "MULTIPLE_ENTRY_STABILITY_SIGNALS_SURVIVED"
OVERALL_VOLUME = "PROMOTE_VOLUME_SIGNAL"
OVERALL_RETURN_STD = "PROMOTE_RETURN_STD_SIGNAL"
OVERALL_MA20_GAP = "PROMOTE_MA20_GAP_SIGNAL"
OVERALL_NONE = "NO_ENTRY_STABILITY_RULE_SURVIVED"

RULE_SPECS: dict[str, dict[str, str]] = {
    RULE_VOLUME_LOW: {
        "feature": "volume_ratio_prev20",
        "band": "LOW",
        "threshold": "same-date READY Q25",
    },
    RULE_RETURN_STD_HIGH: {
        "feature": "return_std_20d_pct",
        "band": "HIGH",
        "threshold": "same-date READY Q75",
    },
    RULE_MA20_GAP_HIGH: {
        "feature": "ma20_gap_change_5d_pct",
        "band": "HIGH",
        "threshold": "same-date READY Q75",
    },
}


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _mean(values: Iterable[Any]) -> float | None:
    nums = [n for value in values if (n := _num(value)) is not None]
    return sum(nums) / len(nums) if nums else None


def _median(values: Iterable[Any]) -> float | None:
    nums = [n for value in values if (n := _num(value)) is not None]
    return statistics.median(nums) if nums else None


def _trimmed_mean(values: Iterable[Any], proportion: float = 0.10) -> float | None:
    nums = sorted(n for value in values if (n := _num(value)) is not None)
    if not nums:
        return None
    trim = int(len(nums) * max(0.0, min(float(proportion), 0.45)))
    if trim and len(nums) > trim * 2:
        nums = nums[trim:-trim]
    return sum(nums) / len(nums)


def _mean_without_best(values: Iterable[Any]) -> float | None:
    nums = sorted((n for value in values if (n := _num(value)) is not None), reverse=True)
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    return sum(nums[1:]) / (len(nums) - 1)


def _rate(values: Iterable[bool]) -> float | None:
    items = list(values)
    return sum(1 for item in items if item) / len(items) if items else None


def _quantile(values: Iterable[Any], q: float) -> float | None:
    nums = sorted(n for value in values if (n := _num(value)) is not None)
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    pos = (len(nums) - 1) * max(0.0, min(float(q), 1.0))
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return nums[lo]
    weight = pos - lo
    return nums[lo] * (1.0 - weight) + nums[hi] * weight


def ensure_scanner_version(actual: Any) -> None:
    version = str(actual or "")
    if version != EXPECTED_SCANNER_VERSION:
        raise RuntimeError(
            f"STALE_SOURCE: expected Scanner {EXPECTED_SCANNER_VERSION}, actual {version or '<missing>'}. "
            "B.2.7-C must run on the current Production Scanner."
        )


def _code(row: dict[str, Any]) -> str:
    return str(row.get("code") or "")


def _rank(row: dict[str, Any], key: str = "current_rank") -> int:
    try:
        return int(row.get(key) or row.get("rank") or 999999)
    except (TypeError, ValueError):
        return 999999


def classify_ready_bands(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    ready = [row for row in rows if str(row.get("candidate_state") or "") == "READY"]
    thresholds: dict[str, dict[str, float | None]] = {}
    for rule_id, spec in RULE_SPECS.items():
        feature = spec["feature"]
        q25 = _quantile((row.get(feature) for row in ready), 0.25)
        q75 = _quantile((row.get(feature) for row in ready), 0.75)
        thresholds[rule_id] = {"q25": q25, "q75": q75}
        for row in rows:
            value = _num(row.get(feature))
            band = "MISSING"
            if str(row.get("candidate_state") or "") == "READY" and value is not None and q25 is not None and q75 is not None:
                if value <= q25:
                    band = "LOW"
                elif value >= q75:
                    band = "HIGH"
                else:
                    band = "MID"
            row[f"{feature}_band"] = band
    return thresholds


def apply_entry_stability_rule(rows: list[dict[str, Any]], rule_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if rule_id not in RULE_SPECS:
        raise ValueError(f"unknown Entry Stability rule: {rule_id}")
    spec = RULE_SPECS[rule_id]
    feature = spec["feature"]
    band = spec["band"]
    current = sorted((dict(row) for row in rows), key=lambda row: (_rank(row), _code(row)))
    ready = [row for row in current if str(row.get("candidate_state") or "") == "READY"]
    stable = [row for row in ready if row.get(f"{feature}_band") != band]
    unstable = [row for row in ready if row.get(f"{feature}_band") == band]
    reordered_ready = stable + unstable

    output = list(current)
    ready_positions = [i for i, row in enumerate(current) if str(row.get("candidate_state") or "") == "READY"]
    for position, replacement in zip(ready_positions, reordered_ready):
        output[position] = replacement

    unstable_codes = {_code(row) for row in unstable}
    for index, row in enumerate(output, start=1):
        row["guard_rank"] = index
        row["unstable_by_rule"] = _code(row) in unstable_codes
        row["guard_rule"] = rule_id
    return output, {
        "rule_id": rule_id,
        "feature": feature,
        "band": band,
        "ready_count": len(ready),
        "unstable_count": len(unstable),
    }


def _row_date(row: dict[str, Any]) -> str:
    return str(row.get("date") or row.get("bas_dd") or row.get("BAS_DD") or "")


def _compact(day: date) -> str:
    return day.strftime("%Y%m%d")


def _flatten_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    forward = outcome.get("forward") or {}
    for horizon in (5, 10, 20):
        metric = forward.get(str(horizon)) or {}
        flat[f"return_{horizon}d"] = metric.get("return_pct")
        flat[f"mfe_{horizon}d"] = metric.get("mfe_pct")
        flat[f"mae_{horizon}d"] = metric.get("mae_pct")
        flat[f"event_{horizon}d"] = (metric.get("event") or {}).get("status")
        flat[f"event_r_{horizon}d"] = metric.get("event_r")
    return flat


@dataclass
class OfflineAuditKrx:
    @staticmethod
    def _today_kst() -> date:
        return date.today()

    async def open_session(self) -> None:
        return None

    async def close_session(self) -> None:
        return None

    @staticmethod
    def request_stats() -> dict[str, int]:
        return {"network_requests": 0}

    @staticmethod
    def budget_snapshot() -> dict[str, int]:
        return {"used": 0, "safe_limit": 0, "remaining": 0}

    async def stock_daily(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise RuntimeError("B.2.7-C is offline-only; KRX stock download was attempted.")

    async def index_daily(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise RuntimeError("B.2.7-C is offline-only; KRX index download was attempted.")


def _attach_future_outcomes(
    rows: list[dict[str, Any]],
    candidate_by_key: dict[tuple[str, str], dict[str, Any]],
    market_store: Any,
    *,
    as_of: date,
) -> list[dict[str, Any]]:
    from app.backtest.scanner_quality.early_pruning_audit import _future_metrics

    # Candidate order and every rule rank are already frozen before this function is called.
    codes_by_market: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        codes_by_market[str(row.get("market") or "")].add(_code(row))

    future_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    future_start = _compact(as_of + timedelta(days=1))
    future_end = _compact(as_of + timedelta(days=60))
    for market, codes in codes_by_market.items():
        if not market or not codes:
            continue
        series_map = market_store.stock_series_many(market, sorted(codes), future_start, future_end)
        for code, series in series_map.items():
            future_by_key[(market, str(code))] = sorted((dict(row) for row in series.rows.values()), key=_row_date)

    output: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row.get("market") or ""), _code(row))
        candidate = candidate_by_key.get(key) or {}
        outcome = _future_metrics(
            candidate=candidate,
            future_rows=future_by_key.get(key, []),
            horizons=(5, 10, 20),
        )
        enriched = dict(row)
        enriched.update(_flatten_outcome(outcome))
        output.append(enriched)
    return output


def run_current_date(scanner: Any, market_store: Any, *, as_of: date, market_scope: str = "ALL") -> dict[str, Any]:
    """Current-version B.2.7-C date run with ranking frozen before future access."""
    from app.backtest.candidate_priority import rank_candidates

    # We need the real candidate price-plan objects for event evaluation, but still must
    # finish every current-time rank before reading D+1 rows. Recreate the Production path
    # here and retain only hidden current-time plan fields until the future phase.
    ensure_scanner_version(getattr(scanner, "VERSION", None))
    scope = market_scope.upper().strip()
    if scope not in {"ALL", "KOSPI", "KOSDAQ"}:
        raise ValueError("market_scope must be ALL, KOSPI or KOSDAQ")
    markets = ["KOSPI", "KOSDAQ"] if scope == "ALL" else [scope]
    as_key = _compact(as_of)
    if not all(
        market_store.latest_complete_date(market, "stock", as_key) == as_key
        and market_store.latest_complete_date(market, "index", as_key) == as_key
        for market in markets
    ):
        return {"analysis_date": as_of.isoformat(), "status": "MISSING_EXACT_EOD"}

    fast_start = as_of - timedelta(days=int(scanner.FAST_HISTORY_CALENDAR_DAYS))
    index_rows_by_market: dict[str, list[dict[str, Any]]] = {}
    quick_inputs: list[tuple[str, dict[str, Any]]] = []
    series_by_market: dict[str, dict[str, Any]] = {}

    for market in markets:
        day_rows = market_store.stock_day_rows(market, as_key)
        ordinary: list[dict[str, Any]] = []
        for row in day_rows:
            if scanner._special_reason(row) is not None:  # noqa: SLF001
                continue
            if float(row.get("trade_value") or 0) < scanner.engine.LIQUIDITY_THRESHOLD:
                continue
            ordinary.append(row)
        ordinary.sort(key=lambda row: (float(row.get("trade_value") or 0), float(row.get("market_cap") or 0)), reverse=True)
        ordinary = ordinary[: int(scanner.QUICK_LIMIT_PER_MARKET)]
        quick_inputs.extend((market, row) for row in ordinary)
        index_series = market_store.index_series(market, _compact(fast_start), as_key)
        index_rows_by_market[market] = sorted((dict(row) for row in index_series.rows.values()), key=_row_date)
        series_by_market[market] = market_store.stock_series_many(
            market,
            [str(row.get("code") or "") for row in ordinary],
            _compact(fast_start),
            as_key,
        )

    quick_candidates: list[dict[str, Any]] = []
    context: dict[tuple[str, str], tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
    for market, row in quick_inputs:
        code = str(row.get("code") or "")
        series = (series_by_market.get(market) or {}).get(code)
        stock_rows = sorted((dict(item) for item in (series.rows.values() if series is not None else [])), key=_row_date)
        index_rows = index_rows_by_market.get(market, [])
        quick = scanner._quick_current_candidate(  # noqa: SLF001
            market=market,
            latest_date=as_key,
            row=row,
            stock_rows=stock_rows,
            index_rows=index_rows,
            sector_input=None,
        )
        if quick is None:
            continue
        quick_candidates.append(quick)
        context[(market, code)] = (stock_rows, index_rows)

    quick_candidates.sort(
        key=lambda item: (float(item.get("quick_score") or 0.0), float(item.get("trade_value") or 0.0)),
        reverse=True,
    )
    actionable: list[dict[str, Any]] = []
    for quick in quick_candidates[: int(scanner.DEEP_LIMIT)]:
        candidate = scanner._current_candidate(quick)  # noqa: SLF001
        if candidate is None or candidate.get("candidate_state") not in {"READY", "WATCH", "VALIDATION"}:
            continue
        actionable.append(candidate)

    ranked, ranking_changes = rank_candidates(actionable)
    rows: list[dict[str, Any]] = []
    candidate_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for rank, candidate in enumerate(ranked, start=1):
        market = str(candidate.get("market") or "")
        code = str(candidate.get("code") or "")
        stock_rows, _ = context.get((market, code), ([], []))
        features = compute_entry_stability_features(stock_rows, as_of=as_of)
        candidate_by_key[(market, code)] = candidate
        row = {
            "analysis_date": as_of.isoformat(),
            "code": code,
            "name": candidate.get("name"),
            "market": market,
            "current_rank": rank,
            "candidate_state": candidate.get("candidate_state"),
            "action": candidate.get("action"),
            "strategy": candidate.get("strategy"),
            "risk_status": (candidate.get("risk") or {}).get("status"),
            "risk_warning": bool((candidate.get("risk") or {}).get("warning")),
            "conditions_missing": (candidate.get("conditions") or {}).get("missing"),
            **features,
        }
        rows.append(row)

    thresholds = classify_ready_bands(rows)
    frozen_variants: dict[str, list[dict[str, Any]]] = {}
    rule_meta: dict[str, dict[str, Any]] = {}
    for rule_id in RULE_ORDER:
        variant, meta = apply_entry_stability_rule(rows, rule_id)
        frozen_variants[rule_id] = variant
        rule_meta[rule_id] = meta

    # Freeze rank mapping before any future data read.
    rank_maps = {
        rule_id: {_code(row): int(row.get("guard_rank") or 999999) for row in variant}
        for rule_id, variant in frozen_variants.items()
    }

    rows_with_outcomes = _attach_future_outcomes(rows, candidate_by_key, market_store, as_of=as_of)
    current = sorted(rows_with_outcomes, key=lambda row: (_rank(row), _code(row)))
    variants: dict[str, list[dict[str, Any]]] = {}
    for rule_id in RULE_ORDER:
        mapping = rank_maps[rule_id]
        variant_rows: list[dict[str, Any]] = []
        feature = RULE_SPECS[rule_id]["feature"]
        band = RULE_SPECS[rule_id]["band"]
        for row in current:
            copy = dict(row)
            copy["guard_rank"] = mapping.get(_code(row), 999999)
            copy["guard_rule"] = rule_id
            copy["unstable_by_rule"] = copy.get(f"{feature}_band") == band and str(copy.get("candidate_state") or "") == "READY"
            variant_rows.append(copy)
        variants[rule_id] = sorted(variant_rows, key=lambda row: (int(row.get("guard_rank") or 999999), _code(row)))

    return {
        "analysis_date": as_of.isoformat(),
        "status": "OK",
        "scanner_version": str(scanner.VERSION),
        "candidate_count": len(current),
        "production_ranking_changes": ranking_changes,
        "thresholds": thresholds,
        "rule_meta": rule_meta,
        "current_candidates": current,
        "variant_candidates": variants,
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"count": len(rows)}
    for horizon in (5, 10, 20):
        nums = [n for row in rows if (n := _num(row.get(f"return_{horizon}d"))) is not None]
        result[f"return_{horizon}d_mean"] = _mean(nums)
        result[f"return_{horizon}d_median"] = _median(nums)
        result[f"return_{horizon}d_positive_rate"] = _rate(n > 0 for n in nums)
        if horizon == 20:
            result["return_20d_trimmed_mean"] = _trimmed_mean(nums)
            result["return_20d_mean_without_best"] = _mean_without_best(nums)
            result["return_20d_max"] = max(nums) if nums else None
    result["mfe_20d_mean"] = _mean(row.get("mfe_20d") for row in rows)
    result["mae_20d_mean"] = _mean(row.get("mae_20d") for row in rows)
    for horizon in (10, 20):
        events = [str(row.get(f"event_{horizon}d") or "") for row in rows if row.get(f"event_{horizon}d") is not None]
        result[f"target1_first_{horizon}d_rate"] = _rate(event == "TARGET1_FIRST" for event in events)
        result[f"stop_first_{horizon}d_rate"] = _rate(event == "STOP_FIRST" for event in events)
        result[f"no_event_{horizon}d_rate"] = _rate(event not in {"TARGET1_FIRST", "STOP_FIRST"} for event in events)
    return result


def _select(date_results: list[dict[str, Any]], variant: str, top_n: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in date_results:
        if variant == CURRENT:
            output.extend((item.get("current_candidates") or [])[:top_n])
        else:
            output.extend(((item.get("variant_candidates") or {}).get(variant) or [])[:top_n])
    return output


def _ranking_impact(date_results: list[dict[str, Any]], rule_id: str) -> dict[str, Any]:
    top1 = top3_membership = top3_order = top5_membership = 0
    moves: list[int] = []
    unstable_count = 0
    changed_dates = 0
    for item in date_results:
        current = item.get("current_candidates") or []
        variant = ((item.get("variant_candidates") or {}).get(rule_id) or [])
        if not current or not variant:
            continue
        c1, v1 = [_code(row) for row in current[:1]], [_code(row) for row in variant[:1]]
        c3, v3 = [_code(row) for row in current[:3]], [_code(row) for row in variant[:3]]
        c5, v5 = [_code(row) for row in current[:5]], [_code(row) for row in variant[:5]]
        top1 += int(c1 != v1)
        top3_membership += int(set(c3) != set(v3))
        top3_order += int(c3 != v3)
        top5_membership += int(set(c5) != set(v5))
        changed_dates += int(c3 != v3)
        current_pos = {_code(row): i + 1 for i, row in enumerate(current)}
        variant_pos = {_code(row): i + 1 for i, row in enumerate(variant)}
        moves.extend(abs(variant_pos[code] - rank) for code, rank in current_pos.items() if code in variant_pos)
        unstable_count += int(((item.get("rule_meta") or {}).get(rule_id) or {}).get("unstable_count") or 0)
    return {
        "checked_dates": len(date_results),
        "top1_changed_dates": top1,
        "top3_membership_changed_dates": top3_membership,
        "top3_order_changed_dates": top3_order,
        "top5_membership_changed_dates": top5_membership,
        "mean_absolute_rank_move": _mean(moves),
        "max_absolute_rank_move": max(moves) if moves else 0,
        "unstable_candidate_count": unstable_count,
        "top3_change_rate": (changed_dates / len(date_results)) if date_results else None,
        "change_rate_warning": bool(date_results and (changed_dates / len(date_results)) > 0.5),
    }


def _rule_verdict(current: dict[str, Any], candidate: dict[str, Any]) -> tuple[str, list[str]]:
    cur_t1 = _num(current.get("target1_first_20d_rate"))
    cur_stop = _num(current.get("stop_first_20d_rate"))
    t1 = _num(candidate.get("target1_first_20d_rate"))
    stop = _num(candidate.get("stop_first_20d_rate"))
    cur_return = _num(current.get("return_20d_mean"))
    ret = _num(candidate.get("return_20d_mean"))
    cur_mae = _num(current.get("mae_20d_mean"))
    mae = _num(candidate.get("mae_20d_mean"))

    reasons: list[str] = []
    t1_up = t1 is not None and cur_t1 is not None and t1 > cur_t1
    stop_down = stop is not None and cur_stop is not None and stop < cur_stop
    return_ok = ret is not None and cur_return is not None and ret >= cur_return - 1.0
    mae_ok = mae is not None and cur_mae is not None and mae >= cur_mae - 1.0

    if t1_up:
        reasons.append("Top3 Target1-first 20D improved")
    if stop_down:
        reasons.append("Top3 Stop-first 20D improved")
    if return_ok:
        reasons.append("20D mean stayed within the -1.0pp protection band")
    if mae_ok:
        reasons.append("MAE20 stayed within the -1.0pp protection band")

    if t1_up and stop_down and return_ok and mae_ok:
        return "PASS", reasons
    if (t1_up or stop_down) and return_ok and mae_ok:
        return "WEAK", reasons or ["Only part of the primary event objective improved"]
    return "FAIL", reasons or ["Primary event objective or return/MAE protection failed"]


def aggregate_validation(date_results: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [item for item in date_results if item.get("status") == "OK"]
    comparisons: dict[str, Any] = {}
    for top_n in (1, 3, 5):
        group: dict[str, Any] = {CURRENT: _metrics(_select(valid, CURRENT, top_n))}
        for rule_id in RULE_ORDER:
            group[rule_id] = _metrics(_select(valid, rule_id, top_n))
        comparisons[f"top{top_n}"] = group

    impacts = {rule_id: _ranking_impact(valid, rule_id) for rule_id in RULE_ORDER}
    current_top3 = comparisons["top3"][CURRENT]
    per_rule: dict[str, Any] = {}
    pass_rules: list[str] = []
    for rule_id in RULE_ORDER:
        verdict, reasons = _rule_verdict(current_top3, comparisons["top3"][rule_id])
        per_rule[rule_id] = {"verdict": verdict, "reasons": reasons}
        if verdict == "PASS":
            pass_rules.append(rule_id)

    examples: dict[str, Any] = {}
    for rule_id in RULE_ORDER:
        avoided: list[dict[str, Any]] = []
        demoted_targets: list[dict[str, Any]] = []
        for item in valid:
            current = item.get("current_candidates") or []
            variant = ((item.get("variant_candidates") or {}).get(rule_id) or [])
            current_top3 = {_code(row): row for row in current[:3]}
            variant_top3 = {_code(row) for row in variant[:3]}
            variant_pos = {_code(row): i + 1 for i, row in enumerate(variant)}
            for code, row in current_top3.items():
                if code in variant_top3:
                    continue
                record = {
                    "analysis_date": item.get("analysis_date"),
                    "code": code,
                    "name": row.get("name"),
                    "current_rank": row.get("current_rank"),
                    "guard_rank": variant_pos.get(code),
                    "event_20d": row.get("event_20d"),
                    "return_20d": row.get("return_20d"),
                    "mae_20d": row.get("mae_20d"),
                }
                if row.get("event_20d") == "STOP_FIRST":
                    avoided.append(record)
                elif row.get("event_20d") == "TARGET1_FIRST":
                    demoted_targets.append(record)
        examples[rule_id] = {
            "avoided_stop_count": len(avoided),
            "demoted_target1_count": len(demoted_targets),
            "avoided_stop_candidates": avoided[:10],
            "demoted_target1_candidates": demoted_targets[:10],
        }

    if len(pass_rules) > 1:
        overall = OVERALL_MULTIPLE
    elif pass_rules == [RULE_VOLUME_LOW]:
        overall = OVERALL_VOLUME
    elif pass_rules == [RULE_RETURN_STD_HIGH]:
        overall = OVERALL_RETURN_STD
    elif pass_rules == [RULE_MA20_GAP_HIGH]:
        overall = OVERALL_MA20_GAP
    else:
        overall = OVERALL_NONE

    return {
        "comparisons": comparisons,
        "ranking_impact": impacts,
        "rule_verdicts": per_rule,
        "surviving_rules": pass_rules,
        "examples": examples,
        "verdict": overall,
    }


def run_validation(scanner: Any, market_store: Any, *, evaluation_dates: list[date], market_scope: str = "ALL", progress: Any | None = None) -> dict[str, Any]:
    ensure_scanner_version(getattr(scanner, "VERSION", None))
    date_results: list[dict[str, Any]] = []
    for index, as_of in enumerate(evaluation_dates, start=1):
        result = run_current_date(scanner, market_store, as_of=as_of, market_scope=market_scope)
        date_results.append(result)
        if callable(progress):
            progress(index, len(evaluation_dates), result)

    aggregate = aggregate_validation(date_results)
    missing = [item.get("analysis_date") for item in date_results if item.get("status") != "OK"]
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scanner_version": str(scanner.VERSION),
        "market_scope": market_scope,
        "production_changed": False,
        "guardrail": (
            "Current-version Entry Stability validation only. The three A/B rules and same-date READY Q25/Q75 policy are fixed. "
            "All CURRENT/rule ranks are frozen before D+1 future rows are read."
        ),
        "evaluation_dates": [day.isoformat() for day in evaluation_dates],
        "valid_date_count": len(evaluation_dates) - len(missing),
        "missing_dates": missing,
        "rules": RULE_SPECS,
        "return_mae_protection_pp": 1.0,
        **aggregate,
        "dates": date_results,
    }


def _fmt_pct(value: Any) -> str:
    number = _num(value)
    return "-" if number is None else f"{number:.2f}%"


def _fmt_rate(value: Any) -> str:
    number = _num(value)
    return "-" if number is None else f"{number * 100:.1f}%"


def _markdown(payload: dict[str, Any]) -> str:
    top3 = (payload.get("comparisons") or {}).get("top3") or {}
    current = top3.get(CURRENT) or {}
    lines = [
        f"# Scanner Entry Stability Current-Version Validation — {AUDIT_VERSION}",
        "",
        f"- verdict: **{payload.get('verdict')}**",
        f"- scanner: `{payload.get('scanner_version')}`",
        f"- valid dates: `{payload.get('valid_date_count')}/{len(payload.get('evaluation_dates') or [])}`",
        f"- Production changed: **{payload.get('production_changed')}**",
        "",
        "## Primary — Top3",
        "",
        "| Variant | T1-first 20D | Stop-first 20D | NO_EVENT | 20D mean | 20D trimmed | MAE20 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| CURRENT | {_fmt_rate(current.get('target1_first_20d_rate'))} | {_fmt_rate(current.get('stop_first_20d_rate'))} | "
        f"{_fmt_rate(current.get('no_event_20d_rate'))} | {_fmt_pct(current.get('return_20d_mean'))} | "
        f"{_fmt_pct(current.get('return_20d_trimmed_mean'))} | {_fmt_pct(current.get('mae_20d_mean'))} |",
    ]
    for rule_id in RULE_ORDER:
        metrics = top3.get(rule_id) or {}
        verdict = ((payload.get("rule_verdicts") or {}).get(rule_id) or {}).get("verdict")
        lines.append(
            f"| {rule_id} ({verdict}) | {_fmt_rate(metrics.get('target1_first_20d_rate'))} | {_fmt_rate(metrics.get('stop_first_20d_rate'))} | "
            f"{_fmt_rate(metrics.get('no_event_20d_rate'))} | {_fmt_pct(metrics.get('return_20d_mean'))} | "
            f"{_fmt_pct(metrics.get('return_20d_trimmed_mean'))} | {_fmt_pct(metrics.get('mae_20d_mean'))} |"
        )

    lines += ["", "## Ranking impact", ""]
    for rule_id in RULE_ORDER:
        impact = (payload.get("ranking_impact") or {}).get(rule_id) or {}
        lines.append(
            f"- {rule_id}: Top1 changed `{impact.get('top1_changed_dates')}`, Top3 membership `{impact.get('top3_membership_changed_dates')}`, "
            f"Top3 order `{impact.get('top3_order_changed_dates')}`, unstable `{impact.get('unstable_candidate_count')}`, "
            f"mean rank move `{impact.get('mean_absolute_rank_move')}`"
        )

    lines += ["", "## Rule decisions", ""]
    for rule_id in RULE_ORDER:
        decision = (payload.get("rule_verdicts") or {}).get(rule_id) or {}
        lines.append(f"### {rule_id} — {decision.get('verdict')}")
        lines.extend(f"- {reason}" for reason in (decision.get("reasons") or []))
        ex = (payload.get("examples") or {}).get(rule_id) or {}
        lines.append(f"- avoided STOP_FIRST from CURRENT Top3: `{ex.get('avoided_stop_count')}`")
        lines.append(f"- demoted TARGET1_FIRST from CURRENT Top3: `{ex.get('demoted_target1_count')}`")
        lines.append("")

    lines += [
        "> B.2.7-C validates only the three discovery rules. No new feature, threshold, strategy exception, weight or Production policy is introduced.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_dir / f"scanner-entry-stability-validation_{stamp}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    csv_path = base.with_suffix(".csv")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")

    fields = [
        "analysis_date", "code", "name", "market", "current_rank", "candidate_state", "action", "strategy",
        "volume_ratio_prev20", "volume_ratio_prev20_band", "return_std_20d_pct", "return_std_20d_pct_band",
        "ma20_gap_change_5d_pct", "ma20_gap_change_5d_pct_band",
        "event_10d", "event_20d", "return_10d", "return_20d", "mfe_20d", "mae_20d",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in payload.get("dates") or []:
            for row in item.get("current_candidates") or []:
                writer.writerow(row)
    return {"json": str(json_path), "markdown": str(md_path), "csv": str(csv_path)}
