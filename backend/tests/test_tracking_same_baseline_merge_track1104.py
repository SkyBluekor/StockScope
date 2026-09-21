from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.tracking.service import RecommendationTrackingService
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
        close = Decimal("132500") if day == date(2026, 9, 18) else Decimal("135000")
        return SimpleNamespace(market=market, close=close, open=close, high=close + 1000, low=close - 1000)


def service(tmp_path: Path):
    return RecommendationTrackingService(RecommendationTrackingRepository(tmp_path / "tracking.db"), FakeMarket())


def scanner_payload():
    return {
        "ticker": "000880",
        "name": "한화",
        "market": "KOSPI",
        "recommendation_date": date(2026, 9, 18),
        "scanner_version": "0.21.3.7",
        "decision_status": "READY",
        "rank": 3,
        "entry_price": "131000",
        "stop_price": "125000",
        "target1_price": "140000",
        "snapshot": {
            "candidate": {
                "entry_risk_guide": {
                    "price_rule": {"kind": "AT_OR_BELOW", "trigger_price": 131000}
                }
            }
        },
    }


def test_manual_then_scanner_same_baseline_merges_into_one_row(tmp_path):
    svc = service(tmp_path)
    manual, created = svc.create_manual({"ticker": "000880", "name": "한화", "market": "KOSPI"})
    assert created is True

    merged, created_scanner = svc.create_scanner(scanner_payload())
    assert created_scanner is False
    assert merged.id == manual.id
    assert merged.manual_source is True
    assert merged.scanner_source is True
    assert merged.rank == 3
    assert merged.scanner_version == "0.21.3.7"
    assert merged.scanner_snapshot["candidate"]["entry_risk_guide"]["price_rule"]["kind"] == "AT_OR_BELOW"
    assert len(svc.list()) == 1
    assert len(svc.list(source="SCANNER")) == 1
    assert len(svc.list(source="MANUAL")) == 1


def test_scanner_then_manual_same_baseline_merges_into_one_row(tmp_path):
    svc = service(tmp_path)
    scanner, created = svc.create_scanner(scanner_payload())
    assert created is True

    merged, created_manual = svc.create_manual({"ticker": "000880", "name": "한화", "market": "KOSPI"})
    assert created_manual is False
    assert merged.id == scanner.id
    assert merged.scanner_source is True
    assert merged.manual_source is True
    assert len(svc.list()) == 1


def test_merged_manual_origin_uses_scanner_snapshot_for_entry_semantics(tmp_path):
    svc = service(tmp_path)
    manual, _ = svc.create_manual({"ticker": "000880", "name": "한화", "market": "KOSPI"})
    merged, _ = svc.create_scanner(scanner_payload())
    assert merged.id == manual.id
    performance = svc.refresh(merged.id)
    assert performance.trading_days == 1
    assert performance.entry_touched is False  # D+1 low is 134000, above the 131000 pullback trigger.
    assert performance.target1_touched is False


def test_v3_duplicate_rows_migrate_to_one_canonical_row(tmp_path):
    db = tmp_path / "tracking.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE tracked_recommendation (
              id TEXT PRIMARY KEY,ticker TEXT NOT NULL,name TEXT NOT NULL,market TEXT NOT NULL,source TEXT NOT NULL,
              recommendation_date TEXT NOT NULL,reference_price TEXT NOT NULL,scanner_version TEXT,scanner_baseline TEXT,
              strategy TEXT,decision_status TEXT,rank INTEGER,entry_price TEXT,stop_price TEXT,target1_price TEXT,target2_price TEXT,
              snapshot_json TEXT NOT NULL,snapshot_schema_version INTEGER NOT NULL DEFAULT 1,snapshot_hash TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'ACTIVE',created_at TEXT NOT NULL,closed_at TEXT,closed_market_date TEXT,close_performance_status TEXT,
              UNIQUE(source, market, ticker, recommendation_date)
            );
            CREATE TABLE recommendation_performance (
              recommendation_id TEXT PRIMARY KEY,market_date TEXT,latest_date TEXT,latest_close TEXT,price_status TEXT NOT NULL DEFAULT 'WAITING',
              trading_days INTEGER NOT NULL DEFAULT 0,current_return_pct TEXT,mfe_pct TEXT,mae_pct TEXT,highest_price TEXT,highest_date TEXT,
              lowest_price TEXT,lowest_date TEXT,return_5d TEXT,return_10d TEXT,return_20d TEXT,entry_touched INTEGER NOT NULL DEFAULT 0,
              entry_touch_date TEXT,stop_touched INTEGER NOT NULL DEFAULT 0,stop_touch_date TEXT,target1_touched INTEGER NOT NULL DEFAULT 0,
              target1_touch_date TEXT,target2_touched INTEGER NOT NULL DEFAULT 0,target2_touch_date TEXT,updated_at TEXT NOT NULL
            );
            """
        )
        manual_snapshot = json.dumps({"kind": "MANUAL_TRACKING"})
        scanner_snapshot = json.dumps({"candidate": {"rank": 3}})
        common = ("000880", "한화", "KOSPI", "2026-09-18", "132500")
        conn.execute(
            "INSERT INTO tracked_recommendation(id,ticker,name,market,source,recommendation_date,reference_price,snapshot_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("manual", *common[:3], "MANUAL", common[3], common[4], manual_snapshot, "ACTIVE", "2026-09-18T00:00:00+00:00"),
        )
        conn.execute(
            """INSERT INTO tracked_recommendation(
               id,ticker,name,market,source,recommendation_date,reference_price,scanner_version,decision_status,rank,snapshot_json,status,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("scanner", *common[:3], "SCANNER", common[3], common[4], "0.21.3.7", "READY", 3, scanner_snapshot, "ACTIVE", "2026-09-18T00:01:00+00:00"),
        )

    repo = RecommendationTrackingRepository(db)
    repo.initialize()
    rows = repo.list()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == "manual"
    assert row.manual_source and row.scanner_source
    assert row.rank == 3
    assert row.scanner_snapshot == {"candidate": {"rank": 3}}


def test_same_ticker_date_but_different_reference_price_stays_separate(tmp_path):
    db = tmp_path / "tracking.db"
    repo = RecommendationTrackingRepository(db)
    repo.initialize()
    # The production service derives one close per market/date, so this edge case is
    # exercised through legacy rows: different baselines must not be auto-merged.
    with repo.connect() as conn:
        conn.execute("DROP TRIGGER IF EXISTS trg_tracking_snapshot_immutable")
        conn.execute(
            """INSERT INTO tracked_recommendation(
            id,ticker,name,market,source,recommendation_date,reference_price,snapshot_json,snapshot_schema_version,snapshot_hash,
            has_scanner_source,has_manual_source,status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("s", "000880", "한화", "KOSPI", "SCANNER", "2026-09-18", "132500", "{}", 1, "x", 1, 0, "ACTIVE", "2026-09-18T00:00:00+00:00"),
        )
        conn.execute(
            """INSERT INTO tracked_recommendation(
            id,ticker,name,market,source,recommendation_date,reference_price,snapshot_json,snapshot_schema_version,snapshot_hash,
            has_scanner_source,has_manual_source,status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("m", "000880", "한화", "KOSPI", "MANUAL", "2026-09-18", "133000", "{}", 1, "x", 0, 1, "ACTIVE", "2026-09-18T00:01:00+00:00"),
        )
    repo.initialize()
    assert len(repo.list()) == 2
