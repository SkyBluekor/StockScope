from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

AUDIT_VERSION = "v0.21.4-B.2.7-A.B"
SNAPSHOT_VERSION = "v0.21.4-B.2.7-A.B-input"
VERDICT_PROMISING = "PROMISING_ENTRY_STABILITY_SIGNAL"
VERDICT_WEAK = "WEAK_ENTRY_STABILITY_SIGNAL"
VERDICT_NONE = "NO_USEFUL_ENTRY_STABILITY_SIGNAL"

FEATURES = (
    "atr14_pct",
    "return_std_20d_pct",
    "max_drawdown_20d_pct",
    "close_location",
    "ma20_gap_change_5d_pct",
    "volume_ratio_prev20",
)

FEATURE_LABELS = {
    "atr14_pct": "ATR14 %",
    "return_std_20d_pct": "20D return std %",
    "max_drawdown_20d_pct": "20D max drawdown %",
    "close_location": "Close location",
    "ma20_gap_change_5d_pct": "MA20 gap change 5D pp",
    "volume_ratio_prev20": "Volume / previous-20D avg",
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


def _rate(values: Iterable[bool]) -> float | None:
    items = list(values)
    return (sum(1 for value in items if value) / len(items)) if items else None


def _quantile(values: Iterable[Any], q: float) -> float | None:
    nums = sorted(n for value in values if (n := _num(value)) is not None)
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    q = max(0.0, min(float(q), 1.0))
    pos = (len(nums) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return nums[lo]
    weight = pos - lo
    return nums[lo] * (1.0 - weight) + nums[hi] * weight


def _row_date(row: dict[str, Any]) -> str:
    return str(row.get("date") or row.get("bas_dd") or row.get("BAS_DD") or "").replace("-", "")


def _field(row: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = _num(row.get(name))
        if value is not None:
            return value
    return None


def _close(row: dict[str, Any]) -> float | None:
    return _field(row, "close", "close_price", "closing_price")


def _high(row: dict[str, Any]) -> float | None:
    return _field(row, "high", "high_price")


def _low(row: dict[str, Any]) -> float | None:
    return _field(row, "low", "low_price")


def _volume(row: dict[str, Any]) -> float | None:
    return _field(row, "volume", "trade_volume")


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    recent = values[-window:]
    return sum(recent) / window


def compute_entry_stability_features(rows: list[dict[str, Any]], *, as_of: date | str) -> dict[str, float | None]:
    """Compute Entry Stability features from rows on or before ``as_of`` only.

    The function intentionally ignores every row after the analysis date. This is the
    core no-lookahead contract for B.2.7.
    """
    as_key = as_of.strftime("%Y%m%d") if isinstance(as_of, date) else str(as_of).replace("-", "")
    history = sorted((dict(row) for row in rows if _row_date(row) and _row_date(row) <= as_key), key=_row_date)
    if not history:
        return {feature: None for feature in FEATURES}

    closes = [value for row in history if (value := _close(row)) is not None]
    current = history[-1]
    current_close = _close(current)

    # ATR14: arithmetic mean of 14 true ranges, requiring a previous close.
    atr14_pct: float | None = None
    if len(history) >= 15 and current_close not in {None, 0.0}:
        tr_values: list[float] = []
        for index in range(len(history) - 14, len(history)):
            row = history[index]
            prev_close = _close(history[index - 1])
            high = _high(row)
            low = _low(row)
            if high is None or low is None or prev_close is None:
                tr_values = []
                break
            tr_values.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        if len(tr_values) == 14:
            atr14_pct = (sum(tr_values) / 14.0) / current_close * 100.0

    return_std_20d_pct: float | None = None
    if len(closes) >= 21:
        recent = closes[-21:]
        returns = [((recent[i] / recent[i - 1]) - 1.0) * 100.0 for i in range(1, len(recent)) if recent[i - 1] != 0]
        if len(returns) == 20:
            return_std_20d_pct = statistics.pstdev(returns)

    max_drawdown_20d_pct: float | None = None
    if len(closes) >= 20:
        peak: float | None = None
        drawdowns: list[float] = []
        for close in closes[-20:]:
            peak = close if peak is None else max(peak, close)
            if peak and peak > 0:
                drawdowns.append((close / peak - 1.0) * 100.0)
        if drawdowns:
            max_drawdown_20d_pct = min(drawdowns)

    close_location: float | None = None
    high = _high(current)
    low = _low(current)
    if current_close is not None and high is not None and low is not None and high > low:
        close_location = max(0.0, min(1.0, (current_close - low) / (high - low)))

    ma20_gap_change_5d_pct: float | None = None
    if len(closes) >= 25:
        ma20_now = _sma(closes, 20)
        past_end = len(closes) - 5
        past_slice = closes[:past_end]
        ma20_past = _sma(past_slice, 20)
        close_past = closes[past_end - 1] if past_end >= 1 else None
        if ma20_now not in {None, 0.0} and ma20_past not in {None, 0.0} and current_close is not None and close_past is not None:
            current_gap = (current_close / ma20_now - 1.0) * 100.0
            past_gap = (close_past / ma20_past - 1.0) * 100.0
            ma20_gap_change_5d_pct = current_gap - past_gap

    volume_ratio_prev20: float | None = None
    if len(history) >= 21:
        current_volume = _volume(current)
        previous = [_volume(row) for row in history[-21:-1]]
        if current_volume is not None and all(value is not None for value in previous):
            prev_values = [float(value) for value in previous if value is not None]
            average = sum(prev_values) / len(prev_values) if prev_values else 0.0
            if average > 0:
                volume_ratio_prev20 = current_volume / average

    return {
        "atr14_pct": atr14_pct,
        "return_std_20d_pct": return_std_20d_pct,
        "max_drawdown_20d_pct": max_drawdown_20d_pct,
        "close_location": close_location,
        "ma20_gap_change_5d_pct": ma20_gap_change_5d_pct,
        "volume_ratio_prev20": volume_ratio_prev20,
    }


def label_for_event(event: Any) -> str:
    value = str(event or "").upper()
    if value == "TARGET1_FIRST":
        return "GOOD_ENTRY"
    if value == "STOP_FIRST":
        return "BAD_ENTRY"
    return "NO_EVENT"


def load_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("snapshot_version") != SNAPSHOT_VERSION:
        raise ValueError(f"unexpected B.2.7 snapshot version: {payload.get('snapshot_version')}")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("B.2.7 snapshot has no candidates")
    return payload


def enrich_snapshot(snapshot: dict[str, Any], market_store: Any, *, progress: Any | None = None) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in snapshot.get("candidates") or []:
        by_date[str(raw.get("analysis_date") or "")].append(dict(raw))

    enriched: list[dict[str, Any]] = []
    dates = sorted(day for day in by_date if day)
    for index, day in enumerate(dates, start=1):
        as_of = date.fromisoformat(day)
        start = (as_of - timedelta(days=120)).strftime("%Y%m%d")
        end = as_of.strftime("%Y%m%d")
        candidates = by_date[day]
        rows_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for market in ("KOSPI", "KOSDAQ"):
            codes = sorted({str(row.get("code") or "") for row in candidates if str(row.get("market") or "") == market})
            if not codes:
                continue
            series_map = market_store.stock_series_many(market, codes, start, end)
            for code, series in series_map.items():
                rows_by_key[(market, str(code))] = sorted((dict(item) for item in series.rows.values()), key=_row_date)

        missing_history = 0
        for candidate in candidates:
            market = str(candidate.get("market") or "")
            code = str(candidate.get("code") or "")
            history = rows_by_key.get((market, code), [])
            if not history:
                missing_history += 1
            features = compute_entry_stability_features(history, as_of=as_of)
            row = dict(candidate)
            row.update(features)
            row["label_10d"] = label_for_event(row.get("event_10d"))
            row["label_20d"] = label_for_event(row.get("event_20d"))
            enriched.append(row)

        if callable(progress):
            progress(index, len(dates), day, len(candidates), missing_history)
    return enriched


def _label_stats(rows: list[dict[str, Any]], feature: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label in ("GOOD_ENTRY", "BAD_ENTRY", "NO_EVENT"):
        subset = [row for row in rows if row.get("label_20d") == label and _num(row.get(feature)) is not None]
        result[label] = {
            "count": len(subset),
            "median": _median(row.get(feature) for row in subset),
            "mean": _mean(row.get(feature) for row in subset),
        }
    return result


def add_same_date_quartile_bands(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float | None]]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[str(row.get("analysis_date") or "")].append(row)

    thresholds: dict[str, dict[str, dict[str, float | None]]] = {}
    for day, day_rows in by_date.items():
        thresholds[day] = {}
        for feature in FEATURES:
            q25 = _quantile((row.get(feature) for row in day_rows), 0.25)
            q75 = _quantile((row.get(feature) for row in day_rows), 0.75)
            thresholds[day][feature] = {"q25": q25, "q75": q75}
            for row in day_rows:
                value = _num(row.get(feature))
                band = "MISSING"
                if value is not None and q25 is not None and q75 is not None:
                    if value <= q25:
                        band = "LOW"
                    elif value >= q75:
                        band = "HIGH"
                    else:
                        band = "MID"
                row[f"{feature}_band"] = band
    return thresholds


def _event_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    labels = [str(row.get("label_20d") or "NO_EVENT") for row in rows]
    return {
        "count": total,
        "target1_first_20d_rate": _rate(label == "GOOD_ENTRY" for label in labels),
        "stop_first_20d_rate": _rate(label == "BAD_ENTRY" for label in labels),
        "no_event_20d_rate": _rate(label == "NO_EVENT" for label in labels),
        "return_20d_mean": _mean(row.get("return_20d") for row in rows),
        "return_20d_median": _median(row.get("return_20d") for row in rows),
        "mfe_20d_mean": _mean(row.get("mfe_20d") for row in rows),
        "mae_20d_mean": _mean(row.get("mae_20d") for row in rows),
    }


def band_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for feature in FEATURES:
        result[feature] = {}
        for band in ("LOW", "MID", "HIGH"):
            subset = [row for row in rows if row.get(f"{feature}_band") == band]
            result[feature][band] = _event_metrics(subset)
    return result


def _rule_id(feature: str, band: str) -> str:
    return f"{feature}:{band}"


def discover_rule_candidates(rows: list[dict[str, Any]], *, max_rules: int = 3, min_band_count: int = 20) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for feature in FEATURES:
        for band in ("LOW", "HIGH"):
            subset = [row for row in rows if row.get(f"{feature}_band") == band]
            rest = [row for row in rows if row.get(f"{feature}_band") in {"LOW", "MID", "HIGH"} and row.get(f"{feature}_band") != band]
            if len(subset) < min_band_count or len(rest) < min_band_count:
                continue
            sub = _event_metrics(subset)
            rem = _event_metrics(rest)
            sub_badness = (_num(sub.get("stop_first_20d_rate")) or 0.0) - (_num(sub.get("target1_first_20d_rate")) or 0.0)
            rem_badness = (_num(rem.get("stop_first_20d_rate")) or 0.0) - (_num(rem.get("target1_first_20d_rate")) or 0.0)
            separation = sub_badness - rem_badness
            if separation <= 0:
                continue
            candidates.append({
                "rule_id": _rule_id(feature, band),
                "feature": feature,
                "band": band,
                "count": len(subset),
                "separation_score": separation,
                "unstable": sub,
                "rest": rem,
                "definition": f"Demote same-date READY candidates in the {band} quartile band of {feature}; preserve current rank within groups.",
            })
    candidates.sort(key=lambda item: (-float(item.get("separation_score") or 0.0), str(item.get("rule_id"))))
    return candidates[: max(0, int(max_rules))]


def apply_rule(rows: list[dict[str, Any]], rule: dict[str, Any]) -> list[dict[str, Any]]:
    feature = str(rule.get("feature") or "")
    band = str(rule.get("band") or "")
    current = sorted((dict(row) for row in rows), key=lambda row: (int(row.get("rank") or 999999), str(row.get("code") or "")))
    stable = [row for row in current if row.get(f"{feature}_band") != band]
    unstable = [row for row in current if row.get(f"{feature}_band") == band]
    output = stable + unstable
    for index, row in enumerate(output, start=1):
        row["research_rank"] = index
        row["unstable_by_rule"] = row.get(f"{feature}_band") == band
    return output


def _select_top(rows: list[dict[str, Any]], *, rank_key: str, top_n: int) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[str(row.get("analysis_date") or "")].append(row)
    selected: list[dict[str, Any]] = []
    for day in sorted(by_date):
        selected.extend(sorted(by_date[day], key=lambda row: (int(row.get(rank_key) or 999999), str(row.get("code") or "")))[:top_n])
    return selected


def smoke_rules(rows: list[dict[str, Any]], rules: list[dict[str, Any]]) -> dict[str, Any]:
    current = _event_metrics(_select_top(rows, rank_key="rank", top_n=3))
    result: dict[str, Any] = {"CURRENT": current}
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[str(row.get("analysis_date") or "")].append(row)

    for rule in rules:
        reranked: list[dict[str, Any]] = []
        changed_dates = 0
        for day in sorted(by_date):
            source = sorted(by_date[day], key=lambda row: (int(row.get("rank") or 999999), str(row.get("code") or "")))
            changed = apply_rule(source, rule)
            if [str(row.get("code")) for row in source[:3]] != [str(row.get("code")) for row in changed[:3]]:
                changed_dates += 1
            for row in changed:
                copy = dict(row)
                copy["analysis_date"] = day
                reranked.append(copy)
        metrics = _event_metrics(_select_top(reranked, rank_key="research_rank", top_n=3))
        metrics["top3_changed_dates"] = changed_dates
        result[str(rule.get("rule_id"))] = metrics
    return result


def strategy_breakdown(rows: list[dict[str, Any]], rules: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for rule in rules:
        feature = str(rule.get("feature") or "")
        band = str(rule.get("band") or "")
        key = str(rule.get("rule_id"))
        output[key] = {}
        strategies = sorted({str(row.get("strategy") or "UNKNOWN") for row in rows})
        for strategy in strategies:
            subset = [row for row in rows if str(row.get("strategy") or "UNKNOWN") == strategy and row.get(f"{feature}_band") == band]
            if subset:
                output[key][strategy] = _event_metrics(subset)
    return output


def choose_verdict(smoke: dict[str, Any], rules: list[dict[str, Any]]) -> tuple[str, list[str]]:
    current = smoke.get("CURRENT") or {}
    cur_t1 = _num(current.get("target1_first_20d_rate"))
    cur_stop = _num(current.get("stop_first_20d_rate"))
    promising: list[str] = []
    weak: list[str] = []
    for rule in rules:
        rid = str(rule.get("rule_id"))
        metrics = smoke.get(rid) or {}
        t1 = _num(metrics.get("target1_first_20d_rate"))
        stop = _num(metrics.get("stop_first_20d_rate"))
        ret = _num(metrics.get("return_20d_mean"))
        mae = _num(metrics.get("mae_20d_mean"))
        cur_ret = _num(current.get("return_20d_mean"))
        cur_mae = _num(current.get("mae_20d_mean"))
        primary = t1 is not None and stop is not None and cur_t1 is not None and cur_stop is not None and t1 > cur_t1 and stop < cur_stop
        secondary_not_both_worse = not (
            ret is not None and cur_ret is not None and ret < cur_ret
            and mae is not None and cur_mae is not None and mae < cur_mae
        )
        if primary and secondary_not_both_worse:
            promising.append(rid)
        elif t1 is not None and stop is not None and cur_t1 is not None and cur_stop is not None and (t1 > cur_t1 or stop < cur_stop):
            weak.append(rid)
    if promising:
        return VERDICT_PROMISING, [f"{rid} improved both Top3 Target1-first and Stop-first without worsening both return and MAE" for rid in promising]
    if weak or rules:
        reasons = [f"{rid} improved only part of the primary event objective" for rid in weak]
        return VERDICT_WEAK, reasons or ["Feature separation exists, but no discovery rule improved both primary event rates"]
    return VERDICT_NONE, ["No quartile-side feature band separated BAD_ENTRY from GOOD_ENTRY strongly enough to form a rule candidate"]


def run_audit(snapshot: dict[str, Any], market_store: Any, *, progress: Any | None = None) -> dict[str, Any]:
    rows = enrich_snapshot(snapshot, market_store, progress=progress)
    thresholds = add_same_date_quartile_bands(rows)
    separation = {feature: _label_stats(rows, feature) for feature in FEATURES}
    bands = band_analysis(rows)
    rules = discover_rule_candidates(rows)
    smoke = smoke_rules(rows, rules)
    strategies = strategy_breakdown(rows, rules)
    verdict, reasons = choose_verdict(smoke, rules)

    missing_counts = {feature: sum(1 for row in rows if _num(row.get(feature)) is None) for feature in FEATURES}
    labels20 = {label: sum(1 for row in rows if row.get("label_20d") == label) for label in ("GOOD_ENTRY", "BAD_ENTRY", "NO_EVENT")}
    labels10 = {label: sum(1 for row in rows if row.get("label_10d") == label) for label in ("GOOD_ENTRY", "BAD_ENTRY", "NO_EVENT")}

    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "production_changed": False,
        "guardrail": "Research-only Entry Stability discovery. Features are computed from local stock rows on/before analysis_date. Future outcomes from the bundled snapshot are labels/evaluation only and never ranking inputs.",
        "source": snapshot.get("source") or {},
        "feature_definitions": {
            "atr14_pct": "14-session arithmetic mean True Range / current close * 100, using rows <= D only.",
            "return_std_20d_pct": "Population standard deviation of the last 20 close-to-close daily returns, using rows <= D only.",
            "max_drawdown_20d_pct": "Worst peak-to-close drawdown across the last 20 closes, using rows <= D only.",
            "close_location": "(close-low)/(high-low) on D, clipped to [0,1].",
            "ma20_gap_change_5d_pct": "Current close/MA20 gap minus the same gap five trading sessions earlier, percentage-point delta.",
            "volume_ratio_prev20": "D volume / arithmetic mean volume of the previous 20 sessions.",
        },
        "label_definition": {
            "GOOD_ENTRY": "TARGET1_FIRST",
            "BAD_ENTRY": "STOP_FIRST",
            "NO_EVENT": "all other event statuses",
            "primary_horizon": "20D",
        },
        "candidate_count": len(rows),
        "date_count": len({str(row.get('analysis_date') or '') for row in rows}),
        "label_counts_10d": labels10,
        "label_counts_20d": labels20,
        "missing_feature_counts": missing_counts,
        "feature_separation": separation,
        "quartile_band_analysis": bands,
        "rule_candidates": rules,
        "development_top3_smoke": smoke,
        "strategy_breakdown": strategies,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "production_changed": False,
        "threshold_policy": "same-date READY Q25/Q75 only; no optimized numeric threshold search",
        "rows": rows,
        "same_date_thresholds": thresholds,
    }


def _fmt_pct(value: Any) -> str:
    num = _num(value)
    return "-" if num is None else f"{num:.2f}%"


def _fmt_rate(value: Any) -> str:
    num = _num(value)
    return "-" if num is None else f"{num * 100:.1f}%"


def _fmt_num(value: Any, digits: int = 3) -> str:
    num = _num(value)
    return "-" if num is None else f"{num:.{digits}f}"


def _markdown(payload: dict[str, Any]) -> str:
    smoke = payload.get("development_top3_smoke") or {}
    current = smoke.get("CURRENT") or {}
    rules = payload.get("rule_candidates") or []
    lines = [
        f"# Scanner Entry Stability Audit — {AUDIT_VERSION}",
        "",
        f"- verdict: **{payload.get('verdict')}**",
        f"- development dates: `{payload.get('date_count')}`",
        f"- READY candidates: `{payload.get('candidate_count')}`",
        f"- Production changed: **{payload.get('production_changed')}**",
        "",
        "## Primary labels — 20D",
        "",
    ]
    counts = payload.get("label_counts_20d") or {}
    lines += [
        f"- GOOD_ENTRY / Target1-first: `{counts.get('GOOD_ENTRY', 0)}`",
        f"- BAD_ENTRY / Stop-first: `{counts.get('BAD_ENTRY', 0)}`",
        f"- NO_EVENT: `{counts.get('NO_EVENT', 0)}`",
        "",
        "## Feature separation — 20D event labels",
        "",
        "| Feature | GOOD median | BAD median | NO_EVENT median | missing |",
        "|---|---:|---:|---:|---:|",
    ]
    separation = payload.get("feature_separation") or {}
    missing = payload.get("missing_feature_counts") or {}
    for feature in FEATURES:
        item = separation.get(feature) or {}
        lines.append(
            f"| {FEATURE_LABELS[feature]} | {_fmt_num((item.get('GOOD_ENTRY') or {}).get('median'))} | "
            f"{_fmt_num((item.get('BAD_ENTRY') or {}).get('median'))} | {_fmt_num((item.get('NO_EVENT') or {}).get('median'))} | {missing.get(feature, 0)} |"
        )

    lines += [
        "",
        "## Candidate rules — discovery only",
        "",
        "| Rule | N unstable | separation | unstable T1 | unstable Stop |",
        "|---|---:|---:|---:|---:|",
    ]
    for rule in rules:
        unstable = rule.get("unstable") or {}
        lines.append(
            f"| `{rule.get('rule_id')}` | {rule.get('count')} | {_fmt_num(rule.get('separation_score'))} | "
            f"{_fmt_rate(unstable.get('target1_first_20d_rate'))} | {_fmt_rate(unstable.get('stop_first_20d_rate'))} |"
        )
    if not rules:
        lines.append("| - | - | - | - | - |")

    lines += [
        "",
        "## Development Top3 smoke",
        "",
        "| Variant | T1-first 20D | Stop-first 20D | NO_EVENT | 20D mean | MAE20 | changed dates |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| CURRENT | {_fmt_rate(current.get('target1_first_20d_rate'))} | {_fmt_rate(current.get('stop_first_20d_rate'))} | "
        f"{_fmt_rate(current.get('no_event_20d_rate'))} | {_fmt_pct(current.get('return_20d_mean'))} | {_fmt_pct(current.get('mae_20d_mean'))} | - |",
    ]
    for rule in rules:
        metrics = smoke.get(str(rule.get("rule_id"))) or {}
        lines.append(
            f"| `{rule.get('rule_id')}` | {_fmt_rate(metrics.get('target1_first_20d_rate'))} | {_fmt_rate(metrics.get('stop_first_20d_rate'))} | "
            f"{_fmt_rate(metrics.get('no_event_20d_rate'))} | {_fmt_pct(metrics.get('return_20d_mean'))} | {_fmt_pct(metrics.get('mae_20d_mean'))} | {metrics.get('top3_changed_dates')} |"
        )

    lines += ["", "## Decision reasons", ""]
    lines.extend(f"- {reason}" for reason in (payload.get("verdict_reasons") or []))
    lines += [
        "",
        "> Discovery-only. Same-date Q25/Q75 bands are the only thresholds tested. No Production Scanner/Ranking/Strategy/Risk/Entry/Target policy is modified.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_dir / f"scanner-entry-stability_{stamp}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    csv_path = base.with_suffix(".csv")

    json_payload = dict(payload)
    rows = json_payload.pop("rows", [])
    thresholds = json_payload.pop("same_date_thresholds", {})
    json_payload["same_date_thresholds"] = thresholds
    json_payload["rows"] = rows
    json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")

    fields = [
        "analysis_date", "rank", "code", "name", "market", "strategy", "label_10d", "label_20d",
        *FEATURES,
        *[f"{feature}_band" for feature in FEATURES],
        "event_10d", "event_20d", "return_10d", "return_20d", "mfe_20d", "mae_20d",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return {"json": str(json_path), "markdown": str(md_path), "csv": str(csv_path)}
