from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

AUDIT_VERSION = "v0.21.4-B.2.6-D"
EXPECTED_CURRENT_AUDIT_VERSION = "v0.21.4-B.2.6-C"
EXPECTED_SCANNER_VERSION = "0.21.3.7"

CURRENT = "CURRENT"
ORIGINAL_GUARD = "OVEREXTENSION_Q75_GUARD"
TRIPLE_ONLY = "TRIPLE_ONLY_GUARD"
REFINED_GUARD = "TREND_RECOVERY_2OF3_EXEMPT"

VERDICT_READY = "REFINED_GUARD_READY_FOR_CONFIRMATION"
VERDICT_INSUFFICIENT = "INSUFFICIENT_SEPARATION"
VERDICT_REJECT = "REJECT_OVEREXTENSION_FAMILY"

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
    return sum(nums) / len(nums) if nums else None


def _median(values: Iterable[Any]) -> float | None:
    nums = [n for value in values if (n := _num(value)) is not None]
    return statistics.median(nums) if nums else None


def _rate(items: Iterable[bool]) -> float | None:
    values = list(items)
    return sum(1 for item in values if item) / len(values) if values else None


def _trimmed_mean(values: Iterable[Any], proportion: float = 0.10) -> float | None:
    nums = sorted(n for value in values if (n := _num(value)) is not None)
    if not nums:
        return None
    trim = int(len(nums) * proportion)
    if trim <= 0 or len(nums) - trim * 2 <= 0:
        return _mean(nums)
    return _mean(nums[trim:-trim])


def _mean_without_best(values: Iterable[Any]) -> float | None:
    nums = sorted(n for value in values if (n := _num(value)) is not None)
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    return _mean(nums[:-1])


def _q75(values: Iterable[Any]) -> float | None:
    nums = sorted(n for value in values if (n := _num(value)) is not None)
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    position = (len(nums) - 1) * 0.75
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return nums[lo]
    weight = position - lo
    return nums[lo] * (1.0 - weight) + nums[hi] * weight


def _code(row: dict[str, Any]) -> str:
    return str(row.get("code") or "")


def _rank(row: dict[str, Any]) -> int:
    for key in ("current_rank", "rank"):
        try:
            value = int(row.get(key))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return 999999


def _is_ready(row: dict[str, Any]) -> bool:
    state = row.get("candidate_state")
    if state is None:
        # B.2.6-A/B compact baseline contains READY rows only.
        return True
    return str(state) == "READY"


def _group_by_date(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("analysis_date") or "")].append(row)
    return dict(grouped)


def _tercile_labels(rows: list[dict[str, Any]]) -> dict[str, str]:
    ordered = [row for row in rows if _num(row.get("return_20d")) is not None]
    ordered.sort(key=lambda row: (_num(row.get("return_20d")) or 0.0, _code(row)))
    if not ordered:
        return {}
    size = max(1, math.ceil(len(ordered) / 3.0))
    bad = {_code(row) for row in ordered[:size]}
    good = {_code(row) for row in ordered[-size:]}
    labels: dict[str, str] = {}
    for row in ordered:
        code = _code(row)
        if code in good:
            labels[code] = "MOMENTUM_CONTINUATION"
        elif code in bad:
            labels[code] = "RISKY_OVEREXTENSION"
        else:
            labels[code] = "NEUTRAL"
    return labels


