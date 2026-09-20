from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

from app.backtest.scanner_quality.entry_stability_audit import (
    FEATURES,
    add_same_date_quartile_bands,
    apply_rule,
    choose_verdict,
    compute_entry_stability_features,
    label_for_event,
    smoke_rules,
)


def _history(days: int = 40) -> list[dict]:
    start = date(2026, 1, 1)
    rows: list[dict] = []
    close = 100.0
    for i in range(days):
        day = start + timedelta(days=i)
        close *= 1.0 + (0.01 if i % 3 == 0 else -0.002)
        rows.append(
            {
                "date": day.isoformat(),
                "open": close - 1.0,
                "high": close + 2.0,
                "low": close - 2.0,
                "close": close,
                "volume": 1000 + i * 10,
            }
        )
    return rows


def test_features_ignore_future_rows() -> None:
    rows = _history(40)
    as_of = date(2026, 2, 4)
    baseline = compute_entry_stability_features(rows, as_of=as_of)
    changed = deepcopy(rows)
    changed.append(
        {
            "date": "2026-12-31",
            "open": 1,
            "high": 9999,
            "low": 1,
            "close": 9999,
            "volume": 99999999,
        }
    )
    assert compute_entry_stability_features(changed, as_of=as_of) == baseline


def test_feature_family_is_present_and_finite_on_normal_history() -> None:
    result = compute_entry_stability_features(_history(40), as_of=date(2026, 2, 9))
    assert set(result) == set(FEATURES)
    assert all(result[name] is not None for name in FEATURES)
    assert 0.0 <= float(result["close_location"]) <= 1.0
    assert float(result["atr14_pct"]) > 0.0
    assert float(result["return_std_20d_pct"]) >= 0.0
    assert float(result["max_drawdown_20d_pct"]) <= 0.0


def test_no_event_is_not_collapsed_into_good_or_bad() -> None:
    assert label_for_event("TARGET1_FIRST") == "GOOD_ENTRY"
    assert label_for_event("STOP_FIRST") == "BAD_ENTRY"
    assert label_for_event("NO_EVENT") == "NO_EVENT"
    assert label_for_event(None) == "NO_EVENT"


def test_same_date_quartile_bands_are_deterministic() -> None:
    rows = []
    for i in range(8):
        row = {"analysis_date": "2026-01-02", "rank": i + 1, "code": f"{i:06d}"}
        for j, feature in enumerate(FEATURES):
            row[feature] = float(i + j)
        rows.append(row)
    first = deepcopy(rows)
    second = deepcopy(rows)
    assert add_same_date_quartile_bands(first) == add_same_date_quartile_bands(second)
    assert [row["atr14_pct_band"] for row in first] == [row["atr14_pct_band"] for row in second]


def test_rule_demotes_only_selected_band_and_preserves_internal_order() -> None:
    rows = [
        {"rank": 1, "code": "A", "atr14_pct_band": "MID"},
        {"rank": 2, "code": "B", "atr14_pct_band": "HIGH"},
        {"rank": 3, "code": "C", "atr14_pct_band": "LOW"},
        {"rank": 4, "code": "D", "atr14_pct_band": "HIGH"},
    ]
    out = apply_rule(rows, {"feature": "atr14_pct", "band": "HIGH"})
    assert [row["code"] for row in out] == ["A", "C", "B", "D"]
    assert [row["research_rank"] for row in out] == [1, 2, 3, 4]


def test_future_outcomes_do_not_change_research_ranking() -> None:
    rows = [
        {"rank": 1, "code": "A", "atr14_pct_band": "MID", "return_20d": -10, "event_20d": "STOP_FIRST"},
        {"rank": 2, "code": "B", "atr14_pct_band": "HIGH", "return_20d": 20, "event_20d": "TARGET1_FIRST"},
        {"rank": 3, "code": "C", "atr14_pct_band": "LOW", "return_20d": 0, "event_20d": "NO_EVENT"},
    ]
    rule = {"feature": "atr14_pct", "band": "HIGH"}
    first = [row["code"] for row in apply_rule(rows, rule)]
    mutated = deepcopy(rows)
    for row in mutated:
        row["return_20d"] = -9999 if row["code"] == "A" else 9999
        row["event_20d"] = "TARGET1_FIRST" if row["event_20d"] != "TARGET1_FIRST" else "STOP_FIRST"
    second = [row["code"] for row in apply_rule(mutated, rule)]
    assert first == second


def test_promising_verdict_requires_both_primary_event_rates() -> None:
    rules = [{"rule_id": "atr14_pct:HIGH"}]
    smoke = {
        "CURRENT": {
            "target1_first_20d_rate": 0.40,
            "stop_first_20d_rate": 0.50,
            "return_20d_mean": 1.0,
            "mae_20d_mean": -10.0,
        },
        "atr14_pct:HIGH": {
            "target1_first_20d_rate": 0.45,
            "stop_first_20d_rate": 0.45,
            "return_20d_mean": 0.5,
            "mae_20d_mean": -9.0,
        },
    }
    verdict, _ = choose_verdict(smoke, rules)
    assert verdict == "PROMISING_ENTRY_STABILITY_SIGNAL"


def test_smoke_rule_keeps_date_membership_and_uses_top3_only() -> None:
    rows = []
    for day in ("2026-01-02", "2026-01-03"):
        for i in range(4):
            rows.append(
                {
                    "analysis_date": day,
                    "rank": i + 1,
                    "code": f"{day}-{i}",
                    "atr14_pct_band": "HIGH" if i == 0 else "MID",
                    "label_20d": "BAD_ENTRY" if i == 0 else "GOOD_ENTRY",
                    "return_20d": 1.0,
                    "mfe_20d": 2.0,
                    "mae_20d": -1.0,
                }
            )
    result = smoke_rules(rows, [{"rule_id": "atr14_pct:HIGH", "feature": "atr14_pct", "band": "HIGH"}])
    assert result["CURRENT"]["count"] == 6
    assert result["atr14_pct:HIGH"]["count"] == 6
    assert result["atr14_pct:HIGH"]["top3_changed_dates"] == 2
