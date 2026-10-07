from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .typesafe_projection import project_typesafe_review
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

    def find_recruitment_by_analysis_unit_key(
        self,
        analysis_unit_key: str,
    ) -> dict[str, Any] | None:
        key = str(analysis_unit_key or "").strip()
        if not key:
            raise TypeSafeJevCatalogError("JEV_TYPESAFE_ANALYSIS_UNIT_KEY_REQUIRED")
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM jev_typesafe_recruitment
                WHERE analysis_unit_key=?
                ORDER BY recruited_at,id
                LIMIT 1
                """,
                (key,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        clean = str(review_id or "").strip()
        if not clean:
            raise TypeSafeJevCatalogError("JEV_TYPESAFE_REVIEW_ID_REQUIRED")
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM jev_typesafe_review WHERE id=?",
                (clean,),
            ).fetchone()
        return dict(row) if row is not None else None

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
            if str(model_identity_status or "") != "MATCHED":
                raise TypeSafeJevCatalogError("JEV_TYPESAFE_MODEL_IDENTITY_UNVERIFIED")
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


    @staticmethod
    def _monitor_protocol(
        conn: sqlite3.Connection,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        activation_row = conn.execute(
            "SELECT * FROM jev_typesafe_activation WHERE singleton_id=1"
        ).fetchone()
        activation = dict(activation_row) if activation_row is not None else None
        protocol_row = None
        if activation is not None:
            protocol_row = conn.execute(
                "SELECT * FROM jev_typesafe_protocol WHERE id=?",
                (activation["protocol_id"],),
            ).fetchone()
        if protocol_row is None:
            protocol_row = conn.execute(
                """
                SELECT * FROM jev_typesafe_protocol
                ORDER BY created_at DESC,id DESC LIMIT 1
                """
            ).fetchone()
        if protocol_row is None:
            return None, activation
        protocol = {
            **dict(protocol_row),
            "spec": json.loads(str(protocol_row["spec_json"])),
        }
        return protocol, activation

    @staticmethod
    def _monitor_review(row: sqlite3.Row) -> dict[str, Any] | None:
        if row["review_id"] is None:
            return None
        return {
            "id": row["review_id"],
            "status": row["review_status"],
            "disposition": row["review_disposition"],
            "uncertainty_reason": row["review_uncertainty_reason"],
            "failure_code": row["review_failure_code"],
            "model_identity_status": row["model_identity_status"],
            "provider_id": row["provider_id"],
            "model_requested": row["model_requested"],
            "model_returned": row["model_returned"],
            "state_contract_version": row["state_contract_version"],
            "projector_version": row["projector_version"],
            "projector_hash": row["projector_hash"],
            "question_contract_version": row["question_contract_version"],
            "question_set_hash": row["question_set_hash"],
            "disposition_policy_version": row["disposition_policy_version"],
            "disposition_policy_hash": row["disposition_policy_hash"],
            "adapter_version": row["adapter_version"],
            "typed_answers": (
                json.loads(str(row["typed_answers_json"]))
                if row["typed_answers_json"]
                else None
            ),
            "latency_ms": row["latency_ms"],
            "completed_at": row["completed_at"],
            "cost_usd": row["cost_usd"],
            "cost_unknown": row["review_cost_unknown"],
        }

    def monitor_status(self) -> dict[str, Any]:
        with self.connect() as conn:
            self.require_ready(conn)
            protocol, activation = self._monitor_protocol(conn)
            if protocol is None:
                return {
                    "available": True,
                    "engine": "TYPESAFE_V2",
                    "core_status": "CORE_READY",
                    "trial_status": "TRIAL_NOT_FROZEN",
                    "enabled": False,
                    "network_enabled": False,
                    "protocol_id": None,
                    "protocol_status": None,
                    "recruitment": {"total": 0, "callable": 0, "skipped": 0},
                    "review_status": {
                        "pending": 0,
                        "valid": 0,
                        "error": 0,
                        "late": 0,
                        "interrupted": 0,
                    },
                    "disposition": {
                        "pass_through": 0,
                        "review_required": 0,
                        "abstain": 0,
                    },
                    "cost": {
                        "known_cost_usd": 0.0,
                        "unknown_cost_count": 0,
                        "reserved_exposure_usd": 0.0,
                    },
                }

            rows = conn.execute(
                """
                SELECT
                    r.id AS recruitment_id,r.callable,r.skip_reason,
                    r.reserved_cost_usd,r.known_cost_usd,
                    r.cost_unknown AS recruitment_cost_unknown,
                    r.review_id,
                    v.status AS review_status,
                    v.disposition AS review_disposition,
                    v.uncertainty_reason AS review_uncertainty_reason,
                    v.failure_code AS review_failure_code,
                    v.model_identity_status,
                    v.provider_id,v.model_requested,v.model_returned,
                    v.state_contract_version,v.projector_version,v.projector_hash,
                    v.question_contract_version,v.question_set_hash,
                    v.disposition_policy_version,v.disposition_policy_hash,
                    v.adapter_version,v.typed_answers_json,v.latency_ms,
                    v.completed_at,v.cost_usd,
                    v.cost_unknown AS review_cost_unknown
                FROM jev_typesafe_recruitment r
                LEFT JOIN jev_typesafe_review v ON v.id=r.review_id
                WHERE r.protocol_id=?
                ORDER BY r.recruited_at,r.id
                """,
                (protocol["id"],),
            ).fetchall()

        recruitment_total = len(rows)
        callable_count = sum(1 for row in rows if bool(row["callable"]))
        skipped_count = recruitment_total - callable_count
        status_counts = {
            "PENDING": 0,
            "VALID": 0,
            "ERROR": 0,
            "LATE": 0,
            "INTERRUPTED": 0,
        }
        disposition_counts = {
            "PASS_THROUGH": 0,
            "REVIEW_REQUIRED": 0,
            "ABSTAIN": 0,
        }
        for row in rows:
            if not bool(row["callable"]):
                continue
            review = self._monitor_review(row)
            if review is None:
                status_counts["PENDING"] += 1
                continue
            projected = project_typesafe_review(review, dict(protocol["spec"]))
            status = projected.operational_status
            if status in status_counts:
                status_counts[status] += 1
            if status == "VALID" and projected.disposition in disposition_counts:
                disposition_counts[str(projected.disposition)] += 1

        enabled = bool(
            activation is not None
            and activation.get("protocol_id") == protocol["id"]
            and activation.get("enabled")
        )
        network_enabled = bool(
            enabled and activation is not None and activation.get("allow_network")
        )
        if str(protocol.get("status") or "") != "FROZEN":
            trial_status = "TRIAL_NOT_FROZEN"
        elif enabled and network_enabled:
            trial_status = "ACTIVE"
        elif enabled:
            trial_status = "FAKE_ACTIVE"
        else:
            trial_status = "FROZEN_NOT_ACTIVE"

        known_cost = sum(
            float(row["known_cost_usd"])
            for row in rows
            if row["known_cost_usd"] is not None
        )
        unknown_cost_count = sum(
            1 for row in rows
            if bool(row["callable"]) and bool(row["recruitment_cost_unknown"])
        )
        reserved_exposure = sum(
            float(row["reserved_cost_usd"] or 0.0)
            for row in rows
            if bool(row["callable"]) and bool(row["recruitment_cost_unknown"])
        )
        return {
            "available": True,
            "engine": "TYPESAFE_V2",
            "core_status": "CORE_READY",
            "trial_status": trial_status,
            "enabled": enabled,
            "network_enabled": network_enabled,
            "protocol_id": protocol["id"],
            "protocol_status": protocol["status"],
            "recruitment": {
                "total": recruitment_total,
                "callable": callable_count,
                "skipped": skipped_count,
            },
            "review_status": {
                "pending": status_counts["PENDING"],
                "valid": status_counts["VALID"],
                "error": status_counts["ERROR"],
                "late": status_counts["LATE"],
                "interrupted": status_counts["INTERRUPTED"],
            },
            "disposition": {
                "pass_through": disposition_counts["PASS_THROUGH"],
                "review_required": disposition_counts["REVIEW_REQUIRED"],
                "abstain": disposition_counts["ABSTAIN"],
            },
            "cost": {
                "known_cost_usd": known_cost,
                "unknown_cost_count": unknown_cost_count,
                "reserved_exposure_usd": reserved_exposure,
            },
        }

    def list_monitor_items(self, capture_run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self.require_ready(conn)
            protocol, _ = self._monitor_protocol(conn)
            if protocol is None:
                return []
            rows = conn.execute(
                """
                SELECT
                    r.id AS recruitment_id,r.capture_run_id,r.sample_index,
                    r.callable,r.skip_reason,r.review_id,
                    v.status AS review_status,
                    v.disposition AS review_disposition,
                    v.uncertainty_reason AS review_uncertainty_reason,
                    v.failure_code AS review_failure_code,
                    v.model_identity_status,
                    v.provider_id,v.model_requested,v.model_returned,
                    v.state_contract_version,v.projector_version,v.projector_hash,
                    v.question_contract_version,v.question_set_hash,
                    v.disposition_policy_version,v.disposition_policy_hash,
                    v.adapter_version,v.typed_answers_json,v.latency_ms,
                    v.completed_at,v.cost_usd,
                    v.cost_unknown AS review_cost_unknown,
                    s.market,s.ticker,s.name
                FROM jev_typesafe_recruitment r
                JOIN prospective_recommendation_sample s
                  ON s.capture_run_id=r.capture_run_id
                 AND s.sample_index=r.sample_index
                LEFT JOIN jev_typesafe_review v ON v.id=r.review_id
                WHERE r.protocol_id=? AND r.capture_run_id=?
                ORDER BY r.sample_index,r.recruited_at,r.id
                """,
                (protocol["id"], capture_run_id),
            ).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            review = self._monitor_review(row)
            if not bool(row["callable"]):
                operational_status = "SKIPPED"
                disposition = None
                reason_codes: list[str] = []
                uncertainty_reason = None
                failure_code = None
                integrity_status = "NOT_APPLICABLE"
            elif review is None:
                operational_status = "PENDING"
                disposition = None
                reason_codes = []
                uncertainty_reason = None
                failure_code = None
                integrity_status = "NOT_APPLICABLE"
            else:
                projected = project_typesafe_review(review, dict(protocol["spec"]))
                operational_status = projected.operational_status
                disposition = projected.disposition
                reason_codes = list(projected.reason_codes)
                uncertainty_reason = projected.uncertainty_reason
                failure_code = projected.failure_code
                integrity_status = projected.integrity_status

            items.append(
                {
                    "capture_id": str(row["capture_run_id"]),
                    "sample_index": int(row["sample_index"]),
                    "market": str(row["market"] or ""),
                    "ticker": str(row["ticker"] or ""),
                    "name": str(row["name"] or ""),
                    "recruitment_id": str(row["recruitment_id"]),
                    "review_id": (
                        str(row["review_id"]) if row["review_id"] is not None else None
                    ),
                    "callable": bool(row["callable"]),
                    "skip_reason": (
                        str(row["skip_reason"])
                        if row["skip_reason"] is not None
                        else None
                    ),
                    "operational_status": operational_status,
                    "disposition": disposition,
                    "uncertainty_reason": uncertainty_reason,
                    "failure_code": failure_code,
                    "integrity_status": integrity_status,
                    "model_identity_status": (
                        str(row["model_identity_status"])
                        if row["model_identity_status"] is not None
                        else None
                    ),
                    "completed_at": (
                        str(row["completed_at"])
                        if row["completed_at"] is not None
                        else None
                    ),
                    "latency_ms": (
                        int(row["latency_ms"])
                        if row["latency_ms"] is not None
                        else None
                    ),
                    "reason_codes": reason_codes,
                }
            )
        return items
