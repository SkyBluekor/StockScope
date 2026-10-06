from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .typesafe_models import (
    JEV_TYPESAFE_DISPOSITIONS,
    JEV_TYPESAFE_PROTOCOL_VERSION,
    JEV_TYPESAFE_PROVIDER_ID,
    JEV_TYPESAFE_SCHEMA_VERSION,
    JEV_TYPESAFE_TERMINAL_STATUSES,
    TypeSafeJevTrialProtocolSpec,
    canonical_json,
    digest_json,
)


class TypeSafeJevCatalogError(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TypeSafeJevCatalog:
    REQUIRED_TABLES = {
        "jev_typesafe_schema_meta",
        "jev_typesafe_protocol",
        "jev_typesafe_activation",
        "jev_typesafe_recruitment",
        "jev_typesafe_review",
    }

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise TypeSafeJevCatalogError("JEV_TYPESAFE_MIGRATION_REQUIRED")
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
                raise TypeSafeJevCatalogError("JEV_TYPESAFE_MIGRATION_REQUIRED")
            row = active.execute(
                "SELECT value FROM jev_typesafe_schema_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None or str(row[0]) != JEV_TYPESAFE_SCHEMA_VERSION:
                raise TypeSafeJevCatalogError("JEV_TYPESAFE_SCHEMA_UNSUPPORTED")
        finally:
            if owns:
                active.close()

    @staticmethod
    def _protocol(row: sqlite3.Row) -> dict[str, Any]:
        return {**dict(row), "spec": json.loads(str(row["spec_json"]))}

    def create_protocol(
        self,
        *,
        client_request_id: str,
        spec: TypeSafeJevTrialProtocolSpec,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        request_id = client_request_id.strip()
        if not request_id:
            raise TypeSafeJevCatalogError("JEV_TYPESAFE_PROTOCOL_REQUEST_ID_REQUIRED")
        payload = spec.to_dict()
        spec_hash = digest_json(payload)
        now = created_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            existing = conn.execute(
                "SELECT * FROM jev_typesafe_protocol WHERE client_request_id=?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                decoded = self._protocol(existing)
                if decoded["spec_hash"] != spec_hash:
                    raise TypeSafeJevCatalogError(
                        "JEV_TYPESAFE_PROTOCOL_REQUEST_CONFLICT"
                    )
                return decoded
            protocol_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO jev_typesafe_protocol(
                    id,client_request_id,protocol_version,name,status,
                    spec_json,spec_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    protocol_id,
                    request_id,
                    JEV_TYPESAFE_PROTOCOL_VERSION,
                    spec.name.strip() or "TypeSafe Jev Trial V2",
                    spec.status(),
                    canonical_json(payload),
                    spec_hash,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM jev_typesafe_protocol WHERE id=?",
                (protocol_id,),
            ).fetchone()
        return self._protocol(row)

    def get_protocol(self, protocol_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM jev_typesafe_protocol WHERE id=?",
                (protocol_id,),
            ).fetchone()
        return None if row is None else self._protocol(row)

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
            raise TypeSafeJevCatalogError("JEV_TYPESAFE_PROTOCOL_NOT_FOUND")
        if allow_network and not enabled:
            raise TypeSafeJevCatalogError("JEV_TYPESAFE_ACTIVATION_INVALID")
        if enabled and protocol["status"] != "FROZEN":
            raise TypeSafeJevCatalogError("JEV_TYPESAFE_PROTOCOL_NOT_FROZEN")
        spec = dict(protocol["spec"])
        provider_id = str(spec.get("provider_id") or "").upper()
        if enabled and provider_id != "FAKE":
            if provider_id != JEV_TYPESAFE_PROVIDER_ID:
                raise TypeSafeJevCatalogError("JEV_TYPESAFE_PROVIDER_UNSUPPORTED")
            if not allow_network:
                raise TypeSafeJevCatalogError(
                    "JEV_TYPESAFE_NETWORK_ACTIVATION_REQUIRED"
                )
            if not bool(spec.get("source_transmission_approved")):
                raise TypeSafeJevCatalogError(
                    "JEV_TYPESAFE_SOURCE_TRANSMISSION_NOT_APPROVED"
                )
        now = updated_at or _now()
        with self.connect() as conn:
            self.require_ready(conn)
            conn.execute(
                """
                INSERT INTO jev_typesafe_activation(
                    singleton_id,protocol_id,enabled,allow_network,updated_at
                ) VALUES(1,?,?,?,?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    protocol_id=excluded.protocol_id,
                    enabled=excluded.enabled,
                    allow_network=excluded.allow_network,
                    updated_at=excluded.updated_at
                """,
                (protocol_id, 1 if enabled else 0, 1 if allow_network else 0, now),
            )
            row = conn.execute(
                "SELECT * FROM jev_typesafe_activation WHERE singleton_id=1"
            ).fetchone()
        return dict(row)

    def reserve_recruitment(
        self,
        *,
        protocol_id: str,
        capture_run_id: str,
        sample_index: int,
        analysis_unit_key: str,
        candidate_snapshot_hash: str,
        callable: bool,
        skip_reason: str | None = None,
        reserved_cost_usd: float = 0.0,
        recruited_at: str | None = None,
    ) -> dict[str, Any]:
        protocol = self.get_protocol(protocol_id)
        if protocol is None:
            raise TypeSafeJevCatalogError("JEV_TYPESAFE_PROTOCOL_NOT_FOUND")
        spec = dict(protocol["spec"])
        reservation = max(0.0, float(reserved_cost_usd))
        now = recruited_at or _now()
        conn = self.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT * FROM jev_typesafe_recruitment
                WHERE protocol_id=? AND analysis_unit_key=?
                """,
                (protocol_id, analysis_unit_key),
            ).fetchone()
            if existing is not None:
                conn.rollback()
                return dict(existing)
            count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM jev_typesafe_recruitment WHERE protocol_id=?",
                    (protocol_id,),
                ).fetchone()[0]
            )
            maximum = spec.get("max_recruited_candidates")
            if maximum is not None and count >= int(maximum):
                conn.rollback()
                return {
                    "status": "NOT_RECRUITED_LIMIT",
                    "protocol_id": protocol_id,
                    "analysis_unit_key": analysis_unit_key,
                }

            final_callable = bool(callable)
            final_skip = skip_reason
            final_reservation = reservation if final_callable else 0.0
            budget = spec.get("budget_limit_usd")
            if final_callable and budget is not None:
                exposure = float(
                    conn.execute(
                        """
                        SELECT COALESCE(SUM(
                            CASE WHEN known_cost_usd IS NOT NULL
                                 THEN known_cost_usd ELSE reserved_cost_usd END
                        ),0)
                        FROM jev_typesafe_recruitment
                        WHERE protocol_id=?
                        """,
                        (protocol_id,),
                    ).fetchone()[0]
                    or 0.0
                )
                if exposure + final_reservation > float(budget):
                    final_callable = False
                    final_skip = "BUDGET_LIMIT"
                    final_reservation = 0.0

            recruitment_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO jev_typesafe_recruitment(
                    id,protocol_id,capture_run_id,sample_index,
                    analysis_unit_key,candidate_snapshot_hash,recruited_at,
                    callable,skip_reason,reserved_cost_usd,known_cost_usd,
                    cost_unknown,review_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL)
                """,
                (
                    recruitment_id,
                    protocol_id,
                    capture_run_id,
                    int(sample_index),
                    analysis_unit_key,
                    candidate_snapshot_hash,
                    now,
                    1 if final_callable else 0,
                    final_skip,
                    final_reservation,
                    None,
                    1 if final_callable else 0,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM jev_typesafe_recruitment WHERE id=?",
                (recruitment_id,),
            ).fetchone()
            return dict(row)
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def begin_review(
        self,
        *,
        recruitment_id: str,
        request_id: str,
        state: dict[str, Any],
        protocol: dict[str, Any],
        deadline_at: str | None,
        requested_at: str | None = None,
    ) -> dict[str, Any]:
        spec = dict(protocol["spec"])
        now = requested_at or _now()
        conn = self.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            recruitment = conn.execute(
                "SELECT * FROM jev_typesafe_recruitment WHERE id=?",
                (recruitment_id,),
            ).fetchone()
            if recruitment is None:
                raise TypeSafeJevCatalogError("JEV_TYPESAFE_RECRUITMENT_NOT_FOUND")
            if not bool(recruitment["callable"]):
                raise TypeSafeJevCatalogError("JEV_TYPESAFE_RECRUITMENT_NOT_CALLABLE")
            if recruitment["review_id"]:
                row = conn.execute(
                    "SELECT * FROM jev_typesafe_review WHERE id=?",
                    (recruitment["review_id"],),
                ).fetchone()
                conn.rollback()
                return dict(row)

            review_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO jev_typesafe_review(
                    id,recruitment_id,request_id,protocol_id,
                    state_contract_version,state_hash,state_json,
                    projector_version,projector_hash,
                    question_contract_version,question_set_hash,
                    disposition_policy_version,disposition_policy_hash,
                    provider_id,model_requested,model_returned,
                    model_identity_status,adapter_version,
                    requested_at,completed_at,deadline_at,status,
                    disposition,uncertainty_reason,failure_code,
                    typed_answers_json,raw_response_hash,latency_ms,
                    usage_json,cost_usd,cost_unknown
                ) VALUES(
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    NULL,?,'PENDING',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,1
                )
                """,
                (
                    review_id,
                    recruitment_id,
                    request_id,
                    protocol["id"],
                    spec["state_contract_version"],
                    digest_json(state),
                    canonical_json(state),
                    spec["projector_version"],
                    spec["projector_hash"],
                    spec["question_contract_version"],
                    spec["question_set_hash"],
                    spec["disposition_policy_version"],
                    spec["disposition_policy_hash"],
                    spec["provider_id"],
                    spec["model_requested"],
                    None,
                    "PENDING",
                    spec["adapter_version"],
                    now,
                    deadline_at,
                ),
            )
            conn.execute(
                "UPDATE jev_typesafe_recruitment SET review_id=? WHERE id=?",
                (review_id, recruitment_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM jev_typesafe_review WHERE id=?",
                (review_id,),
            ).fetchone()
            return dict(row)
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def complete_review(
        self,
        review_id: str,
        *,
        status: str,
        disposition: str | None,
        uncertainty_reason: str | None,
        failure_code: str | None,
        model_returned: str | None,
        model_identity_status: str,
        typed_answers: dict[str, Any] | None,
        raw_response_hash: str | None,
        latency_ms: int | None,
        usage: dict[str, Any] | None,
        cost_usd: float | None,
        cost_unknown: bool,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        clean_status = status.strip().upper()
        if clean_status not in JEV_TYPESAFE_TERMINAL_STATUSES:
            raise TypeSafeJevCatalogError("JEV_TYPESAFE_TERMINAL_STATUS_INVALID")
        if clean_status == "VALID":
            if disposition not in JEV_TYPESAFE_DISPOSITIONS:
                raise TypeSafeJevCatalogError("JEV_TYPESAFE_DISPOSITION_INVALID")
        elif disposition is not None:
            raise TypeSafeJevCatalogError(
                "JEV_TYPESAFE_NONVALID_DISPOSITION_FORBIDDEN"
            )
        now = completed_at or _now()
        conn = self.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jev_typesafe_review WHERE id=?",
                (review_id,),
            ).fetchone()
            if row is None:
                raise TypeSafeJevCatalogError("JEV_TYPESAFE_REVIEW_NOT_FOUND")
            if str(row["status"]) != "PENDING":
                raise TypeSafeJevCatalogError("JEV_TYPESAFE_REVIEW_TERMINAL")
            conn.execute(
                """
                UPDATE jev_typesafe_review SET
                    completed_at=?,status=?,disposition=?,
                    uncertainty_reason=?,failure_code=?,
                    model_returned=?,model_identity_status=?,
                    typed_answers_json=?,raw_response_hash=?,latency_ms=?,
                    usage_json=?,cost_usd=?,cost_unknown=?
                WHERE id=?
                """,
                (
                    now,
                    clean_status,
                    disposition,
                    uncertainty_reason,
                    failure_code,
                    model_returned,
                    model_identity_status,
                    canonical_json(typed_answers) if typed_answers is not None else None,
                    raw_response_hash,
                    latency_ms,
                    canonical_json(usage) if usage is not None else None,
                    cost_usd,
                    1 if cost_unknown else 0,
                    review_id,
                ),
            )
            conn.execute(
                """
                UPDATE jev_typesafe_recruitment
                SET known_cost_usd=?,cost_unknown=?
                WHERE id=?
                """,
                (cost_usd, 1 if cost_unknown else 0, row["recruitment_id"]),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM jev_typesafe_review WHERE id=?",
                (review_id,),
            ).fetchone()
            return dict(updated)
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def mark_pending_interrupted(self) -> int:
        with self.connect() as conn:
            self.require_ready(conn)
            result = conn.execute(
                """
                UPDATE jev_typesafe_review
                SET status='INTERRUPTED',completed_at=?,
                    failure_code='PROCESS_RESTARTED',disposition=NULL
                WHERE status='PENDING'
                """,
                (_now(),),
            )
            return int(result.rowcount)
