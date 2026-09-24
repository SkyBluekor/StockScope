from __future__ import annotations

import asyncio
import gzip
import json
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any, Callable

import httpx

from app.core.stock_code import normalize_stock_code
from app.market.krx_budget import KrxApiBudget
from app.market.kst import today_kst
from app.market.providers.base import ProviderError, ProviderNotConfigured


@dataclass(frozen=True)
class KrxEndpoint:
    path: str
    label: str


class KrxProvider:
    BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"
    DEFAULT_NETWORK_CONCURRENCY = 12

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
    _cache_expiry: dict[tuple[str, str], float] = {}
    _volatile_cache_seconds = 300
    _cache_dir = Path(__file__).resolve().parents[3] / "runtime" / "krx"
    _inflight_guard = threading.RLock()
    _inflight_tasks: dict[tuple[str, str], asyncio.Task[list[dict[str, Any]]]] = {}

    def __init__(self, api_key: str | None, budget: KrxApiBudget | None = None) -> None:
        self.api_key = (api_key or "").strip()
        self.budget = budget or KrxApiBudget()
        self._client: httpx.AsyncClient | None = None
        self._owns_client = False
        raw_limit = os.getenv("KRX_MAX_CONCURRENCY", str(self.DEFAULT_NETWORK_CONCURRENCY)).strip()
        try:
            configured_limit = int(raw_limit)
        except ValueError:
            configured_limit = self.DEFAULT_NETWORK_CONCURRENCY
        self._max_network_concurrency = max(1, min(configured_limit, 24))
        self._network_semaphore: asyncio.Semaphore | None = None
        self._request_stats: dict[str, int] = {
            "memory_hits": 0,
            "disk_hits": 0,
            "empty_marker_hits": 0,
            "network_requests": 0,
            "retries": 0,
            "forced_network_requests": 0,
        }

    async def open_session(self) -> None:
        """Open one reusable HTTP connection pool for bulk/history work."""
        if self._network_semaphore is None:
            self._network_semaphore = asyncio.Semaphore(self._max_network_concurrency)
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                limits=httpx.Limits(
                    max_connections=max(16, self._max_network_concurrency + 4),
                    max_keepalive_connections=max(12, self._max_network_concurrency),
                ),
            )
            self._owns_client = True

    async def close_session(self) -> None:
        if self._client is None or not self._owns_client:
            return
        client = self._client
        self._client = None
        self._owns_client = False
        self._network_semaphore = None
        close = getattr(client, "aclose", None)
        if close is not None:
            await close()

    def request_stats(self) -> dict[str, int]:
        return dict(self._request_stats)

    def budget_snapshot(self) -> dict[str, int | str]:
        return self.budget.snapshot().as_dict()

    def assert_budget(self, estimated_requests: int) -> dict[str, int | str]:
        return self.budget.assert_can_start(estimated_requests).as_dict()

    @classmethod
    def _endpoint_for_kind(cls, market: str, kind: str) -> KrxEndpoint:
        key = market.upper().strip()
        endpoints = cls.STOCK_ENDPOINTS if kind == "stock" else cls.INDEX_ENDPOINTS
        endpoint = endpoints.get(key)
        if endpoint is None:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")
        return endpoint

    def has_cached_day(self, market: str, bas_date: str | date, kind: str) -> bool:
        endpoint = self._endpoint_for_kind(market, kind)
        bas_dd = self._format_date(bas_date)
        key = (endpoint.path, bas_dd)
        expiry = self._cache_expiry.get(key)
        if key in self._rows_cache and (expiry is None or expiry > monotonic()):
            return True
        if self._is_volatile_date(bas_dd):
            return False
        return self._disk_cache_path(endpoint, bas_dd).exists() or self._has_empty_marker(endpoint, bas_dd)

    def cached_daily_snapshot(self, market: str, bas_date: str | date, kind: str) -> dict[str, Any]:
        """Read the currently cached KRX payload without issuing a network request."""
        market_key = market.upper().strip()
        endpoint = self._endpoint_for_kind(market_key, kind)
        bas_dd = self._format_date(bas_date)
        key = (endpoint.path, bas_dd)
        rows: list[dict[str, Any]] | None = None
        source = "none"
        expiry = self._cache_expiry.get(key)
        if key in self._rows_cache and (expiry is None or expiry > monotonic()):
            rows = list(self._rows_cache[key])
            source = "memory"
        elif not self._is_volatile_date(bas_dd):
            rows = self._load_disk_cache(endpoint, bas_dd)
            if rows is not None:
                source = "disk"
            elif self._has_empty_marker(endpoint, bas_dd):
                rows = []
                source = "empty_marker"
        if rows is None:
            return {"source": source, "date": bas_dd, "count": 0, "rows": []}

        if kind == "stock":
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
        else:
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
        return {"source": source, "date": bas_dd, "count": len(normalized), "rows": normalized}

    def _require_key(self) -> None:
        if not self.api_key:
            raise ProviderNotConfigured("KRX_API_KEY가 설정되지 않았습니다.")

    @staticmethod
    def _today_kst() -> date:
        return today_kst()

    @classmethod
    def _is_volatile_date(cls, bas_dd: str) -> bool:
        # 당일/미래 날짜는 KRX가 늦게 게시하거나 정정할 수 있으므로
        # 장기 디스크 캐시로 고정하지 않습니다.
        return bas_dd >= cls._today_kst().strftime("%Y%m%d")

    @classmethod
    def _is_stable_empty_date(cls, bas_dd: str) -> bool:
        """Only persist empty responses far enough in the past to avoid publication-delay traps."""
        try:
            candidate = datetime.strptime(bas_dd, "%Y%m%d").date()
        except ValueError:
            return False
        return candidate <= cls._today_kst() - timedelta(days=3)

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

    @staticmethod
    def _normalize_index_name(value: str | None) -> str:
        return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())

    @classmethod
    def select_index_by_aliases(
        cls,
        rows: list[dict[str, Any]],
        aliases: list[str],
    ) -> dict[str, Any] | None:
        """Select one KRX index row from a list of human-readable aliases.

        Exact normalized-name matches are preferred. Industry/sector class rows get
        priority over thematic/representative indices when names overlap.
        """
        normalized_aliases = [
            (idx, alias, cls._normalize_index_name(alias))
            for idx, alias in enumerate(aliases)
            if cls._normalize_index_name(alias)
        ]
        scored: list[tuple[int, int, int, dict[str, Any], str]] = []
        for row in rows:
            if row.get("close") is None or not row.get("name"):
                continue
            name = str(row.get("name") or "")
            norm_name = cls._normalize_index_name(name)
            class_text = str(row.get("class") or "")
            sector_class = "업종" in class_text or "산업" in class_text
            for alias_index, alias, norm_alias in normalized_aliases:
                if norm_name == norm_alias:
                    match_score = 0
                elif norm_alias in norm_name or norm_name in norm_alias:
                    match_score = 3
                else:
                    continue
                if not sector_class:
                    match_score += 2
                scored.append((match_score, alias_index, len(name), row, alias))
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], item[1], item[2]))
        score, _, _, row, alias = scored[0]
        return {
            **row,
            "matched_alias": alias,
            "match_confidence": "HIGH" if score <= 1 else "MEDIUM",
            "match_confidence_label": "높음" if score <= 1 else "보통",
        }

    @classmethod
    def _disk_cache_path(cls, endpoint: KrxEndpoint, bas_dd: str) -> Path:
        safe_name = endpoint.path.replace("/", "__")
        return cls._cache_dir / f"{safe_name}__{bas_dd}.json.gz"

    @classmethod
    def _empty_marker_path(cls, endpoint: KrxEndpoint, bas_dd: str) -> Path:
        safe_name = endpoint.path.replace("/", "__")
        return cls._cache_dir / f"{safe_name}__{bas_dd}.empty"

    @classmethod
    def _has_empty_marker(cls, endpoint: KrxEndpoint, bas_dd: str) -> bool:
        return cls._empty_marker_path(endpoint, bas_dd).exists()

    @classmethod
    def _save_empty_marker(cls, endpoint: KrxEndpoint, bas_dd: str) -> None:
        if not cls._is_stable_empty_date(bas_dd):
            return
        try:
            cls._cache_dir.mkdir(parents=True, exist_ok=True)
            cls._empty_marker_path(endpoint, bas_dd).touch(exist_ok=True)
        except OSError:
            pass

    @classmethod
    def _clear_empty_marker(cls, endpoint: KrxEndpoint, bas_dd: str) -> None:
        try:
            cls._empty_marker_path(endpoint, bas_dd).unlink(missing_ok=True)
        except OSError:
            pass

    @classmethod
    def _load_disk_cache(cls, endpoint: KrxEndpoint, bas_dd: str) -> list[dict[str, Any]] | None:
        path = cls._disk_cache_path(endpoint, bas_dd)
        if not path.exists():
            return None
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fp:
                payload = json.load(fp)
            if not isinstance(payload, list):
                return None
            if not payload:
                # v0.13 이하에서 저장된 빈 응답 캐시는 최신 데이터 게시 후에도
                # fallback을 고정할 수 있으므로 폐기합니다.
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                return None
            return payload
        except (OSError, json.JSONDecodeError):
            return None

    @classmethod
    def _save_disk_cache(
        cls,
        endpoint: KrxEndpoint,
        bas_dd: str,
        rows: list[dict[str, Any]],
    ) -> None:
        path = cls._disk_cache_path(endpoint, bas_dd)
        temp_path = path.with_name(path.name + ".tmp")
        try:
            cls._cache_dir.mkdir(parents=True, exist_ok=True)
            with gzip.open(temp_path, "wt", encoding="utf-8") as fp:
                json.dump(rows, fp, ensure_ascii=False, separators=(",", ":"))
            os.replace(temp_path, path)
        except OSError:
            # 캐시 실패가 실제 데이터 조회를 막으면 안 됩니다.
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    @classmethod
    def _clear_disk_cache(cls, endpoint: KrxEndpoint, bas_dd: str) -> None:
        try:
            cls._disk_cache_path(endpoint, bas_dd).unlink(missing_ok=True)
        except OSError:
            pass

    async def _request_rows(self, endpoint: KrxEndpoint, bas_dd: str) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL}/{endpoint.path}"
        headers = {"AUTH_KEY": self.api_key}
        params = {"basDd": bas_dd}
        retry_delays = (0.5, 1.0, 2.0)
        last_error: Exception | None = None

        for attempt in range(len(retry_delays) + 1):
            try:
                semaphore = self._network_semaphore
                if semaphore is None:
                    semaphore = asyncio.Semaphore(self._max_network_concurrency)
                    self._network_semaphore = semaphore
                async with semaphore:
                    # Reserve immediately before the real HTTP attempt. SQLite ledger I/O
                    # is pushed off the event loop so concurrent KRX responses stay responsive.
                    await asyncio.to_thread(self.budget.consume, retry=attempt > 0)
                    self._request_stats["network_requests"] += 1
                    if self._client is not None:
                        response = await self._client.get(url, headers=headers, params=params)
                    else:
                        async with httpx.AsyncClient(timeout=15.0) as client:
                            response = await client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= len(retry_delays):
                    raise ProviderError(f"KRX 연결 실패: {exc}") from exc
                self._request_stats["retries"] += 1
                await asyncio.sleep(retry_delays[attempt])
                continue

            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ProviderError("KRX가 JSON이 아닌 응답을 반환했습니다.") from exc
                rows = payload.get("OutBlock_1")
                if not isinstance(rows, list):
                    raise ProviderError("KRX 응답에 OutBlock_1 데이터가 없습니다.")
                return rows

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < len(retry_delays):
                    self._request_stats["retries"] += 1
                    retry_after = None
                    headers_obj = getattr(response, "headers", None)
                    if headers_obj is not None:
                        retry_after = headers_obj.get("Retry-After")
                    try:
                        delay = max(float(retry_after), retry_delays[attempt]) if retry_after else retry_delays[attempt]
                    except (TypeError, ValueError):
                        delay = retry_delays[attempt]
                    await asyncio.sleep(min(delay, 5.0))
                    continue

            raise ProviderError(
                f"KRX 요청 실패 ({response.status_code}). 인증키와 해당 API 활용신청 상태를 확인하세요."
            )

        if last_error is not None:
            raise ProviderError(f"KRX 연결 실패: {last_error}") from last_error
        raise ProviderError("KRX 요청에 실패했습니다.")

    async def _get_rows(self, endpoint: KrxEndpoint, bas_dd: str, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        self._require_key()
        cache_key = (endpoint.path, bas_dd)
        now = monotonic()

        if force_refresh:
            self._request_stats["forced_network_requests"] += 1
            rows = await self._request_rows(endpoint, bas_dd)
            self._rows_cache.pop(cache_key, None)
            self._cache_expiry.pop(cache_key, None)
            if not rows:
                self._rows_cache[cache_key] = []
                self._clear_disk_cache(endpoint, bas_dd)
                if self._is_stable_empty_date(bas_dd):
                    self._save_empty_marker(endpoint, bas_dd)
                else:
                    self._cache_expiry[cache_key] = now + self._volatile_cache_seconds
            else:
                self._clear_empty_marker(endpoint, bas_dd)
                self._rows_cache[cache_key] = rows
                if self._is_volatile_date(bas_dd):
                    self._cache_expiry[cache_key] = now + self._volatile_cache_seconds
                else:
                    await asyncio.to_thread(self._save_disk_cache, endpoint, bas_dd, rows)
            return rows

        expiry = self._cache_expiry.get(cache_key)
        if expiry is not None and expiry <= now:
            self._cache_expiry.pop(cache_key, None)
            self._rows_cache.pop(cache_key, None)

        cached = self._rows_cache.get(cache_key)
        if cached is not None:
            self._request_stats["memory_hits"] += 1
            return cached

        if not self._is_volatile_date(bas_dd):
            disk_cached = await asyncio.to_thread(self._load_disk_cache, endpoint, bas_dd)
            if disk_cached is not None:
                self._request_stats["disk_hits"] += 1
                self._rows_cache[cache_key] = disk_cached
                return disk_cached
            if self._has_empty_marker(endpoint, bas_dd):
                self._request_stats["empty_marker_hits"] += 1
                self._rows_cache[cache_key] = []
                return []

        loop = asyncio.get_running_loop()
        with self._inflight_guard:
            task = self._inflight_tasks.get(cache_key)
            # FastAPI requests normally share one loop. If a test/worker uses another
            # loop, do not await a task bound to the wrong loop.
            if task is None or task.done() or task.get_loop() is not loop:
                task = loop.create_task(self._request_rows(endpoint, bas_dd))
                self._inflight_tasks[cache_key] = task

        try:
            rows = await asyncio.shield(task)
        except Exception:
            with self._inflight_guard:
                if self._inflight_tasks.get(cache_key) is task:
                    self._inflight_tasks.pop(cache_key, None)
            raise

        # Keep the in-flight entry until the shared cache is populated. Otherwise a
        # third caller could slip into the tiny gap after HTTP completion and issue
        # the same request again.
        now = monotonic()
        if not rows:
            self._rows_cache[cache_key] = rows
            if self._is_stable_empty_date(bas_dd):
                self._cache_expiry.pop(cache_key, None)
                self._save_empty_marker(endpoint, bas_dd)
            else:
                # Recent/today empty data can appear before KRX publishes the final daily row.
                self._cache_expiry[cache_key] = now + self._volatile_cache_seconds
        else:
            self._clear_empty_marker(endpoint, bas_dd)
            self._rows_cache[cache_key] = rows
            if self._is_volatile_date(bas_dd):
                self._cache_expiry[cache_key] = now + self._volatile_cache_seconds
            else:
                self._cache_expiry.pop(cache_key, None)
                await asyncio.to_thread(self._save_disk_cache, endpoint, bas_dd, rows)

        with self._inflight_guard:
            if self._inflight_tasks.get(cache_key) is task:
                self._inflight_tasks.pop(cache_key, None)
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
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        market_key = market.upper().strip()
        endpoint = self.STOCK_ENDPOINTS.get(market_key)
        if endpoint is None:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")

        bas_dd = self._format_date(bas_date)
        rows = await self._get_rows(endpoint, bas_dd, force_refresh=force_refresh)

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
        progress: Callable[[int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        """최근 거래일 OHLCV를 오래된 날짜 -> 최신 날짜 순으로 반환합니다.

        KRX Open API는 날짜 단위 bulk API이므로 첫 호출은 여러 날짜를 조회합니다.
        날짜별 원본 응답은 backend/runtime/krx에 gzip 캐시하여 이후 같은 시장의
        다른 종목 분석에서도 재사용합니다.
        """
        wanted = min(max(points, 20), 120)
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
            if progress is not None:
                progress(min(len(found), wanted), wanted)
            if len(found) >= wanted:
                break

        found.sort(key=lambda row: str(row.get("date") or ""))
        return found[-wanted:]

    async def index_daily(self, market: str, bas_date: str | date, *, force_refresh: bool = False) -> dict[str, Any]:
        market_key = market.upper().strip()
        endpoint = self.INDEX_ENDPOINTS.get(market_key)
        if endpoint is None:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")

        bas_dd = self._format_date(bas_date)
        rows = await self._get_rows(endpoint, bas_dd, force_refresh=force_refresh)
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
        concurrency: int = 5,
        progress: Callable[[int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        market_key = market.upper().strip()
        wanted = min(max(points, 2), 120)
        found: list[dict[str, Any]] = []
        seen_dates: set[str] = set()
        dates = self._candidate_dates(as_of, lookback_days)

        for start in range(0, len(dates), max(1, concurrency)):
            batch = dates[start : start + max(1, concurrency)]
            results = await asyncio.gather(
                *(self.index_daily(market_key, candidate) for candidate in batch),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception) or result["count"] == 0:
                    continue
                main = self._select_main_index(result["rows"], market_key)
                if not main:
                    continue
                row_date = str(main.get("date") or result["date"])
                if row_date in seen_dates:
                    continue
                seen_dates.add(row_date)
                found.append(main)
            if progress is not None:
                progress(min(len(found), wanted), wanted)
            if len(found) >= wanted:
                break

        found.sort(key=lambda row: str(row.get("date") or ""))
        return found[-wanted:]

    async def index_alias_history(
        self,
        market: str,
        aliases: list[str],
        as_of: str | date | None = None,
        points: int = 61,
        lookback_days: int = 140,
        concurrency: int = 5,
    ) -> list[dict[str, Any]]:
        """Return one industry/index series selected from aliases for each date."""
        market_key = market.upper().strip()
        wanted = min(max(points, 2), 120)
        found: list[dict[str, Any]] = []
        seen_dates: set[str] = set()
        dates = self._candidate_dates(as_of, lookback_days)

        for start in range(0, len(dates), max(1, concurrency)):
            batch = dates[start : start + max(1, concurrency)]
            results = await asyncio.gather(
                *(self.index_daily(market_key, candidate) for candidate in batch),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception) or result["count"] == 0:
                    continue
                selected = self.select_index_by_aliases(result["rows"], aliases)
                if not selected:
                    continue
                row_date = str(selected.get("date") or result["date"])
                if row_date in seen_dates:
                    continue
                seen_dates.add(row_date)
                found.append(selected)
            if len(found) >= wanted:
                break

        found.sort(key=lambda row: str(row.get("date") or ""))
        return found[-wanted:]

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
