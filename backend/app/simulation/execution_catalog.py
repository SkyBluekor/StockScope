from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .validation_catalog import (
    HistoricalValidationCandidate,
    HistoricalValidationCatalog,
)


EXECUTION_POLICY_VERSION = "EXECUTION_V1"
OUTCOME_STATUSES = frozenset(
    {
        "NOT_EXECUTED",
        "NO_ENTRY_DATA",
        "RISK_PLAN_BLOCKED",
        "OPEN",
        "CLOSED",
        "CENSORED",
    }
)


class ExecutionCatalogError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


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


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_text(value).encode("utf-8")).hexdigest()


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


@dataclass(frozen=True, slots=True)
class HistoricalExecutionRun:
    id: str
    validation_id: str
    execution_policy_version: str
    production_exit_policy_token: str
    market_data_cutoff_date: str
    scanner_version: str
    source_candidate_count: int
    status: str
    processed_candidate_count: int
    not_executed_count: int
    no_entry_data_count: int
    risk_plan_blocked_count: int
    open_count: int
    closed_count: int
    censored_count: int
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    cancel_requested: bool = False


@dataclass(frozen=True, slots=True)
class HistoricalExecutionOutcome:
    execution_run_id: str
    validation_id: str
    signal_date: str
    market: str
    ticker: str
    name: str
    rank: int | None
    result_bucket: str
    strategy: str | None
    candidate_state: str | None
    action: str | None
    candidate_snapshot_hash: str
    day_result_hash: str
    scanner_version: str
    execution_policy_version: str
    production_exit_policy_token: str
    outcome_status: str
    outcome_reason: str | None
    entry_reference_date: str | None
    entry_reference_price: float | None
    entry_date: str | None
    entry_price: float | None
    stop_price: float | None
    target1_price: float | None
    target2_price: float | None
    exit_date: str | None
    exit_price: float | None
    exit_reason: str | None
    holding_days: int | None
    gross_return_pct: float | None
    net_return_pct: float | None
    fee_pct: float
    tax_pct: float
    slippage_pct: float
    mark_date: str | None
    mark_price: float | None
    mark_return_pct: float | None
    details: Any
    outcome_hash: str
    created_at: str


