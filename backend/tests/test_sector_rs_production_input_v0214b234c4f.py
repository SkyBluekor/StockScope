from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.backtest.sector_rs_input import (
    HistoricalSectorInput,
    TEMPORAL_POINT_IN_TIME,
    TEMPORAL_STATIC_CURRENT,
    evaluate_historical_sector_input,
)
from app.market.sector_relative_strength import SectorRelativeStrengthAnalyzer


def _rows(start: float, end: float, count: int, *, start_date: date = date(2026, 1, 1)):
    if count == 1:
        values = [end]
    else:
        values = [start + (end - start) * i / (count - 1) for i in range(count)]
    return [
        {"date": (start_date + timedelta(days=i)).isoformat(), "close": value}
        for i, value in enumerate(values)
    ]


def _market_relative():
    return {
        "primary_period": 20,
        "primary_excess_pct": 0.0,
        "benchmark": {"name": "KOSPI"},
    }


def _prepared(rows, temporal_status):
    return HistoricalSectorInput(
        industry_code="26",
        sector_group="전기·전자",
        benchmark_name="전기·전자",
        sector_rows=tuple(rows),
        mapping={"sector_group": "전기·전자", "aliases": ["전기·전자"]},
        mapping_method="test",
        temporal_status=temporal_status,
    )


def test_point_in_time_20d_sector_rs_is_production_eligible():
    stock = _rows(100.0, 110.0, 21)
    sector = _rows(100.0, 105.0, 21)
    result = evaluate_historical_sector_input(
        analyzer=SectorRelativeStrengthAnalyzer(),
        prepared=_prepared(sector, TEMPORAL_POINT_IN_TIME),
        stock_rows_asof=stock,
        signal_date=stock[-1]["date"],
        market="KOSPI",
        market_relative=_market_relative(),
    )

    assert result.audit_relative_strength_pct == pytest.approx(5.0)
    assert result.production_relative_strength_pct == pytest.approx(5.0)
    assert result.audit["production_safe"] is True
    assert result.audit["unavailable_reason"] is None


def test_static_current_mapping_is_audit_only():
    stock = _rows(100.0, 110.0, 21)
    sector = _rows(100.0, 105.0, 21)
    result = evaluate_historical_sector_input(
        analyzer=SectorRelativeStrengthAnalyzer(),
        prepared=_prepared(sector, TEMPORAL_STATIC_CURRENT),
        stock_rows_asof=stock,
        signal_date=stock[-1]["date"],
        market="KOSPI",
        market_relative=_market_relative(),
    )

    assert result.audit_relative_strength_pct == pytest.approx(5.0)
    assert result.production_relative_strength_pct is None
    assert result.production_context is None
    assert result.audit["production_safe"] is False
    assert result.audit["unavailable_reason"] == "TEMPORAL_MAPPING_UNSAFE"


def test_future_sector_rows_are_ignored():
    stock = _rows(100.0, 110.0, 21)
    sector = _rows(100.0, 105.0, 21)
    signal_date = stock[-1]["date"]
    with_future = sector + [{"date": "2026-12-31", "close": 1.0}]

    base = evaluate_historical_sector_input(
        analyzer=SectorRelativeStrengthAnalyzer(),
        prepared=_prepared(sector, TEMPORAL_POINT_IN_TIME),
        stock_rows_asof=stock,
        signal_date=signal_date,
        market="KOSPI",
        market_relative=_market_relative(),
    )
    future = evaluate_historical_sector_input(
        analyzer=SectorRelativeStrengthAnalyzer(),
        prepared=_prepared(with_future, TEMPORAL_POINT_IN_TIME),
        stock_rows_asof=stock,
        signal_date=signal_date,
        market="KOSPI",
        market_relative=_market_relative(),
    )

    assert future.audit_relative_strength_pct == base.audit_relative_strength_pct
    assert future.production_relative_strength_pct == base.production_relative_strength_pct
    assert future.audit["future_rows_ignored"] == 1
    assert future.audit["sector_history_end_date"] == signal_date.replace("-", "")


def test_signal_date_sector_row_is_included():
    stock = _rows(100.0, 110.0, 21)
    sector = _rows(100.0, 105.0, 21)
    result = evaluate_historical_sector_input(
        analyzer=SectorRelativeStrengthAnalyzer(),
        prepared=_prepared(sector, TEMPORAL_POINT_IN_TIME),
        stock_rows_asof=stock,
        signal_date=stock[-1]["date"],
        market="KOSPI",
        market_relative=_market_relative(),
    )

    assert result.audit["sector_history_end_date"] == stock[-1]["date"].replace("-", "")
    assert result.audit_relative_strength_pct == pytest.approx(5.0)


def test_less_than_21_common_points_does_not_supply_20d_strategy_input():
    stock = _rows(100.0, 110.0, 20)
    sector = _rows(100.0, 105.0, 20)
    result = evaluate_historical_sector_input(
        analyzer=SectorRelativeStrengthAnalyzer(),
        prepared=_prepared(sector, TEMPORAL_POINT_IN_TIME),
        stock_rows_asof=stock,
        signal_date=stock[-1]["date"],
        market="KOSPI",
        market_relative=_market_relative(),
    )

    assert result.production_relative_strength_pct is None
    assert result.audit_relative_strength_pct is None
    assert result.audit["unavailable_reason"] == "INSUFFICIENT_COMMON_DATES"


def test_missing_input_preserves_existing_market_fallback_semantics():
    stock = _rows(100.0, 110.0, 21)
    result = evaluate_historical_sector_input(
        analyzer=SectorRelativeStrengthAnalyzer(),
        prepared=None,
        stock_rows_asof=stock,
        signal_date=stock[-1]["date"],
        market="KOSPI",
        market_relative=_market_relative(),
    )

    assert result.production_relative_strength_pct is None
    assert result.production_context is None
    assert result.audit["input_status"] == "NO_SECTOR_INPUT"
