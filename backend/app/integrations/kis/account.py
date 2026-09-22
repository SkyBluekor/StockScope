from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings

from .client import base_url, normalize_environment, validate_account_settings
from .token_cache import get_access_token


_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"


class KisAccountError(RuntimeError):
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
class KisHolding:
    ticker: str
    name: str
    quantity: Decimal
    orderable_quantity: Decimal
    average_price: Decimal
    purchase_amount: Decimal
    current_price: Decimal
    evaluation_amount: Decimal
    pnl_amount: Decimal
    pnl_rate: Decimal


@dataclass(frozen=True, slots=True)
class KisBalanceSummary:
    deposit_amount: Decimal
    securities_evaluation_amount: Decimal
    total_evaluation_amount: Decimal
    net_asset_amount: Decimal
    purchase_amount_total: Decimal
    evaluation_amount_total: Decimal
    pnl_amount_total: Decimal


@dataclass(frozen=True, slots=True)
class KisDomesticBalance:
    holdings: tuple[KisHolding, ...]
    summary: KisBalanceSummary | None
    page_count: int
    is_complete: bool


def _dec(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _required_decimal(
    row: dict[str, Any],
    field: str,
    *,
    non_negative: bool = False,
    positive: bool = False,
) -> Decimal:
    raw = row.get(field)
    if raw is None or str(raw).strip() == "":
        raise KisAccountError(f"KIS balance holding is missing required field: {field}")
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KisAccountError(
            f"KIS balance holding field {field} is not a valid number."
        ) from exc
    if not value.is_finite():
        raise KisAccountError(f"KIS balance holding field {field} is not finite.")
    if positive and value <= 0:
        raise KisAccountError(
            f"KIS balance holding field {field} must be greater than zero."
        )
    if non_negative and value < 0:
        raise KisAccountError(
            f"KIS balance holding field {field} must not be negative."
        )
    return value


def _holding_from_row(row: dict[str, Any]) -> KisHolding | None:
    ticker = str(row.get("pdno") or "").strip()
    raw_quantity = row.get("hldg_qty")
    if not ticker:
        # KIS may include a blank placeholder row. It is safe to ignore only when
        # the row also does not claim a positive/meaningful holding quantity.
        if raw_quantity in (None, "", "0", "0.0", 0):
            return None
        raise KisAccountError("KIS balance holding is missing required ticker.")
    if len(ticker) != 6 or not ticker.isdigit():
        raise KisAccountError("KIS balance holding ticker must be exactly 6 digits.")

    quantity = _required_decimal(
        row,
        "hldg_qty",
        non_negative=True,
    )
    average_price = (
        _required_decimal(row, "pchs_avg_pric", positive=True)
        if quantity > 0
        else _dec(row.get("pchs_avg_pric"))
    )

    return KisHolding(
        ticker=ticker,
        name=str(row.get("prdt_name") or "").strip(),
        quantity=quantity,
        orderable_quantity=_dec(row.get("ord_psbl_qty")),
        average_price=average_price,
        purchase_amount=_dec(row.get("pchs_amt")),
        current_price=_dec(row.get("prpr")),
        evaluation_amount=_dec(row.get("evlu_amt")),
        pnl_amount=_dec(row.get("evlu_pfls_amt")),
        pnl_rate=_dec(row.get("evlu_pfls_rt") or row.get("evlu_erng_rt")),
    )


def _summary_from_row(row: dict[str, Any] | None) -> KisBalanceSummary | None:
    if not row:
        return None
    return KisBalanceSummary(
        deposit_amount=_dec(row.get("dnca_tot_amt")),
        securities_evaluation_amount=_dec(row.get("scts_evlu_amt")),
        total_evaluation_amount=_dec(row.get("tot_evlu_amt")),
        net_asset_amount=_dec(row.get("nass_amt")),
        purchase_amount_total=_dec(row.get("pchs_amt_smtl_amt")),
        evaluation_amount_total=_dec(row.get("evlu_amt_smtl_amt")),
        pnl_amount_total=_dec(row.get("evlu_pfls_smtl_amt")),
    )


def _tr_id(environment: str | None) -> str:
    return "TTTC8434R" if normalize_environment(environment) == "real" else "VTTC8434R"


def inquire_domestic_balance(
    settings: Settings | None = None,
    *,
    access_token: str | None = None,
    timeout_seconds: float = 15.0,
    include_zero_quantity: bool = False,
    http_client: httpx.Client | None = None,
) -> KisDomesticBalance:
    settings = validate_account_settings(settings or get_settings())
    token_value = access_token or get_access_token(settings).access_token

    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token_value}",
        "appkey": settings.kis_app_key or "",
        "appsecret": settings.kis_app_secret or "",
        "tr_id": _tr_id(settings.kis_env),
        "custtype": "P",
        "tr_cont": "",
    }
    params = {
        "CANO": settings.kis_account_no or "",
        "ACNT_PRDT_CD": settings.kis_account_product_code,
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds)
    holdings: list[KisHolding] = []
    summary: KisBalanceSummary | None = None
    page_count = 0

    try:
        while True:
            response = client.get(
                f"{base_url(settings.kis_env)}{_BALANCE_PATH}",
                headers=headers,
                params=params,
                timeout=timeout_seconds,
            )

            if response.status_code != 200:
                raise KisAccountError(
                    "KIS balance request returned a non-200 response.",
                    status_code=response.status_code,
                )

            body = response.json()
            if str(body.get("rt_cd") or "") != "0":
                raise KisAccountError(
                    str(body.get("msg1") or "KIS balance request failed."),
                    status_code=response.status_code,
                    code=str(body.get("msg_cd") or "") or None,
                )

            page_count += 1
            if page_count > 11:
                raise KisAccountError("KIS balance pagination exceeded the safety limit.")

            rows = body.get("output1") or []
            if not isinstance(rows, list):
                raise KisAccountError("KIS balance output1 had an unexpected shape.")

            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                item = _holding_from_row(raw)
                if item is None:
                    continue
                if not include_zero_quantity and item.quantity <= 0:
                    continue
                holdings.append(item)

            output2 = body.get("output2") or []
            if summary is None and isinstance(output2, list) and output2:
                first = output2[0]
                if isinstance(first, dict):
                    summary = _summary_from_row(first)

            tr_cont = (response.headers.get("tr_cont") or "").strip().upper()
            next_fk = str(body.get("ctx_area_fk100") or "")
            next_nk = str(body.get("ctx_area_nk100") or "")

            if tr_cont not in {"M", "F"} or not (next_fk or next_nk):
                break

            params["CTX_AREA_FK100"] = next_fk
            params["CTX_AREA_NK100"] = next_nk
            headers["tr_cont"] = "N"
            time.sleep(0.6 if normalize_environment(settings.kis_env) == "virtual" else 0.1)
    finally:
        if owns_client:
            client.close()

    return KisDomesticBalance(
        holdings=tuple(holdings),
        summary=summary,
        page_count=page_count,
        is_complete=True,
    )
