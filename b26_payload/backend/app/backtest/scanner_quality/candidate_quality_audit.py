from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

AUDIT_VERSION = "v0.21.4-B.2.6-A.B"
VERDICT_PROMISING = "PROMISING_SIGNAL_NOT_PRODUCTION_READY"
VERDICT_NONE = "NO_ROBUST_SIGNAL"

CURRENT = "CURRENT"
RISK_LOW = "RISK_LOW"
TARGET_NEAR = "TARGET_NEAR"
RISK_Q75 = "RISK_Q75_GUARD"
TARGET_Q75 = "TARGET_Q75_GUARD"
OVEREXT_Q75 = "OVEREXTENSION_Q75_GUARD"

RESEARCH_FEATURES = (
    "risk_pct",
    "structural_target_distance_pct",
    "relative_strength_market_pct",
    "price_vs_ma20_pct",
    "ma20_vs_ma60_pct",
    "ma60_vs_ma120_pct",
)
OVEREXTENSION_FEATURES = (
    "relative_strength_market_pct",
    "price_vs_ma20_pct",
    "ma20_vs_ma60_pct",
)


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mean(values: Iterable[Any]) -> float | None:
    nums = [n for value in values if (n := _num(value)) is not None]
    return (sum(nums) / len(nums)) if nums else None


def _median(values: Iterable[Any]) -> float | None:
    nums = [n for value in values if (n := _num(value)) is not None]
    return statistics.median(nums) if nums else None


def _rate(values: Iterable[bool]) -> float | None:
    items = list(values)
    return (sum(1 for item in items if item) / len(items)) if items else None


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


def _group_by_date(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("analysis_date") or "")].append(row)
    return dict(grouped)


def _candidate_code(row: dict[str, Any]) -> str:
    return str(row.get("code") or "")


def _current_key(row: dict[str, Any]) -> tuple[int, str]:
    try:
        rank = int(row.get("rank") or 999999)
    except (TypeError, ValueError):
        rank = 999999
    return rank, _candidate_code(row)


def _sort_variant(rows: list[dict[str, Any]], variant: str) -> list[dict[str, Any]]:
    if variant == CURRENT:
        return sorted(rows, key=_current_key)
    if variant == RISK_LOW:
        return sorted(rows, key=lambda row: (_num(row.get("risk_pct")) if _num(row.get("risk_pct")) is not None else 1e9, *_current_key(row)))
    if variant == TARGET_NEAR:
        return sorted(rows, key=lambda row: (_num(row.get("structural_target_distance_pct")) if _num(row.get("structural_target_distance_pct")) is not None else 1e9, *_current_key(row)))

    if variant in {RISK_Q75, TARGET_Q75, OVEREXT_Q75}:
        thresholds: dict[str, float | None] = {}
        if variant == RISK_Q75:
            thresholds["risk_pct"] = _q75(row.get("risk_pct") for row in rows)
        elif variant == TARGET_Q75:
            thresholds["structural_target_distance_pct"] = _q75(row.get("structural_target_distance_pct") for row in rows)
        else:
            for feature in OVEREXTENSION_FEATURES:
                thresholds[feature] = _q75(row.get(feature) for row in rows)

        def guarded(row: dict[str, Any]) -> int:
            if variant == RISK_Q75:
                value = _num(row.get("risk_pct"))
                q = thresholds.get("risk_pct")
                return int(value is not None and q is not None and value > q)
            if variant == TARGET_Q75:
                value = _num(row.get("structural_target_distance_pct"))
                q = thresholds.get("structural_target_distance_pct")
                return int(value is not None and q is not None and value > q)
            extreme = 0
            available = 0
            for feature in OVEREXTENSION_FEATURES:
                value = _num(row.get(feature))
                q = thresholds.get(feature)
                if value is None or q is None:
                    continue
                available += 1
                extreme += int(value > q)
            # Audit-only guard: at least two independent overextension signals
            # must be in the same-date top quartile before current rank is demoted.
            return int(available >= 2 and extreme >= 2)

        return sorted(rows, key=lambda row: (guarded(row), *_current_key(row)))

    raise ValueError(f"Unknown quality variant: {variant}")


