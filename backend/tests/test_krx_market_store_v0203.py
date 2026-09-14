from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.backtest.history_store import HistorySeries
from app.backtest.market_store import HistoricalMarketStore
from app.market.krx_budget import KrxApiBudget, KrxBudgetExceeded
from app.market.providers.krx import KrxProvider


def test_budget_persists_and_blocks_before_safe_limit(tmp_path):
    path = tmp_path / "budget.sqlite3"
    first = KrxApiBudget(path, safe_limit=3)
    assert first.snapshot().used == 0
    first.consume()
    first.consume(retry=True)
    assert first.snapshot().used == 2
    assert first.snapshot().retries == 1

    restarted = KrxApiBudget(path, safe_limit=3)
    assert restarted.snapshot().used == 2
    with pytest.raises(KrxBudgetExceeded):
        restarted.assert_can_start(2)
    restarted.consume()
    with pytest.raises(KrxBudgetExceeded):
        restarted.consume()


def test_market_store_reuses_market_day_across_symbols(tmp_path):
    store = HistoricalMarketStore(tmp_path / "market.sqlite3")
    rows = [
        {"date": "20260910", "code": "005930", "close": 100, "open": 99, "high": 101, "low": 98},
        {"date": "20260910", "code": "000660", "close": 200, "open": 198, "high": 202, "low": 197},
    ]
    assert store.put_stock_day("KOSPI", "20260910", rows, stable=True) == 2
    assert store.day_complete("KOSPI", "20260910", "stock") is True
    assert store.has_stock_row("KOSPI", "005930", "20260910") is True
    assert store.has_stock_row("KOSPI", "000660", "20260910") is True
    assert store.stock_series("KOSPI", "005930").rows["20260910"]["close"] == 100
    assert store.stock_series("KOSPI", "000660").rows["20260910"]["close"] == 200


def test_legacy_symbol_history_import_does_not_mark_whole_market_complete(tmp_path):
    store = HistoricalMarketStore(tmp_path / "market.sqlite3")
    legacy = HistorySeries(
        rows={"20260910": {"date": "20260910", "code": "005930", "close": 100}},
        checked_dates={"20260910"},
    )
    store.import_legacy_stock("KOSPI", "005930", legacy)
    assert store.has_stock_row("KOSPI", "005930", "20260910") is True
    assert store.day_complete("KOSPI", "20260910", "stock") is False
    assert store.has_stock_row("KOSPI", "000660", "20260910") is False


@pytest.mark.asyncio
async def test_same_provider_same_day_inflight_is_single_network_request(tmp_path, monkeypatch):
    budget = KrxApiBudget(tmp_path / "budget.sqlite3", safe_limit=20)
    provider = KrxProvider("key", budget=budget)
    monkeypatch.setattr(KrxProvider, "_cache_dir", tmp_path / "raw")
    monkeypatch.setattr(KrxProvider, "_today_kst", staticmethod(lambda: date(2026, 9, 14)))
    KrxProvider._rows_cache.clear()
    KrxProvider._cache_expiry.clear()
    KrxProvider._inflight_tasks.clear()
    calls = 0

    async def fake_request(endpoint, bas_dd):
        nonlocal calls
        calls += 1
        # Mimic the real reservation because this test stubs _request_rows itself.
        provider.budget.consume()
        provider._request_stats["network_requests"] += 1
        await asyncio.sleep(0.01)
        return [{"BAS_DD": bas_dd, "ISU_CD": "005930"}]

    monkeypatch.setattr(provider, "_request_rows", fake_request)
    endpoint = provider.STOCK_ENDPOINTS["KOSPI"]
    a, b = await asyncio.gather(
        provider._get_rows(endpoint, "20260910"),
        provider._get_rows(endpoint, "20260910"),
    )
    assert a == b
    assert calls == 1
    assert budget.snapshot().used == 1


def test_raw_cache_detection_avoids_preflight_overestimate(tmp_path, monkeypatch):
    budget = KrxApiBudget(tmp_path / "budget.sqlite3", safe_limit=20)
    provider = KrxProvider("key", budget=budget)
    cache_dir = tmp_path / "raw"
    monkeypatch.setattr(KrxProvider, "_cache_dir", cache_dir)
    monkeypatch.setattr(KrxProvider, "_today_kst", staticmethod(lambda: date(2026, 9, 14)))
    KrxProvider._rows_cache.clear()
    KrxProvider._cache_expiry.clear()
    KrxProvider._inflight_tasks.clear()
    endpoint = provider.STOCK_ENDPOINTS["KOSPI"]
    provider._save_disk_cache(endpoint, "20260910", [{"BAS_DD": "20260910", "ISU_CD": "005930"}])
    assert provider.has_cached_day("KOSPI", "20260910", "stock") is True
    assert provider.has_cached_day("KOSPI", "20260911", "stock") is False


@pytest.mark.asyncio
async def test_two_provider_instances_share_same_inflight_request(tmp_path, monkeypatch):
    budget = KrxApiBudget(tmp_path / "budget.sqlite3", safe_limit=20)
    first = KrxProvider("key", budget=budget)
    second = KrxProvider("key", budget=budget)
    monkeypatch.setattr(KrxProvider, "_cache_dir", tmp_path / "raw")
    monkeypatch.setattr(KrxProvider, "_today_kst", staticmethod(lambda: date(2026, 9, 14)))
    KrxProvider._rows_cache.clear()
    KrxProvider._cache_expiry.clear()
    KrxProvider._inflight_tasks.clear()
    calls = 0

    async def fake_request(endpoint, bas_dd):
        nonlocal calls
        calls += 1
        budget.consume()
        first._request_stats["network_requests"] += 1
        await asyncio.sleep(0.01)
        return [{"BAS_DD": bas_dd, "ISU_CD": "005930"}]

    monkeypatch.setattr(first, "_request_rows", fake_request)
    # If de-duplication fails this should be called and fail the test.
    async def unexpected(*_args, **_kwargs):
        raise AssertionError("duplicate provider request")
    monkeypatch.setattr(second, "_request_rows", unexpected)
    endpoint = first.STOCK_ENDPOINTS["KOSPI"]
    a, b = await asyncio.gather(
        first._get_rows(endpoint, "20260910"),
        second._get_rows(endpoint, "20260910"),
    )
    assert a == b
    assert calls == 1
    assert budget.snapshot().used == 1
