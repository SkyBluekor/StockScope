from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .models import QuoteVenue


SEOUL = ZoneInfo("Asia/Seoul")

VENUE_TO_WS_TR_ID: dict[QuoteVenue, str] = {
    "INTEGRATED": "H0UNCNT0",
    "KRX": "H0STCNT0",
    "NXT": "H0NXCNT0",
}
WS_TR_ID_TO_VENUE: dict[str, QuoteVenue] = {
    value: key for key, value in VENUE_TO_WS_TR_ID.items()
}

# KIS official domestic-stock realtime execution columns. H0UNCNT0 currently
# shares this layout with H0STCNT0/H0NXCNT0 for the fields StockScope uses.
QUOTE_COLUMNS: tuple[str, ...] = (
    "MKSC_SHRN_ISCD",
    "STCK_CNTG_HOUR",
    "STCK_PRPR",
    "PRDY_VRSS_SIGN",
    "PRDY_VRSS",
    "PRDY_CTRT",
    "WGHN_AVRG_STCK_PRC",
    "STCK_OPRC",
    "STCK_HGPR",
    "STCK_LWPR",
    "ASKP1",
    "BIDP1",
    "CNTG_VOL",
    "ACML_VOL",
    "ACML_TR_PBMN",
    "SELN_CNTG_CSNU",
    "SHNU_CNTG_CSNU",
    "NTBY_CNTG_CSNU",
    "CTTR",
    "SELN_CNTG_SMTN",
    "SHNU_CNTG_SMTN",
    "CNTG_CLS_CODE",
    "SHNU_RATE",
    "PRDY_VOL_VRSS_ACML_VOL_RATE",
    "OPRC_HOUR",
    "OPRC_VRSS_PRPR_SIGN",
    "OPRC_VRSS_PRPR",
    "HGPR_HOUR",
    "HGPR_VRSS_PRPR_SIGN",
    "HGPR_VRSS_PRPR",
    "LWPR_HOUR",
    "LWPR_VRSS_PRPR_SIGN",
    "LWPR_VRSS_PRPR",
    "BSOP_DATE",
    "NEW_MKOP_CLS_CODE",
    "TRHT_YN",
    "ASKP_RSQN1",
    "BIDP_RSQN1",
    "TOTAL_ASKP_RSQN",
    "TOTAL_BIDP_RSQN",
    "VOL_TNRT",
    "PRDY_SMNS_HOUR_ACML_VOL",
    "PRDY_SMNS_HOUR_ACML_VOL_RATE",
    "HOUR_CLS_CODE",
    "MRKT_TRTM_CLS_CODE",
    "VI_STND_PRC",
)


class WebSocketQuoteParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedQuoteTick:
    ticker: str
    venue: QuoteVenue
    current_price: Decimal
    change_amount: Decimal
    change_rate: Decimal
    change_sign: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    base_price: Decimal
    trade_volume: Decimal
    accumulated_volume: Decimal
    provider_timestamp: str
    trading_halt: str | None


