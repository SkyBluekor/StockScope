from __future__ import annotations

from datetime import date

from app.backtest.target1_realism_validation import (
    POLICY_CAP_1_5R,
    POLICY_CURRENT,
    POLICY_FIXED_1_5R,
    _event_for_horizon,
    aggregate_audit,
    build_target_variants,
    classify_target_source,
    distance_bucket,
    evaluate_signal,
    r_bucket,
)


def test_hanmi_like_target_variants_keep_current_and_build_1_5r_alternatives():
    variants = build_target_variants(entry=48_500.0, stop=46_025.04, current_target=61_000.0)
    assert variants[POLICY_CURRENT] == 61_000.0
    assert abs(variants[POLICY_CAP_1_5R] - 52_212.44) < 0.01
    assert abs(variants[POLICY_FIXED_1_5R] - 52_212.44) < 0.01


def test_distance_and_r_buckets_match_extreme_case():
    assert distance_bucket(25.7732) == "20%+"
    assert r_bucket(5.0506) == "4R+"
    assert distance_bucket(9.999) == "5~10%"
    assert r_bucket(1.5) == "<=1.5R"


def test_source_marks_resistance_and_high20_when_same_selected_price():
    risk_plan = {
        "target1_basis": "최근 저항 후보",
        "target1_audit": {
            "target1_basis_code": "RESISTANCE",
            "structural_candidates": [
                {"kind": "RESISTANCE", "price": 61_000.0, "selected": True},
                {"kind": "HIGH20", "price": 61_000.0, "selected": True},
                {"kind": "RISK_1_5R", "price": 52_212.44, "selected": False},
            ],
        },
    }
    source = classify_target_source(risk_plan)
    assert source["source"] == "RESISTANCE_AND_HIGH20"
    assert source["resistance_price"] == 61_000.0
    assert source["high20"] == 61_000.0


def test_same_bar_is_stop_first_primary_and_target_first_sensitivity():
    rows = [{"date": "20260921", "high": 110.0, "low": 94.0, "close": 105.0}]
    result = _event_for_horizon(rows, target=107.5, stop=95.0, horizon=1)
    assert result["raw_status"] == "AMBIGUOUS_SAME_BAR"
    assert result["primary_status"] == "STOP_FIRST"
    assert result["sensitivity_status"] == "TARGET1_FIRST"


def test_evaluate_signal_changes_only_target_policy_not_entry_or_stop():
    candidate = {
        "market": "KOSPI",
        "code": "008930",
        "name": "한미사이언스",
        "strategy": "support_bounce",
        "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE",
        "current_price": 48_500.0,
        "entry_risk_guide": {
            "risk": {
                "entry_reference_price": 48_500.0,
                "invalidation_price": 46_025.04,
                "target1_price": 61_000.0,
                "target1_basis": "최근 저항 후보",
                "target1_audit": {
                    "target1_basis_code": "RESISTANCE",
                    "structural_candidates": [
                        {"kind": "RESISTANCE", "price": 61_000.0, "selected": True},
                        {"kind": "HIGH20", "price": 61_000.0, "selected": True},
                    ],
                },
            }
        },
        "_audit_rank": 1,
    }
    future = [
        {"date": "20260921", "high": 52_500.0, "low": 47_000.0, "close": 52_000.0},
        {"date": "20260922", "high": 53_000.0, "low": 51_000.0, "close": 52_500.0},
        {"date": "20260923", "high": 53_500.0, "low": 52_000.0, "close": 53_000.0},
        {"date": "20260924", "high": 54_000.0, "low": 52_500.0, "close": 53_500.0},
        {"date": "20260925", "high": 54_500.0, "low": 53_000.0, "close": 54_000.0},
    ]
    signal = evaluate_signal(candidate=candidate, future_rows=future, analysis_date=date(2026, 9, 18), horizons=(5,))
    assert signal is not None
    assert signal["entry_reference_price"] == 48_500.0
    assert signal["invalidation_price"] == 46_025.04
    assert signal["distance_bucket"] == "20%+"
    assert signal["r_bucket"] == "4R+"
    assert signal["target_source"]["source"] == "RESISTANCE_AND_HIGH20"
    assert signal["policies"][POLICY_CURRENT]["forward"]["5"]["primary_status"] == "NO_EVENT"
    assert signal["policies"][POLICY_CAP_1_5R]["forward"]["5"]["primary_status"] == "TARGET1_FIRST"
    assert signal["policies"][POLICY_FIXED_1_5R]["forward"]["5"]["primary_status"] == "TARGET1_FIRST"


def test_smoke_aggregate_reports_policy_transitions_without_mutating_signals():
    base = {
        "distance_bucket": "20%+",
        "r_bucket": "4R+",
        "current_target1_distance_pct": 25.0,
        "current_target1_r_multiple": 5.0,
        "target_source": {"source": "RESISTANCE_AND_HIGH20"},
        "policies": {
            POLICY_CURRENT: {"forward": {"5": {"complete": True, "primary_status": "NO_EVENT", "sensitivity_status": "NO_EVENT", "raw_status": "NO_EVENT"}, "10": {"complete": True, "primary_status": "NO_EVENT", "sensitivity_status": "NO_EVENT", "raw_status": "NO_EVENT"}, "20": {"complete": True, "primary_status": "NO_EVENT", "sensitivity_status": "NO_EVENT", "raw_status": "NO_EVENT"}}},
            POLICY_CAP_1_5R: {"forward": {"5": {"complete": True, "primary_status": "TARGET1_FIRST", "sensitivity_status": "TARGET1_FIRST", "raw_status": "TARGET1_FIRST", "day": 3}, "10": {"complete": True, "primary_status": "TARGET1_FIRST", "sensitivity_status": "TARGET1_FIRST", "raw_status": "TARGET1_FIRST", "day": 3}, "20": {"complete": True, "primary_status": "TARGET1_FIRST", "sensitivity_status": "TARGET1_FIRST", "raw_status": "TARGET1_FIRST", "day": 3}}},
            POLICY_FIXED_1_5R: {"forward": {"5": {"complete": True, "primary_status": "TARGET1_FIRST", "sensitivity_status": "TARGET1_FIRST", "raw_status": "TARGET1_FIRST", "day": 3}, "10": {"complete": True, "primary_status": "TARGET1_FIRST", "sensitivity_status": "TARGET1_FIRST", "raw_status": "TARGET1_FIRST", "day": 3}, "20": {"complete": True, "primary_status": "TARGET1_FIRST", "sensitivity_status": "TARGET1_FIRST", "raw_status": "TARGET1_FIRST", "day": 3}}},
        },
    }
    signals = [dict(base) for _ in range(30)]
    aggregate = aggregate_audit(signals, valid_dates=20, requested_dates=20)
    assert aggregate["policy_summary"][POLICY_CURRENT]["20"]["target1_first_pct"] == 0.0
    assert aggregate["policy_summary"][POLICY_CAP_1_5R]["20"]["target1_first_pct"] == 100.0
    assert aggregate["current_to_cap_transitions_20d"]["NO_EVENT->TARGET1_FIRST"] == 30
    assert aggregate["smoke_verdict"] == "CAP_1_5R_REVIEW"
