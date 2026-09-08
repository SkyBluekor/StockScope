from __future__ import annotations

import asyncio
import gzip
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.core.stock_code import normalize_stock_code
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

    BASIC_INFO_ENDPOINTS = {
        "KOSPI": KrxEndpoint("sto/stk_isu_base_info", "유가증권 종목기본정보"),
        "KOSDAQ": KrxEndpoint("sto/ksq_isu_base_info", "코스닥 종목기본정보"),
    }

    _rows_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    _cache_dir = Path(__file__).resolve().parents[3] / "runtime" / "krx"

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

    @staticmethod
    def _select_main_index(
        rows: list[dict[str, Any]],
        market: str,
    ) -> dict[str, Any] | None:
        target_name = {
            "KOSPI": "코스피",
            "KOSDAQ": "코스닥",
        }.get(market.upper())

        if target_name:
            for row in rows:
                if row.get("name") == target_name and row.get("close") is not None:
                    return row

        # KRX 응답 순서가 바뀌어도 null 대표값은 피합니다.
        for row in rows:
            if row.get("close") is not None:
                return row
        return None

    @classmethod
    def _disk_cache_path(cls, endpoint: KrxEndpoint, bas_dd: str) -> Path:
        safe_name = endpoint.path.replace("/", "__")
        return cls._cache_dir / f"{safe_name}__{bas_dd}.json.gz"

    @classmethod
    def _load_disk_cache(cls, endpoint: KrxEndpoint, bas_dd: str) -> list[dict[str, Any]] | None:
        path = cls._disk_cache_path(endpoint, bas_dd)
        if not path.exists():
            return None
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fp:
                payload = json.load(fp)
            return payload if isinstance(payload, list) else None
        except (OSError, json.JSONDecodeError):
            return None

    @classmethod
    def _save_disk_cache(
        cls,
        endpoint: KrxEndpoint,
        bas_dd: str,
        rows: list[dict[str, Any]],
    ) -> None:
        try:
            cls._cache_dir.mkdir(parents=True, exist_ok=True)
            path = cls._disk_cache_path(endpoint, bas_dd)
            with gzip.open(path, "wt", encoding="utf-8") as fp:
                json.dump(rows, fp, ensure_ascii=False, separators=(",", ":"))
        except OSError:
            # 캐시 실패가 실제 데이터 조회를 막으면 안 됩니다.
            pass

    async def _get_rows(self, endpoint: KrxEndpoint, bas_dd: str) -> list[dict[str, Any]]:
        self._require_key()
        cache_key = (endpoint.path, bas_dd)

        cached = self._rows_cache.get(cache_key)
        if cached is not None:
            return cached

        disk_cached = self._load_disk_cache(endpoint, bas_dd)
        if disk_cached is not None:
            self._rows_cache[cache_key] = disk_cached
            return disk_cached

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
        self._save_disk_cache(endpoint, bas_dd, rows)
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
            if candidate.weekday() < 5:
                result.append(candidate)
        return result

    async def stock_daily(
        self,
        market: str,
        bas_date: str | date,
        code: str | None = None,
    ) -> dict[str, Any]:
        market_key = market.upper().strip()
        endpoint = self.STOCK_ENDPOINTS.get(market_key)
        if endpoint is None:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")

        bas_dd = self._format_date(bas_date)
        rows = await self._get_rows(endpoint, bas_dd)

        if code:
            code = normalize_stock_code(code)
            rows = [
                row
                for row in rows
                if str(row.get("ISU_CD", "")).strip().upper() == code
            ]

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

    async def basic_info(
        self,
        market: str,
        bas_date: str | date,
    ) -> dict[str, Any]:
        market_key = market.upper().strip()
        endpoint = self.BASIC_INFO_ENDPOINTS.get(market_key)
        if endpoint is None:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")

        bas_dd = self._format_date(bas_date)
        rows = await self._get_rows(endpoint, bas_dd)
        normalized = [
            {
                "code": str(row.get("ISU_SRT_CD") or "").strip().upper(),
                "standard_code": str(row.get("ISU_CD") or "").strip(),
                "name": str(row.get("ISU_ABBRV") or row.get("ISU_NM") or "").strip(),
                "full_name": str(row.get("ISU_NM") or "").strip(),
                "english_name": str(row.get("ISU_ENG_NM") or "").strip(),
                "market": market_key,
                "market_name": str(row.get("MKT_TP_NM") or "").strip(),
                "security_group": str(row.get("SECUGRP_NM") or "").strip(),
                "section": str(row.get("SECT_TP_NM") or "").strip(),
                "stock_type": str(row.get("KIND_STKCERT_TP_NM") or "").strip(),
                "listed_date": str(row.get("LIST_DD") or "").strip(),
                "listed_shares": self._as_int(row.get("LIST_SHRS")),
            }
            for row in rows
            if str(row.get("ISU_SRT_CD") or "").strip()
        ]
        return {
            "provider": "KRX",
            "endpoint": endpoint.path,
            "market": market_key,
            "date": bas_dd,
            "count": len(normalized),
            "rows": normalized,
        }

    async def latest_basic_info(
        self,
        market: str,
        as_of: str | date | None = None,
        lookback_days: int = 14,
    ) -> dict[str, Any]:
        for candidate in self._candidate_dates(as_of, lookback_days):
            result = await self.basic_info(market, candidate)
            if result["count"] > 0:
                result["requested_date"] = self._format_date(as_of or date.today())
                result["fallback_used"] = result["date"] != result["requested_date"]
                return result
        raise ProviderError(f"최근 {lookback_days}일 범위에서 {market.upper()} 종목기본정보를 찾지 못했습니다.")

    async def search_stocks(
        self,
        query: str,
        market: str | None = None,
        limit: int = 12,
        as_of: str | date | None = None,
    ) -> dict[str, Any]:
        q = query.strip()
        if not q:
            return {"provider": "KRX", "query": query, "count": 0, "rows": [], "warnings": []}

        market_keys = [market.upper()] if market else ["KOSPI", "KOSDAQ"]
        for key in market_keys:
            if key not in self.BASIC_INFO_ENDPOINTS:
                raise ValueError("market은 KOSPI, KOSDAQ 또는 생략이어야 합니다.")

        results = await asyncio.gather(
            *(self.latest_basic_info(key, as_of) for key in market_keys),
            return_exceptions=True,
        )
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        dates: dict[str, str] = {}
        errors: list[Exception] = []
        for key, result in zip(market_keys, results):
            if isinstance(result, Exception):
                errors.append(result)
                warnings.append(f"{key} 종목기본정보 조회 실패: {result}")
                continue
            dates[key] = result["date"]
            rows.extend(result["rows"])

        if not rows and errors:
            raise errors[0]

        compact_q = q.replace(" ", "").lower()

        def rank(row: dict[str, Any]) -> tuple[int, str, str]:
            code = str(row.get("code") or "").lower()
            name = str(row.get("name") or "")
            full_name = str(row.get("full_name") or "")
            english_name = str(row.get("english_name") or "")
            candidates = [name, full_name, english_name]
            compact_names = [value.replace(" ", "").lower() for value in candidates if value]

            if code == compact_q:
                score = 0
            elif any(value == compact_q for value in compact_names):
                score = 1
            elif code.startswith(compact_q):
                score = 2
            elif any(value.startswith(compact_q) for value in compact_names):
                score = 3
            elif compact_q in code:
                score = 4
            elif any(compact_q in value for value in compact_names):
                score = 5
            else:
                score = 99
            return score, name, code

        matched = [row for row in rows if rank(row)[0] < 99]
        matched.sort(key=rank)
        selected = matched[: max(1, min(limit, 30))]
        return {
            "provider": "KRX",
            "query": q,
            "count": len(selected),
            "rows": selected,
            "data_dates": dates,
            "warnings": warnings,
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

    async def stock_history(
        self,
        market: str,
        code: str,
        as_of: str | date | None = None,
        points: int = 30,
        lookback_days: int = 60,
        concurrency: int = 5,
    ) -> list[dict[str, Any]]:
        """최근 거래일 OHLCV를 오래된 날짜 -> 최신 날짜 순으로 반환합니다.

        KRX Open API는 날짜 단위 bulk API이므로 첫 호출은 여러 날짜를 조회합니다.
        날짜별 원본 응답은 backend/runtime/krx에 gzip 캐시하여 이후 같은 시장의
        다른 종목 분석에서도 재사용합니다.
        """
        wanted = min(max(points, 20), 60)
        dates = self._candidate_dates(as_of, lookback_days)
        found: list[dict[str, Any]] = []

        for start in range(0, len(dates), max(1, concurrency)):
            batch = dates[start : start + max(1, concurrency)]
            results = await asyncio.gather(
                *(self.stock_daily(market, candidate, code) for candidate in batch),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception) or result["count"] == 0:
                    continue
                row = result["rows"][0]
                if row.get("close") is not None:
                    found.append(row)
            if len(found) >= wanted:
                break

        found.sort(key=lambda row: str(row.get("date") or ""))
        return found[-wanted:]

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

    async def index_history(
        self,
        market: str,
        as_of: str | date | None = None,
        points: int = 7,
        lookback_days: int = 30,
    ) -> list[dict[str, Any]]:
        market_key = market.upper().strip()
        wanted = min(max(points, 2), 20)
        found: list[dict[str, Any]] = []
        seen_dates: set[str] = set()

        for candidate in self._candidate_dates(as_of, lookback_days):
            result = await self.index_daily(market_key, candidate)
            if result["count"] == 0:
                continue
            main = self._select_main_index(result["rows"], market_key)
            if not main:
                continue
            row_date = str(main.get("date") or result["date"])
            if row_date in seen_dates:
                continue
            seen_dates.add(row_date)
            found.append(main)
            if len(found) >= wanted:
                break

        return list(reversed(found))

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
                main = self._select_main_index(result["rows"], market_key)
                result["main_index"] = main
                result["requested_date"] = self._format_date(as_of or date.today())
                result["fallback_used"] = result["date"] != result["requested_date"]
                return result
        raise ProviderError(f"최근 {lookback_days}일 범위에서 {market_key} 지수 데이터를 찾지 못했습니다.")
