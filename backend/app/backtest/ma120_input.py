from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

MA120_LENGTH = 120


def simple_moving_average_from_rows(
    rows: Sequence[Mapping[str, Any]],
    length: int,
    *,
    field: str = "close",
) -> float | None:
    """Return an SMA from the latest ``length`` valid rows.

    The helper intentionally does not interpolate missing/invalid values.  A moving
    average is available only when the entire requested window contains finite
    numeric values.
    """
    if length <= 0:
        raise ValueError("length must be positive")
    if len(rows) < length:
        return None

    values: list[float] = []
    for row in rows[-length:]:
        raw = row.get(field)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        values.append(value)

    return sum(values) / length


def ma120_from_rows_asof(
    rows: Sequence[Mapping[str, Any]],
    index: int,
    *,
    field: str = "close",
) -> float | None:
    """Calculate SMA120 using rows at or before ``index`` only.

    Future rows are deliberately excluded by slicing through ``index + 1``.  This
    function is shared by live Scanner/backtest snapshot generation so the MA120
    input follows the same as-of boundary in both paths.
    """
    if index < 0 or index >= len(rows):
        raise IndexError("index is outside the supplied row sequence")
    start = max(0, index - MA120_LENGTH + 1)
    return simple_moving_average_from_rows(rows[start : index + 1], MA120_LENGTH, field=field)
