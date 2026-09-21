from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.tracking.service import RecommendationTrackingService
from app.tracking.store import RecommendationTrackingRepository


class FakeMarket:
    def get_bar(self, market, ticker, day):
        if ticker == "MISSING":
            return None
        return SimpleNamespace(market=market, close=Decimal("82000"))


def service(tmp_path: Path):
    return RecommendationTrackingService(RecommendationTrackingRepository(tmp_path / "tracking.db"), FakeMarket())


def payload():
    return {
        "ticker": "005930", "name": "삼성전자", "market": "KOSPI", "source": "SCANNER",
        "recommendation_date": date(2026, 9, 21), "scanner_version": "0.21.3.7",
        "decision_status": "READY", "rank": 2, "entry_price": "81500", "stop_price": "77000",
        "target1_price": "87000", "target2_price": "91000", "snapshot": {"reason": "fixture"},
    }


def test_create_persists_confirmed_close_and_snapshot(tmp_path):
    svc = service(tmp_path)
    item, created = svc.create(payload())
    assert created is True
    assert item.reference_price == Decimal("82000")
    assert item.snapshot == {"reason": "fixture"}
    assert svc.list()[0].ticker == "005930"


def test_duplicate_scanner_recommendation_is_idempotent(tmp_path):
    svc = service(tmp_path)
    first, first_created = svc.create(payload())
    second, second_created = svc.create(payload())
    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert len(svc.list()) == 1


def test_close_preserves_record(tmp_path):
    svc = service(tmp_path)
    item, _ = svc.create(payload())
    closed = svc.close(item.id)
    assert closed.status == "CLOSED"
    assert closed.closed_at is not None
    assert len(svc.list(status="CLOSED")) == 1
