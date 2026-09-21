from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.tracking.models import TrackedRecommendation
from app.tracking.performance import TradingObservation, calculate_performance
from app.tracking.service import RecommendationTrackingService
from app.tracking.store import RecommendationTrackingRepository


def rec(**changes):
    base = TrackedRecommendation(
        id="r1", ticker="005930", name="삼성전자", market="KOSPI", source="SCANNER",
        recommendation_date=date(2026, 9, 1), reference_price=Decimal("100"),
        scanner_version="0.21.3.7", scanner_baseline="baseline", strategy="fixture", decision_status="READY", rank=1,
        entry_price=Decimal("98"), stop_price=Decimal("94"), target1_price=Decimal("108"), target2_price=Decimal("115"),
        snapshot={"immutable": True}, status="ACTIVE", created_at=datetime(2026, 9, 1, tzinfo=timezone.utc), closed_at=None,
    )
    return replace(base, **changes)


def bar(day: date, close: str, high: str | None = None, low: str | None = None):
    c = Decimal(close)
    return SimpleNamespace(
        trading_date=day,
        open=c,
        high=Decimal(high) if high is not None else c,
        low=Decimal(low) if low is not None else c,
        close=c,
    )


def test_performance_ignores_recommendation_day_and_calculates_d1_metrics():
    item = rec()
    observations = [
        TradingObservation(date(2026, 9, 1), bar(date(2026, 9, 1), "150", "160", "50")),
        TradingObservation(date(2026, 9, 2), bar(date(2026, 9, 2), "102", "109", "97")),
        TradingObservation(date(2026, 9, 3), bar(date(2026, 9, 3), "101", "105", "93")),
    ]
    p = calculate_performance(item, observations, updated_at=datetime.now(timezone.utc))
    assert p.trading_days == 2
    assert p.latest_close == Decimal("101")
    assert p.current_return_pct == Decimal("1.0000")
    assert p.mfe_pct == Decimal("9.0000")
    assert p.mae_pct == Decimal("-7.0000")
    assert p.entry_touched is True and p.entry_touch_date == date(2026, 9, 2)
    assert p.stop_touched is True and p.stop_touch_date == date(2026, 9, 3)
    assert p.target1_touched is True and p.target1_touch_date == date(2026, 9, 2)
    assert p.target2_touched is False


def test_fixed_horizons_use_market_trading_day_index_and_missing_bar_stays_null():
    item = rec()
    days = [date(2026, 9, d) for d in range(2, 22)]
    observations = []
    for idx, day in enumerate(days, start=1):
        if idx == 5:
            observations.append(TradingObservation(day, bar(day, "105")))
        elif idx == 10:
            observations.append(TradingObservation(day, None))
        elif idx == 20:
            observations.append(TradingObservation(day, bar(day, "120")))
        else:
            observations.append(TradingObservation(day, bar(day, "100")))
    p = calculate_performance(item, observations, updated_at=datetime.now(timezone.utc))
    assert p.trading_days == 20
    assert p.return_5d == Decimal("5.0000")
    assert p.return_10d is None
    assert p.return_20d == Decimal("20.0000")


def test_same_bar_can_record_stop_and_target_without_execution_order_assumption():
    item = rec(stop_price=Decimal("95"), target1_price=Decimal("110"))
    day = date(2026, 9, 2)
    p = calculate_performance(
        item,
        [TradingObservation(day, bar(day, "100", high="112", low="92"))],
        updated_at=datetime.now(timezone.utc),
    )
    assert p.stop_touched is True
    assert p.target1_touched is True
    assert p.stop_touch_date == p.target1_touch_date == day


class FakeMarket:
    def __init__(self):
        self.days = [date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4), date(2026, 9, 7), date(2026, 9, 8)]

    def get_bar(self, market, ticker, day):
        if day == date(2026, 9, 1):
            return SimpleNamespace(market=market, close=Decimal("100"), open=Decimal("100"), high=Decimal("100"), low=Decimal("100"))
        if day not in self.days:
            return None
        close = Decimal("105") if day == self.days[-1] else Decimal("101")
        return SimpleNamespace(market=market, close=close, open=close, high=close + 1, low=close - 1)

    def next_trading_day(self, day):
        for candidate in self.days:
            if candidate > day:
                return candidate
        return None


def make_service(tmp_path: Path):
    return RecommendationTrackingService(RecommendationTrackingRepository(tmp_path / "tracking.db"), FakeMarket())


def create_payload():
    return {
        "ticker": "005930", "name": "삼성전자", "market": "KOSPI", "source": "SCANNER",
        "recommendation_date": date(2026, 9, 1), "decision_status": "READY",
        "entry_price": "99", "stop_price": "90", "target1_price": "104", "target2_price": "120",
        "snapshot": {"fixed": "snapshot"},
    }


def test_refresh_persists_performance_and_is_idempotent(tmp_path):
    svc = make_service(tmp_path)
    item, _ = svc.create(create_payload())
    first = svc.refresh(item.id)
    second = svc.refresh(item.id)
    first_dict = first.to_dict(); second_dict = second.to_dict()
    first_dict.pop("updated_at", None); second_dict.pop("updated_at", None)
    assert first_dict == second_dict
    stored = svc.repository.get_performance(item.id)
    assert stored is not None
    assert stored.trading_days == 5
    assert stored.return_5d == Decimal("5.0000")
    assert svc.repository.get(item.id).snapshot == {"fixed": "snapshot"}


def test_bulk_refresh_updates_active_only_and_closed_performance_is_preserved(tmp_path):
    svc = make_service(tmp_path)
    active, _ = svc.create(create_payload())
    closed_payload = dict(create_payload())
    closed_payload["ticker"] = "000660"
    closed_payload["name"] = "SK하이닉스"
    closed, _ = svc.create(closed_payload)
    svc.refresh(closed.id)
    before = svc.repository.get_performance(closed.id)
    svc.close(closed.id)

    summary = svc.refresh_active()
    assert summary["failed"] == 0
    assert svc.repository.get_performance(active.id) is not None
    after = svc.repository.get_performance(closed.id)
    assert before is not None and after is not None
    assert before.latest_close == after.latest_close
