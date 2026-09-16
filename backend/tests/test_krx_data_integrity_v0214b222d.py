from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.backtest.market_store import HistoricalMarketStore
from app.backtest.scanner import StockScannerService


def _stock(day: str, code: str, close: int, name: str = "테스트") -> dict:
    return {
        "date": day,
        "code": code,
        "name": name,
        "open": close - 10,
        "high": close + 10,
        "low": close - 20,
        "close": close,
        "volume": 1000,
        "trade_value": close * 1000,
        "market_cap": 1_000_000,
    }


def _index(day: str, market: str, close: float = 1000.0) -> dict:
    return {
        "date": day,
        "name": "코스피" if market == "KOSPI" else "코스닥",
        "close": close,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "volume": 999,
        "change_rate": 0.1,
    }


class FakeKrx:
    def __init__(self) -> None:
        self.today = date(2026, 9, 16)
        self.stock: dict[tuple[str, str], list[dict]] = {}
        self.index: dict[tuple[str, str], list[dict]] = {}
        self.cache: dict[tuple[str, str, str], list[dict]] = {}
        self.stats = {
            "network_requests": 0,
            "memory_hits": 0,
            "disk_hits": 0,
            "empty_marker_hits": 0,
            "retries": 0,
            "forced_network_requests": 0,
        }

    def _today_kst(self) -> date:
        return self.today

    @staticmethod
    def _candidate_dates(as_of: date, lookback_days: int) -> list[date]:
        result: list[date] = []
        for offset in range(lookback_days):
            candidate = as_of - timedelta(days=offset)
            if candidate.weekday() < 5:
                result.append(candidate)
        return result

    async def open_session(self) -> None:
        return None

    async def close_session(self) -> None:
        return None

    def request_stats(self) -> dict[str, int]:
        return dict(self.stats)

    def cached_daily_snapshot(self, market: str, day: date, kind: str) -> dict:
        compact = day.strftime("%Y%m%d")
        rows = self.cache.get((market, compact, kind))
        if rows is None:
            return {"source": "none", "date": compact, "count": 0, "rows": []}
        return {"source": "disk", "date": compact, "count": len(rows), "rows": [dict(row) for row in rows]}

    async def stock_daily(self, market: str, day: date, *, force_refresh: bool = False) -> dict:
        compact = day.strftime("%Y%m%d")
        self.stats["network_requests"] += 1
        if force_refresh:
            self.stats["forced_network_requests"] += 1
        rows = [dict(row) for row in self.stock.get((market, compact), [])]
        self.cache[(market, compact, "stock")] = [dict(row) for row in rows]
        return {"date": compact, "count": len(rows), "rows": rows}

    async def index_daily(self, market: str, day: date, *, force_refresh: bool = False) -> dict:
        compact = day.strftime("%Y%m%d")
        self.stats["network_requests"] += 1
        if force_refresh:
            self.stats["forced_network_requests"] += 1
        rows = [dict(row) for row in self.index.get((market, compact), [])]
        self.cache[(market, compact, "index")] = [dict(row) for row in rows]
        return {"date": compact, "count": len(rows), "rows": rows}

    @staticmethod
    def _select_main_index(rows: list[dict], market: str) -> dict | None:
        return rows[0] if rows else None


def _service(store: HistoricalMarketStore, krx: FakeKrx) -> StockScannerService:
    service = object.__new__(StockScannerService)
    service.market_store = store
    service.krx = krx
    return service


@pytest.mark.asyncio
async def test_integrity_audit_corrects_stale_cache_store_and_removes_stale_ticker(tmp_path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    krx = FakeKrx()
    day = "20260915"
    for market in ("KOSPI", "KOSDAQ"):
        code = "192820" if market == "KOSPI" else "123456"
        final = [_stock(day, code, 273000 if market == "KOSPI" else 5000), _stock(day, "000001", 10000)]
        stale = [dict(final[0], close=274000), _stock(day, "999999", 7777)]
        krx.stock[(market, day)] = final
        krx.index[(market, day)] = [_index(day, market)]
        krx.cache[(market, day, "stock")] = stale
        krx.cache[(market, day, "index")] = [_index(day, market, 999.0)]
        store.put_stock_day(market, day, stale, stable=True)
        store.put_index_day(market, day, _index(day, market, 999.0), stable=True)

    result = await _service(store, krx).audit_input_data(
        market_scope="ALL", as_of_date="2026-09-15", trace_code="192820"
    )

    assert result["status"] == "CORRECTED"
    assert result["markets"]["KOSPI"]["raw_cache_compare_before"]["matches"] is False
    assert result["markets"]["KOSPI"]["market_store_compare_after"]["matches"] is True
    assert result["markets"]["KOSPI"]["trace"]["krx_direct"]["close"] == 273000
    assert result["markets"]["KOSPI"]["trace"]["scanner_input"]["close"] == 273000
    assert store.stock_day_count("KOSPI", day) == 2
    assert all(row["code"] != "999999" for row in store.stock_day_rows("KOSPI", day))


@pytest.mark.asyncio
async def test_latest_freshness_forces_integrity_once_then_reuses_verified_snapshot(tmp_path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    krx = FakeKrx()
    day = "20260915"
    for market in ("KOSPI", "KOSDAQ"):
        code = "192820" if market == "KOSPI" else "123456"
        final = [_stock(day, code, 273000 if market == "KOSPI" else 5000)]
        krx.stock[(market, day)] = final
        krx.index[(market, day)] = [_index(day, market)]
        store.put_stock_day(market, day, [dict(final[0], close=274000)], stable=True)
        store.put_index_day(market, day, _index(day, market, 999.0), stable=True)

    service = _service(store, krx)
    first = await service.prepare_latest_confirmed_data(
        market_scope="ALL", known_data_date="2026-09-15"
    )
    first_requests = krx.stats["network_requests"]

    assert first["resolved_as_of_date"] == "2026-09-15"
    assert first_requests == 4
    assert store.stock_day_rows("KOSPI", day)[0]["close"] == 273000
    assert first["diagnostics"]["data_integrity"]["KOSPI"]["mode"] == "FORCED_KRX_VERIFY"

    second = await service.prepare_latest_confirmed_data(
        market_scope="ALL", known_data_date="2026-09-15"
    )
    assert krx.stats["network_requests"] == first_requests
    assert second["diagnostics"]["data_integrity"]["KOSPI"]["mode"] == "VERIFIED_REUSE"


def test_scanner_input_fingerprint_changes_when_eod_snapshot_changes(tmp_path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    service = object.__new__(StockScannerService)
    service.market_store = store
    day = "20260915"
    for market in ("KOSPI", "KOSDAQ"):
        store.replace_stock_day(market, day, [_stock(day, "192820" if market == "KOSPI" else "123456", 10000)], stable=True)
        store.replace_index_day(market, day, _index(day, market), stable=True)
    dates = {"KOSPI": "2026-09-15", "KOSDAQ": "2026-09-15"}
    before = service._build_input_fingerprint(["KOSPI", "KOSDAQ"], dates)
    store.replace_stock_day("KOSPI", day, [_stock(day, "192820", 10010)], stable=True)
    after = service._build_input_fingerprint(["KOSPI", "KOSDAQ"], dates)
    assert before["id"] != after["id"]
