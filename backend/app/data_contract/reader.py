from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.backtest.jobs import BacktestJobManager, backtest_jobs
from app.core.config import PROJECT_ROOT
from app.market_session import peek_market_session
from app.quotes.service import observe_cached_quote

from .models import (
    ChartCoverageObservation,
    KnownJobObservation,
    LedgerObservation,
    LedgerPositionObservation,
    MarketEodObservation,
    RealtimeQuoteObservation,
    StockStateObservation,
    StoredAnalysisObservation,
)


DEFAULT_MARKET_STORE_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
)
DEFAULT_HOLDINGS_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "holdings" / "holdings.db"
)


class ReadOnlyDataStateReader:
    """Observe already-stored StockScope state without preparing, calculating, or writing.

    This reader deliberately does not reuse HistoricalMarketStore or HoldingsCatalog:
    those classes own writable lifecycle/schema behavior. J-8.1 needs a stricter
    boundary where a read cannot create a directory, database, schema, cache, job,
    provider request, or analysis result.
    """

    def __init__(
        self,
        *,
        market_store_db: Path | None = None,
        holdings_db: Path | None = None,
        job_manager: BacktestJobManager | None = None,
    ) -> None:
        market_env = os.getenv("STOCKSCOPE_MARKET_STORE_DB")
        holdings_env = os.getenv("STOCKSCOPE_HOLDINGS_DB")
        self.market_store_db = Path(
            market_store_db
            if market_store_db is not None
            else market_env or DEFAULT_MARKET_STORE_DB
        )
        self.holdings_db = Path(
            holdings_db
            if holdings_db is not None
            else holdings_env or DEFAULT_HOLDINGS_DB
        )
        self.job_manager = job_manager or backtest_jobs

    @staticmethod
    def _market(market: str) -> str:
        value = (market or "").strip().upper()
        if value not in {"KOSPI", "KOSDAQ"}:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")
        return value

    @staticmethod
    def _ticker(ticker: str) -> str:
        value = (ticker or "").strip().upper()
        if len(value) != 6 or not value.isdigit():
            raise ValueError("국내주식 종목코드는 6자리 숫자여야 합니다.")
        return value

    @staticmethod
    @contextmanager
    def _read_only_connection(path: Path) -> Iterator[sqlite3.Connection]:
        if not path.is_file():
            raise FileNotFoundError(path)
        uri = path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _has_tables(conn: sqlite3.Connection, required: set[str]) -> bool:
        if not required:
            return True
        placeholders = ",".join("?" for _ in required)
        rows = conn.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name IN ({placeholders})",
            tuple(sorted(required)),
        ).fetchall()
        return {str(row["name"]) for row in rows} == required

    def _market_span(
        self,
        *,
        market: str,
        ticker: str,
    ) -> tuple[bool, str | None, str | None, str | None, int]:
        """Return confirmed market date plus ticker span bounded by that date."""
        with self._read_only_connection(self.market_store_db) as conn:
            if not self._has_tables(conn, {"day_status", "stock_daily"}):
                raise LookupError("SCHEMA_UNAVAILABLE")
            confirmed = conn.execute(
                """
                SELECT MAX(bas_dd) AS bas_dd
                FROM day_status
                WHERE market=? AND kind='stock' AND status='data'
                """,
                (market,),
            ).fetchone()
            confirmed_date = str(confirmed["bas_dd"] or "") if confirmed else ""
            if not confirmed_date:
                return True, None, None, None, 0
            span = conn.execute(
                """
                SELECT MIN(bas_dd) AS first_date,
                       MAX(bas_dd) AS latest_date,
                       COUNT(*) AS row_count
                FROM stock_daily
                WHERE market=? AND stock_code=? AND bas_dd<=?
                """,
                (market, ticker, confirmed_date),
            ).fetchone()
        row_count = int(span["row_count"] or 0) if span else 0
        first_date = str(span["first_date"]) if span and span["first_date"] else None
        latest_date = str(span["latest_date"]) if span and span["latest_date"] else None
        return True, confirmed_date, first_date, latest_date, row_count

    def read_market_eod(self, market: str, ticker: str) -> MarketEodObservation:
        clean_market = self._market(market)
        clean_ticker = self._ticker(ticker)
        if not self.market_store_db.is_file():
            return MarketEodObservation(
                available=False,
                present=False,
                source="MARKET_STORE",
                market=clean_market,
                ticker=clean_ticker,
                reason="STORE_NOT_FOUND",
            )
        try:
            _, confirmed_date, first_date, latest_date, row_count = self._market_span(
                market=clean_market,
                ticker=clean_ticker,
            )
        except LookupError:
            return MarketEodObservation(
                available=False,
                present=False,
                source="MARKET_STORE",
                market=clean_market,
                ticker=clean_ticker,
                reason="SCHEMA_UNAVAILABLE",
            )
        except sqlite3.Error as exc:
            return MarketEodObservation(
                available=False,
                present=False,
                source="MARKET_STORE",
                market=clean_market,
                ticker=clean_ticker,
                reason="READ_FAILED",
                error=str(exc),
            )
        return MarketEodObservation(
            available=True,
            present=row_count > 0,
            source="MARKET_STORE",
            market=clean_market,
            ticker=clean_ticker,
            market_confirmed_date=confirmed_date,
            stock_first_date=first_date,
            stock_latest_date=latest_date,
            stock_row_count=row_count,
            reason=None if row_count > 0 else "DATA_ABSENT",
        )

    def read_chart_coverage(self, market: str, ticker: str) -> ChartCoverageObservation:
        clean_market = self._market(market)
        clean_ticker = self._ticker(ticker)
        if not self.market_store_db.is_file():
            return ChartCoverageObservation(
                available=False,
                present=False,
                source="MARKET_STORE",
                market=clean_market,
                ticker=clean_ticker,
                reason="STORE_NOT_FOUND",
            )
        try:
            _, confirmed_date, first_date, latest_date, row_count = self._market_span(
                market=clean_market,
                ticker=clean_ticker,
            )
        except LookupError:
            return ChartCoverageObservation(
                available=False,
                present=False,
                source="MARKET_STORE",
                market=clean_market,
                ticker=clean_ticker,
                reason="SCHEMA_UNAVAILABLE",
            )
        except sqlite3.Error as exc:
            return ChartCoverageObservation(
                available=False,
                present=False,
                source="MARKET_STORE",
                market=clean_market,
                ticker=clean_ticker,
                reason="READ_FAILED",
                error=str(exc),
            )
        return ChartCoverageObservation(
            available=True,
            present=row_count > 0,
            source="MARKET_STORE",
            market=clean_market,
            ticker=clean_ticker,
            first_date=first_date,
            last_date=latest_date,
            row_count=row_count,
            market_confirmed_date=confirmed_date,
            reason=None if row_count > 0 else "DATA_ABSENT",
        )

    def _read_monitored_stock(
        self,
        conn: sqlite3.Connection,
        *,
        market: str,
        ticker: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT id,watch_enabled,archived_at
            FROM monitored_stock
            WHERE market=? AND ticker=?
            LIMIT 1
            """,
            (market, ticker),
        ).fetchone()

    def read_stored_analysis(self, market: str, ticker: str) -> StoredAnalysisObservation:
        clean_market = self._market(market)
        clean_ticker = self._ticker(ticker)
        if not self.holdings_db.is_file():
            return StoredAnalysisObservation(
                available=False,
                present=False,
                source="HOLDINGS_DB",
                market=clean_market,
                ticker=clean_ticker,
                reason="STORE_NOT_FOUND",
            )
        try:
            with self._read_only_connection(self.holdings_db) as conn:
                if not self._has_tables(
                    conn,
                    {"monitored_stock", "stock_analysis_day", "stock_analysis_revision"},
                ):
                    return StoredAnalysisObservation(
                        available=False,
                        present=False,
                        source="HOLDINGS_DB",
                        market=clean_market,
                        ticker=clean_ticker,
                        reason="SCHEMA_UNAVAILABLE",
                    )
                stock = self._read_monitored_stock(
                    conn,
                    market=clean_market,
                    ticker=clean_ticker,
                )
                if stock is None:
                    return StoredAnalysisObservation(
                        available=True,
                        present=False,
                        source="HOLDINGS_DB",
                        market=clean_market,
                        ticker=clean_ticker,
                        reason="ANALYSIS_ABSENT",
                    )

                day = conn.execute(
                    """
                    SELECT id,market_date,current_revision_id
                    FROM stock_analysis_day
                    WHERE monitored_stock_id=? AND current_revision_id IS NOT NULL
                    ORDER BY market_date DESC,id DESC
                    LIMIT 1
                    """,
                    (str(stock["id"]),),
                ).fetchone()
                if day is None:
                    return StoredAnalysisObservation(
                        available=True,
                        present=False,
                        source="HOLDINGS_DB",
                        market=clean_market,
                        ticker=clean_ticker,
                        monitored_stock_id=str(stock["id"]),
                        watch_enabled=bool(stock["watch_enabled"]),
                        archived_at=stock["archived_at"],
                        reason="ANALYSIS_ABSENT",
                    )

                revision = conn.execute(
                    """
                    SELECT id,revision_no,input_fingerprint,strategy_key,action_state,risk_state,
                           scanner_version,analysis_engine_version,policy_version,
                           source_versions_json,computed_at
                    FROM stock_analysis_revision
                    WHERE id=? AND analysis_day_id=?
                    LIMIT 1
                    """,
                    (str(day["current_revision_id"]), str(day["id"])),
                ).fetchone()
                if revision is None:
                    return StoredAnalysisObservation(
                        available=True,
                        present=False,
                        source="HOLDINGS_DB",
                        market=clean_market,
                        ticker=clean_ticker,
                        monitored_stock_id=str(stock["id"]),
                        watch_enabled=bool(stock["watch_enabled"]),
                        archived_at=stock["archived_at"],
                        market_date=str(day["market_date"]),
                        revision_id=str(day["current_revision_id"]),
                        reason="ANALYSIS_CURRENT_REVISION_MISSING",
                    )

                raw_versions = str(revision["source_versions_json"] or "")
                source_versions: dict[str, object] | None = None
                parse_error: str | None = None
                try:
                    parsed = json.loads(raw_versions) if raw_versions else {}
                    if isinstance(parsed, dict):
                        source_versions = parsed
                    else:
                        parse_error = "source_versions_json is not an object"
                except json.JSONDecodeError as exc:
                    parse_error = f"source_versions_json invalid: {exc.msg}"

                return StoredAnalysisObservation(
                    available=True,
                    present=True,
                    source="HOLDINGS_DB",
                    market=clean_market,
                    ticker=clean_ticker,
                    monitored_stock_id=str(stock["id"]),
                    watch_enabled=bool(stock["watch_enabled"]),
                    archived_at=stock["archived_at"],
                    market_date=str(day["market_date"]),
                    revision_id=str(revision["id"]),
                    revision_no=int(revision["revision_no"]),
                    computed_at=str(revision["computed_at"]),
                    strategy_key=revision["strategy_key"],
                    action_state=revision["action_state"],
                    risk_state=revision["risk_state"],
                    input_fingerprint=str(revision["input_fingerprint"]),
                    scanner_version=revision["scanner_version"],
                    analysis_engine_version=revision["analysis_engine_version"],
                    policy_version=revision["policy_version"],
                    source_versions=source_versions,
                    reason="DATA_INVALID" if parse_error else None,
                    error=parse_error,
                )
        except sqlite3.Error as exc:
            return StoredAnalysisObservation(
                available=False,
                present=False,
                source="HOLDINGS_DB",
                market=clean_market,
                ticker=clean_ticker,
                reason="READ_FAILED",
                error=str(exc),
            )

    def read_ledger(self, market: str, ticker: str) -> LedgerObservation:
        clean_market = self._market(market)
        clean_ticker = self._ticker(ticker)
        if not self.holdings_db.is_file():
            return LedgerObservation(
                available=False,
                present=False,
                source="HOLDINGS_DB",
                market=clean_market,
                ticker=clean_ticker,
                reason="STORE_NOT_FOUND",
            )
        try:
            with self._read_only_connection(self.holdings_db) as conn:
                if not self._has_tables(
                    conn,
                    {"monitored_stock", "holding_position", "position_account"},
                ):
                    return LedgerObservation(
                        available=False,
                        present=False,
                        source="HOLDINGS_DB",
                        market=clean_market,
                        ticker=clean_ticker,
                        reason="SCHEMA_UNAVAILABLE",
                    )
                stock = self._read_monitored_stock(
                    conn,
                    market=clean_market,
                    ticker=clean_ticker,
                )
                if stock is None:
                    return LedgerObservation(
                        available=True,
                        present=False,
                        source="HOLDINGS_DB",
                        market=clean_market,
                        ticker=clean_ticker,
                        reason="LEDGER_ABSENT",
                    )

                rows = conn.execute(
                    """
                    SELECT p.id AS position_id,p.position_account_id,p.current_quantity,
                           p.current_average_price,p.current_cost_basis,p.opened_reason,
                           p.opened_at,p.last_observed_at,p.last_sync_run_id,
                           a.provider,a.account_kind,a.broker_environment
                    FROM holding_position p
                    JOIN position_account a ON a.id=p.position_account_id
                    WHERE p.monitored_stock_id=? AND p.status='OPEN'
                    ORDER BY a.account_kind,a.provider,p.opened_at,p.id
                    """,
                    (str(stock["id"]),),
                ).fetchall()

                positions = tuple(
                    LedgerPositionObservation(
                        position_id=str(row["position_id"]),
                        account_id=str(row["position_account_id"]),
                        provider=str(row["provider"]),
                        account_kind=str(row["account_kind"]),
                        broker_environment=row["broker_environment"],
                        current_quantity=str(row["current_quantity"]),
                        current_average_price=(
                            str(row["current_average_price"])
                            if row["current_average_price"] is not None
                            else None
                        ),
                        current_cost_basis=(
                            str(row["current_cost_basis"])
                            if row["current_cost_basis"] is not None
                            else None
                        ),
                        opened_reason=str(row["opened_reason"]),
                        opened_at=str(row["opened_at"]),
                        last_observed_at=row["last_observed_at"],
                        last_sync_run_id=row["last_sync_run_id"],
                    )
                    for row in rows
                )
                return LedgerObservation(
                    available=True,
                    present=bool(positions),
                    source="HOLDINGS_DB",
                    market=clean_market,
                    ticker=clean_ticker,
                    monitored_stock_id=str(stock["id"]),
                    watch_enabled=bool(stock["watch_enabled"]),
                    archived_at=stock["archived_at"],
                    open_position_count=len(positions),
                    positions=positions,
                    reason=None if positions else "LEDGER_ABSENT",
                )
        except sqlite3.Error as exc:
            return LedgerObservation(
                available=False,
                present=False,
                source="HOLDINGS_DB",
                market=clean_market,
                ticker=clean_ticker,
                reason="READ_FAILED",
                error=str(exc),
            )

    def read_realtime_quote(self, market: str, ticker: str) -> RealtimeQuoteObservation:
        clean_market = self._market(market)
        clean_ticker = self._ticker(ticker)
        try:
            observed = observe_cached_quote(
                market=clean_market,
                ticker=clean_ticker,
                venue="INTEGRATED",
            )
        except Exception as exc:
            return RealtimeQuoteObservation(
                capable=False,
                present=False,
                source="KIS_REST",
                market=clean_market,
                ticker=clean_ticker,
                venue="INTEGRATED",
                session_phase="UNKNOWN",
                trading_day=None,
                market_active=None,
                reason="QUOTE_OBSERVATION_FAILED",
                error=str(exc),
            )

        session = peek_market_session("INTEGRATED")
        return RealtimeQuoteObservation(
            capable=observed.capable,
            present=observed.present,
            source=observed.source,
            market=clean_market,
            ticker=clean_ticker,
            provider=observed.provider,
            mode=observed.mode,
            venue=observed.venue,
            current_price=(
                format(observed.current_price, "f")
                if observed.current_price is not None
                else None
            ),
            provider_timestamp=observed.provider_timestamp,
            received_at=(
                observed.received_at.isoformat()
                if observed.received_at is not None
                else None
            ),
            age_ms=observed.age_ms,
            freshness_seconds=observed.freshness_seconds,
            session_phase=session.phase if session is not None else "UNKNOWN",
            trading_day=session.trading_day if session is not None else None,
            market_active=session.market_active if session is not None else None,
            reason=observed.reason,
        )

    def read_known_job(self, job_id: str | None) -> KnownJobObservation:
        normalized = (job_id or "").strip()
        if not normalized:
            return KnownJobObservation(
                available=True,
                present=False,
                source="BACKTEST_JOB_MEMORY",
                job_id=None,
                reason="JOB_ID_ABSENT",
            )
        job = self.job_manager.get(normalized)
        if job is None:
            return KnownJobObservation(
                available=True,
                present=False,
                source="BACKTEST_JOB_MEMORY",
                job_id=normalized,
                reason="JOB_NOT_FOUND",
            )
        return KnownJobObservation(
            available=True,
            present=True,
            source="BACKTEST_JOB_MEMORY",
            job_id=normalized,
            status=job.status,
            stage=job.stage,
            message=job.message,
            current=int(job.current),
            total=int(job.total),
            details=dict(job.details),
            error_message=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    def read_stock_state(
        self,
        market: str,
        ticker: str,
        *,
        known_job_id: str | None = None,
    ) -> StockStateObservation:
        clean_market = self._market(market)
        clean_ticker = self._ticker(ticker)
        return StockStateObservation(
            checked_at=datetime.now(timezone.utc).isoformat(),
            market=clean_market,
            ticker=clean_ticker,
            eod=self.read_market_eod(clean_market, clean_ticker),
            chart=self.read_chart_coverage(clean_market, clean_ticker),
            analysis=self.read_stored_analysis(clean_market, clean_ticker),
            ledger=self.read_ledger(clean_market, clean_ticker),
            realtime=self.read_realtime_quote(clean_market, clean_ticker),
            active_job=self.read_known_job(known_job_id),
        )
