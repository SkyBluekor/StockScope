from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import RecommendationPerformance, TrackedRecommendation


def canonical_snapshot(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_digest(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_snapshot(snapshot).encode("utf-8")).hexdigest()


def _json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"legacy_snapshot_raw": raw}
    return value if isinstance(value, dict) else {"legacy_snapshot": value}


class RecommendationTrackingRepository:
    SCHEMA_VERSION = 4

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
                    snapshot_schema_version INTEGER NOT NULL DEFAULT 1,
                    snapshot_hash TEXT NOT NULL DEFAULT '',
                    has_scanner_source INTEGER NOT NULL DEFAULT 0,
                    has_manual_source INTEGER NOT NULL DEFAULT 0,
                    scanner_snapshot_json TEXT,
                    scanner_snapshot_hash TEXT,
                    scanner_attached_at TEXT,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL,
                    closed_at TEXT,
                    closed_market_date TEXT,
                    close_performance_status TEXT,
                    UNIQUE(source, market, ticker, recommendation_date)
                );
                CREATE INDEX IF NOT EXISTS idx_tracking_status_date
                    ON tracked_recommendation(status, recommendation_date DESC);
                CREATE INDEX IF NOT EXISTS idx_tracking_source_status
                    ON tracked_recommendation(source, status, recommendation_date DESC);

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

            conn.execute("DROP TRIGGER IF EXISTS trg_tracking_snapshot_immutable")
            conn.execute("DROP TRIGGER IF EXISTS trg_tracking_scanner_snapshot_immutable")

            columns = {row["name"] for row in conn.execute("PRAGMA table_info(tracked_recommendation)").fetchall()}
            additions = {
                "snapshot_schema_version": "INTEGER NOT NULL DEFAULT 1",
                "snapshot_hash": "TEXT NOT NULL DEFAULT ''",
                "closed_market_date": "TEXT",
                "close_performance_status": "TEXT",
                "has_scanner_source": "INTEGER NOT NULL DEFAULT 0",
                "has_manual_source": "INTEGER NOT NULL DEFAULT 0",
                "scanner_snapshot_json": "TEXT",
                "scanner_snapshot_hash": "TEXT",
                "scanner_attached_at": "TEXT",
            }
            for name, ddl in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE tracked_recommendation ADD COLUMN {name} {ddl}")

            rows = conn.execute(
                "SELECT id,source,snapshot_json,snapshot_hash,snapshot_schema_version,created_at,scanner_snapshot_json,scanner_snapshot_hash "
                "FROM tracked_recommendation"
            ).fetchall()
            for row in rows:
                snapshot = _json_dict(row["snapshot_json"])
                digest = snapshot_digest(snapshot)
                if not row["snapshot_hash"]:
                    conn.execute(
                        "UPDATE tracked_recommendation SET snapshot_hash=?, snapshot_schema_version=COALESCE(snapshot_schema_version,1) WHERE id=?",
                        (digest, row["id"]),
                    )
                if row["source"] == "SCANNER":
                    scanner_raw = row["scanner_snapshot_json"] or canonical_snapshot(snapshot)
                    scanner_snapshot = _json_dict(scanner_raw)
                    scanner_hash = row["scanner_snapshot_hash"] or snapshot_digest(scanner_snapshot)
                    conn.execute(
                        """UPDATE tracked_recommendation
                           SET has_scanner_source=1,
                               scanner_snapshot_json=COALESCE(scanner_snapshot_json,?),
                               scanner_snapshot_hash=COALESCE(scanner_snapshot_hash,?),
                               scanner_attached_at=COALESCE(scanner_attached_at,created_at)
                           WHERE id=?""",
                        (canonical_snapshot(scanner_snapshot), scanner_hash, row["id"]),
                    )
                if row["source"] == "MANUAL":
                    conn.execute("UPDATE tracked_recommendation SET has_manual_source=1 WHERE id=?", (row["id"],))

            self._merge_existing_same_baseline(conn)

            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_tracking_scanner_flag
                    ON tracked_recommendation(has_scanner_source, status, recommendation_date DESC);
                CREATE INDEX IF NOT EXISTS idx_tracking_manual_flag
                    ON tracked_recommendation(has_manual_source, status, recommendation_date DESC);

                CREATE TRIGGER IF NOT EXISTS trg_tracking_snapshot_immutable
                BEFORE UPDATE OF snapshot_json, snapshot_hash, snapshot_schema_version ON tracked_recommendation
                WHEN NEW.snapshot_json != OLD.snapshot_json
                  OR NEW.snapshot_hash != OLD.snapshot_hash
                  OR NEW.snapshot_schema_version != OLD.snapshot_schema_version
                BEGIN
                    SELECT RAISE(ABORT, 'Tracking snapshot is immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS trg_tracking_scanner_snapshot_immutable
                BEFORE UPDATE OF scanner_snapshot_json, scanner_snapshot_hash ON tracked_recommendation
                WHEN OLD.scanner_snapshot_json IS NOT NULL
                  AND OLD.scanner_snapshot_json != ''
                  AND (COALESCE(NEW.scanner_snapshot_json,'') != COALESCE(OLD.scanner_snapshot_json,'')
                       OR COALESCE(NEW.scanner_snapshot_hash,'') != COALESCE(OLD.scanner_snapshot_hash,''))
                BEGIN
                    SELECT RAISE(ABORT, 'Scanner tracking snapshot is immutable');
                END;
                """
            )
            conn.execute(
                "INSERT INTO tracking_meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(self.SCHEMA_VERSION),),
            )

    @staticmethod
    def _merge_existing_same_baseline(conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT * FROM tracked_recommendation ORDER BY created_at ASC, id ASC").fetchall()
        groups: dict[tuple[str, str, str, Decimal], list[sqlite3.Row]] = {}
        for row in rows:
            try:
                price = Decimal(str(row["reference_price"]))
            except Exception:
                continue
            key = (row["market"], row["ticker"], row["recommendation_date"], price)
            groups.setdefault(key, []).append(row)

        for group in groups.values():
            if len(group) < 2:
                continue
            canonical = group[0]
            canonical_id = canonical["id"]
            duplicate_ids = [row["id"] for row in group[1:]]
            has_scanner = any(bool(row["has_scanner_source"]) or row["source"] == "SCANNER" for row in group)
            has_manual = any(bool(row["has_manual_source"]) or row["source"] == "MANUAL" for row in group)
            scanner_row = next(
                (row for row in group if bool(row["has_scanner_source"]) or row["source"] == "SCANNER"),
                None,
            )
            any_active = any(row["status"] == "ACTIVE" for row in group)
            if any_active:
                status = "ACTIVE"
                closed_at = None
                closed_market_date = None
                close_performance_status = None
            else:
                status = "CLOSED"
                closed_at_values = [row["closed_at"] for row in group if row["closed_at"]]
                closed_market_values = [row["closed_market_date"] for row in group if row["closed_market_date"]]
                closed_at = max(closed_at_values) if closed_at_values else None
                closed_market_date = max(closed_market_values) if closed_market_values else None
                close_performance_status = "FROZEN"

            scanner_values: tuple[Any, ...]
            if scanner_row is not None:
                scanner_snapshot_raw = scanner_row["scanner_snapshot_json"] or scanner_row["snapshot_json"]
                scanner_snapshot = _json_dict(scanner_snapshot_raw)
                scanner_hash = scanner_row["scanner_snapshot_hash"] or snapshot_digest(scanner_snapshot)
                scanner_values = (
                    scanner_row["scanner_version"], scanner_row["scanner_baseline"], scanner_row["strategy"],
                    scanner_row["decision_status"], scanner_row["rank"], scanner_row["entry_price"],
                    scanner_row["stop_price"], scanner_row["target1_price"], scanner_row["target2_price"],
                    canonical_snapshot(scanner_snapshot), scanner_hash,
                    scanner_row["scanner_attached_at"] or scanner_row["created_at"],
                )
            else:
                scanner_values = (None,) * 12

            conn.execute(
                """UPDATE tracked_recommendation SET
                   has_scanner_source=?,has_manual_source=?,
                   scanner_version=?,scanner_baseline=?,strategy=?,decision_status=?,rank=?,entry_price=?,stop_price=?,target1_price=?,target2_price=?,
                   scanner_snapshot_json=?,scanner_snapshot_hash=?,scanner_attached_at=?,
                   status=?,closed_at=?,closed_market_date=?,close_performance_status=?
                   WHERE id=?""",
                (
                    int(has_scanner), int(has_manual), *scanner_values,
                    status, closed_at, closed_market_date, close_performance_status, canonical_id,
                ),
            )

            performance_rows = conn.execute(
                f"SELECT * FROM recommendation_performance WHERE recommendation_id IN ({','.join('?' for _ in group)}) ORDER BY updated_at DESC",
                tuple(row["id"] for row in group),
            ).fetchall()
            if performance_rows:
                newest = performance_rows[0]
                newest_id = newest["recommendation_id"]
                if newest_id != canonical_id:
                    conn.execute("DELETE FROM recommendation_performance WHERE recommendation_id=?", (canonical_id,))
                    conn.execute(
                        "UPDATE recommendation_performance SET recommendation_id=? WHERE recommendation_id=?",
                        (canonical_id, newest_id),
                    )
                for perf in performance_rows:
                    perf_id = perf["recommendation_id"]
                    if perf_id not in {canonical_id, newest_id}:
                        conn.execute("DELETE FROM recommendation_performance WHERE recommendation_id=?", (perf_id,))

            for duplicate_id in duplicate_ids:
                conn.execute("DELETE FROM tracked_recommendation WHERE id=?", (duplicate_id,))

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TrackedRecommendation:
        snapshot = _json_dict(row["snapshot_json"])
        scanner_snapshot = _json_dict(row["scanner_snapshot_json"])
        return TrackedRecommendation(
            id=row["id"], ticker=row["ticker"], name=row["name"], market=row["market"], source=row["source"],
            recommendation_date=date.fromisoformat(row["recommendation_date"]),
            reference_price=Decimal(row["reference_price"]), scanner_version=row["scanner_version"],
            scanner_baseline=row["scanner_baseline"], strategy=row["strategy"], decision_status=row["decision_status"],
            rank=row["rank"], entry_price=Decimal(row["entry_price"]) if row["entry_price"] else None,
            stop_price=Decimal(row["stop_price"]) if row["stop_price"] else None,
            target1_price=Decimal(row["target1_price"]) if row["target1_price"] else None,
            target2_price=Decimal(row["target2_price"]) if row["target2_price"] else None,
            snapshot=snapshot,
            snapshot_schema_version=int(row["snapshot_schema_version"] or 1),
            snapshot_hash=str(row["snapshot_hash"] or ""),
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
            closed_market_date=date.fromisoformat(row["closed_market_date"]) if row["closed_market_date"] else None,
            close_performance_status=row["close_performance_status"],
            has_scanner_source=bool(row["has_scanner_source"]),
            has_manual_source=bool(row["has_manual_source"]),
            scanner_snapshot=scanner_snapshot,
            scanner_snapshot_hash=row["scanner_snapshot_hash"],
            scanner_attached_at=datetime.fromisoformat(row["scanner_attached_at"]) if row["scanner_attached_at"] else None,
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
            mfe_pct=dec("mfe_pct"), mae_pct=dec("mae_pct"), highest_price=dec("highest_price"), highest_date=day("highest_date"),
            lowest_price=dec("lowest_price"), lowest_date=day("lowest_date"), return_5d=dec("return_5d"),
            return_10d=dec("return_10d"), return_20d=dec("return_20d"),
            entry_touched=bool(row["entry_touched"]), entry_touch_date=day("entry_touch_date"),
            stop_touched=bool(row["stop_touched"]), stop_touch_date=day("stop_touch_date"),
            target1_touched=bool(row["target1_touched"]), target1_touch_date=day("target1_touch_date"),
            target2_touched=bool(row["target2_touched"]), target2_touch_date=day("target2_touch_date"),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def find_same_baseline(self, *, market: str, ticker: str, recommendation_date: date, reference_price: Decimal) -> TrackedRecommendation | None:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tracked_recommendation WHERE market=? AND ticker=? AND recommendation_date=? ORDER BY created_at ASC, id ASC",
                (market, ticker, recommendation_date.isoformat()),
            ).fetchall()
        for row in rows:
            try:
                if Decimal(str(row["reference_price"])) == reference_price:
                    return self._from_row(row)
            except Exception:
                continue
        return None

    def find_duplicate(self, *, source: str, market: str, ticker: str, recommendation_date: date) -> TrackedRecommendation | None:
        source = source.upper()
        source_clause = "has_scanner_source=1" if source == "SCANNER" else "has_manual_source=1"
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT * FROM tracked_recommendation WHERE ({source_clause} OR source=?) AND market=? AND ticker=? AND recommendation_date=? ORDER BY created_at ASC LIMIT 1",
                (source, market, ticker, recommendation_date.isoformat()),
            ).fetchone()
        return self._from_row(row) if row else None

    def find_active_manual(self, *, market: str, ticker: str) -> TrackedRecommendation | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tracked_recommendation WHERE (has_manual_source=1 OR source='MANUAL') AND market=? AND ticker=? AND status='ACTIVE' ORDER BY created_at DESC LIMIT 1",
                (market, ticker),
            ).fetchone()
        return self._from_row(row) if row else None

    def attach_scanner(self, item_id: str, *, metadata: dict[str, Any], snapshot: dict[str, Any], attached_at: datetime) -> TrackedRecommendation:
        digest = snapshot_digest(snapshot)
        with self.connect() as conn:
            conn.execute(
                """UPDATE tracked_recommendation SET
                   has_scanner_source=1,
                   scanner_version=?,scanner_baseline=?,strategy=?,decision_status=?,rank=?,entry_price=?,stop_price=?,target1_price=?,target2_price=?,
                   scanner_snapshot_json=?,scanner_snapshot_hash=?,scanner_attached_at=?
                   WHERE id=? AND has_scanner_source=0""",
                (
                    metadata.get("scanner_version"), metadata.get("scanner_baseline"), metadata.get("strategy"), metadata.get("decision_status"),
                    metadata.get("rank"),
                    str(metadata.get("entry_price")) if metadata.get("entry_price") is not None else None,
                    str(metadata.get("stop_price")) if metadata.get("stop_price") is not None else None,
                    str(metadata.get("target1_price")) if metadata.get("target1_price") is not None else None,
                    str(metadata.get("target2_price")) if metadata.get("target2_price") is not None else None,
                    canonical_snapshot(snapshot), digest, attached_at.isoformat(), item_id,
                ),
            )
        item = self.get(item_id)
        if item is None:
            raise KeyError(item_id)
        return item

    def attach_manual(self, item_id: str) -> TrackedRecommendation:
        with self.connect() as conn:
            conn.execute("UPDATE tracked_recommendation SET has_manual_source=1 WHERE id=?", (item_id,))
        item = self.get(item_id)
        if item is None:
            raise KeyError(item_id)
        return item

    def insert(self, item: TrackedRecommendation) -> None:
        scanner_snapshot = item.scanner_snapshot or (item.snapshot if item.scanner_source else {})
        scanner_hash = item.scanner_snapshot_hash or (snapshot_digest(scanner_snapshot) if scanner_snapshot else None)
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO tracked_recommendation(
                id,ticker,name,market,source,recommendation_date,reference_price,scanner_version,scanner_baseline,
                strategy,decision_status,rank,entry_price,stop_price,target1_price,target2_price,snapshot_json,
                snapshot_schema_version,snapshot_hash,has_scanner_source,has_manual_source,scanner_snapshot_json,scanner_snapshot_hash,scanner_attached_at,
                status,created_at,closed_at,closed_market_date,close_performance_status
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.id, item.ticker, item.name, item.market, item.source, item.recommendation_date.isoformat(),
                    str(item.reference_price), item.scanner_version, item.scanner_baseline, item.strategy, item.decision_status,
                    item.rank, str(item.entry_price) if item.entry_price is not None else None,
                    str(item.stop_price) if item.stop_price is not None else None,
                    str(item.target1_price) if item.target1_price is not None else None,
                    str(item.target2_price) if item.target2_price is not None else None,
                    canonical_snapshot(item.snapshot), item.snapshot_schema_version, item.snapshot_hash,
                    int(item.scanner_source), int(item.manual_source),
                    canonical_snapshot(scanner_snapshot) if scanner_snapshot else None, scanner_hash,
                    item.scanner_attached_at.isoformat() if item.scanner_attached_at else (item.created_at.isoformat() if item.scanner_source else None),
                    item.status, item.created_at.isoformat(), item.closed_at.isoformat() if item.closed_at else None,
                    item.closed_market_date.isoformat() if item.closed_market_date else None,
                    item.close_performance_status,
                ),
            )

    def list(self, *, status: str | None = None, source: str | None = None) -> list[TrackedRecommendation]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status=?")
            params.append(status)
        if source == "SCANNER":
            clauses.append("(has_scanner_source=1 OR source='SCANNER')")
        elif source == "MANUAL":
            clauses.append("(has_manual_source=1 OR source='MANUAL')")
        sql = "SELECT * FROM tracked_recommendation"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY recommendation_date DESC, created_at DESC"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, item_id: str) -> TrackedRecommendation | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tracked_recommendation WHERE id=?", (item_id,)).fetchone()
        return self._from_row(row) if row else None

    def close(self, item_id: str, closed_at: datetime, closed_market_date: date | None) -> TrackedRecommendation | None:
        with self.connect() as conn:
            conn.execute(
                """UPDATE tracked_recommendation
                   SET status='CLOSED', closed_at=?, closed_market_date=?, close_performance_status='FROZEN'
                   WHERE id=? AND status!='CLOSED'""",
                (closed_at.isoformat(), closed_market_date.isoformat() if closed_market_date else None, item_id),
            )
        return self.get(item_id)

    def verify_snapshot(self, item: TrackedRecommendation) -> bool:
        base_ok = bool(item.snapshot_hash) and snapshot_digest(item.snapshot) == item.snapshot_hash
        if not base_ok:
            return False
        if item.scanner_source:
            return bool(item.scanner_snapshot_hash) and snapshot_digest(item.scanner_snapshot) == item.scanner_snapshot_hash
        return True

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
                    p.recommendation_id, p.market_date.isoformat() if p.market_date else None,
                    p.latest_date.isoformat() if p.latest_date else None,
                    str(p.latest_close) if p.latest_close is not None else None, p.price_status, p.trading_days,
                    str(p.current_return_pct) if p.current_return_pct is not None else None,
                    str(p.mfe_pct) if p.mfe_pct is not None else None, str(p.mae_pct) if p.mae_pct is not None else None,
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

    def delete(self, item_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM tracked_recommendation WHERE id=?", (item_id,))
        return cursor.rowcount == 1
