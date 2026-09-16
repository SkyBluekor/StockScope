from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.backtest.scanner import StockScannerService
from app.market.providers.base import ProviderError


class FakeStore:
    def __init__(self) -> None:
        self.stock_days: dict[tuple[str, str], list[dict]] = {}
        self.index_days: dict[tuple[str, str], dict] = {}

    def seed(self, market: str, compact: str, *, stock: bool = True, index: bool = True) -> None:
        if stock:
            self.stock_days[(market, compact)] = [{"date": compact, "code": "000001"}]
        if index:
            self.index_days[(market, compact)] = {"date": compact, "name": market}

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
    def __init__(self, today: date, available_day: date) -> None:
        self.today = today
        self.available_day = available_day
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
        if bas_date != self.available_day:
            return {"date": key, "count": 0, "rows": []}
        return {"date": key, "count": 1, "rows": [{"date": key, "name": market, "close": 1000}]}

    @staticmethod
    def _select_main_index(rows, market: str):
        return rows[0] if rows else None


def service_with(store: FakeStore, krx: FakeKrx) -> StockScannerService:
    service = object.__new__(StockScannerService)
    service.market_store = store
    service.krx = krx
    return service


@pytest.mark.asyncio
async def test_valid_current_date_never_regresses_when_refresh_fails() -> None:
    store = FakeStore()
    for market in ("KOSPI", "KOSDAQ"):
        store.seed(market, "20260915")
    krx = FakeKrx(date(2026, 9, 17), date(2026, 9, 16))

    async def fail_stock_daily(market: str, bas_date: date):
        krx.stats["network_requests"] += 1
        raise ProviderError("테스트 네트워크 실패")

    krx.stock_daily = fail_stock_daily  # type: ignore[method-assign]
    result = await service_with(store, krx).prepare_latest_confirmed_data(
        market_scope="ALL", known_data_date="2026-09-15"
    )

    assert result["status"] == "UPDATE_FAILED"
    assert result["current_date_valid"] is True
    assert result["resolved_as_of_date"] == "2026-09-15"
    assert result["available_data_date"] == "2026-09-15"
    assert result["fallback_allowed"] is False
    assert "2026-09-15" in result["message"]


@pytest.mark.asyncio
async def test_invalid_claimed_current_date_is_reported_as_inconsistent() -> None:
    store = FakeStore()
    store.seed("KOSPI", "20260915")
    store.seed("KOSDAQ", "20260914")
    # Common complete date 9/14 exists for both markets, but the claimed 9/15 does not.
    store.seed("KOSPI", "20260914")
    krx = FakeKrx(date(2026, 9, 17), date(2026, 9, 16))

    async def fail_stock_daily(market: str, bas_date: date):
        krx.stats["network_requests"] += 1
        raise ProviderError("테스트 네트워크 실패")

    krx.stock_daily = fail_stock_daily  # type: ignore[method-assign]
    result = await service_with(store, krx).prepare_latest_confirmed_data(
        market_scope="ALL", known_data_date="2026-09-15"
    )

    assert result["status"] == "DATA_INCONSISTENT"
    assert result["current_date_valid"] is False
    assert result["resolved_as_of_date"] is None
    assert result["available_data_date"] == "2026-09-14"
    assert result["fallback_allowed"] is True


@pytest.mark.asyncio
async def test_provider_older_than_valid_local_date_keeps_current_date() -> None:
    store = FakeStore()
    for market in ("KOSPI", "KOSDAQ"):
        store.seed(market, "20260915")
    # Provider probe only finds 9/14 although a verified 9/15 is already local.
    krx = FakeKrx(date(2026, 9, 17), date(2026, 9, 14))
    result = await service_with(store, krx).prepare_latest_confirmed_data(
        market_scope="ALL", known_data_date="2026-09-15"
    )

    assert result["status"] == "READY"
    assert result["resolved_as_of_date"] == "2026-09-15"
    assert result["available_data_date"] == "2026-09-15"
    assert result["consistency_status"] == "CURRENT_RETAINED"
    assert result["date_changed"] is False


@pytest.mark.asyncio
async def test_newer_date_is_committed_only_after_all_markets_and_indexes_are_ready() -> None:
    store = FakeStore()
    for market in ("KOSPI", "KOSDAQ"):
        store.seed(market, "20260914")
    krx = FakeKrx(date(2026, 9, 16), date(2026, 9, 15))
    result = await service_with(store, krx).prepare_latest_confirmed_data(
        market_scope="ALL", known_data_date="2026-09-14"
    )

    assert result["status"] == "UPDATED"
    assert result["resolved_as_of_date"] == "2026-09-15"
    assert result["stored_common_date"] == "2026-09-15"
    assert result["date_changed"] is True
    for market in ("KOSPI", "KOSDAQ"):
        assert store.day_complete(market, "20260915", "stock")
        assert store.day_complete(market, "20260915", "index")


def test_cached_result_date_alignment_rejects_mixed_market_dates() -> None:
    payload = {
        "requested_as_of": "2026-09-15",
        "data_dates": {"KOSPI": "2026-09-15", "KOSDAQ": "2026-09-14"},
    }
    assert StockScannerService._result_date_aligned(payload, "ALL", date(2026, 9, 15)) is False
    payload["data_dates"]["KOSDAQ"] = "2026-09-15"
    assert StockScannerService._result_date_aligned(payload, "ALL", date(2026, 9, 15)) is True
