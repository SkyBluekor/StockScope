from __future__ import annotations

import csv
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

AUDIT_VERSION = "v0.21.4-B.2.3.2c"
KST = timezone(timedelta(hours=9), name="KST")

POLICY_CURRENT = "CURRENT_STRUCTURAL"
POLICY_CAP_1_5R = "CAP_1_5R"
POLICY_FIXED_1_5R = "FIXED_1_5R"
POLICIES = (POLICY_CURRENT, POLICY_CAP_1_5R, POLICY_FIXED_1_5R)

ACTIONABLE_STATES = {"READY", "WATCH", "VALIDATION"}


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _compact(value: date | str | Any) -> str:
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return str(value or "").replace("-", "")


def _pct_distance(entry: float | None, target: float | None) -> float | None:
    if entry is None or target is None or entry <= 0:
        return None
    return (target / entry - 1.0) * 100.0


def _risk_multiple(entry: float | None, stop: float | None, target: float | None) -> float | None:
    if entry is None or stop is None or target is None:
        return None
    risk = entry - stop
    if risk <= 0:
        return None
    return (target - entry) / risk


def _pct(count: int, total: int) -> float | None:
    return round(count / total * 100.0, 4) if total else None


def _mean(values: Iterable[float | None]) -> float | None:
    normalized = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return round(statistics.fmean(normalized), 6) if normalized else None


def _median(values: Iterable[float | None]) -> float | None:
    normalized = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return round(statistics.median(normalized), 6) if normalized else None


def _wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> dict[str, float | None]:
    if total <= 0:
        return {"low_pct": None, "high_pct": None}
    n = float(total)
    p = float(successes) / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    half = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n) / denominator
    return {
        "low_pct": round(max(0.0, center - half) * 100.0, 4),
        "high_pct": round(min(1.0, center + half) * 100.0, 4),
    }


def build_target_variants(*, entry: float, stop: float, current_target: float) -> dict[str, float]:
    if not (0 < stop < entry < current_target):
        raise ValueError("Target1 audit requires 0 < stop < entry < current_target")
    one_half_r = entry + (entry - stop) * 1.5
    return {
        POLICY_CURRENT: current_target,
        POLICY_CAP_1_5R: min(current_target, one_half_r),
        POLICY_FIXED_1_5R: one_half_r,
    }


