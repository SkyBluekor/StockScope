from __future__ import annotations

import bisect
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from app.backtest.scanner_quality.entry_stability_audit import compute_entry_stability_features
from app.backtest.scanner_quality.entry_stability_validation import _attach_future_outcomes

AUDIT_VERSION = "v0.21.4-B.2.7-E"
EXPECTED_SCANNER_VERSION = "0.21.3.7"
EXPECTED_D_AUDIT_VERSION = "v0.21.4-B.2.7-D"
EXPECTED_D_VERDICT = "FREEZE_VOLUME_LOW_GUARD"
CURRENT = "CURRENT"
RULE_ID = "VOLUME_LOW_GUARD"
VERDICT_PROMOTE = "PROMOTE_VOLUME_LOW_GUARD"
VERDICT_KEEP = "KEEP_RESEARCH_ONLY"
VERDICT_REJECT = "REJECT_VOLUME_LOW_GUARD"
MIN_TRADING_DAY_GAP = 3
MIN_REQUIRED_DATES = 20
FUTURE_SESSIONS_REQUIRED = 20
RETURN_MAE_PROTECTION_PP = 1.0

FROZEN_RULE_SPEC = {
    "feature": "volume_ratio_prev20",
    "lookback": "D volume / arithmetic mean of previous 20 sessions",
    "threshold": "same-date READY Q25",
    "comparison": "<=",
    "scope": "READY_ONLY",
    "demotion": "unstable_after_stable",
    "within_group_order": "PRODUCTION_ORDER",
    "non_ready_slots": "immutable",
}
EXPECTED_FROZEN_RULE_FINGERPRINT = "bcb71bbb21fa3e16c91f973ea0f91cd81130c169f5dcd45cb6c2dcbc25390b56"


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
    trim = int(len(nums) * max(0.0, min(proportion, 0.45)))
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


def _rate(flags: Iterable[bool]) -> float | None:
    values = list(flags)
    return sum(1 for flag in values if flag) / len(values) if values else None


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


def _code(row: dict[str, Any]) -> str:
    return str(row.get("code") or "")


def _market(row: dict[str, Any]) -> str:
    return str(row.get("market") or "")


def _rank(row: dict[str, Any], key: str = "current_rank") -> int:
    try:
        value = int(row.get(key) or row.get("rank") or 999999)
    except (TypeError, ValueError):
        return 999999
    return value if value > 0 else 999999


def _compact(day: date) -> str:
    return day.strftime("%Y%m%d")


def _row_date(row: dict[str, Any]) -> str:
    return str(row.get("date") or row.get("bas_dd") or row.get("BAS_DD") or "")


def frozen_rule_fingerprint(spec: dict[str, Any] | None = None) -> str:
    payload = FROZEN_RULE_SPEC if spec is None else spec
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ensure_frozen_rule() -> str:
    actual = frozen_rule_fingerprint()
    if actual != EXPECTED_FROZEN_RULE_FINGERPRINT:
        raise RuntimeError(
            "FROZEN_RULE_CHANGED: B.2.7-E rule fingerprint mismatch. "
            f"expected={EXPECTED_FROZEN_RULE_FINGERPRINT} actual={actual}"
        )
    return actual


def ensure_scanner_version(actual: Any) -> None:
    version = str(actual or "")
    if version != EXPECTED_SCANNER_VERSION:
        raise RuntimeError(
            f"STALE_SCANNER_VERSION: expected Scanner {EXPECTED_SCANNER_VERSION}, actual {version or '<missing>'}."
        )


