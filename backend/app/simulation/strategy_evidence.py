from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from app.feedback import FEEDBACK_REPORT_VERSION, FeedbackService
from app.feedback.adapter import DEFAULT_TRACKING_DB
from app.prospective.models import (
    PROSPECTIVE_EVALUATION_VERSION,
    PROSPECTIVE_PROTOCOL_VERSION,
    PROSPECTIVE_REPORT_VERSION,
    digest_json as prospective_digest_json,
)

STRATEGY_EVALUATION_ARTIFACT_VERSION = "VN_P5_S1_STRATEGY_EVIDENCE_V1"

SOURCE_FEEDBACK_REPORT = "FEEDBACK_REPORT"
SOURCE_PROSPECTIVE_REPORT = "PROSPECTIVE_REPORT"
SUPPORTED_SOURCE_KINDS = frozenset(
    {SOURCE_FEEDBACK_REPORT, SOURCE_PROSPECTIVE_REPORT}
)


class StrategyEvidenceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class StrategyEvidenceService:
    """
    Bind existing P2 evaluation evidence to an immutable Strategy Version.

    This service never changes Strategy Registry status and never publishes a
    Production Selection Policy. It only records what evidence was reviewed.
    """

    def __init__(
        self,
        simulation_db: Path,
        *,
        tracking_db: Path | None = None,
        feedback_service: FeedbackService | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.simulation_db = Path(simulation_db)
        self.tracking_db = Path(tracking_db or DEFAULT_TRACKING_DB)
        self._feedback_service = feedback_service
        self.clock = clock or _now

    def _connect(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise StrategyEvidenceError(
                "STRATEGY_GOVERNANCE_STORE_NOT_FOUND",
                f"Simulation DB를 찾을 수 없습니다: {self.simulation_db}",
            )
        conn = sqlite3.connect(self.simulation_db, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _tables(conn: sqlite3.Connection) -> set[str]:
        return {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    def _require_ready(self, conn: sqlite3.Connection) -> None:
        required = {
            "strategy_registry_version",
            "strategy_evaluation_artifact",
            "prospective_evaluation_report",
            "prospective_evaluation_run",
            "prospective_evaluation_protocol",
            "feedback_report",
        }
        missing = sorted(required - self._tables(conn))
        if missing:
            raise StrategyEvidenceError(
                "STRATEGY_EVIDENCE_MIGRATION_REQUIRED",
                "P5-S1 Strategy Evidence schema가 준비되지 않았습니다: "
                + ", ".join(missing),
            )

    @staticmethod
    def _strategy_row(
        conn: sqlite3.Connection,
        strategy_version_id: str,
    ) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT * FROM strategy_registry_version
            WHERE strategy_version_id=?
            """,
            (strategy_version_id,),
        ).fetchone()
        if row is None:
            raise StrategyEvidenceError(
                "STRATEGY_VERSION_NOT_FOUND",
                "Strategy Version을 찾을 수 없습니다.",
            )
        if str(row["strategy_key"]) == "no_trade":
            raise StrategyEvidenceError(
                "NO_TRADE_NOT_STRATEGY",
                "NO_TRADE는 Strategy Evaluation Artifact 대상이 아닙니다.",
            )
        return row

    @staticmethod
    def _artifact_id(
        *,
        strategy_version_id: str,
        source_kind: str,
        source_report_id: str,
        source_set_hash: str,
    ) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                (
                    "stockscope:strategy-evidence:"
                    f"{STRATEGY_EVALUATION_ARTIFACT_VERSION}:"
                    f"{strategy_version_id}:{source_kind}:"
                    f"{source_report_id}:{source_set_hash}"
                ),
            )
        )

    @staticmethod
    def _artifact_payload(
        *,
        strategy_version_id: str,
        strategy_key: str,
        source_kind: str,
        source_report_id: str,
        source_report_version: str,
        source_parent_id: str,
        source_set_hash: str,
        source_summary_hash: str,
        evidence_state: str,
        evidence: dict[str, Any],
        limitations: dict[str, Any],
        source_contract: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "artifact_version": STRATEGY_EVALUATION_ARTIFACT_VERSION,
            "strategy_version_id": strategy_version_id,
            "strategy_key": strategy_key,
            "source_kind": source_kind,
            "source_report_id": source_report_id,
            "source_report_version": source_report_version,
            "source_parent_id": source_parent_id,
            "source_set_hash": source_set_hash,
            "source_summary_hash": source_summary_hash,
            "evidence_state": evidence_state,
            "evidence": evidence,
            "limitations": limitations,
            "source_contract": source_contract,
        }

    @staticmethod
    def _row_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "artifact_version": str(row["artifact_version"]),
            "strategy_version_id": str(row["strategy_version_id"]),
            "strategy_key": str(row["strategy_key"]),
            "source_kind": str(row["source_kind"]),
            "source_report_id": str(row["source_report_id"]),
            "source_report_version": str(row["source_report_version"]),
            "source_parent_id": str(row["source_parent_id"]),
            "source_set_hash": str(row["source_set_hash"]),
            "source_summary_hash": str(row["source_summary_hash"]),
            "evidence_state": str(row["evidence_state"]),
            "evidence": json.loads(str(row["evidence_json"])),
            "limitations": json.loads(str(row["limitations_json"])),
            "source_contract": json.loads(str(row["source_contract_json"])),
            "artifact_hash": str(row["artifact_hash"]),
            "created_at": str(row["created_at"]),
        }

    def _insert_artifact(
        self,
        conn: sqlite3.Connection,
        *,
        strategy_version_id: str,
        strategy_key: str,
        source_kind: str,
        source_report_id: str,
        source_report_version: str,
        source_parent_id: str,
        source_set_hash: str,
        source_summary_hash: str,
        evidence_state: str,
        evidence: dict[str, Any],
        limitations: dict[str, Any],
        source_contract: dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._artifact_payload(
            strategy_version_id=strategy_version_id,
            strategy_key=strategy_key,
            source_kind=source_kind,
            source_report_id=source_report_id,
            source_report_version=source_report_version,
            source_parent_id=source_parent_id,
            source_set_hash=source_set_hash,
            source_summary_hash=source_summary_hash,
            evidence_state=evidence_state,
            evidence=evidence,
            limitations=limitations,
            source_contract=source_contract,
        )
        artifact_hash = _digest(payload)
        artifact_id = self._artifact_id(
            strategy_version_id=strategy_version_id,
            source_kind=source_kind,
            source_report_id=source_report_id,
            source_set_hash=source_set_hash,
        )
        existing = conn.execute(
            """
            SELECT * FROM strategy_evaluation_artifact
            WHERE id=?
            """,
            (artifact_id,),
        ).fetchone()
        if existing is not None:
            if str(existing["artifact_hash"]) != artifact_hash:
                raise StrategyEvidenceError(
                    "STRATEGY_EVIDENCE_IDENTITY_CONFLICT",
                    "동일 Evidence identity에 다른 Artifact payload가 존재합니다.",
                )
            return self._row_payload(existing)

        conn.execute(
            """
            INSERT INTO strategy_evaluation_artifact(
                id,strategy_version_id,strategy_key,artifact_version,
                source_kind,source_report_id,source_report_version,
                source_parent_id,source_set_hash,source_summary_hash,
                evidence_state,evidence_json,limitations_json,
                source_contract_json,artifact_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                artifact_id,
                strategy_version_id,
                strategy_key,
                STRATEGY_EVALUATION_ARTIFACT_VERSION,
                source_kind,
                source_report_id,
                source_report_version,
                source_parent_id,
                source_set_hash,
                source_summary_hash,
                evidence_state,
                _canonical_json(evidence),
                _canonical_json(limitations),
                _canonical_json(source_contract),
                artifact_hash,
                self.clock(),
            ),
        )
        row = conn.execute(
            "SELECT * FROM strategy_evaluation_artifact WHERE id=?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            raise StrategyEvidenceError(
                "STRATEGY_EVIDENCE_INSERT_FAILED",
                "Strategy Evaluation Artifact 저장에 실패했습니다.",
            )
        return self._row_payload(row)

    def create_from_prospective(
        self,
        *,
        strategy_version_id: str,
        report_id: str,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            strategy = self._strategy_row(conn, strategy_version_id)
            report = conn.execute(
                """
                SELECT * FROM prospective_evaluation_report
                WHERE id=?
                """,
                (report_id,),
            ).fetchone()
            if report is None:
                raise StrategyEvidenceError(
                    "PROSPECTIVE_REPORT_NOT_FOUND",
                    "Prospective Evaluation Report를 찾을 수 없습니다.",
                )
            run = conn.execute(
                """
                SELECT * FROM prospective_evaluation_run
                WHERE id=?
                """,
                (str(report["evaluation_run_id"]),),
            ).fetchone()
            if run is None or str(run["status"]) != "COMPLETED":
                raise StrategyEvidenceError(
                    "PROSPECTIVE_RUN_NOT_COMPLETED",
                    "COMPLETED Prospective Evaluation Run만 근거로 연결할 수 있습니다.",
                )
            protocol = conn.execute(
                """
                SELECT * FROM prospective_evaluation_protocol
                WHERE id=?
                """,
                (str(run["protocol_id"]),),
            ).fetchone()
            if protocol is None:
                raise StrategyEvidenceError(
                    "PROSPECTIVE_PROTOCOL_NOT_FOUND",
                    "Prospective Evaluation Protocol을 찾을 수 없습니다.",
                )
            if str(run["evaluation_version"]) != PROSPECTIVE_EVALUATION_VERSION:
                raise StrategyEvidenceError(
                    "PROSPECTIVE_EVALUATION_VERSION_UNSUPPORTED",
                    "지원하지 않는 Prospective evaluation version입니다.",
                )
            if str(report["report_version"]) != PROSPECTIVE_REPORT_VERSION:
                raise StrategyEvidenceError(
                    "PROSPECTIVE_REPORT_VERSION_UNSUPPORTED",
                    "지원하지 않는 Prospective report version입니다.",
                )
            if str(protocol["protocol_version"]) != PROSPECTIVE_PROTOCOL_VERSION:
                raise StrategyEvidenceError(
                    "PROSPECTIVE_PROTOCOL_VERSION_UNSUPPORTED",
                    "지원하지 않는 Prospective protocol version입니다.",
                )

            protocol_spec = json.loads(str(protocol["spec_json"]))
            protocol_spec_hash = prospective_digest_json(protocol_spec)
            if protocol_spec_hash != str(protocol["spec_hash"]):
                raise StrategyEvidenceError(
                    "PROSPECTIVE_PROTOCOL_HASH_MISMATCH",
                    "Prospective protocol spec hash가 현재 내용과 일치하지 않습니다.",
                )

            summary = json.loads(str(report["summary_json"]))
            if str(summary.get("protocol_id") or "") != str(protocol["id"]):
                raise StrategyEvidenceError(
                    "PROSPECTIVE_PROTOCOL_LINK_MISMATCH",
                    "Prospective report의 protocol 연결이 일치하지 않습니다.",
                )
            if str(summary.get("protocol_version") or "") != str(
                protocol["protocol_version"]
            ):
                raise StrategyEvidenceError(
                    "PROSPECTIVE_PROTOCOL_LINK_MISMATCH",
                    "Prospective report의 protocol version이 일치하지 않습니다.",
                )
            if str(summary.get("protocol_spec_hash") or "") != str(
                protocol["spec_hash"]
            ):
                raise StrategyEvidenceError(
                    "PROSPECTIVE_PROTOCOL_LINK_MISMATCH",
                    "Prospective report의 protocol hash가 일치하지 않습니다.",
                )

            strategy_key = str(strategy["strategy_key"])
            breakdown = summary.get("strategy_breakdown")
            rows = breakdown if isinstance(breakdown, list) else []
            strategy_rows = [
                item
                for item in rows
                if isinstance(item, dict)
                and str(item.get("strategy") or "") == strategy_key
            ]
            if len(strategy_rows) != 1:
                raise StrategyEvidenceError(
                    "PROSPECTIVE_STRATEGY_EVIDENCE_MISSING",
                    "Prospective report에 해당 Strategy의 단일 breakdown이 없습니다.",
                )

            restrictions = {
                "minimum_sample_policy_defined": bool(
                    summary.get("minimum_sample_policy_defined", False)
                ),
                "performance_conclusion_allowed": bool(
                    summary.get("performance_conclusion_allowed", False)
                ),
                "strategy_promotion_allowed": bool(
                    summary.get("strategy_promotion_allowed", False)
                ),
                "adaptive_rotation_enabled": bool(
                    summary.get("adaptive_rotation_enabled", False)
                ),
            }
            if (
                restrictions["performance_conclusion_allowed"]
                or restrictions["strategy_promotion_allowed"]
                or restrictions["adaptive_rotation_enabled"]
            ):
                raise StrategyEvidenceError(
                    "PROSPECTIVE_PROMOTION_GUARD_VIOLATION",
                    "P2-S2 report가 허용하지 않은 성능 결론/승격 상태를 포함합니다.",
                )

            source_set_hash = str(report["source_set_hash"] or "")
            if not source_set_hash:
                raise StrategyEvidenceError(
                    "PROSPECTIVE_SOURCE_HASH_MISSING",
                    "Prospective Report source_set_hash가 없습니다.",
                )

            evidence = {
                "strategy_breakdown": strategy_rows[0],
                "counts": summary.get("counts") or {},
                "split_counts": summary.get("split_counts") or {},
                "maturity_counts": summary.get("maturity_counts") or {},
                "execution_counts": summary.get("execution_counts") or {},
                "market_counts": summary.get("market_counts") or {},
            }
            limitations = {
                **restrictions,
                "notes": list(summary.get("notes") or []),
                "censored_is_realized_return": bool(
                    (summary.get("virtual_execution") or {}).get(
                        "censored_is_realized_return",
                        False,
                    )
                ),
            }
            source_contract = {
                "protocol_id": str(protocol["id"]),
                "protocol_version": str(protocol["protocol_version"]),
                "protocol_spec_hash": str(protocol["spec_hash"]),
                "evaluation_run_id": str(run["id"]),
                "evaluation_version": str(run["evaluation_version"]),
                "run_status": str(run["status"]),
                "cross_report_aggregation_performed": False,
            }
            return self._insert_artifact(
                conn,
                strategy_version_id=strategy_version_id,
                strategy_key=strategy_key,
                source_kind=SOURCE_PROSPECTIVE_REPORT,
                source_report_id=str(report["id"]),
                source_report_version=str(report["report_version"]),
                source_parent_id=str(report["evaluation_run_id"]),
                source_set_hash=source_set_hash,
                source_summary_hash=_digest(summary),
                evidence_state=str(
                    summary.get("evidence_state")
                    or "INSUFFICIENT_EVIDENCE"
                ),
                evidence=evidence,
                limitations=limitations,
                source_contract=source_contract,
            )

    def _feedback(self) -> FeedbackService:
        if self._feedback_service is not None:
            return self._feedback_service
        return FeedbackService(
            self.simulation_db,
            self.tracking_db,
        )

    def create_from_feedback(
        self,
        *,
        strategy_version_id: str,
        report_id: str,
    ) -> dict[str, Any]:
        feedback = self._feedback()
        try:
            report = feedback.get_report(report_id)
        except Exception as exc:
            raise StrategyEvidenceError(
                "FEEDBACK_REPORT_NOT_AVAILABLE",
                f"Feedback Report를 읽을 수 없습니다: {exc}",
            ) from exc

        if str(report.get("report_version") or "") != FEEDBACK_REPORT_VERSION:
            raise StrategyEvidenceError(
                "FEEDBACK_REPORT_VERSION_UNSUPPORTED",
                "지원하지 않는 Feedback report version입니다.",
            )

        current = report.get("source_verification_current") or {}
        if (
            str(current.get("status") or "") != "MATCH"
            or bool(report.get("source_changed_or_missing"))
            or str(report.get("effective_status") or "") != "READY"
        ):
            raise StrategyEvidenceError(
                "FEEDBACK_SOURCE_INVALID",
                "원본이 변경되거나 누락된 Feedback Report는 새 Artifact로 등록할 수 없습니다.",
            )

        with self._connect() as conn:
            self._require_ready(conn)
            strategy = self._strategy_row(conn, strategy_version_id)
            strategy_key = str(strategy["strategy_key"])
            summary = report.get("summary")
            if not isinstance(summary, dict):
                raise StrategyEvidenceError(
                    "FEEDBACK_SUMMARY_INVALID",
                    "Feedback Report summary가 올바르지 않습니다.",
                )

            comparison = summary.get("comparison")
            groups = (
                comparison.get("groups")
                if isinstance(comparison, dict)
                else None
            )
            group_rows = groups if isinstance(groups, list) else []
            matching = [
                item
                for item in group_rows
                if isinstance(item, dict)
                and str(
                    (item.get("comparison_dimensions") or {}).get("strategy")
                    or ""
                )
                == strategy_key
            ]
            if not matching:
                raise StrategyEvidenceError(
                    "FEEDBACK_STRATEGY_EVIDENCE_MISSING",
                    "Feedback Report에 해당 Strategy 비교 그룹이 없습니다.",
                )

            if bool(
                (comparison or {}).get(
                    "cross_group_aggregation_allowed",
                    False,
                )
            ):
                raise StrategyEvidenceError(
                    "FEEDBACK_CROSS_GROUP_AGGREGATION_FORBIDDEN",
                    "서로 다른 Feedback comparison group은 P5에서 합산할 수 없습니다.",
                )

            if bool(summary.get("performance_conclusion_allowed", False)):
                raise StrategyEvidenceError(
                    "FEEDBACK_PROMOTION_GUARD_VIOLATION",
                    "P2-S1 Feedback은 P5 승격 결론을 직접 허용할 수 없습니다.",
                )

            source_set_hash = str(report.get("source_set_hash") or "")
            if not source_set_hash:
                raise StrategyEvidenceError(
                    "FEEDBACK_SOURCE_HASH_MISSING",
                    "Feedback Report source_set_hash가 없습니다.",
                )

            evidence = {
                "comparison_groups": matching,
                "counts": summary.get("counts") or {},
                "source_types": summary.get("source_types") or {},
                "maturity": summary.get("maturity") or {},
                "exclusion_reasons": summary.get("exclusion_reasons") or {},
            }
            limitations = {
                "minimum_sample_policy_defined": bool(
                    summary.get("minimum_sample_policy_defined", False)
                ),
                "performance_conclusion_allowed": False,
                "cross_group_aggregation_allowed": bool(
                    (comparison or {}).get(
                        "cross_group_aggregation_allowed",
                        False,
                    )
                ),
                "different_comparison_keys_are_not_merged": bool(
                    (comparison or {}).get(
                        "different_comparison_keys_are_not_merged",
                        True,
                    )
                ),
                "notes": list(summary.get("notes") or []),
            }
            source_contract = {
                "cohort_id": str(report.get("cohort_id") or ""),
                "report_sequence": int(report.get("report_sequence") or 0),
                "source_verification": current,
                "effective_status": str(report.get("effective_status") or ""),
                "cross_group_aggregation_performed": False,
            }
            return self._insert_artifact(
                conn,
                strategy_version_id=strategy_version_id,
                strategy_key=strategy_key,
                source_kind=SOURCE_FEEDBACK_REPORT,
                source_report_id=str(report.get("id") or report_id),
                source_report_version=str(report.get("report_version") or ""),
                source_parent_id=str(report.get("cohort_id") or ""),
                source_set_hash=source_set_hash,
                source_summary_hash=_digest(summary),
                evidence_state=str(
                    summary.get("evidence_state")
                    or "INSUFFICIENT_EVIDENCE"
                ),
                evidence=evidence,
                limitations=limitations,
                source_contract=source_contract,
            )

    def _verify_prospective(
        self,
        conn: sqlite3.Connection,
        artifact: dict[str, Any],
    ) -> str:
        row = conn.execute(
            """
            SELECT * FROM prospective_evaluation_report
            WHERE id=?
            """,
            (artifact["source_report_id"],),
        ).fetchone()
        if row is None:
            return "SOURCE_MISSING"
        summary = json.loads(str(row["summary_json"]))
        if (
            str(row["source_set_hash"]) != artifact["source_set_hash"]
            or _digest(summary) != artifact["source_summary_hash"]
            or str(row["report_version"])
            != artifact["source_report_version"]
        ):
            return "SOURCE_CHANGED"
        return "CURRENT"

    def _verify_feedback(self, artifact: dict[str, Any]) -> str:
        try:
            report = self._feedback().get_report(
                artifact["source_report_id"]
            )
        except Exception:
            return "SOURCE_MISSING"
        current = report.get("source_verification_current") or {}
        states = list(current.get("sources") or [])
        if any(str(item.get("state")) == "SOURCE_MISSING" for item in states):
            return "SOURCE_MISSING"
        if (
            str(current.get("status") or "") != "MATCH"
            or bool(report.get("source_changed_or_missing"))
        ):
            return "SOURCE_CHANGED"
        summary = report.get("summary") or {}
        if (
            str(report.get("source_set_hash") or "")
            != artifact["source_set_hash"]
            or _digest(summary) != artifact["source_summary_hash"]
            or str(report.get("report_version") or "")
            != artifact["source_report_version"]
        ):
            return "SOURCE_CHANGED"
        return "CURRENT"

    def get_artifact(
        self,
        artifact_id: str,
        *,
        verify_source: bool = True,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM strategy_evaluation_artifact
                WHERE id=?
                """,
                (artifact_id,),
            ).fetchone()
            if row is None:
                raise StrategyEvidenceError(
                    "STRATEGY_EVIDENCE_NOT_FOUND",
                    "Strategy Evaluation Artifact를 찾을 수 없습니다.",
                )
            artifact = self._row_payload(row)
            expected_hash = _digest(
                self._artifact_payload(
                    strategy_version_id=artifact["strategy_version_id"],
                    strategy_key=artifact["strategy_key"],
                    source_kind=artifact["source_kind"],
                    source_report_id=artifact["source_report_id"],
                    source_report_version=artifact["source_report_version"],
                    source_parent_id=artifact["source_parent_id"],
                    source_set_hash=artifact["source_set_hash"],
                    source_summary_hash=artifact["source_summary_hash"],
                    evidence_state=artifact["evidence_state"],
                    evidence=artifact["evidence"],
                    limitations=artifact["limitations"],
                    source_contract=artifact["source_contract"],
                )
            )
            artifact["artifact_integrity"] = (
                "MATCH"
                if expected_hash == artifact["artifact_hash"]
                else "HASH_MISMATCH"
            )
            if not verify_source:
                artifact["current_source_status"] = "NOT_CHECKED"
            elif artifact["source_kind"] == SOURCE_PROSPECTIVE_REPORT:
                artifact["current_source_status"] = self._verify_prospective(
                    conn,
                    artifact,
                )
            elif artifact["source_kind"] == SOURCE_FEEDBACK_REPORT:
                artifact["current_source_status"] = self._verify_feedback(
                    artifact
                )
            else:
                artifact["current_source_status"] = "SOURCE_UNSUPPORTED"
            return artifact

    def list_artifacts(
        self,
        *,
        strategy_version_id: str | None = None,
        verify_source: bool = False,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_ready(conn)
            if strategy_version_id is None:
                rows = conn.execute(
                    """
                    SELECT id FROM strategy_evaluation_artifact
                    ORDER BY created_at DESC,id DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id FROM strategy_evaluation_artifact
                    WHERE strategy_version_id=?
                    ORDER BY created_at DESC,id DESC
                    """,
                    (strategy_version_id,),
                ).fetchall()
        return [
            self.get_artifact(
                str(row["id"]),
                verify_source=verify_source,
            )
            for row in rows
        ]