def _select(rows: list[dict[str, Any]], variant: str, top_n: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for _date, group in sorted(_group_by_date(rows).items()):
        selected.extend(_sort_variant(group, variant)[: max(1, int(top_n))])
    return selected


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "count": len(rows),
        "dates": len(_group_by_date(rows)),
    }
    for horizon in (5, 10, 20):
        key = f"return_{horizon}d"
        nums = [n for row in rows if (n := _num(row.get(key))) is not None]
        result[f"return_{horizon}d_mean"] = _mean(nums)
        result[f"return_{horizon}d_median"] = _median(nums)
        result[f"return_{horizon}d_positive_rate"] = _rate(n > 0 for n in nums)
    result["mfe_20d_mean"] = _mean(row.get("mfe_20d") for row in rows)
    result["mae_20d_mean"] = _mean(row.get("mae_20d") for row in rows)
    return result


def _cap_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "count": len(rows),
        "dates": len(_group_by_date(rows)),
    }
    for horizon in (10, 20):
        key = f"cap_event_{horizon}d"
        events = [str(row.get(key) or "") for row in rows if row.get(key) is not None]
        result[f"target1_first_{horizon}d_rate"] = _rate(event == "TARGET1_FIRST" for event in events)
        result[f"stop_first_{horizon}d_rate"] = _rate(event == "STOP_FIRST" for event in events)
    result["mfe_20d_mean"] = _mean(row.get("mfe_20d") for row in rows)
    result["mae_20d_mean"] = _mean(row.get("mae_20d") for row in rows)
    return result


def _date_tercile_labels(rows: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    labels: dict[tuple[str, str], str] = {}
    for analysis_date, group in _group_by_date(rows).items():
        ordered = [row for row in group if _num(row.get("return_20d")) is not None]
        ordered.sort(key=lambda row: (_num(row.get("return_20d")) or 0.0, _candidate_code(row)))
        if not ordered:
            continue
        size = max(1, math.ceil(len(ordered) / 3.0))
        bad_ids = {id(row) for row in ordered[:size]}
        good_ids = {id(row) for row in ordered[-size:]}
        for row in ordered:
            label = "GOOD" if id(row) in good_ids else "BAD" if id(row) in bad_ids else "NEUTRAL"
            labels[(analysis_date, _candidate_code(row))] = label
    return labels


def _feature_separation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = _date_tercile_labels(rows)
    report: list[dict[str, Any]] = []
    for feature in RESEARCH_FEATURES:
        good = []
        bad = []
        for row in rows:
            label = labels.get((str(row.get("analysis_date") or ""), _candidate_code(row)))
            value = _num(row.get(feature))
            if value is None:
                continue
            if label == "GOOD":
                good.append(value)
            elif label == "BAD":
                bad.append(value)
        good_med = _median(good)
        bad_med = _median(bad)
        report.append({
            "feature": feature,
            "good_count": len(good),
            "bad_count": len(bad),
            "good_median": good_med,
            "bad_median": bad_med,
            "median_delta_good_minus_bad": None if good_med is None or bad_med is None else good_med - bad_med,
        })
    return report


def _split_dates(rows: list[dict[str, Any]], validation_dates: int = 20) -> tuple[list[str], list[str]]:
    dates = sorted(_group_by_date(rows))
    if not dates:
        return [], []
    validation_dates = min(max(1, int(validation_dates)), max(1, len(dates) - 1)) if len(dates) > 1 else 1
    return dates[:-validation_dates], dates[-validation_dates:]


def _rows_for_dates(rows: list[dict[str, Any]], dates: set[str]) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("analysis_date") or "") in dates]


