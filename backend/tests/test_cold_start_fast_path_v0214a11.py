from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.backtest.history_store import HistoricalStore
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.service import BacktestService


class _NoopEngine:
    pass


class _ColdProvider:
    """Every day is a true HTTP miss; single-stock path must still pass code."""

    def __init__(self) -> None:
        self.stock_codes: list[str | None] = []
        self._stats = {
            "memory_hits": 0,
            "disk_hits": 0,
            "empty_marker_hits": 0,
            "network_requests": 0,
            "retries": 0,
        }

    @staticmethod
    def _today_kst() -> date:
        return date(2026, 9, 15)

    @staticmethod
    def _is_stable_empty_date(_key: str) -> bool:
        return True

    @staticmethod
    def _select_main_index(rows, _market):
        return rows[0] if rows else None

    def request_stats(self):
        return dict(self._stats)

    def has_cached_day(self, _market, _day, _kind):
        return False

    def assert_budget(self, estimated):
        assert estimated >= 0
        return {"used": 0, "safe_limit": 8000, "remaining": 8000}

    def budget_snapshot(self):
        return {"used": self._stats["network_requests"], "safe_limit": 8000, "remaining": 8000}

    async def stock_daily(self, market, day, code=None):
        # This is the regression guard: even true network misses must NOT request
        # full normalized market rows on a single-stock backtest path.
        self.stock_codes.append(code)
        assert code == "003670"
        self._stats["network_requests"] += 1
        key = day.strftime("%Y%m%d")
        return {
            "count": 1,
            "rows": [{
                "date": key,
                "code": code,
                "market": market,
                "close": 100,
                "open": 99,
                "high": 101,
                "low": 98,
                "volume": 1000,
            }],
        }

    async def index_daily(self, _market, day):
        self._stats["network_requests"] += 1
        key = day.strftime("%Y%m%d")
        return {"count": 1, "rows": [{"date": key, "name": "코스피", "close": 2500.0}]}


@pytest.mark.asyncio
async def test_cold_start_network_miss_still_uses_selected_symbol_only(tmp_path, monkeypatch):
    provider = _ColdProvider()
    market_store = HistoricalMarketStore(tmp_path / "market.sqlite3")

    def fail_stock_promotion(*_args, **_kwargs):
        raise AssertionError("single-stock cold start must not synchronously promote whole market rows")

    def fail_index_promotion(*_args, **_kwargs):
        raise AssertionError("single-stock cold start must not synchronously promote index rows")

    monkeypatch.setattr(market_store, "put_stock_day", fail_stock_promotion)
    monkeypatch.setattr(market_store, "put_index_day", fail_index_promotion)

    service = BacktestService(
        provider,
        engine=_NoopEngine(),
        history_store=HistoricalStore(tmp_path / "legacy"),
        market_store=market_store,
    )
    progress: list[dict] = []
    cfg = SimpleNamespace(code="003670", market="KOSPI")

    stock_rows, index_rows, warnings, _warmup_start, stats = await service._prepare_history(
        config=cfg,
        start=date(2026, 6, 1),
        end=date(2026, 6, 10),
        progress=progress.append,
    )

    assert stock_rows and index_rows
    assert not warnings
    assert provider.stock_codes
    assert all(code == "003670" for code in provider.stock_codes)
    assert stats["network_requests"] > 0
    assert stats["cold_start_fast_path"] is True
    assert stats["market_wide_sqlite_promotions"] == 0
    assert stats["concurrency"] == 12

    data_events = [event for event in progress if event.get("stage") == "data_prepare"]
    assert data_events
    assert any(event["details"].get("network_symbol_fast_path_hits", 0) > 0 for event in data_events)
    assert all(event["details"].get("market_wide_sqlite_promotions") == 0 for event in data_events)
    assert all(event["details"].get("cold_start_fast_path") is True for event in data_events)


def test_cold_start_uses_full_provider_concurrency_cap():
    assert BacktestService.FETCH_CONCURRENCY == 12
    assert BacktestService.MAX_FETCH_CONCURRENCY == 12
    assert BacktestService.MIN_FETCH_CONCURRENCY == 4


class _RawCachingProvider(_ColdProvider):
    """Simulates KrxProvider: first HTTP miss seeds a shared raw date cache."""

    def __init__(self) -> None:
        super().__init__()
        self.cached_stock: set[str] = set()
        self.cached_index: set[str] = set()
        self.inflight = 0
        self.max_inflight = 0

    def has_cached_day(self, _market, day, kind):
        key = day.strftime("%Y%m%d")
        return key in (self.cached_stock if kind == "stock" else self.cached_index)

    async def _enter(self):
        import asyncio
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        await asyncio.sleep(0.001)

    def _leave(self):
        self.inflight -= 1

    async def stock_daily(self, market, day, code=None):
        assert code is not None
        self.stock_codes.append(code)
        key = day.strftime("%Y%m%d")
        await self._enter()
        try:
            if key in self.cached_stock:
                self._stats["disk_hits"] += 1
            else:
                self.cached_stock.add(key)
                self._stats["network_requests"] += 1
            return {
                "count": 1,
                "rows": [{
                    "date": key,
                    "code": code,
                    "market": market,
                    "close": 100,
                    "open": 99,
                    "high": 101,
                    "low": 98,
                    "volume": 1000,
                }],
            }
        finally:
            self._leave()

    async def index_daily(self, _market, day):
        key = day.strftime("%Y%m%d")
        await self._enter()
        try:
            if key in self.cached_index:
                self._stats["disk_hits"] += 1
            else:
                self.cached_index.add(key)
                self._stats["network_requests"] += 1
            return {"count": 1, "rows": [{"date": key, "name": "코스피", "close": 2500.0}]}
        finally:
            self._leave()


@pytest.mark.asyncio
async def test_first_symbol_seeds_shared_raw_cache_and_second_symbol_needs_no_http(tmp_path):
    provider = _RawCachingProvider()
    service = BacktestService(
        provider,
        engine=_NoopEngine(),
        history_store=HistoricalStore(tmp_path / "legacy"),
        market_store=HistoricalMarketStore(tmp_path / "market.sqlite3"),
    )

    first = SimpleNamespace(code="003670", market="KOSPI")
    _rows, _idx, _warn, _warm, first_stats = await service._prepare_history(
        config=first,
        start=date(2026, 6, 1),
        end=date(2026, 6, 10),
        progress=None,
    )
    assert first_stats["network_requests"] > 0
    assert provider.max_inflight >= 4

    network_before = provider._stats["network_requests"]
    second = SimpleNamespace(code="005930", market="KOSPI")
    rows2, _idx2, _warn2, _warm2, second_stats = await service._prepare_history(
        config=second,
        start=date(2026, 6, 1),
        end=date(2026, 6, 10),
        progress=None,
    )

    assert rows2
    assert provider._stats["network_requests"] == network_before
    assert second_stats["network_requests"] == 0
    assert second_stats["cached_symbol_fast_path_hits"] > 0
