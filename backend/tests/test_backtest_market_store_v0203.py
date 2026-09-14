from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.backtest.history_store import HistoricalStore
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.service import BacktestService


class _NoopEngine:
    pass


class _MarketWideFakeKrx:
    def __init__(self) -> None:
        self.calls = {"stock": 0, "index": 0}
        self._stats = {
            "memory_hits": 0,
            "disk_hits": 0,
            "empty_marker_hits": 0,
            "network_requests": 0,
            "retries": 0,
        }

    @staticmethod
    def _today_kst() -> date:
        return date(2026, 9, 14)

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

    def assert_budget(self, _estimated):
        return {"used": self._stats["network_requests"], "safe_limit": 8000, "remaining": 8000}

    def budget_snapshot(self):
        used = self._stats["network_requests"]
        return {"used": used, "safe_limit": 8000, "remaining": 8000 - used}

    async def stock_daily(self, _market, day):
        self.calls["stock"] += 1
        self._stats["network_requests"] += 1
        key = day.strftime("%Y%m%d")
        return {
            "count": 2,
            "rows": [
                {"date": key, "code": "005930", "close": 100, "open": 99, "high": 101, "low": 98, "volume": 10},
                {"date": key, "code": "000660", "close": 200, "open": 199, "high": 201, "low": 198, "volume": 20},
            ],
        }

    async def index_daily(self, _market, day):
        self.calls["index"] += 1
        self._stats["network_requests"] += 1
        key = day.strftime("%Y%m%d")
        return {"count": 1, "rows": [{"date": key, "name": "코스피", "close": 2500.0}]}


@pytest.mark.asyncio
async def test_second_symbol_reuses_same_market_days_without_krx_calls(tmp_path):
    provider = _MarketWideFakeKrx()
    service = BacktestService(
        provider,
        engine=_NoopEngine(),
        history_store=HistoricalStore(tmp_path / "legacy"),
        market_store=HistoricalMarketStore(tmp_path / "market.sqlite3"),
    )

    first_cfg = SimpleNamespace(code="005930", market="KOSPI")
    first_rows, _, _, _, _ = await service._prepare_history(
        config=first_cfg,
        start=date(2026, 6, 1),
        end=date(2026, 6, 5),
        progress=None,
    )
    assert first_rows
    assert provider.calls["stock"] > 0
    assert provider.calls["index"] > 0

    provider.calls = {"stock": 0, "index": 0}
    before_network = provider._stats["network_requests"]
    second_cfg = SimpleNamespace(code="000660", market="KOSPI")
    second_rows, _, _, _, stats = await service._prepare_history(
        config=second_cfg,
        start=date(2026, 6, 1),
        end=date(2026, 6, 5),
        progress=None,
    )

    assert second_rows
    assert provider.calls == {"stock": 0, "index": 0}
    assert provider._stats["network_requests"] == before_network
    assert stats["network_requests"] == 0
    assert stats["market_store_hits"] > 0
