from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import TrackedRecommendation


class RecommendationTrackingRepository:
    SCHEMA_VERSION = 1

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
