from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.backtest.history_store import HistoricalStore
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.service import BacktestService


class _NoopEngine:
    pass


class _CachedDailyProvider:
    """Pretend every requested KRX day already exists in the raw gzip cache."""

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
        return True

    def assert_budget(self, estimated):
        assert estimated == 0
        return {"used": 0, "safe_limit": 8000, "remaining": 8000}

    def budget_snapshot(self):
        return {"used": 0, "safe_limit": 8000, "remaining": 8000}

    async def stock_daily(self, market, day, code=None):
        self.stock_codes.append(code)
        self._stats["disk_hits"] += 1
        key = day.strftime("%Y%m%d")
        # The fast path must always ask for the selected code.  A non-fast call
        # deliberately returns peers too so the assertion can catch regressions.
        if code:
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
        return {
            "count": 3,
            "rows": [
                {"date": key, "code": "005930", "close": 100},
                {"date": key, "code": "000660", "close": 200},
                {"date": key, "code": "003670", "close": 300},
            ],
        }

    async def index_daily(self, _market, day):
        self._stats["disk_hits"] += 1
        key = day.strftime("%Y%m%d")
        return {"count": 1, "rows": [{"date": key, "name": "코스피", "close": 2500.0}]}


@pytest.mark.asyncio
async def test_cached_market_days_use_selected_symbol_fast_path(tmp_path):
    provider = _CachedDailyProvider()
    service = BacktestService(
        provider,
        engine=_NoopEngine(),
        history_store=HistoricalStore(tmp_path / "legacy"),
        market_store=HistoricalMarketStore(tmp_path / "market.sqlite3"),
    )
    progress: list[dict] = []
    cfg = SimpleNamespace(code="003670", market="KOSPI")

    stock_rows, index_rows, warnings, _warmup_start, stats = await service._prepare_history(
        config=cfg,
        start=date(2026, 6, 1),
        end=date(2026, 6, 30),
        progress=progress.append,
    )

    assert stock_rows and index_rows
    assert not warnings
    assert provider.stock_codes
    assert all(code == "003670" for code in provider.stock_codes)
    assert stats["network_requests"] == 0
    assert stats["single_stock_fast_path"] is True
    assert stats["cached_symbol_fast_path_hits"] == len(provider.stock_codes)
    assert stats["legacy_rows_imported"] == 0

    data_events = [event for event in progress if event.get("stage") == "data_prepare"]
    assert data_events
    # Progress is now trading-day based, not stock+index item based (2x day count).
    assert all(event["current"] <= event["total"] for event in data_events)
    assert all(event["details"].get("single_stock_fast_path") is True for event in data_events)
    assert max(event["total"] for event in data_events) < 100


@pytest.mark.asyncio
async def test_second_run_reuses_compact_symbol_history_without_provider_calls(tmp_path):
    provider = _CachedDailyProvider()
    service = BacktestService(
        provider,
        engine=_NoopEngine(),
        history_store=HistoricalStore(tmp_path / "legacy"),
        market_store=HistoricalMarketStore(tmp_path / "market.sqlite3"),
    )
    cfg = SimpleNamespace(code="003670", market="KOSPI")

    await service._prepare_history(
        config=cfg,
        start=date(2026, 6, 1),
        end=date(2026, 6, 30),
        progress=None,
    )
    first_calls = len(provider.stock_codes)
    assert first_calls > 0

    provider.stock_codes.clear()
    provider._stats = {
        "memory_hits": 0,
        "disk_hits": 0,
        "empty_marker_hits": 0,
        "network_requests": 0,
        "retries": 0,
    }
    _stock, _index, _warnings, _warmup_start, stats = await service._prepare_history(
        config=cfg,
        start=date(2026, 6, 1),
        end=date(2026, 6, 30),
        progress=None,
    )

    assert provider.stock_codes == []
    assert stats["network_requests"] == 0
    assert stats["raw_cache_hits"] == 0
    assert stats["history_store_hits"] > 0


def test_market_store_status_query_respects_requested_window(tmp_path):
    store = HistoricalMarketStore(tmp_path / "market.sqlite3")
    store.put_stock_day("KOSPI", "20250102", [], stable=True)
    store.put_stock_day("KOSPI", "20260102", [], stable=True)
    store.put_index_day("KOSPI", "20250102", None, stable=True)
    store.put_index_day("KOSPI", "20260102", None, stable=True)

    stock = store.stock_series("KOSPI", "005930", start_dd="20260101", end_dd="20261231")
    index = store.index_series("KOSPI", start_dd="20260101", end_dd="20261231")

    assert stock.checked_dates == {"20260102"}
    assert index.checked_dates == {"20260102"}
