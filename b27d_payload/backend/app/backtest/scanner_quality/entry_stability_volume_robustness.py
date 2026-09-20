from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

AUDIT_VERSION = "v0.21.4-B.2.7-D"
EXPECTED_DEVELOPMENT_VERSION = "v0.21.4-B.2.7-A.B"
EXPECTED_VALIDATION_VERSION = "v0.21.4-B.2.7-C"
EXPECTED_SCANNER_VERSION = "0.21.3.7"
RULE_ID = "VOLUME_LOW_GUARD"
VERDICT_FREEZE = "FREEZE_VOLUME_LOW_GUARD"
VERDICT_AGGRESSIVE = "VOLUME_SIGNAL_TOO_AGGRESSIVE"
VERDICT_NOT_ROBUST = "VOLUME_SIGNAL_NOT_ROBUST"
VERDICT_INSUFFICIENT = "INSUFFICIENT_ROBUSTNESS_EVIDENCE"


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _mean(values: Iterable[Any]) -> float | None:
    nums = [x for value in values if (x := _num(value)) is not None]
    return sum(nums) / len(nums) if nums else None


def _median(values: Iterable[Any]) -> float | None:
    nums = [x for value in values if (x := _num(value)) is not None]
    return statistics.median(nums) if nums else None


def _trimmed_mean(values: Iterable[Any], proportion: float = 0.10) -> float | None:
    nums = sorted(x for value in values if (x := _num(value)) is not None)
    if not nums:
        return None
    trim = int(len(nums) * max(0.0, min(float(proportion), 0.45)))
    if trim and len(nums) > trim * 2:
        nums = nums[trim:-trim]
    return sum(nums) / len(nums)


def _mean_without_best(values: Iterable[Any]) -> float | None:
    nums = sorted((x for value in values if (x := _num(value)) is not None), reverse=True)
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    return sum(nums[1:]) / (len(nums) - 1)


def _rate(flags: Iterable[bool]) -> float | None:
    values = list(flags)
    return sum(bool(x) for x in values) / len(values) if values else None


def _code(row: dict[str, Any]) -> str:
    return str(row.get("code") or "")


def _rank(row: dict[str, Any]) -> int:
    for key in ("current_rank", "rank", "guard_rank"):
        try:
            if row.get(key) is not None:
                return int(row[key])
        except (TypeError, ValueError):
            pass
    return 999999


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    events = [str(row.get("event_20d") or "") for row in rows if row.get("event_20d") is not None]
    returns = [x for row in rows if (x := _num(row.get("return_20d"))) is not None]
    maes = [x for row in rows if (x := _num(row.get("mae_20d"))) is not None]
    event_r = [x for row in rows if (x := _num(row.get("event_r_20d"))) is not None]
    return {
        "count": len(rows),
        "target1_first_20d_rate": _rate(event == "TARGET1_FIRST" for event in events),
        "stop_first_20d_rate": _rate(event == "STOP_FIRST" for event in events),
        "no_event_20d_rate": _rate(event not in {"TARGET1_FIRST", "STOP_FIRST"} for event in events),
        "return_20d_mean": _mean(returns),
        "return_20d_median": _median(returns),
        "return_20d_trimmed_mean": _trimmed_mean(returns),
        "return_20d_mean_without_best": _mean_without_best(returns),
        "mae_20d_mean": _mean(maes),
        "event_r_20d_mean": _mean(event_r),
        "event_r_20d_median": _median(event_r),
        "event_r_20d_trimmed_mean": _trimmed_mean(event_r),
        "event_r_20d_positive_rate": _rate(x > 0 for x in event_r),
    }