def validate_d_source(payload: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("audit_version") or "") != EXPECTED_D_AUDIT_VERSION:
        raise ValueError(f"Expected {EXPECTED_D_AUDIT_VERSION}, got {payload.get('audit_version')!r}")
    if str(payload.get("verdict") or "") != EXPECTED_D_VERDICT:
        raise ValueError(f"B.2.7-D is not frozen for holdout: {payload.get('verdict')!r}")
    if bool(payload.get("production_changed")):
        raise ValueError("B.2.7-D unexpectedly reports Production changed=True")
    rule = payload.get("rule") or {}
    if str(rule.get("rule_id") or "") != RULE_ID:
        raise ValueError("B.2.7-D frozen rule_id mismatch")
    if str(rule.get("feature") or "") != FROZEN_RULE_SPEC["feature"]:
        raise ValueError("B.2.7-D frozen feature mismatch")
    if str(rule.get("threshold") or "") != FROZEN_RULE_SPEC["threshold"]:
        raise ValueError("B.2.7-D frozen threshold mismatch")
    if bool(rule.get("tuning_allowed", True)):
        raise ValueError("B.2.7-D must report tuning_allowed=False")
    scanner = str((((payload.get("sources") or {}).get("validation") or {}).get("scanner_version")) or "")
    if scanner != EXPECTED_SCANNER_VERSION:
        raise ValueError(f"B.2.7-D source scanner mismatch: {scanner!r}")
    return {
        "audit_version": payload.get("audit_version"),
        "generated_at": payload.get("generated_at"),
        "verdict": payload.get("verdict"),
        "scanner_version": scanner,
    }


