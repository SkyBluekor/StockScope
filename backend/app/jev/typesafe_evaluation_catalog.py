from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import canonical_json
from .typesafe_evaluation_models import (
    JEV_TYPESAFE_EVALUATION_REPORT_VERSION,
    JEV_TYPESAFE_EVALUATION_RUN_VERSION,
    JEV_TYPESAFE_EVALUATION_SCHEMA_VERSION,
)


class TypeSafeJevEvaluationCatalogError(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TypeSafeJevEvaluationCatalog:
    REQUIRED_TABLES = {
        "jev_typesafe_evaluation_schema_meta",
        "jev_typesafe_evaluation_run",
        "jev_typesafe_evaluation_unit",
        "jev_typesafe_evaluation_report",
    }

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise TypeSafeJevEvaluationCatalogError(
                "JEV_TYPESAFE_EVALUATION_MIGRATION_REQUIRED"
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
                str(row[0])
                for row in active.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if not self.REQUIRED_TABLES.issubset(tables):
                raise TypeSafeJevEvaluationCatalogError(
                    "JEV_TYPESAFE_EVALUATION_MIGRATION_REQUIRED"
                )
            row = active.execute(
                """
                SELECT value FROM jev_typesafe_evaluation_schema_meta
                WHERE key='schema_version'
                """
            ).fetchone()
            if row is None or str(row[0]) != JEV_TYPESAFE_EVALUATION_SCHEMA_VERSION:
                raise TypeSafeJevEvaluationCatalogError(
                    "JEV_TYPESAFE_EVALUATION_SCHEMA_UNSUPPORTED"
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
            "callable_count": int(row["callable_count"]),
            "review_created_count": int(row["review_created_count"]),
            "valid_count": int(row["valid_count"]),
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
        clean = client_request_id.strip()
        if not clean:
            raise TypeSafeJevEvaluationCatalogError(
                "JEV_TYPESAFE_EVALUATION_REQUEST_ID_REQUIRED"
            )
        with self.connect() as conn:
            self.require_ready(conn)
            existing = conn.execute(
                """
                SELECT * FROM jev_typesafe_evaluation_run
                WHERE client_request_id=?
                """,
                (clean,),
            ).fetchone()
            if existing is not None:
                return self._run(existing)
            run_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO jev_typesafe_evaluation_run(
                    id,client_request_id,run_version,protocol_id,
                    protocol_spec_hash,evaluation_policy_id,
                    evaluation_policy_hash,evaluation_as_of,
                    exit_policy_token,status,source_set_hash,
                    recruited_count,callable_count,review_created_count,
                    valid_count,mature_count,comparable_closed_count,
                    disagreement_count,created_at,completed_at,
                    error_code,error_message
                ) VALUES(
                    ?,?,?,?,?,?,?,?,?,'PENDING',NULL,
                    0,0,0,0,0,0,0,?,NULL,NULL,NULL
                )
                """,
                (
                    run_id,
                    clean,
                    JEV_TYPESAFE_EVALUATION_RUN_VERSION,
                    protocol_id,
                    protocol_spec_hash,
                    evaluation_policy_id,
                    evaluation_policy_hash,
                    evaluation_as_of,
                    exit_policy_token,
                    _now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM jev_typesafe_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._run(row)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM jev_typesafe_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return None if row is None else self._run(row)

    def begin_run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM jev_typesafe_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise TypeSafeJevEvaluationCatalogError(
                    "JEV_TYPESAFE_EVALUATION_RUN_NOT_FOUND"
                )
            if row["status"] == "COMPLETED":
                return self._run(row)
            if row["status"] == "RUNNING":
                raise TypeSafeJevEvaluationCatalogError(
                    "JEV_TYPESAFE_EVALUATION_ALREADY_RUNNING"
                )
            conn.execute(
                """
                UPDATE jev_typesafe_evaluation_run
                SET status='RUNNING',error_code=NULL,error_message=NULL
                WHERE id=?
                """,
                (run_id,),
            )
            updated = conn.execute(
                "SELECT * FROM jev_typesafe_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._run(updated)

    def mark_running_interrupted(self) -> int:
        with self.connect() as conn:
            self.require_ready(conn)
            cursor = conn.execute(
                """
                UPDATE jev_typesafe_evaluation_run
                SET status='INTERRUPTED',
                    error_code='PROCESS_RESTART',
                    error_message='Evaluation process restarted before completion.'
                WHERE status='RUNNING'
                """
            )
            return int(cursor.rowcount or 0)

    def mark_failed(self, run_id: str, *, code: str, message: str) -> None:
        with self.connect() as conn:
            self.require_ready(conn)
            conn.execute(
                """
                UPDATE jev_typesafe_evaluation_run
                SET status='FAILED',completed_at=?,
                    error_code=?,error_message=?
                WHERE id=? AND status!='COMPLETED'
                """,
                (_now(), code, message, run_id),
            )

    def complete_run(
        self,
        *,
        run_id: str,
        units: list[dict[str, Any]],
        report_summary: dict[str, Any],
        source_set_hash: str,
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jev_typesafe_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise TypeSafeJevEvaluationCatalogError(
                    "JEV_TYPESAFE_EVALUATION_RUN_NOT_FOUND"
                )
            if row["status"] == "COMPLETED":
                conn.rollback()
                return self._run(row)

            conn.execute(
                "DELETE FROM jev_typesafe_evaluation_unit WHERE evaluation_run_id=?",
                (run_id,),
            )
            for unit in units:
                conn.execute(
                    """
                    INSERT INTO jev_typesafe_evaluation_unit(
                        evaluation_run_id,recruitment_id,capture_run_id,sample_index,
                        review_id,market,ticker,name,signal_date,strategy,horizon,
                        callable,skip_reason,operational_status,disposition,
                        failure_code,integrity_status,provider_id,model_requested,
                        model_returned,model_identity_status,model_cohort_key,
                        latency_ms,reserved_cost_usd,known_cost_usd,cost_unknown,
                        maturity_status,available_trading_days,evaluated_through,
                        return_5d,return_10d,return_20d,mfe_pct,mae_pct,
                        execution_status,execution_reason,entry_date,entry_price,
                        exit_date,exit_price,exit_reason,holding_days,
                        gross_return_pct,net_return_pct,mark_return_pct,
                        comparison_eligible,details_json,computed_at
                    ) VALUES(
                        :evaluation_run_id,:recruitment_id,:capture_run_id,:sample_index,
                        :review_id,:market,:ticker,:name,:signal_date,:strategy,:horizon,
                        :callable,:skip_reason,:operational_status,:disposition,
                        :failure_code,:integrity_status,:provider_id,:model_requested,
                        :model_returned,:model_identity_status,:model_cohort_key,
                        :latency_ms,:reserved_cost_usd,:known_cost_usd,:cost_unknown,
                        :maturity_status,:available_trading_days,:evaluated_through,
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

            conn.execute(
                "DELETE FROM jev_typesafe_evaluation_report WHERE evaluation_run_id=?",
                (run_id,),
            )
            conn.execute(
                """
                INSERT INTO jev_typesafe_evaluation_report(
                    id,evaluation_run_id,report_version,source_set_hash,
                    summary_json,created_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    str(uuid4()),
                    run_id,
                    JEV_TYPESAFE_EVALUATION_REPORT_VERSION,
                    source_set_hash,
                    canonical_json(report_summary),
                    _now(),
                ),
            )
            funnel = dict(report_summary.get("funnel") or {})
            comparison = dict(report_summary.get("comparison") or {})
            conn.execute(
                """
                UPDATE jev_typesafe_evaluation_run
                SET status='COMPLETED',source_set_hash=?,
                    recruited_count=?,callable_count=?,review_created_count=?,
                    valid_count=?,mature_count=?,comparable_closed_count=?,
                    disagreement_count=?,completed_at=?,
                    error_code=NULL,error_message=NULL
                WHERE id=?
                """,
                (
                    source_set_hash,
                    int(funnel.get("recruited") or 0),
                    int(funnel.get("callable") or 0),
                    int(funnel.get("review_created") or 0),
                    int(funnel.get("valid") or 0),
                    int(funnel.get("mature") or 0),
                    int(funnel.get("comparable_closed") or 0),
                    int(comparison.get("disagreement_count") or 0),
                    _now(),
                    run_id,
                ),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM jev_typesafe_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
            return self._run(updated)
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def latest_completed(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM jev_typesafe_evaluation_run
                WHERE status='COMPLETED'
                ORDER BY completed_at DESC,id DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return self.detail(str(row["id"]))

    def detail(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise TypeSafeJevEvaluationCatalogError(
                "JEV_TYPESAFE_EVALUATION_RUN_NOT_FOUND"
            )
        with self.connect() as conn:
            self.require_ready(conn)
            report = conn.execute(
                """
                SELECT * FROM jev_typesafe_evaluation_report
                WHERE evaluation_run_id=?
                """,
                (run_id,),
            ).fetchone()
            units = conn.execute(
                """
                SELECT * FROM jev_typesafe_evaluation_unit
                WHERE evaluation_run_id=?
                ORDER BY signal_date,market,ticker,recruitment_id
                """,
                (run_id,),
            ).fetchall()
        return {
            "run": run,
            "report": (
                {
                    **dict(report),
                    "summary": json.loads(str(report["summary_json"])),
                }
                if report is not None
                else None
            ),
            "units": [
                {
                    **dict(row),
                    "details": json.loads(str(row["details_json"])),
                }
                for row in units
            ],
        }
