from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import (
    FEEDBACK_ADAPTER_VERSION,
    FEEDBACK_COHORT_VERSION,
    FEEDBACK_REPORT_VERSION,
    FEEDBACK_SCHEMA_VERSION,
    FeedbackEvidence,
    canonical_json,
    digest_json,
)


class FeedbackCatalogError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class FeedbackCatalog:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _table_names(conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {str(row["name"]) for row in rows}

    def require_ready(self, conn: sqlite3.Connection | None = None) -> None:
        owns = conn is None
        active = conn or self.connect()
        try:
            required = {
                "feedback_schema_meta",
                "feedback_source_ref",
                "feedback_cohort",
                "feedback_cohort_source",
                "feedback_cohort_member",
                "feedback_report",
            }
            if not required.issubset(self._table_names(active)):
                raise FeedbackCatalogError(
                    "FEEDBACK_MIGRATION_REQUIRED",
                    "VN-P2-S1 Feedback migration을 먼저 실행해야 합니다.",
                )
            row = active.execute(
                "SELECT value FROM feedback_schema_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None or str(row["value"]) != FEEDBACK_SCHEMA_VERSION:
                raise FeedbackCatalogError(
                    "FEEDBACK_SCHEMA_UNSUPPORTED",
                    "지원하지 않는 Feedback schema version입니다.",
                )
        finally:
            if owns:
                active.close()

    @staticmethod
    def _source_ref_payload(row: sqlite3.Row) -> dict[str, Any]:
        evidence = json.loads(str(row["evidence_json"]))
        return {
            "id": row["id"],
            "adapter_version": row["adapter_version"],
            "source_type": row["source_type"],
            "source_owner": row["source_owner"],
            "source_id": row["source_id"],
            "source_item_id": row["source_item_id"],
            "source_hash": row["source_hash"],
            "durability": row["durability"],
            "origin_kind": row["origin_kind"],
            "comparison_key": row["comparison_key"],
            "comparison_dimensions": json.loads(str(row["comparison_json"])),
            "evidence": evidence,
            "source_observed_at": row["source_observed_at"],
            "created_at": row["created_at"],
        }

    def _upsert_source_ref(
        self,
        conn: sqlite3.Connection,
        evidence: FeedbackEvidence,
        *,
        created_at: str,
    ) -> str:
        existing = conn.execute(
            """
            SELECT id FROM feedback_source_ref
            WHERE source_type=? AND source_id=? AND source_item_id=? AND source_hash=?
            LIMIT 1
            """,
            (
                evidence.source_type,
                evidence.source_id,
                evidence.source_item_id,
                evidence.source_hash,
            ),
        ).fetchone()
        if existing is not None:
            return str(existing["id"])
        ref_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO feedback_source_ref(
                id,adapter_version,source_type,source_owner,source_id,source_item_id,
                source_hash,durability,origin_kind,comparison_key,comparison_json,
                evidence_json,source_observed_at,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ref_id,
                FEEDBACK_ADAPTER_VERSION,
                evidence.source_type,
                evidence.source_owner,
                evidence.source_id,
                evidence.source_item_id,
                evidence.source_hash,
                evidence.durability,
                evidence.origin_kind,
                evidence.comparison_key,
                canonical_json(evidence.comparison_dimensions()),
                canonical_json(evidence.to_dict()),
                evidence.source_observed_at,
                created_at,
            ),
        )
        return ref_id

    def create_cohort(
        self,
        *,
        client_request_id: str,
        name: str,
        filters: dict[str, Any],
        selector_results: list[dict[str, Any]],
        evidence: list[FeedbackEvidence],
        created_at: str,
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id FROM feedback_cohort WHERE client_request_id=?",
                (client_request_id,),
            ).fetchone()
            if existing is not None:
                conn.rollback()
                return self.get_cohort(str(existing["id"]))

            cohort_id = str(uuid4())
            status = "READY" if evidence else "EMPTY"
            conn.execute(
                """
                INSERT INTO feedback_cohort(
                    id,client_request_id,name,cohort_version,filter_json,status,created_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    cohort_id,
                    client_request_id,
                    name,
                    FEEDBACK_COHORT_VERSION,
                    canonical_json(filters),
                    status,
                    created_at,
                ),
            )
            for index, source in enumerate(selector_results):
                conn.execute(
                    """
                    INSERT INTO feedback_cohort_source(
                        cohort_id,source_order,source_type,source_id,selector_json,
                        status,error_code,error_message,evidence_count,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        cohort_id,
                        index,
                        source["source_type"],
                        source["source_id"],
                        canonical_json(source["selector"]),
                        source["status"],
                        source.get("error_code"),
                        source.get("error_message"),
                        int(source.get("evidence_count") or 0),
                        created_at,
                    ),
                )

            seen_refs: set[str] = set()
            for item in evidence:
                ref_id = self._upsert_source_ref(conn, item, created_at=created_at)
                if ref_id in seen_refs:
                    continue
                seen_refs.add(ref_id)
                conn.execute(
                    """
                    INSERT INTO feedback_cohort_member(
                        cohort_id,source_ref_id,inclusion_status,exclusion_reason,created_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (
                        cohort_id,
                        ref_id,
                        item.inclusion_status,
                        item.exclusion_reason,
                        created_at,
                    ),
                )
            conn.commit()
            return self.get_cohort(cohort_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_cohort(self, cohort_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM feedback_cohort WHERE id=?",
                (cohort_id,),
            ).fetchone()
            if row is None:
                raise FeedbackCatalogError(
                    "FEEDBACK_COHORT_NOT_FOUND",
                    "평가 cohort를 찾을 수 없습니다.",
                )
            source_rows = conn.execute(
                """
                SELECT * FROM feedback_cohort_source
                WHERE cohort_id=?
                ORDER BY source_order
                """,
                (cohort_id,),
            ).fetchall()
            member_rows = conn.execute(
                """
                SELECT m.inclusion_status,m.exclusion_reason,r.*
                FROM feedback_cohort_member m
                JOIN feedback_source_ref r ON r.id=m.source_ref_id
                WHERE m.cohort_id=?
                ORDER BY r.source_type,r.source_id,r.source_item_id
                """,
                (cohort_id,),
            ).fetchall()
        members = []
        for item in member_rows:
            payload = self._source_ref_payload(item)
            payload["inclusion_status"] = item["inclusion_status"]
            payload["exclusion_reason"] = item["exclusion_reason"]
            members.append(payload)
        return {
            "id": row["id"],
            "client_request_id": row["client_request_id"],
            "name": row["name"],
            "cohort_version": row["cohort_version"],
            "filters": json.loads(str(row["filter_json"])),
            "status": row["status"],
            "created_at": row["created_at"],
            "sources": [
                {
                    "source_order": int(item["source_order"]),
                    "source_type": item["source_type"],
                    "source_id": item["source_id"],
                    "selector": json.loads(str(item["selector_json"])),
                    "status": item["status"],
                    "error_code": item["error_code"],
                    "error_message": item["error_message"],
                    "evidence_count": int(item["evidence_count"] or 0),
                }
                for item in source_rows
            ],
            "members": members,
        }

    def list_cohorts(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                """
                SELECT c.*,
                       COUNT(m.source_ref_id) AS member_count,
                       SUM(CASE WHEN m.inclusion_status='INCLUDED' THEN 1 ELSE 0 END) AS included_count
                FROM feedback_cohort c
                LEFT JOIN feedback_cohort_member m ON m.cohort_id=c.id
                GROUP BY c.id
                ORDER BY c.created_at DESC,c.id DESC
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "client_request_id": row["client_request_id"],
                "name": row["name"],
                "cohort_version": row["cohort_version"],
                "filters": json.loads(str(row["filter_json"])),
                "status": row["status"],
                "member_count": int(row["member_count"] or 0),
                "included_count": int(row["included_count"] or 0),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def create_report(
        self,
        *,
        cohort_id: str,
        client_request_id: str,
        summary: dict[str, Any],
        source_set_hash: str,
        status: str,
        created_at: str,
    ) -> dict[str, Any]:
        conn = self.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id FROM feedback_report WHERE client_request_id=?",
                (client_request_id,),
            ).fetchone()
            if existing is not None:
                conn.rollback()
                return self.get_report(str(existing["id"]))
            cohort = conn.execute(
                "SELECT id FROM feedback_cohort WHERE id=?",
                (cohort_id,),
            ).fetchone()
            if cohort is None:
                raise FeedbackCatalogError(
                    "FEEDBACK_COHORT_NOT_FOUND",
                    "평가 cohort를 찾을 수 없습니다.",
                )
            next_version = int(
                conn.execute(
                    "SELECT COALESCE(MAX(report_sequence),0)+1 AS n FROM feedback_report WHERE cohort_id=?",
                    (cohort_id,),
                ).fetchone()["n"]
            )
            report_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO feedback_report(
                    id,cohort_id,client_request_id,report_version,report_sequence,
                    source_set_hash,status,summary_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    report_id,
                    cohort_id,
                    client_request_id,
                    FEEDBACK_REPORT_VERSION,
                    next_version,
                    source_set_hash,
                    status,
                    canonical_json(summary),
                    created_at,
                ),
            )
            conn.commit()
            return self.get_report(report_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_report(self, report_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM feedback_report WHERE id=?",
                (report_id,),
            ).fetchone()
        if row is None:
            raise FeedbackCatalogError(
                "FEEDBACK_REPORT_NOT_FOUND",
                "평가 보고서를 찾을 수 없습니다.",
            )
        return {
            "id": row["id"],
            "cohort_id": row["cohort_id"],
            "client_request_id": row["client_request_id"],
            "report_version": row["report_version"],
            "report_sequence": int(row["report_sequence"]),
            "source_set_hash": row["source_set_hash"],
            "status": row["status"],
            "summary": json.loads(str(row["summary_json"])),
            "created_at": row["created_at"],
        }

    def list_reports(self, cohort_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self.require_ready(conn)
            rows = conn.execute(
                """
                SELECT * FROM feedback_report
                WHERE cohort_id=?
                ORDER BY report_sequence DESC
                """,
                (cohort_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "cohort_id": row["cohort_id"],
                "client_request_id": row["client_request_id"],
                "report_version": row["report_version"],
                "report_sequence": int(row["report_sequence"]),
                "source_set_hash": row["source_set_hash"],
                "status": row["status"],
                "summary": json.loads(str(row["summary_json"])),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def source_set_hash(self, cohort_id: str) -> str:
        cohort = self.get_cohort(cohort_id)
        refs = [
            {
                "source_type": item["source_type"],
                "source_id": item["source_id"],
                "source_item_id": item["source_item_id"],
                "source_hash": item["source_hash"],
                "inclusion_status": item["inclusion_status"],
                "exclusion_reason": item["exclusion_reason"],
            }
            for item in cohort["members"]
        ]
        return digest_json(refs)
