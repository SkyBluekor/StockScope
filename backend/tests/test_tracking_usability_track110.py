from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tracking.service import RecommendationTrackingService, TrackingError
from app.tracking.store import RecommendationTrackingRepository


class FakeStore:
    def latest_complete_date(self, market, instrument_type, as_of):
        return "20260918"


class FakeMarket:
    def __init__(self):
        self.store = FakeStore()
        self.days = [date(2026, 9, 18), date(2026, 9, 21)]

    def has_trading_day(self, day):
        return day in self.days

    def next_trading_day(self, day):
        for candidate in self.days:
            if candidate > day:
                return candidate
        return None

    def get_bar(self, market, ticker, day):
        if day not in self.days:
            return None
        price = Decimal("84000") if day == date(2026, 9, 18) else Decimal("85000")
        return SimpleNamespace(market=market, close=price, open=price, high=price + 1000, low=price - 1000)


def make_service(tmp_path: Path):
    return RecommendationTrackingService(RecommendationTrackingRepository(tmp_path / "tracking.db"), FakeMarket())


def test_closed_tracking_record_can_be_deleted_and_performance_cascades(tmp_path):
    service = make_service(tmp_path)
    item, _ = service.create_manual({"ticker": "005930", "name": "삼성전자", "market": "KOSPI"})
    service.refresh(item.id)
    service.close(item.id)
    service.delete(item.id)
    assert service.repository.get(item.id) is None
    assert service.repository.get_performance(item.id) is None


def test_active_tracking_record_must_be_closed_before_delete(tmp_path):
    service = make_service(tmp_path)
    item, _ = service.create_manual({"ticker": "005930", "name": "삼성전자", "market": "KOSPI"})
    with pytest.raises(TrackingError) as caught:
        service.delete(item.id)
    assert caught.value.code == "TRACK_DELETE_ACTIVE"
    assert service.repository.get(item.id) is not None
