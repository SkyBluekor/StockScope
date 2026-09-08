from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.core.trading_policy import BrokerageCapability, assert_read_only_capability
from app.market.kis.models import DailyBar, DailyChartResponse, KisCredentials, StockQuote


REAL_BASE_URL = "https://openapi.koreainvestment.com:9443"
DEMO_BASE_URL = "https://openapivts.koreainvestment.com:29443"

TOKEN_PATH = "/oauth2/tokenP"
QUOTE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
DAILY_CHART_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"

READ_ONLY_ENDPOINTS = frozenset({QUOTE_PATH, DAILY_CHART_PATH})


class KisApiError(RuntimeError):
    pass


class KisReadOnlyClient:
    """Minimal KIS REST client intentionally restricted to market-data endpoints."""

    def __init__(self, timeout: float = 12.0) -> None:
        self.timeout = timeout

    @staticmethod
    def _base_url(environment: str) -> str:
        return REAL_BASE_URL if environment == "real" else DEMO_BASE_URL

    @staticmethod
    def _assert_allowed_path(path: str) -> None:
        if path not in READ_ONLY_ENDPOINTS:
            raise KisApiError(f"Blocked non-read-only KIS endpoint: {path}")

    async def issue_access_token(self, credentials: KisCredentials) -> tuple[str, int]:
        url = f"{self._base_url(credentials.environment)}{TOKEN_PATH}"
        payload = {
            "grant_type": "client_credentials",
            "appkey": credentials.app_key,
            "appsecret": credentials.app_secret,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers={"content-type": "application/json"})
        data = self._json_or_raise(response, "KIS access-token request")
        token = data.get("access_token")
        if not token:
            raise KisApiError(self._message(data, "KIS access token was not returned."))
        expires_in = self._to_int(data.get("expires_in"), default=86400)
        return str(token), expires_in

    async def get_quote(
        self,
        *,
        app_key: str,
        app_secret: str,
        access_token: str,
        environment: str,
        symbol: str,
    ) -> StockQuote:
        assert_read_only_capability(BrokerageCapability.MARKET_DATA)
        self._assert_allowed_path(QUOTE_PATH)
        symbol = self._validate_symbol(symbol)
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol}
        data = await self._get(
            path=QUOTE_PATH,
            tr_id="FHKST01010100",
            params=params,
            app_key=app_key,
            app_secret=app_secret,
            access_token=access_token,
            environment=environment,
        )
        output = data.get("output") or {}
        if not isinstance(output, dict):
            raise KisApiError("Unexpected KIS quote response format.")
        return StockQuote(
            symbol=symbol,
            name=self._first_str(output, "hts_kor_isnm", "rprs_mrkt_kor_name"),
            price=self._required_int(output, "stck_prpr"),
            change=self._optional_int(output, "prdy_vrss"),
            change_rate=self._optional_float(output, "prdy_ctrt"),
            open=self._optional_int(output, "stck_oprc"),
            high=self._optional_int(output, "stck_hgpr"),
            low=self._optional_int(output, "stck_lwpr"),
            volume=self._optional_int(output, "acml_vol"),
        )

    async def get_daily_chart(
        self,
        *,
        app_key: str,
        app_secret: str,
        access_token: str,
        environment: str,
        symbol: str,
        start_date: date,
        end_date: date,
        period: str = "D",
        adjusted: bool = True,
    ) -> DailyChartResponse:
        assert_read_only_capability(BrokerageCapability.CHART_DATA)
        self._assert_allowed_path(DAILY_CHART_PATH)
        symbol = self._validate_symbol(symbol)
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": period,
            # KIS current example: 0 = adjusted price, 1 = original price.
            "FID_ORG_ADJ_PRC": "0" if adjusted else "1",
        }
        data = await self._get(
            path=DAILY_CHART_PATH,
            tr_id="FHKST03010100",
            params=params,
            app_key=app_key,
            app_secret=app_secret,
            access_token=access_token,
            environment=environment,
        )
        rows = data.get("output2") or []
        if not isinstance(rows, list):
            raise KisApiError("Unexpected KIS daily-chart response format.")
        bars: list[DailyBar] = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("stck_bsop_date"):
                continue
            bars.append(
                DailyBar(
                    trading_date=date.fromisoformat(
                        f"{row['stck_bsop_date'][0:4]}-{row['stck_bsop_date'][4:6]}-{row['stck_bsop_date'][6:8]}"
                    ),
                    open=self._required_int(row, "stck_oprc"),
                    high=self._required_int(row, "stck_hgpr"),
                    low=self._required_int(row, "stck_lwpr"),
                    close=self._required_int(row, "stck_clpr"),
                    volume=self._required_int(row, "acml_vol"),
                )
            )
        bars.sort(key=lambda item: item.trading_date)
        return DailyChartResponse(symbol=symbol, period=period, adjusted=adjusted, bars=bars)

    async def _get(
        self,
        *,
        path: str,
        tr_id: str,
        params: dict[str, str],
        app_key: str,
        app_secret: str,
        access_token: str,
        environment: str,
    ) -> dict[str, Any]:
        headers = {
            "authorization": f"Bearer {access_token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "content-type": "application/json; charset=utf-8",
        }
        url = f"{self._base_url(environment)}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params, headers=headers)
        return self._json_or_raise(response, f"KIS GET {path}")

    @staticmethod
    def _json_or_raise(response: httpx.Response, operation: str) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise KisApiError(f"{operation} returned a non-JSON response ({response.status_code}).") from exc
        if not isinstance(data, dict):
            raise KisApiError(f"{operation} returned an unexpected response.")
        if response.is_error:
            raise KisApiError(KisReadOnlyClient._message(data, f"{operation} failed ({response.status_code})."))
        # KIS quotation APIs commonly return rt_cd == '0' on success.
        rt_cd = data.get("rt_cd")
        if rt_cd not in (None, "0", 0):
            raise KisApiError(KisReadOnlyClient._message(data, f"{operation} failed."))
        return data

    @staticmethod
    def _message(data: dict[str, Any], fallback: str) -> str:
        message = data.get("msg1") or data.get("error_description") or data.get("message")
        code = data.get("msg_cd") or data.get("error_code")
        return f"{message} ({code})" if message and code else str(message or fallback)

    @staticmethod
    def _validate_symbol(symbol: str) -> str:
        value = symbol.strip().upper()
        if not (len(value) == 6 and value.isdigit()):
            raise KisApiError("Domestic stock symbol must be a 6-digit code, e.g. 005930.")
        return value

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return default

    @classmethod
    def _required_int(cls, data: dict[str, Any], key: str) -> int:
        if key not in data or data[key] in (None, ""):
            raise KisApiError(f"KIS response is missing required field: {key}")
        return cls._to_int(data[key])

    @classmethod
    def _optional_int(cls, data: dict[str, Any], key: str) -> int | None:
        if key not in data or data[key] in (None, ""):
            return None
        return cls._to_int(data[key])

    @staticmethod
    def _optional_float(data: dict[str, Any], key: str) -> float | None:
        try:
            value = data.get(key)
            return None if value in (None, "") else float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _first_str(data: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                return str(value)
        return None
