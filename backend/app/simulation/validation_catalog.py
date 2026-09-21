from __future__ import annotations

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
        }


class HistoricalValidationCatalog:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

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
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_historical_validation_status_created
                    ON historical_validation_run(status, created_at DESC);
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
