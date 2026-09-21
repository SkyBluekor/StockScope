from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import RecommendationPerformance, TrackedRecommendation


class RecommendationTrackingRepository:
    SCHEMA_VERSION = 2

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tracking_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tracked_recommendation (
                    id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    source TEXT NOT NULL,
                    recommendation_date TEXT NOT NULL,
                    reference_price TEXT NOT NULL,
                    scanner_version TEXT,
                    scanner_baseline TEXT,
                    strategy TEXT,
                    decision_status TEXT,
                    rank INTEGER,
                    entry_price TEXT,
                    stop_price TEXT,
                    target1_price TEXT,
                    target2_price TEXT,
                    snapshot_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL,
                    closed_at TEXT,
                    UNIQUE(source, market, ticker, recommendation_date)
                );
                CREATE INDEX IF NOT EXISTS idx_tracking_status_date
                    ON tracked_recommendation(status, recommendation_date DESC);

                CREATE TABLE IF NOT EXISTS recommendation_performance (
                    recommendation_id TEXT PRIMARY KEY,
                    market_date TEXT,
                    latest_date TEXT,
                    latest_close TEXT,
                    price_status TEXT NOT NULL DEFAULT 'WAITING',
                    trading_days INTEGER NOT NULL DEFAULT 0,
                    current_return_pct TEXT,
                    mfe_pct TEXT,
                    mae_pct TEXT,
                    highest_price TEXT,
                    highest_date TEXT,
                    lowest_price TEXT,
                    lowest_date TEXT,
                    return_5d TEXT,
                    return_10d TEXT,
                    return_20d TEXT,
                    entry_touched INTEGER NOT NULL DEFAULT 0,
                    entry_touch_date TEXT,
                    stop_touched INTEGER NOT NULL DEFAULT 0,
                    stop_touch_date TEXT,
                    target1_touched INTEGER NOT NULL DEFAULT 0,
                    target1_touch_date TEXT,
                    target2_touched INTEGER NOT NULL DEFAULT 0,
                    target2_touch_date TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(recommendation_id) REFERENCES tracked_recommendation(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                "INSERT INTO tracking_meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(self.SCHEMA_VERSION),),
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TrackedRecommendation:
        return TrackedRecommendation(
            id=row["id"], ticker=row["ticker"], name=row["name"], market=row["market"], source=row["source"],
            recommendation_date=date.fromisoformat(row["recommendation_date"]),
            reference_price=Decimal(row["reference_price"]), scanner_version=row["scanner_version"],
            scanner_baseline=row["scanner_baseline"], strategy=row["strategy"], decision_status=row["decision_status"],
            rank=row["rank"], entry_price=Decimal(row["entry_price"]) if row["entry_price"] else None,
            stop_price=Decimal(row["stop_price"]) if row["stop_price"] else None,
            target1_price=Decimal(row["target1_price"]) if row["target1_price"] else None,
            target2_price=Decimal(row["target2_price"]) if row["target2_price"] else None,
            snapshot=json.loads(row["snapshot_json"]), status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
        )

    @staticmethod
    def _performance_from_row(row: sqlite3.Row) -> RecommendationPerformance:
        def dec(name: str) -> Decimal | None:
            return Decimal(row[name]) if row[name] not in (None, "") else None

        def day(name: str) -> date | None:
            return date.fromisoformat(row[name]) if row[name] else None

        return RecommendationPerformance(
            recommendation_id=row["recommendation_id"],
            market_date=day("market_date"), latest_date=day("latest_date"), latest_close=dec("latest_close"),
            price_status=row["price_status"], trading_days=int(row["trading_days"]), current_return_pct=dec("current_return_pct"),
            mfe_pct=dec("mfe_pct"), mae_pct=dec("mae_pct"),
            highest_price=dec("highest_price"), highest_date=day("highest_date"),
            lowest_price=dec("lowest_price"), lowest_date=day("lowest_date"),
            return_5d=dec("return_5d"), return_10d=dec("return_10d"), return_20d=dec("return_20d"),
            entry_touched=bool(row["entry_touched"]), entry_touch_date=day("entry_touch_date"),
            stop_touched=bool(row["stop_touched"]), stop_touch_date=day("stop_touch_date"),
            target1_touched=bool(row["target1_touched"]), target1_touch_date=day("target1_touch_date"),
            target2_touched=bool(row["target2_touched"]), target2_touch_date=day("target2_touch_date"),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def find_duplicate(self, *, source: str, market: str, ticker: str, recommendation_date: date) -> TrackedRecommendation | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tracked_recommendation WHERE source=? AND market=? AND ticker=? AND recommendation_date=?",
                (source, market, ticker, recommendation_date.isoformat()),
            ).fetchone()
        return self._from_row(row) if row else None

    def insert(self, item: TrackedRecommendation) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO tracked_recommendation(
                id,ticker,name,market,source,recommendation_date,reference_price,scanner_version,scanner_baseline,
                strategy,decision_status,rank,entry_price,stop_price,target1_price,target2_price,snapshot_json,
                status,created_at,closed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.id, item.ticker, item.name, item.market, item.source, item.recommendation_date.isoformat(),
                    str(item.reference_price), item.scanner_version, item.scanner_baseline, item.strategy,
                    item.decision_status, item.rank, str(item.entry_price) if item.entry_price is not None else None,
                    str(item.stop_price) if item.stop_price is not None else None,
                    str(item.target1_price) if item.target1_price is not None else None,
                    str(item.target2_price) if item.target2_price is not None else None,
                    json.dumps(item.snapshot, ensure_ascii=False, separators=(",", ":")), item.status,
                    item.created_at.isoformat(), item.closed_at.isoformat() if item.closed_at else None,
                ),
            )

    def list(self, *, status: str | None = None) -> list[TrackedRecommendation]:
        sql = "SELECT * FROM tracked_recommendation"
        params: tuple[Any, ...] = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        sql += " ORDER BY recommendation_date DESC, created_at DESC"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, item_id: str) -> TrackedRecommendation | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tracked_recommendation WHERE id=?", (item_id,)).fetchone()
        return self._from_row(row) if row else None

    def close(self, item_id: str, closed_at: datetime) -> TrackedRecommendation | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE tracked_recommendation SET status='CLOSED', closed_at=? WHERE id=? AND status!='CLOSED'",
                (closed_at.isoformat(), item_id),
            )
        return self.get(item_id)

    def upsert_performance(self, performance: RecommendationPerformance) -> None:
        p = performance
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO recommendation_performance(
                recommendation_id,market_date,latest_date,latest_close,price_status,trading_days,current_return_pct,mfe_pct,mae_pct,
                highest_price,highest_date,lowest_price,lowest_date,return_5d,return_10d,return_20d,
                entry_touched,entry_touch_date,stop_touched,stop_touch_date,target1_touched,target1_touch_date,
                target2_touched,target2_touch_date,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(recommendation_id) DO UPDATE SET
                market_date=excluded.market_date,latest_date=excluded.latest_date,latest_close=excluded.latest_close,price_status=excluded.price_status,trading_days=excluded.trading_days,
                current_return_pct=excluded.current_return_pct,mfe_pct=excluded.mfe_pct,mae_pct=excluded.mae_pct,
                highest_price=excluded.highest_price,highest_date=excluded.highest_date,
                lowest_price=excluded.lowest_price,lowest_date=excluded.lowest_date,
                return_5d=excluded.return_5d,return_10d=excluded.return_10d,return_20d=excluded.return_20d,
                entry_touched=excluded.entry_touched,entry_touch_date=excluded.entry_touch_date,
                stop_touched=excluded.stop_touched,stop_touch_date=excluded.stop_touch_date,
                target1_touched=excluded.target1_touched,target1_touch_date=excluded.target1_touch_date,
                target2_touched=excluded.target2_touched,target2_touch_date=excluded.target2_touch_date,
                updated_at=excluded.updated_at""",
                (
                    p.recommendation_id,
                    p.market_date.isoformat() if p.market_date else None,
                    p.latest_date.isoformat() if p.latest_date else None,
                    str(p.latest_close) if p.latest_close is not None else None,
                    p.price_status,
                    p.trading_days,
                    str(p.current_return_pct) if p.current_return_pct is not None else None,
                    str(p.mfe_pct) if p.mfe_pct is not None else None,
                    str(p.mae_pct) if p.mae_pct is not None else None,
                    str(p.highest_price) if p.highest_price is not None else None,
                    p.highest_date.isoformat() if p.highest_date else None,
                    str(p.lowest_price) if p.lowest_price is not None else None,
                    p.lowest_date.isoformat() if p.lowest_date else None,
                    str(p.return_5d) if p.return_5d is not None else None,
                    str(p.return_10d) if p.return_10d is not None else None,
                    str(p.return_20d) if p.return_20d is not None else None,
                    int(p.entry_touched), p.entry_touch_date.isoformat() if p.entry_touch_date else None,
                    int(p.stop_touched), p.stop_touch_date.isoformat() if p.stop_touch_date else None,
                    int(p.target1_touched), p.target1_touch_date.isoformat() if p.target1_touch_date else None,
                    int(p.target2_touched), p.target2_touch_date.isoformat() if p.target2_touch_date else None,
                    p.updated_at.isoformat(),
                ),
            )

    def get_performance(self, recommendation_id: str) -> RecommendationPerformance | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM recommendation_performance WHERE recommendation_id=?", (recommendation_id,)
            ).fetchone()
        return self._performance_from_row(row) if row else None
