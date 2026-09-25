from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from time import monotonic
from typing import Any

from app.core.stock_code import normalize_stock_code
from app.market.providers.base import ProviderError
from app.news.models import NewsError, NewsResponse
from app.news.naver import NaverNewsProvider
from app.news.policy import NewsSourcePolicy


class NewsService:
    _guard = threading.RLock()
    _cache: dict[tuple[Any, ...], tuple[float, NewsResponse]] = {}
    _inflight: dict[tuple[Any, ...], asyncio.Task[tuple[tuple[Any, ...], str, int]]] = {}
    _max_cache_entries = 256

    def __init__(self, krx: Any, provider: NaverNewsProvider, policy: NewsSourcePolicy) -> None:
        self.krx = krx
        self.provider = provider
        self.policy = policy

    async def _company_name(self, code: str, market: str) -> str:
        try:
            result = await self.krx.search_stocks(code, market, 10)
        except (ProviderError, ValueError) as exc:
            raise NewsError("NEWS_PROVIDER_FAILED", "종목 이름을 확인하지 못했습니다.", retryable=True) from exc
        exact = next(
            (
                row for row in result.get("rows", [])
                if str(row.get("code") or "").strip().upper() == code
                and str(row.get("market") or "").strip().upper() == market
            ),
            None,
        )
        if exact is None:
            raise NewsError("STOCK_NOT_FOUND", "해당 시장에서 종목을 찾지 못했습니다.")
        name = str(exact.get("name") or exact.get("full_name") or "").strip()
        if len(name) < 2:
            raise NewsError("NEWS_QUERY_INVALID", "뉴스 검색에 사용할 회사명을 확인하지 못했습니다.")
        return name

    @staticmethod
    def _normalized_query(value: str) -> str:
        return " ".join(value.split()).casefold()

    @classmethod
    def _trim_cache(cls) -> None:
        now = monotonic()
        expired = [key for key, (expiry, _) in cls._cache.items() if expiry <= now]
        for key in expired:
            cls._cache.pop(key, None)
        if len(cls._cache) <= cls._max_cache_entries:
            return
        ordered = sorted(cls._cache.items(), key=lambda item: item[1][0])
        for key, _ in ordered[: len(cls._cache) - cls._max_cache_entries]:
            cls._cache.pop(key, None)

    async def get_stock_news(self, code: str, market: str, limit: int = 10) -> NewsResponse:
        code = normalize_stock_code(code)
        market = (market or "").strip().upper()
        if market not in {"KOSPI", "KOSDAQ"}:
            raise NewsError("NEWS_QUERY_INVALID", "market은 KOSPI 또는 KOSDAQ이어야 합니다.")
        if not 1 <= limit <= 10:
            raise NewsError("NEWS_QUERY_INVALID", "뉴스 조회 개수는 1~10이어야 합니다.")
        if not self.policy.display_allowed:
            raise NewsError("NEWS_USAGE_NOT_ALLOWED", "현재 source 정책에서는 뉴스 표시가 허용되지 않습니다.")

        company_name = await self._company_name(code, market)
        query = company_name
        key = (
            self.provider.provider_kind,
            self.policy.policy_version,
            self._normalized_query(query),
            "date",
            "ko",
            limit,
        )

        cache_seconds = max(0, int(self.policy.server_cache_seconds))
        if cache_seconds > 0:
            with self._guard:
                self._trim_cache()
                cached = self._cache.get(key)
                if cached and cached[0] > monotonic():
                    return replace(cached[1], cache_hit=True, cache_stale=False)

        loop = asyncio.get_running_loop()
        with self._guard:
            task = self._inflight.get(key)
            if task is None or task.get_loop() is not loop:
                task = loop.create_task(self.provider.search(query, limit))
                self._inflight[key] = task

        try:
            items, fetched_at, discarded = await task
            response = NewsResponse(
                code=code,
                market=market,
                company_name=company_name,
                query=query,
                fetched_at=fetched_at,
                status="ok",
                items=items,
                cache_hit=False,
                cache_stale=False,
                discarded_items=discarded,
            )
            if cache_seconds > 0:
                with self._guard:
                    self._cache[key] = (monotonic() + cache_seconds, response)
                    self._trim_cache()
            return response
        finally:
            with self._guard:
                if self._inflight.get(key) is task:
                    self._inflight.pop(key, None)
