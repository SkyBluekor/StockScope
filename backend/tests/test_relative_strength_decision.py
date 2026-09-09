from app.market.relative_strength import RelativeStrengthAnalyzer


def period(days, excess, stock=0.0, market=0.0):
    return {
        "days": days,
        "available": True,
        "stock_return_pct": stock,
        "market_return_pct": market,
        "excess_return_pct": excess,
        "status": "STRONG" if excess >= 5 else "WEAK" if excess <= -5 else "NEUTRAL",
        "label": "테스트",
    }


def test_short_term_recovery_is_interpreted_as_result_not_just_number():
    result = RelativeStrengthAnalyzer._decision_result(
        periods=[
            period(5, 1.5, 3.2, 1.7),
            period(20, 6.8, 17.2, 10.4),
            period(60, -2.0, -16.4, -14.4),
        ],
        trend="STABLE",
        trend_label="유지",
        benchmark="코스피",
        position_mode="NOT_HELD",
    )
    assert result["archetype"] == "SHORT_TERM_RECOVERY"
    assert "추격" in result["new_entry"]["action"]
    assert result["preferred_strategies"]
    assert result["watch_points"]


def test_market_laggard_lowers_trend_breakout_priority():
    result = RelativeStrengthAnalyzer._decision_result(
        periods=[
            period(5, -2.0),
            period(20, -6.0),
            period(60, -8.0),
        ],
        trend="DETERIORATING",
        trend_label="약화 중",
        benchmark="코스피",
        position_mode="NOT_HELD",
    )
    assert result["archetype"] == "MARKET_LAGGARD"
    assert "돌파" in result["deprioritized_strategies"]


def test_holding_context_changes_user_response():
    result = RelativeStrengthAnalyzer._decision_result(
        periods=[
            period(5, 2.0),
            period(20, 7.0),
            period(60, 4.0),
        ],
        trend="STABLE",
        trend_label="유지",
        benchmark="코스피",
        position_mode="HOLDING",
    )
    assert result["user_response"]["perspective"] == "보유 관리"
    assert result["user_response"]["action"] == result["holding"]["action"]
