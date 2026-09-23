from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.backtest.scanner import StockScannerService


class FakeStore:
    def __init__(self, latest: str | None) -> None:
        self.stock_days: dict[tuple[str, str], list[dict]] = {}
        self.index_days: dict[tuple[str, str], dict] = {}
        if latest:
            for market in ("KOSPI", "KOSDAQ"):
                self.stock_days[(market, latest)] = [{"date": latest, "code": "000001"}]
                self.index_days[(market, latest)] = {"date": latest, "name": market}

    def latest_complete_date(self, market: str, kind: str = "stock", end_dd: str | None = None) -> str | None:
        source = self.stock_days if kind == "stock" else self.index_days
        dates = sorted(key[1] for key in source if key[0] == market and (end_dd is None or key[1] <= end_dd))
        return dates[-1] if dates else None

    def day_complete(self, market: str, bas_dd: str, kind: str) -> bool:
        source = self.stock_days if kind == "stock" else self.index_days
        return (market, bas_dd) in source

    def put_stock_day(self, market: str, bas_dd: str, rows, *, stable: bool) -> int:
        self.stock_days[(market, bas_dd)] = list(rows)
        return len(self.stock_days[(market, bas_dd)])

    def put_index_day(self, market: str, bas_dd: str, row, *, stable: bool) -> None:
        self.index_days[(market, bas_dd)] = dict(row)


class FakeKrx:
    def __init__(self, today: date, available_day: date, *, fail: bool = False) -> None:
        self.today = today
        self.available_day = available_day
        self.fail = fail
        self.opened = 0
        self.closed = 0
        self.stats = {"network_requests": 0, "memory_hits": 0, "disk_hits": 0, "empty_marker_hits": 0, "retries": 0}

    def _today_kst(self) -> date:
        return self.today

    @staticmethod
    def _candidate_dates(as_of: date, lookback_days: int):
        result = []
        for offset in range(lookback_days):
            candidate = as_of - timedelta(days=offset)
            if candidate.weekday() < 5:
                result.append(candidate)
        return result

    async def open_session(self) -> None:
        self.opened += 1

    async def close_session(self) -> None:
        self.closed += 1

    def request_stats(self):
        return dict(self.stats)

    async def stock_daily(self, market: str, bas_date: date):
        self.stats["network_requests"] += 1
        if self.fail:
            raise RuntimeError("network down")
        key = bas_date.strftime("%Y%m%d")
        if bas_date != self.available_day:
            return {"date": key, "count": 0, "rows": []}
        return {
            "date": key,
            "count": 1,
            "rows": [{"date": key, "code": "000001", "name": "테스트", "close": 10000}],
        }

    async def index_daily(self, market: str, bas_date: date):
        self.stats["network_requests"] += 1
        key = bas_date.strftime("%Y%m%d")
        return {"date": key, "count": 1, "rows": [{"date": key, "name": market, "close": 1000}]}

    @staticmethod
    def _select_main_index(rows, market: str):
        return rows[0] if rows else None


@pytest.mark.asyncio
async def test_freshness_advances_store_and_reports_date_change() -> None:
    store = FakeStore("20260914")
    krx = FakeKrx(date(2026, 9, 16), date(2026, 9, 15))
    service = object.__new__(StockScannerService)
    service.market_store = store
    service.krx = krx

    result = await service.prepare_latest_confirmed_data(market_scope="ALL", known_data_date="2026-09-14")

    assert result["status"] == "UPDATED"
    assert result["resolved_as_of_date"] == "2026-09-15"
    assert result["date_changed"] is True
    assert result["market_data_updated"] is True
    assert result["data_dates"] == {"KOSPI": "2026-09-15", "KOSDAQ": "2026-09-15"}
    assert store.day_complete("KOSPI", "20260915", "stock")
    assert store.day_complete("KOSDAQ", "20260915", "index")
    assert krx.closed == 1


@pytest.mark.asyncio
async def test_freshness_up_to_date_store_avoids_krx_requests() -> None:
    store = FakeStore("20260915")
    krx = FakeKrx(date(2026, 9, 16), date(2026, 9, 15))
    service = object.__new__(StockScannerService)
    service.market_store = store
    service.krx = krx

    result = await service.prepare_latest_confirmed_data(market_scope="ALL", known_data_date="2026-09-15")

    assert result["status"] == "READY"
    assert result["resolved_as_of_date"] == "2026-09-15"
    assert result["date_changed"] is False
    assert result["diagnostics"]["network_requests"] == 4
    assert result["diagnostics"]["data_integrity"]["KOSPI"]["mode"] == "FORCED_KRX_VERIFY"
    assert result["diagnostics"]["data_integrity"]["KOSDAQ"]["mode"] == "FORCED_KRX_VERIFY"


@pytest.mark.asyncio
async def test_freshness_weekend_resolves_previous_trading_day() -> None:
    store = FakeStore("20260917")
    # Monday 9/21 -> requested end is Sunday 9/20, latest trading day is Friday 9/18.
    krx = FakeKrx(date(2026, 9, 21), date(2026, 9, 18))
    service = object.__new__(StockScannerService)
    service.market_store = store
    service.krx = krx

    result = await service.prepare_latest_confirmed_data(market_scope="KOSPI", known_data_date="2026-09-17")

    assert result["resolved_as_of_date"] == "2026-09-18"
    assert result["date_changed"] is True


@pytest.mark.asyncio
async def test_freshness_failure_keeps_previous_date_for_explicit_fallback() -> None:
    store = FakeStore("20260914")
    krx = FakeKrx(date(2026, 9, 16), date(2026, 9, 15), fail=True)
    service = object.__new__(StockScannerService)
    service.market_store = store
    service.krx = krx

    # Use ProviderError-compatible failure behavior by monkeying stock_daily below.
    from app.market.providers.base import ProviderError

    async def fail_stock_daily(market: str, bas_date: date):
        krx.stats["network_requests"] += 1
        raise ProviderError("테스트 네트워크 실패")

    krx.stock_daily = fail_stock_daily  # type: ignore[method-assign]
    result = await service.prepare_latest_confirmed_data(market_scope="ALL", known_data_date="2026-09-14")

    assert result["status"] == "UPDATE_FAILED"
    assert result["resolved_as_of_date"] == "2026-09-14"
    assert result["current_date_valid"] is True
    assert result["fallback_allowed"] is False
    assert result["available_data_date"] == "2026-09-14"
    assert result["market_data_updated"] is False