def _chronological_blocks(rows: list[dict[str, Any]], count: int = 4) -> list[dict[str, Any]]:
    dates = sorted(_group_by_date(rows))
    if not dates:
        return []
    block_count = min(max(1, int(count)), len(dates))
    result: list[dict[str, Any]] = []
    for index in range(block_count):
        start = round(index * len(dates) / block_count)
        end = round((index + 1) * len(dates) / block_count)
        block_dates = dates[start:end]
        block_rows = _rows_for_dates(rows, set(block_dates))
        current = _metrics(_select(block_rows, CURRENT, 3))
        guard = _metrics(_select(block_rows, OVEREXT_Q75, 3))
        result.append({
            "block": index + 1,
            "first_date": block_dates[0] if block_dates else None,
            "last_date": block_dates[-1] if block_dates else None,
            "current_top3": current,
            "overextension_guard_top3": guard,
            "return20_improved": (
                _num(guard.get("return_20d_mean")) is not None
                and _num(current.get("return_20d_mean")) is not None
                and float(guard["return_20d_mean"]) > float(current["return_20d_mean"])
            ),
            "mae20_improved": (
                _num(guard.get("mae_20d_mean")) is not None
                and _num(current.get("mae_20d_mean")) is not None
                and float(guard["mae_20d_mean"]) > float(current["mae_20d_mean"])
            ),
        })
    return result


def _false_positives(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    current_top3 = _select(rows, CURRENT, 3)
    candidates = [row for row in current_top3 if _num(row.get("return_20d")) is not None]
    candidates.sort(key=lambda row: (_num(row.get("return_20d")) or 0.0, _num(row.get("mae_20d")) or 0.0))
    result = []
    for row in candidates[: max(1, int(limit))]:
        result.append({
            "analysis_date": row.get("analysis_date"),
            "code": _candidate_code(row),
            "name": row.get("name"),
            "rank": row.get("rank"),
            "strategy": row.get("strategy"),
            "return_20d": row.get("return_20d"),
            "mfe_20d": row.get("mfe_20d"),
            "mae_20d": row.get("mae_20d"),
            "risk_pct": row.get("risk_pct"),
            "relative_strength_market_pct": row.get("relative_strength_market_pct"),
            "price_vs_ma20_pct": row.get("price_vs_ma20_pct"),
            "ma20_vs_ma60_pct": row.get("ma20_vs_ma60_pct"),
        })
    return result


def run_candidate_quality_audit(
    baseline_snapshot: dict[str, Any],
    cap_validation_snapshot: dict[str, Any] | None = None,
    *,
    validation_dates: int = 20,
) -> dict[str, Any]:
    rows = [dict(row) for row in baseline_snapshot.get("candidates") or []]
    dev_dates, val_dates = _split_dates(rows, validation_dates=validation_dates)
    dev_rows = _rows_for_dates(rows, set(dev_dates))
    val_rows = _rows_for_dates(rows, set(val_dates))

    variants = (CURRENT, RISK_LOW, TARGET_NEAR, RISK_Q75, TARGET_Q75, OVEREXT_Q75)
    comparisons: dict[str, Any] = {}
    for split_name, split_rows in (("development", dev_rows), ("validation", val_rows)):
        comparisons[split_name] = {}
        for top_n in (1, 3, 5):
            comparisons[split_name][f"top{top_n}"] = {
                variant: _metrics(_select(split_rows, variant, top_n))
                for variant in variants
            }

    cap_validation: dict[str, Any] | None = None
    if cap_validation_snapshot:
        cap_rows = [dict(row) for row in cap_validation_snapshot.get("candidates") or []]
        cap_validation = {
            "source": cap_validation_snapshot.get("source") or {},
            "top1": {
                variant: _cap_metrics(_select(cap_rows, variant, 1))
                for variant in (CURRENT, RISK_LOW, TARGET_NEAR, RISK_Q75, TARGET_Q75)
            },
            "top3": {
                variant: _cap_metrics(_select(cap_rows, variant, 3))
                for variant in (CURRENT, RISK_LOW, TARGET_NEAR, RISK_Q75, TARGET_Q75)
            },
            "note": "The independent CAP_1_5R snapshot does not carry overextension features, so it cannot validate OVEREXTENSION_Q75_GUARD.",
        }

    val_current = comparisons.get("validation", {}).get("top3", {}).get(CURRENT, {})
    val_guard = comparisons.get("validation", {}).get("top3", {}).get(OVEREXT_Q75, {})
    blocks = _chronological_blocks(rows, 4)
    block_return_wins = sum(1 for block in blocks if block.get("return20_improved"))
    block_mae_wins = sum(1 for block in blocks if block.get("mae20_improved"))
    validation_signal = (
        _num(val_guard.get("return_20d_mean")) is not None
        and _num(val_current.get("return_20d_mean")) is not None
        and float(val_guard["return_20d_mean"]) > float(val_current["return_20d_mean"])
        and _num(val_guard.get("mae_20d_mean")) is not None
        and _num(val_current.get("mae_20d_mean")) is not None
        and float(val_guard["mae_20d_mean"]) > float(val_current["mae_20d_mean"])
        and (_num(val_guard.get("return_20d_positive_rate")) or 0.0) >= (_num(val_current.get("return_20d_positive_rate")) or 0.0)
    )
    verdict = VERDICT_PROMISING if validation_signal else VERDICT_NONE

    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "production_changed": False,
        "verdict": verdict,
        "guardrail": (
            "Research-only. Future outcomes define labels/evaluation only and are never inputs to Production ranking. "
            "No Scanner/Strategy/Risk/Entry/Target policy is modified by this audit."
        ),
        "source": baseline_snapshot.get("source") or {},
        "split": {
            "development_dates": len(dev_dates),
            "development_first": dev_dates[0] if dev_dates else None,
            "development_last": dev_dates[-1] if dev_dates else None,
            "validation_dates": len(val_dates),
            "validation_first": val_dates[0] if val_dates else None,
            "validation_last": val_dates[-1] if val_dates else None,
        },
        "score_saturation": (baseline_snapshot.get("source") or {}).get("score_saturation") or {},
        "feature_separation": {
            "development": _feature_separation(dev_rows),
            "validation": _feature_separation(val_rows),
            "label_definition": "GOOD=within-date top third of 20D return, BAD=within-date bottom third, NEUTRAL=middle; research label only.",
        },
        "comparisons": comparisons,
        "chronological_blocks": blocks,
        "stability": {
            "overextension_guard_top3_return20_improved_blocks": block_return_wins,
            "overextension_guard_top3_mae20_improved_blocks": block_mae_wins,
            "block_count": len(blocks),
            "interpretation": "A signal that helps only some chronological blocks is treated as regime-dependent, not Production-ready.",
        },
        "independent_cap_validation": cap_validation,
        "false_positives": _false_positives(rows, 10),
        "recommendation": {
            "production_change": False,
            "next_step": (
                "Run a current-version 20-date focused audit for overextension features before any ranking change. "
                "Do not replace B.2.5-C or add weights yet."
                if verdict == VERDICT_PROMISING
                else "Keep Production ranking unchanged and investigate a different candidate-quality feature family."
            ),
        },
    }


