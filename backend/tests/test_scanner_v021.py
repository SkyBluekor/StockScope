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


def test_scanner_fast_request_limit_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("KRX_SCANNER_FAST_REQUEST_LIMIT", "77")
    assert StockScannerService.fast_request_limit() == 77


def test_scanner_history_plan_counts_only_uncached_network_requests() -> None:
    class FakeStore:
        @staticmethod
        def day_complete(market: str, key: str, kind: str) -> bool:
            return key == "20260901"

    class FakeKrx:
        @staticmethod
        def has_cached_day(market: str, day: date, kind: str) -> bool:
            return kind == "stock"

    service = object.__new__(StockScannerService)
    service.market_store = FakeStore()
    service.krx = FakeKrx()
    plan = service._history_plan(
        market="KOSPI",
        start=date(2026, 9, 1),
        end=date(2026, 9, 4),
    )
    assert plan["total"] == 8
    assert plan["reused"] == 2
    assert len(plan["work"]) == 6
    assert plan["estimated_network_requests"] == 3


def test_scanner_current_only_candidate_is_labeled_as_unverified_history() -> None:
    service = object.__new__(StockScannerService)
    item = {
        "code": "000001",
        "name": "테스트",
        "market": "KOSPI",
        "latest_date": "20260911",
        "current_price": 10000,
        "quick_strategy": "MOMENTUM_CONTINUATION",
        "quick_guide": {
            "easy_name": "강한 상승 이어가기",
            "professional_name": "모멘텀 지속",
            "description": "상승 힘이 이어지는지 확인하는 방법입니다.",
        },
        "quick_current": {
            "status": "WATCH",
            "passed": 8,
            "missing": 1,
            "total": 9,
            "risk_warning": False,
            "risk_status": "READY",
            "summary": "9개 중 1개 조건이 부족합니다.",
            "warnings": [],
        },
        "quick_condition_state": {
            "missing_details": [
                {"raw": "거래량", "label": "거래량 증가", "detail": "거래량 조건이 부족합니다."}
            ]
        },
        "quick_score": 80,
    }
    candidate = service._fast_candidate(item)
    assert candidate is not None
    assert candidate["candidate_state"] == "WATCH"
    assert candidate["verification_level"] == "CURRENT_ONLY"
    assert candidate["historical_fit"]["verified"] is False
    assert candidate["historical_fit"]["label"] == "과거 검증 전"


def test_scanner_ready_current_candidate_is_not_blocked_only_because_history_is_unverified() -> None:
    service = object.__new__(StockScannerService)
    item = {
        "code": "000002",
        "name": "현재조건완료",
        "market": "KOSPI",
        "latest_date": "20260911",
        "current_price": 20000,
        "quick_strategy": "trend_following",
        "quick_guide": {
            "easy_name": "상승 흐름 따라가기",
            "professional_name": "추세 추종",
            "description": "상승 흐름을 확인합니다.",
        },
        "quick_current": {
            "status": "READY",
            "passed": 6,
            "missing": 0,
            "total": 6,
            "risk_warning": False,
            "risk_status": "READY",
            "summary": "모든 현재 조건을 통과했습니다.",
            "warnings": [],
        },
        "quick_condition_state": {"missing_details": []},
        "quick_entry_risk_guide": {"action": {"status": "ENTRY_CANDIDATE"}},
        "quick_score": 90,
    }
    candidate = service._fast_candidate(item)
    assert candidate is not None
    assert candidate["candidate_state"] == "READY"
    assert candidate["action"] == "ENTRY_CANDIDATE"
    assert candidate["historical_fit"]["verified"] is False
    assert "과거 검증 전" in candidate["candidate_label"]


def test_v0212_evidence_cache_key_separates_strategy_and_data_end(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(StockScannerService, "CACHE_ROOT", tmp_path)
    first = StockScannerService._evidence_cache_path(
        market="KOSPI", code="005930", strategy="breakout", data_end=date(2026, 9, 14)
    )
    second = StockScannerService._evidence_cache_path(
        market="KOSPI", code="005930", strategy="pullback", data_end=date(2026, 9, 14)
    )
    third = StockScannerService._evidence_cache_path(
        market="KOSPI", code="005930", strategy="breakout", data_end=date(2026, 9, 15)
    )
    assert first != second
    assert first != third
    assert StockScannerService.HISTORICAL_EVIDENCE_POLICY_VERSION in first.name


def test_v0213_scanner_version_invalidates_old_daily_cache() -> None:
    assert StockScannerService.VERSION == "0.21.3.7"


def test_v0212_unverified_evidence_is_not_frozen_in_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(StockScannerService, "CACHE_ROOT", tmp_path)
    data_end = date(2026, 9, 14)
    StockScannerService._save_evidence_cache(
        market="KOSPI",
        code="005930",
        strategy="breakout",
        data_end=data_end,
        evidence={"verified": False, "status": "DATA_UNAVAILABLE"},
    )
    assert StockScannerService._load_evidence_cache(
        market="KOSPI", code="005930", strategy="breakout", data_end=data_end
    ) is None
    assert not list((tmp_path / "historical_evidence").glob("*.json"))
