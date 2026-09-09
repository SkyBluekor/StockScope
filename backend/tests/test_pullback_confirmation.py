from app.market.pullback_confirmation import PullbackConfirmationAnalyzer


def make_history(count: int = 40, *, falling_last: bool = False):
    rows = []
    price = 100.0
    for i in range(count):
        price += 1.0
        if falling_last and i >= count - 4:
            price -= 1.8
        rows.append({
            "date": f"202601{(i % 28) + 1:02d}",
            "open": price - 0.5,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "volume": 1_000_000,
        })
    return rows


def base_technical():
    return {
        "support": 132.0,
        "distance_to_20d_high_pct": 5.0,
        "ma20_slope_pct": 0.8,
        "higher_low": True,
    }


def test_support_failed_is_not_called_pullback():
    result = PullbackConfirmationAnalyzer.analyze(
        history=make_history(),
        technical=base_technical(),
        current_price=128.0,
        current_ma20=133.0,
        current_rsi14=45.0,
        current_volume_ratio=1.1,
        source="USER_INPUT",
        position_mode="NOT_HELD",
        reference_low=127.0,
        reference_high=134.0,
        reference_volume=900_000,
    )
    assert result["state"] == "SUPPORT_FAILED"
    assert "보류" in result["new_entry"]["action"]


def test_intraday_support_test_stays_unconfirmed_without_low():
    result = PullbackConfirmationAnalyzer.analyze(
        history=make_history(),
        technical=base_technical(),
        current_price=133.0,
        current_ma20=132.5,
        current_rsi14=50.0,
        current_volume_ratio=0.9,
        source="USER_INPUT",
        position_mode="NOT_HELD",
    )
    assert result["state"] in {"SUPPORT_TESTING", "SUPPORT_APPROACH"}
    support_check = next(item for item in result["checks"] if item["key"] == "support_hold")
    assert support_check["status"] in {"WARN", "UNKNOWN"}
    assert result["confirmed"] is False


def test_confirmed_eod_can_mark_rebound():
    history = make_history()
    # Make the latest candle explicitly test support and close green above it.
    history[-1].update({"open": 131.0, "low": 131.5, "high": 136.0, "close": 135.0})
    result = PullbackConfirmationAnalyzer.analyze(
        history=history,
        technical={
            "support": 132.0,
            "distance_to_20d_high_pct": 5.0,
            "ma20_slope_pct": 0.8,
            "higher_low": True,
        },
        current_price=135.0,
        current_ma20=132.5,
        current_rsi14=55.0,
        current_volume_ratio=1.2,
        source="KRX_EOD",
        position_mode="NOT_HELD",
    )
    assert result["state"] in {"REBOUND_CONFIRMED", "SUPPORT_TESTING"}
    if result["state"] == "REBOUND_CONFIRMED":
        assert result["confirmed"] is True