def annotate_overextension(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate same-date Q75 overextension and research-only outcome labels.

    Future outcome fields are used only after the overextension annotation is fixed.
    They never participate in the demotion rule itself.
    """
    output: list[dict[str, Any]] = []
    for analysis_date, group in sorted(_group_by_date(rows).items()):
        ready = [row for row in group if _is_ready(row)]
        thresholds = {feature: _q75(row.get(feature) for row in ready) for feature in OVEREXTENSION_FEATURES}
        annotations: list[dict[str, Any]] = []
        for row in group:
            copy = dict(row)
            extreme: list[str] = []
            available = 0
            if _is_ready(copy):
                for feature in OVEREXTENSION_FEATURES:
                    value = _num(copy.get(feature))
                    threshold = thresholds.get(feature)
                    if value is None or threshold is None:
                        continue
                    available += 1
                    if value > threshold:
                        extreme.append(feature)
            copy["available_feature_count"] = available
            copy["extreme_feature_count"] = len(extreme)
            copy["extreme_features"] = extreme
            copy["overextended"] = bool(_is_ready(copy) and available >= 2 and len(extreme) >= 2)
            annotations.append(copy)

        labels = _tercile_labels([row for row in annotations if _is_ready(row)])
        for copy in annotations:
            copy["outcome_label"] = labels.get(_code(copy), "NEUTRAL")
            copy["analysis_date"] = analysis_date
            output.append(copy)
    return output


def should_demote(row: dict[str, Any], variant: str) -> bool:
    """Current-time-only demotion rule. No outcome field is consumed."""
    if not _is_ready(row):
        return False
    overextended = bool(row.get("overextended"))
    count = int(row.get("extreme_feature_count") or 0)
    strategy = str(row.get("strategy") or "")

    if variant == ORIGINAL_GUARD:
        return overextended
    if variant == TRIPLE_ONLY:
        return count >= 3
    if variant == REFINED_GUARD:
        # Development-only finding: trend_recovery with exactly 2-of-3 extreme
        # features showed continuation characteristics, while 3-of-3 remained risky.
        return overextended and not (strategy == "trend_recovery" and count == 2)
    if variant == CURRENT:
        return False
    raise ValueError(f"Unknown B.2.6-D variant: {variant}")


def rank_variant(rows: list[dict[str, Any]], variant: str) -> list[dict[str, Any]]:
    current = sorted((dict(row) for row in rows), key=lambda row: (_rank(row), _code(row)))
    if variant == CURRENT:
        output = current
    else:
        ready = [row for row in current if _is_ready(row)]
        ranked_ready = sorted(
            ready,
            key=lambda row: (int(should_demote(row, variant)), _rank(row), _code(row)),
        )
        output = list(current)
        ready_positions = [index for index, row in enumerate(current) if _is_ready(row)]
        for index, replacement in zip(ready_positions, ranked_ready):
            output[index] = replacement

    for new_rank, row in enumerate(output, start=1):
        row["variant_rank"] = new_rank
        row["variant_demoted"] = bool(should_demote(row, variant)) if variant != CURRENT else False
    return output


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [n for row in rows if (n := _num(row.get("return_20d"))) is not None]
    events = [str(row.get("event_20d") or "") for row in rows if row.get("event_20d") is not None]
    return {
        "count": len(rows),
        "return_20d_mean": _mean(returns),
        "return_20d_median": _median(returns),
        "return_20d_trimmed_mean": _trimmed_mean(returns),
        "return_20d_mean_without_best": _mean_without_best(returns),
        "return_20d_positive_rate": _rate(value > 0 for value in returns),
        "mfe_20d_mean": _mean(row.get("mfe_20d") for row in rows),
        "mae_20d_mean": _mean(row.get("mae_20d") for row in rows),
        "target1_first_20d_rate": _rate(event == "TARGET1_FIRST" for event in events),
        "stop_first_20d_rate": _rate(event == "STOP_FIRST" for event in events),
    }


def _select_top(grouped: dict[str, list[dict[str, Any]]], variant: str, top_n: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for _date, rows in sorted(grouped.items()):
        selected.extend(rank_variant(rows, variant)[:top_n])
    return selected


def _subset_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        **_metrics(rows),
        "risky_count": sum(1 for row in rows if row.get("outcome_label") == "RISKY_OVEREXTENSION"),
        "continuation_count": sum(1 for row in rows if row.get("outcome_label") == "MOMENTUM_CONTINUATION"),
        "neutral_count": sum(1 for row in rows if row.get("outcome_label") == "NEUTRAL"),
    }


def _development_evidence(annotated: list[dict[str, Any]]) -> dict[str, Any]:
    overextended = [row for row in annotated if bool(row.get("overextended"))]
    labels = Counter(str(row.get("outcome_label") or "NEUTRAL") for row in overextended)

    by_extreme_count: dict[str, Any] = {}
    for count in (2, 3):
        subset = [row for row in overextended if int(row.get("extreme_feature_count") or 0) == count]
        by_extreme_count[str(count)] = _subset_metrics(subset)

    by_strategy: dict[str, Any] = {}
    for strategy in sorted({str(row.get("strategy") or "") for row in overextended}):
        subset = [row for row in overextended if str(row.get("strategy") or "") == strategy]
        if subset:
            by_strategy[strategy] = _subset_metrics(subset)

    trend_recovery_2of3 = [
        row for row in overextended
        if str(row.get("strategy") or "") == "trend_recovery"
        and int(row.get("extreme_feature_count") or 0) == 2
    ]
    trend_recovery_3of3 = [
        row for row in overextended
        if str(row.get("strategy") or "") == "trend_recovery"
        and int(row.get("extreme_feature_count") or 0) == 3
    ]

    return {
        "overextended_count": len(overextended),
        "risky_count": int(labels.get("RISKY_OVEREXTENSION", 0)),
        "continuation_count": int(labels.get("MOMENTUM_CONTINUATION", 0)),
        "neutral_count": int(labels.get("NEUTRAL", 0)),
        "by_extreme_count": by_extreme_count,
        "by_strategy": by_strategy,
        "key_split": {
            "trend_recovery_2of3": _subset_metrics(trend_recovery_2of3),
            "trend_recovery_3of3": _subset_metrics(trend_recovery_3of3),
        },
        "label_definition": (
            "Research-only: within-date READY 20D return top tercile = MOMENTUM_CONTINUATION, "
            "bottom tercile = RISKY_OVEREXTENSION, middle = NEUTRAL."
        ),
    }


def _validate_current_payload(payload: dict[str, Any]) -> None:
    if str(payload.get("audit_version") or "") != EXPECTED_CURRENT_AUDIT_VERSION:
        raise ValueError(
            f"Expected current validation {EXPECTED_CURRENT_AUDIT_VERSION}, "
            f"got {payload.get('audit_version')!r}"
        )
    if str(payload.get("scanner_version") or "") != EXPECTED_SCANNER_VERSION:
        raise ValueError(
            f"Expected Scanner {EXPECTED_SCANNER_VERSION}, got {payload.get('scanner_version')!r}"
        )
    if int(payload.get("valid_date_count") or 0) < 20:
        raise ValueError(f"Expected at least 20 current-version validation dates, got {payload.get('valid_date_count')}")
    if bool(payload.get("production_changed")):
        raise ValueError("Current validation payload unexpectedly reports Production changed=True")


def _current_grouped(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in payload.get("dates") or []:
        if item.get("status") != "OK":
            continue
        rows = [dict(row) for row in (item.get("current_candidates") or [])]
        # C already contains frozen same-date Q75 annotations. Reuse them exactly.
        grouped[str(item.get("analysis_date") or "")] = rows
    return grouped


def _comparison(grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    variants = (CURRENT, ORIGINAL_GUARD, TRIPLE_ONLY, REFINED_GUARD)
    result: dict[str, Any] = {}
    for top_n in (1, 3, 5):
        result[f"top{top_n}"] = {
            variant: _metrics(_select_top(grouped, variant, top_n))
            for variant in variants
        }
    return result


def _rank_impact(grouped: dict[str, list[dict[str, Any]]], variant: str) -> dict[str, Any]:
    top1_changed = 0
    top3_membership_changed = 0
    top3_order_changed = 0
    moves: list[int] = []
    for _date, rows in sorted(grouped.items()):
        current = rank_variant(rows, CURRENT)
        other = rank_variant(rows, variant)
        c1 = [_code(row) for row in current[:1]]
        o1 = [_code(row) for row in other[:1]]
        c3 = [_code(row) for row in current[:3]]
        o3 = [_code(row) for row in other[:3]]
        top1_changed += int(c1 != o1)
        top3_membership_changed += int(set(c3) != set(o3))
        top3_order_changed += int(c3 != o3)
        current_pos = {_code(row): index + 1 for index, row in enumerate(current)}
        other_pos = {_code(row): index + 1 for index, row in enumerate(other)}
        moves.extend(abs(other_pos[code] - rank) for code, rank in current_pos.items() if code in other_pos)
    return {
        "checked_dates": len(grouped),
        "top1_changed_dates": top1_changed,
        "top3_membership_changed_dates": top3_membership_changed,
        "top3_order_changed_dates": top3_order_changed,
        "mean_absolute_rank_move": _mean(moves),
    }


def _verdict(comparisons: dict[str, Any]) -> tuple[str, list[str]]:
    top3 = comparisons.get("top3") or {}
    cur = top3.get(CURRENT) or {}
    refined = top3.get(REFINED_GUARD) or {}
    reasons: list[str] = []

    def gt(key: str) -> bool:
        a, b = _num(refined.get(key)), _num(cur.get(key))
        return a is not None and b is not None and a > b

    def ge(key: str) -> bool:
        a, b = _num(refined.get(key)), _num(cur.get(key))
        return a is not None and b is not None and a >= b

    def le(key: str) -> bool:
        a, b = _num(refined.get(key)), _num(cur.get(key))
        return a is not None and b is not None and a <= b

    checks = {
        "20D mean improved": gt("return_20d_mean"),
        "20D trimmed mean improved": gt("return_20d_trimmed_mean"),
        "20D mean without best did not worsen": ge("return_20d_mean_without_best"),
        "MAE20 did not worsen": ge("mae_20d_mean"),
        "Target1-first 20D restored/nonworse": ge("target1_first_20d_rate"),
        "Stop-first 20D restored/nonworse": le("stop_first_20d_rate"),
    }
    reasons.extend(label for label, passed in checks.items() if passed)

    if all(checks.values()):
        return VERDICT_READY, reasons

    clearly_worse = (
        not ge("return_20d_mean")
        and not ge("return_20d_trimmed_mean")
        and not ge("mae_20d_mean")
    )
    if clearly_worse:
        return VERDICT_REJECT, ["Refined guard underperformed CURRENT on return and MAE checks"]
    return VERDICT_INSUFFICIENT, reasons or ["Current-version split is not strong enough for confirmation"]


def run_context_audit(
    development_payload: dict[str, Any],
    current_validation_payload: dict[str, Any],
) -> dict[str, Any]:
    _validate_current_payload(current_validation_payload)
    source_rows = [dict(row) for row in (development_payload.get("candidates") or [])]
    dates = sorted(_group_by_date(source_rows))
    if len(dates) < 21:
        raise ValueError("Development baseline does not contain enough dates for held-out split")

    # Freeze development to the same first 53 dates used in B.2.6-A/B.
    development_dates = dates[:-20]
    development_rows = [row for row in source_rows if str(row.get("analysis_date") or "") in set(development_dates)]
    annotated_development = annotate_overextension(development_rows)
    development_grouped = _group_by_date(annotated_development)
    current_grouped = _current_grouped(current_validation_payload)

    development_comparisons = {
        variant: _metrics(_select_top(development_grouped, variant, 3))
        for variant in (CURRENT, ORIGINAL_GUARD, TRIPLE_ONLY, REFINED_GUARD)
    }
    validation_comparisons = _comparison(current_grouped)
    verdict, reasons = _verdict(validation_comparisons)

    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "production_changed": False,
        "guardrail": (
            "Research-only. Variant rules consume only same-date current features/strategy. "
            "Future outcomes are used only for research labels and evaluation."
        ),
        "development_source": {
            **(development_payload.get("source") or {}),
            "development_dates": len(development_dates),
            "development_first": development_dates[0],
            "development_last": development_dates[-1],
        },
        "current_validation_source": {
            "audit_version": current_validation_payload.get("audit_version"),
            "scanner_version": current_validation_payload.get("scanner_version"),
            "generated_at": current_validation_payload.get("generated_at"),
            "valid_date_count": current_validation_payload.get("valid_date_count"),
            "evaluation_first": (current_validation_payload.get("evaluation_dates") or [None])[0],
            "evaluation_last": (current_validation_payload.get("evaluation_dates") or [None])[-1],
        },
        "development_evidence": _development_evidence(annotated_development),
        "rule_candidates": {
            ORIGINAL_GUARD: "Demote every READY candidate with >=2 of 3 same-date Q75 overextension signals.",
            TRIPLE_ONLY: "Demote only READY candidates with all 3 overextension signals above same-date Q75.",
            REFINED_GUARD: (
                "Demote >=2-of-3 overextended READY candidates, except trend_recovery with exactly 2-of-3; "
                "3-of-3 trend_recovery remains demoted."
            ),
        },
        "development_top3": development_comparisons,
        "current_validation": validation_comparisons,
        "ranking_impact": {
            ORIGINAL_GUARD: _rank_impact(current_grouped, ORIGINAL_GUARD),
            TRIPLE_ONLY: _rank_impact(current_grouped, TRIPLE_ONLY),
            REFINED_GUARD: _rank_impact(current_grouped, REFINED_GUARD),
        },
        "verdict": verdict,
        "verdict_reasons": reasons,
    }


def _fmt_pct(value: Any) -> str:
    number = _num(value)
    return "-" if number is None else f"{number:.2f}%"


def _fmt_rate(value: Any) -> str:
    number = _num(value)
    return "-" if number is None else f"{number * 100:.1f}%"


def _markdown(payload: dict[str, Any]) -> str:
    evidence = payload.get("development_evidence") or {}
    key = evidence.get("key_split") or {}
    tr2 = key.get("trend_recovery_2of3") or {}
    tr3 = key.get("trend_recovery_3of3") or {}
    top3 = (payload.get("current_validation") or {}).get("top3") or {}
    cur = top3.get(CURRENT) or {}
    orig = top3.get(ORIGINAL_GUARD) or {}
    triple = top3.get(TRIPLE_ONLY) or {}
    refined = top3.get(REFINED_GUARD) or {}

    lines = [
        f"# Scanner Overextension Context Audit — {AUDIT_VERSION}",
        "",
        f"- verdict: **{payload.get('verdict')}**",
        f"- current scanner: `{(payload.get('current_validation_source') or {}).get('scanner_version')}`",
        f"- development dates: `{(payload.get('development_source') or {}).get('development_dates')}`",
        f"- current validation dates: `{(payload.get('current_validation_source') or {}).get('valid_date_count')}`",
        f"- Production changed: **{payload.get('production_changed')}**",
        "",
        "## Development overextension split",
        "",
        f"- Overextended candidates: `{evidence.get('overextended_count')}`",
        f"- Risky: `{evidence.get('risky_count')}`",
        f"- Momentum continuation: `{evidence.get('continuation_count')}`",
        f"- Neutral: `{evidence.get('neutral_count')}`",
        "",
        "| Development subgroup | N | 20D mean | T1-first | Stop-first | MAE20 |",
        "|---|---:|---:|---:|---:|---:|",
        f"| trend_recovery 2-of-3 | {tr2.get('count')} | {_fmt_pct(tr2.get('return_20d_mean'))} | {_fmt_rate(tr2.get('target1_first_20d_rate'))} | {_fmt_rate(tr2.get('stop_first_20d_rate'))} | {_fmt_pct(tr2.get('mae_20d_mean'))} |",
        f"| trend_recovery 3-of-3 | {tr3.get('count')} | {_fmt_pct(tr3.get('return_20d_mean'))} | {_fmt_rate(tr3.get('target1_first_20d_rate'))} | {_fmt_rate(tr3.get('stop_first_20d_rate'))} | {_fmt_pct(tr3.get('mae_20d_mean'))} |",
        "",
        "## Current-version Top3 validation",
        "",
        "| Metric | CURRENT | Original guard | Triple-only | Refined guard |",
        "|---|---:|---:|---:|---:|",
        f"| 20D mean | {_fmt_pct(cur.get('return_20d_mean'))} | {_fmt_pct(orig.get('return_20d_mean'))} | {_fmt_pct(triple.get('return_20d_mean'))} | {_fmt_pct(refined.get('return_20d_mean'))} |",
        f"| 20D median | {_fmt_pct(cur.get('return_20d_median'))} | {_fmt_pct(orig.get('return_20d_median'))} | {_fmt_pct(triple.get('return_20d_median'))} | {_fmt_pct(refined.get('return_20d_median'))} |",
        f"| 20D trimmed mean | {_fmt_pct(cur.get('return_20d_trimmed_mean'))} | {_fmt_pct(orig.get('return_20d_trimmed_mean'))} | {_fmt_pct(triple.get('return_20d_trimmed_mean'))} | {_fmt_pct(refined.get('return_20d_trimmed_mean'))} |",
        f"| 20D mean w/o best | {_fmt_pct(cur.get('return_20d_mean_without_best'))} | {_fmt_pct(orig.get('return_20d_mean_without_best'))} | {_fmt_pct(triple.get('return_20d_mean_without_best'))} | {_fmt_pct(refined.get('return_20d_mean_without_best'))} |",
        f"| T1-first 20D | {_fmt_rate(cur.get('target1_first_20d_rate'))} | {_fmt_rate(orig.get('target1_first_20d_rate'))} | {_fmt_rate(triple.get('target1_first_20d_rate'))} | {_fmt_rate(refined.get('target1_first_20d_rate'))} |",
        f"| Stop-first 20D | {_fmt_rate(cur.get('stop_first_20d_rate'))} | {_fmt_rate(orig.get('stop_first_20d_rate'))} | {_fmt_rate(triple.get('stop_first_20d_rate'))} | {_fmt_rate(refined.get('stop_first_20d_rate'))} |",
        f"| MAE20 | {_fmt_pct(cur.get('mae_20d_mean'))} | {_fmt_pct(orig.get('mae_20d_mean'))} | {_fmt_pct(triple.get('mae_20d_mean'))} | {_fmt_pct(refined.get('mae_20d_mean'))} |",
        "",
        "## Decision reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in (payload.get("verdict_reasons") or []))
    lines += [
        "",
        "> B.2.6-D does not tune Q75 or add weights. The refined exception was selected from the held-out development block and then applied unchanged to the current 0.21.3.7 validation payload.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_dir / f"scanner-overextension-context_{stamp}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    csv_path = base.with_suffix(".csv")

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")

    fields = [
        "variant", "top_n", "count", "return_20d_mean", "return_20d_median",
        "return_20d_trimmed_mean", "return_20d_mean_without_best", "return_20d_positive_rate",
        "mfe_20d_mean", "mae_20d_mean", "target1_first_20d_rate", "stop_first_20d_rate",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for top_key, variants in (payload.get("current_validation") or {}).items():
            top_n = int(str(top_key).replace("top", ""))
            for variant, metrics in variants.items():
                writer.writerow({"variant": variant, "top_n": top_n, **metrics})

    return {"json": str(json_path), "markdown": str(md_path), "csv": str(csv_path)}
