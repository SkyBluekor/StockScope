from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.backtest.ma120_input import MA120_LENGTH, ma120_from_rows_asof, simple_moving_average_from_rows


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENGINE = BACKEND_ROOT / "app" / "backtest" / "engine.py"
SCANNER = BACKEND_ROOT / "app" / "backtest" / "scanner.py"


def _rows(count: int, *, start: float = 1.0) -> list[dict[str, float]]:
    return [{"close": start + i} for i in range(count)]


def test_sma120_requires_120_valid_rows() -> None:
    assert simple_moving_average_from_rows(_rows(119), MA120_LENGTH) is None
    assert simple_moving_average_from_rows(_rows(120), MA120_LENGTH) == pytest.approx(60.5)


def test_sma120_uses_latest_120_only() -> None:
    rows = _rows(121)
    # 2..121 => mean 61.5
    assert simple_moving_average_from_rows(rows, MA120_LENGTH) == pytest.approx(61.5)
    rows = _rows(200)
    # 81..200 => mean 140.5
    assert simple_moving_average_from_rows(rows, MA120_LENGTH) == pytest.approx(140.5)


def test_sma120_rejects_missing_nan_and_invalid_close() -> None:
    rows = _rows(120)
    rows[-1]["close"] = None  # type: ignore[assignment]
    assert simple_moving_average_from_rows(rows, MA120_LENGTH) is None

    rows = _rows(120)
    rows[-1]["close"] = math.nan
    assert simple_moving_average_from_rows(rows, MA120_LENGTH) is None

    rows = _rows(120)
    rows[-1]["close"] = "bad"  # type: ignore[assignment]
    assert simple_moving_average_from_rows(rows, MA120_LENGTH) is None


def test_ma120_asof_does_not_read_future_rows() -> None:
    rows = _rows(120)
    baseline = ma120_from_rows_asof(rows, 119)
    assert baseline == pytest.approx(60.5)

    # Mutating/appending future data must not change the value at index 119.
    rows.extend({"close": 10_000_000.0 + i} for i in range(20))
    for row in rows[120:]:
        row["close"] *= -100.0
    assert ma120_from_rows_asof(rows, 119) == pytest.approx(baseline)


def test_ma120_asof_boundaries() -> None:
    rows = _rows(121)
    assert ma120_from_rows_asof(rows, 118) is None
    assert ma120_from_rows_asof(rows, 119) == pytest.approx(60.5)
    assert ma120_from_rows_asof(rows, 120) == pytest.approx(61.5)
    with pytest.raises(IndexError):
        ma120_from_rows_asof(rows, -1)
    with pytest.raises(IndexError):
        ma120_from_rows_asof(rows, len(rows))


def test_engine_keeps_existing_60_row_technical_path_and_only_supplies_ma120() -> None:
    source = ENGINE.read_text(encoding="utf-8")
    assert "LIVE_HISTORY_POINTS = 60" in source
    assert "technical = self.technical.analyze(history)" in source
    assert 'if technical.get("ma120") is None:' in source
    assert "ma120 = ma120_from_rows_asof(stock_rows, index)" in source
    assert 'technical["ma120"] = ma120' in source
    # c.4d must not change the known sector-RS issue; that belongs to c.4e.
    assert "relative_strength_sector_pct=None" in source


def test_scanner_cache_version_is_bumped_for_changed_decisions() -> None:
    source = SCANNER.read_text(encoding="utf-8")
    assert 'VERSION = "0.21.3.4"' in source
