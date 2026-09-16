from __future__ import annotations

from app.backtest.production_exit_policy import ProductionExitPolicyEngine, ProductionExitPolicyResolution


def test_baseline_metadata_marks_target2_as_reference_only() -> None:
    row = ProductionExitPolicyEngine.historical_policy_metadata(
        ProductionExitPolicyResolution(strategy="TREND_FOLLOWING")
    )
    assert row["policy_id"] == "TARGET1_FULL_EXIT"
    assert row["target1_is_exit"] is True
    assert row["target2_included"] is False
    assert row["profit_protection"]["enabled"] is False
    assert row["profit_protection"]["state"] == "NOT_APPLICABLE"
    assert row["profit_protection"]["current_protection_price"] is None


def test_tracking_metadata_never_invents_current_protection_price() -> None:
    row = ProductionExitPolicyEngine.historical_policy_metadata(
        ProductionExitPolicyResolution(
            strategy="BREAKOUT",
            policy_id="ATR_TRAIL_2_0",
            holding_policy="TRAILING_HORIZON_AFTER_TARGET2",
            policy_source="VALIDATED_PRODUCTION_MAPPING",
            fallback_used=False,
            fallback_reason=None,
        )
    )
    assert row["target1_is_exit"] is False
    assert row["target2_included"] is True
    assert row["profit_protection"]["enabled"] is True
    assert row["profit_protection"]["activation"] == "AFTER_TARGET2"
    assert row["profit_protection"]["state"] == "POSITION_CONTEXT_REQUIRED"
    assert row["profit_protection"]["current_protection_price"] is None
    assert row["profit_protection"]["protection_never_decreases"] is True
