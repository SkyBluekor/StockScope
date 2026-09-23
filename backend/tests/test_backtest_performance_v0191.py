from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.backtest.history_store import HistoricalStore, HistorySeries
from app.backtest.jobs import BacktestJobManager
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.models import BacktestConfig
from app.backtest.service import BacktestService
from app.market.krx_budget import KrxApiBudget
from app.market.providers.krx import KrxProvider


def _weekday_rows(start: date, end: date, *, index: bool = False) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    current = start
    i = 0
    while current <= end:
        if current.weekday() < 5:
            key = current.strftime("%Y%m%d")
            if index:
                rows[key] = {"date": key, "name": "코스피", "close": 2500.0 + i, "change_rate": 0.1}
            else:
                price = 60_000 + i * 100
                rows[key] = {
                    "date": key,
                    "code": "005930",
                    "close": price,
                    "open": price - 50,
                    "high": price + 100,
                    "low": price - 100,
                    "volume": 1_000_000,
                    "trade_value": 2_000_000_000,
                }
            i += 1
        current += timedelta(days=1)
    return rows


class _FakeEngine:
    LIVE_HISTORY_POINTS = 60
    RELATIVE_STRENGTH_POINTS = 61

    def run(self, *, stock_rows, index_rows, config, progress_callback=None, **kwargs):
        if progress_callback:
            progress_callback({
                "stage": "strategy_calculation",
                "message": "테스트 계산",
                "current": 1,
                "total": 1,
                "details": {},
            })
        return {
            "version": "0.19",
            "strategy": "pullback",
            "code": config.code,
            "market": config.market,
            "period": {"start": config.start_date, "end": config.end_date},
            "summary": {"trades": 0},
            "config": {},
            "methodology": {},
        }


