from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta
from typing import Any

import pytest

from app.backtest.scanner import StockScannerService
from app.market.providers.krx import KrxProvider


class _FakeStore:
    def __init__(self) -> None:
        self.stock_writes = 0
        self.index_writes = 0

    def put_stock_day(self, market: str, key: str, rows: list[dict[str, Any]], *, stable: bool) -> int:
        time.sleep(0.001)
        self.stock_writes += 1
        return len(rows)

    def put_index_day(self, market: str, key: str, row: dict[str, Any] | None, *, stable: bool) -> None:
        time.sleep(0.001)
        self.index_writes += 1


class _FakeKrx:
    def __init__(self, *, delay: float = 0.01, retry_calls: set[int] | None = None) -> None:
        self.delay = delay
        self.retry_calls = retry_calls or set()
        self.calls = 0
        self.active = 0
        self.peak = 0
        self.stats = {
            "network_requests": 0,
            "retries": 0,
            "disk_hits": 0,
            "memory_hits": 0,
            "empty_marker_hits": 0,
        }

    def assert_budget(self, estimated: int) -> dict[str, int]:
        return {"estimated": estimated}

    def request_stats(self) -> dict[str, int]:
        return dict(self.stats)

    async def _fetch(self, day: date, *, stock: bool) -> dict[str, Any]:
        self.calls += 1
        call_no = self.calls
        self.stats["network_requests"] += 1
        if call_no in self.retry_calls:
            self.stats["retries"] += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
        finally:
            self.active -= 1
        if stock:
            return {
                "count": 1,
                "rows": [{"date": day.strftime("%Y%m%d"), "code": "005930", "close": 100_000}],
            }
        return {
            "count": 1,
            "rows": [{"date": day.strftime("%Y%m%d"), "name": "코스피", "close": 2500.0}],
        }

    async def stock_daily(self, market: str, day: date) -> dict[str, Any]:
        return await self._fetch(day, stock=True)

    async def index_daily(self, market: str, day: date) -> dict[str, Any]:
        return await self._fetch(day, stock=False)

    @staticmethod
    def _select_main_index(rows: list[dict[str, Any]], market: str) -> dict[str, Any] | None:
        return rows[0] if rows else None


def _plan(count_days: int) -> dict[str, Any]:
    start = date(2026, 1, 2)
    work: list[tuple[str, date]] = []
    for offset in range(count_days):
        day = start + timedelta(days=offset)
        work.append(("stock", day))
        work.append(("index", day))
    return {
        "work": work,
        "total": len(work),
        "reused": 0,
        "estimated_network_requests": len(work),
    }


@pytest.mark.asyncio
async def test_bootstrap_keeps_requests_in_flight_and_persists_every_completed_day() -> None:
    service = object.__new__(StockScannerService)
    service.krx = _FakeKrx(delay=0.01)
    service.market_store = _FakeStore()
    plan = _plan(40)
    started = time.perf_counter()

    result = await service._ensure_market_history(
        market="KOSPI",
        start=date(2026, 1, 2),
        end=date(2026, 1, 2),
        progress=None,
        progress_base=0,
        progress_span=25,
        started_at=started,
        plan=plan,
    )

    assert result["processed_items"] == 80
    assert result["errors"] == 0
    assert 8 <= result["peak_concurrency"] <= 12
    assert service.krx.peak == result["peak_concurrency"]
    assert service.market_store.stock_writes == 40
    assert service.market_store.index_writes == 40


@pytest.mark.asyncio
async def test_bootstrap_adaptive_concurrency_reduces_limit_when_retry_signals_appear() -> None:
    service = object.__new__(StockScannerService)
    service.krx = _FakeKrx(delay=0.003, retry_calls={8, 16, 24})
    service.market_store = _FakeStore()
    plan = _plan(30)

    result = await service._ensure_market_history(
        market="KOSDAQ",
        start=date(2026, 1, 2),
        end=date(2026, 1, 2),
        progress=None,
        progress_base=0,
        progress_span=25,
        started_at=time.perf_counter(),
        plan=plan,
    )

    assert result["processed_items"] == 60
    assert result["peak_concurrency"] <= 12
    assert result["final_concurrency_limit"] < StockScannerService.FETCH_CONCURRENCY_MAX


class _Budget:
    def snapshot(self):
        return type("Snapshot", (), {"as_dict": lambda self: {}})()

    def assert_can_start(self, estimated_requests: int):
        return type("Snapshot", (), {"as_dict": lambda self: {}})()

    def consume(self, *, retry: bool = False):
        return None


@pytest.mark.asyncio
async def test_provider_global_network_limit_caps_parallel_http_requests(monkeypatch) -> None:
    class Response:
        status_code = 200
        headers: dict[str, str] = {}

        def __init__(self, bas_dd: str) -> None:
            self.bas_dd = bas_dd

        def json(self) -> dict[str, Any]:
            return {"OutBlock_1": [{"BAS_DD": self.bas_dd}]}

    class FakeClient:
        active = 0
        peak = 0

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def get(self, url: str, headers=None, params=None):
            type(self).active += 1
            type(self).peak = max(type(self).peak, type(self).active)
            try:
                await asyncio.sleep(0.01)
                return Response(params["basDd"])
            finally:
                type(self).active -= 1

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("app.market.providers.krx.httpx.AsyncClient", FakeClient)
    provider = KrxProvider("key", budget=_Budget())
    provider._max_network_concurrency = 12
    await provider.open_session()
    endpoint = provider.STOCK_ENDPOINTS["KOSPI"]
    try:
        await asyncio.gather(
            *(provider._request_rows(endpoint, f"202601{day:02d}") for day in range(1, 21))
        )
    finally:
        await provider.close_session()

    assert FakeClient.peak == 12
    assert provider.request_stats()["network_requests"] == 20
