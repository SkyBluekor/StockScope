from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import PROJECT_ROOT

from .domain import (
    ACCOUNT_KINDS,
    ACCOUNT_STATUSES,
    BROKER_ENVIRONMENTS,
    POSITION_EVENT_TYPES,
    POSITION_OPEN_REASONS,
    POSITION_STATUSES,
    SYNC_STATUSES,
    AccountSyncRun,
    HoldingPosition,
    HoldingPositionEvent,
    MonitoredStock,
    PositionAccount,
    StockAnalysisDay,
    StockAnalysisRevision,
)


DEFAULT_HOLDINGS_DB = PROJECT_ROOT / "backend" / "runtime" / "holdings" / "holdings.db"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class HoldingsCatalogError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _json_value(value: str | None) -> Any:
    if value in (None, ""):
        return None
    return json.loads(value)


def _decimal_text(value: Decimal | int | float | str | None) -> str | None:
    if value is None:
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HoldingsCatalogError(
            "HOLD_DECIMAL_INVALID",
            f"유효하지 않은 숫자입니다: {value}",
        ) from exc
    if not number.is_finite():
        raise HoldingsCatalogError("HOLD_DECIMAL_INVALID", "유한한 숫자만 저장할 수 있습니다.")
    return format(number, "f")


def _decimal_value(value: str | int | float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


class HoldingsCatalog:
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path or DEFAULT_HOLDINGS_DB)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def connection(self):
        """Transaction scope that always closes the SQLite handle."""
        conn = self.connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _ensure_opening_balance_event_type(conn: sqlite3.Connection) -> None:
        # HOLD-LEDGER.1: preserve ambiguous BUY rows; convert only the deterministic
        # G.5.2R initial-registration marker while rebuilding the SQLite CHECK.
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='holding_position_event'"
        ).fetchone()
        if row is None or "OPENING_BALANCE" in str(row["sql"] or ""):
            return

        legacy = "holding_position_event_hold_ledger1_legacy"
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (legacy,)
        ).fetchone() is not None:
            raise HoldingsCatalogError(
                "HOLD_LEDGER_MIGRATION_CONFLICT",
                "HOLD-LEDGER.1 임시 migration 테이블이 남아 있어 자동 진행하지 않습니다.",
            )

        before_count = int(conn.execute("SELECT COUNT(*) FROM holding_position_event").fetchone()[0])
        conn.execute("DROP TRIGGER IF EXISTS trg_holding_position_event_no_update")
        conn.execute("DROP TRIGGER IF EXISTS trg_holding_position_event_no_delete")
        conn.execute("DROP INDEX IF EXISTS ux_holding_event_external_key")
        conn.execute("DROP INDEX IF EXISTS idx_holding_event_position_created")
        conn.execute(f"ALTER TABLE holding_position_event RENAME TO {legacy}")

        conn.execute("""
            CREATE TABLE holding_position_event (
                id TEXT PRIMARY KEY,
                position_id TEXT NOT NULL,
                event_type TEXT NOT NULL
                    CHECK(event_type IN (
                        'OPENING_BALANCE','BUY','SELL','CORRECTION','BALANCE_OBSERVED','RECONCILED'
                    )),
                quantity_delta TEXT,
                unit_price TEXT,
                before_quantity TEXT,
                after_quantity TEXT,
                before_average_price TEXT,
                after_average_price TEXT,
                observed_at TEXT,
                effective_at TEXT,
                analysis_revision_id TEXT,
                account_sync_run_id TEXT,
                external_event_key TEXT,
                note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(position_id) REFERENCES holding_position(id) ON DELETE RESTRICT,
                FOREIGN KEY(analysis_revision_id) REFERENCES stock_analysis_revision(id) ON DELETE RESTRICT,
                FOREIGN KEY(account_sync_run_id) REFERENCES account_sync_run(id) ON DELETE RESTRICT
            )
        """)
        conn.execute(f"""
            INSERT INTO holding_position_event(
                id,position_id,event_type,quantity_delta,unit_price,
                before_quantity,after_quantity,before_average_price,after_average_price,
                observed_at,effective_at,analysis_revision_id,account_sync_run_id,
                external_event_key,note,created_at
            )
            SELECT
                e.id,e.position_id,
                CASE
                    WHEN e.event_type='BUY'
                     AND COALESCE(e.note,'')='보유종목 최초 등록'
                     AND COALESCE(e.before_quantity,'')='0'
                     AND e.analysis_revision_id IS NULL
                     AND e.id=(SELECT e2.id FROM {legacy} e2
                               WHERE e2.position_id=e.position_id
                               ORDER BY e2.created_at,e2.id LIMIT 1)
                    THEN 'OPENING_BALANCE'
                    ELSE e.event_type
                END,
                e.quantity_delta,e.unit_price,e.before_quantity,e.after_quantity,
                e.before_average_price,e.after_average_price,e.observed_at,e.effective_at,
                e.analysis_revision_id,e.account_sync_run_id,e.external_event_key,e.note,e.created_at
            FROM {legacy} e
            ORDER BY e.created_at,e.id
        """)
        after_count = int(conn.execute("SELECT COUNT(*) FROM holding_position_event").fetchone()[0])
        if before_count != after_count:
            raise HoldingsCatalogError(
                "HOLD_LEDGER_MIGRATION_COUNT_MISMATCH",
                "Position Event migration 전후 row 수가 일치하지 않습니다.",
            )

        conn.execute("""
            CREATE UNIQUE INDEX ux_holding_event_external_key
                ON holding_position_event(position_id, external_event_key)
                WHERE external_event_key IS NOT NULL
        """)
        conn.execute("""
            CREATE INDEX idx_holding_event_position_created
                ON holding_position_event(position_id, created_at, id)
        """)
        conn.execute("""
            CREATE TRIGGER trg_holding_position_event_no_update
            BEFORE UPDATE ON holding_position_event
            BEGIN
                SELECT RAISE(ABORT, 'holding_position_event is append-only');
            END
        """)
        conn.execute("""
            CREATE TRIGGER trg_holding_position_event_no_delete
            BEFORE DELETE ON holding_position_event
            BEGIN
                SELECT RAISE(ABORT, 'holding_position_event is append-only');
            END
        """)
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise HoldingsCatalogError(
                "HOLD_LEDGER_MIGRATION_FOREIGN_KEY",
                "Position Event migration 후 foreign key 검증에 실패했습니다.",
            )
        conn.execute(f"DROP TABLE {legacy}")

    def initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS position_account (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    account_kind TEXT NOT NULL
                        CHECK(account_kind IN ('BROKER','MANUAL','VIRTUAL')),
                    broker_environment TEXT
                        CHECK(broker_environment IS NULL OR broker_environment IN ('REAL','VIRTUAL')),
                    external_account_fingerprint TEXT,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK(status IN ('ACTIVE','ARCHIVED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS ux_position_account_external
                    ON position_account(provider, broker_environment, external_account_fingerprint)
                    WHERE external_account_fingerprint IS NOT NULL;

                CREATE TABLE IF NOT EXISTS monitored_stock (
                    id TEXT PRIMARY KEY,
                    market TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    name TEXT NOT NULL,
                    watch_enabled INTEGER NOT NULL DEFAULT 1
                        CHECK(watch_enabled IN (0,1)),
                    archived_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(market, ticker)
                );

                CREATE TABLE IF NOT EXISTS stock_analysis_day (
                    id TEXT PRIMARY KEY,
                    monitored_stock_id TEXT NOT NULL,
                    market_date TEXT NOT NULL,
                    current_revision_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(monitored_stock_id, market_date),
                    FOREIGN KEY(monitored_stock_id)
                        REFERENCES monitored_stock(id) ON DELETE RESTRICT,
                    FOREIGN KEY(current_revision_id)
                        REFERENCES stock_analysis_revision(id) ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS stock_analysis_revision (
                    id TEXT PRIMARY KEY,
                    analysis_day_id TEXT NOT NULL,
                    revision_no INTEGER NOT NULL CHECK(revision_no >= 1),
                    input_fingerprint TEXT NOT NULL,
                    strategy_key TEXT,
                    action_state TEXT,
                    risk_state TEXT,
                    reference_price TEXT,
                    stop_price TEXT,
                    target1_price TEXT,
                    target2_price TEXT,
                    scanner_version TEXT,
                    analysis_engine_version TEXT,
                    policy_version TEXT,
                    source_versions_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    revision_reason TEXT,
                    computed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(analysis_day_id, revision_no),
                    UNIQUE(analysis_day_id, input_fingerprint),
                    FOREIGN KEY(analysis_day_id)
                        REFERENCES stock_analysis_day(id) ON DELETE RESTRICT
                );

                CREATE TRIGGER IF NOT EXISTS trg_stock_analysis_revision_no_update
                BEFORE UPDATE ON stock_analysis_revision
                BEGIN
                    SELECT RAISE(ABORT, 'stock_analysis_revision is immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS trg_stock_analysis_revision_no_delete
                BEFORE DELETE ON stock_analysis_revision
                BEGIN
                    SELECT RAISE(ABORT, 'stock_analysis_revision is immutable');
                END;

                CREATE TABLE IF NOT EXISTS account_sync_run (
                    id TEXT PRIMARY KEY,
                    position_account_id TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK(status IN ('RUNNING','COMPLETED','FAILED')),
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    is_complete INTEGER NOT NULL DEFAULT 0
                        CHECK(is_complete IN (0,1)),
                    observed_at TEXT,
                    page_count INTEGER NOT NULL DEFAULT 0 CHECK(page_count >= 0),
                    holding_count INTEGER NOT NULL DEFAULT 0 CHECK(holding_count >= 0),
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(position_account_id)
                        REFERENCES position_account(id) ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS idx_account_sync_run_account_started
                    ON account_sync_run(position_account_id, started_at DESC);

                CREATE TABLE IF NOT EXISTS holding_position (
                    id TEXT PRIMARY KEY,
                    monitored_stock_id TEXT NOT NULL,
                    position_account_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED')),
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    current_quantity TEXT NOT NULL,
                    current_average_price TEXT,
                    current_cost_basis TEXT,
                    opened_reason TEXT NOT NULL
                        CHECK(opened_reason IN ('MANUAL','KIS_OBSERVED','VIRTUAL')),
                    last_observed_at TEXT,
                    last_sync_run_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(monitored_stock_id)
                        REFERENCES monitored_stock(id) ON DELETE RESTRICT,
                    FOREIGN KEY(position_account_id)
                        REFERENCES position_account(id) ON DELETE RESTRICT,
                    FOREIGN KEY(last_sync_run_id)
                        REFERENCES account_sync_run(id) ON DELETE RESTRICT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS ux_holding_position_open_stock_account
                    ON holding_position(monitored_stock_id, position_account_id)
                    WHERE status='OPEN';

                CREATE INDEX IF NOT EXISTS idx_holding_position_stock_status
                    ON holding_position(monitored_stock_id, status);

                CREATE TABLE IF NOT EXISTS holding_position_event (
                    id TEXT PRIMARY KEY,
                    position_id TEXT NOT NULL,
                    event_type TEXT NOT NULL
                        CHECK(event_type IN (
                            'OPENING_BALANCE','BUY','SELL','CORRECTION','BALANCE_OBSERVED','RECONCILED'
                        )),
                    quantity_delta TEXT,
                    unit_price TEXT,
                    before_quantity TEXT,
                    after_quantity TEXT,
                    before_average_price TEXT,
                    after_average_price TEXT,
                    observed_at TEXT,
                    effective_at TEXT,
                    analysis_revision_id TEXT,
                    account_sync_run_id TEXT,
                    external_event_key TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(position_id)
                        REFERENCES holding_position(id) ON DELETE RESTRICT,
                    FOREIGN KEY(analysis_revision_id)
                        REFERENCES stock_analysis_revision(id) ON DELETE RESTRICT,
                    FOREIGN KEY(account_sync_run_id)
                        REFERENCES account_sync_run(id) ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS holding_management_plan (
                    id TEXT PRIMARY KEY,
                    position_id TEXT NOT NULL,
                    plan_version INTEGER NOT NULL CHECK(plan_version >= 1),
                    status TEXT NOT NULL CHECK(status IN ('ACTIVE','SUPERSEDED','CLOSED')),
                    source_type TEXT NOT NULL CHECK(source_type IN ('ANALYSIS_REVISION')),
                    source_analysis_revision_id TEXT NOT NULL,
                    reference_price TEXT,
                    stop_price TEXT NOT NULL,
                    target1_price TEXT,
                    target2_price TEXT,
                    confirmation_policy TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    change_reason TEXT,
                    previous_plan_id TEXT,
                    superseded_at TEXT,
                    closed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(position_id, plan_version),
                    FOREIGN KEY(position_id) REFERENCES holding_position(id) ON DELETE RESTRICT,
                    FOREIGN KEY(source_analysis_revision_id) REFERENCES stock_analysis_revision(id) ON DELETE RESTRICT,
                    FOREIGN KEY(previous_plan_id) REFERENCES holding_management_plan(id) ON DELETE RESTRICT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS ux_holding_management_plan_active
                    ON holding_management_plan(position_id)
                    WHERE status='ACTIVE';

                CREATE INDEX IF NOT EXISTS idx_holding_management_plan_position_version
                    ON holding_management_plan(position_id, plan_version DESC);

                CREATE TRIGGER IF NOT EXISTS trg_holding_position_close_management_plan
                AFTER UPDATE OF status ON holding_position
                WHEN OLD.status='OPEN' AND NEW.status='CLOSED'
                BEGIN
                    UPDATE holding_management_plan
                    SET status='CLOSED',
                        closed_at=COALESCE(NEW.closed_at,NEW.updated_at),
                        updated_at=NEW.updated_at
                    WHERE position_id=NEW.id AND status='ACTIVE';
                END;

                CREATE UNIQUE INDEX IF NOT EXISTS ux_holding_event_external_key
                    ON holding_position_event(position_id, external_event_key)
                    WHERE external_event_key IS NOT NULL;

                CREATE INDEX IF NOT EXISTS idx_holding_event_position_created
                    ON holding_position_event(position_id, created_at, id);

                CREATE TRIGGER IF NOT EXISTS trg_holding_position_event_no_update
                BEFORE UPDATE ON holding_position_event
                BEGIN
                    SELECT RAISE(ABORT, 'holding_position_event is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS trg_holding_position_event_no_delete
                BEFORE DELETE ON holding_position_event
                BEGIN
                    SELECT RAISE(ABORT, 'holding_position_event is append-only');
                END;
                """
            )
            self._ensure_opening_balance_event_type(conn)

    @staticmethod
    def _account_from_row(row: sqlite3.Row) -> PositionAccount:
        return PositionAccount(
            id=row["id"],
            provider=row["provider"],
            account_kind=row["account_kind"],
            broker_environment=row["broker_environment"],
            external_account_fingerprint=row["external_account_fingerprint"],
            display_name=row["display_name"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _stock_from_row(row: sqlite3.Row) -> MonitoredStock:
        return MonitoredStock(
            id=row["id"],
            market=row["market"],
            ticker=row["ticker"],
            name=row["name"],
            watch_enabled=bool(row["watch_enabled"]),
            archived_at=row["archived_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _sync_from_row(row: sqlite3.Row) -> AccountSyncRun:
        return AccountSyncRun(
            id=row["id"],
            position_account_id=row["position_account_id"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            is_complete=bool(row["is_complete"]),
            observed_at=row["observed_at"],
            page_count=int(row["page_count"] or 0),
            holding_count=int(row["holding_count"] or 0),
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _position_from_row(row: sqlite3.Row) -> HoldingPosition:
        return HoldingPosition(
            id=row["id"],
            monitored_stock_id=row["monitored_stock_id"],
            position_account_id=row["position_account_id"],
            status=row["status"],
            opened_at=row["opened_at"],
            closed_at=row["closed_at"],
            current_quantity=_decimal_value(row["current_quantity"]) or Decimal("0"),
            current_average_price=_decimal_value(row["current_average_price"]),
            current_cost_basis=_decimal_value(row["current_cost_basis"]),
            opened_reason=row["opened_reason"],
            last_observed_at=row["last_observed_at"],
            last_sync_run_id=row["last_sync_run_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> HoldingPositionEvent:
        return HoldingPositionEvent(
            id=row["id"],
            position_id=row["position_id"],
            event_type=row["event_type"],
            quantity_delta=_decimal_value(row["quantity_delta"]),
            unit_price=_decimal_value(row["unit_price"]),
            before_quantity=_decimal_value(row["before_quantity"]),
            after_quantity=_decimal_value(row["after_quantity"]),
            before_average_price=_decimal_value(row["before_average_price"]),
            after_average_price=_decimal_value(row["after_average_price"]),
            observed_at=row["observed_at"],
            effective_at=row["effective_at"],
            analysis_revision_id=row["analysis_revision_id"],
            account_sync_run_id=row["account_sync_run_id"],
            external_event_key=row["external_event_key"],
            note=row["note"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _day_from_row(row: sqlite3.Row) -> StockAnalysisDay:
        return StockAnalysisDay(
            id=row["id"],
            monitored_stock_id=row["monitored_stock_id"],
            market_date=row["market_date"],
            current_revision_id=row["current_revision_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _revision_from_row(row: sqlite3.Row) -> StockAnalysisRevision:
        return StockAnalysisRevision(
            id=row["id"],
            analysis_day_id=row["analysis_day_id"],
            revision_no=int(row["revision_no"]),
            input_fingerprint=row["input_fingerprint"],
            strategy_key=row["strategy_key"],
            action_state=row["action_state"],
            risk_state=row["risk_state"],
            reference_price=_decimal_value(row["reference_price"]),
            stop_price=_decimal_value(row["stop_price"]),
            target1_price=_decimal_value(row["target1_price"]),
            target2_price=_decimal_value(row["target2_price"]),
            scanner_version=row["scanner_version"],
            analysis_engine_version=row["analysis_engine_version"],
            policy_version=row["policy_version"],
            source_versions=_json_value(row["source_versions_json"]),
            snapshot=_json_value(row["snapshot_json"]),
            revision_reason=row["revision_reason"],
            computed_at=row["computed_at"],
            created_at=row["created_at"],
        )

    def create_position_account(
        self,
        *,
        provider: str,
        account_kind: str,
        display_name: str,
        broker_environment: str | None = None,
        external_account_fingerprint: str | None = None,
    ) -> PositionAccount:
        provider_value = provider.strip().upper()
        kind = account_kind.strip().upper()
        environment = broker_environment.strip().upper() if broker_environment else None
        name = display_name.strip()
        fingerprint = (
            external_account_fingerprint.strip().lower()
            if external_account_fingerprint
            else None
        )

        if not provider_value or not name:
            raise HoldingsCatalogError(
                "HOLD_ACCOUNT_REQUIRED",
                "provider와 display_name이 필요합니다.",
            )
        if kind not in ACCOUNT_KINDS:
            raise HoldingsCatalogError("HOLD_ACCOUNT_KIND_INVALID", f"지원하지 않는 account_kind입니다: {kind}")
        if environment is not None and environment not in BROKER_ENVIRONMENTS:
            raise HoldingsCatalogError("HOLD_BROKER_ENV_INVALID", f"지원하지 않는 broker_environment입니다: {environment}")
        if kind == "BROKER" and fingerprint is None:
            raise HoldingsCatalogError(
                "HOLD_ACCOUNT_FINGERPRINT_REQUIRED",
                "BROKER 계좌에는 외부 계좌 fingerprint가 필요합니다.",
            )
        if fingerprint is not None and not _HEX64.fullmatch(fingerprint):
            raise HoldingsCatalogError(
                "HOLD_ACCOUNT_FINGERPRINT_INVALID",
                "외부 계좌 fingerprint는 SHA-256 64자리 hex 형식이어야 합니다.",
            )

        now = _now()
        account_id = str(uuid4())
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO position_account(
                        id,provider,account_kind,broker_environment,
                        external_account_fingerprint,display_name,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        account_id,
                        provider_value,
                        kind,
                        environment,
                        fingerprint,
                        name,
                        "ACTIVE",
                        now,
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM position_account WHERE id=?",
                    (account_id,),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise HoldingsCatalogError(
                "HOLD_ACCOUNT_DUPLICATE",
                "이미 등록된 외부 계좌입니다.",
            ) from exc
        return self._account_from_row(row)

    def get_position_account(self, account_id: str) -> PositionAccount | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM position_account WHERE id=?",
                (account_id,),
            ).fetchone()
        return self._account_from_row(row) if row else None

    def create_monitored_stock(
        self,
        *,
        market: str,
        ticker: str,
        name: str,
        watch_enabled: bool = True,
    ) -> MonitoredStock:
        market_value = market.strip().upper()
        ticker_value = ticker.strip()
        name_value = name.strip()
        if not market_value or not ticker_value or not name_value:
            raise HoldingsCatalogError(
                "HOLD_STOCK_REQUIRED",
                "market, ticker, name이 필요합니다.",
            )

        now = _now()
        stock_id = str(uuid4())
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO monitored_stock(
                        id,market,ticker,name,watch_enabled,archived_at,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        stock_id,
                        market_value,
                        ticker_value,
                        name_value,
                        int(watch_enabled),
                        None,
                        now,
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM monitored_stock WHERE id=?",
                    (stock_id,),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise HoldingsCatalogError(
                "HOLD_STOCK_DUPLICATE",
                f"이미 등록된 종목입니다: {market_value}/{ticker_value}",
            ) from exc
        return self._stock_from_row(row)

    def get_monitored_stock(self, stock_id: str) -> MonitoredStock | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM monitored_stock WHERE id=?",
                (stock_id,),
            ).fetchone()
        return self._stock_from_row(row) if row else None

    def list_monitored_stocks(self, *, include_archived: bool = False) -> list[MonitoredStock]:
        with self.connection() as conn:
            if include_archived:
                rows = conn.execute(
                    "SELECT * FROM monitored_stock ORDER BY market,ticker"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM monitored_stock WHERE archived_at IS NULL ORDER BY market,ticker"
                ).fetchall()
        return [self._stock_from_row(row) for row in rows]

    def set_watch_enabled(self, stock_id: str, enabled: bool) -> MonitoredStock:
        now = _now()
        with self.connection() as conn:
            cursor = conn.execute(
                "UPDATE monitored_stock SET watch_enabled=?,updated_at=? WHERE id=?",
                (int(enabled), now, stock_id),
            )
            if cursor.rowcount != 1:
                raise HoldingsCatalogError("HOLD_STOCK_NOT_FOUND", "종목을 찾을 수 없습니다.")
            row = conn.execute(
                "SELECT * FROM monitored_stock WHERE id=?",
                (stock_id,),
            ).fetchone()
        return self._stock_from_row(row)

    def archive_monitored_stock(self, stock_id: str) -> MonitoredStock:
        now = _now()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE monitored_stock
                SET archived_at=COALESCE(archived_at,?),updated_at=?
                WHERE id=?
                """,
                (now, now, stock_id),
            )
            if cursor.rowcount != 1:
                raise HoldingsCatalogError("HOLD_STOCK_NOT_FOUND", "종목을 찾을 수 없습니다.")
            row = conn.execute(
                "SELECT * FROM monitored_stock WHERE id=?",
                (stock_id,),
            ).fetchone()
        return self._stock_from_row(row)

    def open_position(
        self,
        *,
        monitored_stock_id: str,
        position_account_id: str,
        opened_reason: str,
        opened_at: str | None = None,
        current_quantity: Decimal | int | float | str = "0",
        current_average_price: Decimal | int | float | str | None = None,
        current_cost_basis: Decimal | int | float | str | None = None,
    ) -> HoldingPosition:
        reason = opened_reason.strip().upper()
        if reason not in POSITION_OPEN_REASONS:
            raise HoldingsCatalogError(
                "HOLD_POSITION_REASON_INVALID",
                f"지원하지 않는 opened_reason입니다: {reason}",
            )
        quantity = _decimal_text(current_quantity)
        if Decimal(quantity or "0") < 0:
            raise HoldingsCatalogError(
                "HOLD_POSITION_QUANTITY_INVALID",
                "보유 수량은 음수일 수 없습니다.",
            )

        now = _now()
        position_id = str(uuid4())
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO holding_position(
                        id,monitored_stock_id,position_account_id,status,
                        opened_at,closed_at,current_quantity,current_average_price,
                        current_cost_basis,opened_reason,last_observed_at,last_sync_run_id,
                        created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        position_id,
                        monitored_stock_id,
                        position_account_id,
                        "OPEN",
                        opened_at or now,
                        None,
                        quantity,
                        _decimal_text(current_average_price),
                        _decimal_text(current_cost_basis),
                        reason,
                        None,
                        None,
                        now,
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM holding_position WHERE id=?",
                    (position_id,),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "ux_holding_position_open_stock_account" in message or "unique constraint failed" in message:
                raise HoldingsCatalogError(
                    "HOLD_OPEN_POSITION_DUPLICATE",
                    "같은 종목과 계좌에는 열린 Position을 하나만 둘 수 있습니다.",
                ) from exc
            raise HoldingsCatalogError(
                "HOLD_POSITION_FK_INVALID",
                "종목 또는 계좌 참조가 유효하지 않습니다.",
            ) from exc
        return self._position_from_row(row)

    def get_position(self, position_id: str) -> HoldingPosition | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM holding_position WHERE id=?",
                (position_id,),
            ).fetchone()
        return self._position_from_row(row) if row else None

    def list_positions(
        self,
        monitored_stock_id: str,
        *,
        status: str | None = None,
    ) -> list[HoldingPosition]:
        with self.connection() as conn:
            if status is None:
                rows = conn.execute(
                    """
                    SELECT * FROM holding_position
                    WHERE monitored_stock_id=?
                    ORDER BY opened_at,id
                    """,
                    (monitored_stock_id,),
                ).fetchall()
            else:
                status_value = status.strip().upper()
                if status_value not in POSITION_STATUSES:
                    raise HoldingsCatalogError(
                        "HOLD_POSITION_STATUS_INVALID",
                        f"지원하지 않는 Position 상태입니다: {status}",
                    )
                rows = conn.execute(
                    """
                    SELECT * FROM holding_position
                    WHERE monitored_stock_id=? AND status=?
                    ORDER BY opened_at,id
                    """,
                    (monitored_stock_id, status_value),
                ).fetchall()
        return [self._position_from_row(row) for row in rows]

    def close_position(
        self,
        position_id: str,
        *,
        closed_at: str | None = None,
    ) -> HoldingPosition:
        now = _now()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE holding_position
                SET status='CLOSED',closed_at=?,updated_at=?
                WHERE id=? AND status='OPEN'
                """,
                (closed_at or now, now, position_id),
            )
            if cursor.rowcount != 1:
                raise HoldingsCatalogError(
                    "HOLD_OPEN_POSITION_NOT_FOUND",
                    "열린 Position을 찾을 수 없습니다.",
                )
            row = conn.execute(
                "SELECT * FROM holding_position WHERE id=?",
                (position_id,),
            ).fetchone()
        return self._position_from_row(row)

    def append_position_event(
        self,
        *,
        position_id: str,
        event_type: str,
        quantity_delta: Decimal | int | float | str | None = None,
        unit_price: Decimal | int | float | str | None = None,
        before_quantity: Decimal | int | float | str | None = None,
        after_quantity: Decimal | int | float | str | None = None,
        before_average_price: Decimal | int | float | str | None = None,
        after_average_price: Decimal | int | float | str | None = None,
        observed_at: str | None = None,
        effective_at: str | None = None,
        analysis_revision_id: str | None = None,
        account_sync_run_id: str | None = None,
        external_event_key: str | None = None,
        note: str | None = None,
    ) -> HoldingPositionEvent:
        kind = event_type.strip().upper()
        if kind not in POSITION_EVENT_TYPES:
            raise HoldingsCatalogError(
                "HOLD_EVENT_TYPE_INVALID",
                f"지원하지 않는 Position Event입니다: {kind}",
            )

        now = _now()
        event_id = str(uuid4())
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO holding_position_event(
                        id,position_id,event_type,quantity_delta,unit_price,
                        before_quantity,after_quantity,before_average_price,
                        after_average_price,observed_at,effective_at,
                        analysis_revision_id,account_sync_run_id,
                        external_event_key,note,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        event_id,
                        position_id,
                        kind,
                        _decimal_text(quantity_delta),
                        _decimal_text(unit_price),
                        _decimal_text(before_quantity),
                        _decimal_text(after_quantity),
                        _decimal_text(before_average_price),
                        _decimal_text(after_average_price),
                        observed_at,
                        effective_at,
                        analysis_revision_id,
                        account_sync_run_id,
                        external_event_key.strip() if external_event_key else None,
                        note,
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM holding_position_event WHERE id=?",
                    (event_id,),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            if "unique constraint failed" in str(exc).lower():
                raise HoldingsCatalogError(
                    "HOLD_EVENT_DUPLICATE",
                    "이미 기록된 외부 Position Event입니다.",
                ) from exc
            raise HoldingsCatalogError(
                "HOLD_EVENT_REFERENCE_INVALID",
                "Position Event의 참조가 유효하지 않습니다.",
            ) from exc
        return self._event_from_row(row)

    def list_position_events(self, position_id: str) -> list[HoldingPositionEvent]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM holding_position_event
                WHERE position_id=?
                ORDER BY created_at,id
                """,
                (position_id,),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def start_sync_run(
        self,
        *,
        position_account_id: str,
        observed_at: str | None = None,
    ) -> AccountSyncRun:
        now = _now()
        sync_id = str(uuid4())
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO account_sync_run(
                        id,position_account_id,status,started_at,completed_at,
                        is_complete,observed_at,page_count,holding_count,
                        error_code,error_message,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        sync_id,
                        position_account_id,
                        "RUNNING",
                        now,
                        None,
                        0,
                        observed_at,
                        0,
                        0,
                        None,
                        None,
                        now,
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM account_sync_run WHERE id=?",
                    (sync_id,),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise HoldingsCatalogError(
                "HOLD_SYNC_ACCOUNT_INVALID",
                "동기화 대상 계좌를 찾을 수 없습니다.",
            ) from exc
        return self._sync_from_row(row)

    def complete_sync_run(
        self,
        sync_run_id: str,
        *,
        observed_at: str,
        page_count: int,
        holding_count: int,
    ) -> AccountSyncRun:
        if page_count < 0 or holding_count < 0:
            raise HoldingsCatalogError(
                "HOLD_SYNC_COUNT_INVALID",
                "동기화 count는 음수일 수 없습니다.",
            )
        now = _now()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE account_sync_run
                SET status='COMPLETED',completed_at=?,is_complete=1,
                    observed_at=?,page_count=?,holding_count=?,
                    error_code=NULL,error_message=NULL,updated_at=?
                WHERE id=? AND status='RUNNING'
                """,
                (
                    now,
                    observed_at,
                    int(page_count),
                    int(holding_count),
                    now,
                    sync_run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise HoldingsCatalogError(
                    "HOLD_SYNC_RUNNING_NOT_FOUND",
                    "실행 중인 동기화 기록을 찾을 수 없습니다.",
                )
            row = conn.execute(
                "SELECT * FROM account_sync_run WHERE id=?",
                (sync_run_id,),
            ).fetchone()
        return self._sync_from_row(row)

    def fail_sync_run(
        self,
        sync_run_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> AccountSyncRun:
        now = _now()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE account_sync_run
                SET status='FAILED',completed_at=?,is_complete=0,
                    error_code=?,error_message=?,updated_at=?
                WHERE id=? AND status='RUNNING'
                """,
                (now, error_code, error_message, now, sync_run_id),
            )
            if cursor.rowcount != 1:
                raise HoldingsCatalogError(
                    "HOLD_SYNC_RUNNING_NOT_FOUND",
                    "실행 중인 동기화 기록을 찾을 수 없습니다.",
                )
            row = conn.execute(
                "SELECT * FROM account_sync_run WHERE id=?",
                (sync_run_id,),
            ).fetchone()
        return self._sync_from_row(row)

    def get_or_create_analysis_day(
        self,
        *,
        monitored_stock_id: str,
        market_date: str,
    ) -> StockAnalysisDay:
        date_value = market_date.strip()
        if not date_value:
            raise HoldingsCatalogError(
                "HOLD_ANALYSIS_DATE_REQUIRED",
                "market_date가 필요합니다.",
            )
        with self.connection() as conn:
            existing = conn.execute(
                """
                SELECT * FROM stock_analysis_day
                WHERE monitored_stock_id=? AND market_date=?
                """,
                (monitored_stock_id, date_value),
            ).fetchone()
            if existing is not None:
                return self._day_from_row(existing)

            now = _now()
            day_id = str(uuid4())
            try:
                conn.execute(
                    """
                    INSERT INTO stock_analysis_day(
                        id,monitored_stock_id,market_date,current_revision_id,
                        created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        day_id,
                        monitored_stock_id,
                        date_value,
                        None,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise HoldingsCatalogError(
                    "HOLD_ANALYSIS_STOCK_INVALID",
                    "분석 대상 종목을 찾을 수 없습니다.",
                ) from exc
            row = conn.execute(
                "SELECT * FROM stock_analysis_day WHERE id=?",
                (day_id,),
            ).fetchone()
        return self._day_from_row(row)

    def append_analysis_revision(
        self,
        *,
        analysis_day_id: str,
        input_fingerprint: str,
        strategy_key: str | None,
        action_state: str | None,
        risk_state: str | None,
        reference_price: Decimal | int | float | str | None,
        stop_price: Decimal | int | float | str | None,
        target1_price: Decimal | int | float | str | None,
        target2_price: Decimal | int | float | str | None,
        scanner_version: str | None,
        analysis_engine_version: str | None,
        policy_version: str | None,
        source_versions: Any,
        snapshot: Any,
        revision_reason: str | None = None,
        computed_at: str | None = None,
    ) -> StockAnalysisRevision:
        fingerprint = input_fingerprint.strip()
        if not fingerprint:
            raise HoldingsCatalogError(
                "HOLD_ANALYSIS_FINGERPRINT_REQUIRED",
                "input_fingerprint가 필요합니다.",
            )

        with self.connection() as conn:
            existing = conn.execute(
                """
                SELECT * FROM stock_analysis_revision
                WHERE analysis_day_id=? AND input_fingerprint=?
                """,
                (analysis_day_id, fingerprint),
            ).fetchone()
            if existing is not None:
                return self._revision_from_row(existing)

            day = conn.execute(
                "SELECT id FROM stock_analysis_day WHERE id=?",
                (analysis_day_id,),
            ).fetchone()
            if day is None:
                raise HoldingsCatalogError(
                    "HOLD_ANALYSIS_DAY_NOT_FOUND",
                    "분석일을 찾을 수 없습니다.",
                )

            next_revision = int(
                conn.execute(
                    """
                    SELECT COALESCE(MAX(revision_no),0)+1 AS next_revision
                    FROM stock_analysis_revision
                    WHERE analysis_day_id=?
                    """,
                    (analysis_day_id,),
                ).fetchone()["next_revision"]
            )
            now = _now()
            revision_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO stock_analysis_revision(
                    id,analysis_day_id,revision_no,input_fingerprint,
                    strategy_key,action_state,risk_state,
                    reference_price,stop_price,target1_price,target2_price,
                    scanner_version,analysis_engine_version,policy_version,
                    source_versions_json,snapshot_json,revision_reason,
                    computed_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    revision_id,
                    analysis_day_id,
                    next_revision,
                    fingerprint,
                    strategy_key,
                    action_state,
                    risk_state,
                    _decimal_text(reference_price),
                    _decimal_text(stop_price),
                    _decimal_text(target1_price),
                    _decimal_text(target2_price),
                    scanner_version,
                    analysis_engine_version,
                    policy_version,
                    _json_text(source_versions),
                    _json_text(snapshot),
                    revision_reason,
                    computed_at or now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM stock_analysis_revision WHERE id=?",
                (revision_id,),
            ).fetchone()
        return self._revision_from_row(row)

    def promote_current_revision(
        self,
        *,
        analysis_day_id: str,
        revision_id: str,
    ) -> StockAnalysisDay:
        now = _now()
        with self.connection() as conn:
            revision = conn.execute(
                """
                SELECT id FROM stock_analysis_revision
                WHERE id=? AND analysis_day_id=?
                """,
                (revision_id, analysis_day_id),
            ).fetchone()
            if revision is None:
                raise HoldingsCatalogError(
                    "HOLD_ANALYSIS_REVISION_MISMATCH",
                    "해당 분석일의 revision이 아닙니다.",
                )
            cursor = conn.execute(
                """
                UPDATE stock_analysis_day
                SET current_revision_id=?,updated_at=?
                WHERE id=?
                """,
                (revision_id, now, analysis_day_id),
            )
            if cursor.rowcount != 1:
                raise HoldingsCatalogError(
                    "HOLD_ANALYSIS_DAY_NOT_FOUND",
                    "분석일을 찾을 수 없습니다.",
                )
            row = conn.execute(
                "SELECT * FROM stock_analysis_day WHERE id=?",
                (analysis_day_id,),
            ).fetchone()
        return self._day_from_row(row)

    def get_current_revision(
        self,
        analysis_day_id: str,
    ) -> StockAnalysisRevision | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT r.*
                FROM stock_analysis_day d
                JOIN stock_analysis_revision r ON r.id=d.current_revision_id
                WHERE d.id=?
                """,
                (analysis_day_id,),
            ).fetchone()
        return self._revision_from_row(row) if row else None