@pytest.mark.asyncio
async def test_historical_store_makes_second_run_network_free(tmp_path, monkeypatch):
    start = date(2026, 6, 1)
    end = date(2026, 7, 31)
    all_start = start - timedelta(days=120)
    stock = _weekday_rows(all_start, end)
    indices = _weekday_rows(all_start, end, index=True)

    provider = KrxProvider("test", budget=KrxApiBudget(tmp_path / "budget.sqlite3", safe_limit=8000))
    calls = {"stock": 0, "index": 0}

    async def no_open():
        return None

    async def no_close():
        return None

    async def stock_daily(market, day, code=None):
        calls["stock"] += 1
        key = day.strftime("%Y%m%d")
        row = stock.get(key)
        return {"count": 1 if row else 0, "rows": [row] if row else []}

    async def index_daily(market, day):
        calls["index"] += 1
        key = day.strftime("%Y%m%d")
        row = indices.get(key)
        return {"count": 1 if row else 0, "rows": [row] if row else []}

    monkeypatch.setattr(provider, "open_session", no_open)
    monkeypatch.setattr(provider, "close_session", no_close)
    monkeypatch.setattr(provider, "stock_daily", stock_daily)
    monkeypatch.setattr(provider, "index_daily", index_daily)
    monkeypatch.setattr(provider, "_today_kst", lambda: date(2026, 9, 10))

    service = BacktestService(
        provider,
        engine=_FakeEngine(),
        history_store=HistoricalStore(tmp_path / "legacy"),
        market_store=HistoricalMarketStore(tmp_path / "market.sqlite3"),
    )
    cfg = BacktestConfig(
        code="005930",
        market="KOSPI",
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    first = await service.run_pullback(cfg)
    first_calls = calls["stock"] + calls["index"]
    assert first_calls > 0
    assert first["data_window"]["warmup_start"] == (start - timedelta(days=100)).isoformat()

    calls["stock"] = 0
    calls["index"] = 0
    second = await service.run_pullback(cfg)
    assert calls == {"stock": 0, "index": 0}
    assert second["performance"]["history_store_hits"] > 0


def test_historical_store_merges_without_losing_existing_rows(tmp_path):
    store = HistoricalStore(tmp_path)
    first = HistorySeries(rows={"20260102": {"date": "20260102", "close": 100}}, checked_dates={"20260102"})
    second = HistorySeries(rows={"20260105": {"date": "20260105", "close": 101}}, checked_dates={"20260105"})
    store.save_stock("KOSPI", "005930", first)
    store.save_stock("KOSPI", "005930", second)
    loaded = store.load_stock("KOSPI", "005930")
    assert sorted(loaded.rows) == ["20260102", "20260105"]
    assert loaded.checked_dates == {"20260102", "20260105"}


@pytest.mark.asyncio
async def test_krx_shared_session_reuses_one_async_client(monkeypatch, tmp_path):
    instances = []

    class FakeResponse:
        status_code = 200
        headers = {}
        def __init__(self, bas_dd):
            self.bas_dd = bas_dd
        def json(self):
            return {"OutBlock_1": [{"BAS_DD": self.bas_dd}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.closed = False
            instances.append(self)
        async def get(self, url, headers=None, params=None):
            return FakeResponse(params["basDd"])
        async def aclose(self):
            self.closed = True

    monkeypatch.setattr("app.market.providers.krx.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(KrxProvider, "_cache_dir", tmp_path)
    KrxProvider._rows_cache.clear()
    KrxProvider._cache_expiry.clear()
    provider = KrxProvider("key", budget=KrxApiBudget(tmp_path / "budget.sqlite3", safe_limit=8000))
    endpoint = provider.STOCK_ENDPOINTS["KOSPI"]

    await provider.open_session()
    await provider._get_rows(endpoint, "20260105")
    await provider._get_rows(endpoint, "20260106")
    await provider.close_session()

    assert len(instances) == 1
    assert instances[0].closed is True
    assert provider.request_stats()["network_requests"] == 2


def test_job_manager_progress_completion_and_cancel():
    manager = BacktestJobManager()
    job = manager.create()
    manager.update_progress(job.job_id, {
        "stage": "data_prepare",
        "message": "데이터 준비",
        "current": 25,
        "total": 100,
        "details": {"network_requests": 4},
    })
    public = manager.get(job.job_id).public()  # type: ignore[union-attr]
    assert public["status"] == "running"
    assert public["progress"]["percent"] == 25.0
    assert public["progress"]["details"]["network_requests"] == 4

    manager.complete(job.job_id, {"ok": True})
    completed = manager.get(job.job_id).public()  # type: ignore[union-attr]
    assert completed["status"] == "completed"
    assert completed["result"] == {"ok": True}

    cancel_job = manager.create()
    assert manager.cancel(cancel_job.job_id) is True
    assert manager.get(cancel_job.job_id).public()["status"] == "cancelled"  # type: ignore[union-attr]

@pytest.mark.asyncio
async def test_stable_empty_krx_date_uses_persistent_marker(monkeypatch, tmp_path):
    class EmptyResponse:
        status_code = 200
        headers = {}
        def json(self):
            return {"OutBlock_1": []}

    class FakeClient:
        calls = 0
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def get(self, *args, **kwargs):
            type(self).calls += 1
            return EmptyResponse()

    monkeypatch.setattr("app.market.providers.krx.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(KrxProvider, "_cache_dir", tmp_path)
    monkeypatch.setattr(KrxProvider, "_today_kst", staticmethod(lambda: date(2026, 9, 10)))
    KrxProvider._rows_cache.clear()
    KrxProvider._cache_expiry.clear()
    FakeClient.calls = 0

    provider = KrxProvider("key", budget=KrxApiBudget(tmp_path / "budget.sqlite3", safe_limit=8000))
    endpoint = provider.INDEX_ENDPOINTS["KOSPI"]
    first = await provider._get_rows(endpoint, "20260101")
    assert first == []
    assert FakeClient.calls == 1
    assert provider._empty_marker_path(endpoint, "20260101").exists()

    # Simulate restart/in-memory cache loss. Persistent marker should prevent HTTP.
    KrxProvider._rows_cache.clear()
    KrxProvider._cache_expiry.clear()
    second = await provider._get_rows(endpoint, "20260101")
    assert second == []
    assert FakeClient.calls == 1
    assert provider.request_stats()["empty_marker_hits"] == 1


@pytest.mark.asyncio
async def test_krx_retries_server_error_then_succeeds(monkeypatch, tmp_path):
    class Response:
        headers = {}
        def __init__(self, status_code, rows=None):
            self.status_code = status_code
            self.rows = rows or []
        def json(self):
            return {"OutBlock_1": self.rows}

    class FakeClient:
        responses = [Response(503), Response(200, [{"BAS_DD": "20260102"}])]
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def get(self, *args, **kwargs):
            return type(self).responses.pop(0)

    async def no_sleep(_):
        return None

    monkeypatch.setattr("app.market.providers.krx.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("app.market.providers.krx.asyncio.sleep", no_sleep)
    monkeypatch.setattr(KrxProvider, "_cache_dir", tmp_path)
    KrxProvider._rows_cache.clear()
    KrxProvider._cache_expiry.clear()
    provider = KrxProvider("key", budget=KrxApiBudget(tmp_path / "budget.sqlite3", safe_limit=8000))
    rows = await provider._get_rows(provider.STOCK_ENDPOINTS["KOSPI"], "20260102")
    assert rows[0]["BAS_DD"] == "20260102"
    assert provider.request_stats()["retries"] == 1
    assert provider.request_stats()["network_requests"] == 2