def annotate_and_rank_frozen_volume(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Apply the exact frozen Volume-Low rule using current-time READY values only."""
    ensure_frozen_rule()
    current = sorted((dict(row) for row in rows), key=lambda row: (_rank(row), _code(row)))
    ready = [row for row in current if str(row.get("candidate_state") or "") == "READY"]
    q25 = _quantile((row.get("volume_ratio_prev20") for row in ready), 0.25)

    annotated: list[dict[str, Any]] = []
    for row in current:
        copy = dict(row)
        value = _num(copy.get("volume_ratio_prev20"))
        is_ready = str(copy.get("candidate_state") or "") == "READY"
        low = bool(is_ready and value is not None and q25 is not None and value <= q25)
        copy["volume_q25"] = q25
        copy["volume_low"] = low
        copy["volume_ratio_prev20_band"] = "LOW" if low else ("READY_OTHER" if is_ready else "NON_READY")
        annotated.append(copy)

    ready_rows = [row for row in annotated if str(row.get("candidate_state") or "") == "READY"]
    stable = [row for row in ready_rows if not bool(row.get("volume_low"))]
    low_rows = [row for row in ready_rows if bool(row.get("volume_low"))]
    reordered_ready = stable + low_rows

    guard = list(annotated)
    ready_positions = [index for index, row in enumerate(annotated) if str(row.get("candidate_state") or "") == "READY"]
    for index, replacement in zip(ready_positions, reordered_ready):
        guard[index] = dict(replacement)

    guard_rank_by_key: dict[tuple[str, str], int] = {}
    for position, row in enumerate(guard, start=1):
        row["guard_rank"] = position
        row["guard_rule"] = RULE_ID
        guard_rank_by_key[(_market(row), _code(row))] = position
    for row in annotated:
        row["guard_rank"] = guard_rank_by_key.get((_market(row), _code(row)))
        row["guard_rule"] = RULE_ID

    meta = {
        "rule_id": RULE_ID,
        "q25": q25,
        "ready_count": len(ready_rows),
        "unstable_count": len(low_rows),
        "rule_fingerprint": EXPECTED_FROZEN_RULE_FINGERPRINT,
    }
    return annotated, guard, meta


def ranking_freeze_hash(analysis_date: str, current: list[dict[str, Any]], guard: list[dict[str, Any]], q25: Any) -> str:
    guard_pos = {(_market(row), _code(row)): int(row.get("guard_rank") or 999999) for row in guard}
    canonical_rows = []
    for row in current:
        key = (_market(row), _code(row))
        canonical_rows.append({
            "analysis_date": analysis_date,
            "market": key[0],
            "code": key[1],
            "current_rank": _rank(row),
            "candidate_state": str(row.get("candidate_state") or ""),
            "volume_ratio_prev20": _num(row.get("volume_ratio_prev20")),
            "q25": _num(q25),
            "volume_low": bool(row.get("volume_low")),
            "guard_rank": guard_pos.get(key),
        })
    canonical = json.dumps(canonical_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_holdout_date(scanner: Any, market_store: Any, *, as_of: date, market_scope: str = "ALL") -> dict[str, Any]:
    """Run Production ranking + frozen Volume-Low rank, freeze hash, then read D+1 outcomes."""
    from app.backtest.candidate_priority import rank_candidates

    ensure_frozen_rule()
    ensure_scanner_version(getattr(scanner, "VERSION", None))
    scope = market_scope.upper().strip()
    if scope != "ALL":
        raise ValueError("B.2.7-E is frozen to market_scope=ALL")
    markets = ["KOSPI", "KOSDAQ"]
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
        ordinary.sort(
            key=lambda row: (float(row.get("trade_value") or 0), float(row.get("market_cap") or 0)),
            reverse=True,
        )
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
        rows.append({
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
        })

    current_frozen, guard_frozen, meta = annotate_and_rank_frozen_volume(rows)
    freeze_hash = ranking_freeze_hash(as_of.isoformat(), current_frozen, guard_frozen, meta.get("q25"))
    guard_rank_map = {(_market(row), _code(row)): int(row.get("guard_rank") or 999999) for row in guard_frozen}

    # Future rows are read only after both rankings and the freeze hash are complete.
    current_with_outcomes = _attach_future_outcomes(current_frozen, candidate_by_key, market_store, as_of=as_of)
    current = sorted(current_with_outcomes, key=lambda row: (_rank(row), _code(row)))
    guard: list[dict[str, Any]] = []
    for row in current:
        copy = dict(row)
        copy["guard_rank"] = guard_rank_map.get((_market(row), _code(row)), 999999)
        copy["guard_rule"] = RULE_ID
        guard.append(copy)
    guard.sort(key=lambda row: (int(row.get("guard_rank") or 999999), _code(row)))

    return {
        "analysis_date": as_of.isoformat(),
        "status": "OK",
        "scanner_version": str(scanner.VERSION),
        "candidate_count": len(current),
        "production_ranking_changes": ranking_changes,
        "frozen_rule_meta": meta,
        "ranking_freeze_hash": freeze_hash,
        "current_candidates": current,
        "guard_candidates": guard,
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
    event_r = [n for row in rows if (n := _num(row.get("event_r_20d"))) is not None]
    result["event_r_20d_mean"] = _mean(event_r)
    result["event_r_20d_median"] = _median(event_r)
    result["event_r_20d_trimmed_mean"] = _trimmed_mean(event_r)
    result["event_r_20d_positive_rate"] = _rate(n > 0 for n in event_r)
    for horizon in (10, 20):
        events = [str(row.get(f"event_{horizon}d") or "") for row in rows if row.get(f"event_{horizon}d") is not None]
        result[f"target1_first_{horizon}d_rate"] = _rate(event == "TARGET1_FIRST" for event in events)
        result[f"stop_first_{horizon}d_rate"] = _rate(event == "STOP_FIRST" for event in events)
        result[f"no_event_{horizon}d_rate"] = _rate(event not in {"TARGET1_FIRST", "STOP_FIRST"} for event in events)
    return result


def _select(date_results: list[dict[str, Any]], variant: str, top_n: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in date_results:
        rows = item.get("current_candidates") if variant == CURRENT else item.get("guard_candidates")
        output.extend((rows or [])[:top_n])
    return output


def _date_event_r(rows: list[dict[str, Any]]) -> float | None:
    return _mean(row.get("event_r_20d") for row in rows[:3])


def _date_outcome(current: list[dict[str, Any]], guard: list[dict[str, Any]]) -> dict[str, Any]:
    cur = _date_event_r(current)
    new = _date_event_r(guard)
    if cur is None or new is None:
        status = "TIE"
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
    c_top, g_top = current[:3], guard[:3]
    c_codes, g_codes = {_code(row) for row in c_top}, {_code(row) for row in g_top}
    removed = [row for row in c_top if _code(row) not in g_codes]
    added = [row for row in g_top if _code(row) not in c_codes]
    out: list[dict[str, Any]] = []
    for rem, add in zip(removed, added):
        out.append({
            "analysis_date": analysis_date,
            "category": _swap_category(rem, add),
            "removed": {k: rem.get(k) for k in ("code", "name", "current_rank", "event_20d", "event_r_20d", "return_20d", "mae_20d")},
            "added": {k: add.get(k) for k in ("code", "name", "current_rank", "event_20d", "event_r_20d", "return_20d", "mae_20d")},
        })
    return out


def _ranking_impact(date_results: list[dict[str, Any]]) -> dict[str, Any]:
    top1 = top3_membership = top3_order = top5_membership = 0
    moves: list[int] = []
    unstable = 0
    for item in date_results:
        current = item.get("current_candidates") or []
        guard = item.get("guard_candidates") or []
        if not current or not guard:
            continue
        c1, g1 = [_code(x) for x in current[:1]], [_code(x) for x in guard[:1]]
        c3, g3 = [_code(x) for x in current[:3]], [_code(x) for x in guard[:3]]
        c5, g5 = [_code(x) for x in current[:5]], [_code(x) for x in guard[:5]]
        top1 += int(c1 != g1)
        top3_membership += int(set(c3) != set(g3))
        top3_order += int(c3 != g3)
        top5_membership += int(set(c5) != set(g5))
        guard_pos = {_code(row): i + 1 for i, row in enumerate(guard)}
        for i, row in enumerate(current, start=1):
            if _code(row) in guard_pos:
                moves.append(abs(guard_pos[_code(row)] - i))
            unstable += int(bool(row.get("volume_low")))
    checked = len([x for x in date_results if x.get("status") == "OK"])
    return {
        "checked_dates": checked,
        "top1_changed_dates": top1,
        "top3_membership_changed_dates": top3_membership,
        "top3_order_changed_dates": top3_order,
        "top5_membership_changed_dates": top5_membership,
        "unstable_candidate_count": unstable,
        "mean_absolute_rank_move": _mean(moves),
        "max_absolute_rank_move": max(moves) if moves else 0,
        "top3_change_rate": top3_membership / checked if checked else None,
    }


def _split_blocks(dates: list[str], block_count: int = 4) -> list[list[str]]:
    if not dates:
        return []
    base, remainder = divmod(len(dates), block_count)
    output: list[list[str]] = []
    start = 0
    for index in range(block_count):
        size = base + (1 if index < remainder else 0)
        if size:
            output.append(dates[start:start + size])
        start += size
    return output


def _block_status(current: dict[str, Any], guard: dict[str, Any]) -> str:
    ct, gt = _num(current.get("target1_first_20d_rate")), _num(guard.get("target1_first_20d_rate"))
    cs, gs = _num(current.get("stop_first_20d_rate")), _num(guard.get("stop_first_20d_rate"))
    if None in (ct, gt, cs, gs):
        return "NEUTRAL"
    if gt > ct + 1e-12 and gs < cs - 1e-12:
        return "POSITIVE"
    if gt < ct - 1e-12 or gs > cs + 1e-12:
        return "NEGATIVE"
    return "NEUTRAL"


def _gte(a: Any, b: Any) -> bool:
    x, y = _num(a), _num(b)
    return x is not None and y is not None and x >= y - 1e-12


def _gt(a: Any, b: Any) -> bool:
    x, y = _num(a), _num(b)
    return x is not None and y is not None and x > y + 1e-12


def _lt(a: Any, b: Any) -> bool:
    x, y = _num(a), _num(b)
    return x is not None and y is not None and x < y - 1e-12


def _verdict(current: dict[str, Any], guard: dict[str, Any], date_outcomes: dict[str, Any], swaps: dict[str, Any], impact: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    t1_up = _gt(guard.get("target1_first_20d_rate"), current.get("target1_first_20d_rate"))
    stop_down = _lt(guard.get("stop_first_20d_rate"), current.get("stop_first_20d_rate"))
    event_r_up = _gt(guard.get("event_r_20d_mean"), current.get("event_r_20d_mean"))
    cur_mae, grd_mae = _num(current.get("mae_20d_mean")), _num(guard.get("mae_20d_mean"))
    cur_ret, grd_ret = _num(current.get("return_20d_mean")), _num(guard.get("return_20d_mean"))
    mae_ok = cur_mae is not None and grd_mae is not None and grd_mae >= cur_mae - RETURN_MAE_PROTECTION_PP
    return_ok = cur_ret is not None and grd_ret is not None and grd_ret >= cur_ret - RETURN_MAE_PROTECTION_PP
    wins_ok = int(date_outcomes.get("WIN", 0)) >= int(date_outcomes.get("LOSS", 0))
    swaps_ok = int(swaps.get("GOOD_SWAP", 0)) >= int(swaps.get("BAD_SWAP", 0))
    top1_safe = int(impact.get("top1_changed_dates", 0)) <= max(1, int(impact.get("checked_dates", 0)) // 10)

    if t1_up: reasons.append("Fresh Top3 Target1-first 20D improved")
    if stop_down: reasons.append("Fresh Top3 Stop-first 20D improved")
    if event_r_up: reasons.append("Fresh Top3 mean event-R 20D improved")
    if mae_ok: reasons.append("Fresh MAE20 stayed within the -1.0pp protection band")
    if return_ok: reasons.append("Fresh 20D mean stayed within the -1.0pp protection band")
    if wins_ok: reasons.append("Fresh event-R WIN dates are not fewer than LOSS dates")
    if swaps_ok: reasons.append("Fresh GOOD_SWAP count is not below BAD_SWAP count")
    if top1_safe: reasons.append("Fresh Top1 is not destructively changed")

    mandatory = t1_up and stop_down and event_r_up and mae_ok and return_ok
    robustness = wins_ok and swaps_ok and top1_safe
    if mandatory and robustness:
        return VERDICT_PROMOTE, reasons
    if not mandatory and (
        (_gte(guard.get("target1_first_20d_rate"), current.get("target1_first_20d_rate")) and _gte(current.get("stop_first_20d_rate"), guard.get("stop_first_20d_rate")))
        or event_r_up
    ):
        return VERDICT_KEEP, reasons + ["Fresh holdout is directionally mixed or insufficient for Production promotion"]
    return VERDICT_REJECT, reasons + ["Fresh holdout contradicts one or more frozen-rule requirements"]


def aggregate_holdout(date_results: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [item for item in date_results if item.get("status") == "OK"]
    comparisons: dict[str, Any] = {}
    for top_n in (1, 3, 5):
        comparisons[f"top{top_n}"] = {
            CURRENT: _metrics(_select(valid, CURRENT, top_n)),
            RULE_ID: _metrics(_select(valid, RULE_ID, top_n)),
        }

    date_details = [
        {"analysis_date": item.get("analysis_date"), **_date_outcome(item.get("current_candidates") or [], item.get("guard_candidates") or [])}
        for item in valid
    ]
    date_outcomes = {**Counter(item["status"] for item in date_details), "details": date_details}
    swap_details = [
        swap
        for item in valid
        for swap in _swaps(item.get("current_candidates") or [], item.get("guard_candidates") or [], str(item.get("analysis_date") or ""))
    ]
    swaps = {**Counter(item["category"] for item in swap_details), "count": len(swap_details), "details": swap_details[:40]}
    avoided_stop = sum(1 for item in swap_details if str((item.get("removed") or {}).get("event_20d")) == "STOP_FIRST")
    demoted_target = sum(1 for item in swap_details if str((item.get("removed") or {}).get("event_20d")) == "TARGET1_FIRST")
    impact = _ranking_impact(valid)

    by_date = {str(item.get("analysis_date")): item for item in valid}
    blocks: list[dict[str, Any]] = []
    for index, block_dates in enumerate(_split_blocks(sorted(by_date)), start=1):
        current_rows = [row for day in block_dates for row in (by_date[day].get("current_candidates") or [])[:3]]
        guard_rows = [row for day in block_dates for row in (by_date[day].get("guard_candidates") or [])[:3]]
        cm, gm = _metrics(current_rows), _metrics(guard_rows)
        blocks.append({
            "block": index,
            "first_date": block_dates[0],
            "last_date": block_dates[-1],
            "date_count": len(block_dates),
            "current": cm,
            "guard": gm,
            "status": _block_status(cm, gm),
        })

    top3_current = comparisons["top3"][CURRENT]
    top3_guard = comparisons["top3"][RULE_ID]
    verdict, reasons = _verdict(top3_current, top3_guard, date_outcomes, swaps, impact)
    return {
        "comparisons": comparisons,
        "ranking_impact": impact,
        "date_outcomes": date_outcomes,
        "swaps": swaps,
        "avoided_stop_count": avoided_stop,
        "demoted_target1_count": demoted_target,
        "blocks": blocks,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }


def run_holdout(
    scanner: Any,
    market_store: Any,
    *,
    evaluation_dates: list[date],
    excluded_dates: set[date],
    d_source: dict[str, Any],
    market_scope: str = "ALL",
    progress: Any | None = None,
) -> dict[str, Any]:
    ensure_frozen_rule()
    ensure_scanner_version(getattr(scanner, "VERSION", None))
    overlap = set(evaluation_dates) & set(excluded_dates)
    if overlap:
        raise ValueError(f"fresh holdout overlaps excluded dates: {[d.isoformat() for d in sorted(overlap)]}")
    date_results: list[dict[str, Any]] = []
    for index, as_of in enumerate(evaluation_dates, start=1):
        result = run_holdout_date(scanner, market_store, as_of=as_of, market_scope=market_scope)
        date_results.append(result)
        if callable(progress):
            progress(index, len(evaluation_dates), result)
    aggregate = aggregate_holdout(date_results)
    missing = [item.get("analysis_date") for item in date_results if item.get("status") != "OK"]
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scanner_version": str(scanner.VERSION),
        "market_scope": market_scope,
        "production_changed": False,
        "guardrail": (
            "Frozen Volume-Low fresh independent holdout. Q25, formula, READY-only scope and demotion semantics are locked. "
            "Current and guard ranks plus ranking freeze hash are computed before D+1 future rows are read."
        ),
        "frozen_rule": FROZEN_RULE_SPEC,
        "frozen_rule_fingerprint": EXPECTED_FROZEN_RULE_FINGERPRINT,
        "frozen_rule_changed": False,
        "d_source": d_source,
        "holdout": {
            "evaluation_dates": [day.isoformat() for day in evaluation_dates],
            "requested_date_count": len(evaluation_dates),
            "valid_date_count": len(evaluation_dates) - len(missing),
            "missing_dates": missing,
            "excluded_date_count": len(excluded_dates),
            "overlap_with_excluded": 0,
            "min_trading_day_gap_from_excluded": MIN_TRADING_DAY_GAP,
            "date_fingerprint": hashlib.sha256("|".join(day.isoformat() for day in evaluation_dates).encode("utf-8")).hexdigest(),
        },
        "ranking_freeze_hashes": {str(item.get("analysis_date")): item.get("ranking_freeze_hash") for item in date_results if item.get("status") == "OK"},
        **aggregate,
        "dates": date_results,
    }


def _is_complete_day(market_store: Any, day: date) -> bool:
    key = _compact(day)
    return all(
        market_store.latest_complete_date(market, kind, key) == key
        for market in ("KOSPI", "KOSDAQ")
        for kind in ("stock", "index")
    )


def build_common_trading_calendar(
    market_store: Any,
    *,
    start: date = date(2023, 1, 1),
    end: date | None = None,
) -> list[date]:
    end = end or date.today()
    output: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5 and _is_complete_day(market_store, current):
            output.append(current)
        current += timedelta(days=1)
    return output


def _trading_index(calendar: list[date], day: date) -> int:
    return bisect.bisect_left(calendar, day)


def _far_from_dates(calendar: list[date], candidate: date, blocked: set[date], min_gap: int) -> bool:
    cidx = _trading_index(calendar, candidate)
    indices = sorted(_trading_index(calendar, day) for day in blocked)
    pos = bisect.bisect_left(indices, cidx)
    for neighbor in (pos - 1, pos):
        if 0 <= neighbor < len(indices) and abs(cidx - indices[neighbor]) < min_gap:
            return False
    return True


def _allocation_by_year(years: list[int], sample_size: int) -> dict[int, int]:
    if not years or sample_size < len(years):
        raise ValueError("sample size is smaller than the number of eligible year blocks")
    base, remainder = divmod(sample_size, len(years))
    return {year: base + (1 if index < remainder else 0) for index, year in enumerate(sorted(years))}


def _spread_pick(candidates: list[date], count: int, *, calendar: list[date], blocked: set[date], min_gap: int) -> list[date]:
    if count <= 0:
        return []
    available = [day for day in candidates if _far_from_dates(calendar, day, blocked, min_gap)]
    if len(available) < count:
        raise ValueError(f"not enough eligible dates: need {count}, have {len(available)}")
    selected: list[date] = []
    for slot in range(count):
        target = round(slot * (len(available) - 1) / max(count - 1, 1))
        order = sorted(range(len(available)), key=lambda idx: (abs(idx - target), idx))
        chosen = None
        for idx in order:
            day = available[idx]
            if day in selected:
                continue
            if _far_from_dates(calendar, day, blocked | set(selected), min_gap):
                chosen = day
                break
        if chosen is None:
            raise ValueError("unable to satisfy holdout spacing while preserving deterministic spread")
        selected.append(chosen)
    return sorted(selected)


def select_fresh_holdout(
    calendar: list[date],
    excluded_dates: set[date],
    *,
    sample_size: int = 20,
    existing_dates: list[date] | None = None,
    min_gap: int = MIN_TRADING_DAY_GAP,
    future_sessions_required: int = FUTURE_SESSIONS_REQUIRED,
) -> list[date]:
    if len(calendar) <= future_sessions_required:
        raise ValueError("trading calendar has insufficient future sessions")
    latest_candidate_index = len(calendar) - future_sessions_required - 1
    candidate_calendar = calendar[: latest_candidate_index + 1]
    existing = sorted(set(existing_dates or []))
    if set(existing) & excluded_dates:
        raise ValueError("existing holdout overlaps excluded dates")
    blocked = set(excluded_dates)
    for day in existing:
        if day not in candidate_calendar:
            raise ValueError(f"existing holdout lacks enough future sessions or is incomplete: {day.isoformat()}")
        if not _far_from_dates(calendar, day, blocked, min_gap):
            raise ValueError(f"existing holdout violates exclusion gap: {day.isoformat()}")
        if not _far_from_dates(calendar, day, set(existing) - {day}, min_gap):
            raise ValueError(f"existing holdout dates violate mutual spacing: {day.isoformat()}")

    eligible = [day for day in candidate_calendar if day not in excluded_dates and _far_from_dates(calendar, day, excluded_dates, min_gap)]
    years = sorted({day.year for day in eligible})
    allocation = _allocation_by_year(years, sample_size)
    selected = list(existing)
    selected_set = set(selected)
    for year in years:
        desired = allocation[year]
        current = [day for day in selected if day.year == year]
        need = desired - len(current)
        if need <= 0:
            continue
        candidates = [day for day in eligible if day.year == year and day not in selected_set]
        picks = _spread_pick(candidates, need, calendar=calendar, blocked=excluded_dates | selected_set, min_gap=min_gap)
        selected.extend(picks)
        selected_set.update(picks)
    selected = sorted(selected)
    if len(selected) != sample_size:
        raise ValueError(f"holdout selector produced {len(selected)} dates, expected {sample_size}")
    return selected


def _fmt_pct(value: Any) -> str:
    x = _num(value)
    return "-" if x is None else f"{x:.2f}%"


def _fmt_rate(value: Any) -> str:
    x = _num(value)
    return "-" if x is None else f"{x * 100:.1f}%"


def _fmt_r(value: Any) -> str:
    x = _num(value)
    return "-" if x is None else f"{x:+.3f}R"


def _markdown(payload: dict[str, Any]) -> str:
    top3 = (payload.get("comparisons") or {}).get("top3") or {}
    cur, guard = top3.get(CURRENT) or {}, top3.get(RULE_ID) or {}
    holdout = payload.get("holdout") or {}
    impact = payload.get("ranking_impact") or {}
    outcomes = payload.get("date_outcomes") or {}
    swaps = payload.get("swaps") or {}
    lines = [
        f"# Frozen Volume-Low Fresh Holdout — {AUDIT_VERSION}", "",
        f"- verdict: **{payload.get('verdict')}**",
        f"- scanner: `{payload.get('scanner_version')}`",
        f"- fresh dates: `{holdout.get('valid_date_count')}/{holdout.get('requested_date_count')}`",
        f"- excluded prior dates: `{holdout.get('excluded_date_count')}`",
        f"- overlap: `{holdout.get('overlap_with_excluded')}`",
        f"- frozen fingerprint: `{payload.get('frozen_rule_fingerprint')}`",
        f"- Production changed: **{payload.get('production_changed')}**", "",
        "## Primary — Top3", "",
        "| Variant | T1-first | Stop-first | NO_EVENT | Event-R mean | Event-R trimmed | 20D mean | 20D trimmed | MAE20 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| CURRENT | {_fmt_rate(cur.get('target1_first_20d_rate'))} | {_fmt_rate(cur.get('stop_first_20d_rate'))} | {_fmt_rate(cur.get('no_event_20d_rate'))} | {_fmt_r(cur.get('event_r_20d_mean'))} | {_fmt_r(cur.get('event_r_20d_trimmed_mean'))} | {_fmt_pct(cur.get('return_20d_mean'))} | {_fmt_pct(cur.get('return_20d_trimmed_mean'))} | {_fmt_pct(cur.get('mae_20d_mean'))} |",
        f"| {RULE_ID} | {_fmt_rate(guard.get('target1_first_20d_rate'))} | {_fmt_rate(guard.get('stop_first_20d_rate'))} | {_fmt_rate(guard.get('no_event_20d_rate'))} | {_fmt_r(guard.get('event_r_20d_mean'))} | {_fmt_r(guard.get('event_r_20d_trimmed_mean'))} | {_fmt_pct(guard.get('return_20d_mean'))} | {_fmt_pct(guard.get('return_20d_trimmed_mean'))} | {_fmt_pct(guard.get('mae_20d_mean'))} |",
        "", "## Stability / side effects", "",
        f"- Event-R dates WIN / TIE / LOSS: `{outcomes.get('WIN',0)} / {outcomes.get('TIE',0)} / {outcomes.get('LOSS',0)}`",
        f"- GOOD / BAD / NEUTRAL swaps: `{swaps.get('GOOD_SWAP',0)} / {swaps.get('BAD_SWAP',0)} / {swaps.get('NEUTRAL_SWAP',0)}`",
        f"- avoided STOP_FIRST / demoted TARGET1_FIRST: `{payload.get('avoided_stop_count',0)} / {payload.get('demoted_target1_count',0)}`",
        f"- Top1 changed: `{impact.get('top1_changed_dates')}/{impact.get('checked_dates')}`",
        f"- Top3 membership changed: `{impact.get('top3_membership_changed_dates')}/{impact.get('checked_dates')}`",
        f"- mean / max absolute rank move: `{impact.get('mean_absolute_rank_move')} / {impact.get('max_absolute_rank_move')}`",
        "", "## Time blocks", "",
        "| Block | Dates | Status | T1 current→guard | Stop current→guard | Event-R current→guard |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for block in payload.get("blocks") or []:
        cm, gm = block.get("current") or {}, block.get("guard") or {}
        lines.append(
            f"| {block.get('block')} | {block.get('first_date')}..{block.get('last_date')} | {block.get('status')} | "
            f"{_fmt_rate(cm.get('target1_first_20d_rate'))}→{_fmt_rate(gm.get('target1_first_20d_rate'))} | "
            f"{_fmt_rate(cm.get('stop_first_20d_rate'))}→{_fmt_rate(gm.get('stop_first_20d_rate'))} | "
            f"{_fmt_r(cm.get('event_r_20d_mean'))}→{_fmt_r(gm.get('event_r_20d_mean'))} |"
        )
    lines += ["", "## Decision reasons", ""] + [f"- {reason}" for reason in payload.get("verdict_reasons") or []]
    lines += ["", "> This is a frozen independent holdout. The Q25 threshold, feature formula, READY-only scope, and demotion semantics are not retuned from the observed result.", ""]
    return "\n".join(lines)


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_dir / f"scanner-entry-stability-volume-holdout_{stamp}"
    json_path, md_path, csv_path = base.with_suffix(".json"), base.with_suffix(".md"), base.with_suffix(".csv")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["analysis_date", "code", "name", "market", "current_rank", "guard_rank", "candidate_state", "strategy", "volume_ratio_prev20", "volume_q25", "volume_low", "event_20d", "event_r_20d", "return_20d", "mfe_20d", "mae_20d"])
        writer.writeheader()
        for item in payload.get("dates") or []:
            for row in item.get("current_candidates") or []:
                writer.writerow(row)
    return {"json": str(json_path), "markdown": str(md_path), "csv": str(csv_path)}
