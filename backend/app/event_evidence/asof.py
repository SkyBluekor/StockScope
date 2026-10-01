from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.stock_code import normalize_stock_code
from app.event_evidence.errors import EventEvidenceContractError


EVENT_REFERENCE_AS_OF_CONTRACT_VERSION = (
    "VN_NEXT6D_S2_EVENT_REFERENCE_AS_OF_V1"
)
EVENT_REFERENCE_AS_OF_MODE = "SYSTEM_OBSERVED_AS_OF"
DEFAULT_REFERENCE_LIMIT = 3

_REQUIRED_TABLES = {
    "event_evidence_policy_snapshot",
    "event_evidence_source_ref",
    "event_evidence_record",
    "event_evidence_record_source",
    "event_evidence_entity",
    "event_evidence_entity_relevance",
    "event_evidence_canonical_group",
    "event_evidence_resolution",
    "event_evidence_quality_assessment",
}
_ACTIVE_REVISIONS = {"ORIGINAL", "CORRECTED"}
_REFERENCE_QUALITY = {"USABLE", "LIMITED"}


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
            "EVENT_EVIDENCE_ASOF_JSON_INVALID",
            "Event Evidence as-of payload must be canonical JSON.",
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _aware_utc(value: str, field: str) -> tuple[datetime, str]:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise EventEvidenceContractError(
            "EVENT_EVIDENCE_ASOF_TIME_INVALID",
            f"{field} must be a timezone-aware ISO-8601 datetime.",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventEvidenceContractError(
            "EVENT_EVIDENCE_ASOF_TIMEZONE_REQUIRED",
            f"{field} must include a timezone offset.",
        )
    utc = parsed.astimezone(timezone.utc)
    return utc, utc.isoformat()


def _is_after(value: str, cutoff: datetime, field: str) -> bool:
    parsed, _ = _aware_utc(value, field)
    return parsed > cutoff


class EventEvidenceAsOfReader:
    """Read-only P6 reference projection frozen at a decision cutoff.

    The reader reconstructs only evidence that StockScope had actually observed
    by the cutoff. It does not claim a complete historical source corpus and
    never performs evaluation, prediction, provider access, or database writes.
    """

    def __init__(self, simulation_db: Path) -> None:
        self.simulation_db = Path(simulation_db)

    def _connect(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_STORE_NOT_FOUND",
                f"Simulation DB not found: {self.simulation_db}",
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
        missing = sorted(_REQUIRED_TABLES - self._tables(conn))
        if missing:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_SCHEMA_NOT_READY",
                "P6 Event Evidence as-of schema is not ready: "
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
                "market must be KOSPI or KOSDAQ.",
            )
        return value

    @staticmethod
    def _entity_as_of(
        conn: sqlite3.Connection,
        *,
        code: str,
        market: str,
        cutoff_dt: datetime,
    ) -> tuple[sqlite3.Row | None, dict[str, int]]:
        rows = conn.execute(
            """
            SELECT *
            FROM event_evidence_entity
            WHERE entity_type='LISTED_COMPANY'
              AND market=?
              AND ticker=?
            ORDER BY identity_as_of DESC,entity_id
            """,
            (market, code),
        ).fetchall()
        diagnostics = {
            "excluded_entity_after_cutoff_count": 0,
            "excluded_entity_late_ingest_count": 0,
        }
        for row in rows:
            if _is_after(
                str(row["identity_as_of"]),
                cutoff_dt,
                "entity.identity_as_of",
            ):
                diagnostics["excluded_entity_after_cutoff_count"] += 1
                continue
            if _is_after(
                str(row["created_at"]),
                cutoff_dt,
                "entity.created_at",
            ):
                diagnostics["excluded_entity_late_ingest_count"] += 1
                continue
            return row, diagnostics
        return None, diagnostics

    @staticmethod
    def _event_ids_known_as_of(
        conn: sqlite3.Connection,
        *,
        entity_id: str,
        cutoff_dt: datetime,
    ) -> tuple[list[str], int, int]:
        rows = conn.execute(
            """
            SELECT event_id,evidence_as_of,created_at
            FROM event_evidence_entity_relevance
            WHERE entity_id=?
            ORDER BY event_id,event_version,relation_type
            """,
            (entity_id,),
        ).fetchall()
        event_ids: set[str] = set()
        excluded_after = 0
        excluded_late = 0
        for row in rows:
            if _is_after(
                str(row["evidence_as_of"]),
                cutoff_dt,
                "relevance.evidence_as_of",
            ):
                excluded_after += 1
                continue
            if _is_after(
                str(row["created_at"]),
                cutoff_dt,
                "relevance.created_at",
            ):
                excluded_late += 1
                continue
            event_ids.add(str(row["event_id"]))
        return sorted(event_ids), excluded_after, excluded_late

    @staticmethod
    def _latest_revision_as_of(
        conn: sqlite3.Connection,
        *,
        event_id: str,
        cutoff_dt: datetime,
    ) -> tuple[sqlite3.Row | None, int, int]:
        rows = conn.execute(
            """
            SELECT *
            FROM event_evidence_record
            WHERE event_id=?
            ORDER BY event_version DESC
            """,
            (event_id,),
        ).fetchall()
        excluded_after = 0
        excluded_late = 0
        for row in rows:
            if _is_after(
                str(row["available_at"]),
                cutoff_dt,
                "event.available_at",
            ):
                excluded_after += 1
                continue
            if _is_after(
                str(row["created_at"]),
                cutoff_dt,
                "event.created_at",
            ):
                excluded_late += 1
                continue
            return row, excluded_after, excluded_late
        return None, excluded_after, excluded_late

    @staticmethod
    def _candidate_quality_rows(
        conn: sqlite3.Connection,
        *,
        entity_id: str,
        event_id: str,
        event_version: int,
    ) -> list[sqlite3.Row]:
        return conn.execute(
            """
            SELECT
                q.*,
                r.evidence_as_of,
                r.created_at AS relevance_created_at,
                r.event_hash AS relevance_event_hash,
                r.entity_hash AS relevance_entity_hash,
                r.relation_hash AS current_relevance_hash,
                e.event_type,
                e.available_at,
                e.created_at AS event_created_at,
                e.event_state,
                e.event_hash AS current_event_hash,
                e.source_bundle_hash AS current_source_bundle_hash
            FROM event_evidence_quality_assessment q
            JOIN event_evidence_record e
              ON e.event_id=q.event_id
             AND e.event_version=q.event_version
            JOIN event_evidence_entity_relevance r
              ON r.relevance_id=q.relevance_id
            WHERE q.entity_id=?
              AND q.event_id=?
              AND q.event_version=?
              AND q.assessment_scope='REFERENCE'
              AND q.quality_state IN ('USABLE','LIMITED')
            ORDER BY q.assessment_as_of DESC,q.assessment_id
            """,
            (entity_id, event_id, event_version),
        ).fetchall()

    @staticmethod
    def _verify_candidate(
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        entity: sqlite3.Row,
        cutoff_dt: datetime,
    ) -> tuple[list[str], list[dict[str, str]], str | None]:
        try:
            quality_payload = json.loads(str(row["quality_json"]))
        except json.JSONDecodeError as exc:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_ASOF_QUALITY_CORRUPT",
                "Reference quality payload cannot be decoded.",
            ) from exc

        if _digest(quality_payload) != str(row["quality_hash"]):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_ASOF_QUALITY_CORRUPT",
                "Reference quality hash does not match its payload.",
            )
        if quality_payload.get("assessment_id") != str(row["assessment_id"]):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_ASOF_QUALITY_IDENTITY_MISMATCH",
                "Reference quality assessment identity does not match.",
            )

        if (
            str(row["current_event_hash"]) != str(row["event_hash"])
            or str(row["current_source_bundle_hash"])
            != str(row["source_bundle_hash"])
            or str(entity["identity_hash"]) != str(row["entity_hash"])
            or str(row["relevance_event_hash"]) != str(row["event_hash"])
            or str(row["relevance_entity_hash"]) != str(row["entity_hash"])
            or str(row["current_relevance_hash"])
            != str(row["relevance_hash"])
        ):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_ASOF_REFERENCE_INTEGRITY_MISMATCH",
                "Reference immutable evidence pins do not match.",
            )

        if str(row["revision_state"]) != str(row["event_state"]):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_ASOF_REVISION_INTEGRITY_MISMATCH",
                "Quality revision_state does not match the selected event revision.",
            )

        canonical_event_id = (
            str(row["canonical_event_id"])
            if row["canonical_event_id"] is not None
            else None
        )
        if canonical_event_id is not None:
            group = conn.execute(
                """
                SELECT canonical_hash,created_at
                FROM event_evidence_canonical_group
                WHERE canonical_event_id=? AND canonical_version=?
                """,
                (canonical_event_id, row["canonical_version"]),
            ).fetchone()
            resolution = conn.execute(
                """
                SELECT resolution_hash,created_at
                FROM event_evidence_resolution
                WHERE event_id=? AND event_version=?
                """,
                (row["event_id"], row["event_version"]),
            ).fetchone()
            if group is None or resolution is None:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_ASOF_CANONICAL_REFERENCE_MISSING",
                    "Pinned canonical resolution is missing.",
                )
            if (
                str(group["canonical_hash"]) != str(row["canonical_hash"])
                or str(resolution["resolution_hash"])
                != str(row["resolution_hash"])
            ):
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_ASOF_CANONICAL_INTEGRITY_MISMATCH",
                    "Pinned canonical resolution hash does not match.",
                )
            if _is_after(
                str(group["created_at"]),
                cutoff_dt,
                "canonical.created_at",
            ) or _is_after(
                str(resolution["created_at"]),
                cutoff_dt,
                "resolution.created_at",
            ):
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_ASOF_CANONICAL_AFTER_CUTOFF",
                    "Pinned canonical resolution was not observed by cutoff.",
                )

        source_refs = quality_payload.get("source_refs") or []
        if not isinstance(source_refs, list) or not source_refs:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_ASOF_SOURCE_PIN_MISSING",
                "Reference quality has no source pins.",
            )

        source_kinds: list[str] = []
        source_identities: list[dict[str, str]] = []
        for pin in source_refs:
            if not isinstance(pin, dict):
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_ASOF_SOURCE_PIN_INVALID",
                    "Reference source pin has an invalid shape.",
                )
            source = conn.execute(
                """
                SELECT
                    sr.source_kind,
                    sr.source_ref_hash,
                    sr.rights_policy_id,
                    sr.available_at,
                    sr.created_at AS source_created_at,
                    p.policy_hash,
                    p.created_at AS policy_created_at
                FROM event_evidence_source_ref sr
                JOIN event_evidence_policy_snapshot p
                  ON p.policy_id=sr.rights_policy_id
                WHERE sr.source_ref_id=?
                """,
                (pin.get("source_ref_id"),),
            ).fetchone()
            if source is None:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_ASOF_SOURCE_MISSING",
                    "Reference pinned source is missing.",
                )
            if (
                str(source["source_ref_hash"])
                != str(pin.get("source_ref_hash"))
                or str(source["rights_policy_id"])
                != str(pin.get("rights_policy_id"))
                or str(source["policy_hash"]) != str(pin.get("policy_hash"))
            ):
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_ASOF_SOURCE_INTEGRITY_MISMATCH",
                    "Reference source/policy pins do not match.",
                )
            if _is_after(
                str(source["available_at"]),
                cutoff_dt,
                "source.available_at",
            ):
                return [], [], "SOURCE_AFTER_CUTOFF"
            if _is_after(
                str(source["source_created_at"]),
                cutoff_dt,
                "source.created_at",
            ) or _is_after(
                str(source["policy_created_at"]),
                cutoff_dt,
                "policy.created_at",
            ):
                return [], [], "SOURCE_LATE_INGEST"

            source_kinds.append(str(source["source_kind"]))
            source_identities.append(
                {
                    "source_ref_hash": str(source["source_ref_hash"]),
                    "policy_hash": str(source["policy_hash"]),
                }
            )

        return (
            sorted(set(source_kinds)),
            sorted(
                source_identities,
                key=lambda item: (
                    item["source_ref_hash"],
                    item["policy_hash"],
                ),
            ),
            None,
        )

    def stock_reference_as_of(
        self,
        code: str,
        market: str,
        decision_cutoff: str,
        *,
        limit: int = DEFAULT_REFERENCE_LIMIT,
    ) -> dict[str, Any]:
        normalized_code = self._normalize_code(code)
        normalized_market = self._normalize_market(market)
        if limit < 1 or limit > 50:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_ASOF_LIMIT_INVALID",
                "limit must be between 1 and 50.",
            )
        cutoff_dt, cutoff = _aware_utc(
            decision_cutoff,
            "decision_cutoff",
        )

        diagnostics = {
            "candidate_count": 0,
            "excluded_after_cutoff_count": 0,
            "excluded_late_ingest_count": 0,
            "excluded_inactive_revision_count": 0,
            "excluded_integrity_count": 0,
            "excluded_synthetic_count": 0,
            "excluded_duplicate_count": 0,
        }

        with self._connect() as conn:
            self._require_ready(conn)
            entity, entity_diag = self._entity_as_of(
                conn,
                code=normalized_code,
                market=normalized_market,
                cutoff_dt=cutoff_dt,
            )
            diagnostics["excluded_after_cutoff_count"] += entity_diag[
                "excluded_entity_after_cutoff_count"
            ]
            diagnostics["excluded_late_ingest_count"] += entity_diag[
                "excluded_entity_late_ingest_count"
            ]

            if entity is None:
                return self._response(
                    code=normalized_code,
                    market=normalized_market,
                    cutoff=cutoff,
                    event_status="NO_OBSERVED_ENTITY_BY_CUTOFF",
                    items=[],
                    identity_refs=[],
                    diagnostics=diagnostics,
                    limit=limit,
                    entity_identity_hash=None,
                )

            event_ids, rel_after, rel_late = self._event_ids_known_as_of(
                conn,
                entity_id=str(entity["entity_id"]),
                cutoff_dt=cutoff_dt,
            )
            diagnostics["excluded_after_cutoff_count"] += rel_after
            diagnostics["excluded_late_ingest_count"] += rel_late

            candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
            integrity_blocked = False

            for event_id in event_ids:
                revision, event_after, event_late = self._latest_revision_as_of(
                    conn,
                    event_id=event_id,
                    cutoff_dt=cutoff_dt,
                )
                diagnostics["excluded_after_cutoff_count"] += event_after
                diagnostics["excluded_late_ingest_count"] += event_late
                if revision is None:
                    continue
                if str(revision["event_state"]) not in _ACTIVE_REVISIONS:
                    diagnostics["excluded_inactive_revision_count"] += 1
                    continue

                rows = self._candidate_quality_rows(
                    conn,
                    entity_id=str(entity["entity_id"]),
                    event_id=event_id,
                    event_version=int(revision["event_version"]),
                )
                diagnostics["candidate_count"] += len(rows)

                for row in rows:
                    if _is_after(
                        str(row["available_at"]),
                        cutoff_dt,
                        "event.available_at",
                    ) or _is_after(
                        str(row["evidence_as_of"]),
                        cutoff_dt,
                        "relevance.evidence_as_of",
                    ) or _is_after(
                        str(row["assessment_as_of"]),
                        cutoff_dt,
                        "quality.assessment_as_of",
                    ):
                        diagnostics["excluded_after_cutoff_count"] += 1
                        continue

                    if _is_after(
                        str(row["event_created_at"]),
                        cutoff_dt,
                        "event.created_at",
                    ) or _is_after(
                        str(row["relevance_created_at"]),
                        cutoff_dt,
                        "relevance.created_at",
                    ) or _is_after(
                        str(row["created_at"]),
                        cutoff_dt,
                        "quality.created_at",
                    ):
                        diagnostics["excluded_late_ingest_count"] += 1
                        continue

                    quality_state = str(row["quality_state"])
                    if quality_state not in _REFERENCE_QUALITY:
                        continue

                    try:
                        source_kinds, source_ids, exclusion = (
                            self._verify_candidate(
                                conn,
                                row,
                                entity=entity,
                                cutoff_dt=cutoff_dt,
                            )
                        )
                    except EventEvidenceContractError:
                        diagnostics["excluded_integrity_count"] += 1
                        integrity_blocked = True
                        continue

                    if exclusion == "SOURCE_AFTER_CUTOFF":
                        diagnostics["excluded_after_cutoff_count"] += 1
                        continue
                    if exclusion == "SOURCE_LATE_INGEST":
                        diagnostics["excluded_late_ingest_count"] += 1
                        continue
                    if (
                        not source_kinds
                        or "TEST_SYNTHETIC" in source_kinds
                    ):
                        diagnostics["excluded_synthetic_count"] += 1
                        continue

                    item = {
                        "event_type": str(row["event_type"]),
                        "relation_type": str(row["relation_type"]),
                        "relevance_state": str(row["relevance_state"]),
                        "quality_state": quality_state,
                        "source_kinds": source_kinds,
                        "available_at": _aware_utc(
                            str(row["available_at"]),
                            "event.available_at",
                        )[1],
                        "evidence_as_of": _aware_utc(
                            str(row["evidence_as_of"]),
                            "relevance.evidence_as_of",
                        )[1],
                        "revision_state": str(row["event_state"]),
                        "assessment_as_of": _aware_utc(
                            str(row["assessment_as_of"]),
                            "quality.assessment_as_of",
                        )[1],
                    }
                    sample_identity = str(
                        row["canonical_event_id"] or row["event_id"]
                    )
                    identity = {
                        "sample_identity": sample_identity,
                        "event_hash": str(row["event_hash"]),
                        "relevance_hash": str(row["relevance_hash"]),
                        "quality_hash": str(row["quality_hash"]),
                        "source_identities": source_ids,
                    }
                    candidates.append((item, identity))

            candidates.sort(
                key=lambda pair: (
                    pair[0]["assessment_as_of"],
                    pair[0]["available_at"],
                    pair[1]["sample_identity"],
                    pair[1]["quality_hash"],
                ),
                reverse=True,
            )

            seen: set[str] = set()
            deduped: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for item, identity in candidates:
                sample_identity = identity["sample_identity"]
                if sample_identity in seen:
                    diagnostics["excluded_duplicate_count"] += 1
                    continue
                seen.add(sample_identity)
                deduped.append((item, identity))

            projected = deduped[:limit]
            items = [item for item, _ in projected]
            identity_refs = [identity for _, identity in projected]

            if items:
                event_status = (
                    "REFERENCE_AVAILABLE"
                    if any(
                        item["quality_state"] == "USABLE"
                        for item in items
                    )
                    else "REFERENCE_LIMITED"
                )
            elif integrity_blocked:
                event_status = "EVIDENCE_BLOCKED"
            else:
                event_status = "NO_VALIDATED_EVIDENCE"

            return self._response(
                code=normalized_code,
                market=normalized_market,
                cutoff=cutoff,
                event_status=event_status,
                items=items,
                identity_refs=identity_refs,
                diagnostics=diagnostics,
                limit=limit,
                entity_identity_hash=str(entity["identity_hash"]),
                total_reference_count=len(deduped),
            )

    @staticmethod
    def _response(
        *,
        code: str,
        market: str,
        cutoff: str,
        event_status: str,
        items: list[dict[str, Any]],
        identity_refs: list[dict[str, Any]],
        diagnostics: dict[str, int],
        limit: int,
        entity_identity_hash: str | None,
        total_reference_count: int = 0,
    ) -> dict[str, Any]:
        latest_as_of = (
            max(item["assessment_as_of"] for item in items)
            if items
            else None
        )
        overall_status = (
            "AVAILABLE"
            if event_status == "REFERENCE_AVAILABLE"
            else "PARTIAL"
        )

        temporal_projection = {
            "mode": EVENT_REFERENCE_AS_OF_MODE,
            "decision_cutoff": cutoff,
            "storage_observation_cutoff_enforced": True,
            "historical_source_completeness_proven": False,
            "historical_evaluation_approved": False,
        }
        event_evidence = {
            "status": event_status,
            "reference_count": total_reference_count,
            "projected_reference_count": len(items),
            "latest_as_of": latest_as_of,
            "items": items,
            "diagnostics": diagnostics,
        }
        value_validation = {
            "status": "NOT_PROJECTED_AS_OF",
            "product_scope": "RESEARCH_ONLY",
        }
        prediction = {
            "status": "NOT_VALIDATED",
            "direction": None,
            "horizon_sessions": None,
            "probability": None,
        }
        governance = {
            "claim_scope": "REFERENCE_CONTEXT_AS_OF_ONLY",
            "historical_evaluation_approved": False,
            "prediction_approved": False,
            "strategy_input_approved": False,
            "scanner_input_approved": False,
            "risk_gate_input_approved": False,
            "holdings_plan_input_approved": False,
            "production_decision_approved": False,
            "network_access": False,
            "database_write": False,
        }

        identity_payload = {
            "contract_version": EVENT_REFERENCE_AS_OF_CONTRACT_VERSION,
            "status": overall_status,
            "code": code,
            "market": market,
            "decision_cutoff": cutoff,
            "limit": limit,
            "entity_identity_hash": entity_identity_hash,
            "temporal_projection": temporal_projection,
            "event_status": event_status,
            "identity_refs": identity_refs,
            "items": items,
            "value_validation": value_validation,
            "prediction": prediction,
            "governance": governance,
        }
        projection_hash = _digest(identity_payload)
        return {
            "contract_version": EVENT_REFERENCE_AS_OF_CONTRACT_VERSION,
            "projection_id": f"EVASOF-{projection_hash[:16]}",
            "projection_hash": projection_hash,
            "status": overall_status,
            "code": code,
            "market": market,
            "decision_cutoff": cutoff,
            "temporal_projection": temporal_projection,
            "recent_news": {
                "mode": "DISPLAY_ONLY",
                "decision_input": False,
            },
            "event_evidence": event_evidence,
            "value_validation": value_validation,
            "prediction": prediction,
            "governance": governance,
        }
