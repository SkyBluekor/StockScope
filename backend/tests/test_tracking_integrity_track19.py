from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tracking.service import RecommendationTrackingService, TrackingError
from app.tracking.store import RecommendationTrackingRepository


class FakeStore:
    latest = "20260918"

    def latest_complete_date(self, market, instrument_type, as_of):
        return self.latest


class FakeMarket:
    def __init__(self):
        self.store = FakeStore()
        self.days = [date(2026, 9, 18), date(2026, 9, 21), date(2026, 9, 22)]

    def has_trading_day(self, day):
        return day in self.days

    def previous_trading_day(self, day):
        previous = [candidate for candidate in self.days if candidate < day]
        return previous[-1] if previous else None

    def next_trading_day(self, day):
        for candidate in self.days:
            if candidate > day:
                return candidate
        return None

    def get_bar(self, market, ticker, day):
        if day not in self.days:
            return None
        close = Decimal("84000") if day == date(2026, 9, 18) else Decimal("85000")
        return SimpleNamespace(market=market, close=close, open=close, high=close + 1000, low=close - 1000)


def service(tmp_path: Path):
    return RecommendationTrackingService(RecommendationTrackingRepository(tmp_path / "tracking.db"), FakeMarket())


def test_manual_source_is_server_owned_and_active_duplicate_returns_same_item(tmp_path):
    svc = service(tmp_path)
    first, created = svc.create_manual({"ticker": "005930", "name": "삼성전자", "market": "KOSPI"})
    second, created_again = svc.create_manual({"ticker": "005930", "name": "삼성전자", "market": "KOSPI"})
    assert created is True
    assert created_again is False
    assert first.id == second.id
    assert first.source == "MANUAL"
    assert first.recommendation_date == date(2026, 9, 18)
    assert first.reference_price == Decimal("84000")


def test_legacy_create_rejects_manual_source_spoof(tmp_path):
    svc = service(tmp_path)
    with pytest.raises(TrackingError) as caught:
        svc.create({
            "ticker": "005930", "name": "삼성전자", "market": "KOSPI", "source": "MANUAL",
            "recommendation_date": date(2026, 9, 18),
        })
    assert caught.value.code == "TRACK_SOURCE_SPOOF"


def test_manual_same_market_day_cannot_reopen_after_close(tmp_path):
    svc = service(tmp_path)
    item, _ = svc.create_manual({"ticker": "005930", "name": "삼성전자", "market": "KOSPI"})
    svc.close(item.id)
    with pytest.raises(TrackingError) as caught:
        svc.create_manual({"ticker": "005930", "name": "삼성전자", "market": "KOSPI"})
    assert caught.value.code == "TRACK_MANUAL_SAME_DAY_REOPEN"


def test_snapshot_columns_migrate_and_snapshot_trigger_is_immutable(tmp_path):
    db = tmp_path / "tracking.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE tracked_recommendation (
              id TEXT PRIMARY KEY,ticker TEXT NOT NULL,name TEXT NOT NULL,market TEXT NOT NULL,source TEXT NOT NULL,
              recommendation_date TEXT NOT NULL,reference_price TEXT NOT NULL,scanner_version TEXT,scanner_baseline TEXT,
              strategy TEXT,decision_status TEXT,rank INTEGER,entry_price TEXT,stop_price TEXT,target1_price TEXT,target2_price TEXT,
              snapshot_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'ACTIVE',created_at TEXT NOT NULL,closed_at TEXT,
              UNIQUE(source, market, ticker, recommendation_date)
            );
            """
        )
        conn.execute(
            "INSERT INTO tracked_recommendation(id,ticker,name,market,source,recommendation_date,reference_price,snapshot_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("legacy", "005930", "삼성전자", "KOSPI", "SCANNER", "2026-09-18", "84000", json.dumps({"legacy": True}), "ACTIVE", "2026-09-18T00:00:00+00:00"),
        )
    repo = RecommendationTrackingRepository(db)
    repo.initialize()
    item = repo.get("legacy")
    assert item is not None
    assert item.snapshot_hash
    assert item.snapshot_schema_version == 1
    with repo.connect() as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE tracked_recommendation SET snapshot_json='{}' WHERE id='legacy'")