def _decimal(raw: str, field: str, *, positive: bool = False) -> Decimal:
    try:
        value = Decimal((raw or "").strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise WebSocketQuoteParseError(f"{field} is not a valid Decimal") from exc
    if not value.is_finite():
        raise WebSocketQuoteParseError(f"{field} is not finite")
    if positive and value <= 0:
        raise WebSocketQuoteParseError(f"{field} must be greater than zero")
    return value


def _base_price(current_price: Decimal, change_amount: Decimal, sign: str) -> Decimal:
    magnitude = abs(change_amount)
    if sign in {"1", "2"}:
        base = current_price - magnitude
    elif sign == "3":
        base = current_price
    elif sign in {"4", "5"}:
        base = current_price + magnitude
    else:
        raise WebSocketQuoteParseError("PRDY_VRSS_SIGN is invalid")
    if base <= 0:
        raise WebSocketQuoteParseError("derived base price must be greater than zero")
    return base


def _provider_timestamp(business_date: str, trade_time: str) -> str:
    date_text = (business_date or "").strip()
    time_text = (trade_time or "").strip()
    if len(date_text) != 8 or not date_text.isdigit():
        raise WebSocketQuoteParseError("BSOP_DATE must be YYYYMMDD")
    if len(time_text) != 6 or not time_text.isdigit():
        raise WebSocketQuoteParseError("STCK_CNTG_HOUR must be HHMMSS")
    try:
        value = datetime.strptime(date_text + time_text, "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise WebSocketQuoteParseError("trade date/time is invalid") from exc
    return value.replace(tzinfo=SEOUL).isoformat()


def parse_quote_frame(raw: str) -> tuple[ParsedQuoteTick, ...]:
    if not isinstance(raw, str) or not raw:
        raise WebSocketQuoteParseError("empty websocket frame")

    parts = raw.split("|", 3)
    if len(parts) != 4:
        raise WebSocketQuoteParseError("realtime frame must contain four pipe sections")

    encrypted_flag, tr_id, count_text, payload = parts
    if encrypted_flag != "0":
        raise WebSocketQuoteParseError("encrypted quote frames are not supported")
    venue = WS_TR_ID_TO_VENUE.get(tr_id)
    if venue is None:
        raise WebSocketQuoteParseError(f"unsupported quote TR: {tr_id}")

    try:
        count = int(count_text)
    except ValueError as exc:
        raise WebSocketQuoteParseError("realtime frame count is invalid") from exc
    if count <= 0:
        raise WebSocketQuoteParseError("realtime frame count must be positive")

    values = payload.split("^")
    expected = count * len(QUOTE_COLUMNS)
    if len(values) != expected:
        raise WebSocketQuoteParseError(
            f"invalid field count: expected {expected}, got {len(values)}"
        )

    ticks: list[ParsedQuoteTick] = []
    width = len(QUOTE_COLUMNS)
    for index in range(count):
        row_values = values[index * width : (index + 1) * width]
        row = dict(zip(QUOTE_COLUMNS, row_values, strict=True))
        ticker = row["MKSC_SHRN_ISCD"].strip()
        if len(ticker) != 6 or not ticker.isdigit():
            raise WebSocketQuoteParseError("ticker must be six digits")

        current_price = _decimal(row["STCK_PRPR"], "STCK_PRPR", positive=True)
        change_amount = _decimal(row["PRDY_VRSS"], "PRDY_VRSS")
        change_rate = _decimal(row["PRDY_CTRT"], "PRDY_CTRT")
        change_sign = row["PRDY_VRSS_SIGN"].strip()
        open_price = _decimal(row["STCK_OPRC"], "STCK_OPRC")
        high_price = _decimal(row["STCK_HGPR"], "STCK_HGPR")
        low_price = _decimal(row["STCK_LWPR"], "STCK_LWPR")
        trade_volume = _decimal(row["CNTG_VOL"], "CNTG_VOL")
        accumulated_volume = _decimal(row["ACML_VOL"], "ACML_VOL")
        for field, value in (
            ("STCK_OPRC", open_price),
            ("STCK_HGPR", high_price),
            ("STCK_LWPR", low_price),
            ("CNTG_VOL", trade_volume),
            ("ACML_VOL", accumulated_volume),
        ):
            if value < 0:
                raise WebSocketQuoteParseError(f"{field} must not be negative")

        ticks.append(
            ParsedQuoteTick(
                ticker=ticker,
                venue=venue,
                current_price=current_price,
                change_amount=change_amount,
                change_rate=change_rate,
                change_sign=change_sign,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                base_price=_base_price(current_price, change_amount, change_sign),
                trade_volume=trade_volume,
                accumulated_volume=accumulated_volume,
                provider_timestamp=_provider_timestamp(
                    row["BSOP_DATE"], row["STCK_CNTG_HOUR"]
                ),
                trading_halt=row["TRHT_YN"].strip() or None,
            )
        )

    return tuple(ticks)
