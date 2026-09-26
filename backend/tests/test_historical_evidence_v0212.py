from __future__ import annotations

from datetime import date, timedelta

from app.backtest.historical_evidence import (
    MIN_SAMPLE_FOR_EVALUATION,
    data_readiness,
    evaluate_historical_evidence,
    unavailable_historical_evidence,
    validation_start_for_years,
)


def _metrics(*, trades: int, wins: int, avg: float | None, pf: float | None, mdd: float | None) -> dict:
    return {
        "trades": trades,
        "wins": wins,
        "losses": max(0, trades - wins),
        "win_rate_pct": None if trades == 0 else wins / trades * 100,
        "average_net_return_pct": avg,
        "median_net_return_pct": avg,
        "expectancy_pct": avg,
        "profit_factor": pf,
        "max_drawdown_pct": mdd,
        "average_win_pct": 4.0 if wins else None,
        "average_loss_pct": -3.0 if trades - wins else None,
    }


def _trades(count: int, *, regime: str = "TREND_UP", net: float = 1.0) -> list[dict]:
    return [
        {
            "market_regime": regime,
            "net_return_pct": net,
            "exit_reason": "TARGET_1" if net > 0 else "STOP",
        }
        for _ in range(count)
    ]


def test_v0212_requires_ten_historical_trades_before_evidence_rating() -> None:
    evidence = evaluate_historical_evidence(
        metrics=_metrics(trades=9, wins=9, avg=8.0, pf=9.0, mdd=-2.0),
        trades=_trades(9),
        validation_start="2023-09-14",
        validation_end="2026-09-14",
    )
    assert MIN_SAMPLE_FOR_EVALUATION == 10
    assert evidence["status"] == "INSUFFICIENT"
    assert evidence["label"] == "표본 부족"
    assert evidence["sample_sufficient"] is False


def test_v0212_can_rate_good_evidence_after_sample_is_sufficient() -> None:
    evidence = evaluate_historical_evidence(
        metrics=_metrics(trades=14, wins=9, avg=1.8, pf=1.45, mdd=-11.0),
        trades=_trades(14),
        validation_start="2023-09-14",
        validation_end="2026-09-14",
    )
    assert evidence["status"] == "GOOD"
    assert evidence["sample_sufficient"] is True
    assert evidence["sample_count"] == 14
    assert evidence["wins"] == 9


def test_v0212_history_never_turns_win_rate_into_future_probability_text() -> None:
    evidence = evaluate_historical_evidence(
        metrics=_metrics(trades=12, wins=8, avg=1.0, pf=1.3, mdd=-8.0),
        trades=_trades(12),
        validation_start="2023-09-14",
        validation_end="2026-09-14",
    )
    assert "상승 확률" in evidence["guardrail"]
    assert "보장하지" in evidence["guardrail"]


def test_v0212_warns_when_a_market_regime_has_negative_average() -> None:
    trades = _trades(7, regime="TREND_UP", net=2.0) + _trades(5, regime="TREND_DOWN", net=-4.0)
    evidence = evaluate_historical_evidence(
        metrics=_metrics(trades=12, wins=7, avg=-0.5, pf=0.9, mdd=-18.0),
        trades=trades,
        validation_start="2023-09-14",
        validation_end="2026-09-14",
    )
    assert evidence["status"] == "WEAK"
    assert any("하락장" in warning for warning in evidence["warnings"])


def test_v0212_no_cases_is_not_promoted_to_weak_or_good() -> None:
    evidence = evaluate_historical_evidence(
        metrics=_metrics(trades=0, wins=0, avg=None, pf=None, mdd=0.0),
        trades=[],
        validation_start="2023-09-14",
        validation_end="2026-09-14",
    )
    assert evidence["status"] == "NO_CASES"
    assert evidence["verified"] is True
    assert evidence["sample_count"] == 0


def _daily_rows(start: date, days: int) -> list[dict]:
    rows = []
    cursor = start
    while len(rows) < days:
        if cursor.weekday() < 5:
            rows.append({"date": cursor.strftime("%Y%m%d")})
        cursor += timedelta(days=1)
    return rows


def test_v0212_data_readiness_requires_real_three_year_start_and_warmup() -> None:
    validation_start = date(2023, 9, 14)
    validation_end = date(2026, 9, 14)
    full_rows = _daily_rows(validation_start - timedelta(days=220), 980)
    ready = data_readiness(
        stock_rows=full_rows,
        index_rows=full_rows,
        validation_start=validation_start,
        validation_end=validation_end,
    )
    assert ready["ready"] is True

    short_rows = _daily_rows(date(2025, 1, 1), 430)
    short = data_readiness(
        stock_rows=short_rows,
        index_rows=short_rows,
        validation_start=validation_start,
        validation_end=validation_end,
    )
    assert short["ready"] is False
    assert any("3년 시작구간" in reason for reason in short["reasons"])


def test_v0212_unavailable_history_stays_separate_from_current_entry_condition() -> None:
    evidence = unavailable_historical_evidence(
        validation_start=date(2023, 9, 14),
        validation_end=date(2026, 9, 14),
        reasons=["종목 3년 시작구간 데이터 부족"],
    )
    assert evidence["verified"] is False
    assert evidence["status"] == "DATA_UNAVAILABLE"
    assert evidence["unavailable_reason"] == "MISSING_HISTORY"
    assert evidence["preparation_available"] is True
    assert "현재 전략 조건 실패" in evidence["guardrail"]





def test_v0212_unsupported_evidence_does_not_offer_data_preparation() -> None:
    evidence = unavailable_historical_evidence(
        validation_start=date(2023, 9, 14),
        validation_end=date(2026, 9, 14),
        reasons=["지원하지 않는 전략: UNKNOWN"],
        unavailable_reason="UNSUPPORTED_STRATEGY",
        preparation_available=False,
    )
    assert evidence["status"] == "DATA_UNAVAILABLE"
    assert evidence["unavailable_reason"] == "UNSUPPORTED_STRATEGY"
    assert evidence["preparation_available"] is False


def test_v0212_verified_evidence_never_requests_data_preparation() -> None:
    evidence = evaluate_historical_evidence(
        metrics=_metrics(trades=12, wins=7, avg=-0.3, pf=0.9, mdd=-18.0),
        trades=_trades(12, net=-0.3),
        validation_start="2023-09-14",
        validation_end="2026-09-14",
    )
    assert evidence["verified"] is True
    assert evidence["unavailable_reason"] is None
    assert evidence["preparation_available"] is False


def test_v0212_three_year_period_uses_calendar_date_not_1095_day_approximation() -> None:
    assert validation_start_for_years(date(2026, 9, 14)) == date(2023, 9, 14)
    assert validation_start_for_years(date(2024, 2, 29)) == date(2021, 2, 28)
