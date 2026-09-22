from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


PRODUCTION_SCANNER_VERSION = "0.21.3.7"


class ValidationCatalogError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# VAL.1-A — replay persistence foundation
def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_value(value: str | None) -> Any:
    if value in (None, ""):
        return None
    return json.loads(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_text(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class HistoricalValidationDraft:
    id: str
    name: str
    validation_target: str
    market_scope: str
    scanner_version: str
    scanner_baseline: str | None
    requested_period_type: str
    requested_start_month: str
    requested_end_month: str
    resolved_start_date: str
    resolved_end_date: str
    trading_day_count: int
    status: str
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    processed_day_count: int = 0
    candidate_count: int = 0
    last_completed_date: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "validation_target": self.validation_target,
            "market_scope": self.market_scope,
            "scanner_version": self.scanner_version,
            "scanner_baseline": self.scanner_baseline,
            "requested_period_type": self.requested_period_type,
            "requested_start_month": self.requested_start_month,
            "requested_end_month": self.requested_end_month,
            "resolved_start_date": self.resolved_start_date,
            "resolved_end_date": self.resolved_end_date,
            "trading_day_count": self.trading_day_count,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "processed_day_count": self.processed_day_count,
            "candidate_count": self.candidate_count,
            "last_completed_date": self.last_completed_date,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "cancel_requested": self.cancel_requested,
        }


@dataclass(frozen=True, slots=True)
class HistoricalValidationDay:
    validation_id: str
    trading_date: str
    status: str
    scanner_version: str
    market_scope: str
    candidate_count: int
    scanner_cache_hit: bool
    partial_data: bool
    input_fingerprint: Any
    result_hash: str | None
    duration_ms: int
    market_summary: Any
    summary: Any
    methodology: Any
    diagnostics: Any
    error_code: str | None
    error_message: str | None
    started_at: str
    completed_at: str | None


@dataclass(frozen=True, slots=True)
class HistoricalValidationCandidate:
    validation_id: str
    trading_date: str
    market: str
    ticker: str
    name: str
    rank: int | None
    result_bucket: str
    strategy: str | None
    decision_status: str | None
    snapshot: dict[str, Any]
    snapshot_hash: str


class HistoricalValidationCatalog:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection, table: str, definitions: dict[str, str]) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, ddl in definitions.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS historical_validation_run (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    validation_target TEXT NOT NULL,
                    market_scope TEXT NOT NULL,
                    scanner_version TEXT NOT NULL,
                    scanner_baseline TEXT,
                    requested_period_type TEXT NOT NULL,
                    requested_start_month TEXT NOT NULL,
                    requested_end_month TEXT NOT NULL,
                    resolved_start_date TEXT NOT NULL,
                    resolved_end_date TEXT NOT NULL,
                    trading_day_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    processed_day_count INTEGER NOT NULL DEFAULT 0,
                    candidate_count INTEGER NOT NULL DEFAULT 0,
                    last_completed_date TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            self._ensure_columns(
                conn,
                "historical_validation_run",
                {
                    "started_at": "TEXT",
                    "completed_at": "TEXT",
                    "processed_day_count": "INTEGER NOT NULL DEFAULT 0",
                    "candidate_count": "INTEGER NOT NULL DEFAULT 0",
                    "last_completed_date": "TEXT",
                    "error_code": "TEXT",
                    "error_message": "TEXT",
                    "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
                },
            )
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_historical_validation_status_created
                    ON historical_validation_run(status, created_at DESC);

                CREATE TABLE IF NOT EXISTS historical_validation_day (
                    validation_id TEXT NOT NULL,
                    trading_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scanner_version TEXT NOT NULL,
                    market_scope TEXT NOT NULL,
                    candidate_count INTEGER NOT NULL DEFAULT 0,
                    scanner_cache_hit INTEGER NOT NULL DEFAULT 0,
                    partial_data INTEGER NOT NULL DEFAULT 0,
                    input_fingerprint_json TEXT,
                    result_hash TEXT,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    market_summary_json TEXT,
                    summary_json TEXT,
                    methodology_json TEXT,
                    diagnostics_json TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    PRIMARY KEY(validation_id, trading_date),
                    FOREIGN KEY(validation_id) REFERENCES historical_validation_run(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS historical_validation_candidate (
                    validation_id TEXT NOT NULL,
                    trading_date TEXT NOT NULL,
                    market TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    name TEXT NOT NULL,
                    rank INTEGER,
                    result_bucket TEXT NOT NULL,
                    strategy TEXT,
                    decision_status TEXT,
                    candidate_snapshot_json TEXT NOT NULL,
                    snapshot_hash TEXT NOT NULL,
                    PRIMARY KEY(validation_id, trading_date, market, ticker),
                    FOREIGN KEY(validation_id, trading_date)
                        REFERENCES historical_validation_day(validation_id, trading_date)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_historical_validation_day_status_date
                    ON historical_validation_day(validation_id, status, trading_date);

                CREATE INDEX IF NOT EXISTS idx_historical_validation_candidate_day_rank
                    ON historical_validation_candidate(validation_id, trading_date, rank, ticker);
                """
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> HistoricalValidationDraft:
        return HistoricalValidationDraft(
            id=row["id"], name=row["name"], validation_target=row["validation_target"],
            market_scope=row["market_scope"], scanner_version=row["scanner_version"],
            scanner_baseline=row["scanner_baseline"], requested_period_type=row["requested_period_type"],
            requested_start_month=row["requested_start_month"], requested_end_month=row["requested_end_month"],
            resolved_start_date=row["resolved_start_date"], resolved_end_date=row["resolved_end_date"],
            trading_day_count=int(row["trading_day_count"]), status=row["status"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            started_at=row["started_at"], completed_at=row["completed_at"],
            processed_day_count=int(row["processed_day_count"] or 0),
            candidate_count=int(row["candidate_count"] or 0),
            last_completed_date=row["last_completed_date"],
            error_code=row["error_code"], error_message=row["error_message"],
            cancel_requested=bool(row["cancel_requested"]),
        )

    @staticmethod
    def _day_from_row(row: sqlite3.Row) -> HistoricalValidationDay:
        return HistoricalValidationDay(
            validation_id=row["validation_id"],
            trading_date=row["trading_date"],
            status=row["status"],
            scanner_version=row["scanner_version"],
            market_scope=row["market_scope"],
            candidate_count=int(row["candidate_count"] or 0),
            scanner_cache_hit=bool(row["scanner_cache_hit"]),
            partial_data=bool(row["partial_data"]),
            input_fingerprint=_json_value(row["input_fingerprint_json"]),
            result_hash=row["result_hash"],
            duration_ms=int(row["duration_ms"] or 0),
            market_summary=_json_value(row["market_summary_json"]),
            summary=_json_value(row["summary_json"]),
            methodology=_json_value(row["methodology_json"]),
            diagnostics=_json_value(row["diagnostics_json"]),
            error_code=row["error_code"],
            error_message=row["error_message"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    @staticmethod
    def _candidate_from_row(row: sqlite3.Row) -> HistoricalValidationCandidate:
        return HistoricalValidationCandidate(
            validation_id=row["validation_id"],
            trading_date=row["trading_date"],
            market=row["market"],
            ticker=row["ticker"],
            name=row["name"],
            rank=int(row["rank"]) if row["rank"] is not None else None,
            result_bucket=row["result_bucket"],
            strategy=row["strategy"],
            decision_status=row["decision_status"],
            snapshot=_json_value(row["candidate_snapshot_json"]) or {},
            snapshot_hash=row["snapshot_hash"],
        )

    def create_draft(
        self,
        *,
        name: str,
        market_scope: str,
        requested_period_type: str,
        requested_start_month: str,
        requested_end_month: str,
        resolved_start_date: str,
        resolved_end_date: str,
        trading_day_count: int,
        scanner_baseline: str | None = None,
    ) -> HistoricalValidationDraft:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationCatalogError("SIM_VALIDATION_NAME_REQUIRED", "검증 이름을 입력해주세요.")
        if len(clean_name) > 120:
            raise ValidationCatalogError("SIM_VALIDATION_NAME_TOO_LONG", "검증 이름은 120자 이내로 입력해주세요.")
        now = datetime.now(timezone.utc).isoformat()
        draft = HistoricalValidationDraft(
            id=str(uuid4()), name=clean_name, validation_target="PRODUCTION_SCANNER",
            market_scope=market_scope, scanner_version=PRODUCTION_SCANNER_VERSION,
            scanner_baseline=scanner_baseline, requested_period_type=requested_period_type,
            requested_start_month=requested_start_month, requested_end_month=requested_end_month,
            resolved_start_date=resolved_start_date, resolved_end_date=resolved_end_date,
            trading_day_count=int(trading_day_count), status="DRAFT", created_at=now, updated_at=now,
        )
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO historical_validation_run(
                    id,name,validation_target,market_scope,scanner_version,scanner_baseline,
                    requested_period_type,requested_start_month,requested_end_month,
                    resolved_start_date,resolved_end_date,trading_day_count,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    draft.id, draft.name, draft.validation_target, draft.market_scope,
                    draft.scanner_version, draft.scanner_baseline, draft.requested_period_type,
                    draft.requested_start_month, draft.requested_end_month, draft.resolved_start_date,
                    draft.resolved_end_date, draft.trading_day_count, draft.status, draft.created_at, draft.updated_at,
                ),
            )
        return draft

    def list(self) -> list[HistoricalValidationDraft]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM historical_validation_run ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, validation_id: str) -> HistoricalValidationDraft | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM historical_validation_run WHERE id=?", (validation_id,)).fetchone()
        return self._from_row(row) if row else None

    def delete(self, validation_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT status FROM historical_validation_run WHERE id=?", (validation_id,)).fetchone()
            if row is None:
                return False
            if row["status"] == "RUNNING":
                raise ValidationCatalogError("SIM_VALIDATION_RUNNING", "실행 중인 검증은 삭제할 수 없습니다.")
            cursor = conn.execute("DELETE FROM historical_validation_run WHERE id=?", (validation_id,))
        return cursor.rowcount == 1

    def list_days(self, validation_id: str) -> list[HistoricalValidationDay]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM historical_validation_day WHERE validation_id=? ORDER BY trading_date",
                (validation_id,),
            ).fetchall()
        return [self._day_from_row(row) for row in rows]

    def get_day(self, validation_id: str, trading_date: str) -> HistoricalValidationDay | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM historical_validation_day WHERE validation_id=? AND trading_date=?",
                (validation_id, trading_date),
            ).fetchone()
        return self._day_from_row(row) if row else None

    def completed_dates(self, validation_id: str) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT trading_date FROM historical_validation_day WHERE validation_id=? AND status='COMPLETED'",
                (validation_id,),
            ).fetchall()
        return {str(row["trading_date"]) for row in rows}

    def list_candidates(self, validation_id: str, trading_date: str | None = None) -> list[HistoricalValidationCandidate]:
        with self.connect() as conn:
            if trading_date is None:
                rows = conn.execute(
                    """SELECT * FROM historical_validation_candidate
                       WHERE validation_id=?
                       ORDER BY trading_date, CASE result_bucket WHEN 'TOP' THEN 0 ELSE 1 END, rank, ticker""",
                    (validation_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM historical_validation_candidate
                       WHERE validation_id=? AND trading_date=?
                       ORDER BY CASE result_bucket WHEN 'TOP' THEN 0 ELSE 1 END, rank, ticker""",
                    (validation_id, trading_date),
                ).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    @staticmethod
    def _refresh_progress_uow(conn: sqlite3.Connection, validation_id: str, now: str) -> None:
        conn.execute(
            """UPDATE historical_validation_run
               SET processed_day_count=(
                       SELECT COUNT(*) FROM historical_validation_day
                       WHERE validation_id=? AND status='COMPLETED'
                   ),
                   candidate_count=(
                       SELECT COALESCE(SUM(candidate_count), 0) FROM historical_validation_day
                       WHERE validation_id=? AND status='COMPLETED'
                   ),
                   last_completed_date=(
                       SELECT MAX(trading_date) FROM historical_validation_day
                       WHERE validation_id=? AND status='COMPLETED'
                   ),
                   updated_at=?
               WHERE id=?""",
            (validation_id, validation_id, validation_id, now, validation_id),
        )

    def save_completed_day(
        self,
        *,
        validation_id: str,
        trading_date: str,
        scanner_version: str,
        market_scope: str,
        scanner_cache_hit: bool,
        partial_data: bool,
        input_fingerprint: Any,
        market_summary: Any,
        summary: Any,
        methodology: Any,
        diagnostics: Any,
        candidates: list[dict[str, Any]],
        duration_ms: int = 0,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> HistoricalValidationDay:
        started = started_at or datetime.now(timezone.utc).isoformat()
        completed = completed_at or datetime.now(timezone.utc).isoformat()
        normalized: list[dict[str, Any]] = []
        for candidate in candidates:
            market = str(candidate.get("market") or "").strip().upper()
            ticker = str(candidate.get("ticker") or "").strip()
            name = str(candidate.get("name") or "").strip()
            bucket = str(candidate.get("result_bucket") or "").strip().upper()
            if not market or not ticker or not name or bucket not in {"TOP", "MORE"}:
                raise ValidationCatalogError(
                    "VAL_REPLAY_CANDIDATE_INVALID",
                    "Replay candidate requires market, ticker, name and TOP/MORE result_bucket.",
                )
            snapshot_value = candidate.get("snapshot")
            snapshot = dict(snapshot_value) if isinstance(snapshot_value, dict) else dict(candidate)
            rank_value = candidate.get("rank")
            normalized.append(
                {
                    "market": market,
                    "ticker": ticker,
                    "name": name,
                    "rank": int(rank_value) if rank_value not in (None, "") else None,
                    "result_bucket": bucket,
                    "strategy": str(candidate["strategy"]).strip() if candidate.get("strategy") else None,
                    "decision_status": str(candidate["decision_status"]).strip() if candidate.get("decision_status") else None,
                    "snapshot": snapshot,
                    "snapshot_hash": _digest(snapshot),
                }
            )

        result_hash = _digest(
            {
                "validation_id": validation_id,
                "trading_date": trading_date,
                "scanner_version": scanner_version,
                "market_scope": market_scope,
                "input_fingerprint": input_fingerprint,
                "candidate_hashes": [row["snapshot_hash"] for row in normalized],
            }
        )
        now = datetime.now(timezone.utc).isoformat()

        with self.connect() as conn:
            parent = conn.execute("SELECT id FROM historical_validation_run WHERE id=?", (validation_id,)).fetchone()
            if parent is None:
                raise ValidationCatalogError("VAL_REPLAY_NOT_FOUND", "저장된 검증을 찾을 수 없습니다.")

            existing = conn.execute(
                "SELECT * FROM historical_validation_day WHERE validation_id=? AND trading_date=?",
                (validation_id, trading_date),
            ).fetchone()
            if existing is not None and existing["status"] == "COMPLETED":
                return self._day_from_row(existing)

            conn.execute(
                "DELETE FROM historical_validation_candidate WHERE validation_id=? AND trading_date=?",
                (validation_id, trading_date),
            )
            conn.execute(
                """INSERT INTO historical_validation_day(
                    validation_id,trading_date,status,scanner_version,market_scope,candidate_count,
                    scanner_cache_hit,partial_data,input_fingerprint_json,result_hash,duration_ms,
                    market_summary_json,summary_json,methodology_json,diagnostics_json,
                    error_code,error_message,started_at,completed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(validation_id,trading_date) DO UPDATE SET
                    status=excluded.status,
                    scanner_version=excluded.scanner_version,
                    market_scope=excluded.market_scope,
                    candidate_count=excluded.candidate_count,
                    scanner_cache_hit=excluded.scanner_cache_hit,
                    partial_data=excluded.partial_data,
                    input_fingerprint_json=excluded.input_fingerprint_json,
                    result_hash=excluded.result_hash,
                    duration_ms=excluded.duration_ms,
                    market_summary_json=excluded.market_summary_json,
                    summary_json=excluded.summary_json,
                    methodology_json=excluded.methodology_json,
                    diagnostics_json=excluded.diagnostics_json,
                    error_code=NULL,
                    error_message=NULL,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at""",
                (
                    validation_id, trading_date, "COMPLETED", scanner_version, market_scope,
                    len(normalized), 1 if scanner_cache_hit else 0, 1 if partial_data else 0,
                    _json_text(input_fingerprint) if input_fingerprint is not None else None,
                    result_hash, max(0, int(duration_ms)),
                    _json_text(market_summary) if market_summary is not None else None,
                    _json_text(summary) if summary is not None else None,
                    _json_text(methodology) if methodology is not None else None,
                    _json_text(diagnostics) if diagnostics is not None else None,
                    None, None, started, completed,
                ),
            )
            for candidate in normalized:
                conn.execute(
                    """INSERT INTO historical_validation_candidate(
                        validation_id,trading_date,market,ticker,name,rank,result_bucket,
                        strategy,decision_status,candidate_snapshot_json,snapshot_hash
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        validation_id, trading_date, candidate["market"], candidate["ticker"], candidate["name"],
                        candidate["rank"], candidate["result_bucket"], candidate["strategy"],
                        candidate["decision_status"], _json_text(candidate["snapshot"]), candidate["snapshot_hash"],
                    ),
                )
            self._refresh_progress_uow(conn, validation_id, now)
            row = conn.execute(
                "SELECT * FROM historical_validation_day WHERE validation_id=? AND trading_date=?",
                (validation_id, trading_date),
            ).fetchone()
        return self._day_from_row(row)


    # VAL.1-B — replay lifecycle
    def begin_replay(self, validation_id: str) -> HistoricalValidationDraft:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM historical_validation_run WHERE id=?", (validation_id,)
            ).fetchone()
            if row is None:
                raise ValidationCatalogError("VAL_REPLAY_NOT_FOUND", "저장된 검증을 찾을 수 없습니다.")
            status = str(row["status"])
            if status == "RUNNING":
                raise ValidationCatalogError("VAL_REPLAY_ALREADY_RUNNING", "이미 실행 중인 검증입니다.")
            if status == "COMPLETED":
                raise ValidationCatalogError("VAL_REPLAY_ALREADY_COMPLETED", "이미 완료된 검증입니다.")
            if status not in {"DRAFT", "FAILED", "CANCELLED"}:
                raise ValidationCatalogError(
                    "VAL_REPLAY_INVALID_STATUS",
                    f"검증을 실행할 수 없는 상태입니다: {status}",
                )
            conn.execute(
                """UPDATE historical_validation_run
                   SET status='RUNNING',
                       started_at=COALESCE(started_at, ?),
                       completed_at=NULL,
                       error_code=NULL,
                       error_message=NULL,
                       cancel_requested=0,
                       updated_at=?
                   WHERE id=?""",
                (now, now, validation_id),
            )
            updated = conn.execute(
                "SELECT * FROM historical_validation_run WHERE id=?", (validation_id,)
            ).fetchone()
        return self._from_row(updated)

    def request_cancel(self, validation_id: str) -> HistoricalValidationDraft:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM historical_validation_run WHERE id=?", (validation_id,)
            ).fetchone()
            if row is None:
                raise ValidationCatalogError("VAL_REPLAY_NOT_FOUND", "저장된 검증을 찾을 수 없습니다.")
            if row["status"] == "RUNNING":
                conn.execute(
                    "UPDATE historical_validation_run SET cancel_requested=1,updated_at=? WHERE id=?",
                    (now, validation_id),
                )
            updated = conn.execute(
                "SELECT * FROM historical_validation_run WHERE id=?", (validation_id,)
            ).fetchone()
        return self._from_row(updated)

    def cancel_requested(self, validation_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM historical_validation_run WHERE id=?", (validation_id,)
            ).fetchone()
        if row is None:
            raise ValidationCatalogError("VAL_REPLAY_NOT_FOUND", "저장된 검증을 찾을 수 없습니다.")
        return bool(row["cancel_requested"])

    def mark_replay_failed(
        self, validation_id: str, error_code: str, error_message: str
    ) -> HistoricalValidationDraft:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                """UPDATE historical_validation_run
                   SET status='FAILED',
                       error_code=?,
                       error_message=?,
                       cancel_requested=0,
                       updated_at=?
                   WHERE id=?""",
                (error_code, error_message, now, validation_id),
            )
            if cursor.rowcount != 1:
                raise ValidationCatalogError("VAL_REPLAY_NOT_FOUND", "저장된 검증을 찾을 수 없습니다.")
            row = conn.execute(
                "SELECT * FROM historical_validation_run WHERE id=?", (validation_id,)
            ).fetchone()
        return self._from_row(row)

    def mark_replay_cancelled(self, validation_id: str) -> HistoricalValidationDraft:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                """UPDATE historical_validation_run
                   SET status='CANCELLED',
                       error_code=NULL,
                       error_message=NULL,
                       cancel_requested=0,
                       updated_at=?
                   WHERE id=?""",
                (now, validation_id),
            )
            if cursor.rowcount != 1:
                raise ValidationCatalogError("VAL_REPLAY_NOT_FOUND", "저장된 검증을 찾을 수 없습니다.")
            row = conn.execute(
                "SELECT * FROM historical_validation_run WHERE id=?", (validation_id,)
            ).fetchone()
        return self._from_row(row)

    def mark_replay_completed(self, validation_id: str) -> HistoricalValidationDraft:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                """UPDATE historical_validation_run
                   SET status='COMPLETED',
                       completed_at=?,
                       error_code=NULL,
                       error_message=NULL,
                       cancel_requested=0,
                       updated_at=?
                   WHERE id=?""",
                (now, now, validation_id),
            )
            if cursor.rowcount != 1:
                raise ValidationCatalogError("VAL_REPLAY_NOT_FOUND", "저장된 검증을 찾을 수 없습니다.")
            row = conn.execute(
                "SELECT * FROM historical_validation_run WHERE id=?", (validation_id,)
            ).fetchone()
        return self._from_row(row)

    def record_failed_day(
        self,
        *,
        validation_id: str,
        trading_date: str,
        scanner_version: str,
        market_scope: str,
        error_code: str,
        error_message: str,
        duration_ms: int = 0,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> HistoricalValidationDay:
        started = started_at or datetime.now(timezone.utc).isoformat()
        completed = completed_at or datetime.now(timezone.utc).isoformat()
        now = datetime.now(timezone.utc).isoformat()

        with self.connect() as conn:
            parent = conn.execute("SELECT id FROM historical_validation_run WHERE id=?", (validation_id,)).fetchone()
            if parent is None:
                raise ValidationCatalogError("VAL_REPLAY_NOT_FOUND", "저장된 검증을 찾을 수 없습니다.")

            existing = conn.execute(
                "SELECT * FROM historical_validation_day WHERE validation_id=? AND trading_date=?",
                (validation_id, trading_date),
            ).fetchone()
            if existing is not None and existing["status"] == "COMPLETED":
                return self._day_from_row(existing)

            conn.execute(
                "DELETE FROM historical_validation_candidate WHERE validation_id=? AND trading_date=?",
                (validation_id, trading_date),
            )
            conn.execute(
                """INSERT INTO historical_validation_day(
                    validation_id,trading_date,status,scanner_version,market_scope,candidate_count,
                    scanner_cache_hit,partial_data,input_fingerprint_json,result_hash,duration_ms,
                    market_summary_json,summary_json,methodology_json,diagnostics_json,
                    error_code,error_message,started_at,completed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(validation_id,trading_date) DO UPDATE SET
                    status=excluded.status,
                    scanner_version=excluded.scanner_version,
                    market_scope=excluded.market_scope,
                    candidate_count=0,
                    scanner_cache_hit=0,
                    partial_data=0,
                    input_fingerprint_json=NULL,
                    result_hash=NULL,
                    duration_ms=excluded.duration_ms,
                    market_summary_json=NULL,
                    summary_json=NULL,
                    methodology_json=NULL,
                    diagnostics_json=NULL,
                    error_code=excluded.error_code,
                    error_message=excluded.error_message,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at""",
                (
                    validation_id, trading_date, "FAILED", scanner_version, market_scope,
                    0, 0, 0, None, None, max(0, int(duration_ms)),
                    None, None, None, None, error_code, error_message, started, completed,
                ),
            )
            self._refresh_progress_uow(conn, validation_id, now)
            row = conn.execute(
                "SELECT * FROM historical_validation_day WHERE validation_id=? AND trading_date=?",
                (validation_id, trading_date),
            ).fetchone()
        return self._day_from_row(row)

