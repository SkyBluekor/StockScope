from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx

from app.market.providers.base import ProviderError, ProviderNotConfigured


@dataclass(frozen=True)
class KrxEndpoint:
    path: str
    label: str


class KrxProvider:
    BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"

    STOCK_ENDPOINTS = {
        "KOSPI": KrxEndpoint("sto/stk_bydd_trd", "유가증권 일별매매정보"),
        "KOSDAQ": KrxEndpoint("sto/ksq_bydd_trd", "코스닥 일별매매정보"),
    }

    INDEX_ENDPOINTS = {
        "KOSPI": KrxEndpoint("idx/kospi_dd_trd", "KOSPI 시리즈 일별시세정보"),
        "KOSDAQ": KrxEndpoint("idx/kosdaq_dd_trd", "KOSDAQ 시리즈 일별시세정보"),
    }

    # KRX 일별 API는 같은 날짜를 여러 종목에서 반복 조회할 가능성이 높습니다.
    # 개발 PoC 단계에서는 프로세스 메모리 캐시로 중복 호출을 줄입니다.
    _rows_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def __init__(self, api_key: str | None) -> None:
        self.api_key = (api_key or "").strip()

    def _require_key(self) -> None:
        if not self.api_key:
            raise ProviderNotConfigured("KRX_API_KEY가 설정되지 않았습니다.")

    @staticmethod
    def _format_date(value: str | date) -> str:
        if isinstance(value, date):
            return value.strftime("%Y%m%d")
        compact = value.replace("-", "").strip()
        if len(compact) != 8 or not compact.isdigit():
            raise ValueError("KRX 기준일자는 YYYY-MM-DD 또는 YYYYMMDD 형식이어야 합니다.")
        return compact

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value in (None, "", "-"):
            return None
        try:
            return int(str(value).replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value in (None, "", "-"):
            return None
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None

    async def _get_rows(self, endpoint: KrxEndpoint, bas_dd: str) -> list[dict[str, Any]]:
        self._require_key()
        cache_key = (endpoint.path, bas_dd)
        cached = self._rows_cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}/{endpoint.path}"
        headers = {"AUTH_KEY": self.api_key}
        params = {"basDd": bas_dd}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"KRX 연결 실패: {exc}") from exc

        if response.status_code != 200:
            raise ProviderError(
                f"KRX 요청 실패 ({response.status_code}). 인증키와 해당 API 활용신청 상태를 확인하세요."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("KRX가 JSON이 아닌 응답을 반환했습니다.") from exc

        rows = payload.get("OutBlock_1")
        if not isinstance(rows, list):
            raise ProviderError("KRX 응답에 OutBlock_1 데이터가 없습니다.")

        self._rows_cache[cache_key] = rows
        return rows

    @staticmethod
    def _candidate_dates(as_of: str | date | None, lookback_days: int) -> list[date]:
        if as_of is None:
            current = date.today()
        elif isinstance(as_of, date):
            current = as_of
        else:
            compact = as_of.replace("-", "").strip()
            if len(compact) != 8 or not compact.isdigit():
                raise ValueError("기준일자는 YYYY-MM-DD 또는 YYYYMMDD 형식이어야 합니다.")
            current = date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))

        result: list[date] = []
        for offset in range(max(lookback_days, 1)):
            candidate = current - timedelta(days=offset)
            if candidate.weekday() < 5:  # 토/일은 API 호출 전 제외
                result.append(candidate)
        return result

    async def stock_daily(self, market: str, bas_date: str | date, code: str | None = None) -> dict[str, Any]:
        market_key = market.upper().strip()
        endpoint = self.STOCK_ENDPOINTS.get(market_key)
        if endpoint is None:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")

        bas_dd = self._format_date(bas_date)
        rows = await self._get_rows(endpoint, bas_dd)

        if code:
            code = code.strip()
            rows = [row for row in rows if str(row.get("ISU_CD", "")).strip() == code]

        normalized = [
            {
                "date": row.get("BAS_DD"),
                "code": row.get("ISU_CD"),
                "name": row.get("ISU_NM"),
                "market": row.get("MKT_NM"),
                "section": row.get("SECT_TP_NM"),
                "close": self._as_int(row.get("TDD_CLSPRC")),
                "change": self._as_int(row.get("CMPPREVDD_PRC")),
                "change_rate": self._as_float(row.get("FLUC_RT")),
                "open": self._as_int(row.get("TDD_OPNPRC")),
                "high": self._as_int(row.get("TDD_HGPRC")),
                "low": self._as_int(row.get("TDD_LWPRC")),
                "volume": self._as_int(row.get("ACC_TRDVOL")),
                "trade_value": self._as_int(row.get("ACC_TRDVAL")),
                "market_cap": self._as_int(row.get("MKTCAP")),
                "listed_shares": self._as_int(row.get("LIST_SHRS")),
            }
            for row in rows
        ]

        return {
            "provider": "KRX",
            "endpoint": endpoint.path,
            "market": market_key,
            "date": bas_dd,
            "count": len(normalized),
            "rows": normalized,
        }

    async def latest_stock_daily(
        self,
        market: str,
        code: str,
        as_of: str | date | None = None,
        lookback_days: int = 14,
    ) -> dict[str, Any]:
        for candidate in self._candidate_dates(as_of, lookback_days):
            result = await self.stock_daily(market, candidate, code)
            if result["count"] > 0:
                result["requested_date"] = self._format_date(as_of or date.today())
                result["fallback_used"] = result["date"] != result["requested_date"]
                return result
        raise ProviderError(f"최근 {lookback_days}일 범위에서 해당 종목의 KRX 일별 데이터를 찾지 못했습니다.")

    async def index_daily(self, market: str, bas_date: str | date) -> dict[str, Any]:
        market_key = market.upper().strip()
        endpoint = self.INDEX_ENDPOINTS.get(market_key)
        if endpoint is None:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")

        bas_dd = self._format_date(bas_date)
        rows = await self._get_rows(endpoint, bas_dd)
        normalized = [
            {
                "date": row.get("BAS_DD"),
                "class": row.get("IDX_CLSS"),
                "name": row.get("IDX_NM"),
                "close": self._as_float(row.get("CLSPRC_IDX")),
                "change": self._as_float(row.get("CMPPREVDD_IDX")),
                "change_rate": self._as_float(row.get("FLUC_RT")),
                "open": self._as_float(row.get("OPNPRC_IDX")),
                "high": self._as_float(row.get("HGPRC_IDX")),
                "low": self._as_float(row.get("LWPRC_IDX")),
                "volume": self._as_int(row.get("ACC_TRDVOL")),
                "trade_value": self._as_int(row.get("ACC_TRDVAL")),
                "market_cap": self._as_int(row.get("MKTCAP")),
            }
            for row in rows
        ]

        return {
            "provider": "KRX",
            "endpoint": endpoint.path,
            "market": market_key,
            "date": bas_dd,
            "count": len(normalized),
            "rows": normalized,
        }

    async def latest_index_daily(
        self,
        market: str,
        as_of: str | date | None = None,
        lookback_days: int = 14,
    ) -> dict[str, Any]:
        market_key = market.upper().strip()
        for candidate in self._candidate_dates(as_of, lookback_days):
            result = await self.index_daily(market_key, candidate)
            if result["count"] > 0:
                # 시리즈 API에는 여러 지수가 포함되므로 대표 지수를 별도 제공합니다.
                main = next(
                    (row for row in result["rows"] if str(row.get("name", "")).upper() == market_key),
                    result["rows"][0] if result["rows"] else None,
                )
                result["main_index"] = main
                result["requested_date"] = self._format_date(as_of or date.today())
                result["fallback_used"] = result["date"] != result["requested_date"]
                return result
        raise ProviderError(f"최근 {lookback_days}일 범위에서 {market_key} 지수 데이터를 찾지 못했습니다.")
