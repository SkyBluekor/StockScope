from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import Settings, get_settings

from .client import base_url, validate_settings
from .token_cache import get_access_token


_QUOTE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
_QUOTE_TR_ID = "FHKST01010100"
_ALLOWED_MARKET_DIVISIONS = {"J", "NX", "UN"}


class KisQuoteError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True, slots=True)
class KisDomesticPrice:
    ticker: str
    name: str | None
    market_division: str
    current_price: Decimal
    change_amount: Decimal
    change_rate: Decimal
    change_sign: str | None
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    base_price: Decimal
    volume: Decimal


def _required_decimal(
    row: dict[str, Any],
    field: str,
    *,
    positive: bool = False,
) -> Decimal:
    raw = row.get(field)
    if raw is None or str(raw).strip() == "":
        raise KisQuoteError(f"KIS quote output is missing required field: {field}")

    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KisQuoteError(
            f"KIS quote field {field} is not a valid number."
        ) from exc

    if not value.is_finite():
        raise KisQuoteError(f"KIS quote field {field} is not finite.")
    if positive and value <= 0:
        raise KisQuoteError(f"KIS quote field {field} must be greater than zero.")
    if value < 0 and field in {
        "stck_oprc",
        "stck_hgpr",
        "stck_lwpr",
        "stck_sdpr",
        "acml_vol",
    }:
        raise KisQuoteError(f"KIS quote field {field} must not be negative.")
    return value


def _normalize_ticker(ticker: str) -> str:
    value = (ticker or "").strip().upper()
    if len(value) != 6 or not value.isdigit():
        raise KisQuoteError("Domestic stock ticker must be exactly 6 digits.")
    return value


def _normalize_market_division(market_division: str) -> str:
    value = (market_division or "").strip().upper()
    if value not in _ALLOWED_MARKET_DIVISIONS:
        raise KisQuoteError(
            "market_division must be one of J (KRX), NX (NXT), or UN (integrated)."
        )
    return value


def inquire_domestic_price(
    ticker: str,
    market_division: str = "J",
    settings: Settings | None = None,
    *,
    access_token: str | None = None,
    timeout_seconds: float = 15.0,
    http_client: httpx.Client | None = None,
) -> KisDomesticPrice:
    """Read a domestic-stock quote from KIS.

    This is a market-data adapter only. It must not be used to recompute the
    official EOD Strategy/Risk snapshot inside HOLD.1.
    """
    settings = validate_settings(settings or get_settings())
    normalized_ticker = _normalize_ticker(ticker)
    normalized_market = _normalize_market_division(market_division)
    token_value = access_token or get_access_token(settings).access_token

    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token_value}",
        "appkey": settings.kis_app_key or "",
        "appsecret": settings.kis_app_secret or "",
        "tr_id": _QUOTE_TR_ID,
        "custtype": "P",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": normalized_market,
        "FID_INPUT_ISCD": normalized_ticker,
    }

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds)

    try:
        try:
            response = client.get(
                f"{base_url(settings.kis_env)}{_QUOTE_PATH}",
                headers=headers,
                params=params,
                timeout=timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise KisQuoteError(
                f"KIS quote request failed before receiving a response: {exc}"
            ) from exc

        if response.status_code != 200:
            raise KisQuoteError(
                "KIS quote request returned a non-200 response.",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise KisQuoteError(
                "KIS quote response was not valid JSON.",
                status_code=response.status_code,
            ) from exc

        if not isinstance(body, dict):
            raise KisQuoteError("KIS quote response had an unexpected shape.")

        if str(body.get("rt_cd") or "") != "0":
            raise KisQuoteError(
                str(body.get("msg1") or "KIS quote request failed."),
                status_code=response.status_code,
                code=str(body.get("msg_cd") or "") or None,
            )

        output = body.get("output")
        if not isinstance(output, dict) or not output:
            raise KisQuoteError("KIS quote response did not contain output.")

        current_price = _required_decimal(output, "stck_prpr", positive=True)

        return KisDomesticPrice(
            ticker=normalized_ticker,
            name=(
                str(
                    output.get("hts_kor_isnm")
                    or output.get("prdt_name")
                    or ""
                ).strip()
                or None
            ),
            market_division=normalized_market,
            current_price=current_price,
            change_amount=_required_decimal(output, "prdy_vrss"),
            change_rate=_required_decimal(output, "prdy_ctrt"),
            change_sign=(
                str(output.get("prdy_vrss_sign")).strip()
                if output.get("prdy_vrss_sign") not in (None, "")
                else None
            ),
            open_price=_required_decimal(output, "stck_oprc"),
            high_price=_required_decimal(output, "stck_hgpr"),
            low_price=_required_decimal(output, "stck_lwpr"),
            base_price=_required_decimal(output, "stck_sdpr"),
            volume=_required_decimal(output, "acml_vol"),
        )
    finally:
        if owns_client:
            client.close()