def _apply_development_volume_guard(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted((dict(row) for row in rows), key=lambda row: (_rank(row), _code(row)))
    ready = [row for row in ordered if str(row.get("candidate_state") or "") == "READY"]
    stable = [row for row in ready if str(row.get("volume_ratio_prev20_band") or "") != "LOW"]
    low = [row for row in ready if str(row.get("volume_ratio_prev20_band") or "") == "LOW"]
    reordered = stable + low
    output = list(ordered)
    ready_positions = [i for i, row in enumerate(ordered) if str(row.get("candidate_state") or "") == "READY"]
    for pos, replacement in zip(ready_positions, reordered):
        output[pos] = replacement
    for index, row in enumerate(output, start=1):
        row["guard_rank"] = index
    return output


def _split_blocks(dates: list[str], block_count: int = 4) -> list[list[str]]:
    if not dates:
        return []
    return [dates[round(i * len(dates) / block_count): round((i + 1) * len(dates) / block_count)] for i in range(block_count)]


def _block_status(current: dict[str, Any], guard: dict[str, Any]) -> str:
    ct, gt = current.get("target1_first_20d_rate"), guard.get("target1_first_20d_rate")
    cs, gs = current.get("stop_first_20d_rate"), guard.get("stop_first_20d_rate")
    if None in {ct, gt, cs, gs}:
        return "INSUFFICIENT"
    if gt > ct and gs < cs:
        return "POSITIVE"
    if gt >= ct and gs <= cs:
        return "NEUTRAL"
    return "NEGATIVE"


def _date_event_r(rows: list[dict[str, Any]]) -> float | None:
    return _mean(row.get("event_r_20d") for row in rows[:3])


def _date_outcome(current: list[dict[str, Any]], guard: list[dict[str, Any]]) -> dict[str, Any]:
    cur = _date_event_r(current)
    new = _date_event_r(guard)
    if cur is None or new is None:
        status = "INSUFFICIENT"
    elif new > cur + 1e-12:
        status = "WIN"
    elif new < cur - 1e-12:
        status = "LOSS"
    else:
        status = "TIE"
    return {"status": status, "current_event_r": cur, "guard_event_r": new, "delta_event_r": None if cur is None or new is None else new - cur}


def _swap_category(removed: dict[str, Any], added: dict[str, Any]) -> str:
    rem = str(removed.get("event_20d") or "NO_EVENT")
    add = str(added.get("event_20d") or "NO_EVENT")
    if rem == "STOP_FIRST" and add != "STOP_FIRST":
        return "GOOD_SWAP"
    if rem != "STOP_FIRST" and add == "STOP_FIRST":
        return "BAD_SWAP"
    if rem != "TARGET1_FIRST" and add == "TARGET1_FIRST":
        return "GOOD_SWAP"
    if rem == "TARGET1_FIRST" and add != "TARGET1_FIRST":
        return "BAD_SWAP"
    if rem == add:
        return "NEUTRAL_SWAP"
    return "MIXED_SWAP"


def _swaps(current: list[dict[str, Any]], guard: list[dict[str, Any]], analysis_date: str) -> list[dict[str, Any]]:
    current_top = current[:3]
    guard_top = guard[:3]
    current_codes = {_code(row) for row in current_top}
    guard_codes = {_code(row) for row in guard_top}
    removed = [row for row in current_top if _code(row) not in guard_codes]
    added = [row for row in guard_top if _code(row) not in current_codes]
    out: list[dict[str, Any]] = []
    for rem, add in zip(removed, added):
        out.append({
            "analysis_date": analysis_date,
            "category": _swap_category(rem, add),
            "removed": {
                "code": _code(rem), "name": rem.get("name"), "rank": _rank(rem),
                "event_20d": rem.get("event_20d"), "event_r_20d": rem.get("event_r_20d"),
                "return_20d": rem.get("return_20d"), "mae_20d": rem.get("mae_20d"),
            },
            "added": {
                "code": _code(add), "name": add.get("name"), "rank": _rank(add),
                "event_20d": add.get("event_20d"), "event_r_20d": add.get("event_r_20d"),
                "return_20d": add.get("return_20d"), "mae_20d": add.get("mae_20d"),
            },
        })
    return out


def _aggressiveness(current_by_date: dict[str, list[dict[str, Any]]], guard_by_date: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    demotions: list[dict[str, Any]] = []
    top1_changed = 0
    top3_changed = 0
    for day in sorted(current_by_date):
        current = current_by_date[day]
        guard = guard_by_date[day]
        if [_code(x) for x in current[:1]] != [_code(x) for x in guard[:1]]:
            top1_changed += 1
        if {_code(x) for x in current[:3]} != {_code(x) for x in guard[:3]}:
            top3_changed += 1
        guard_pos = {_code(row): i + 1 for i, row in enumerate(guard)}
        for rank, row in enumerate(current[:3], start=1):
            new_rank = guard_pos.get(_code(row))
            if new_rank is not None and new_rank > rank:
                demotions.append({"analysis_date": day, "code": _code(row), "name": row.get("name"), "from_rank": rank, "to_rank": new_rank, "distance": new_rank-rank})
    distances = [int(item["distance"]) for item in demotions]
    destination = Counter("4-5" if item["to_rank"] <= 5 else "6-10" if item["to_rank"] <= 10 else "11+" for item in demotions)
    origins = Counter(int(item["from_rank"]) for item in demotions)
    return {
        "checked_dates": len(current_by_date),
        "top1_changed_dates": top1_changed,
        "top3_membership_changed_dates": top3_changed,
        "top3_change_rate": top3_changed / len(current_by_date) if current_by_date else None,
        "demoted_top3_candidates": len(demotions),
        "median_demotion_distance": _median(distances),
        "max_demotion_distance": max(distances) if distances else 0,
        "demoted_from_rank_1": origins.get(1, 0),
        "demoted_from_rank_2": origins.get(2, 0),
        "demoted_from_rank_3": origins.get(3, 0),
        "destination_4_5": destination.get("4-5", 0),
        "destination_6_10": destination.get("6-10", 0),
        "destination_11_plus": destination.get("11+", 0),
        "examples": demotions[:20],
    }


def _strategy_low_volume(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row.get("volume_ratio_prev20_band") or "") == "LOW":
            groups[str(row.get("strategy") or "UNKNOWN")].append(row)
    result: dict[str, Any] = {}
    for strategy, items in sorted(groups.items()):
        summary = _metrics(items)
        summary["evidence"] = "SUFFICIENT" if len(items) >= 10 else "INSUFFICIENT_SUBGROUP_SAMPLE"
        result[strategy] = summary
    return result


def _build_development(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[str(row.get("analysis_date") or "")].append(dict(row))
    current_by: dict[str, list[dict[str, Any]]] = {}
    guard_by: dict[str, list[dict[str, Any]]] = {}
    for day, items in by_date.items():
        ordered = sorted(items, key=lambda row: (_rank(row), _code(row)))
        current_by[day] = ordered
        guard_by[day] = _apply_development_volume_guard(ordered)
    dates = sorted(current_by)
    blocks = []
    for index, block_dates in enumerate(_split_blocks(dates), start=1):
        cur = [row for day in block_dates for row in current_by[day][:3]]
        grd = [row for day in block_dates for row in guard_by[day][:3]]
        cm, gm = _metrics(cur), _metrics(grd)
        blocks.append({"block": index, "first_date": block_dates[0], "last_date": block_dates[-1], "date_count": len(block_dates), "current": cm, "guard": gm, "status": _block_status(cm, gm)})
    date_outcomes = [{"analysis_date": day, **_date_outcome(current_by[day], guard_by[day])} for day in dates]
    swaps = [swap for day in dates for swap in _swaps(current_by[day], guard_by[day], day)]
    return {
        "date_count": len(dates),
        "candidate_count": len(rows),
        "current_top3": _metrics([row for day in dates for row in current_by[day][:3]]),
        "guard_top3": _metrics([row for day in dates for row in guard_by[day][:3]]),
        "blocks": blocks,
        "date_outcomes": {**Counter(item["status"] for item in date_outcomes), "details": date_outcomes},
        "swaps": {**Counter(item["category"] for item in swaps), "count": len(swaps), "details": swaps[:30]},
        "aggressiveness": _aggressiveness(current_by, guard_by),
        "low_volume_strategy": _strategy_low_volume(rows),
    }


def _build_validation(payload: dict[str, Any]) -> dict[str, Any]:
    valid = [item for item in payload.get("dates") or [] if item.get("status") == "OK"]
    current_by: dict[str, list[dict[str, Any]]] = {}
    guard_by: dict[str, list[dict[str, Any]]] = {}
    all_current: list[dict[str, Any]] = []
    for item in valid:
        day = str(item.get("analysis_date") or "")
        current = [dict(row) for row in item.get("current_candidates") or []]
        guard = [dict(row) for row in ((item.get("variant_candidates") or {}).get(RULE_ID) or [])]
        current_by[day] = current
        guard_by[day] = guard
        all_current.extend(current)
    dates = sorted(current_by)
    blocks = []
    for index, block_dates in enumerate(_split_blocks(dates), start=1):
        cur = [row for day in block_dates for row in current_by[day][:3]]
        grd = [row for day in block_dates for row in guard_by[day][:3]]
        cm, gm = _metrics(cur), _metrics(grd)
        blocks.append({"block": index, "first_date": block_dates[0], "last_date": block_dates[-1], "date_count": len(block_dates), "current": cm, "guard": gm, "status": _block_status(cm, gm)})
    date_outcomes = [{"analysis_date": day, **_date_outcome(current_by[day], guard_by[day])} for day in dates]
    swaps = [swap for day in dates for swap in _swaps(current_by[day], guard_by[day], day)]
    return {
        "date_count": len(dates),
        "current_top3": _metrics([row for day in dates for row in current_by[day][:3]]),
        "guard_top3": _metrics([row for day in dates for row in guard_by[day][:3]]),
        "blocks": blocks,
        "date_outcomes": {**Counter(item["status"] for item in date_outcomes), "details": date_outcomes},
        "swaps": {**Counter(item["category"] for item in swaps), "count": len(swaps), "details": swaps[:30]},
        "aggressiveness": _aggressiveness(current_by, guard_by),
        "low_volume_strategy": _strategy_low_volume(all_current),
    }


def _validate_inputs(development: dict[str, Any], validation: dict[str, Any]) -> None:
    if development.get("audit_version") != EXPECTED_DEVELOPMENT_VERSION:
        raise RuntimeError(f"development audit must be {EXPECTED_DEVELOPMENT_VERSION}")
    if validation.get("audit_version") != EXPECTED_VALIDATION_VERSION:
        raise RuntimeError(f"validation audit must be {EXPECTED_VALIDATION_VERSION}")
    if str(validation.get("scanner_version") or "") != EXPECTED_SCANNER_VERSION:
        raise RuntimeError(f"STALE_SOURCE: expected Scanner {EXPECTED_SCANNER_VERSION}")
    if validation.get("verdict") != "PROMOTE_VOLUME_SIGNAL" or RULE_ID not in (validation.get("surviving_rules") or []):
        raise RuntimeError("B.2.7-D requires B.2.7-C with VOLUME_LOW_GUARD as the surviving promoted signal")


def _gte(a: Any, b: Any) -> bool:
    x, y = _num(a), _num(b)
    return x is not None and y is not None and x >= y - 1e-12


def _lte(a: Any, b: Any) -> bool:
    x, y = _num(a), _num(b)
    return x is not None and y is not None and x <= y + 1e-12


def _gt(a: Any, b: Any) -> bool:
    x, y = _num(a), _num(b)
    return x is not None and y is not None and x > y + 1e-12


def _verdict(dev: dict[str, Any], val: dict[str, Any]) -> tuple[str, list[str]]:
    if dev.get("date_count", 0) < 40 or val.get("date_count", 0) < 20:
        return VERDICT_INSUFFICIENT, ["development or validation date count is below the robustness minimum"]
    dc, dg = dev["current_top3"], dev["guard_top3"]
    vc, vg = val["current_top3"], val["guard_top3"]
    reasons: list[str] = []
    dev_primary = _gte(dg.get("target1_first_20d_rate"), dc.get("target1_first_20d_rate")) and _lte(dg.get("stop_first_20d_rate"), dc.get("stop_first_20d_rate"))
    val_primary = _gte(vg.get("target1_first_20d_rate"), vc.get("target1_first_20d_rate")) and _lte(vg.get("stop_first_20d_rate"), vc.get("stop_first_20d_rate"))
    val_event_r = _gt(vg.get("event_r_20d_mean"), vc.get("event_r_20d_mean")) and _gte(vg.get("event_r_20d_trimmed_mean"), vc.get("event_r_20d_trimmed_mean"))
    val_mae = _gte(vg.get("mae_20d_mean"), vc.get("mae_20d_mean"))
    swaps_good = int(val["swaps"].get("GOOD_SWAP", 0)) > int(val["swaps"].get("BAD_SWAP", 0))
    dates_good = int(val["date_outcomes"].get("WIN", 0)) >= int(val["date_outcomes"].get("LOSS", 0))
    top1_safe = int(val["aggressiveness"].get("top1_changed_dates", 0)) <= 1

    if dev_primary: reasons.append("development T1-first/Stop-first direction is nonworse")
    if val_primary: reasons.append("current-version validation improves/nonworsens both T1-first and Stop-first")
    if val_event_r: reasons.append("validation mean and trimmed event-R improve")
    if val_mae: reasons.append("validation MAE20 is nonworse")
    if swaps_good: reasons.append("validation GOOD_SWAP count exceeds BAD_SWAP count")
    if dates_good: reasons.append("validation event-R WIN dates are not fewer than LOSS dates")
    if top1_safe: reasons.append("current-version Top1 is effectively preserved")

    if dev_primary and val_primary and val_event_r and val_mae and swaps_good and dates_good and top1_safe:
        return VERDICT_FREEZE, reasons
    if dev_primary and val_primary and val_event_r and val_mae and (not swaps_good or not top1_safe):
        return VERDICT_AGGRESSIVE, reasons + ["signal works but ranking side effects are too aggressive"]
    return VERDICT_NOT_ROBUST, reasons + ["one or more robustness requirements failed"]


def run_robustness(development: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    _validate_inputs(development, validation)
    dev = _build_development(development)
    val = _build_validation(validation)
    verdict, reasons = _verdict(dev, val)
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "production_changed": False,
        "rule": {
            "rule_id": RULE_ID,
            "feature": "volume_ratio_prev20",
            "threshold": "same-date READY Q25",
            "action": "demote LOW-volume READY candidates after other READY peers; preserve Production order within both groups",
            "tuning_allowed": False,
        },
        "sources": {
            "development": {"audit_version": development.get("audit_version"), "generated_at": development.get("generated_at"), "date_count": development.get("date_count")},
            "validation": {"audit_version": validation.get("audit_version"), "generated_at": validation.get("generated_at"), "scanner_version": validation.get("scanner_version"), "date_count": validation.get("valid_date_count")},
        },
        "development": dev,
        "validation": val,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "next_step": "B.2.7-E fresh independent holdout" if verdict == VERDICT_FREEZE else "Do not proceed to Production integration",
    }


def _fmt_pct(value: Any) -> str:
    x = _num(value)
    return "-" if x is None else f"{x:.2f}%"


def _fmt_rate(value: Any) -> str:
    x = _num(value)
    return "-" if x is None else f"{x*100:.1f}%"


def _fmt_r(value: Any) -> str:
    x = _num(value)
    return "-" if x is None else f"{x:+.3f}R"


def _markdown(payload: dict[str, Any]) -> str:
    dev, val = payload["development"], payload["validation"]
    lines = [
        f"# Entry Stability Volume Robustness — {AUDIT_VERSION}", "",
        f"- verdict: **{payload.get('verdict')}**",
        f"- Production changed: **{payload.get('production_changed')}**",
        f"- rule: `{RULE_ID}` / same-date READY Q25", "",
        "## Primary robustness", "",
        "| Set | Variant | T1-first | Stop-first | Event-R mean | Event-R trimmed | 20D mean | MAE20 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, block in (("Development", dev), ("Validation", val)):
        for variant, key in (("CURRENT", "current_top3"), (RULE_ID, "guard_top3")):
            m = block[key]
            lines.append(f"| {label} | {variant} | {_fmt_rate(m.get('target1_first_20d_rate'))} | {_fmt_rate(m.get('stop_first_20d_rate'))} | {_fmt_r(m.get('event_r_20d_mean'))} | {_fmt_r(m.get('event_r_20d_trimmed_mean'))} | {_fmt_pct(m.get('return_20d_mean'))} | {_fmt_pct(m.get('mae_20d_mean'))} |")
    lines += ["", "## Validation side effects", ""]
    a = val["aggressiveness"]
    s = val["swaps"]
    d = val["date_outcomes"]
    lines += [
        f"- Top1 changed: `{a.get('top1_changed_dates')}/{a.get('checked_dates')}`",
        f"- Top3 membership changed: `{a.get('top3_membership_changed_dates')}/{a.get('checked_dates')}`",
        f"- GOOD / BAD / NEUTRAL swaps: `{s.get('GOOD_SWAP',0)} / {s.get('BAD_SWAP',0)} / {s.get('NEUTRAL_SWAP',0)}`",
        f"- Event-R dates WIN / TIE / LOSS: `{d.get('WIN',0)} / {d.get('TIE',0)} / {d.get('LOSS',0)}`",
        f"- Median / max Top3 demotion distance: `{a.get('median_demotion_distance')} / {a.get('max_demotion_distance')}` ranks",
        "", "## Time-block stability", "",
        "| Set | Block | Dates | Status | T1 current→guard | Stop current→guard | Event-R current→guard |",
        "|---|---:|---|---|---:|---:|---:|",
    ]
    for label, block in (("Development", dev), ("Validation", val)):
        for b in block["blocks"]:
            cm, gm = b["current"], b["guard"]
            lines.append(f"| {label} | {b['block']} | {b['first_date']}..{b['last_date']} | {b['status']} | {_fmt_rate(cm.get('target1_first_20d_rate'))}→{_fmt_rate(gm.get('target1_first_20d_rate'))} | {_fmt_rate(cm.get('stop_first_20d_rate'))}→{_fmt_rate(gm.get('stop_first_20d_rate'))} | {_fmt_r(cm.get('event_r_20d_mean'))}→{_fmt_r(gm.get('event_r_20d_mean'))} |")
    lines += ["", "## Decision reasons", ""] + [f"- {reason}" for reason in payload.get("verdict_reasons") or []]
    lines += ["", "> B.2.7-D does not retune Q25, add strategy exceptions, combine features, or modify Production ranking. It only audits the already-surviving Volume-Low rule.", ""]
    return "\n".join(lines)


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_dir / f"scanner-entry-stability-volume-robustness_{stamp}"
    json_path, md_path, csv_path = base.with_suffix(".json"), base.with_suffix(".md"), base.with_suffix(".csv")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["set","analysis_date","status","current_event_r","guard_event_r","delta_event_r"])
        writer.writeheader()
        for label in ("development", "validation"):
            for item in payload[label]["date_outcomes"]["details"]:
                writer.writerow({"set": label, **item})
    return {"json": str(json_path), "markdown": str(md_path), "csv": str(csv_path)}
