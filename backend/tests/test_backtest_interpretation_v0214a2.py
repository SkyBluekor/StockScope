from pathlib import Path
from types import SimpleNamespace

from app.backtest.entry_risk_guide import build_entry_risk_guide


def test_krx_display_prices_do_not_change_raw_risk_values():
    guide = build_entry_risk_guide(
        strategy="ma20_rebound",
        data=SimpleNamespace(current_price=474_000, ma20=471_600),
        technical={},
        condition_state={"conditions": []},
        risk_plan={
            "status": "READY",
            "reference_only": True,
            "entry_price": 474_000,
            "invalidation_price": 456_707,
            "target1_price": 495_500,
            "target2_price": 508_586,
            "risk_pct": 3.65,
            "reward1_pct": 4.54,
            "reward2_pct": 7.30,
            "rr1": 1.24,
            "rr2": 2.00,
        },
        current_state={"decision_reason": "ENTRY_CONDITIONS_MISSING"},
        historical_verified=True,
        historical_status="WEAK",
        as_of_date="2026-09-14",
    )
    risk = guide["risk"]
    assert risk["invalidation_price"] == 456_707
    assert risk["display_invalidation_price"] == 456_500
    assert risk["target1_price"] == 495_500
    assert risk["display_target1_price"] == 495_500
    assert risk["target2_price"] == 508_586
    assert risk["display_target2_price"] == 509_000
    assert risk["rr1"] == 1.24
    assert risk["rr2"] == 2.00


def test_historical_policy_marks_target2_as_reference_only_for_current_backtest():
    guide = build_entry_risk_guide(
        strategy="trend_following",
        data=SimpleNamespace(current_price=100_000),
        technical={},
        condition_state={"conditions": []},
        risk_plan=None,
        current_state={"decision_reason": "ENTRY_CONDITIONS_MISSING"},
        historical_verified=True,
        historical_status="FAIR",
    )
    policy = guide["historical_policy"]
    assert policy["policy_id"] == "TARGET1_FULL_EXIT_V1"
    assert policy["target1_is_exit"] is True
    assert policy["target2_included"] is False
    assert policy["target2_label"] == "2차 확장 목표"


def test_market_drop_copy_matches_actual_downtrend_and_panic_rule():
    selector_path = Path(__file__).resolve().parents[1] / "app" / "backtest" / "selector.py"
    source = selector_path.read_text(encoding="utf-8")
    assert '"시장 급락 아님": ("시장 흐름이 하락장이나 패닉 상태가 아니기"' in source
    assert "하락 추세이거나 패닉 상태" in source
