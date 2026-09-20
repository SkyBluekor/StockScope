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

AUDIT_VERSION = "v0.21.4-B.2.6-C"
EXPECTED_SCANNER_VERSION = "0.21.3.7"
CURRENT = "CURRENT"
OVEREXTENSION = "OVEREXTENSION_Q75_GUARD"
VERDICT_PROMOTE = "PROMOTE_TO_PRODUCTION_CANDIDATE"
VERDICT_KEEP = "KEEP_RESEARCH_ONLY"
VERDICT_REJECT = "REJECT_OVEREXTENSION_GUARD"

OVEREXTENSION_FEATURES = (
    "relative_strength_market_pct",
    "price_vs_ma20_pct",
    "ma20_vs_ma60_pct",
)


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _mean(values: Iterable[Any]) -> float | None:
    nums = [n for value in values if (n := _num(value)) is not None]
    return (sum(nums) / len(nums)) if nums else None


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


def _rate(items: Iterable[bool]) -> float | None:
    values = list(items)
    return (sum(1 for item in values if item) / len(values)) if values else None


def _q75(values: Iterable[Any]) -> float | None:
    nums = sorted(n for value in values if (n := _num(value)) is not None)
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    pos = (len(nums) - 1) * 0.75
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
            "B.2.6-C must run on the current Production Scanner."
        )


def _code(row: dict[str, Any]) -> str:
    return str(row.get("code") or "")


def _current_rank(row: dict[str, Any]) -> int:
    try:
        return int(row.get("current_rank") or row.get("rank") or 999999)
    except (TypeError, ValueError):
        return 999999


