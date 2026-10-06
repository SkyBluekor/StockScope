from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .evaluation_models import (
    JEV_EVALUATION_REPORT_VERSION,
    JEV_EVALUATION_RUN_VERSION,
    JEV_EVALUATION_SCHEMA_VERSION,
)
from .models import canonical_json


class JevEvaluationCatalogError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JevEvaluationCatalog:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise JevEvaluationCatalogError(
                "JEV_EVALUATION_MIGRATION_REQUIRED",
                f"Simulation DB를 찾을 수 없습니다: {self.db_path}",
            )
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=20000")
        return conn

    def require_ready(self, conn: sqlite3.Connection | None = None) -> None:
        owns = conn is None
        active = conn or self.connect()
        try:
            tables = {
                str(row["name"])
                for row in active.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            required = {
                "jev_evaluation_schema_meta",
                "jev_evaluation_run",
                "jev_evaluation_unit",
                "jev_shadow_comparison_report",
            }
            if not required.issubset(tables):
                raise JevEvaluationCatalogError(
                    "JEV_EVALUATION_MIGRATION_REQUIRED",
                    "JEV evaluation migration을 먼저 실행해야 합니다.",
                )
            row = active.execute(
                """
                SELECT value
                FROM jev_evaluation_schema_meta
                WHERE key='schema_version'
                """
            ).fetchone()
            if row is None or str(row["value"]) != JEV_EVALUATION_SCHEMA_VERSION:
                raise JevEvaluationCatalogError(
                    "JEV_EVALUATION_SCHEMA_UNSUPPORTED",
                    "지원하지 않는 JEV evaluation schema입니다.",
                )
        finally:
            if owns:
                active.close()

    @staticmethod
    def _run(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "client_request_id": row["client_request_id"],
            "run_version": row["run_version"],
            "protocol_id": row["protocol_id"],
            "protocol_spec_hash": row["protocol_spec_hash"],
            "evaluation_policy_id": row["evaluation_policy_id"],
            "evaluation_policy_hash": row["evaluation_policy_hash"],
            "evaluation_as_of": row["evaluation_as_of"],
            "exit_policy_token": row["exit_policy_token"],
            "status": row["status"],
            "source_set_hash": row["source_set_hash"],
            "recruited_count": int(row["recruited_count"]),
            "mature_count": int(row["mature_count"]),
            "comparable_closed_count": int(row["comparable_closed_count"]),
            "disagreement_count": int(row["disagreement_count"]),
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "error_code": row["error_code"],
            "error_message": row["error_message"],
        }

    def create_run(
        self,
        *,
        client_request_id: str,
        protocol_id: str,
        protocol_spec_hash: str,
        evaluation_policy_id: str,
        evaluation_policy_hash: str,
        evaluation_as_of: str,
        exit_policy_token: str,
    ) -> dict[str, Any]:
        clean_id = client_request_id.strip()
        if not clean_id:
            raise JevEvaluationCatalogError(
                "JEV_EVALUATION_REQUEST_ID_REQUIRED",
                "client_request_id가 필요합니다.",
            )
        with self.connect() as conn:
            self.require_ready(conn)
            existing = conn.execute(
                """
                SELECT * FROM jev_evaluation_run
                WHERE client_request_id=?
                """,
                (clean_id,),
            ).fetchone()
            if existing is not None:
                return self._run(existing)
            run_id = str(uuid4())
            now = _now()
            conn.execute(
                """
                INSERT INTO jev_evaluation_run(
                    id,client_request_id,run_version,protocol_id,
                    protocol_spec_hash,evaluation_policy_id,
                    evaluation_policy_hash,evaluation_as_of,
                    exit_policy_token,status,source_set_hash,
                    recruited_count,mature_count,comparable_closed_count,
                    disagreement_count,created_at,completed_at,
                    error_code,error_message
                ) VALUES(?,?,?,?,?,?,?,?,?,'PENDING',NULL,0,0,0,0,?,NULL,NULL,NULL)
                """,
                (
                    run_id,
                    clean_id,
                    JEV_EVALUATION_RUN_VERSION,
                    protocol_id,
                    protocol_spec_hash,
                    evaluation_policy_id,
                    evaluation_policy_hash,
                    evaluation_as_of,
                    exit_policy_token,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM jev_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._run(row)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM jev_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return None if row is None else self._run(row)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                """
                SELECT * FROM jev_evaluation_run
                ORDER BY created_at DESC,id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self._run(row) for row in rows]

    def begin_run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM jev_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise JevEvaluationCatalogError(
                    "JEV_EVALUATION_RUN_NOT_FOUND",
                    "JEV evaluation run을 찾을 수 없습니다.",
                )
            status = str(row["status"])
            if status == "COMPLETED":
                return self._run(row)
            if status == "RUNNING":
                raise JevEvaluationCatalogError(
                    "JEV_EVALUATION_ALREADY_RUNNING",
                    "JEV evaluation run이 이미 실행 중입니다.",
                )
            conn.execute(
                """
                UPDATE jev_evaluation_run
                SET status='RUNNING',error_code=NULL,error_message=NULL
                WHERE id=?
                """,
                (run_id,),
            )
            updated = conn.execute(
                "SELECT * FROM jev_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._run(updated)

    def mark_running_interrupted(self) -> int:
        with self.connect() as conn:
            self.require_ready(conn)
            cursor = conn.execute(
                """
                UPDATE jev_evaluation_run
                SET status='INTERRUPTED',
                    error_code='PROCESS_RESTART',
                    error_message='Evaluation process restarted before completion.'
                WHERE status='RUNNING'
                """
            )
            return int(cursor.rowcount or 0)

    def mark_failed(
        self,
        run_id: str,
        *,
        code: str,
        message: str,
    ) -> None:
        with self.connect() as conn:
            self.require_ready(conn)
            conn.execute(
                """
                UPDATE jev_evaluation_run
                SET status='FAILED',completed_at=?,
                    error_code=?,error_message=?
                WHERE id=? AND status!='COMPLETED'
                """,
                (_now(), code, message[:1000], run_id),
            )

    def complete_run(
        self,
        *,
        run_id: str,
        units: list[dict[str, Any]],
        report_summary: dict[str, Any],
        source_set_hash: str,
        recruited_count: int,
        mature_count: int,
        comparable_closed_count: int,
        disagreement_count: int,
    ) -> dict[str, Any]:
        now = _now()
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM jev_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise JevEvaluationCatalogError(
                    "JEV_EVALUATION_RUN_NOT_FOUND",
                    "JEV evaluation run을 찾을 수 없습니다.",
                )
            if str(row["status"]) == "COMPLETED":
                return self._run(row)

            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM jev_evaluation_unit WHERE evaluation_run_id=?",
                (run_id,),
            )
            for unit in units:
                conn.execute(
                    """
                    INSERT INTO jev_evaluation_unit(
                        evaluation_run_id,capture_run_id,sample_index,review_id,
                        market,ticker,name,signal_date,strategy,horizon,
                        review_status,review_decision,provider_id,model_id,
                        served_model,model_cohort_key,maturity_status,
                        available_trading_days,evaluated_through,
                        return_5d,return_10d,return_20d,mfe_pct,mae_pct,
                        execution_status,execution_reason,entry_date,entry_price,
                        exit_date,exit_price,exit_reason,holding_days,
                        gross_return_pct,net_return_pct,mark_return_pct,
                        comparison_eligible,details_json,computed_at
                    ) VALUES(
                        :evaluation_run_id,:capture_run_id,:sample_index,:review_id,
                        :market,:ticker,:name,:signal_date,:strategy,:horizon,
                        :review_status,:review_decision,:provider_id,:model_id,
                        :served_model,:model_cohort_key,:maturity_status,
                        :available_trading_days,:evaluated_through,
                        :return_5d,:return_10d,:return_20d,:mfe_pct,:mae_pct,
                        :execution_status,:execution_reason,:entry_date,:entry_price,
                        :exit_date,:exit_price,:exit_reason,:holding_days,
                        :gross_return_pct,:net_return_pct,:mark_return_pct,
                        :comparison_eligible,:details_json,:computed_at
                    )
                    """,
                    {
                        **unit,
                        "evaluation_run_id": run_id,
                        "details_json": canonical_json(unit.get("details") or {}),
                    },
                )

            existing_report = conn.execute(
                """
                SELECT id FROM jev_shadow_comparison_report
                WHERE protocol_id=? AND source_set_hash=?
                """,
                (row["protocol_id"], source_set_hash),
            ).fetchone()
            if existing_report is None:
                conn.execute(
                    """
                    INSERT INTO jev_shadow_comparison_report(
                        id,protocol_id,report_version,source_set_hash,
                        summary_json,created_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        str(uuid4()),
                        row["protocol_id"],
                        JEV_EVALUATION_REPORT_VERSION,
                        source_set_hash,
                        canonical_json(report_summary),
                        now,
                    ),
                )

            conn.execute(
                """
                UPDATE jev_evaluation_run
                SET status='COMPLETED',source_set_hash=?,
                    recruited_count=?,mature_count=?,
                    comparable_closed_count=?,disagreement_count=?,
                    completed_at=?,error_code=NULL,error_message=NULL
                WHERE id=?
                """,
                (
                    source_set_hash,
                    int(recruited_count),
                    int(mature_count),
                    int(comparable_closed_count),
                    int(disagreement_count),
                    now,
                    run_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM jev_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._run(updated)

    def list_units(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                """
                SELECT * FROM jev_evaluation_unit
                WHERE evaluation_run_id=?
                ORDER BY signal_date,capture_run_id,sample_index
                """,
                (run_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(str(item.pop("details_json")))
            result.append(item)
        return result

    def get_report(self, run: dict[str, Any]) -> dict[str, Any] | None:
        source_set_hash = run.get("source_set_hash")
        if not source_set_hash:
            return None
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM jev_shadow_comparison_report
                WHERE protocol_id=? AND source_set_hash=?
                LIMIT 1
                """,
                (run["protocol_id"], source_set_hash),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "protocol_id": row["protocol_id"],
            "report_version": row["report_version"],
            "source_set_hash": row["source_set_hash"],
            "summary": json.loads(str(row["summary_json"])),
            "created_at": row["created_at"],
        }

    def detail(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise JevEvaluationCatalogError(
                "JEV_EVALUATION_RUN_NOT_FOUND",
                "JEV evaluation run을 찾을 수 없습니다.",
            )
        return {
            "run": run,
            "report": self.get_report(run),
            "units": self.list_units(run_id),
        }

    def latest_completed(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM jev_evaluation_run
                WHERE status='COMPLETED'
                ORDER BY completed_at DESC,id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return self.detail(str(row["id"]))
