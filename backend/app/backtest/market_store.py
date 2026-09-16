from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.backtest.history_store import HistorySeries


@dataclass(frozen=True)
class MarketStoreStats:
    stock_rows: int = 0
    index_rows: int = 0
    stock_days: int = 0
    index_days: int = 0


class HistoricalMarketStore:
    """SQLite market-wide history store shared by every stock in the same market.

    A KRX stock-by-date response contains the entire market. Persisting that payload
    by market/date means the next stock can reuse it without reopening hundreds of
    raw gzip files or issuing another network request.
    """

    _default_db = Path(__file__).resolve().parents[2] / "runtime" / "market_history" / "market_history.db"

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or self._default_db
        self._lock = threading.RLock()
        self._ensure_schema()

    @staticmethod
    def _market(market: str) -> str:
        value = market.upper().strip()
        if value not in {"KOSPI", "KOSDAQ"}:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")
        return value

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=20.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=20000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stock_daily (
                    market TEXT NOT NULL,
                    bas_dd TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    row_json TEXT NOT NULL,
                    PRIMARY KEY (market, bas_dd, stock_code)
                );
                CREATE INDEX IF NOT EXISTS idx_stock_daily_lookup
                    ON stock_daily(market, stock_code, bas_dd);

                CREATE TABLE IF NOT EXISTS main_index_daily (
                    market TEXT NOT NULL,
                    bas_dd TEXT NOT NULL,
                    row_json TEXT NOT NULL,
                    PRIMARY KEY (market, bas_dd)
                );

                CREATE TABLE IF NOT EXISTS day_status (
                    market TEXT NOT NULL,
                    bas_dd TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('stock', 'index')),
                    status TEXT NOT NULL CHECK(status IN ('data', 'empty')),
                    PRIMARY KEY (market, bas_dd, kind)
                );
                """
            )

    @staticmethod
    def _dump(row: dict[str, Any]) -> str:
        return json.dumps(row, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _load(raw: str) -> dict[str, Any]:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}

    def put_stock_day(self, market: str, bas_dd: str, rows: Iterable[dict[str, Any]], *, stable: bool) -> int:
        market = self._market(market)
        normalized = [row for row in rows if str(row.get("code") or "").strip()]
        with self._lock, self._connect() as conn:
            if normalized:
                conn.executemany(
                    """
                    INSERT INTO stock_daily(market, bas_dd, stock_code, row_json)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(market, bas_dd, stock_code) DO UPDATE SET row_json = excluded.row_json
                    """,
                    [
                        (market, bas_dd, str(row.get("code") or "").strip().upper(), self._dump(row))
                        for row in normalized
                    ],
                )
            if stable:
                conn.execute(
                    """
                    INSERT INTO day_status(market, bas_dd, kind, status)
                    VALUES (?, ?, 'stock', ?)
                    ON CONFLICT(market, bas_dd, kind) DO UPDATE SET status = excluded.status
                    """,
                    (market, bas_dd, "data" if normalized else "empty"),
                )
        return len(normalized)

    def put_index_day(self, market: str, bas_dd: str, row: dict[str, Any] | None, *, stable: bool) -> None:
        market = self._market(market)
        with self._lock, self._connect() as conn:
            if row is not None:
                conn.execute(
                    """
                    INSERT INTO main_index_daily(market, bas_dd, row_json)
                    VALUES (?, ?, ?)
                    ON CONFLICT(market, bas_dd) DO UPDATE SET row_json = excluded.row_json
                    """,
                    (market, bas_dd, self._dump(row)),
                )
            if stable:
                conn.execute(
                    """
                    INSERT INTO day_status(market, bas_dd, kind, status)
                    VALUES (?, ?, 'index', ?)
                    ON CONFLICT(market, bas_dd, kind) DO UPDATE SET status = excluded.status
                    """,
                    (market, bas_dd, "data" if row is not None else "empty"),
                )

    def import_legacy_stock(self, market: str, code: str, series: HistorySeries) -> int:
        market = self._market(market)
        code = code.strip().upper()
        rows = [
            (market, key, code, self._dump(row))
            for key, row in series.rows.items()
            if isinstance(row, dict)
        ]
        if not rows:
            return 0
        with self._lock, self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO stock_daily(market, bas_dd, stock_code, row_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(market, bas_dd, stock_code) DO NOTHING
                """,
                rows,
            )
        return len(rows)

    def import_legacy_index(self, market: str, series: HistorySeries) -> int:
        market = self._market(market)
        rows = [(market, key, self._dump(row)) for key, row in series.rows.items() if isinstance(row, dict)]
        with self._lock, self._connect() as conn:
            if rows:
                conn.executemany(
                    """
                    INSERT INTO main_index_daily(market, bas_dd, row_json)
                    VALUES (?, ?, ?)
                    ON CONFLICT(market, bas_dd) DO NOTHING
                    """,
                    rows,
                )
            # Legacy index history is already the selected main index and its checked dates
            # were stable when persisted, so it is safe to mark these dates complete.
            for key in series.checked_dates:
                status = "data" if key in series.rows else "empty"
                conn.execute(
                    """
                    INSERT INTO day_status(market, bas_dd, kind, status)
                    VALUES (?, ?, 'index', ?)
                    ON CONFLICT(market, bas_dd, kind) DO NOTHING
                    """,
                    (market, key, status),
                )
        return len(rows)

    def has_stock_row(self, market: str, code: str, bas_dd: str) -> bool:
        market = self._market(market)
        with self._lock, self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM stock_daily WHERE market=? AND stock_code=? AND bas_dd=? LIMIT 1",
                (market, code.upper(), bas_dd),
            ).fetchone() is not None

    def day_complete(self, market: str, bas_dd: str, kind: str) -> bool:
        market = self._market(market)
        with self._lock, self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM day_status WHERE market=? AND bas_dd=? AND kind=? LIMIT 1",
                (market, bas_dd, kind),
            ).fetchone() is not None

    def completed_days(self, market: str, start_dd: str, end_dd: str, kind: str) -> set[str]:
        market = self._market(market)
        if kind not in {"stock", "index"}:
            raise ValueError("kind는 stock 또는 index여야 합니다.")
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT bas_dd FROM day_status WHERE market=? AND kind=? AND bas_dd>=? AND bas_dd<=?",
                (market, kind, start_dd, end_dd),
            ).fetchall()
        return {str(row["bas_dd"]) for row in rows}

    def stock_series(self, market: str, code: str, start_dd: str | None = None, end_dd: str | None = None) -> HistorySeries:
        market = self._market(market)
        clauses = ["market=?", "stock_code=?"]
        params: list[Any] = [market, code.upper()]
        if start_dd:
            clauses.append("bas_dd>=?")
            params.append(start_dd)
        if end_dd:
            clauses.append("bas_dd<=?")
            params.append(end_dd)
        status_clauses = ["market=?", "kind='stock'"]
        status_params: list[Any] = [market]
        if start_dd:
            status_clauses.append("bas_dd>=?")
            status_params.append(start_dd)
        if end_dd:
            status_clauses.append("bas_dd<=?")
            status_params.append(end_dd)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT bas_dd,row_json FROM stock_daily WHERE {' AND '.join(clauses)} ORDER BY bas_dd",
                params,
            ).fetchall()
            statuses = conn.execute(
                f"SELECT bas_dd FROM day_status WHERE {' AND '.join(status_clauses)}",
                status_params,
            ).fetchall()
        return HistorySeries(
            rows={str(row["bas_dd"]): self._load(str(row["row_json"])) for row in rows},
            checked_dates={str(row["bas_dd"]) for row in statuses},
        )

    def latest_complete_date(self, market: str, kind: str = "stock", end_dd: str | None = None) -> str | None:
        market = self._market(market)
        if kind not in {"stock", "index"}:
            raise ValueError("kind는 stock 또는 index여야 합니다.")
        clauses = ["market=?", "kind=?", "status='data'"]
        params: list[Any] = [market, kind]
        if end_dd:
            clauses.append("bas_dd<=?")
            params.append(end_dd)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"SELECT MAX(bas_dd) AS bas_dd FROM day_status WHERE {' AND '.join(clauses)}",
                params,
            ).fetchone()
        value = None if row is None else row["bas_dd"]
        return str(value) if value else None

    def stock_day_rows(self, market: str, bas_dd: str) -> list[dict[str, Any]]:
        market = self._market(market)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT row_json FROM stock_daily WHERE market=? AND bas_dd=? ORDER BY stock_code",
                (market, bas_dd),
            ).fetchall()
        return [self._load(str(row["row_json"])) for row in rows]

    def stock_series_many(
        self,
        market: str,
        codes: Iterable[str],
        start_dd: str | None = None,
        end_dd: str | None = None,
    ) -> dict[str, HistorySeries]:
        market = self._market(market)
        normalized_codes = sorted({str(code).strip().upper() for code in codes if str(code).strip()})
        if not normalized_codes:
            return {}
        placeholders = ",".join("?" for _ in normalized_codes)
        clauses = ["market=?", f"stock_code IN ({placeholders})"]
        params: list[Any] = [market, *normalized_codes]
        if start_dd:
            clauses.append("bas_dd>=?")
            params.append(start_dd)
        if end_dd:
            clauses.append("bas_dd<=?")
            params.append(end_dd)
        status_clauses = ["market=?", "kind='stock'"]
        status_params: list[Any] = [market]
        if start_dd:
            status_clauses.append("bas_dd>=?")
            status_params.append(start_dd)
        if end_dd:
            status_clauses.append("bas_dd<=?")
            status_params.append(end_dd)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT bas_dd,stock_code,row_json FROM stock_daily WHERE {' AND '.join(clauses)} ORDER BY stock_code,bas_dd",
                params,
            ).fetchall()
            statuses = conn.execute(
                f"SELECT bas_dd FROM day_status WHERE {' AND '.join(status_clauses)}",
                status_params,
            ).fetchall()
        checked_dates = {str(row["bas_dd"]) for row in statuses}
        result = {code: HistorySeries(rows={}, checked_dates=set(checked_dates)) for code in normalized_codes}
        for row in rows:
            code = str(row["stock_code"])
            series = result.setdefault(code, HistorySeries(rows={}, checked_dates=set(checked_dates)))
            series.rows[str(row["bas_dd"])] = self._load(str(row["row_json"]))
        return result


    def research_candidates(
        self,
        market: str,
        start_dd: str,
        end_dd: str,
        *,
        minimum_coverage_pct: float = 90.0,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Return locally available symbols suitable for research without network fill.

        Coverage is measured against market trading days that already exist in the
        Market Store (day_status=stock/data), not calendar weekdays.
        """
        market = self._market(market)
        with self._lock, self._connect() as conn:
            trading_row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM day_status
                WHERE market=? AND kind='stock' AND status='data' AND bas_dd>=? AND bas_dd<=?
                """,
                (market, start_dd, end_dd),
            ).fetchone()
            trading_days = int((trading_row or {"cnt": 0})["cnt"] or 0)
            index_row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM day_status
                WHERE market=? AND kind='index' AND status='data' AND bas_dd>=? AND bas_dd<=?
                """,
                (market, start_dd, end_dd),
            ).fetchone()
            index_days = int((index_row or {"cnt": 0})["cnt"] or 0)
            rows = conn.execute(
                """
                SELECT stock_code, COUNT(*) AS row_count, MIN(bas_dd) AS first_date, MAX(bas_dd) AS last_date
                FROM stock_daily
                WHERE market=? AND bas_dd>=? AND bas_dd<=?
                GROUP BY stock_code
                ORDER BY row_count DESC, stock_code ASC
                """,
                (market, start_dd, end_dd),
            ).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            row_count = int(row["row_count"] or 0)
            coverage = 0.0 if trading_days <= 0 else row_count / trading_days * 100.0
            if coverage + 1e-9 < minimum_coverage_pct:
                continue
            candidates.append({
                "code": str(row["stock_code"]),
                "market": market,
                "row_count": row_count,
                "trading_days": trading_days,
                "coverage_pct": round(coverage, 2),
                "first_date": str(row["first_date"] or ""),
                "last_date": str(row["last_date"] or ""),
            })
            if len(candidates) >= limit:
                break

        return {
            "market": market,
            "trading_days": trading_days,
            "index_days": index_days,
            "index_coverage_pct": 0.0 if trading_days <= 0 else round(index_days / trading_days * 100.0, 2),
            "candidates": candidates,
        }

    def index_series(self, market: str, start_dd: str | None = None, end_dd: str | None = None) -> HistorySeries:
        market = self._market(market)
        clauses = ["market=?"]
        params: list[Any] = [market]
        if start_dd:
            clauses.append("bas_dd>=?")
            params.append(start_dd)
        if end_dd:
            clauses.append("bas_dd<=?")
            params.append(end_dd)
        status_clauses = ["market=?", "kind='index'"]
        status_params: list[Any] = [market]
        if start_dd:
            status_clauses.append("bas_dd>=?")
            status_params.append(start_dd)
        if end_dd:
            status_clauses.append("bas_dd<=?")
            status_params.append(end_dd)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT bas_dd,row_json FROM main_index_daily WHERE {' AND '.join(clauses)} ORDER BY bas_dd",
                params,
            ).fetchall()
            statuses = conn.execute(
                f"SELECT bas_dd FROM day_status WHERE {' AND '.join(status_clauses)}",
                status_params,
            ).fetchall()
        return HistorySeries(
            rows={str(row["bas_dd"]): self._load(str(row["row_json"])) for row in rows},
            checked_dates={str(row["bas_dd"]) for row in statuses},
        )
