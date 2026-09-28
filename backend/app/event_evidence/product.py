from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.core.stock_code import normalize_stock_code
from app.event_evidence.errors import EventEvidenceContractError


EVENT_EVIDENCE_PRODUCT_CONTRACT_VERSION = "VN_P6_S1_EVENT_EVIDENCE_PRODUCT_V1"
PRODUCT_REFERENCE_LIMIT = 3


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EventEvidenceContractError(
            "EVENT_EVIDENCE_PRODUCT_JSON_INVALID",
            "Event Evidence product payload는 canonical JSON이어야 합니다.",
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class EventEvidenceProductQuery:
    """Read-only P6 product projection.

    This class never creates or mutates evidence, evaluation, or value-gate
    artifacts. It exposes only user-facing state that already exists in the
    immutable P6 store.
    """

    def __init__(self, simulation_db: Path) -> None:
        self.simulation_db = Path(simulation_db)

    def _connect(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_STORE_NOT_FOUND",
                f"Simulation DB를 찾을 수 없습니다: {self.simulation_db}",
            )
        uri = self.simulation_db.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
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
            "event_evidence_entity",
            "event_evidence_entity_relevance",
            "event_evidence_record",
            "event_evidence_record_source",
            "event_evidence_source_ref",
            "event_evidence_policy_snapshot",
            "event_evidence_quality_assessment",
            "event_evidence_outcome_observation",
            "event_evidence_evaluation_report",
            "event_evidence_value_gate_protocol",
            "event_evidence_value_gate_decision",
        }
        missing = sorted(required - self._tables(conn))
        if missing:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_SCHEMA_NOT_READY",
                "P6 Event Evidence product schema가 준비되지 않았습니다: "
                + ", ".join(missing),
            )

    @staticmethod
    def _normalize_code(code: str) -> str:
        try:
            return normalize_stock_code(code)
        except ValueError as exc:
            raise EventEvidenceContractError(
                "STOCK_CODE_INVALID",
                str(exc),
            ) from exc

    @staticmethod
    def _normalize_market(market: str) -> str:
        value = str(market or "").strip().upper()
        if value not in {"KOSPI", "KOSDAQ"}:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_MARKET_INVALID",
                "market은 KOSPI 또는 KOSDAQ이어야 합니다.",
            )
        return value

    @staticmethod
    def _base_response(code: str, market: str) -> dict[str, Any]:
        return {
            "contract_version": EVENT_EVIDENCE_PRODUCT_CONTRACT_VERSION,
            "code": code,
            "market": market,
            "recent_news": {
                "mode": "DISPLAY_ONLY",
                "decision_input": False,
            },
            "event_evidence": {
                "status": "NO_VALIDATED_EVIDENCE",
                "reference_count": 0,
                "latest_as_of": None,
                "items": [],
            },
            "value_validation": {
                "status": "NOT_EVALUATED",
                "product_scope": "RESEARCH_ONLY",
            },
            "prediction": {
                "status": "NOT_VALIDATED",
                "direction": None,
                "horizon_sessions": None,
                "probability": None,
            },
        }

    @staticmethod
    def _entity(
        conn: sqlite3.Connection,
        *,
        code: str,
        market: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT *
            FROM event_evidence_entity
            WHERE entity_type='LISTED_COMPANY'
              AND market=?
              AND ticker=?
            ORDER BY identity_as_of DESC,entity_id
            LIMIT 1
            """,
            (market, code),
        ).fetchone()

    @staticmethod
    def _verify_reference(
        conn: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> list[str]:
        try:
            quality_payload = json.loads(str(row["quality_json"]))
        except json.JSONDecodeError as exc:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_QUALITY_CORRUPT",
                "Reference quality payload를 읽을 수 없습니다.",
            ) from exc
        if _digest(quality_payload) != str(row["quality_hash"]):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_QUALITY_CORRUPT",
                "Reference quality hash가 payload와 일치하지 않습니다.",
            )
        if quality_payload.get("assessment_id") != str(row["assessment_id"]):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_QUALITY_IDENTITY_MISMATCH",
                "Reference quality identity가 일치하지 않습니다.",
            )

        event = conn.execute(
            """
            SELECT event_hash,source_bundle_hash
            FROM event_evidence_record
            WHERE event_id=? AND event_version=?
            """,
            (row["event_id"], row["event_version"]),
        ).fetchone()
        entity = conn.execute(
            """
            SELECT identity_hash
            FROM event_evidence_entity
            WHERE entity_id=?
            """,
            (row["entity_id"],),
        ).fetchone()
        relevance = conn.execute(
            """
            SELECT event_hash,entity_hash,relation_hash
            FROM event_evidence_entity_relevance
            WHERE relevance_id=?
            """,
            (row["relevance_id"],),
        ).fetchone()
        if event is None or entity is None or relevance is None:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_REFERENCE_MISSING",
                "Reference가 pin한 immutable evidence를 찾을 수 없습니다.",
            )
        if (
            str(event["event_hash"]) != str(row["event_hash"])
            or str(event["source_bundle_hash"]) != str(row["source_bundle_hash"])
            or str(entity["identity_hash"]) != str(row["entity_hash"])
            or str(relevance["event_hash"]) != str(row["event_hash"])
            or str(relevance["entity_hash"]) != str(row["entity_hash"])
            or str(relevance["relation_hash"]) != str(row["relevance_hash"])
        ):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_REFERENCE_INTEGRITY_MISMATCH",
                "Reference evidence pin이 현재 immutable row와 일치하지 않습니다.",
            )

        source_kinds: list[str] = []
        source_refs = quality_payload.get("source_refs") or []
        if not isinstance(source_refs, list) or not source_refs:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_SOURCE_PIN_MISSING",
                "Reference quality에 source pin이 없습니다.",
            )
        for pin in source_refs:
            if not isinstance(pin, dict):
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_PRODUCT_SOURCE_PIN_INVALID",
                    "Reference quality source pin 형식이 잘못되었습니다.",
                )
            source = conn.execute(
                """
                SELECT
                    sr.source_kind,
                    sr.source_ref_hash,
                    sr.rights_policy_id,
                    p.policy_hash
                FROM event_evidence_source_ref sr
                JOIN event_evidence_policy_snapshot p
                  ON p.policy_id=sr.rights_policy_id
                WHERE sr.source_ref_id=?
                """,
                (pin.get("source_ref_id"),),
            ).fetchone()
            if source is None:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_PRODUCT_SOURCE_MISSING",
                    "Reference가 pin한 source를 찾을 수 없습니다.",
                )
            if (
                str(source["source_ref_hash"]) != str(pin.get("source_ref_hash"))
                or str(source["rights_policy_id"]) != str(pin.get("rights_policy_id"))
                or str(source["policy_hash"]) != str(pin.get("policy_hash"))
            ):
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_PRODUCT_SOURCE_INTEGRITY_MISMATCH",
                    "Reference source/policy pin이 현재 immutable row와 다릅니다.",
                )
            source_kinds.append(str(source["source_kind"]))

        return sorted(set(source_kinds))

    @staticmethod
    def _reference_rows(
        conn: sqlite3.Connection,
        entity_id: str,
    ) -> list[sqlite3.Row]:
        return conn.execute(
            """
            SELECT
                q.*,
                e.event_type,
                e.available_at,
                e.event_state,
                r.evidence_as_of
            FROM event_evidence_quality_assessment q
            JOIN event_evidence_record e
              ON e.event_id=q.event_id
             AND e.event_version=q.event_version
            JOIN event_evidence_entity_relevance r
              ON r.relevance_id=q.relevance_id
            WHERE q.entity_id=?
              AND q.assessment_scope='REFERENCE'
              AND q.quality_state IN ('USABLE','LIMITED')
            ORDER BY q.assessment_as_of DESC,q.assessment_id
            """,
            (entity_id,),
        ).fetchall()

    def _project_references(
        self,
        conn: sqlite3.Connection,
        entity_id: str,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        seen_samples: set[str] = set()
        integrity_blocked = False
        for row in self._reference_rows(conn, entity_id):
            try:
                source_kinds = self._verify_reference(conn, row)
            except EventEvidenceContractError:
                integrity_blocked = True
                continue

            if not source_kinds or "TEST_SYNTHETIC" in source_kinds:
                continue
            sample_identity = str(row["canonical_event_id"] or row["event_id"])
            if sample_identity in seen_samples:
                continue
            seen_samples.add(sample_identity)
            items.append(
                {
                    "event_type": str(row["event_type"]),
                    "relation_type": str(row["relation_type"]),
                    "relevance_state": str(row["relevance_state"]),
                    "quality_state": str(row["quality_state"]),
                    "source_kinds": source_kinds,
                    "available_at": str(row["available_at"]),
                    "evidence_as_of": str(row["evidence_as_of"]),
                    "revision_state": str(row["event_state"]),
                    "assessment_as_of": str(row["assessment_as_of"]),
                }
            )

        if items:
            status = (
                "REFERENCE_AVAILABLE"
                if any(item["quality_state"] == "USABLE" for item in items)
                else "REFERENCE_LIMITED"
            )
            return {
                "status": status,
                "reference_count": len(items),
                "latest_as_of": max(item["assessment_as_of"] for item in items),
                "items": items[:PRODUCT_REFERENCE_LIMIT],
            }
        return {
            "status": (
                "EVIDENCE_BLOCKED"
                if integrity_blocked
                else "NO_VALIDATED_EVIDENCE"
            ),
            "reference_count": 0,
            "latest_as_of": None,
            "items": [],
        }

    @staticmethod
    def _report_contains_entity(
        conn: sqlite3.Connection,
        report_json: str,
        entity_id: str,
    ) -> bool:
        try:
            payload = json.loads(report_json)
        except json.JSONDecodeError:
            return False
        pins = payload.get("observations") or []
        for pin in pins:
            if not isinstance(pin, dict):
                continue
            row = conn.execute(
                """
                SELECT entity_id
                FROM event_evidence_outcome_observation
                WHERE observation_id=?
                """,
                (pin.get("observation_id"),),
            ).fetchone()
            if row is not None and str(row["entity_id"]) == entity_id:
                return True
        return False

    @staticmethod
    def _verify_decision(
        conn: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> None:
        try:
            payload = json.loads(str(row["decision_json"]))
        except json.JSONDecodeError as exc:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_DECISION_CORRUPT",
                "Value Gate Decision payload를 읽을 수 없습니다.",
            ) from exc
        if _digest(payload) != str(row["decision_hash"]):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_DECISION_CORRUPT",
                "Value Gate Decision hash가 payload와 일치하지 않습니다.",
            )
        protocol = conn.execute(
            """
            SELECT protocol_hash
            FROM event_evidence_value_gate_protocol
            WHERE protocol_id=?
            """,
            (row["gate_protocol_id"],),
        ).fetchone()
        report = conn.execute(
            """
            SELECT report_hash
            FROM event_evidence_evaluation_report
            WHERE report_id=?
            """,
            (row["evaluation_report_id"],),
        ).fetchone()
        if protocol is None or report is None:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_DECISION_REFERENCE_MISSING",
                "Value Gate Decision이 pin한 protocol/report를 찾을 수 없습니다.",
            )
        if (
            str(protocol["protocol_hash"]) != str(row["gate_protocol_hash"])
            or str(report["report_hash"]) != str(row["evaluation_report_hash"])
        ):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_DECISION_INTEGRITY_MISMATCH",
                "Value Gate Decision pin이 현재 immutable artifact와 다릅니다.",
            )
        if bool(row["prediction_eligible"]):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_PREDICTION_GUARDRAIL_BROKEN",
                "P6-S1-F V1 Decision은 prediction eligible일 수 없습니다.",
            )
        if str(row["product_scope"]) not in {
            "RESEARCH_ONLY",
            "REFERENCE_CONTEXT",
        }:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PRODUCT_SCOPE_GUARDRAIL_BROKEN",
                "P6-S1-G는 prediction product scope를 노출하지 않습니다.",
            )

    def _project_value_validation(
        self,
        conn: sqlite3.Connection,
        entity_id: str,
    ) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT d.*,r.report_json
            FROM event_evidence_value_gate_decision d
            JOIN event_evidence_evaluation_report r
              ON r.report_id=d.evaluation_report_id
            ORDER BY d.created_at DESC,d.decision_id
            """
        ).fetchall()
        for row in rows:
            if str(row["evidence_population"]) != "REAL_CORPUS":
                continue
            if not self._report_contains_entity(
                conn,
                str(row["report_json"]),
                entity_id,
            ):
                continue
            try:
                self._verify_decision(conn, row)
            except EventEvidenceContractError:
                return {
                    "status": "BLOCKED",
                    "product_scope": "RESEARCH_ONLY",
                }
            return {
                "status": str(row["decision"]),
                "product_scope": str(row["product_scope"]),
            }
        return {
            "status": "NOT_EVALUATED",
            "product_scope": "RESEARCH_ONLY",
        }

    def stock_status(self, code: str, market: str) -> dict[str, Any]:
        normalized_code = self._normalize_code(code)
        normalized_market = self._normalize_market(market)
        response = self._base_response(normalized_code, normalized_market)

        with self._connect() as conn:
            self._require_ready(conn)
            entity = self._entity(
                conn,
                code=normalized_code,
                market=normalized_market,
            )
            if entity is None:
                return response

            entity_id = str(entity["entity_id"])
            response["event_evidence"] = self._project_references(
                conn,
                entity_id,
            )
            response["value_validation"] = self._project_value_validation(
                conn,
                entity_id,
            )

        return response
