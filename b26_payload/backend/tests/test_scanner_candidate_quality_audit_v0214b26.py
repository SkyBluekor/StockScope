from __future__ import annotations

from app.backtest.scanner_quality.candidate_quality_audit import (
    CURRENT,
    OVEREXT_Q75,
    RISK_Q75,
    _sort_variant,
    run_candidate_quality_audit,
)


def _row(code: str, rank: int, *, risk: float, rs: float, p20: float, m2060: float, ret20: float) -> dict:
    return {
        "analysis_date": "2026-01-02",
        "code": code,
        "rank": rank,
        "risk_pct": risk,
        "structural_target_distance_pct": 5.0 + rank,
        "relative_strength_market_pct": rs,
        "price_vs_ma20_pct": p20,
        "ma20_vs_ma60_pct": m2060,
        "ma60_vs_ma120_pct": 2.0,
        "return_5d": ret20 / 3,
        "return_10d": ret20 / 2,
        "return_20d": ret20,
        "mfe_20d": max(ret20, 1.0),
        "mae_20d": min(ret20, -1.0),
    }


def test_current_order_is_unchanged():
    rows = [
        _row("000003", 3, risk=2, rs=1, p20=1, m2060=1, ret20=1),
        _row("000001", 1, risk=6, rs=8, p20=8, m2060=8, ret20=-1),
        _row("000002", 2, risk=3, rs=2, p20=2, m2060=2, ret20=2),
    ]
    assert [row["code"] for row in _sort_variant(rows, CURRENT)] == ["000001", "000002", "000003"]


def test_risk_guard_only_demotes_top_quartile_risk():
    rows = [
        _row("000001", 1, risk=10, rs=1, p20=1, m2060=1, ret20=-5),
        _row("000002", 2, risk=2, rs=2, p20=2, m2060=2, ret20=2),
        _row("000003", 3, risk=3, rs=3, p20=3, m2060=3, ret20=1),
        _row("000004", 4, risk=4, rs=4, p20=4, m2060=4, ret20=0),
    ]
    ranked = _sort_variant(rows, RISK_Q75)
    assert ranked[-1]["code"] == "000001"
    assert [row["code"] for row in ranked[:3]] == ["000002", "000003", "000004"]


def test_overextension_guard_requires_two_extreme_signals():
    rows = [
        _row("000001", 1, risk=2, rs=20, p20=20, m2060=20, ret20=-5),
        _row("000002", 2, risk=2, rs=1, p20=1, m2060=1, ret20=2),
        _row("000003", 3, risk=2, rs=2, p20=2, m2060=2, ret20=1),
        _row("000004", 4, risk=2, rs=3, p20=3, m2060=3, ret20=0),
    ]
    ranked = _sort_variant(rows, OVEREXT_Q75)
    assert ranked[-1]["code"] == "000001"


def test_outcomes_do_not_participate_in_quality_sort():
    rows = [
        _row("000001", 1, risk=5, rs=8, p20=8, m2060=8, ret20=-99),
        _row("000002", 2, risk=2, rs=1, p20=1, m2060=1, ret20=99),
        _row("000003", 3, risk=3, rs=2, p20=2, m2060=2, ret20=50),
        _row("000004", 4, risk=4, rs=3, p20=3, m2060=3, ret20=10),
    ]
    before = [row["code"] for row in _sort_variant(rows, OVEREXT_Q75)]
    for row in rows:
        row["return_20d"] = -float(row["return_20d"])
        row["return_10d"] = -float(row["return_10d"])
        row["return_5d"] = -float(row["return_5d"])
    after = [row["code"] for row in _sort_variant(rows, OVEREXT_Q75)]
    assert before == after


def test_audit_never_claims_production_change():
    rows = []
    for date_index in range(4):
        date = f"2026-01-{date_index + 2:02d}"
        for i in range(1, 5):
            row = _row(f"{i:06d}", i, risk=float(i), rs=float(i), p20=float(i), m2060=float(i), ret20=float(5 - i))
            row["analysis_date"] = date
            rows.append(row)
    payload = run_candidate_quality_audit({"source": {"scanner_version": "test"}, "candidates": rows}, None, validation_dates=2)
    assert payload["production_changed"] is False
    assert payload["recommendation"]["production_change"] is False
