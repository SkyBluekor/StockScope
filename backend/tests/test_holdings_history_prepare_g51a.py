from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.backtest.history_store import HistoricalStore, HistorySeries
from app.backtest.market_store import HistoricalMarketStore
from app.holdings.history_prepare import (
    HoldingsHistoryPrepareError,
    HoldingsHistoryPrepareService,
)


TARGET = date(2026, 9, 23)


def _dates(count: int) -> list[date]:
    rows: list[date] = []
    cursor = TARGET
    while len(rows) < count:
        if cursor.weekday() < 5:
            rows.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(rows)


def _stock_rows(count: int) -> list[dict]:
    return [
        {
            "date": day.isoformat(),
            "code": "005930",
            "name": "삼성전자",
            "open": 70000 + index,
            "high": 70100 + index,
            "low": 69900 + index,
            "close": 70050 + index,
            "volume": 1000000 + index,
            "trade_value": 10000000000 + index,
            "market_cap": 400000000000000,
            "change_rate": 0.1,
        }
        for index, day in enumerate(_dates(count))
    ]


def _index_rows(count: int) -> list[dict]:
    return [
        {
            "date": day.isoformat(),
            "open": 3000 + index,
            "high": 3010 + index,
            "low": 2990 + index,
            "close": 3005 + index,
            "change_rate": 0.1,
        }
        for index, day in enumerate(_dates(count))
    ]


def _series(rows: list[dict]) -> HistorySeries:
    return HistorySeries(
        rows={str(row["date"]).replace("-", ""): row for row in rows},
        checked_dates=set(),
    )


class FakeProvider:
    def __init__(self, stock_rows: list[dict], index_rows: list[dict], *, fail: bool = False):
        self.stock_rows = stock_rows
        self.index_rows = index_rows
        self.fail = fail
        self.stock_calls = 0
        self.index_calls = 0
        self._network = 0

    async def open_session(self):
        return None

    async def close_session(self):
        return None

    def request_stats(self):
        return {"network_requests": self._network}

    async def stock_history(self, *args, **kwargs):
        self.stock_calls += 1
        self._network += 1
        if self.fail:
            raise RuntimeError("provider down")
        return list(self.stock_rows)

    async def index_history(self, *args, **kwargs):
        self.index_calls += 1
        self._network += 1
        if self.fail:
            raise RuntimeError("provider down")
        return list(self.index_rows)


def _service(tmp_path: Path, provider: FakeProvider) -> HoldingsHistoryPrepareService:
    return HoldingsHistoryPrepareService(
        krx_api_key="test",
        market_store_db=tmp_path / "market.db",
        history_store=HistoricalStore(tmp_path / "history"),
        provider_factory=lambda key: provider,
    )


def test_ready_local_history_uses_zero_network(tmp_path: Path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    store.import_legacy_stock("KOSPI", "005930", _series(_stock_rows(61)))
    store.import_legacy_index("KOSPI", _series(_index_rows(61)))
    provider = FakeProvider([], [])

    result = asyncio.run(
        _service(tmp_path, provider).prepare(
            market="KOSPI", ticker="005930", market_date=TARGET.isoformat()
        )
    )

    assert result.status == "READY"
    assert result.final_rows >= 61
    assert result.network_requests == 0
    assert provider.stock_calls == 0
    assert provider.index_calls == 0


def test_fetches_selected_symbol_without_marking_market_day_complete(tmp_path: Path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    store.import_legacy_stock("KOSPI", "005930", _series(_stock_rows(1)))
    provider = FakeProvider(_stock_rows(61), _index_rows(61))

    result = asyncio.run(
        _service(tmp_path, provider).prepare(
            market="KOSPI", ticker="005930", market_date=TARGET.isoformat()
        )
    )

    assert result.status == "UPDATED"
    assert result.existing_rows == 1
    assert result.final_rows >= 61
    assert result.prepared_rows >= 60
    assert provider.stock_calls == 1
    assert provider.index_calls == 1

    # Partial recovery must not claim that any full-market stock day is complete.
    with store._connect() as conn:  # noqa: SLF001 - invariant test
        stock_status_count = conn.execute(
            "SELECT COUNT(*) FROM day_status WHERE market='KOSPI' AND kind='stock'"
        ).fetchone()[0]
    assert stock_status_count == 0


def test_actual_short_history_returns_recoverable_insufficient_error(tmp_path: Path) -> None:
    provider = FakeProvider(_stock_rows(25), _index_rows(61))
    with pytest.raises(HoldingsHistoryPrepareError) as exc:
        asyncio.run(
            _service(tmp_path, provider).prepare(
                market="KOSPI", ticker="005930", market_date=TARGET.isoformat()
            )
        )

    assert exc.value.code == "HOLD_ANALYSIS_HISTORY_INSUFFICIENT"
    assert exc.value.details["current_rows"] == 25
    assert exc.value.details["required_rows"] == 61


def test_provider_failure_keeps_existing_rows(tmp_path: Path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    store.import_legacy_stock("KOSPI", "005930", _series(_stock_rows(1)))
    provider = FakeProvider([], [], fail=True)

    with pytest.raises(HoldingsHistoryPrepareError) as exc:
        asyncio.run(
            _service(tmp_path, provider).prepare(
                market="KOSPI", ticker="005930", market_date=TARGET.isoformat()
            )
        )

    assert exc.value.code == "HOLD_ANALYSIS_HISTORY_PREPARE_FAILED"
    assert len(store.stock_series("KOSPI", "005930").rows) == 1