def distance_bucket(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value < 5.0:
        return "0~5%"
    if value < 10.0:
        return "5~10%"
    if value < 15.0:
        return "10~15%"
    if value < 20.0:
        return "15~20%"
    return "20%+"


def r_bucket(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value <= 1.5:
        return "<=1.5R"
    if value < 2.0:
        return "1.5~2R"
    if value < 3.0:
        return "2~3R"
    if value < 4.0:
        return "3~4R"
    return "4R+"


def classify_target_source(risk_plan: dict[str, Any]) -> dict[str, Any]:
    audit = dict(risk_plan.get("target1_audit") or {})
    selected = [
        item for item in (audit.get("structural_candidates") or [])
        if bool(item.get("selected")) and str(item.get("kind") or "") in {"RESISTANCE", "HIGH20"}
    ]
    selected_kinds = {str(item.get("kind") or "") for item in selected}
    if selected_kinds == {"RESISTANCE", "HIGH20"}:
        source = "RESISTANCE_AND_HIGH20"
    elif "RESISTANCE" in selected_kinds:
        source = "RESISTANCE"
    elif "HIGH20" in selected_kinds:
        source = "HIGH20"
    else:
        basis_code = str(audit.get("target1_basis_code") or "")
        if basis_code == "RESISTANCE":
            source = "RESISTANCE"
        elif basis_code == "HIGH20":
            source = "HIGH20"
        elif basis_code == "RISK_1_5R":
            source = "R_FALLBACK"
        else:
            raw = str(risk_plan.get("target1_basis") or "")
            if "저항" in raw:
                source = "RESISTANCE"
            elif "20일" in raw and "고점" in raw:
                source = "HIGH20"
            elif "1.5" in raw:
                source = "R_FALLBACK"
            else:
                source = "UNKNOWN"
    return {
        "source": source,
        "basis": risk_plan.get("target1_basis") or audit.get("target1_basis"),
        "resistance_price": next((_float(item.get("price")) for item in selected if item.get("kind") == "RESISTANCE"), None),
        "high20": next((_float(item.get("price")) for item in selected if item.get("kind") == "HIGH20"), None),
    }


def _event_for_horizon(
    rows: list[dict[str, Any]],
    *,
    target: float,
    stop: float,
    horizon: int,
) -> dict[str, Any]:
    sample = rows[: max(0, int(horizon))]
    if len(sample) < horizon:
        return {
            "complete": False,
            "rows": len(sample),
            "raw_status": "INSUFFICIENT_FUTURE_DATA",
            "primary_status": "INSUFFICIENT_FUTURE_DATA",
            "sensitivity_status": "INSUFFICIENT_FUTURE_DATA",
            "day": None,
        }
    for index, row in enumerate(sample, start=1):
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        close = _float(row.get("close"))
        if high is None:
            high = close
        if low is None:
            low = close
        target_hit = high is not None and high >= target
        stop_hit = low is not None and low <= stop
        if target_hit and stop_hit:
            return {
                "complete": True,
                "rows": len(sample),
                "raw_status": "AMBIGUOUS_SAME_BAR",
                "primary_status": "STOP_FIRST",
                "sensitivity_status": "TARGET1_FIRST",
                "day": index,
            }
        if target_hit:
            return {
                "complete": True,
                "rows": len(sample),
                "raw_status": "TARGET1_FIRST",
                "primary_status": "TARGET1_FIRST",
                "sensitivity_status": "TARGET1_FIRST",
                "day": index,
            }
        if stop_hit:
            return {
                "complete": True,
                "rows": len(sample),
                "raw_status": "STOP_FIRST",
                "primary_status": "STOP_FIRST",
                "sensitivity_status": "STOP_FIRST",
                "day": index,
            }
    return {
        "complete": True,
        "rows": len(sample),
        "raw_status": "NO_EVENT",
        "primary_status": "NO_EVENT",
        "sensitivity_status": "NO_EVENT",
        "day": None,
    }


def _mfe_mae(rows: list[dict[str, Any]], *, entry: float, horizon: int) -> tuple[float | None, float | None]:
    sample = rows[: max(0, int(horizon))]
    if len(sample) < horizon or entry <= 0:
        return None, None
    highs = [(_float(row.get("high")) or _float(row.get("close"))) for row in sample]
    lows = [(_float(row.get("low")) or _float(row.get("close"))) for row in sample]
    valid_highs = [value for value in highs if value is not None]
    valid_lows = [value for value in lows if value is not None]
    mfe = (max(valid_highs) / entry - 1.0) * 100.0 if valid_highs else None
    mae = (min(valid_lows) / entry - 1.0) * 100.0 if valid_lows else None
    return (None if mfe is None else round(mfe, 6), None if mae is None else round(mae, 6))


def evaluate_signal(
    *,
    candidate: dict[str, Any],
    future_rows: list[dict[str, Any]],
    analysis_date: date,
    horizons: tuple[int, ...] = (5, 10, 20),
) -> dict[str, Any] | None:
    guide = dict(candidate.get("entry_risk_guide") or {})
    risk_plan = dict(guide.get("risk") or candidate.get("price_plan") or {})
    entry = _float(risk_plan.get("entry_reference_price")) or _float(candidate.get("current_price"))
    stop = _float(risk_plan.get("invalidation_price"))
    current_target = _float(risk_plan.get("target1_price"))
    if entry is None or stop is None or current_target is None or not (0 < stop < entry < current_target):
        return None

    variants = build_target_variants(entry=entry, stop=stop, current_target=current_target)
    source = classify_target_source(risk_plan)
    current_distance = _pct_distance(entry, current_target)
    current_r = _risk_multiple(entry, stop, current_target)
    policy_results: dict[str, Any] = {}
    for policy_id, target in variants.items():
        forward: dict[str, Any] = {}
        for horizon in sorted(set(int(v) for v in horizons if int(v) > 0)):
            event = _event_for_horizon(future_rows, target=target, stop=stop, horizon=horizon)
            mfe, mae = _mfe_mae(future_rows, entry=entry, horizon=horizon)
            event["mfe_pct"] = mfe
            event["mae_pct"] = mae
            forward[str(horizon)] = event
        policy_results[policy_id] = {
            "target1_price": round(target, 6),
            "distance_pct": round(_pct_distance(entry, target) or 0.0, 6),
            "r_multiple": round(_risk_multiple(entry, stop, target) or 0.0, 6),
            "forward": forward,
        }

    return {
        "analysis_date": analysis_date.isoformat(),
        "market": str(candidate.get("market") or ""),
        "code": str(candidate.get("code") or ""),
        "name": str(candidate.get("name") or ""),
        "strategy": candidate.get("strategy"),
        "candidate_state": candidate.get("candidate_state"),
        "action": candidate.get("action"),
        "rank": candidate.get("_audit_rank"),
        "entry_reference_price": round(entry, 6),
        "invalidation_price": round(stop, 6),
        "risk_amount": round(entry - stop, 6),
        "current_target1_price": round(current_target, 6),
        "current_target1_distance_pct": None if current_distance is None else round(current_distance, 6),
        "current_target1_r_multiple": None if current_r is None else round(current_r, 6),
        "distance_bucket": distance_bucket(current_distance),
        "r_bucket": r_bucket(current_r),
        "target_source": source,
        "policies": policy_results,
    }


def _policy_aggregate(signals: list[dict[str, Any]], policy_id: str, horizon: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for signal in signals:
        item = (((signal.get("policies") or {}).get(policy_id) or {}).get("forward") or {}).get(str(horizon)) or {}
        if item.get("complete"):
            rows.append(item)
    primary = Counter(str(item.get("primary_status") or "") for item in rows)
    sensitivity = Counter(str(item.get("sensitivity_status") or "") for item in rows)
    target_days = [float(item["day"]) for item in rows if item.get("raw_status") == "TARGET1_FIRST" and item.get("day") is not None]
    return {
        "policy_id": policy_id,
        "horizon": horizon,
        "complete_signals": len(rows),
        "target1_first_count": primary["TARGET1_FIRST"],
        "target1_first_pct": _pct(primary["TARGET1_FIRST"], len(rows)),
        "target1_first_ci95": _wilson_interval(primary["TARGET1_FIRST"], len(rows)),
        "stop_first_count": primary["STOP_FIRST"],
        "stop_first_pct": _pct(primary["STOP_FIRST"], len(rows)),
        "no_event_count": primary["NO_EVENT"],
        "ambiguous_same_bar_count": sum(1 for item in rows if item.get("raw_status") == "AMBIGUOUS_SAME_BAR"),
        "sensitivity_target1_first_pct": _pct(sensitivity["TARGET1_FIRST"], len(rows)),
        "median_target_hit_day": _median(target_days),
    }


def _bucket_aggregate(signals: list[dict[str, Any]], key: str, *, horizon: int = 20) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        label = str(signal.get(key) or "UNKNOWN")
        grouped[label].append(signal)
    preferred = {
        "distance_bucket": ["0~5%", "5~10%", "10~15%", "15~20%", "20%+", "UNKNOWN"],
        "r_bucket": ["<=1.5R", "1.5~2R", "2~3R", "3~4R", "4R+", "UNKNOWN"],
    }.get(key, [])
    labels = [label for label in preferred if label in grouped] + sorted(label for label in grouped if label not in preferred)
    result = []
    for label in labels:
        bucket_signals = grouped[label]
        row = {
            "bucket": label,
            "sample_count": len(bucket_signals),
            "current_target_distance_mean_pct": _mean(s.get("current_target1_distance_pct") for s in bucket_signals),
            "current_target_r_mean": _mean(s.get("current_target1_r_multiple") for s in bucket_signals),
        }
        for policy_id in POLICIES:
            metrics = _policy_aggregate(bucket_signals, policy_id, horizon)
            row[policy_id] = {
                "target1_first_pct": metrics["target1_first_pct"],
                "stop_first_pct": metrics["stop_first_pct"],
                "complete_signals": metrics["complete_signals"],
            }
        result.append(row)
    return result


def _source_aggregate(signals: list[dict[str, Any]], *, horizon: int = 20) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        grouped[str((signal.get("target_source") or {}).get("source") or "UNKNOWN")].append(signal)
    result = []
    for source, bucket_signals in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        row = {"source": source, "sample_count": len(bucket_signals)}
        for policy_id in POLICIES:
            metrics = _policy_aggregate(bucket_signals, policy_id, horizon)
            row[policy_id] = {
                "target1_first_pct": metrics["target1_first_pct"],
                "stop_first_pct": metrics["stop_first_pct"],
            }
        result.append(row)
    return result


def _transitions(signals: list[dict[str, Any]], *, left: str, right: str, horizon: int = 20) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for signal in signals:
        left_item = (((signal.get("policies") or {}).get(left) or {}).get("forward") or {}).get(str(horizon)) or {}
        right_item = (((signal.get("policies") or {}).get(right) or {}).get("forward") or {}).get(str(horizon)) or {}
        if not left_item.get("complete") or not right_item.get("complete"):
            continue
        before = str(left_item.get("primary_status") or "UNKNOWN")
        after = str(right_item.get("primary_status") or "UNKNOWN")
        counts[f"{before}->{after}"] += 1
    return dict(sorted(counts.items()))


def aggregate_audit(signals: list[dict[str, Any]], *, valid_dates: int, requested_dates: int) -> dict[str, Any]:
    policy_summary = {
        policy_id: {str(h): _policy_aggregate(signals, policy_id, h) for h in (5, 10, 20)}
        for policy_id in POLICIES
    }
    current20 = policy_summary[POLICY_CURRENT]["20"]
    cap20 = policy_summary[POLICY_CAP_1_5R]["20"]
    fixed20 = policy_summary[POLICY_FIXED_1_5R]["20"]
    extreme = [s for s in signals if s.get("distance_bucket") == "20%+" or s.get("r_bucket") == "4R+"]
    extreme_current20 = _policy_aggregate(extreme, POLICY_CURRENT, 20)

    # Smoke-first, conservative signal only. This is not a Production policy decision.
    if valid_dates < min(10, requested_dates) or current20["complete_signals"] < 30:
        smoke_verdict = "INSUFFICIENT_SAMPLE"
    else:
        cap_delta = None
        if current20["target1_first_pct"] is not None and cap20["target1_first_pct"] is not None:
            cap_delta = round(cap20["target1_first_pct"] - current20["target1_first_pct"], 4)
        if (
            cap_delta is not None
            and cap_delta >= 7.5
            and len(extreme) >= 10
            and extreme_current20["target1_first_pct"] is not None
            and extreme_current20["target1_first_pct"] < 25.0
        ):
            smoke_verdict = "CAP_1_5R_REVIEW"
        elif (
            current20["target1_first_pct"] is not None
            and cap20["target1_first_pct"] is not None
            and abs(cap20["target1_first_pct"] - current20["target1_first_pct"]) < 3.0
        ):
            smoke_verdict = "CURRENT_SUPPORTED_SMOKE"
        else:
            smoke_verdict = "INCONCLUSIVE"

    return {
        "signal_count": len(signals),
        "valid_dates": valid_dates,
        "requested_dates": requested_dates,
        "smoke_verdict": smoke_verdict,
        "smoke_verdict_guardrail": "20-date smoke verdict is a review signal only; it does not modify Production Target1.",
        "policy_summary": policy_summary,
        "distance_buckets": _bucket_aggregate(signals, "distance_bucket", horizon=20),
        "r_buckets": _bucket_aggregate(signals, "r_bucket", horizon=20),
        "source_buckets": _source_aggregate(signals, horizon=20),
        "current_to_cap_transitions_20d": _transitions(signals, left=POLICY_CURRENT, right=POLICY_CAP_1_5R, horizon=20),
        "current_to_fixed_transitions_20d": _transitions(signals, left=POLICY_CURRENT, right=POLICY_FIXED_1_5R, horizon=20),
        "extreme_20pct_or_4r": {
            "sample_count": len(extreme),
            "current_20d": extreme_current20,
        },
    }


class Target1RealismAuditor:
    """Offline, smoke-first Target1 policy comparison using the Production Scanner candidate path."""

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
        raise ValueError("market_scope must be ALL, KOSPI, or KOSDAQ")

    def _exact_day_available(self, markets: list[str], as_of: date) -> bool:
        key = _compact(as_of)
        return all(
            self.market_store.latest_complete_date(market, "stock", key) == key
            and self.market_store.latest_complete_date(market, "index", key) == key
            for market in markets
        )

    def _ranked_candidates(self, *, as_of: date, market_scope: str) -> list[dict[str, Any]]:
        from app.backtest.candidate_priority import rank_candidates

        markets = self._markets(market_scope)
        key = _compact(as_of)
        fast_start = as_of - timedelta(days=int(self.scanner.FAST_HISTORY_CALENDAR_DAYS))
        quick_candidates: list[dict[str, Any]] = []

        for market in markets:
            day_rows = self.market_store.stock_day_rows(market, key)
            ordinary: list[dict[str, Any]] = []
            for row in day_rows:
                if self.scanner._special_reason(row) is not None:  # noqa: SLF001
                    continue
                if float(row.get("trade_value") or 0) < self.scanner.engine.LIQUIDITY_THRESHOLD:
                    continue
                ordinary.append(row)
            ordinary.sort(
                key=lambda row: (float(row.get("trade_value") or 0), float(row.get("market_cap") or 0)),
                reverse=True,
            )
            prefiltered = ordinary[: int(self.scanner.QUICK_LIMIT_PER_MARKET)]
            index_series = self.market_store.index_series(market, _compact(fast_start), key)
            index_rows = sorted((dict(row) for row in index_series.rows.values()), key=lambda row: _compact(row.get("date") or row.get("bas_dd")))
            series_map = self.market_store.stock_series_many(
                market,
                [str(row.get("code") or "") for row in prefiltered],
                _compact(fast_start),
                key,
            )
            for row in prefiltered:
                code = str(row.get("code") or "")
                series = series_map.get(code)
                stock_rows = list(series.rows.values()) if series is not None else []
                quick = self.scanner._quick_current_candidate(  # noqa: SLF001
                    market=market,
                    latest_date=key,
                    row=row,
                    stock_rows=stock_rows,
                    index_rows=index_rows,
                )
                if quick is not None:
                    quick_candidates.append(quick)

        quick_candidates.sort(
            key=lambda item: (float(item.get("quick_score") or 0), float(item.get("trade_value") or 0)),
            reverse=True,
        )
        selected = quick_candidates[: int(self.scanner.DEEP_LIMIT)]
        current: list[dict[str, Any]] = []
        for item in selected:
            evaluated = self.scanner._current_candidate(item)  # noqa: SLF001
            if evaluated is not None:
                current.append(evaluated)
        current.sort(key=lambda item: float(item.get("internal_rank") or 0.0), reverse=True)
        actionable = [item for item in current if item.get("candidate_state") in ACTIONABLE_STATES]
        ranked, _ranking_changes = rank_candidates(actionable)
        for index, item in enumerate(ranked, start=1):
            item["_audit_rank"] = index
        return ranked

    def _future_rows(self, *, candidates: list[dict[str, Any]], as_of: date, max_horizon: int) -> dict[tuple[str, str], list[dict[str, Any]]]:
        by_market: dict[str, set[str]] = defaultdict(set)
        for candidate in candidates:
            by_market[str(candidate.get("market") or "")].add(str(candidate.get("code") or ""))
        start = _compact(as_of + timedelta(days=1))
        end = _compact(as_of + timedelta(days=max(45, max_horizon * 3)))
        result: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for market, codes in by_market.items():
            series_map = self.market_store.stock_series_many(market, sorted(codes), start, end)
            for code, series in series_map.items():
                rows = sorted((dict(row) for row in series.rows.values()), key=lambda row: _compact(row.get("date") or row.get("bas_dd")))
                result[(market, code)] = rows
        return result

    def run_date(self, *, as_of: date, market_scope: str = "ALL", horizons: tuple[int, ...] = (5, 10, 20)) -> dict[str, Any]:
        started = time.perf_counter()
        markets = self._markets(market_scope)
        if not self._exact_day_available(markets, as_of):
            return {
                "analysis_date": as_of.isoformat(),
                "status": "SKIPPED_INSUFFICIENT_DATA",
                "signals": [],
                "runtime_seconds": round(time.perf_counter() - started, 6),
            }
        ranked = self._ranked_candidates(as_of=as_of, market_scope=market_scope)
        future = self._future_rows(candidates=ranked, as_of=as_of, max_horizon=max(horizons))
        signals: list[dict[str, Any]] = []
        for candidate in ranked:
            key = (str(candidate.get("market") or ""), str(candidate.get("code") or ""))
            signal = evaluate_signal(
                candidate=candidate,
                future_rows=future.get(key, []),
                analysis_date=as_of,
                horizons=horizons,
            )
            if signal is not None:
                signals.append(signal)
        return {
            "analysis_date": as_of.isoformat(),
            "status": "OK",
            "candidate_count": len(ranked),
            "signal_count": len(signals),
            "signals": signals,
            "runtime_seconds": round(time.perf_counter() - started, 6),
        }

    def run_dates(
        self,
        *,
        dates: list[date],
        market_scope: str = "ALL",
        horizons: tuple[int, ...] = (5, 10, 20),
        progress_callback: Callable[[int, int, date, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        runs: list[dict[str, Any]] = []
        all_signals: list[dict[str, Any]] = []
        for index, as_of in enumerate(dates, start=1):
            run = self.run_date(as_of=as_of, market_scope=market_scope, horizons=horizons)
            runs.append(run)
            if run.get("status") == "OK":
                all_signals.extend(run.get("signals") or [])
            if progress_callback is not None:
                progress_callback(index, len(dates), as_of, run)
        valid_dates = sum(1 for run in runs if run.get("status") == "OK")
        aggregate = aggregate_audit(all_signals, valid_dates=valid_dates, requested_dates=len(dates))
        return {
            "audit_version": AUDIT_VERSION,
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "scanner_version": str(getattr(self.scanner, "VERSION", "unknown")),
            "market_scope": market_scope.upper(),
            "evaluation_dates": [value.isoformat() for value in dates],
            "valid_date_count": valid_dates,
            "skipped_date_count": len(dates) - valid_dates,
            "policies": list(POLICIES),
            "aggregate": aggregate,
            "runs": runs,
            "runtime_seconds": round(time.perf_counter() - started, 6),
            "production_changed": False,
            "guardrail": "Audit-only. Production Target1, Strategy, Ranking, Risk, Entry, Stop and Scanner VERSION are unchanged.",
        }


def _csv_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in payload.get("runs") or []:
        for signal in run.get("signals") or []:
            row = {
                "analysis_date": signal.get("analysis_date"),
                "market": signal.get("market"),
                "code": signal.get("code"),
                "name": signal.get("name"),
                "rank": signal.get("rank"),
                "strategy": signal.get("strategy"),
                "candidate_state": signal.get("candidate_state"),
                "entry_reference_price": signal.get("entry_reference_price"),
                "invalidation_price": signal.get("invalidation_price"),
                "current_target1_price": signal.get("current_target1_price"),
                "current_target1_distance_pct": signal.get("current_target1_distance_pct"),
                "current_target1_r_multiple": signal.get("current_target1_r_multiple"),
                "distance_bucket": signal.get("distance_bucket"),
                "r_bucket": signal.get("r_bucket"),
                "target_source": (signal.get("target_source") or {}).get("source"),
            }
            for policy_id in POLICIES:
                policy = (signal.get("policies") or {}).get(policy_id) or {}
                row[f"{policy_id}_target"] = policy.get("target1_price")
                row[f"{policy_id}_20d"] = (((policy.get("forward") or {}).get("20") or {}).get("primary_status"))
                row[f"{policy_id}_20d_raw"] = (((policy.get("forward") or {}).get("20") or {}).get("raw_status"))
            rows.append(row)
    return rows


def write_outputs(payload: dict[str, Any], *, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"target1-realism-audit_{stamp}.json"
    csv_path = output_dir / f"target1-realism-signals_{stamp}.csv"
    md_path = output_dir / f"target1-realism-summary_{stamp}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = _csv_rows(payload)
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        csv_path.write_text("", encoding="utf-8-sig")

    aggregate = payload.get("aggregate") or {}
    policies = aggregate.get("policy_summary") or {}
    lines = [
        f"# Target1 Realism Smoke Audit — {payload.get('audit_version')}",
        "",
        f"- Scanner: **{payload.get('scanner_version')}**",
        f"- Market scope: **{payload.get('market_scope')}**",
        f"- Valid dates: **{payload.get('valid_date_count')}/{len(payload.get('evaluation_dates') or [])}**",
        f"- Signals: **{aggregate.get('signal_count')}**",
        f"- Smoke verdict: **{aggregate.get('smoke_verdict')}**",
        "- Production changed: **False**",
        "",
        "## 20D primary outcome",
        "",
        "| Policy | Target-first | Stop-first | Complete |",
        "|---|---:|---:|---:|",
    ]
    for policy_id in POLICIES:
        item = ((policies.get(policy_id) or {}).get("20") or {})
        lines.append(
            f"| {policy_id} | {item.get('target1_first_pct')}% | {item.get('stop_first_pct')}% | {item.get('complete_signals')} |"
        )
    extreme = aggregate.get("extreme_20pct_or_4r") or {}
    extreme20 = extreme.get("current_20d") or {}
    lines.extend([
        "",
        "## Extreme current Target1 (20%+ or 4R+)",
        "",
        f"- Sample: **{extreme.get('sample_count')}**",
        f"- CURRENT 20D Target-first: **{extreme20.get('target1_first_pct')}%**",
        f"- CURRENT 20D Stop-first: **{extreme20.get('stop_first_pct')}%**",
        "",
        "## Guardrail",
        "",
        "This is a smoke-first audit. It does not modify Production Target1. Run a larger sample only if the 20-date result is inconclusive or extreme-target samples are too small.",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "markdown": md_path}
