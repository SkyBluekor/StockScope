from __future__ import annotations

from app.backtest.target1_audit import (
    TARGET1_POLICY_BASELINE,
    TARGET1_POLICY_CAP_1_5R,
    TARGET1_POLICY_FIXED_1_5R,
    build_current_target1_audit,
    build_historical_target1_audit,
)


def _plan(**overrides):
    base = {
        "entry_price": 100.0,
        "invalidation_price": 95.0,
        "target1_price": 107.0,
        "target1_basis": "최근 저항 후보",
        "target2_price": 110.0,
        "target2_basis": "2R 이상 확장 시나리오",
    }
    base.update(overrides)
    return base


def test_current_audit_matches_nearest_structural_target_before_1_5r():
    audit = build_current_target1_audit(
        risk_plan=_plan(target1_price=106.0, target1_basis="최근 20일 고점"),
        data={"resistance_price": 112.0},
        technical={"high20": 106.0},
    )
    assert audit["formula_status"] == "MATCH"
    assert audit["expected_target1_price"] == 106.0
    assert audit["expected_target1_basis_code"] == "HIGH20"
    assert audit["one_half_r_price"] == 107.5
    assert audit["target1_gain_pct"] == 6.0
    assert audit["target1_r_multiple"] == 1.2


def test_current_audit_uses_1_5r_only_when_no_structural_target_above_entry():
    audit = build_current_target1_audit(
        risk_plan=_plan(target1_price=107.5, target1_basis="1.5R 손익 구조 참고"),
        data={"resistance_price": 99.0},
        technical={"high20": 98.0},
    )
    assert audit["formula_status"] == "MATCH"
    assert audit["expected_target1_basis_code"] == "RISK_1_5R"
    assert audit["expected_target1_price"] == 107.5


def test_current_audit_detects_formula_mismatch_without_changing_price():
    audit = build_current_target1_audit(
        risk_plan=_plan(target1_price=120.0, target1_basis="최근 저항 후보"),
        data={"resistance_price": 110.0},
        technical={"high20": 115.0},
    )
    assert audit["formula_status"] == "MISMATCH"
    assert audit["target1_price"] == 120.0
    assert audit["expected_target1_price"] == 107.5
    assert audit["expected_target1_basis_code"] == "RISK_1_5R_CAP"


def test_observed_scanner_target_distance_math_is_reproducible():
    # 2026-09-17 user screen observations. This checks distance math only;
    # it deliberately does not assert an unseen target basis from the screenshot.
    observed = [
        ("현대해상", 48_500, 52_500, 8.2474),
        ("코스맥스", 280_500, 306_500, 9.2692),
        ("한화엔진", 48_050, 50_800, 5.7232),
        ("비에이치아이", 63_200, 66_800, 5.6962),
        ("삼성SDI", 544_000, 574_000, 5.5147),
        ("한국금융지주", 186_900, 194_600, 4.1199),
        ("포스코인터내셔널", 54_800, 56_700, 3.4672),
        ("이수페타시스", 107_600, 115_800, 7.6208),
        ("대한항공", 29_050, 30_900, 6.3683),
        ("대우건설", 18_570, 21_300, 14.7011),
        ("기업은행", 20_200, 21_050, 4.2079),
        ("두산에너빌리티", 83_800, 89_100, 6.3246),
        ("메리츠금융지주", 125_000, 139_100, 11.28),
        ("한국콜마", 150_000, 165_900, 10.6),
        ("DB손해보험", 187_000, 208_000, 11.2299),
    ]
    for _name, current, target, expected in observed:
        audit = build_current_target1_audit(
            risk_plan={
                "entry_price": current,
                "invalidation_price": current * 0.95,
                "target1_price": target,
                "target1_basis": "최근 저항 후보",
                "target2_price": target * 1.03,
            },
            data={"resistance_price": target},
            technical={"high20": target * 1.05},
        )
        assert abs(audit["target1_gain_pct"] - expected) < 0.01


def _row(day: int, *, open_: float, high: float, low: float, close: float):
    return {
        "date": f"202601{day:02d}",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    }


def test_historical_target1_audit_replays_baseline_and_1_5r_without_mutating_baseline():
    rows = [
        _row(2, open_=100, high=102, low=99, close=101),
        _row(3, open_=101, high=107.6, low=100, close=107),  # 1.5R 107.5 hit, structural 120 not hit
        _row(4, open_=107, high=110, low=106, close=109),
        _row(5, open_=109, high=121, low=108, close=120),   # baseline structural target hit on day 4
        _row(6, open_=120, high=121, low=119, close=120),
        _row(7, open_=120, high=121, low=119, close=120),
    ]
    trades = [{
        "entry_date": "20260102",
        "entry_price": 100.0,
        "stop_price": 95.0,
        "target1_price": 120.0,
        "metadata": {"audit": {"target1": {"basis": "최근 저항 후보", "price": 120.0}}},
    }]
    audit = build_historical_target1_audit(
        trades=trades,
        stock_rows=rows,
        max_holding_days=5,
        round_trip_cost_pct=0.0,
    )
    assert audit["available"] is True
    assert audit["sample_count"] == 1
    assert audit["average_target_distance_pct"] == 20.0
    assert audit["average_target_r_multiple"] == 4.0
    policies = {row["policy_id"]: row for row in audit["policy_comparison"]}
    assert policies[TARGET1_POLICY_BASELINE]["target_hit_count"] == 1
    assert policies[TARGET1_POLICY_BASELINE]["average_target_hit_days"] == 4.0
    assert policies[TARGET1_POLICY_CAP_1_5R]["target_hit_count"] == 1
    assert policies[TARGET1_POLICY_CAP_1_5R]["average_target_hit_days"] == 2.0
    assert policies[TARGET1_POLICY_FIXED_1_5R]["target_hit_count"] == 1
    assert policies[TARGET1_POLICY_FIXED_1_5R]["average_target_hit_days"] == 2.0
    # Research replay does not rewrite the original trade target.
    assert trades[0]["target1_price"] == 120.0


def test_historical_audit_keeps_same_day_stop_priority():
    rows = [_row(2, open_=100, high=121, low=94, close=110)]
    trades = [{
        "entry_date": "20260102",
        "entry_price": 100.0,
        "stop_price": 95.0,
        "target1_price": 120.0,
        "metadata": {"audit": {"target1": {"basis": "최근 저항 후보"}}},
    }]
    audit = build_historical_target1_audit(trades=trades, stock_rows=rows, max_holding_days=20)
    policies = {row["policy_id"]: row for row in audit["policy_comparison"]}
    assert policies[TARGET1_POLICY_BASELINE]["stop_first_count"] == 1
    assert policies[TARGET1_POLICY_BASELINE]["target_hit_count"] == 0
    assert policies[TARGET1_POLICY_FIXED_1_5R]["stop_first_count"] == 1
    assert policies[TARGET1_POLICY_FIXED_1_5R]["target_hit_count"] == 0
