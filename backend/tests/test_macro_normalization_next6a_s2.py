from __future__ import annotations

import pytest

from app.macro.normalization import normalize_fred_dgs10_row


def test_dgs10_missing_marker_is_missing_not_zero():
    row = normalize_fred_dgs10_row(
        {
            "date": "2026-09-28",
            "value": ".",
            "realtime_start": "2026-09-28",
            "realtime_end": "2026-09-28",
        }
    )
    assert row.missing is True
    assert row.normalized_value is None
    assert row.raw_value == "."


def test_dgs10_percent_value_is_preserved_as_percent_level():
    row = normalize_fred_dgs10_row(
        {
            "date": "2026-09-28",
            "value": "4.100",
            "realtime_start": "2026-09-28",
            "realtime_end": "2026-09-28",
        }
    )
    assert row.missing is False
    assert row.normalized_value == "4.1"


def test_dgs10_invalid_numeric_value_is_rejected():
    with pytest.raises(ValueError, match="not numeric"):
        normalize_fred_dgs10_row(
            {
                "date": "2026-09-28",
                "value": "not-a-number",
            }
        )
