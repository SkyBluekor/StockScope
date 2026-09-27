from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import (
    PROSPECTIVE_CAPTURE_VERSION,
    PROSPECTIVE_EVALUATION_VERSION,
    PROSPECTIVE_PROTOCOL_VERSION,
    PROSPECTIVE_REPORT_VERSION,
    PROSPECTIVE_SCHEMA_VERSION,
    EvaluationProtocolSpec,
    ProspectiveCaptureRequest,
    canonical_json,
    digest_json,
)


class ProspectiveCatalogError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProspectiveCatalog:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise ProspectiveCatalogError(
                "PROSPECTIVE_MIGRATION_REQUIRED",
                f"Simulation DB 또는 P2-S2 schema를 찾을 수 없습니다: {self.db_path}",
            )
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=20000")
        return conn

    @staticmethod
    def _tables(conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {str(row["name"]) for row in rows}

    def require_ready(self, conn: sqlite3.Connection | None = None) -> None:
        owns = conn is None
        active = conn or self.connect()
        try:
            required = {
                "prospective_schema_meta",
                "prospective_capture_run",
                "prospective_recommendation_sample",
                "prospective_evaluation_protocol",
                "prospective_evaluation_run",
                "prospective_evaluation_unit",
                "prospective_evaluation_report",
            }
            if not required.issubset(self._tables(active)):
                raise ProspectiveCatalogError(
                    "PROSPECTIVE_MIGRATION_REQUIRED",
                    "VN-P2-S2 prospective migration을 먼저 실행해야 합니다.",
                )
            row = active.execute(
                "SELECT value FROM prospective_schema_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None or str(row["value"]) != PROSPECTIVE_SCHEMA_VERSION:
                raise ProspectiveCatalogError(
                    "PROSPECTIVE_SCHEMA_UNSUPPORTED",
                    "지원하지 않는 prospective schema version입니다.",
                )
        finally:
            if owns:
                active.close()

    def is_ready(self) -> bool:
        try:
            with self.connect() as conn:
                self.require_ready(conn)
            return True
        except ProspectiveCatalogError:
            return False

    def begin_capture(
        self,
        *,
        source_job_id: str,
        request: ProspectiveCaptureRequest,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        now = created_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            existing = conn.execute(
                "SELECT * FROM prospective_capture_run WHERE source_job_id=?",
                (source_job_id,),
            ).fetchone()
            if existing is not None:
                return self._capture_from_row(existing)
            capture_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO prospective_capture_run(
                    id,capture_version,source_job_id,status,request_json,
                    market_scope,requested_as_of,candidate_limit,
                    horizon_intent,horizon_policy_version,
                    created_at,started_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    capture_id,
                    PROSPECTIVE_CAPTURE_VERSION,
                    source_job_id,
                    "PENDING",
                    canonical_json(request.to_dict()),
                    request.market_scope,
                    request.requested_as_of,
                    int(request.candidate_limit),
                    request.horizon_intent,
                    request.horizon_policy_version,
                    now,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM prospective_capture_run WHERE id=?",
                (capture_id,),
            ).fetchone()
        return self._capture_from_row(row)

    @staticmethod
    def _capture_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "capture_version": row["capture_version"],
            "source_job_id": row["source_job_id"],
            "source_execution_key": row["source_execution_key"],
            "canonical_capture_id": row["canonical_capture_id"],
            "status": row["status"],
            "request": json.loads(str(row["request_json"])),
            "scanner_version": row["scanner_version"],
            "scanner_baseline": row["scanner_baseline"],
            "market_scope": row["market_scope"],
            "requested_as_of": row["requested_as_of"],
            "actual_data_date": row["actual_data_date"],
            "input_fingerprint": row["input_fingerprint"],
            "horizon_intent": row["horizon_intent"],
            "horizon_policy_version": row["horizon_policy_version"],
            "candidate_limit": int(row["candidate_limit"]),
            "actionable_candidate_count": int(row["actionable_candidate_count"] or 0),
            "returned_candidate_count": int(row["returned_candidate_count"] or 0),
            "result_hash": row["result_hash"],
            "source_snapshot_hash": row["source_snapshot_hash"],
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "updated_at": row["updated_at"],
        }

    def _result_identity(
        self,
        *,
        request: ProspectiveCaptureRequest,
        result: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> tuple[str, str, str]:
        snapshot = {
            "version": result.get("version"),
            "requested_as_of": result.get("requested_as_of"),
            "market_scope": result.get("market_scope"),
            "data_dates": result.get("data_dates"),
            "input_fingerprint": result.get("input_fingerprint"),
            "partial_data": bool(result.get("partial_data")),
            "summary": result.get("summary"),
            "candidates": candidates,
            "horizon_context": result.get("horizon_context"),
        }
        source_snapshot_hash = digest_json(snapshot)
        source_execution_key = digest_json(
            {
                "scanner_version": result.get("version"),
                "market_scope": result.get("market_scope") or request.market_scope,
                "requested_as_of": result.get("requested_as_of"),
                "candidate_limit": request.candidate_limit,
                "input_fingerprint": result.get("input_fingerprint"),
                "source_snapshot_hash": source_snapshot_hash,
            }
        )
        result_hash = digest_json(
            {
                "source_execution_key": source_execution_key,
                "summary": result.get("summary"),
                "candidate_count": len(candidates),
            }
        )
        return source_execution_key, source_snapshot_hash, result_hash

    @staticmethod
    def _candidate_snapshot(item: dict[str, Any]) -> dict[str, Any]:
        return dict(item)

    def finalize_capture(
        self,
        *,
        source_job_id: str,
        request: ProspectiveCaptureRequest,
        result: dict[str, Any],
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        now = completed_at or _now()
        top = result.get("candidates") if isinstance(result.get("candidates"), list) else []
        more = result.get("more_candidates") if isinstance(result.get("more_candidates"), list) else []
        candidates = [
            dict(item)
            for item in [*top, *more]
            if isinstance(item, dict)
        ]
        execution_key, source_snapshot_hash, result_hash = self._result_identity(
            request=request,
            result=result,
            candidates=candidates,
        )
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        repro = (
            (result.get("diagnostics") or {}).get("reproducibility_audit")
            if isinstance(result.get("diagnostics"), dict)
            else None
        )
        baseline = None
        if isinstance(repro, dict):
            baseline = repro.get("production_baseline") or repro.get("scanner_baseline")
        scanner_version = str(result.get("version") or "") or None
        data_date = str(result.get("requested_as_of") or "") or None
        market_scope = str(result.get("market_scope") or request.market_scope)
        input_fingerprint = str(result.get("input_fingerprint") or "") or None

        conn = self.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM prospective_capture_run WHERE source_job_id=?",
                (source_job_id,),
            ).fetchone()
            if row is None:
                capture_id = str(uuid4())
                conn.execute(
                    """
                    INSERT INTO prospective_capture_run(
                        id,capture_version,source_job_id,status,request_json,
                        market_scope,requested_as_of,candidate_limit,
                        horizon_intent,horizon_policy_version,
                        created_at,started_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        capture_id,
                        PROSPECTIVE_CAPTURE_VERSION,
                        source_job_id,
                        "PENDING",
                        canonical_json(request.to_dict()),
                        request.market_scope,
                        request.requested_as_of,
                        int(request.candidate_limit),
                        request.horizon_intent,
                        request.horizon_policy_version,
                        now,
                        now,
                        now,
                    ),
                )
            else:
                capture_id = str(row["id"])

            duplicate = conn.execute(
                """
                SELECT id FROM prospective_capture_run
                WHERE source_execution_key=? AND status='COMPLETE' AND id<>?
                ORDER BY completed_at,id LIMIT 1
                """,
                (execution_key, capture_id),
            ).fetchone()
            if duplicate is not None:
                conn.execute(
                    """
                    UPDATE prospective_capture_run
                    SET source_execution_key=?,canonical_capture_id=?,status='DUPLICATE',
                        scanner_version=?,scanner_baseline=?,market_scope=?,
                        actual_data_date=?,input_fingerprint=?,
                        actionable_candidate_count=?,returned_candidate_count=?,
                        result_hash=?,source_snapshot_hash=?,
                        completed_at=?,updated_at=?,error_code=NULL,error_message=NULL
                    WHERE id=?
                    """,
                    (
                        execution_key,
                        duplicate["id"],
                        scanner_version,
                        baseline,
                        market_scope,
                        data_date,
                        input_fingerprint,
                        int(summary.get("candidate_count") or 0),
                        len(candidates),
                        result_hash,
                        source_snapshot_hash,
                        now,
                        now,
                        capture_id,
                    ),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM prospective_capture_run WHERE id=?",
                    (capture_id,),
                ).fetchone()
                return self._capture_from_row(row)

            conn.execute(
                """
                UPDATE prospective_capture_run
                SET source_execution_key=?,canonical_capture_id=NULL,status='COMPLETE',
                    scanner_version=?,scanner_baseline=?,market_scope=?,
                    actual_data_date=?,input_fingerprint=?,
                    actionable_candidate_count=?,returned_candidate_count=?,
                    result_hash=?,source_snapshot_hash=?,
                    completed_at=?,updated_at=?,error_code=NULL,error_message=NULL
                WHERE id=?
                """,
                (
                    execution_key,
                    scanner_version,
                    baseline,
                    market_scope,
                    data_date,
                    input_fingerprint,
                    int(summary.get("candidate_count") or 0),
                    len(candidates),
                    result_hash,
                    source_snapshot_hash,
                    now,
                    now,
                    capture_id,
                ),
            )
            for index, candidate in enumerate(candidates):
                snapshot = self._candidate_snapshot(candidate)
                market = str(candidate.get("market") or "").upper()
                ticker = str(candidate.get("code") or candidate.get("ticker") or "").strip().upper()
                if not market or not ticker:
                    continue
                name = str(candidate.get("name") or ticker)
                rank = candidate.get("rank")
                try:
                    rank_value = int(rank) if rank is not None else None
                except (TypeError, ValueError):
                    rank_value = None
                strategy = candidate.get("strategy")
                if strategy is None:
                    strategy = candidate.get("quick_strategy")
                decision = candidate.get("decision_status")
                state = candidate.get("candidate_state")
                action = candidate.get("action")
                snapshot_hash = digest_json(snapshot)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO prospective_recommendation_sample(
                        capture_run_id,sample_index,market,ticker,name,rank,
                        strategy,decision_status,candidate_state,action,
                        signal_date,snapshot_json,snapshot_hash,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        capture_id,
                        index,
                        market,
                        ticker,
                        name,
                        rank_value,
                        str(strategy) if strategy is not None else None,
                        str(decision) if decision is not None else None,
                        str(state) if state is not None else None,
                        str(action) if action is not None else None,
                        data_date,
                        canonical_json(snapshot),
                        snapshot_hash,
                        now,
                    ),
                )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM prospective_capture_run WHERE id=?",
                (capture_id,),
            ).fetchone()
            return self._capture_from_row(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_capture_terminal(
        self,
        source_job_id: str,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        updated_at: str | None = None,
    ) -> dict[str, Any] | None:
        clean = status.strip().upper()
        if clean not in {"FAILED", "CANCELLED", "INTERRUPTED"}:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_CAPTURE_STATUS_INVALID",
                f"지원하지 않는 capture 종료 상태입니다: {status}",
            )
        now = updated_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM prospective_capture_run WHERE source_job_id=?",
                (source_job_id,),
            ).fetchone()
            if row is None:
                return None
            if str(row["status"]) in {"COMPLETE", "DUPLICATE"}:
                return self._capture_from_row(row)
            conn.execute(
                """
                UPDATE prospective_capture_run
                SET status=?,error_code=?,error_message=?,completed_at=?,updated_at=?
                WHERE source_job_id=?
                """,
                (clean, error_code, error_message, now, now, source_job_id),
            )
            row = conn.execute(
                "SELECT * FROM prospective_capture_run WHERE source_job_id=?",
                (source_job_id,),
            ).fetchone()
        return self._capture_from_row(row)

    def mark_pending_interrupted(
        self,
        *,
        reason: str = "BACKEND_RESTARTED_BEFORE_CAPTURE_COMMIT",
        updated_at: str | None = None,
    ) -> int:
        now = updated_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            cursor = conn.execute(
                """
                UPDATE prospective_capture_run
                SET status='INTERRUPTED',
                    error_code='PROSPECTIVE_CAPTURE_INTERRUPTED',
                    error_message=?,
                    completed_at=?,
                    updated_at=?
                WHERE status='PENDING'
                """,
                (reason, now, now),
            )
            return int(cursor.rowcount or 0)

    def get_capture_by_job(self, source_job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM prospective_capture_run WHERE source_job_id=?",
                (source_job_id,),
            ).fetchone()
        return self._capture_from_row(row) if row else None

    def list_captures(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                """
                SELECT * FROM prospective_capture_run
                ORDER BY created_at DESC,id DESC LIMIT ?
                """,
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [self._capture_from_row(row) for row in rows]

    def list_samples(
        self,
        *,
        capture_run_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        market_scope: str | None = None,
        strategy: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["r.status='COMPLETE'"]
        params: list[Any] = []
        if capture_run_id:
            clauses.append("s.capture_run_id=?")
            params.append(capture_run_id)
        if date_from:
            clauses.append("s.signal_date>=?")
            params.append(date_from)
        if date_to:
            clauses.append("s.signal_date<=?")
            params.append(date_to)
        if market_scope and market_scope != "ALL":
            clauses.append("s.market=?")
            params.append(market_scope)
        if strategy:
            clauses.append("s.strategy=?")
            params.append(strategy)
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                f"""
                SELECT s.*,r.scanner_version,r.scanner_baseline,r.market_scope,
                       r.input_fingerprint,r.source_execution_key,r.horizon_intent,
                       r.horizon_policy_version
                FROM prospective_recommendation_sample s
                JOIN prospective_capture_run r ON r.id=s.capture_run_id
                WHERE {' AND '.join(clauses)}
                ORDER BY s.signal_date,s.capture_run_id,s.sample_index
                """,
                params,
            ).fetchall()
        return [
            {
                **dict(row),
                "snapshot": json.loads(str(row["snapshot_json"])),
            }
            for row in rows
        ]

    def create_protocol(
        self,
        *,
        client_request_id: str,
        spec: EvaluationProtocolSpec,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        now = created_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            existing = conn.execute(
                "SELECT * FROM prospective_evaluation_protocol WHERE client_request_id=?",
                (client_request_id,),
            ).fetchone()
            if existing is not None:
                return self._protocol_from_row(existing)
            protocol_id = str(uuid4())
            spec_json = canonical_json(spec.to_dict())
            spec_hash = digest_json(spec.to_dict())
            conn.execute(
                """
                INSERT INTO prospective_evaluation_protocol(
                    id,client_request_id,protocol_version,name,status,
                    spec_json,spec_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    protocol_id,
                    client_request_id,
                    PROSPECTIVE_PROTOCOL_VERSION,
                    spec.name,
                    "FROZEN",
                    spec_json,
                    spec_hash,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_protocol WHERE id=?",
                (protocol_id,),
            ).fetchone()
        return self._protocol_from_row(row)

    @staticmethod
    def _protocol_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "client_request_id": row["client_request_id"],
            "protocol_version": row["protocol_version"],
            "name": row["name"],
            "status": row["status"],
            "spec": json.loads(str(row["spec_json"])),
            "spec_hash": row["spec_hash"],
            "created_at": row["created_at"],
        }

    def get_protocol(self, protocol_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_protocol WHERE id=?",
                (protocol_id,),
            ).fetchone()
        return self._protocol_from_row(row) if row else None

    def list_protocols(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                "SELECT * FROM prospective_evaluation_protocol ORDER BY created_at DESC,id DESC"
            ).fetchall()
        return [self._protocol_from_row(row) for row in rows]

    def create_evaluation_run(
        self,
        *,
        protocol_id: str,
        client_request_id: str,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        now = created_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            protocol = conn.execute(
                "SELECT * FROM prospective_evaluation_protocol WHERE id=?",
                (protocol_id,),
            ).fetchone()
            if protocol is None:
                raise ProspectiveCatalogError(
                    "PROSPECTIVE_PROTOCOL_NOT_FOUND",
                    "평가 protocol을 찾을 수 없습니다.",
                )
            existing = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE client_request_id=?",
                (client_request_id,),
            ).fetchone()
            if existing is not None:
                return self._run_from_row(existing)
            run_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO prospective_evaluation_run(
                    id,protocol_id,client_request_id,evaluation_version,status,
                    created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    run_id,
                    protocol_id,
                    client_request_id,
                    PROSPECTIVE_EVALUATION_VERSION,
                    "DRAFT",
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._run_from_row(row)

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "protocol_id": row["protocol_id"],
            "client_request_id": row["client_request_id"],
            "evaluation_version": row["evaluation_version"],
            "status": row["status"],
            "source_capture_count": int(row["source_capture_count"] or 0),
            "source_sample_count": int(row["source_sample_count"] or 0),
            "development_count": int(row["development_count"] or 0),
            "holdout_count": int(row["holdout_count"] or 0),
            "purged_count": int(row["purged_count"] or 0),
            "mature_count": int(row["mature_count"] or 0),
            "immature_count": int(row["immature_count"] or 0),
            "excluded_count": int(row["excluded_count"] or 0),
            "failed_count": int(row["failed_count"] or 0),
            "processed_count": int(row["processed_count"] or 0),
            "cancel_requested": bool(row["cancel_requested"]),
            "restart_count": int(row["restart_count"] or 0),
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "updated_at": row["updated_at"],
        }

    def get_evaluation_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._run_from_row(row) if row else None

    def list_evaluation_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                """
                SELECT * FROM prospective_evaluation_run
                ORDER BY created_at DESC,id DESC LIMIT ?
                """,
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def begin_evaluation_run(self, run_id: str) -> dict[str, Any]:
        now = _now()
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ProspectiveCatalogError(
                    "PROSPECTIVE_EVALUATION_RUN_NOT_FOUND",
                    "평가 run을 찾을 수 없습니다.",
                )
            status = str(row["status"])
            if status == "COMPLETED":
                return self._run_from_row(row)
            if status == "RUNNING":
                raise ProspectiveCatalogError(
                    "PROSPECTIVE_EVALUATION_ALREADY_RUNNING",
                    "이미 실행 중인 평가입니다.",
                )
            if status == "CANCELLED":
                raise ProspectiveCatalogError(
                    "PROSPECTIVE_EVALUATION_CANCELLED",
                    "취소된 평가는 같은 run에서 재개하지 않습니다. 새 run을 생성하세요.",
                )
            restart_increment = 1 if status in {"FAILED", "INTERRUPTED"} else 0
            conn.execute(
                """
                UPDATE prospective_evaluation_run
                SET status='RUNNING',started_at=COALESCE(started_at,?),
                    cancel_requested=0,processed_count=0,
                    restart_count=restart_count+?,
                    error_code=NULL,error_message=NULL,updated_at=?
                WHERE id=?
                """,
                (now, restart_increment, now, run_id),
            )
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._run_from_row(row)

    def replace_evaluation_units(
        self,
        *,
        run_id: str,
        units: list[dict[str, Any]],
        counts: dict[str, int],
        report_summary: dict[str, Any],
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        now = completed_at or _now()
        conn = self.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ProspectiveCatalogError(
                    "PROSPECTIVE_EVALUATION_RUN_NOT_FOUND",
                    "평가 run을 찾을 수 없습니다.",
                )
            if str(row["status"]) == "COMPLETED":
                conn.rollback()
                return self._run_from_row(row)
            conn.execute(
                "DELETE FROM prospective_evaluation_unit WHERE evaluation_run_id=?",
                (run_id,),
            )
            for unit in units:
                conn.execute(
                    """
                    INSERT INTO prospective_evaluation_unit(
                        evaluation_run_id,capture_run_id,sample_index,split,
                        maturity_status,exclusion_reason,signal_date,market,ticker,
                        strategy,available_trading_days,evaluated_through,
                        return_5d,return_10d,return_20d,mfe_pct,mae_pct,
                        entry_comparable,entry_touched,stop_comparable,stop_touched,
                        target1_comparable,target1_touched,target2_comparable,target2_touched,
                        execution_status,execution_reason,entry_date,entry_price,
                        exit_date,exit_price,exit_reason,holding_days,
                        gross_return_pct,net_return_pct,mark_return_pct,
                        details_json,computed_at
                    ) VALUES(
                        :evaluation_run_id,:capture_run_id,:sample_index,:split,
                        :maturity_status,:exclusion_reason,:signal_date,:market,:ticker,
                        :strategy,:available_trading_days,:evaluated_through,
                        :return_5d,:return_10d,:return_20d,:mfe_pct,:mae_pct,
                        :entry_comparable,:entry_touched,:stop_comparable,:stop_touched,
                        :target1_comparable,:target1_touched,:target2_comparable,:target2_touched,
                        :execution_status,:execution_reason,:entry_date,:entry_price,
                        :exit_date,:exit_price,:exit_reason,:holding_days,
                        :gross_return_pct,:net_return_pct,:mark_return_pct,
                        :details_json,:computed_at
                    )
                    """,
                    {
                        **unit,
                        "evaluation_run_id": run_id,
                        "details_json": canonical_json(unit.get("details") or {}),
                    },
                )
            report_id = str(uuid4())
            source_hash = digest_json(
                [
                    {
                        "capture_run_id": unit["capture_run_id"],
                        "sample_index": unit["sample_index"],
                        "signal_date": unit["signal_date"],
                        "market": unit["market"],
                        "ticker": unit["ticker"],
                        "split": unit["split"],
                        "maturity_status": unit["maturity_status"],
                    }
                    for unit in units
                ]
            )
            conn.execute(
                """
                INSERT INTO prospective_evaluation_report(
                    id,evaluation_run_id,report_version,source_set_hash,
                    summary_json,created_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    report_id,
                    run_id,
                    PROSPECTIVE_REPORT_VERSION,
                    source_hash,
                    canonical_json(report_summary),
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE prospective_evaluation_run
                SET status='COMPLETED',
                    source_capture_count=?,source_sample_count=?,
                    development_count=?,holdout_count=?,purged_count=?,
                    mature_count=?,immature_count=?,excluded_count=?,failed_count=?,
                    processed_count=?,cancel_requested=0,
                    completed_at=?,updated_at=?,error_code=NULL,error_message=NULL
                WHERE id=?
                """,
                (
                    int(counts.get("source_capture_count", 0)),
                    int(counts.get("source_sample_count", 0)),
                    int(counts.get("development_count", 0)),
                    int(counts.get("holdout_count", 0)),
                    int(counts.get("purged_count", 0)),
                    int(counts.get("mature_count", 0)),
                    int(counts.get("immature_count", 0)),
                    int(counts.get("excluded_count", 0)),
                    int(counts.get("failed_count", 0)),
                    len(units),
                    now,
                    now,
                    run_id,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
            return self._run_from_row(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def request_evaluation_cancel(self, run_id: str) -> dict[str, Any]:
        now = _now()
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ProspectiveCatalogError(
                    "PROSPECTIVE_EVALUATION_RUN_NOT_FOUND",
                    "평가 run을 찾을 수 없습니다.",
                )
            if str(row["status"]) in {"COMPLETED", "CANCELLED"}:
                return self._run_from_row(row)
            conn.execute(
                """
                UPDATE prospective_evaluation_run
                SET cancel_requested=1,updated_at=?
                WHERE id=?
                """,
                (now, run_id),
            )
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._run_from_row(row)

    def evaluation_cancel_requested(self, run_id: str) -> bool:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT cancel_requested FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_EVALUATION_RUN_NOT_FOUND",
                "평가 run을 찾을 수 없습니다.",
            )
        return bool(row["cancel_requested"])

    def update_evaluation_progress(self, run_id: str, processed_count: int) -> None:
        with self.connect() as conn:
            self.require_ready(conn)
            conn.execute(
                """
                UPDATE prospective_evaluation_run
                SET processed_count=?,updated_at=?
                WHERE id=? AND status='RUNNING'
                """,
                (max(0, int(processed_count)), _now(), run_id),
            )

    def mark_evaluation_cancelled(self, run_id: str) -> dict[str, Any]:
        now = _now()
        with self.connect() as conn:
            self.require_ready(conn)
            conn.execute(
                """
                UPDATE prospective_evaluation_run
                SET status='CANCELLED',completed_at=?,updated_at=?,
                    error_code=NULL,error_message=NULL
                WHERE id=? AND status='RUNNING'
                """,
                (now, now, run_id),
            )
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_EVALUATION_RUN_NOT_FOUND",
                "평가 run을 찾을 수 없습니다.",
            )
        return self._run_from_row(row)

    def mark_running_evaluations_interrupted(
        self,
        *,
        reason: str = "BACKEND_RESTARTED_DURING_EVALUATION",
    ) -> int:
        now = _now()
        with self.connect() as conn:
            self.require_ready(conn)
            cursor = conn.execute(
                """
                UPDATE prospective_evaluation_run
                SET status='INTERRUPTED',
                    error_code='PROSPECTIVE_EVALUATION_INTERRUPTED',
                    error_message=?,completed_at=?,updated_at=?
                WHERE status='RUNNING'
                """,
                (reason, now, now),
            )
            return int(cursor.rowcount or 0)

    def fail_evaluation_run(
        self,
        run_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> dict[str, Any]:
        now = _now()
        with self.connect() as conn:
            self.require_ready(conn)
            conn.execute(
                """
                UPDATE prospective_evaluation_run
                SET status='FAILED',error_code=?,error_message=?,
                    completed_at=?,updated_at=?
                WHERE id=?
                """,
                (error_code, error_message, now, now, run_id),
            )
            row = conn.execute(
                "SELECT * FROM prospective_evaluation_run WHERE id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_EVALUATION_RUN_NOT_FOUND",
                "평가 run을 찾을 수 없습니다.",
            )
        return self._run_from_row(row)

    def get_report_for_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM prospective_evaluation_report
                WHERE evaluation_run_id=? ORDER BY created_at DESC,id DESC LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "evaluation_run_id": row["evaluation_run_id"],
            "report_version": row["report_version"],
            "source_set_hash": row["source_set_hash"],
            "summary": json.loads(str(row["summary_json"])),
            "created_at": row["created_at"],
        }

    def list_units(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                """
                SELECT * FROM prospective_evaluation_unit
                WHERE evaluation_run_id=?
                ORDER BY signal_date,capture_run_id,sample_index
                """,
                (run_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(str(item.pop("details_json")))
            result.append(item)
        return result

    def status_summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            self.require_ready(conn)
            capture_counts = {
                str(row["status"]): int(row["n"])
                for row in conn.execute(
                    "SELECT status,COUNT(*) AS n FROM prospective_capture_run GROUP BY status"
                ).fetchall()
            }
            sample_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM prospective_recommendation_sample s
                    JOIN prospective_capture_run r ON r.id=s.capture_run_id
                    WHERE r.status='COMPLETE'
                    """
                ).fetchone()[0]
            )
            first_signal = conn.execute(
                """
                SELECT MIN(s.signal_date) AS d
                FROM prospective_recommendation_sample s
                JOIN prospective_capture_run r ON r.id=s.capture_run_id
                WHERE r.status='COMPLETE'
                """
            ).fetchone()["d"]
            latest_signal = conn.execute(
                """
                SELECT MAX(s.signal_date) AS d
                FROM prospective_recommendation_sample s
                JOIN prospective_capture_run r ON r.id=s.capture_run_id
                WHERE r.status='COMPLETE'
                """
            ).fetchone()["d"]
            protocol_count = int(
                conn.execute("SELECT COUNT(*) FROM prospective_evaluation_protocol").fetchone()[0]
            )
            evaluation_count = int(
                conn.execute("SELECT COUNT(*) FROM prospective_evaluation_run").fetchone()[0]
            )
        return {
            "schema_version": PROSPECTIVE_SCHEMA_VERSION,
            "capture_counts": capture_counts,
            "sample_count": sample_count,
            "first_signal_date": first_signal,
            "latest_signal_date": latest_signal,
            "protocol_count": protocol_count,
            "evaluation_run_count": evaluation_count,
            "minimum_sample_policy_defined": False,
            "strategy_promotion_allowed": False,
            "adaptive_rotation_enabled": False,
        }
