from __future__ import annotations

import asyncio
from datetime import date

from app.backtest.sector_rs_input import TEMPORAL_STATIC_CURRENT
from app.backtest.sector_rs_prefetch import HistoricalSectorInputPrefetcher


class FakeCompanyProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def company_by_stock_code(self, code: str):
        self.calls.append(code)
        return {"industry_code": {"000001": "26", "000002": "26", "000003": "20"}.get(code)}


class FakeKrx:
    def __init__(self) -> None:
        self.calls: list[date] = []

    async def index_daily(self, market: str, candidate: date):
        self.calls.append(candidate)
        stamp = candidate.strftime("%Y%m%d")
        # The two mapped groups are available every requested weekday.
        return {
            "count": 2,
            "date": stamp,
            "rows": [
                {"date": stamp, "name": "전기·전자", "class": "업종", "close": 1000.0},
                {"date": stamp, "name": "화학", "class": "업종", "close": 800.0},
            ],
        }


def test_prefetch_deduplicates_company_and_index_requests_across_sector_peers() -> None:
    company = FakeCompanyProvider()
    krx = FakeKrx()
    prefetch = HistoricalSectorInputPrefetcher(krx, company, concurrency=4)

    prepared, stats = asyncio.run(
        prefetch.prepare(
            market="KOSPI",
            codes=["000001", "000002", "000001", "000003"],
            as_of="2026-09-18",
            points=21,
            lookback_days=60,
        )
    )

    assert set(prepared) == {"000001", "000002", "000003"}
    assert sorted(company.calls) == ["000001", "000002", "000003"]
    assert stats["unique_codes"] == 3
    assert stats["company_requests"] == 3
    assert stats["unique_sector_alias_sets"] == 2
    # Critical scaling property: index requests are per date, never per stock.
    assert stats["index_daily_calls"] == len(krx.calls)
    assert stats["index_daily_calls"] < 3 * 21
    assert prepared["000001"].sector_rows == prepared["000002"].sector_rows


def test_prefetch_is_audit_only_and_never_requests_a_future_date() -> None:
    company = FakeCompanyProvider()
    krx = FakeKrx()
    prefetch = HistoricalSectorInputPrefetcher(krx, company)

    prepared, stats = asyncio.run(
        prefetch.prepare(
            market="KOSPI",
            codes=["000001"],
            as_of="2026-09-18",
            points=21,
            lookback_days=60,
        )
    )

    item = prepared["000001"]
    assert item.temporal_status == TEMPORAL_STATIC_CURRENT
    assert item.production_safe is False
    assert stats["temporal_status"] == TEMPORAL_STATIC_CURRENT
    assert all(candidate <= date(2026, 9, 18) for candidate in krx.calls)
    assert item.benchmark_name == "전기·전자"
    assert len(item.sector_rows) == 21


def test_prefetch_cache_reuses_company_metadata_on_second_prepare() -> None:
    company = FakeCompanyProvider()
    krx = FakeKrx()
    prefetch = HistoricalSectorInputPrefetcher(krx, company)

    asyncio.run(prefetch.prepare(market="KOSPI", codes=["000001"], as_of="2026-09-18", points=5, lookback_days=20))
    _, stats = asyncio.run(prefetch.prepare(market="KOSPI", codes=["000001"], as_of="2026-09-18", points=5, lookback_days=20))

    assert company.calls == ["000001"]
    assert stats["company_requests"] == 0
    assert stats["company_cache_hits"] == 1
