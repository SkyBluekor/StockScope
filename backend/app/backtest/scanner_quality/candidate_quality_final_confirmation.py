from __future__ import annotations

import bisect
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from app.backtest.scanner_quality.candidate_quality_validation import (
    EXPECTED_SCANNER_VERSION,
    OVEREXTENSION_FEATURES as _C_FEATURES,
    _compact,
    _flatten_outcome,
    _mean,
    _mean_without_best,
    _median,
    _num,
    _quality_features,
    _q75,
    _rate,
    _row_date,
    _trimmed_mean,
    ensure_scanner_version,
)

AUDIT_VERSION = "v0.21.4-B.2.6-E"
EXPECTED_D_AUDIT_VERSION = "v0.21.4-B.2.6-D"
EXPECTED_D_VERDICT = "REFINED_GUARD_READY_FOR_CONFIRMATION"

CURRENT = "CURRENT"
FROZEN_REFINED = "FROZEN_REFINED_GUARD"

VERDICT_PROMOTE = "PROMOTE_TO_PRODUCTION"
VERDICT_KEEP = "KEEP_RESEARCH_ONLY"
VERDICT_REJECT = "REJECT_REFINED_GUARD"
VERDICT_INSUFFICIENT = "INSUFFICIENT_FINAL_SAMPLE"

MIN_OVEREXTENDED = 15
MIN_EXCEPTION_OPPORTUNITIES = 3
MIN_BLOCKS_STABLE = 3
MIN_TRADING_DAY_GAP_FROM_USED = 3

OVEREXTENSION_FEATURES = tuple(_C_FEATURES)
if OVEREXTENSION_FEATURES != (
    "relative_strength_market_pct",
    "price_vs_ma20_pct",
    "ma20_vs_ma60_pct",
):
    raise RuntimeError("B.2.6-E frozen feature family no longer matches B.2.6-C")

FROZEN_RULE_SPEC = {
    "features": list(OVEREXTENSION_FEATURES),
    "threshold": "same-date READY Q75",
    "overextension": "available_features>=2 and extreme_feature_count>=2",
    "demotion": (
        "READY overextended candidates move after non-overextended READY peers; "
        "current Production rank preserved within groups"
    ),
    "exemption": "strategy==trend_recovery and extreme_feature_count==2",
    "exemption_3of3": False,
    "non_ready_slots": "immutable",
}
EXPECTED_FROZEN_RULE_FINGERPRINT = "5967c491bbfaa11ca4fa4f8197504813712d08d2b76d76be78ea314b49800579"

BLOCKS: tuple[tuple[str, date, date], ...] = (
    ("2023", date(2023, 1, 1), date(2023, 12, 31)),
    ("2024", date(2024, 1, 1), date(2024, 12, 31)),
    ("2025", date(2025, 1, 1), date(2025, 12, 31)),
    ("2026", date(2026, 1, 1), date(2026, 8, 18)),
)


def frozen_rule_fingerprint(spec: dict[str, Any] | None = None) -> str:
    payload = FROZEN_RULE_SPEC if spec is None else spec
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ensure_frozen_rule() -> str:
    actual = frozen_rule_fingerprint()
    if actual != EXPECTED_FROZEN_RULE_FINGERPRINT:
        raise RuntimeError(
            "FROZEN_RULE_CHANGED: B.2.6-E rule fingerprint mismatch. "
            f"expected={EXPECTED_FROZEN_RULE_FINGERPRINT} actual={actual}"
        )
    return actual


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


def _is_ready(row: dict[str, Any]) -> bool:
    return str(row.get("candidate_state") or "") == "READY"


