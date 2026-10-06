from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import (
    JEV_COMPARISON_REPORT_VERSION,
    JEV_REVIEW_TERMINAL_STATUSES,
    JEV_SCHEMA_VERSION,
    JEV_TRIAL_PROTOCOL_VERSION,
    JevTrialProtocolSpec,
    canonical_json,
    digest_json,
)


class JevCatalogError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JevCatalog:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise JevCatalogError(
                "JEV_MIGRATION_REQUIRED",
                f"Simulation DB 또는 JEV shadow schema를 찾을 수 없습니다: {self.db_path}",
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
                "jev_shadow_schema_meta",
                "jev_shadow_protocol",
                "jev_shadow_activation",
                "jev_shadow_review",
                "jev_shadow_comparison_report",
            }
            if not required.issubset(self._tables(active)):
                raise JevCatalogError(
                    "JEV_MIGRATION_REQUIRED",
                    "JEV shadow migration을 먼저 실행해야 합니다.",
                )
            row = active.execute(
                "SELECT value FROM jev_shadow_schema_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None or str(row["value"]) != JEV_SCHEMA_VERSION:
                raise JevCatalogError(
                    "JEV_SCHEMA_UNSUPPORTED",
                    "지원하지 않는 JEV shadow schema version입니다.",
                )
        finally:
            if owns:
                active.close()

    def is_ready(self) -> bool:
        try:
            with self.connect() as conn:
                self.require_ready(conn)
            return True
        except JevCatalogError:
            return False

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

    def create_protocol(
        self,
        *,
        client_request_id: str,
        spec: JevTrialProtocolSpec,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        clean_request_id = client_request_id.strip()
        if not clean_request_id:
            raise JevCatalogError(
                "JEV_PROTOCOL_REQUEST_ID_REQUIRED",
                "client_request_id가 필요합니다.",
            )
        now = created_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            existing = conn.execute(
                "SELECT * FROM jev_shadow_protocol WHERE client_request_id=?",
                (clean_request_id,),
            ).fetchone()
            if existing is not None:
                return self._protocol_from_row(existing)
            protocol_id = str(uuid4())
            payload = spec.to_dict()
            conn.execute(
                """
                INSERT INTO jev_shadow_protocol(
                    id,client_request_id,protocol_version,name,status,
                    spec_json,spec_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    protocol_id,
                    clean_request_id,
                    JEV_TRIAL_PROTOCOL_VERSION,
                    spec.name.strip() or "JEV Shadow Trial",
                    spec.status(),
                    canonical_json(payload),
                    digest_json(payload),
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM jev_shadow_protocol WHERE id=?",
                (protocol_id,),
            ).fetchone()
        return self._protocol_from_row(row)

    def get_protocol(self, protocol_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM jev_shadow_protocol WHERE id=?",
                (protocol_id,),
            ).fetchone()
        return None if row is None else self._protocol_from_row(row)

    def set_activation(
        self,
        protocol_id: str,
        *,
        enabled: bool,
        allow_network: bool = False,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        protocol = self.get_protocol(protocol_id)
        if protocol is None:
            raise JevCatalogError(
                "JEV_PROTOCOL_NOT_FOUND",
                "활성화할 JEV protocol을 찾을 수 없습니다.",
            )
        now = updated_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            conn.execute(
                """
                INSERT INTO jev_shadow_activation(
                    singleton_id,protocol_id,enabled,allow_network,updated_at
                ) VALUES(1,?,?,?,?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    protocol_id=excluded.protocol_id,
                    enabled=excluded.enabled,
                    allow_network=excluded.allow_network,
                    updated_at=excluded.updated_at
                """,
                (
                    protocol_id,
                    1 if enabled else 0,
                    1 if allow_network else 0,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM jev_shadow_activation WHERE singleton_id=1"
            ).fetchone()
        return dict(row)

    def active_protocol(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            activation = conn.execute(
                "SELECT * FROM jev_shadow_activation WHERE singleton_id=1"
            ).fetchone()
            if activation is None or not bool(activation["enabled"]):
                return None
            row = conn.execute(
                "SELECT * FROM jev_shadow_protocol WHERE id=?",
                (activation["protocol_id"],),
            ).fetchone()
            if row is None:
                raise JevCatalogError(
                    "JEV_PROTOCOL_NOT_FOUND",
                    "활성 JEV protocol을 찾을 수 없습니다.",
                )
        return self._protocol_from_row(row), dict(activation)

    def load_capture_candidates(self, capture_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                """
                SELECT
                    s.capture_run_id,s.sample_index,s.market,s.ticker,s.name,s.rank,
                    s.strategy,s.decision_status,s.candidate_state,s.action,
                    s.signal_date,s.snapshot_json,s.snapshot_hash,s.created_at,
                    r.status AS capture_status,r.request_json,r.scanner_version,
                    r.scanner_baseline,r.market_scope,r.input_fingerprint,
                    r.source_execution_key,r.source_snapshot_hash,
                    r.horizon_intent,r.horizon_policy_version,r.completed_at
                FROM prospective_recommendation_sample s
                JOIN prospective_capture_run r ON r.id=s.capture_run_id
                WHERE s.capture_run_id=?
                ORDER BY s.sample_index
                """,
                (capture_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["snapshot"] = json.loads(str(item.pop("snapshot_json")))
            item["capture_request"] = json.loads(str(item.pop("request_json")))
            result.append(item)
        return result

    @staticmethod
    def _review_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "request_id": row["request_id"],
            "protocol_id": row["protocol_id"],
            "capture_run_id": row["capture_run_id"],
            "sample_index": int(row["sample_index"]),
            "candidate_ref": row["candidate_ref"],
            "candidate_snapshot_hash": row["candidate_snapshot_hash"],
            "idempotency_key": row["idempotency_key"],
            "attempt": int(row["attempt"]),
            "input_hash": row["input_hash"],
            "input": json.loads(str(row["input_json"])),
            "provider_id": row["provider_id"],
            "model_id": row["model_id"],
            "model_revision": row["model_revision"],
            "prompt_version": row["prompt_version"],
            "prompt_hash": row["prompt_hash"],
            "output_contract_version": row["output_contract_version"],
            "adapter_version": row["adapter_version"],
            "comparison_policy": row["comparison_policy"],
            "requested_at": row["requested_at"],
            "completed_at": row["completed_at"],
            "deadline_at": row["deadline_at"],
            "status": row["status"],
            "decision": row["decision"],
            "abstain_reason": row["abstain_reason"],
            "failure_code": row["failure_code"],
            "normalized_response": (
                json.loads(str(row["normalized_response_json"]))
                if row["normalized_response_json"]
                else None
            ),
            "raw_response_hash": row["raw_response_hash"],
            "latency_ms": (
                int(row["latency_ms"]) if row["latency_ms"] is not None else None
            ),
            "usage": (
                json.loads(str(row["usage_json"])) if row["usage_json"] else None
            ),
            "cost_usd": (
                float(row["cost_usd"]) if row["cost_usd"] is not None else None
            ),
        }

    def enqueue_review(
        self,
        *,
        request_id: str,
        protocol: dict[str, Any],
        capture_run_id: str,
        sample_index: int,
        candidate_ref: str,
        candidate_snapshot_hash: str,
        idempotency_key: str,
        input_payload: dict[str, Any],
        deadline_at: str | None,
        status: str = "PENDING",
        failure_code: str | None = None,
        attempt: int = 1,
        requested_at: str | None = None,
    ) -> dict[str, Any]:
        clean_status = status.strip().upper()
        if clean_status not in {"PENDING", "SKIPPED"}:
            raise JevCatalogError(
                "JEV_REVIEW_STATUS_INVALID",
                f"enqueue에서 지원하지 않는 상태입니다: {status}",
            )
        now = requested_at or _now()
        spec = dict(protocol["spec"])
        with self.connect() as conn:
            self.require_ready(conn)
            existing = conn.execute(
                "SELECT * FROM jev_shadow_review WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return self._review_from_row(existing)
            review_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO jev_shadow_review(
                    id,request_id,protocol_id,capture_run_id,sample_index,
                    candidate_ref,candidate_snapshot_hash,idempotency_key,attempt,
                    input_hash,input_json,provider_id,model_id,model_revision,
                    prompt_version,prompt_hash,output_contract_version,
                    adapter_version,comparison_policy,requested_at,completed_at,
                    deadline_at,status,decision,abstain_reason,failure_code,
                    normalized_response_json,raw_response_hash,latency_ms,
                    usage_json,cost_usd
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    review_id,
                    request_id,
                    protocol["id"],
                    capture_run_id,
                    int(sample_index),
                    candidate_ref,
                    candidate_snapshot_hash,
                    idempotency_key,
                    int(attempt),
                    str(input_payload.get("input_hash") or ""),
                    canonical_json(input_payload),
                    str(spec.get("provider_id") or ""),
                    str(spec.get("model_id") or ""),
                    str(spec.get("model_revision") or ""),
                    str(spec.get("prompt_version") or ""),
                    str(spec.get("prompt_hash") or ""),
                    str(spec.get("output_contract_version") or ""),
                    str(spec.get("adapter_version") or ""),
                    str(spec.get("comparison_policy") or ""),
                    now,
                    now if clean_status == "SKIPPED" else None,
                    deadline_at,
                    clean_status,
                    None,
                    None,
                    failure_code,
                    None,
                    None,
                    0 if clean_status == "SKIPPED" else None,
                    None,
                    0.0 if clean_status == "SKIPPED" else None,
                ),
            )
            row = conn.execute(
                "SELECT * FROM jev_shadow_review WHERE id=?",
                (review_id,),
            ).fetchone()
        return self._review_from_row(row)

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM jev_shadow_review WHERE id=?",
                (review_id,),
            ).fetchone()
        return None if row is None else self._review_from_row(row)

    def list_reviews(
        self,
        *,
        protocol_id: str | None = None,
        capture_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        params: list[Any] = []
        if protocol_id:
            clauses.append("protocol_id=?")
            params.append(protocol_id)
        if capture_run_id:
            clauses.append("capture_run_id=?")
            params.append(capture_run_id)
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                f"""
                SELECT * FROM jev_shadow_review
                WHERE {' AND '.join(clauses)}
                ORDER BY requested_at,id
                """,
                params,
            ).fetchall()
        return [self._review_from_row(row) for row in rows]

    def complete_review(
        self,
        review_id: str,
        *,
        status: str,
        decision: str,
        abstain_reason: str | None,
        failure_code: str | None,
        normalized_response: dict[str, Any],
        raw_response_hash: str | None,
        latency_ms: int,
        usage: dict[str, Any] | None,
        cost_usd: float | None,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        clean_status = status.strip().upper()
        if clean_status not in {"VALID", "ERROR", "LATE"}:
            raise JevCatalogError(
                "JEV_REVIEW_STATUS_INVALID",
                f"지원하지 않는 review 종료 상태입니다: {status}",
            )
        now = completed_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM jev_shadow_review WHERE id=?",
                (review_id,),
            ).fetchone()
            if row is None:
                raise JevCatalogError(
                    "JEV_REVIEW_NOT_FOUND",
                    "JEV shadow review를 찾을 수 없습니다.",
                )
            if str(row["status"]) in JEV_REVIEW_TERMINAL_STATUSES:
                return self._review_from_row(row)
            conn.execute(
                """
                UPDATE jev_shadow_review
                SET completed_at=?,status=?,decision=?,abstain_reason=?,
                    failure_code=?,normalized_response_json=?,
                    raw_response_hash=?,latency_ms=?,usage_json=?,cost_usd=?
                WHERE id=?
                """,
                (
                    now,
                    clean_status,
                    decision,
                    abstain_reason,
                    failure_code,
                    canonical_json(normalized_response),
                    raw_response_hash,
                    max(0, int(latency_ms)),
                    canonical_json(usage) if usage is not None else None,
                    cost_usd,
                    review_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM jev_shadow_review WHERE id=?",
                (review_id,),
            ).fetchone()
        return self._review_from_row(updated)

    def mark_pending_interrupted(self, updated_at: str | None = None) -> int:
        now = updated_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            cursor = conn.execute(
                """
                UPDATE jev_shadow_review
                SET completed_at=?,status='INTERRUPTED',
                    decision='ABSTAIN',abstain_reason='MODEL_ERROR',
                    failure_code='PROCESS_RESTART',latency_ms=NULL,cost_usd=NULL
                WHERE status='PENDING'
                """,
                (now,),
            )
            return int(cursor.rowcount or 0)

    def create_comparison_report(
        self,
        *,
        protocol_id: str,
        source_set_hash: str,
        summary: dict[str, Any],
        created_at: str | None = None,
    ) -> dict[str, Any]:
        now = created_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            existing = conn.execute(
                """
                SELECT * FROM jev_shadow_comparison_report
                WHERE protocol_id=? AND source_set_hash=?
                """,
                (protocol_id, source_set_hash),
            ).fetchone()
            if existing is not None:
                return {
                    **dict(existing),
                    "summary": json.loads(str(existing["summary_json"])),
                }
            report_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO jev_shadow_comparison_report(
                    id,protocol_id,report_version,source_set_hash,summary_json,created_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    report_id,
                    protocol_id,
                    JEV_COMPARISON_REPORT_VERSION,
                    source_set_hash,
                    canonical_json(summary),
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM jev_shadow_comparison_report WHERE id=?",
                (report_id,),
            ).fetchone()
        return {**dict(row), "summary": json.loads(str(row["summary_json"]))}

    def status_summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            self.require_ready(conn)
            activation = conn.execute(
                "SELECT * FROM jev_shadow_activation WHERE singleton_id=1"
            ).fetchone()
            counts = conn.execute(
                """
                SELECT status,COUNT(*) AS n
                FROM jev_shadow_review
                GROUP BY status
                ORDER BY status
                """
            ).fetchall()
            decisions = conn.execute(
                """
                SELECT decision,COUNT(*) AS n
                FROM jev_shadow_review
                WHERE decision IS NOT NULL
                GROUP BY decision
                ORDER BY decision
                """
            ).fetchall()
        return {
            "schema_version": JEV_SCHEMA_VERSION,
            "activation": dict(activation) if activation is not None else None,
            "status_counts": {str(row["status"]): int(row["n"]) for row in counts},
            "decision_counts": {
                str(row["decision"]): int(row["n"]) for row in decisions
            },
        }