def apply_overextension_guard(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Demote READY peers only when >=2 of 3 same-date features exceed READY Q75.

    The function never consumes future outcome fields and never changes non-READY
    positions. Current Production rank remains the tie-break inside each guard group.
    """
    current = sorted((dict(row) for row in rows), key=lambda row: (_current_rank(row), _code(row)))
    ready = [row for row in current if str(row.get("candidate_state") or "") == "READY"]
    thresholds = {feature: _q75(row.get(feature) for row in ready) for feature in OVEREXTENSION_FEATURES}

    annotations: dict[str, dict[str, Any]] = {}
    for row in ready:
        extreme_features: list[str] = []
        available = 0
        for feature in OVEREXTENSION_FEATURES:
            value = _num(row.get(feature))
            threshold = thresholds.get(feature)
            if value is None or threshold is None:
                continue
            available += 1
            if value > threshold:
                extreme_features.append(feature)
        annotations[_code(row)] = {
            "available_feature_count": available,
            "extreme_feature_count": len(extreme_features),
            "extreme_features": extreme_features,
            "overextended": bool(available >= 2 and len(extreme_features) >= 2),
        }

    guarded_ready = sorted(
        ready,
        key=lambda row: (
            int(bool((annotations.get(_code(row)) or {}).get("overextended"))),
            _current_rank(row),
            _code(row),
        ),
    )

    # Replace only READY slots. WATCH/VALIDATION locations are immutable.
    output = list(current)
    ready_positions = [index for index, row in enumerate(current) if str(row.get("candidate_state") or "") == "READY"]
    for position, replacement in zip(ready_positions, guarded_ready):
        output[position] = replacement

    for guard_rank, row in enumerate(output, start=1):
        row["guard_rank"] = guard_rank
        row.update(annotations.get(_code(row)) or {
            "available_feature_count": 0,
            "extreme_feature_count": 0,
            "extreme_features": [],
            "overextended": False,
        })

    return output, {
        "thresholds": thresholds,
        "ready_count": len(ready),
        "overextended_count": sum(1 for item in annotations.values() if item.get("overextended")),
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"count": len(rows)}
    for horizon in (5, 10, 20):
        key = f"return_{horizon}d"
        nums = [n for row in rows if (n := _num(row.get(key))) is not None]
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
    return result


def _select_top(date_results: list[dict[str, Any]], variant: str, top_n: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    key = "current_candidates" if variant == CURRENT else "guard_candidates"
    for item in date_results:
        selected.extend((item.get(key) or [])[:top_n])
    return selected


def _rank_changes(date_result: dict[str, Any]) -> dict[str, Any]:
    current = date_result.get("current_candidates") or []
    guard = date_result.get("guard_candidates") or []
    c1 = [_code(row) for row in current[:1]]
    g1 = [_code(row) for row in guard[:1]]
    c3 = [_code(row) for row in current[:3]]
    g3 = [_code(row) for row in guard[:3]]
    current_pos = {_code(row): i + 1 for i, row in enumerate(current)}
    guard_pos = {_code(row): i + 1 for i, row in enumerate(guard)}
    movements = [abs(guard_pos[code] - rank) for code, rank in current_pos.items() if code in guard_pos]
    return {
        "top1_changed": c1 != g1,
        "top3_membership_changed": set(c3) != set(g3),
        "top3_order_changed": c3 != g3,
        "mean_absolute_rank_move": _mean(movements),
    }


def _verdict(comparisons: dict[str, Any], changes: dict[str, Any]) -> tuple[str, list[str]]:
    cur = comparisons["top3"][CURRENT]
    grd = comparisons["top3"][OVEREXTENSION]
    reasons: list[str] = []

    def gt(key: str) -> bool:
        a, b = _num(grd.get(key)), _num(cur.get(key))
        return a is not None and b is not None and a > b

    def ge(key: str) -> bool:
        a, b = _num(grd.get(key)), _num(cur.get(key))
        return a is not None and b is not None and a >= b

    def le(key: str) -> bool:
        a, b = _num(grd.get(key)), _num(cur.get(key))
        return a is not None and b is not None and a <= b

    primary_return = gt("return_20d_mean")
    mae_nonworse = ge("mae_20d_mean")  # less negative is better
    stop_nonworse = le("stop_first_20d_rate")
    outlier_guard = ge("return_20d_trimmed_mean") and ge("return_20d_mean_without_best")
    secondary = (
        gt("return_20d_median")
        or gt("return_20d_positive_rate")
        or gt("target1_first_20d_rate")
    )
    changed_dates = int(changes.get("top3_order_changed_dates") or 0)

    if primary_return:
        reasons.append("Top3 20D mean improved")
    if mae_nonworse:
        reasons.append("Top3 MAE20 did not worsen")
    if stop_nonworse:
        reasons.append("Top3 Stop-first 20D did not worsen")
    if secondary:
        reasons.append("At least one secondary Top3 metric improved")
    if outlier_guard:
        reasons.append("Trimmed/mean-without-best checks did not worsen")

    if primary_return and mae_nonworse and stop_nonworse and secondary and outlier_guard and changed_dates >= 3:
        return VERDICT_PROMOTE, reasons

    clearly_worse = (
        not ge("return_20d_mean")
        and not ge("mae_20d_mean")
        and not le("stop_first_20d_rate")
    )
    if clearly_worse:
        return VERDICT_REJECT, ["Top3 20D mean, MAE20 and Stop-first all worsened"]
    return VERDICT_KEEP, reasons or ["Current-version evidence is insufficient for Production promotion"]


def aggregate_validation(date_results: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [item for item in date_results if item.get("status") == "OK"]
    comparisons: dict[str, Any] = {}
    for top_n in (1, 3, 5):
        comparisons[f"top{top_n}"] = {
            CURRENT: _metrics(_select_top(valid, CURRENT, top_n)),
            OVEREXTENSION: _metrics(_select_top(valid, OVEREXTENSION, top_n)),
        }

    date_changes = [_rank_changes(item) for item in valid]
    changes = {
        "checked_dates": len(valid),
        "top1_changed_dates": sum(int(item["top1_changed"]) for item in date_changes),
        "top3_membership_changed_dates": sum(int(item["top3_membership_changed"]) for item in date_changes),
        "top3_order_changed_dates": sum(int(item["top3_order_changed"]) for item in date_changes),
        "mean_absolute_rank_move": _mean(item["mean_absolute_rank_move"] for item in date_changes),
        "overextended_candidates": sum(int((item.get("guard_meta") or {}).get("overextended_count") or 0) for item in valid),
    }

    removed_rows: list[dict[str, Any]] = []
    for item in valid:
        current_top3 = {_code(row): row for row in (item.get("current_candidates") or [])[:3]}
        guard_top3 = {_code(row): row for row in (item.get("guard_candidates") or [])[:3]}
        for code, row in current_top3.items():
            if code not in guard_top3:
                removed_rows.append({
                    "analysis_date": item.get("analysis_date"),
                    "code": code,
                    "name": row.get("name"),
                    "current_rank": row.get("current_rank"),
                    "guard_rank": next((x.get("guard_rank") for x in item.get("guard_candidates") or [] if _code(x) == code), None),
                    "return_20d": row.get("return_20d"),
                    "mae_20d": row.get("mae_20d"),
                    "event_20d": row.get("event_20d"),
                    "extreme_features": row.get("extreme_features") or [],
                })

    avoided_bad = sorted(removed_rows, key=lambda row: (_num(row.get("return_20d")) if _num(row.get("return_20d")) is not None else 1e9))[:10]
    missed_winner = sorted(removed_rows, key=lambda row: (_num(row.get("return_20d")) if _num(row.get("return_20d")) is not None else -1e9), reverse=True)[:10]

    verdict, reasons = _verdict(comparisons, changes)
    return {
        "comparisons": comparisons,
        "ranking_changes": changes,
        "examples": {
            "avoided_bad_candidates": avoided_bad,
            "demoted_winners": missed_winner,
        },
        "verdict": verdict,
        "verdict_reasons": reasons,
    }


@dataclass
class OfflineAuditKrx:
    """Strictly local provider shim; any network path is an audit failure."""

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

    async def stock_daily(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - integration guard
        raise RuntimeError("B.2.6-C is offline-only; KRX stock download was attempted.")

    async def index_daily(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - integration guard
        raise RuntimeError("B.2.6-C is offline-only; KRX index download was attempted.")


def _compact(day: date) -> str:
    return day.strftime("%Y%m%d")


def _row_date(row: dict[str, Any]) -> str:
    return str(row.get("date") or row.get("bas_dd") or row.get("BAS_DD") or "")


def _quality_features(snapshot: dict[str, Any] | None) -> dict[str, float | None]:
    if not snapshot:
        return {feature: None for feature in OVEREXTENSION_FEATURES}
    data = snapshot.get("strategy_input")
    technical = snapshot.get("technical") or {}
    current_price = _num(getattr(data, "current_price", None)) or _num(technical.get("current_price"))
    ma20 = _num(getattr(data, "ma20", None)) or _num(technical.get("ma20"))
    ma60 = _num(getattr(data, "ma60", None)) or _num(technical.get("ma60"))
    relative = _num(snapshot.get("relative_strength_market_pct"))
    if relative is None:
        relative = _num(getattr(data, "relative_strength_market_pct", None))
    price_vs_ma20 = ((current_price / ma20) - 1.0) * 100.0 if current_price is not None and ma20 not in {None, 0.0} else None
    ma20_vs_ma60 = ((ma20 / ma60) - 1.0) * 100.0 if ma20 is not None and ma60 not in {None, 0.0} else None
    return {
        "relative_strength_market_pct": relative,
        "price_vs_ma20_pct": price_vs_ma20,
        "ma20_vs_ma60_pct": ma20_vs_ma60,
    }


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
    flat["mfe_20d"] = flat.get("mfe_20d")
    flat["mae_20d"] = flat.get("mae_20d")
    return flat


def run_current_date(scanner: Any, market_store: Any, *, as_of: date, market_scope: str = "ALL") -> dict[str, Any]:
    """Recreate only the current Production candidate path for one historical date."""
    from app.backtest.candidate_priority import rank_candidates
    from app.backtest.models import BacktestConfig
    from app.backtest.scanner_quality.early_pruning_audit import _future_metrics

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
            if scanner._special_reason(row) is not None:  # noqa: SLF001 - audit mirrors Production
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
    context: dict[tuple[str, str], tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]] = {}
    for market, row in quick_inputs:
        code = str(row.get("code") or "")
        series = (series_by_market.get(market) or {}).get(code)
        stock_rows = sorted((dict(item) for item in (series.rows.values() if series is not None else [])), key=_row_date)
        index_rows = index_rows_by_market.get(market, [])
        quick = scanner._quick_current_candidate(  # noqa: SLF001 - canonical current path
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
        context[(market, code)] = (row, stock_rows, index_rows)

    # Match current StockScannerService.run ordering exactly before DEEP_LIMIT.
    quick_candidates.sort(
        key=lambda item: (float(item.get("quick_score") or 0.0), float(item.get("trade_value") or 0.0)),
        reverse=True,
    )
    deep_inputs = quick_candidates[: int(scanner.DEEP_LIMIT)]

    actionable: list[dict[str, Any]] = []
    features_by_key: dict[tuple[str, str], dict[str, float | None]] = {}
    for quick in deep_inputs:
        candidate = scanner._current_candidate(quick)  # noqa: SLF001 - canonical current path
        if candidate is None:
            continue
        if candidate.get("candidate_state") not in {"READY", "WATCH", "VALIDATION"}:
            continue
        actionable.append(candidate)

        market = str(candidate.get("market") or "")
        code = str(candidate.get("code") or "")
        source = context.get((market, code))
        snapshot = None
        if source is not None:
            row, stock_rows, index_rows = source
            if stock_rows:
                config = BacktestConfig(
                    code=code,
                    market=market,
                    start_date=as_of.isoformat(),
                    end_date=as_of.isoformat(),
                    initial_capital=10_000_000,
                    max_holding_days=20,
                    round_trip_cost_pct=0.0,
                )
                snapshot = scanner.engine._signal_snapshot(  # noqa: SLF001 - audit reads current-time features
                    stock_rows=stock_rows,
                    index_rows=index_rows,
                    index=len(stock_rows) - 1,
                    config=config,
                    sector_input=None,
                )
        features_by_key[(market, code)] = _quality_features(snapshot)

    ranked, ranking_changes = rank_candidates(actionable)
    codes_by_market: dict[str, set[str]] = defaultdict(set)
    for candidate in ranked:
        codes_by_market[str(candidate.get("market") or "")].add(str(candidate.get("code") or ""))

    future_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    future_start = _compact(as_of + timedelta(days=1))
    future_end = _compact(as_of + timedelta(days=60))
    for market, codes in codes_by_market.items():
        if not market or not codes:
            continue
        series_map = market_store.stock_series_many(market, sorted(codes), future_start, future_end)
        for code, series in series_map.items():
            future_by_key[(market, str(code))] = sorted((dict(row) for row in series.rows.values()), key=_row_date)

    current_rows: list[dict[str, Any]] = []
    for rank, candidate in enumerate(ranked, start=1):
        market = str(candidate.get("market") or "")
        code = str(candidate.get("code") or "")
        outcome = _future_metrics(
            candidate=candidate,
            future_rows=future_by_key.get((market, code), []),
            horizons=(5, 10, 20),
        )
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
            **(features_by_key.get((market, code)) or {}),
            **_flatten_outcome(outcome),
        }
        current_rows.append(row)

    guard_rows, guard_meta = apply_overextension_guard(current_rows)
    guard_map = {_code(row): row for row in guard_rows}
    for row in current_rows:
        guard = guard_map.get(_code(row)) or {}
        row["guard_rank"] = guard.get("guard_rank")
        row["overextended"] = guard.get("overextended", False)
        row["extreme_feature_count"] = guard.get("extreme_feature_count", 0)
        row["extreme_features"] = guard.get("extreme_features") or []
    # Use one shared row object shape for both lists so outcomes/features stay identical.
    current_rows.sort(key=lambda row: (_current_rank(row), _code(row)))
    guard_rows = sorted((dict(row) for row in current_rows), key=lambda row: (int(row.get("guard_rank") or 999999), _code(row)))

    return {
        "analysis_date": as_of.isoformat(),
        "status": "OK",
        "scanner_version": str(scanner.VERSION),
        "candidate_count": len(current_rows),
        "ranking_changes": ranking_changes,
        "guard_meta": guard_meta,
        "current_candidates": current_rows,
        "guard_candidates": guard_rows,
    }


def run_validation(
    scanner: Any,
    market_store: Any,
    *,
    evaluation_dates: list[date],
    market_scope: str = "ALL",
    progress: Any | None = None,
) -> dict[str, Any]:
    ensure_scanner_version(getattr(scanner, "VERSION", None))
    date_results: list[dict[str, Any]] = []
    for index, as_of in enumerate(evaluation_dates, start=1):
        result = run_current_date(scanner, market_store, as_of=as_of, market_scope=market_scope)
        date_results.append(result)
        if callable(progress):
            progress(index, len(evaluation_dates), result)

    aggregate = aggregate_validation(date_results)
    missing = [item.get("analysis_date") for item in date_results if item.get("status") != "OK"]
    payload = {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scanner_version": str(scanner.VERSION),
        "market_scope": market_scope,
        "production_changed": False,
        "guardrail": (
            "Current-version research validation only. Guard ranking consumes only same-date current features; "
            "future prices are read after Production candidates are fixed and are used only for evaluation."
        ),
        "evaluation_dates": [day.isoformat() for day in evaluation_dates],
        "valid_date_count": len(evaluation_dates) - len(missing),
        "missing_dates": missing,
        "guard_definition": {
            "features": list(OVEREXTENSION_FEATURES),
            "threshold": "same-date READY Q75",
            "rule": ">=2 available features and >=2 features above Q75 => overextended",
            "ranking": "Only READY slots are reordered: non-overextended first, then current Production rank.",
            "tuned_in_this_step": False,
        },
        **aggregate,
        "dates": date_results,
    }
    return payload


def _fmt_pct(value: Any) -> str:
    number = _num(value)
    return "-" if number is None else f"{number:.2f}%"


def _fmt_rate(value: Any) -> str:
    number = _num(value)
    return "-" if number is None else f"{number * 100:.1f}%"


def _markdown(payload: dict[str, Any]) -> str:
    comp = payload.get("comparisons") or {}
    top3 = comp.get("top3") or {}
    cur = top3.get(CURRENT) or {}
    grd = top3.get(OVEREXTENSION) or {}
    changes = payload.get("ranking_changes") or {}
    lines = [
        f"# Scanner Candidate Quality Current-Version Validation — {AUDIT_VERSION}",
        "",
        f"- verdict: **{payload.get('verdict')}**",
        f"- scanner: `{payload.get('scanner_version')}`",
        f"- valid dates: `{payload.get('valid_date_count')}/{len(payload.get('evaluation_dates') or [])}`",
        f"- Production changed: **{payload.get('production_changed')}**",
        "",
        "## Primary — Top3",
        "",
        "| Metric | CURRENT | OVEREXTENSION_Q75_GUARD |",
        "|---|---:|---:|",
        f"| 10D mean | {_fmt_pct(cur.get('return_10d_mean'))} | {_fmt_pct(grd.get('return_10d_mean'))} |",
        f"| 20D mean | {_fmt_pct(cur.get('return_20d_mean'))} | {_fmt_pct(grd.get('return_20d_mean'))} |",
        f"| 20D median | {_fmt_pct(cur.get('return_20d_median'))} | {_fmt_pct(grd.get('return_20d_median'))} |",
        f"| 20D trimmed mean | {_fmt_pct(cur.get('return_20d_trimmed_mean'))} | {_fmt_pct(grd.get('return_20d_trimmed_mean'))} |",
        f"| 20D mean without best | {_fmt_pct(cur.get('return_20d_mean_without_best'))} | {_fmt_pct(grd.get('return_20d_mean_without_best'))} |",
        f"| 20D positive | {_fmt_rate(cur.get('return_20d_positive_rate'))} | {_fmt_rate(grd.get('return_20d_positive_rate'))} |",
        f"| Target1-first 20D | {_fmt_rate(cur.get('target1_first_20d_rate'))} | {_fmt_rate(grd.get('target1_first_20d_rate'))} |",
        f"| Stop-first 20D | {_fmt_rate(cur.get('stop_first_20d_rate'))} | {_fmt_rate(grd.get('stop_first_20d_rate'))} |",
        f"| MFE20 | {_fmt_pct(cur.get('mfe_20d_mean'))} | {_fmt_pct(grd.get('mfe_20d_mean'))} |",
        f"| MAE20 | {_fmt_pct(cur.get('mae_20d_mean'))} | {_fmt_pct(grd.get('mae_20d_mean'))} |",
        "",
        "## Ranking impact",
        "",
        f"- Top1 changed dates: `{changes.get('top1_changed_dates')}`",
        f"- Top3 membership changed dates: `{changes.get('top3_membership_changed_dates')}`",
        f"- Top3 order changed dates: `{changes.get('top3_order_changed_dates')}`",
        f"- Overextended candidates: `{changes.get('overextended_candidates')}`",
        f"- Mean absolute rank move: `{changes.get('mean_absolute_rank_move')}`",
        "",
        "## Decision reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in (payload.get("verdict_reasons") or []))
    missing = payload.get("missing_dates") or []
    if missing:
        lines += ["", "## Missing dates", "", *[f"- {day}" for day in missing]]
    lines += [
        "",
        "> No feature/threshold tuning occurs in B.2.6-C. Future outcomes are evaluation-only and never ranking inputs.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_dir / f"scanner-candidate-quality-validation_{stamp}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    csv_path = base.with_suffix(".csv")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")

    fields = [
        "analysis_date", "code", "name", "market", "current_rank", "guard_rank",
        "candidate_state", "action", "strategy", "risk_status", "risk_warning", "conditions_missing",
        *OVEREXTENSION_FEATURES, "overextended", "extreme_feature_count", "extreme_features",
        "return_5d", "return_10d", "return_20d", "mfe_20d", "mae_20d", "event_10d", "event_20d",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for date_result in payload.get("dates") or []:
            for row in date_result.get("current_candidates") or []:
                copy = dict(row)
                copy["extreme_features"] = ",".join(copy.get("extreme_features") or [])
                writer.writerow(copy)
    return {"json": str(json_path), "markdown": str(md_path), "csv": str(csv_path)}