def annotate_and_rank_frozen(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Freeze current-time annotations/ranks before any future outcome is read."""
    ensure_frozen_rule()
    current = sorted((dict(row) for row in rows), key=lambda row: (_rank(row), _code(row)))
    ready = [row for row in current if _is_ready(row)]
    thresholds = {feature: _q75(row.get(feature) for row in ready) for feature in OVEREXTENSION_FEATURES}

    annotations: dict[tuple[str, str], dict[str, Any]] = {}
    for row in current:
        key = (_market(row), _code(row))
        if not _is_ready(row):
            annotations[key] = {
                "available_feature_count": 0,
                "extreme_feature_count": 0,
                "extreme_features": [],
                "overextended": False,
                "refined_exception": False,
                "frozen_demoted": False,
            }
            continue

        extreme: list[str] = []
        available = 0
        for feature in OVEREXTENSION_FEATURES:
            value = _num(row.get(feature))
            threshold = thresholds.get(feature)
            if value is None or threshold is None:
                continue
            available += 1
            if value > threshold:
                extreme.append(feature)

        overextended = available >= 2 and len(extreme) >= 2
        refined_exception = (
            overextended
            and str(row.get("strategy") or "") == "trend_recovery"
            and len(extreme) == 2
        )
        annotations[key] = {
            "available_feature_count": available,
            "extreme_feature_count": len(extreme),
            "extreme_features": extreme,
            "overextended": overextended,
            "refined_exception": refined_exception,
            "frozen_demoted": bool(overextended and not refined_exception),
        }

    annotated_current: list[dict[str, Any]] = []
    for row in current:
        copy = dict(row)
        copy.update(annotations[(_market(copy), _code(copy))])
        annotated_current.append(copy)

    ready_rows = [row for row in annotated_current if _is_ready(row)]
    frozen_ready = sorted(
        ready_rows,
        key=lambda row: (int(bool(row.get("frozen_demoted"))), _rank(row), _code(row)),
    )
    frozen = list(annotated_current)
    ready_positions = [index for index, row in enumerate(annotated_current) if _is_ready(row)]
    for index, replacement in zip(ready_positions, frozen_ready):
        frozen[index] = dict(replacement)

    frozen_rank_by_key: dict[tuple[str, str], int] = {}
    for position, row in enumerate(frozen, start=1):
        row["frozen_rank"] = position
        frozen_rank_by_key[(_market(row), _code(row))] = position
    for row in annotated_current:
        row["frozen_rank"] = frozen_rank_by_key.get((_market(row), _code(row)))

    meta = {
        "thresholds": thresholds,
        "ready_count": len(ready_rows),
        "overextended_count": sum(int(bool(row.get("overextended"))) for row in annotated_current if _is_ready(row)),
        "refined_exception_opportunities": sum(int(bool(row.get("refined_exception"))) for row in annotated_current if _is_ready(row)),
        "refined_exception_used": sum(int(bool(row.get("refined_exception"))) for row in annotated_current if _is_ready(row)),
        "actually_demoted_count": sum(int(bool(row.get("frozen_demoted"))) for row in annotated_current if _is_ready(row)),
        "rule_fingerprint": EXPECTED_FROZEN_RULE_FINGERPRINT,
    }
    return annotated_current, frozen, meta


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return _market(row), _code(row)


def _enrich_outcomes(
    rows: list[dict[str, Any]],
    outcomes: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        copy.update(outcomes.get(_row_key(copy)) or {})
        result.append(copy)
    return result


def run_frozen_date(scanner: Any, market_store: Any, *, as_of: date, market_scope: str = "ALL") -> dict[str, Any]:
    """Run current Production ranking + frozen refined guard, then read future outcomes."""
    from app.backtest.candidate_priority import rank_candidates
    from app.backtest.models import BacktestConfig
    from app.backtest.scanner_quality.early_pruning_audit import _future_metrics

    ensure_frozen_rule()
    ensure_scanner_version(getattr(scanner, "VERSION", None))
    scope = market_scope.upper().strip()
    if scope != "ALL":
        raise ValueError("B.2.6-E final confirmation is frozen to market_scope=ALL")
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
            if scanner._special_reason(row) is not None:  # noqa: SLF001 - audit mirrors Production
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
            _row, stock_rows, index_rows = source
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
                snapshot = scanner.engine._signal_snapshot(  # noqa: SLF001
                    stock_rows=stock_rows,
                    index_rows=index_rows,
                    index=len(stock_rows) - 1,
                    config=config,
                    sector_input=None,
                )
        features_by_key[(market, code)] = _quality_features(snapshot)

    ranked, ranking_changes = rank_candidates(actionable)
    pre_future_rows: list[dict[str, Any]] = []
    for rank, candidate in enumerate(ranked, start=1):
        market = str(candidate.get("market") or "")
        code = str(candidate.get("code") or "")
        pre_future_rows.append({
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
        })

    # Freeze both current and refined ranks before D+1 data is touched.
    current_pre, frozen_pre, guard_meta = annotate_and_rank_frozen(pre_future_rows)
    frozen_order_hash = hashlib.sha256(
        "|".join(f"{_market(row)}:{_code(row)}:{row.get('frozen_rank')}" for row in frozen_pre).encode("utf-8")
    ).hexdigest()

    codes_by_market: dict[str, set[str]] = defaultdict(set)
    for row in current_pre:
        codes_by_market[_market(row)].add(_code(row))

    future_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    future_start = _compact(as_of + timedelta(days=1))
    future_end = _compact(as_of + timedelta(days=60))
    for market, codes in codes_by_market.items():
        if not market or not codes:
            continue
        series_map = market_store.stock_series_many(market, sorted(codes), future_start, future_end)
        for code, series in series_map.items():
            future_by_key[(market, str(code))] = sorted((dict(row) for row in series.rows.values()), key=_row_date)

    candidate_by_key = {
        (str(candidate.get("market") or ""), str(candidate.get("code") or "")): candidate
        for candidate in ranked
    }
    outcomes: dict[tuple[str, str], dict[str, Any]] = {}
    for key, candidate in candidate_by_key.items():
        outcome = _future_metrics(
            candidate=candidate,
            future_rows=future_by_key.get(key, []),
            horizons=(5, 10, 20),
        )
        outcomes[key] = _flatten_outcome(outcome)

    current_rows = _enrich_outcomes(current_pre, outcomes)
    frozen_rows = _enrich_outcomes(frozen_pre, outcomes)
    current_rows.sort(key=lambda row: (_rank(row), _code(row)))
    frozen_rows.sort(key=lambda row: (_rank(row, "frozen_rank"), _code(row)))

    return {
        "analysis_date": as_of.isoformat(),
        "status": "OK",
        "scanner_version": str(scanner.VERSION),
        "candidate_count": len(current_rows),
        "production_ranking_changes": ranking_changes,
        "guard_meta": guard_meta,
        "frozen_order_hash_before_future": frozen_order_hash,
        "current_candidates": current_rows,
        "refined_candidates": frozen_rows,
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"count": len(rows)}
    for horizon in (5, 10, 20):
        values = [n for row in rows if (n := _num(row.get(f"return_{horizon}d"))) is not None]
        result[f"return_{horizon}d_mean"] = _mean(values)
        result[f"return_{horizon}d_median"] = _median(values)
        result[f"return_{horizon}d_positive_rate"] = _rate(value > 0 for value in values)
        if horizon == 20:
            result["return_20d_trimmed_mean"] = _trimmed_mean(values)
            result["return_20d_mean_without_best"] = _mean_without_best(values)
            result["return_20d_max"] = max(values) if values else None
    result["mfe_20d_mean"] = _mean(row.get("mfe_20d") for row in rows)
    result["mae_20d_mean"] = _mean(row.get("mae_20d") for row in rows)
    for horizon in (10, 20):
        events = [str(row.get(f"event_{horizon}d") or "") for row in rows if row.get(f"event_{horizon}d") is not None]
        result[f"target1_first_{horizon}d_rate"] = _rate(event == "TARGET1_FIRST" for event in events)
        result[f"stop_first_{horizon}d_rate"] = _rate(event == "STOP_FIRST" for event in events)
    return result


def _select_top(date_results: list[dict[str, Any]], variant: str, top_n: int) -> list[dict[str, Any]]:
    key = "current_candidates" if variant == CURRENT else "refined_candidates"
    selected: list[dict[str, Any]] = []
    for item in date_results:
        if item.get("status") != "OK":
            continue
        selected.extend((item.get(key) or [])[:top_n])
    return selected


def _comparison(date_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        f"top{top_n}": {
            CURRENT: _metrics(_select_top(date_results, CURRENT, top_n)),
            FROZEN_REFINED: _metrics(_select_top(date_results, FROZEN_REFINED, top_n)),
        }
        for top_n in (1, 3, 5)
    }


def _ranking_impact(date_results: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [item for item in date_results if item.get("status") == "OK"]
    top1 = top3_membership = top3_order = top5_membership = 0
    moves: list[int] = []
    max_move = 0
    for item in valid:
        current = item.get("current_candidates") or []
        refined = item.get("refined_candidates") or []
        current_codes = [_code(row) for row in current]
        refined_codes = [_code(row) for row in refined]
        top1 += int(current_codes[:1] != refined_codes[:1])
        top3_membership += int(set(current_codes[:3]) != set(refined_codes[:3]))
        top3_order += int(current_codes[:3] != refined_codes[:3])
        top5_membership += int(set(current_codes[:5]) != set(refined_codes[:5]))
        refined_pos = {_row_key(row): index + 1 for index, row in enumerate(refined)}
        for index, row in enumerate(current, start=1):
            move = abs(int(refined_pos.get(_row_key(row), index)) - index)
            moves.append(move)
            max_move = max(max_move, move)
    return {
        "checked_dates": len(valid),
        "top1_changed_dates": top1,
        "top3_membership_changed_dates": top3_membership,
        "top3_order_changed_dates": top3_order,
        "top5_membership_changed_dates": top5_membership,
        "mean_absolute_rank_move": _mean(moves),
        "max_absolute_rank_move": max_move,
        "overextended_candidates": sum(int((item.get("guard_meta") or {}).get("overextended_count") or 0) for item in valid),
        "refined_exception_opportunities": sum(int((item.get("guard_meta") or {}).get("refined_exception_opportunities") or 0) for item in valid),
        "refined_exception_used": sum(int((item.get("guard_meta") or {}).get("refined_exception_used") or 0) for item in valid),
        "actually_demoted_count": sum(int((item.get("guard_meta") or {}).get("actually_demoted_count") or 0) for item in valid),
    }


def _block_name(day: str) -> str:
    return str(day)[:4]


def _block_stability(date_results: list[dict[str, Any]]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    stable_count = 0
    for label, _start, _end in BLOCKS:
        subset = [item for item in date_results if item.get("status") == "OK" and _block_name(str(item.get("analysis_date") or "")) == label]
        comp = _comparison(subset).get("top3") or {}
        current = comp.get(CURRENT) or {}
        refined = comp.get(FROZEN_REFINED) or {}
        cur_return = _num(current.get("return_20d_mean"))
        ref_return = _num(refined.get("return_20d_mean"))
        cur_mae = _num(current.get("mae_20d_mean"))
        ref_mae = _num(refined.get("mae_20d_mean"))
        return_improved = cur_return is not None and ref_return is not None and ref_return > cur_return
        mae_improved = cur_mae is not None and ref_mae is not None and ref_mae > cur_mae
        stable = bool(subset and (return_improved or mae_improved))
        stable_count += int(stable)
        blocks.append({
            "block": label,
            "date_count": len(subset),
            "first_date": min((str(x.get("analysis_date")) for x in subset), default=None),
            "last_date": max((str(x.get("analysis_date")) for x in subset), default=None),
            "current_top3": current,
            "refined_top3": refined,
            "return20_improved": return_improved,
            "mae20_improved": mae_improved,
            "stable": stable,
        })
    return {"stable_block_count": stable_count, "block_count": len(BLOCKS), "blocks": blocks}


def _removed_top3(date_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    removed: list[dict[str, Any]] = []
    for item in date_results:
        if item.get("status") != "OK":
            continue
        current = item.get("current_candidates") or []
        refined = item.get("refined_candidates") or []
        refined_top3 = {_row_key(row) for row in refined[:3]}
        refined_rank = {_row_key(row): row.get("frozen_rank") for row in refined}
        for row in current[:3]:
            if _row_key(row) in refined_top3:
                continue
            removed.append({
                "analysis_date": item.get("analysis_date"),
                "code": row.get("code"),
                "name": row.get("name"),
                "strategy": row.get("strategy"),
                "current_rank": row.get("current_rank"),
                "refined_rank": refined_rank.get(_row_key(row)),
                "return_20d": row.get("return_20d"),
                "mae_20d": row.get("mae_20d"),
                "event_20d": row.get("event_20d"),
                "extreme_feature_count": row.get("extreme_feature_count"),
                "extreme_features": row.get("extreme_features") or [],
                "refined_exception": bool(row.get("refined_exception")),
            })
    return removed


def _large_move_examples(date_results: list[dict[str, Any]]) -> dict[str, Any]:
    removed = _removed_top3(date_results)
    avoided_large_losers = [
        row for row in removed
        if (_num(row.get("return_20d")) is not None and _num(row.get("return_20d")) <= -10.0)
        and str(row.get("event_20d") or "") == "STOP_FIRST"
        and (_num(row.get("mae_20d")) is not None and _num(row.get("mae_20d")) <= -15.0)
    ]
    demoted_large_winners = [
        row for row in removed
        if _num(row.get("return_20d")) is not None and _num(row.get("return_20d")) >= 10.0
    ]
    avoided_large_losers.sort(key=lambda row: (_num(row.get("return_20d")) or 0.0))
    demoted_large_winners.sort(key=lambda row: (_num(row.get("return_20d")) or 0.0), reverse=True)
    return {
        "removed_current_top3_count": len(removed),
        "avoided_large_loser_count": len(avoided_large_losers),
        "demoted_large_winner_count": len(demoted_large_winners),
        "avoided_large_losers": avoided_large_losers[:10],
        "demoted_large_winners": demoted_large_winners[:10],
    }


def _verdict(
    comparisons: dict[str, Any],
    ranking_impact: dict[str, Any],
    stability: dict[str, Any],
) -> tuple[str, list[str]]:
    sample_overextended = int(ranking_impact.get("overextended_candidates") or 0)
    sample_exceptions = int(ranking_impact.get("refined_exception_opportunities") or 0)
    if sample_overextended < MIN_OVEREXTENDED or sample_exceptions < MIN_EXCEPTION_OPPORTUNITIES:
        return VERDICT_INSUFFICIENT, [
            f"overextended sample {sample_overextended} (min {MIN_OVEREXTENDED})",
            f"refined exception opportunities {sample_exceptions} (min {MIN_EXCEPTION_OPPORTUNITIES})",
        ]

    top3 = comparisons.get("top3") or {}
    cur = top3.get(CURRENT) or {}
    ref = top3.get(FROZEN_REFINED) or {}

    def gt(key: str) -> bool:
        a, b = _num(ref.get(key)), _num(cur.get(key))
        return a is not None and b is not None and a > b

    def ge(key: str) -> bool:
        a, b = _num(ref.get(key)), _num(cur.get(key))
        return a is not None and b is not None and a >= b

    def le(key: str) -> bool:
        a, b = _num(ref.get(key)), _num(cur.get(key))
        return a is not None and b is not None and a <= b

    core = {
        "Top3 20D mean improved": gt("return_20d_mean"),
        "Top3 20D trimmed mean nonworse": ge("return_20d_trimmed_mean"),
        "Top3 20D mean without best nonworse": ge("return_20d_mean_without_best"),
        "Top3 MAE20 nonworse": ge("mae_20d_mean"),
        "Top3 Target1-first 20D nonworse": ge("target1_first_20d_rate"),
        "Top3 Stop-first 20D nonworse": le("stop_first_20d_rate"),
    }
    secondary = {
        "Top3 20D median improved": gt("return_20d_median"),
        "Top3 20D positive rate improved": gt("return_20d_positive_rate"),
        "Top3 10D mean improved": gt("return_10d_mean"),
        "Top3 Target1-first 10D improved": gt("target1_first_10d_rate"),
    }
    stable = int(stability.get("stable_block_count") or 0) >= MIN_BLOCKS_STABLE
    reasons = [label for label, passed in core.items() if passed]
    reasons.extend(label for label, passed in secondary.items() if passed)
    if stable:
        reasons.append(f"block stability {stability.get('stable_block_count')}/{stability.get('block_count')}")

    if all(core.values()) and any(secondary.values()) and stable:
        return VERDICT_PROMOTE, reasons

    clearly_worse = (
        not ge("return_20d_mean")
        and not ge("return_20d_trimmed_mean")
        and not ge("mae_20d_mean")
        and (not ge("target1_first_20d_rate") or not le("stop_first_20d_rate"))
    )
    if clearly_worse:
        return VERDICT_REJECT, ["Frozen refined guard failed the independent holdout on return/MAE and event quality"]
    return VERDICT_KEEP, reasons or ["Frozen refined guard did not clear all Production promotion gates"]


def run_final_confirmation(
    scanner: Any,
    market_store: Any,
    *,
    evaluation_dates: list[date],
    used_dates: set[date],
    market_scope: str = "ALL",
    progress: Any | None = None,
    frozen_rule_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_frozen_rule()
    ensure_scanner_version(getattr(scanner, "VERSION", None))
    overlap = sorted(set(evaluation_dates) & set(used_dates))
    if overlap:
        raise ValueError(f"HOLDOUT_OVERLAP: {[day.isoformat() for day in overlap]}")

    date_results: list[dict[str, Any]] = []
    for index, as_of in enumerate(evaluation_dates, start=1):
        result = run_frozen_date(scanner, market_store, as_of=as_of, market_scope=market_scope)
        date_results.append(result)
        if callable(progress):
            progress(index, len(evaluation_dates), result)

    valid = [item for item in date_results if item.get("status") == "OK"]
    missing = [item.get("analysis_date") for item in date_results if item.get("status") != "OK"]
    comparisons = _comparison(valid)
    ranking_impact = _ranking_impact(valid)
    stability = _block_stability(valid)
    examples = _large_move_examples(valid)
    verdict, reasons = _verdict(comparisons, ranking_impact, stability)

    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scanner_version": str(scanner.VERSION),
        "market_scope": market_scope,
        "production_changed": False,
        "guardrail": (
            "Frozen-rule independent holdout. No feature/threshold/exemption tuning is allowed. "
            "Current and frozen ranks are fixed before D+1 future rows are read."
        ),
        "frozen_rule": {
            "spec": FROZEN_RULE_SPEC,
            "fingerprint": EXPECTED_FROZEN_RULE_FINGERPRINT,
            "changed": False,
            "source": frozen_rule_source or {},
        },
        "holdout": {
            "evaluation_dates": [day.isoformat() for day in evaluation_dates],
            "requested_date_count": len(evaluation_dates),
            "valid_date_count": len(valid),
            "missing_dates": missing,
            "overlap_with_previous_73": 0,
            "min_trading_day_gap_from_previous": MIN_TRADING_DAY_GAP_FROM_USED,
            "date_fingerprint": hashlib.sha256("|".join(day.isoformat() for day in evaluation_dates).encode("utf-8")).hexdigest(),
        },
        "comparisons": comparisons,
        "ranking_impact": ranking_impact,
        "block_stability": stability,
        "examples": examples,
        "verdict": verdict,
        "verdict_reasons": reasons,
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
    end: date = date(2026, 8, 18),
) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5 and _is_complete_day(market_store, current):
            days.append(current)
        current += timedelta(days=1)
    return days


def _allocate_by_blocks(total: int) -> dict[str, int]:
    if total < len(BLOCKS):
        raise ValueError(f"sample size must be at least {len(BLOCKS)}")
    base, remainder = divmod(total, len(BLOCKS))
    return {label: base + (1 if index < remainder else 0) for index, (label, _s, _e) in enumerate(BLOCKS)}


def _spread_pick(candidates: list[date], count: int) -> list[date]:
    if count <= 0:
        return []
    if len(candidates) < count:
        raise ValueError(f"not enough eligible dates: need {count}, have {len(candidates)}")
    if count == 1:
        return [candidates[len(candidates) // 2]]
    selected: list[date] = []
    used_indices: set[int] = set()
    for i in range(count):
        index = round(i * (len(candidates) - 1) / (count - 1))
        if index in used_indices:
            for delta in range(1, len(candidates)):
                alternatives = (index - delta, index + delta)
                found = next((x for x in alternatives if 0 <= x < len(candidates) and x not in used_indices), None)
                if found is not None:
                    index = found
                    break
        used_indices.add(index)
        selected.append(candidates[index])
    return sorted(selected)


def _trading_index(calendar: list[date], day: date) -> int:
    index = bisect.bisect_left(calendar, day)
    if index < len(calendar) and calendar[index] == day:
        return index
    return index


def _far_from_used(calendar: list[date], candidate: date, used_dates: set[date], min_gap: int) -> bool:
    candidate_index = _trading_index(calendar, candidate)
    used_indices = sorted(_trading_index(calendar, day) for day in used_dates)
    pos = bisect.bisect_left(used_indices, candidate_index)
    for neighbor in (pos - 1, pos):
        if 0 <= neighbor < len(used_indices) and abs(candidate_index - used_indices[neighbor]) < min_gap:
            return False
    return True


def select_holdout_from_calendar(
    calendar: list[date],
    used_dates: set[date],
    *,
    sample_size: int = 20,
    existing_dates: list[date] | None = None,
    min_gap: int = MIN_TRADING_DAY_GAP_FROM_USED,
) -> list[date]:
    if len(calendar) < sample_size:
        raise ValueError("trading calendar is smaller than requested holdout")
    existing = sorted(set(existing_dates or []))
    if set(existing) & used_dates:
        raise ValueError("existing holdout dates overlap previous evaluation dates")
    for day in existing:
        if day not in calendar:
            raise ValueError(f"existing holdout date is not a complete trading date: {day.isoformat()}")
        if not _far_from_used(calendar, day, used_dates, min_gap):
            raise ValueError(f"existing holdout date violates min trading-day gap: {day.isoformat()}")

    allocation = _allocate_by_blocks(sample_size)
    selected = list(existing)
    selected_set = set(selected)
    for label, start, end in BLOCKS:
        desired = allocation[label]
        current_block = [day for day in selected if start <= day <= end]
        need = desired - len(current_block)
        if need <= 0:
            continue
        eligible = [
            day for day in calendar
            if start <= day <= end
            and day not in used_dates
            and day not in selected_set
            and _far_from_used(calendar, day, used_dates, min_gap)
        ]
        picks = _spread_pick(eligible, need)
        selected.extend(picks)
        selected_set.update(picks)
    selected = sorted(selected)
    if len(selected) != sample_size:
        raise ValueError(f"holdout selector produced {len(selected)} dates, expected {sample_size}")
    return selected


def used_dates_from_baseline(payload: dict[str, Any]) -> set[date]:
    result: set[date] = set()
    for row in payload.get("candidates") or []:
        value = str(row.get("analysis_date") or "")
        if value:
            result.add(date.fromisoformat(value))
    if len(result) < 73:
        raise ValueError(f"B.2.6-E expected at least 73 prior candidate dates, got {len(result)}")
    return result


def validate_d_source(payload: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("audit_version") or "") != EXPECTED_D_AUDIT_VERSION:
        raise ValueError(f"Expected {EXPECTED_D_AUDIT_VERSION}, got {payload.get('audit_version')!r}")
    if str(payload.get("verdict") or "") != EXPECTED_D_VERDICT:
        raise ValueError(f"B.2.6-D is not ready for confirmation: {payload.get('verdict')!r}")
    if bool(payload.get("production_changed")):
        raise ValueError("B.2.6-D unexpectedly reports Production changed=True")
    scanner = str((payload.get("current_validation_source") or {}).get("scanner_version") or "")
    if scanner != EXPECTED_SCANNER_VERSION:
        raise ValueError(f"B.2.6-D source scanner mismatch: {scanner!r}")
    return {
        "audit_version": payload.get("audit_version"),
        "verdict": payload.get("verdict"),
        "generated_at": payload.get("generated_at"),
        "scanner_version": scanner,
    }


def _fmt_pct(value: Any) -> str:
    number = _num(value)
    return "-" if number is None else f"{number:.2f}%"


def _fmt_rate(value: Any) -> str:
    number = _num(value)
    return "-" if number is None else f"{number * 100:.1f}%"


def _markdown(payload: dict[str, Any]) -> str:
    holdout = payload.get("holdout") or {}
    top3 = (payload.get("comparisons") or {}).get("top3") or {}
    cur = top3.get(CURRENT) or {}
    ref = top3.get(FROZEN_REFINED) or {}
    impact = payload.get("ranking_impact") or {}
    stability = payload.get("block_stability") or {}
    examples = payload.get("examples") or {}
    rule = payload.get("frozen_rule") or {}

    lines = [
        f"# Scanner Candidate Quality Frozen Rule Confirmation — {AUDIT_VERSION}",
        "",
        f"- verdict: **{payload.get('verdict')}**",
        f"- scanner: `{payload.get('scanner_version')}`",
        f"- holdout: `{holdout.get('valid_date_count')}/{holdout.get('requested_date_count')}`",
        f"- rule changed: **{rule.get('changed')}**",
        f"- Production changed: **{payload.get('production_changed')}**",
        f"- rule fingerprint: `{rule.get('fingerprint')}`",
        "",
        "## Primary — Top3",
        "",
        "| Metric | CURRENT | FROZEN_REFINED_GUARD |",
        "|---|---:|---:|",
        f"| 10D mean | {_fmt_pct(cur.get('return_10d_mean'))} | {_fmt_pct(ref.get('return_10d_mean'))} |",
        f"| 20D mean | {_fmt_pct(cur.get('return_20d_mean'))} | {_fmt_pct(ref.get('return_20d_mean'))} |",
        f"| 20D median | {_fmt_pct(cur.get('return_20d_median'))} | {_fmt_pct(ref.get('return_20d_median'))} |",
        f"| 20D trimmed mean | {_fmt_pct(cur.get('return_20d_trimmed_mean'))} | {_fmt_pct(ref.get('return_20d_trimmed_mean'))} |",
        f"| 20D mean without best | {_fmt_pct(cur.get('return_20d_mean_without_best'))} | {_fmt_pct(ref.get('return_20d_mean_without_best'))} |",
        f"| 20D positive | {_fmt_rate(cur.get('return_20d_positive_rate'))} | {_fmt_rate(ref.get('return_20d_positive_rate'))} |",
        f"| Target1-first 10D | {_fmt_rate(cur.get('target1_first_10d_rate'))} | {_fmt_rate(ref.get('target1_first_10d_rate'))} |",
        f"| Target1-first 20D | {_fmt_rate(cur.get('target1_first_20d_rate'))} | {_fmt_rate(ref.get('target1_first_20d_rate'))} |",
        f"| Stop-first 20D | {_fmt_rate(cur.get('stop_first_20d_rate'))} | {_fmt_rate(ref.get('stop_first_20d_rate'))} |",
        f"| MFE20 | {_fmt_pct(cur.get('mfe_20d_mean'))} | {_fmt_pct(ref.get('mfe_20d_mean'))} |",
        f"| MAE20 | {_fmt_pct(cur.get('mae_20d_mean'))} | {_fmt_pct(ref.get('mae_20d_mean'))} |",
        "",
        "## Frozen-rule sample / ranking impact",
        "",
        f"- Overextended candidates: `{impact.get('overextended_candidates')}`",
        f"- Refined exception opportunities: `{impact.get('refined_exception_opportunities')}`",
        f"- Refined exceptions used: `{impact.get('refined_exception_used')}`",
        f"- Actually demoted: `{impact.get('actually_demoted_count')}`",
        f"- Top1 changed dates: `{impact.get('top1_changed_dates')}`",
        f"- Top3 membership changed dates: `{impact.get('top3_membership_changed_dates')}`",
        f"- Top3 order changed dates: `{impact.get('top3_order_changed_dates')}`",
        f"- Stable blocks: `{stability.get('stable_block_count')}/{stability.get('block_count')}`",
        "",
        "## Large-move sanity",
        "",
        f"- Avoided large losers: `{examples.get('avoided_large_loser_count')}`",
        f"- Demoted large winners: `{examples.get('demoted_large_winner_count')}`",
        "",
        "## Decision reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in (payload.get("verdict_reasons") or []))
    lines += [
        "",
        "> B.2.6-E is an independent frozen-rule holdout. The rule, Q75 threshold, feature family and trend_recovery exact-2-of-3 exemption are not tuned in this step.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_dir / f"scanner-candidate-quality-final_{stamp}"
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")

    fields = [
        "analysis_date", "market", "code", "name", "strategy", "candidate_state",
        "current_rank", "frozen_rank", "overextended", "extreme_feature_count",
        "refined_exception", "frozen_demoted", "relative_strength_market_pct",
        "price_vs_ma20_pct", "ma20_vs_ma60_pct", "return_5d", "return_10d",
        "return_20d", "mfe_20d", "mae_20d", "event_10d", "event_20d",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in payload.get("dates") or []:
            for row in item.get("current_candidates") or []:
                writer.writerow({key: row.get(key) for key in fields})

    return {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}