class HistoricalExecutionCatalog:
    """VAL.2 persistence isolated from immutable VAL.1 replay results."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.validation_catalog = HistoricalValidationCatalog(self.db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _ensure_columns(
        conn: sqlite3.Connection,
        table: str,
        definitions: dict[str, str],
    ) -> None:
        existing = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, ddl in definitions.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def initialize(self) -> None:
        # Ensure the source VAL.1 tables exist first. This is migration-safe and
        # does not rewrite completed VAL.1 rows.
        self.validation_catalog.initialize()
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS historical_execution_run (
                    id TEXT PRIMARY KEY,
                    validation_id TEXT NOT NULL,
                    execution_policy_version TEXT NOT NULL,
                    production_exit_policy_token TEXT NOT NULL,
                    market_data_cutoff_date TEXT NOT NULL,
                    scanner_version TEXT NOT NULL,
                    source_candidate_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'DRAFT',
                    processed_candidate_count INTEGER NOT NULL DEFAULT 0,
                    not_executed_count INTEGER NOT NULL DEFAULT 0,
                    no_entry_data_count INTEGER NOT NULL DEFAULT 0,
                    risk_plan_blocked_count INTEGER NOT NULL DEFAULT 0,
                    open_count INTEGER NOT NULL DEFAULT 0,
                    closed_count INTEGER NOT NULL DEFAULT 0,
                    censored_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(
                        validation_id,
                        execution_policy_version,
                        production_exit_policy_token,
                        market_data_cutoff_date
                    ),
                    FOREIGN KEY(validation_id)
                        REFERENCES historical_validation_run(id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS historical_execution_outcome (
                    execution_run_id TEXT NOT NULL,
                    validation_id TEXT NOT NULL,
                    signal_date TEXT NOT NULL,
                    market TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    name TEXT NOT NULL,
                    rank INTEGER,
                    result_bucket TEXT NOT NULL,
                    strategy TEXT,
                    candidate_state TEXT,
                    action TEXT,
                    candidate_snapshot_hash TEXT NOT NULL,
                    day_result_hash TEXT NOT NULL,
                    scanner_version TEXT NOT NULL,
                    execution_policy_version TEXT NOT NULL,
                    production_exit_policy_token TEXT NOT NULL,
                    outcome_status TEXT NOT NULL,
                    outcome_reason TEXT,
                    entry_reference_date TEXT,
                    entry_reference_price REAL,
                    entry_date TEXT,
                    entry_price REAL,
                    stop_price REAL,
                    target1_price REAL,
                    target2_price REAL,
                    exit_date TEXT,
                    exit_price REAL,
                    exit_reason TEXT,
                    holding_days INTEGER,
                    gross_return_pct REAL,
                    net_return_pct REAL,
                    fee_pct REAL NOT NULL DEFAULT 0,
                    tax_pct REAL NOT NULL DEFAULT 0,
                    slippage_pct REAL NOT NULL DEFAULT 0,
                    mark_date TEXT,
                    mark_price REAL,
                    mark_return_pct REAL,
                    details_json TEXT,
                    outcome_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(execution_run_id, signal_date, market, ticker),
                    FOREIGN KEY(execution_run_id)
                        REFERENCES historical_execution_run(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY(validation_id, signal_date, market, ticker)
                        REFERENCES historical_validation_candidate(
                            validation_id, trading_date, market, ticker
                        )
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_historical_execution_run_validation
                    ON historical_execution_run(validation_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_historical_execution_outcome_status
                    ON historical_execution_outcome(
                        execution_run_id, outcome_status, signal_date
                    );

                CREATE INDEX IF NOT EXISTS idx_historical_execution_outcome_strategy
                    ON historical_execution_outcome(
                        execution_run_id, strategy, signal_date
                    );
                """
            )
            self._ensure_columns(
                conn,
                "historical_execution_run",
                {
                    "started_at": "TEXT",
                    "completed_at": "TEXT",
                    "error_code": "TEXT",
                    "error_message": "TEXT",
                    "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
                },
            )

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> HistoricalExecutionRun:
        return HistoricalExecutionRun(
            id=row["id"],
            validation_id=row["validation_id"],
            execution_policy_version=row["execution_policy_version"],
            production_exit_policy_token=row["production_exit_policy_token"],
            market_data_cutoff_date=row["market_data_cutoff_date"],
            scanner_version=row["scanner_version"],
            source_candidate_count=int(row["source_candidate_count"] or 0),
            status=row["status"],
            processed_candidate_count=int(row["processed_candidate_count"] or 0),
            not_executed_count=int(row["not_executed_count"] or 0),
            no_entry_data_count=int(row["no_entry_data_count"] or 0),
            risk_plan_blocked_count=int(row["risk_plan_blocked_count"] or 0),
            open_count=int(row["open_count"] or 0),
            closed_count=int(row["closed_count"] or 0),
            censored_count=int(row["censored_count"] or 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            cancel_requested=bool(row["cancel_requested"]),
        )

    @staticmethod
    def _outcome_from_row(row: sqlite3.Row) -> HistoricalExecutionOutcome:
        return HistoricalExecutionOutcome(
            execution_run_id=row["execution_run_id"],
            validation_id=row["validation_id"],
            signal_date=row["signal_date"],
            market=row["market"],
            ticker=row["ticker"],
            name=row["name"],
            rank=_optional_int(row["rank"]),
            result_bucket=row["result_bucket"],
            strategy=row["strategy"],
            candidate_state=row["candidate_state"],
            action=row["action"],
            candidate_snapshot_hash=row["candidate_snapshot_hash"],
            day_result_hash=row["day_result_hash"],
            scanner_version=row["scanner_version"],
            execution_policy_version=row["execution_policy_version"],
            production_exit_policy_token=row["production_exit_policy_token"],
            outcome_status=row["outcome_status"],
            outcome_reason=row["outcome_reason"],
            entry_reference_date=row["entry_reference_date"],
            entry_reference_price=_optional_float(row["entry_reference_price"]),
            entry_date=row["entry_date"],
            entry_price=_optional_float(row["entry_price"]),
            stop_price=_optional_float(row["stop_price"]),
            target1_price=_optional_float(row["target1_price"]),
            target2_price=_optional_float(row["target2_price"]),
            exit_date=row["exit_date"],
            exit_price=_optional_float(row["exit_price"]),
            exit_reason=row["exit_reason"],
            holding_days=_optional_int(row["holding_days"]),
            gross_return_pct=_optional_float(row["gross_return_pct"]),
            net_return_pct=_optional_float(row["net_return_pct"]),
            fee_pct=float(row["fee_pct"] or 0),
            tax_pct=float(row["tax_pct"] or 0),
            slippage_pct=float(row["slippage_pct"] or 0),
            mark_date=row["mark_date"],
            mark_price=_optional_float(row["mark_price"]),
            mark_return_pct=_optional_float(row["mark_return_pct"]),
            details=_json_value(row["details_json"]),
            outcome_hash=row["outcome_hash"],
            created_at=row["created_at"],
        )

    def create_run(
        self,
        *,
        validation_id: str,
        market_data_cutoff_date: str,
        production_exit_policy_token: str,
        execution_policy_version: str = EXECUTION_POLICY_VERSION,
    ) -> HistoricalExecutionRun:
        validation = self.validation_catalog.get(validation_id)
        if validation is None:
            raise ExecutionCatalogError(
                "VAL2_SOURCE_NOT_FOUND",
                "VAL.2 source Historical Validation을 찾을 수 없습니다.",
            )
        if validation.status != "COMPLETED":
            raise ExecutionCatalogError(
                "VAL2_SOURCE_NOT_COMPLETED",
                f"VAL.2는 완료된 VAL.1만 입력으로 사용할 수 있습니다: {validation.status}",
            )

        try:
            date.fromisoformat(market_data_cutoff_date)
        except ValueError as exc:
            raise ExecutionCatalogError(
                "VAL2_CUTOFF_INVALID",
                f"market_data_cutoff_date가 ISO 날짜가 아닙니다: {market_data_cutoff_date}",
            ) from exc

        policy_version = execution_policy_version.strip()
        exit_token = production_exit_policy_token.strip()
        if not policy_version or not exit_token:
            raise ExecutionCatalogError(
                "VAL2_POLICY_REQUIRED",
                "Execution policy와 Production exit policy token이 필요합니다.",
            )

        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM historical_execution_run
                WHERE validation_id=?
                  AND execution_policy_version=?
                  AND production_exit_policy_token=?
                  AND market_data_cutoff_date=?
                """,
                (
                    validation_id,
                    policy_version,
                    exit_token,
                    market_data_cutoff_date,
                ),
            ).fetchone()
            if existing is not None:
                return self._run_from_row(existing)

            source_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM historical_validation_candidate
                    WHERE validation_id=?
                    """,
                    (validation_id,),
                ).fetchone()[0]
            )
            now = datetime.now(timezone.utc).isoformat()
            run_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO historical_execution_run(
                    id,validation_id,execution_policy_version,
                    production_exit_policy_token,market_data_cutoff_date,
                    scanner_version,source_candidate_count,status,
                    created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,'DRAFT',?,?)
                """,
                (
                    run_id,
                    validation_id,
                    policy_version,
                    exit_token,
                    market_data_cutoff_date,
                    validation.scanner_version,
                    source_count,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._run_from_row(row)

    def get_run(self, execution_run_id: str) -> HistoricalExecutionRun | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
        return self._run_from_row(row) if row else None

    def list_runs(self, validation_id: str | None = None) -> list[HistoricalExecutionRun]:
        with self.connect() as conn:
            if validation_id is None:
                rows = conn.execute(
                    "SELECT * FROM historical_execution_run ORDER BY created_at DESC,id DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM historical_execution_run
                    WHERE validation_id=?
                    ORDER BY created_at DESC,id DESC
                    """,
                    (validation_id,),
                ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def begin_run(self, execution_run_id: str) -> HistoricalExecutionRun:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
            if row is None:
                raise ExecutionCatalogError(
                    "VAL2_RUN_NOT_FOUND",
                    f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
                )
            status = str(row["status"])
            if status == "RUNNING":
                raise ExecutionCatalogError(
                    "VAL2_RUN_ALREADY_RUNNING",
                    "이미 실행 중인 Execution Validation입니다.",
                )
            if status == "COMPLETED":
                raise ExecutionCatalogError(
                    "VAL2_RUN_ALREADY_COMPLETED",
                    "이미 완료된 Execution Validation입니다.",
                )
            if status not in {"DRAFT", "FAILED", "CANCELLED"}:
                raise ExecutionCatalogError(
                    "VAL2_RUN_INVALID_STATUS",
                    f"Execution Validation을 실행할 수 없는 상태입니다: {status}",
                )
            conn.execute(
                """
                UPDATE historical_execution_run
                SET status='RUNNING',
                    started_at=COALESCE(started_at, ?),
                    completed_at=NULL,
                    error_code=NULL,
                    error_message=NULL,
                    cancel_requested=0,
                    updated_at=?
                WHERE id=?
                """,
                (now, now, execution_run_id),
            )
            updated = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
        return self._run_from_row(updated)

    def request_cancel(self, execution_run_id: str) -> HistoricalExecutionRun:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
            if row is None:
                raise ExecutionCatalogError(
                    "VAL2_RUN_NOT_FOUND",
                    f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
                )
            if row["status"] == "RUNNING":
                conn.execute(
                    """
                    UPDATE historical_execution_run
                    SET cancel_requested=1,updated_at=?
                    WHERE id=?
                    """,
                    (now, execution_run_id),
                )
            updated = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
        return self._run_from_row(updated)

    def cancel_requested(self, execution_run_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
        if row is None:
            raise ExecutionCatalogError(
                "VAL2_RUN_NOT_FOUND",
                f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
            )
        return bool(row["cancel_requested"])

    def mark_failed(
        self,
        execution_run_id: str,
        error_code: str,
        error_message: str,
    ) -> HistoricalExecutionRun:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE historical_execution_run
                SET status='FAILED',
                    error_code=?,
                    error_message=?,
                    cancel_requested=0,
                    updated_at=?
                WHERE id=?
                """,
                (error_code, error_message, now, execution_run_id),
            )
            if cursor.rowcount != 1:
                raise ExecutionCatalogError(
                    "VAL2_RUN_NOT_FOUND",
                    f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
                )
            row = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
        return self._run_from_row(row)

    def mark_cancelled(self, execution_run_id: str) -> HistoricalExecutionRun:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE historical_execution_run
                SET status='CANCELLED',
                    error_code=NULL,
                    error_message=NULL,
                    cancel_requested=0,
                    updated_at=?
                WHERE id=?
                """,
                (now, execution_run_id),
            )
            if cursor.rowcount != 1:
                raise ExecutionCatalogError(
                    "VAL2_RUN_NOT_FOUND",
                    f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
                )
            row = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
        return self._run_from_row(row)

    def mark_completed(self, execution_run_id: str) -> HistoricalExecutionRun:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
            if row is None:
                raise ExecutionCatalogError(
                    "VAL2_RUN_NOT_FOUND",
                    f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
                )
            if int(row["processed_candidate_count"] or 0) != int(
                row["source_candidate_count"] or 0
            ):
                raise ExecutionCatalogError(
                    "VAL2_RUN_INCOMPLETE",
                    "모든 VAL.1 candidate가 처리되기 전에는 완료할 수 없습니다.",
                )
            conn.execute(
                """
                UPDATE historical_execution_run
                SET status='COMPLETED',
                    completed_at=?,
                    error_code=NULL,
                    error_message=NULL,
                    cancel_requested=0,
                    updated_at=?
                WHERE id=?
                """,
                (now, now, execution_run_id),
            )
            updated = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
        return self._run_from_row(updated)

    def get_outcome(
        self,
        execution_run_id: str,
        signal_date: str,
        market: str,
        ticker: str,
    ) -> HistoricalExecutionOutcome | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM historical_execution_outcome
                WHERE execution_run_id=? AND signal_date=? AND market=? AND ticker=?
                """,
                (execution_run_id, signal_date, market.strip().upper(), ticker.strip()),
            ).fetchone()
        return self._outcome_from_row(row) if row else None

    def list_outcomes(
        self,
        execution_run_id: str,
        *,
        outcome_status: str | None = None,
    ) -> list[HistoricalExecutionOutcome]:
        with self.connect() as conn:
            if outcome_status is None:
                rows = conn.execute(
                    """
                    SELECT * FROM historical_execution_outcome
                    WHERE execution_run_id=?
                    ORDER BY signal_date,
                             CASE result_bucket WHEN 'TOP' THEN 0 ELSE 1 END,
                             rank,ticker
                    """,
                    (execution_run_id,),
                ).fetchall()
            else:
                status = outcome_status.strip().upper()
                rows = conn.execute(
                    """
                    SELECT * FROM historical_execution_outcome
                    WHERE execution_run_id=? AND outcome_status=?
                    ORDER BY signal_date,
                             CASE result_bucket WHEN 'TOP' THEN 0 ELSE 1 END,
                             rank,ticker
                    """,
                    (execution_run_id, status),
                ).fetchall()
        return [self._outcome_from_row(row) for row in rows]

    def pending_candidates(
        self,
        execution_run_id: str,
    ) -> list[HistoricalValidationCandidate]:
        run = self.get_run(execution_run_id)
        if run is None:
            raise ExecutionCatalogError(
                "VAL2_RUN_NOT_FOUND",
                f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
            )

        completed_keys = {
            (row.signal_date, row.market, row.ticker)
            for row in self.list_outcomes(execution_run_id)
        }
        return [
            candidate
            for candidate in self.validation_catalog.list_candidates(run.validation_id)
            if (candidate.trading_date, candidate.market, candidate.ticker)
            not in completed_keys
        ]

    @staticmethod
    def _refresh_progress_uow(
        conn: sqlite3.Connection,
        execution_run_id: str,
        now: str,
    ) -> None:
        conn.execute(
            """
            UPDATE historical_execution_run
            SET processed_candidate_count=(
                    SELECT COUNT(*)
                    FROM historical_execution_outcome
                    WHERE execution_run_id=?
                ),
                not_executed_count=(
                    SELECT COUNT(*)
                    FROM historical_execution_outcome
                    WHERE execution_run_id=? AND outcome_status='NOT_EXECUTED'
                ),
                no_entry_data_count=(
                    SELECT COUNT(*)
                    FROM historical_execution_outcome
                    WHERE execution_run_id=? AND outcome_status='NO_ENTRY_DATA'
                ),
                risk_plan_blocked_count=(
                    SELECT COUNT(*)
                    FROM historical_execution_outcome
                    WHERE execution_run_id=? AND outcome_status='RISK_PLAN_BLOCKED'
                ),
                open_count=(
                    SELECT COUNT(*)
                    FROM historical_execution_outcome
                    WHERE execution_run_id=? AND outcome_status='OPEN'
                ),
                closed_count=(
                    SELECT COUNT(*)
                    FROM historical_execution_outcome
                    WHERE execution_run_id=? AND outcome_status='CLOSED'
                ),
                censored_count=(
                    SELECT COUNT(*)
                    FROM historical_execution_outcome
                    WHERE execution_run_id=? AND outcome_status='CENSORED'
                ),
                updated_at=?
            WHERE id=?
            """,
            (
                execution_run_id,
                execution_run_id,
                execution_run_id,
                execution_run_id,
                execution_run_id,
                execution_run_id,
                execution_run_id,
                now,
                execution_run_id,
            ),
        )

    def save_outcome(
        self,
        *,
        execution_run_id: str,
        signal_date: str,
        market: str,
        ticker: str,
        outcome_status: str,
        outcome_reason: str | None = None,
        entry_reference_date: str | None = None,
        entry_reference_price: float | None = None,
        entry_date: str | None = None,
        entry_price: float | None = None,
        stop_price: float | None = None,
        target1_price: float | None = None,
        target2_price: float | None = None,
        exit_date: str | None = None,
        exit_price: float | None = None,
        exit_reason: str | None = None,
        holding_days: int | None = None,
        gross_return_pct: float | None = None,
        net_return_pct: float | None = None,
        fee_pct: float = 0.0,
        tax_pct: float = 0.0,
        slippage_pct: float = 0.0,
        mark_date: str | None = None,
        mark_price: float | None = None,
        mark_return_pct: float | None = None,
        details: Any = None,
    ) -> HistoricalExecutionOutcome:
        status = outcome_status.strip().upper()
        if status not in OUTCOME_STATUSES:
            raise ExecutionCatalogError(
                "VAL2_OUTCOME_STATUS_INVALID",
                f"지원하지 않는 execution outcome 상태입니다: {outcome_status}",
            )

        clean_market = market.strip().upper()
        clean_ticker = ticker.strip()
        if not clean_market or not clean_ticker:
            raise ExecutionCatalogError(
                "VAL2_SOURCE_KEY_REQUIRED",
                "market과 ticker가 필요합니다.",
            )

        with self.connect() as conn:
            run_row = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (execution_run_id,),
            ).fetchone()
            if run_row is None:
                raise ExecutionCatalogError(
                    "VAL2_RUN_NOT_FOUND",
                    f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
                )
            run = self._run_from_row(run_row)

            existing = conn.execute(
                """
                SELECT * FROM historical_execution_outcome
                WHERE execution_run_id=? AND signal_date=? AND market=? AND ticker=?
                """,
                (execution_run_id, signal_date, clean_market, clean_ticker),
            ).fetchone()
            if existing is not None:
                # One execution run is a frozen view at one market-data cutoff.
                # Re-saving the same source candidate must never rewrite its result.
                return self._outcome_from_row(existing)

            source = conn.execute(
                """
                SELECT c.*, d.result_hash AS day_result_hash
                FROM historical_validation_candidate c
                JOIN historical_validation_day d
                  ON d.validation_id=c.validation_id
                 AND d.trading_date=c.trading_date
                WHERE c.validation_id=?
                  AND c.trading_date=?
                  AND c.market=?
                  AND c.ticker=?
                  AND d.status='COMPLETED'
                """,
                (
                    run.validation_id,
                    signal_date,
                    clean_market,
                    clean_ticker,
                ),
            ).fetchone()
            if source is None:
                raise ExecutionCatalogError(
                    "VAL2_SOURCE_CANDIDATE_NOT_FOUND",
                    "VAL.1 완료 candidate를 찾을 수 없습니다.",
                )

            day_result_hash = str(source["day_result_hash"] or "")
            candidate_snapshot_hash = str(source["snapshot_hash"] or "")
            if not day_result_hash or not candidate_snapshot_hash:
                raise ExecutionCatalogError(
                    "VAL2_SOURCE_PROVENANCE_MISSING",
                    "VAL.1 source hash가 없어 Execution Validation을 고정할 수 없습니다.",
                )

            snapshot = _json_value(source["candidate_snapshot_json"]) or {}
            action = str(snapshot.get("action") or "").strip() or None

            payload = {
                "execution_run_id": execution_run_id,
                "validation_id": run.validation_id,
                "signal_date": signal_date,
                "market": clean_market,
                "ticker": clean_ticker,
                "candidate_snapshot_hash": candidate_snapshot_hash,
                "day_result_hash": day_result_hash,
                "scanner_version": run.scanner_version,
                "execution_policy_version": run.execution_policy_version,
                "production_exit_policy_token": run.production_exit_policy_token,
                "outcome_status": status,
                "outcome_reason": outcome_reason,
                "entry_reference_date": entry_reference_date,
                "entry_reference_price": entry_reference_price,
                "entry_date": entry_date,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target1_price": target1_price,
                "target2_price": target2_price,
                "exit_date": exit_date,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "holding_days": holding_days,
                "gross_return_pct": gross_return_pct,
                "net_return_pct": net_return_pct,
                "fee_pct": float(fee_pct),
                "tax_pct": float(tax_pct),
                "slippage_pct": float(slippage_pct),
                "mark_date": mark_date,
                "mark_price": mark_price,
                "mark_return_pct": mark_return_pct,
                "details": details,
            }
            outcome_hash = _digest(payload)
            now = datetime.now(timezone.utc).isoformat()

            conn.execute(
                """
                INSERT INTO historical_execution_outcome(
                    execution_run_id,validation_id,signal_date,market,ticker,name,
                    rank,result_bucket,strategy,candidate_state,action,
                    candidate_snapshot_hash,day_result_hash,scanner_version,
                    execution_policy_version,production_exit_policy_token,
                    outcome_status,outcome_reason,
                    entry_reference_date,entry_reference_price,
                    entry_date,entry_price,stop_price,target1_price,target2_price,
                    exit_date,exit_price,exit_reason,holding_days,
                    gross_return_pct,net_return_pct,
                    fee_pct,tax_pct,slippage_pct,
                    mark_date,mark_price,mark_return_pct,
                    details_json,outcome_hash,created_at
                ) VALUES(
                    ?,?,?,?,?,?,
                    ?,?,?,?,?, 
                    ?,?,?,?,
                    ?,?,
                    ?,?,
                    ?,?,?,?,?,?,
                    ?,?,?,?,
                    ?,?,
                    ?,?,?,
                    ?,?,?,
                    ?,?,?
                )
                """,
                (
                    execution_run_id,
                    run.validation_id,
                    signal_date,
                    clean_market,
                    clean_ticker,
                    source["name"],
                    source["rank"],
                    source["result_bucket"],
                    source["strategy"],
                    source["decision_status"],
                    action,
                    candidate_snapshot_hash,
                    day_result_hash,
                    run.scanner_version,
                    run.execution_policy_version,
                    run.production_exit_policy_token,
                    status,
                    outcome_reason,
                    entry_reference_date,
                    entry_reference_price,
                    entry_date,
                    entry_price,
                    stop_price,
                    target1_price,
                    target2_price,
                    exit_date,
                    exit_price,
                    exit_reason,
                    holding_days,
                    gross_return_pct,
                    net_return_pct,
                    float(fee_pct),
                    float(tax_pct),
                    float(slippage_pct),
                    mark_date,
                    mark_price,
                    mark_return_pct,
                    _json_text(details) if details is not None else None,
                    outcome_hash,
                    now,
                ),
            )
            self._refresh_progress_uow(conn, execution_run_id, now)
            row = conn.execute(
                """
                SELECT * FROM historical_execution_outcome
                WHERE execution_run_id=? AND signal_date=? AND market=? AND ticker=?
                """,
                (execution_run_id, signal_date, clean_market, clean_ticker),
            ).fetchone()
        return self._outcome_from_row(row)
