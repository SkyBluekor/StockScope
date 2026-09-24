from __future__ import annotations

import asyncio
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from app.backtest.history_store import HistorySeries
from app.backtest.market_store import HistoricalMarketStore
from app.holdings.chart_prepare import HoldingsChartPrepareService


def _dd(day: date) -> str:
    return day.strftime("%Y%m%d")


def _row(day: date, code: str = "190510") -> dict[str, object]:
    base = 15000 + (day.toordinal() % 700)
    return {
        "date": _dd(day), "code": code, "name": "나무가",
        "open": base, "high": base + 120, "low": base - 100,
        "close": base + 20, "volume": 100000,
    }


class FakeProvider:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.network_requests = 0

    async def open_session(self) -> None: return None
    async def close_session(self) -> None: return None
    def request_stats(self) -> dict[str, int]: return {"network_requests": self.network_requests}

    async def stock_history(self, market: str, code: str, *, as_of, points: int, lookback_days: int, concurrency: int, progress=None):
        self.network_requests += 1
        target = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
        floor = target - timedelta(days=lookback_days)
        eligible = []
        for row in self.rows:
            raw = str(row["date"])
            row_date = date.fromisoformat(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
            if floor <= row_date <= target:
                eligible.append(row)
        eligible.sort(key=lambda row: str(row["date"]))
        selected = eligible[-min(max(points, 20), 120):]
        if progress is not None:
            progress(len(selected), min(max(points, 20), 120))
        return selected


def _seed(db: Path, count: int, *, target: date) -> None:
    store = HistoricalMarketStore(db)
    rows = {}
    cursor = target
    while len(rows) < count:
        if cursor.weekday() < 5:
            rows[_dd(cursor)] = _row(cursor)
        cursor -= timedelta(days=1)
    store.import_legacy_stock("KOSDAQ", "190510", HistorySeries(rows=rows, checked_dates=set()))
    store.put_stock_day("KOSDAQ", _dd(target), [_row(target)], stable=True)


def _provider_rows(target: date, count: int = 400):
    rows = []
    cursor = target
    while len(rows) < count:
        if cursor.weekday() < 5:
            rows.append(_row(cursor))
        cursor -= timedelta(days=1)
    return rows


def test_six_month_prepare_extends_selected_symbol_without_full_day_status(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    target = date(2026, 9, 22)
    _seed(db, 61, target=target)
    provider = FakeProvider(_provider_rows(target))
    service = HoldingsChartPrepareService(krx_api_key="x", market_store_db=db, provider_factory=lambda _: provider)
    progress = []
    result = asyncio.run(service.prepare(market="KOSDAQ", ticker="190510", chart_range="6m", progress=progress.append))
    assert result.status == "READY"
    assert result.required_rows == 132
    assert result.final_rows >= 132
    assert progress
    with sqlite3.connect(db) as conn:
        statuses = conn.execute("SELECT bas_dd,kind,status FROM day_status WHERE market='KOSDAQ' ORDER BY bas_dd,kind").fetchall()
    assert statuses == [("20260922", "stock", "data")]


def test_ready_range_uses_zero_network_requests(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    target = date(2026, 9, 22)
    _seed(db, 140, target=target)
    def should_not_create_provider(_): raise AssertionError("provider must not be created")
    service = HoldingsChartPrepareService(krx_api_key="x", market_store_db=db, provider_factory=should_not_create_provider)
    result = asyncio.run(service.prepare(market="KOSDAQ", ticker="190510", chart_range="6m"))
    assert result.status == "READY"
    assert result.network_requests == 0


def test_one_year_crosses_provider_120_point_limit(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    target = date(2026, 9, 22)
    _seed(db, 61, target=target)
    provider = FakeProvider(_provider_rows(target))
    service = HoldingsChartPrepareService(krx_api_key="x", market_store_db=db, provider_factory=lambda _: provider)
    result = asyncio.run(service.prepare(market="KOSDAQ", ticker="190510", chart_range="1y"))
    assert result.status == "READY"
    assert result.required_rows == 252
    assert result.final_rows >= 252
    assert provider.network_requests >= 2


def test_frontend_exposes_partial_range_and_explicit_prepare() -> None:
    component = Path("frontend/src/components/HoldingsPriceChart.tsx").read_text(encoding="utf-8")
    service = Path("frontend/src/services/holdingsApi.ts").read_text(encoding="utf-8")
    api = Path("backend/app/api/holdings.py").read_text(encoding="utf-8")
    assert "chart.count < chart.requested_bars" in component
    assert "일부 기간만 표시 중" in component
    assert "prepareHoldingChartWithProgress" in component
    assert "chart/prepare-stream" in service
    assert "chart/prepare-stream" in api