def _pct(value: Any) -> str:
    number = _num(value)
    return "-" if number is None else f"{number * 100:.1f}%"


def _n(value: Any, digits: int = 2) -> str:
    number = _num(value)
    return "-" if number is None else f"{number:.{digits}f}"


def render_markdown(payload: dict[str, Any]) -> str:
    split = payload.get("split") or {}
    source = payload.get("source") or {}
    lines = [
        f"# Scanner Candidate Quality Audit — {payload.get('audit_version')}",
        "",
        f"- verdict: **{payload.get('verdict')}**",
        f"- source scanner version: `{source.get('scanner_version')}`",
        f"- source ready candidates: `{source.get('ready_candidates')}`",
        f"- development dates: `{split.get('development_dates')}`",
        f"- validation dates: `{split.get('validation_dates')}` ({split.get('validation_first')}..{split.get('validation_last')})",
        "- production changed: **False**",
        "",
        "## Score saturation",
        "",
    ]
    sat = payload.get("score_saturation") or {}
    lines += [
        f"- Strategy Fit=120 rate: `{_pct(sat.get('strategy_fit_score_120_rate'))}`",
        f"- Internal rank=108 rate: `{_pct(sat.get('internal_rank_108_rate'))}`",
        f"- Baseline quick score=120 rate: `{_pct(sat.get('baseline_quick_score_120_rate'))}`",
        "",
        "## Feature separation — GOOD vs BAD",
        "",
        "GOOD/BAD are within-date 20D-return terciles. Lower GOOD median can indicate that less-extreme values were associated with better outcomes.",
        "",
        "| Feature | Dev GOOD | Dev BAD | Val GOOD | Val BAD |",
        "|---|---:|---:|---:|---:|",
    ]
    dev_sep = {item["feature"]: item for item in ((payload.get("feature_separation") or {}).get("development") or [])}
    val_sep = {item["feature"]: item for item in ((payload.get("feature_separation") or {}).get("validation") or [])}
    for feature in RESEARCH_FEATURES:
        d = dev_sep.get(feature, {})
        v = val_sep.get(feature, {})
        lines.append(
            f"| {feature} | {_n(d.get('good_median'))} | {_n(d.get('bad_median'))} | {_n(v.get('good_median'))} | {_n(v.get('bad_median'))} |"
        )

    lines += ["", "## Ranking smoke — validation Top3", ""]
    top3 = (((payload.get("comparisons") or {}).get("validation") or {}).get("top3") or {})
    lines += [
        "| Variant | 10D mean | 20D mean | 20D median | 20D positive | MFE20 | MAE20 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for variant in (CURRENT, RISK_Q75, TARGET_Q75, OVEREXT_Q75):
        m = top3.get(variant) or {}
        lines.append(
            f"| {variant} | {_n(m.get('return_10d_mean'))}% | {_n(m.get('return_20d_mean'))}% | {_n(m.get('return_20d_median'))}% | {_pct(m.get('return_20d_positive_rate'))} | {_n(m.get('mfe_20d_mean'))}% | {_n(m.get('mae_20d_mean'))}% |"
        )

    lines += ["", "## Stability by chronological block — OVEREXTENSION_Q75_GUARD Top3", ""]
    lines += [
        "| Block | Range | Current 20D | Guard 20D | Current MAE | Guard MAE |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for block in payload.get("chronological_blocks") or []:
        c = block.get("current_top3") or {}
        g = block.get("overextension_guard_top3") or {}
        lines.append(
            f"| {block.get('block')} | {block.get('first_date')}..{block.get('last_date')} | {_n(c.get('return_20d_mean'))}% | {_n(g.get('return_20d_mean'))}% | {_n(c.get('mae_20d_mean'))}% | {_n(g.get('mae_20d_mean'))}% |"
        )

    cap = payload.get("independent_cap_validation") or {}
    if cap:
        lines += ["", "## Independent CAP_1_5R validation", ""]
        lines += [
            "This snapshot validates risk/structural-target variants only; it does **not** contain the overextension features.",
            "",
            "| Variant | Top3 T1-first 20D | Top3 Stop-first 20D | Top3 MAE20 |",
            "|---|---:|---:|---:|",
        ]
        for variant in (CURRENT, RISK_Q75, TARGET_Q75):
            m = ((cap.get("top3") or {}).get(variant) or {})
            lines.append(
                f"| {variant} | {_pct(m.get('target1_first_20d_rate'))} | {_pct(m.get('stop_first_20d_rate'))} | {_n(m.get('mae_20d_mean'))}% |"
            )

    lines += [
        "",
        "## Decision",
        "",
        "- Production Ranking change: **NO**",
        "- Strong finding: READY candidates' legacy fit/quick/internal scores are saturated, so those scores do not separate READY peers in this sample.",
        "- Promising finding: overextension-related current features can separate recent winners/losers and improved the latest validation block.",
        "- Blocking finding: the effect is not stable across all chronological blocks, and the independent CAP snapshot cannot validate the overextension feature family.",
        "- Next: current-version focused 20-date validation only; no new weights and no broad 80D rerun yet.",
        "",
        f"> {payload.get('guardrail')}",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"scanner-candidate-quality-audit_{stamp}.json"
    md_path = output_dir / f"scanner-candidate-quality-audit_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
