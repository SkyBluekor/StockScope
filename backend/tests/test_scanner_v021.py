from __future__ import annotations

from datetime import date
from pathlib import Path

from app.backtest.market_store import HistoricalMarketStore
from app.backtest.scanner import StockScannerService


def _row(code: str, name: str, *, trade_value: int = 2_000_000_000, volume: int = 100_000) -> dict:
    return {
        "date": "20260911",
        "code": code,
        "name": name,
        "market": "KOSPI",
        "section": "보통주",
        "close": 100_000,
        "open": 99_000,
        "high": 101_000,
        "low": 98_500,
        "volume": volume,
        "trade_value": trade_value,
        "market_cap": 100_000_000_000,
    }


def test_market_store_can_reuse_one_market_day_for_many_symbols(tmp_path: Path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    rows = [_row("005930", "삼성전자"), _row("000660", "SK하이닉스")]
    assert store.put_stock_day("KOSPI", "20260911", rows, stable=True) == 2

    assert store.latest_complete_date("KOSPI", "stock") == "20260911"
    day_rows = store.stock_day_rows("KOSPI", "20260911")
    assert {row["code"] for row in day_rows} == {"005930", "000660"}

    series = store.stock_series_many("KOSPI", ["005930", "000660"], "20260911", "20260911")
    assert series["005930"].rows["20260911"]["name"] == "삼성전자"
    assert series["000660"].rows["20260911"]["name"] == "SK하이닉스"


def test_scanner_special_product_filter_keeps_ordinary_stock() -> None:
    assert StockScannerService._special_reason(_row("005930", "삼성전자")) is None


def test_scanner_special_product_filter_excludes_preferred_and_spac() -> None:
    assert StockScannerService._special_reason(_row("005935", "삼성전자우")) == "우선주"
    assert StockScannerService._special_reason(_row("123456", "테스트스팩1호")) == "SPAC"


def test_scanner_filter_excludes_suspended_or_no_trade_row() -> None:
    assert StockScannerService._special_reason(_row("005930", "삼성전자", volume=0)) == "거래정지 또는 거래 없음"


def test_scanner_result_cache_key_includes_candidate_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(StockScannerService, "CACHE_ROOT", tmp_path)
    first = StockScannerService._cache_path("ALL", date(2026, 9, 14), 5)
    second = StockScannerService._cache_path("ALL", date(2026, 9, 14), 10)
    assert first != second
    assert "_5_" in first.name
    assert "_10_" in second.name
