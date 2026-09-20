from __future__ import annotations

import pytest

from app.backtest.scanner_quality.candidate_quality_validation import (
    CURRENT,
    EXPECTED_SCANNER_VERSION,
    OVEREXTENSION,
    VERDICT_KEEP,
    VERDICT_PROMOTE,
    aggregate_validation,
    apply_overextension_guard,
    ensure_scanner_version,
)


def _row(code: str, rank: int, *, state: str = "READY", rs: float = 0, p20: float = 0, m2060: float = 0, ret: float = 0, mae: float = -2, event: str = "NO_EVENT") -> dict:
    return {
        "analysis_date": "2026-01-02",
        "code": code,
        "name": code,
        "current_rank": rank,
        "candidate_state": state,
        "relative_strength_market_pct": rs,
        "price_vs_ma20_pct": p20,
        "ma20_vs_ma60_pct": m2060,
        "return_5d": ret / 4,
        "return_10d": ret / 2,
        "return_20d": ret,
        "mfe_20d": max(ret, 1),
        "mae_20d": mae,
        "event_10d": event,
        "event_20d": event,
    }


def test_scanner_version_guard_rejects_stale_source():
    ensure_scanner_version(EXPECTED_SCANNER_VERSION)
    with pytest.raises(RuntimeError, match="STALE_SOURCE"):
        ensure_scanner_version("0.21.3.6")


def test_guard_requires_two_q75_extremes_and_keeps_current_order_inside_groups():
    rows = [
        _row("A", 1, rs=100, p20=100, m2060=100),
        _row("B", 2, rs=1, p20=1, m2060=1),
        _row("C", 3, rs=2, p20=2, m2060=2),
        _row("D", 4, rs=3, p20=3, m2060=3),
    ]
    ranked, meta = apply_overextension_guard(rows)
    assert [row["code"] for row in ranked] == ["B", "C", "D", "A"]
    assert meta["overextended_count"] == 1
    assert ranked[-1]["extreme_feature_count"] == 3


def test_guard_never_promotes_watch_across_ready_slots():
    rows = [
        _row("A", 1, state="READY", rs=100, p20=100, m2060=100),
        _row("W", 2, state="WATCH", rs=0, p20=0, m2060=0),
        _row("B", 3, state="READY", rs=1, p20=1, m2060=1),
        _row("C", 4, state="READY", rs=2, p20=2, m2060=2),
        _row("D", 5, state="READY", rs=3, p20=3, m2060=3),
    ]
    ranked, _ = apply_overextension_guard(rows)
    assert ranked[1]["code"] == "W"
    assert ranked[1]["candidate_state"] == "WATCH"


def test_future_outcome_mutation_cannot_change_guard_ranking():
    rows = [
        _row("A", 1, rs=100, p20=100, m2060=100, ret=-99),
        _row("B", 2, rs=1, p20=1, m2060=1, ret=99),
        _row("C", 3, rs=2, p20=2, m2060=2, ret=50),
        _row("D", 4, rs=3, p20=3, m2060=3, ret=10),
    ]
    before = [row["code"] for row in apply_overextension_guard(rows)[0]]
    for row in rows:
        row["return_20d"] = -float(row["return_20d"])
        row["event_20d"] = "TARGET1_FIRST" if row["event_20d"] != "TARGET1_FIRST" else "STOP_FIRST"
    after = [row["code"] for row in apply_overextension_guard(rows)[0]]
    assert before == after


def _date_result(day: int, bad_first: bool = True) -> dict:
    date = f"2026-01-{day:02d}"
    rows = [
        _row("A", 1, rs=100, p20=100, m2060=100, ret=(-8 if bad_first else 8), mae=(-9 if bad_first else -2), event=("STOP_FIRST" if bad_first else "TARGET1_FIRST")),
        _row("B", 2, rs=1, p20=1, m2060=1, ret=4, mae=-2, event="TARGET1_FIRST"),
        _row("C", 3, rs=2, p20=2, m2060=2, ret=3, mae=-2, event="TARGET1_FIRST"),
        _row("D", 4, rs=3, p20=3, m2060=3, ret=2, mae=-2, event="TARGET1_FIRST"),
    ]
    for row in rows:
        row["analysis_date"] = date
    guard, meta = apply_overextension_guard(rows)
    guard_map = {row["code"]: row for row in guard}
    for row in rows:
        row["guard_rank"] = guard_map[row["code"]]["guard_rank"]
        row["overextended"] = guard_map[row["code"]]["overextended"]
        row["extreme_features"] = guard_map[row["code"]]["extreme_features"]
    return {
        "analysis_date": date,
        "status": "OK",
        "guard_meta": meta,
        "current_candidates": sorted(rows, key=lambda x: x["current_rank"]),
        "guard_candidates": sorted(rows, key=lambda x: x["guard_rank"]),
    }


def test_aggregate_can_promote_when_guard_improves_robust_top3_metrics():
    payload = aggregate_validation([_date_result(day) for day in range(2, 8)])
    assert payload["verdict"] == VERDICT_PROMOTE
    assert payload["comparisons"]["top3"][OVEREXTENSION]["return_20d_mean"] > payload["comparisons"]["top3"][CURRENT]["return_20d_mean"]


def test_aggregate_keeps_research_only_when_no_ranking_change():
    results = []
    for day in range(2, 8):
        rows = [
            _row("A", 1, rs=1, p20=1, m2060=1, ret=1),
            _row("B", 2, rs=1, p20=1, m2060=1, ret=1),
            _row("C", 3, rs=1, p20=1, m2060=1, ret=1),
        ]
        for row in rows:
            row["analysis_date"] = f"2026-01-{day:02d}"
        guard, meta = apply_overextension_guard(rows)
        results.append({"analysis_date": f"2026-01-{day:02d}", "status": "OK", "guard_meta": meta, "current_candidates": rows, "guard_candidates": guard})
    payload = aggregate_validation(results)
    assert payload["verdict"] == VERDICT_KEEP
