from __future__ import annotations

from decimal import Decimal

import pytest

from app.quotes.websocket_parser import (
    QUOTE_COLUMNS,
    WebSocketQuoteParseError,
    parse_quote_frame,
)


def _frame(**overrides: str) -> str:
    row = {name: "0" for name in QUOTE_COLUMNS}
    row.update(
        {
            "MKSC_SHRN_ISCD": "005930",
            "STCK_CNTG_HOUR": "093012",
            "STCK_PRPR": "84200",
            "PRDY_VRSS_SIGN": "2",
            "PRDY_VRSS": "1200",
            "PRDY_CTRT": "1.45",
            "STCK_OPRC": "83300",
            "STCK_HGPR": "85000",
            "STCK_LWPR": "82900",
            "CNTG_VOL": "15",
            "ACML_VOL": "12345678",
            "BSOP_DATE": "20260928",
            "TRHT_YN": "N",
        }
    )
    row.update(overrides)
    payload = "^".join(row[name] for name in QUOTE_COLUMNS)
    return f"0|H0UNCNT0|1|{payload}"


def test_integrated_quote_frame_maps_required_fields() -> None:
    tick = parse_quote_frame(_frame())[0]

    assert tick.ticker == "005930"
    assert tick.venue == "INTEGRATED"
    assert tick.current_price == Decimal("84200")
    assert tick.change_amount == Decimal("1200")
    assert tick.change_rate == Decimal("1.45")
    assert tick.base_price == Decimal("83000")
    assert tick.open_price == Decimal("83300")
    assert tick.high_price == Decimal("85000")
    assert tick.low_price == Decimal("82900")
    assert tick.accumulated_volume == Decimal("12345678")
    assert tick.provider_timestamp == "2026-09-28T09:30:12+09:00"


@pytest.mark.parametrize(
    "overrides",
    [
        {"MKSC_SHRN_ISCD": "5930"},
        {"STCK_PRPR": "0"},
        {"PRDY_VRSS_SIGN": "9"},
        {"BSOP_DATE": "20260230"},
        {"STCK_CNTG_HOUR": "256199"},
    ],
)
def test_invalid_quote_tick_is_rejected(overrides: dict[str, str]) -> None:
    with pytest.raises(WebSocketQuoteParseError):
        parse_quote_frame(_frame(**overrides))


def test_invalid_field_count_is_rejected() -> None:
    frame = _frame().rsplit("^", 1)[0]
    with pytest.raises(WebSocketQuoteParseError, match="field count"):
        parse_quote_frame(frame)
