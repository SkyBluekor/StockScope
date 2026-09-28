from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from app.event_evidence.errors import EventEvidenceContractError
from app.event_evidence.resolution import (
    DuplicateClassification,
    EventResolutionService,
)
from app.event_evidence.store import EventEvidenceStore


EVENT_EVIDENCE_QUALITY_CONTRACT_VERSION = "VN_P6_S1_EVENT_QUALITY_V1"
QUALITY_TABLE = "event_evidence_quality_assessment"


class EvidenceQualityScope(str, Enum):
    REFERENCE = "REFERENCE"
    HISTORICAL_EVALUATION = "HISTORICAL_EVALUATION"


class EvidenceQualityState(str, Enum):
    USABLE = "USABLE"
    LIMITED = "LIMITED"
    INSUFFICIENT = "INSUFFICIENT"
    BLOCKED = "BLOCKED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            "EVENT_QUALITY_JSON_INVALID",
            "Evidence Quality payload는 canonical JSON으로 직렬화할 수 있어야 합니다.",
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_aware(value: str, field_name: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EventEvidenceContractError(
            "EVENT_QUALITY_TIME_INVALID",
            f"{field_name}은 timezone이 포함된 ISO-8601 시각이어야 합니다.",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventEvidenceContractError(
            "EVENT_QUALITY_TIMEZONE_REQUIRED",
            f"{field_name}에는 timezone offset이 필요합니다.",
        )
    return parsed


def _stable_ids(payload: dict[str, Any]) -> set[str]:
    keys = ("official_event_id", "receipt_no", "rcept_no", "source_event_id")
    values: set[str] = set()
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            values.add(f"{key}:{str(value).strip()}")
    nested = payload.get("identifiers")
    if isinstance(nested, dict):
        for key in keys:
            value = nested.get(key)
            if value not in (None, ""):
                values.add(f"{key}:{str(value).strip()}")
    return values


def _event_date(value: str | None) -> str | None:
    if not value:
        return None
    return str(value)[:10]


class EventEvidenceQualityService:
    """Create immutable, as-of quality assessments for P6 event evidence.

    Quality is an evidence-eligibility gate, not a market direction score,
    probability, source ranking, or Strategy input.
    """

    def __init__(
        self,
        simulation_db: Path,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.simulation_db = Path(simulation_db)
        self.clock = clock or _now
        self.store = EventEvidenceStore(self.simulation_db, clock=self.clock)
        self.resolver = EventResolutionService(
            self.simulation_db,
            clock=self.clock,
        )

    def _connect(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_STORE_NOT_FOUND",
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
            QUALITY_TABLE,
            "event_evidence_record",
            "event_evidence_record_source",
            "event_evidence_source_ref",
            "event_evidence_policy_snapshot",
            "event_evidence_entity",
            "event_evidence_entity_relevance",
            "event_evidence_canonical_group",
            "event_evidence_resolution",
        }
        missing = sorted(required - self._tables(conn))
        if missing:
            raise EventEvidenceContractError(
                "EVENT_QUALITY_MIGRATION_REQUIRED",
                "P6 Evidence Quality schema가 준비되지 않았습니다: "
                + ", ".join(missing),
            )

    @staticmethod
    def _event_row(
        conn: sqlite3.Connection,
        event_id: str,
        event_version: int,
    ) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT * FROM event_evidence_record
            WHERE event_id=? AND event_version=?
            """,
            (event_id, event_version),
        ).fetchone()
        if row is None:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_NOT_FOUND",
                "Event Evidence revision을 찾을 수 없습니다.",
            )
        return row

    @staticmethod
    def _entity_row(conn: sqlite3.Connection, entity_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM event_evidence_entity WHERE entity_id=?",
            (entity_id,),
        ).fetchone()
        if row is None:
            raise EventEvidenceContractError(
                "EVENT_ENTITY_NOT_FOUND",
                "Event Entity를 찾을 수 없습니다.",
            )
        return row

    @staticmethod
    def _relevance_rows(
        conn: sqlite3.Connection,
        *,
        event_id: str,
        event_version: int,
        entity_id: str,
        relevance_id: str | None,
    ) -> list[sqlite3.Row]:
        if relevance_id:
            row = conn.execute(
                """
                SELECT * FROM event_evidence_entity_relevance
                WHERE relevance_id=?
                  AND event_id=? AND event_version=? AND entity_id=?
                """,
                (relevance_id, event_id, event_version, entity_id),
            ).fetchone()
            return [row] if row is not None else []
        return conn.execute(
            """
            SELECT * FROM event_evidence_entity_relevance
            WHERE event_id=? AND event_version=? AND entity_id=?
            ORDER BY relation_type,relevance_id
            """,
            (event_id, event_version, entity_id),
        ).fetchall()

    @staticmethod
    def _verify_entity_and_relevance(
        event_row: sqlite3.Row,
        entity_row: sqlite3.Row,
        relevance_row: sqlite3.Row,
    ) -> None:
        entity_payload = json.loads(str(entity_row["identity_json"]))
        if _digest(entity_payload) != str(entity_row["identity_hash"]):
            raise EventEvidenceContractError(
                "EVENT_QUALITY_ENTITY_INTEGRITY_MISMATCH",
                "Entity identity hash가 저장 내용과 일치하지 않습니다.",
            )
        relation_payload = json.loads(str(relevance_row["relation_json"]))
        if _digest(relation_payload) != str(relevance_row["relation_hash"]):
            raise EventEvidenceContractError(
                "EVENT_QUALITY_RELEVANCE_INTEGRITY_MISMATCH",
                "Relevance hash가 저장 내용과 일치하지 않습니다.",
            )
        if str(relevance_row["event_hash"]) != str(event_row["event_hash"]):
            raise EventEvidenceContractError(
                "EVENT_QUALITY_RELEVANCE_EVENT_HASH_MISMATCH",
                "Relevance가 pin한 Event hash가 현재 immutable Event와 다릅니다.",
            )
        if str(relevance_row["entity_hash"]) != str(entity_row["identity_hash"]):
            raise EventEvidenceContractError(
                "EVENT_QUALITY_RELEVANCE_ENTITY_HASH_MISMATCH",
                "Relevance가 pin한 Entity hash가 현재 immutable Entity와 다릅니다.",
            )

    @staticmethod
    def _source_rows(
        conn: sqlite3.Connection,
        *,
        event_id: str,
        event_version: int,
    ) -> list[sqlite3.Row]:
        return conn.execute(
            """
            SELECT
                sr.*,
                p.policy_json,
                p.policy_hash,
                p.derived_retention_allowed,
                p.historical_evaluation_allowed
            FROM event_evidence_record_source rs
            JOIN event_evidence_source_ref sr
              ON sr.source_ref_id=rs.source_ref_id
            JOIN event_evidence_policy_snapshot p
              ON p.policy_id=sr.rights_policy_id
            WHERE rs.event_id=? AND rs.event_version=?
            ORDER BY sr.source_ref_id
            """,
            (event_id, event_version),
        ).fetchall()

    @staticmethod
    def _policy_bundle_hash(source_rows: list[sqlite3.Row]) -> str:
        bundle = sorted(
            {
                (
                    str(row["rights_policy_id"]),
                    str(row["policy_hash"]),
                )
                for row in source_rows
            }
        )
        return _digest(
            [
                {"policy_id": policy_id, "policy_hash": policy_hash}
                for policy_id, policy_hash in bundle
            ]
        )

    @staticmethod
    def _source_origin(row: sqlite3.Row) -> str:
        source_name = str(row["source_name"] or "").strip()
        if source_name:
            return f"{row['source_kind']}:{source_name}"
        return str(row["source_kind"])

    @staticmethod
    def _verify_resolution_row(
        conn: sqlite3.Connection,
        resolution_row: sqlite3.Row,
    ) -> tuple[sqlite3.Row, str]:
        basis = json.loads(str(resolution_row["resolution_basis_json"]))
        if _digest(basis) != str(resolution_row["resolution_hash"]):
            raise EventEvidenceContractError(
                "EVENT_QUALITY_RESOLUTION_INTEGRITY_MISMATCH",
                "Event Resolution hash가 저장 내용과 일치하지 않습니다.",
            )
        group = conn.execute(
            """
            SELECT * FROM event_evidence_canonical_group
            WHERE canonical_event_id=? AND canonical_version=?
            """,
            (
                resolution_row["canonical_event_id"],
                resolution_row["canonical_version"],
            ),
        ).fetchone()
        if group is None:
            raise EventEvidenceContractError(
                "EVENT_QUALITY_CANONICAL_GROUP_MISSING",
                "Resolution이 참조하는 canonical group이 없습니다.",
            )
        group_payload = {
            "contract_version": str(group["resolution_contract_version"]),
            "canonical_event_id": str(group["canonical_event_id"]),
            "canonical_version": int(group["canonical_version"]),
            "representative_event_id": str(group["representative_event_id"]),
            "representative_event_version": int(
                group["representative_event_version"]
            ),
            "resolution_method": str(group["resolution_method"]),
            "resolution_confidence": str(group["resolution_confidence"]),
            "canonical_fingerprint": str(group["canonical_fingerprint"]),
        }
        if _digest(group_payload) != str(group["canonical_hash"]):
            raise EventEvidenceContractError(
                "EVENT_QUALITY_CANONICAL_INTEGRITY_MISMATCH",
                "Canonical Event hash가 저장 내용과 일치하지 않습니다.",
            )
        return group, str(resolution_row["resolution_type"])

    @staticmethod
    def _direct_entity_keys_as_of(
        conn: sqlite3.Connection,
        *,
        event_id: str,
        event_version: int,
        cutoff: datetime,
    ) -> set[str]:
        rows = conn.execute(
            """
            SELECT e.entity_key,r.evidence_as_of
            FROM event_evidence_entity_relevance r
            JOIN event_evidence_entity e ON e.entity_id=r.entity_id
            WHERE r.event_id=? AND r.event_version=?
              AND r.relation_type='DIRECT_COMPANY'
              AND r.relevance_state IN ('CONFIRMED','SUPPORTED')
            """,
            (event_id, event_version),
        ).fetchall()
        return {
            str(row["entity_key"])
            for row in rows
            if _parse_aware(str(row["evidence_as_of"]), "evidence_as_of")
            <= cutoff
        }

    @staticmethod
    def _source_identity_as_of(
        conn: sqlite3.Connection,
        *,
        event_id: str,
        event_version: int,
        cutoff: datetime,
    ) -> tuple[set[str], set[str]]:
        rows = conn.execute(
            """
            SELECT sr.source_kind,sr.source_native_id,sr.content_hash,
                   sr.available_at
            FROM event_evidence_record_source rs
            JOIN event_evidence_source_ref sr
              ON sr.source_ref_id=rs.source_ref_id
            WHERE rs.event_id=? AND rs.event_version=?
            """,
            (event_id, event_version),
        ).fetchall()
        visible = [
            row
            for row in rows
            if _parse_aware(str(row["available_at"]), "source.available_at")
            <= cutoff
        ]
        return (
            {
                f"{row['source_kind']}:{row['source_native_id']}"
                for row in visible
            },
            {str(row["content_hash"]) for row in visible},
        )

    def _unresolved_duplicate_state(
        self,
        conn: sqlite3.Connection,
        *,
        event_row: sqlite3.Row,
        cutoff_text: str,
        cutoff: datetime,
    ) -> tuple[str, list[str]]:
        target_id = str(event_row["event_id"])
        target_version = int(event_row["event_version"])
        target_payload = json.loads(str(event_row["event_payload_json"]))
        target_stable = _stable_ids(target_payload)
        target_direct = self._direct_entity_keys_as_of(
            conn,
            event_id=target_id,
            event_version=target_version,
            cutoff=cutoff,
        )
        target_native, target_hashes = self._source_identity_as_of(
            conn,
            event_id=target_id,
            event_version=target_version,
            cutoff=cutoff,
        )
        target_date = _event_date(
            event_row["event_time"] or event_row["available_at"]
        )

        candidate_ids = {
            str(row["event_id"])
            for row in conn.execute(
                """
                SELECT event_id,available_at FROM event_evidence_record
                WHERE event_id<>? AND event_type=?
                """,
                (target_id, event_row["event_type"]),
            ).fetchall()
            if _parse_aware(str(row["available_at"]), "candidate.available_at")
            <= cutoff
        }

        found_candidate = False
        found_exact = False
        bases: list[str] = []
        for candidate_id in sorted(candidate_ids):
            resolved = self.resolver.resolve_event_as_of(
                candidate_id,
                cutoff_text,
            )
            if resolved is None:
                continue
            candidate_version = int(resolved["event_version"])
            candidate_direct = self._direct_entity_keys_as_of(
                conn,
                event_id=candidate_id,
                event_version=candidate_version,
                cutoff=cutoff,
            )
            if target_direct and candidate_direct and target_direct.isdisjoint(
                candidate_direct
            ):
                continue

            candidate_payload = dict(resolved["event_payload"])
            candidate_stable = _stable_ids(candidate_payload)
            candidate_native, candidate_hashes = self._source_identity_as_of(
                conn,
                event_id=candidate_id,
                event_version=candidate_version,
                cutoff=cutoff,
            )

            shared_stable = target_stable & candidate_stable
            shared_native = target_native & candidate_native
            shared_hash = target_hashes & candidate_hashes
            if shared_stable or shared_native or shared_hash:
                found_exact = True
                bases.append(
                    "OFFICIAL_IDENTITY_MATCH"
                    if shared_stable
                    else (
                        "SOURCE_NATIVE_ID_MATCH"
                        if shared_native
                        else "SOURCE_CONTENT_HASH_MATCH"
                    )
                )
                continue

            candidate_date = _event_date(
                resolved["event_time"] or resolved["available_at"]
            )
            if (
                target_direct
                and candidate_direct
                and bool(target_direct & candidate_direct)
                and target_date is not None
                and target_date == candidate_date
            ):
                found_candidate = True
                bases.append("TYPE_ENTITY_DATE_MATCH_WITHOUT_STABLE_IDENTITY")

        if found_exact:
            return "UNRESOLVED", sorted(set(bases))
        if found_candidate:
            return "CANDIDATE_DUPLICATE", sorted(set(bases))
        return "DISTINCT", []

    @staticmethod
    def _assessment_id(
        *,
        scope: EvidenceQualityScope,
        assessment_as_of: str,
        event_id: str,
        event_version: int,
        entity_id: str,
        relevance_id: str,
    ) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                (
                    "stockscope:event-quality:"
                    f"{EVENT_EVIDENCE_QUALITY_CONTRACT_VERSION}:"
                    f"{scope.value}:{assessment_as_of}:"
                    f"{event_id}:{event_version}:{entity_id}:{relevance_id}"
                ),
            )
        )

    def assess_event_entity(
        self,
        *,
        event_id: str,
        entity_id: str,
        assessment_scope: EvidenceQualityScope | str,
        assessment_as_of: str,
        relevance_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            scope = (
                assessment_scope
                if isinstance(assessment_scope, EvidenceQualityScope)
                else EvidenceQualityScope(str(assessment_scope))
            )
        except ValueError as exc:
            raise EventEvidenceContractError(
                "EVENT_QUALITY_SCOPE_INVALID",
                f"알 수 없는 quality assessment scope입니다: {assessment_scope}",
            ) from exc
        cutoff = _parse_aware(assessment_as_of, "assessment_as_of")
        canonical_as_of = cutoff.isoformat()

        resolved = self.resolver.resolve_event_as_of(event_id, canonical_as_of)
        future_event = resolved is None

        with self._connect() as conn:
            self._require_ready(conn)
            entity_row = self._entity_row(conn, entity_id)

            if resolved is None:
                event_row = conn.execute(
                    """
                    SELECT * FROM event_evidence_record
                    WHERE event_id=?
                    ORDER BY event_version
                    LIMIT 1
                    """,
                    (event_id,),
                ).fetchone()
                if event_row is None:
                    raise EventEvidenceContractError(
                        "EVENT_EVIDENCE_NOT_FOUND",
                        "Event Evidence revision을 찾을 수 없습니다.",
                    )
                event_version = int(event_row["event_version"])
            else:
                event_version = int(resolved["event_version"])
                event_row = self._event_row(conn, event_id, event_version)

            relevance_rows = self._relevance_rows(
                conn,
                event_id=event_id,
                event_version=event_version,
                entity_id=entity_id,
                relevance_id=relevance_id,
            )
            if not relevance_rows:
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_RELEVANCE_NOT_FOUND",
                    "해당 Event revision과 Entity를 연결하는 Relevance가 없습니다.",
                )
            if len(relevance_rows) > 1 and relevance_id is None:
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_RELEVANCE_AMBIGUOUS",
                    "같은 Event/Entity에 여러 relation이 있어 relevance_id 지정이 필요합니다.",
                )
            relevance_row = relevance_rows[0]

            blocking: list[str] = []
            limitations: list[str] = []
            insufficient: list[str] = []
            integrity_state = "MATCH"

            try:
                self.store.verify_event_revision(event_id, event_version)
                self._verify_entity_and_relevance(
                    event_row,
                    entity_row,
                    relevance_row,
                )
            except EventEvidenceContractError:
                integrity_state = "MISMATCH"
                blocking.append("INTEGRITY_MISMATCH")

            if future_event:
                blocking.append("FUTURE_EVIDENCE")

            if _parse_aware(
                str(entity_row["identity_as_of"]),
                "identity_as_of",
            ) > cutoff:
                blocking.append("FUTURE_ENTITY_IDENTITY")

            relevance_as_of = _parse_aware(
                str(relevance_row["evidence_as_of"]),
                "evidence_as_of",
            )
            if relevance_as_of > cutoff:
                blocking.append("FUTURE_RELEVANCE")

            source_rows = self._source_rows(
                conn,
                event_id=event_id,
                event_version=event_version,
            )
            visible_sources = [
                row
                for row in source_rows
                if _parse_aware(
                    str(row["available_at"]),
                    "source.available_at",
                ) <= cutoff
            ]
            if not visible_sources:
                blocking.append("SOURCE_NOT_AVAILABLE_AS_OF")
            if len(visible_sources) != len(source_rows) and not future_event:
                blocking.append("SOURCE_NOT_AVAILABLE_AS_OF")

            rights_state = "ALLOWED"
            for row in visible_sources:
                try:
                    policy_payload = json.loads(str(row["policy_json"]))
                    if _digest(policy_payload) != str(row["policy_hash"]):
                        raise ValueError("policy hash mismatch")
                except (ValueError, json.JSONDecodeError):
                    if "INTEGRITY_MISMATCH" not in blocking:
                        blocking.append("INTEGRITY_MISMATCH")
                    integrity_state = "MISMATCH"
                    continue
                if not bool(row["derived_retention_allowed"]):
                    rights_state = "BLOCKED"
                    blocking.append("REFERENCE_RIGHTS_NOT_ALLOWED")
                if (
                    scope is EvidenceQualityScope.HISTORICAL_EVALUATION
                    and not bool(row["historical_evaluation_allowed"])
                ):
                    rights_state = "BLOCKED"
                    blocking.append(
                        "HISTORICAL_EVALUATION_RIGHTS_NOT_ALLOWED"
                    )

            time_quality = str(event_row["time_quality"])
            temporal_state = "ELIGIBLE"
            if scope is EvidenceQualityScope.HISTORICAL_EVALUATION:
                if time_quality == "DATE_ONLY":
                    temporal_state = "BLOCKED"
                    blocking.append("TIME_DATE_ONLY")
                elif time_quality == "INFERRED":
                    temporal_state = "BLOCKED"
                    blocking.append("TIME_INFERRED")
                elif time_quality == "UNKNOWN":
                    temporal_state = "BLOCKED"
                    blocking.append("TIME_UNKNOWN")
            else:
                if time_quality == "DATE_ONLY":
                    temporal_state = "LIMITED"
                    limitations.append("TIME_DATE_ONLY")
                elif time_quality == "INFERRED":
                    temporal_state = "LIMITED"
                    limitations.append("TIME_INFERRED")
                elif time_quality == "UNKNOWN":
                    temporal_state = "INSUFFICIENT"
                    insufficient.append("TIME_UNKNOWN")

            relevance_state = str(relevance_row["relevance_state"])
            if relevance_state == "REJECTED":
                blocking.append("RELEVANCE_REJECTED")
            elif relevance_state == "WEAK":
                insufficient.append("RELEVANCE_WEAK")
            elif relevance_state == "UNKNOWN":
                insufficient.append("RELEVANCE_UNKNOWN")
            elif relevance_state == "SUPPORTED":
                limitations.append("SUPPORTED_RELATION")

            revision_state = str(event_row["event_state"])
            if revision_state == "WITHDRAWN":
                blocking.append("EVENT_WITHDRAWN")
            elif revision_state == "SUPERSEDED":
                blocking.append("EVENT_SUPERSEDED")

            resolution_row = conn.execute(
                """
                SELECT * FROM event_evidence_resolution
                WHERE event_id=? AND event_version=?
                """,
                (event_id, event_version),
            ).fetchone()
            canonical_event_id: str | None = None
            canonical_version: int | None = None
            canonical_hash: str | None = None
            resolution_hash: str | None = None
            resolution_state = "DISTINCT"
            if resolution_row is not None:
                try:
                    group, resolution_state = self._verify_resolution_row(
                        conn,
                        resolution_row,
                    )
                    canonical_event_id = str(group["canonical_event_id"])
                    canonical_version = int(group["canonical_version"])
                    canonical_hash = str(group["canonical_hash"])
                    resolution_hash = str(resolution_row["resolution_hash"])
                except EventEvidenceContractError:
                    integrity_state = "MISMATCH"
                    if "INTEGRITY_MISMATCH" not in blocking:
                        blocking.append("INTEGRITY_MISMATCH")
                    resolution_state = "UNRESOLVED"
            else:
                resolution_state, duplicate_bases = (
                    self._unresolved_duplicate_state(
                        conn,
                        event_row=event_row,
                        cutoff_text=canonical_as_of,
                        cutoff=cutoff,
                    )
                )
                if resolution_state == "UNRESOLVED":
                    limitations.append("DUPLICATE_UNRESOLVED")
                elif resolution_state == "CANDIDATE_DUPLICATE":
                    limitations.append("CANDIDATE_DUPLICATE")
                if duplicate_bases:
                    limitations.extend(
                        f"DUPLICATE_BASIS:{basis}" for basis in duplicate_bases
                    )

            source_count = len(visible_sources)
            origins = {
                self._source_origin(row)
                for row in visible_sources
            }
            distinct_source_origin_count = len(origins)
            if source_count == 0:
                corroboration_state = "UNKNOWN"
            elif source_count == 1:
                corroboration_state = "SINGLE_SOURCE"
                limitations.append("SINGLE_SOURCE_ONLY")
            else:
                corroboration_state = "MULTI_SOURCE"

            policy_bundle_hash = self._policy_bundle_hash(visible_sources)
            source_refs = [
                {
                    "source_ref_id": str(row["source_ref_id"]),
                    "source_ref_hash": str(row["source_ref_hash"]),
                    "rights_policy_id": str(row["rights_policy_id"]),
                    "policy_hash": str(row["policy_hash"]),
                }
                for row in visible_sources
            ]

            blocking = sorted(set(blocking))
            limitations = sorted(set(limitations))
            insufficient = sorted(set(insufficient))
            state_limitation_prefixes = (
                "TIME_DATE_ONLY",
                "TIME_INFERRED",
                "SUPPORTED_RELATION",
                "DUPLICATE_UNRESOLVED",
                "CANDIDATE_DUPLICATE",
            )
            state_limited = any(
                reason.startswith(state_limitation_prefixes)
                for reason in limitations
            )
            if blocking:
                quality_state = EvidenceQualityState.BLOCKED
            elif insufficient:
                quality_state = EvidenceQualityState.INSUFFICIENT
            elif state_limited:
                quality_state = EvidenceQualityState.LIMITED
            else:
                quality_state = EvidenceQualityState.USABLE

            assessment_id = self._assessment_id(
                scope=scope,
                assessment_as_of=canonical_as_of,
                event_id=event_id,
                event_version=event_version,
                entity_id=entity_id,
                relevance_id=str(relevance_row["relevance_id"]),
            )
            quality_payload = {
                "quality_contract_version": (
                    EVENT_EVIDENCE_QUALITY_CONTRACT_VERSION
                ),
                "assessment_id": assessment_id,
                "assessment_scope": scope.value,
                "assessment_as_of": canonical_as_of,
                "event_id": event_id,
                "event_version": event_version,
                "event_hash": str(event_row["event_hash"]),
                "source_bundle_hash": str(event_row["source_bundle_hash"]),
                "entity_id": entity_id,
                "entity_hash": str(entity_row["identity_hash"]),
                "relevance_id": str(relevance_row["relevance_id"]),
                "relevance_hash": str(relevance_row["relation_hash"]),
                "relation_type": str(relevance_row["relation_type"]),
                "rights_policy_bundle_hash": policy_bundle_hash,
                "canonical_event_id": canonical_event_id,
                "canonical_version": canonical_version,
                "canonical_hash": canonical_hash,
                "resolution_hash": resolution_hash,
                "components": {
                    "rights_state": rights_state,
                    "integrity_state": integrity_state,
                    "temporal_state": temporal_state,
                    "time_quality": time_quality,
                    "relevance_state": relevance_state,
                    "resolution_state": resolution_state,
                    "revision_state": revision_state,
                    "corroboration_state": corroboration_state,
                },
                "source_count": source_count,
                "distinct_source_origin_count": distinct_source_origin_count,
                "source_refs": source_refs,
                "quality_state": quality_state.value,
                "blocking_reasons": blocking,
                "insufficient_reasons": insufficient,
                "limitations": limitations,
            }
            quality_json = _canonical_json(quality_payload)
            quality_hash = _digest(quality_payload)

            existing = conn.execute(
                """
                SELECT quality_hash,quality_json
                FROM event_evidence_quality_assessment
                WHERE assessment_id=?
                """,
                (assessment_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["quality_hash"]) == quality_hash
                    and str(existing["quality_json"]) == quality_json
                ):
                    conn.commit()
                    return self.get_assessment(assessment_id)
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_IDENTITY_CONFLICT",
                    "같은 Quality Assessment identity가 다른 결과로 이미 저장되어 있습니다.",
                )

            conn.execute(
                """
                INSERT INTO event_evidence_quality_assessment(
                    assessment_id,quality_contract_version,
                    assessment_scope,assessment_as_of,
                    event_id,event_version,event_hash,source_bundle_hash,
                    entity_id,entity_hash,relevance_id,relevance_hash,
                    relation_type,rights_policy_bundle_hash,
                    canonical_event_id,canonical_version,
                    canonical_hash,resolution_hash,
                    rights_state,integrity_state,temporal_state,
                    relevance_state,resolution_state,revision_state,
                    corroboration_state,source_count,
                    distinct_source_origin_count,quality_state,
                    blocking_reasons_json,insufficient_reasons_json,
                    limitations_json,quality_json,quality_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    assessment_id,
                    EVENT_EVIDENCE_QUALITY_CONTRACT_VERSION,
                    scope.value,
                    canonical_as_of,
                    event_id,
                    event_version,
                    str(event_row["event_hash"]),
                    str(event_row["source_bundle_hash"]),
                    entity_id,
                    str(entity_row["identity_hash"]),
                    str(relevance_row["relevance_id"]),
                    str(relevance_row["relation_hash"]),
                    str(relevance_row["relation_type"]),
                    policy_bundle_hash,
                    canonical_event_id,
                    canonical_version,
                    canonical_hash,
                    resolution_hash,
                    rights_state,
                    integrity_state,
                    temporal_state,
                    relevance_state,
                    resolution_state,
                    revision_state,
                    corroboration_state,
                    source_count,
                    distinct_source_origin_count,
                    quality_state.value,
                    _canonical_json(blocking),
                    _canonical_json(insufficient),
                    _canonical_json(limitations),
                    quality_json,
                    quality_hash,
                    self.clock(),
                ),
            )
            conn.commit()
        return self.get_assessment(assessment_id)

    def get_assessment(self, assessment_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_quality_assessment
                WHERE assessment_id=?
                """,
                (assessment_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_NOT_FOUND",
                    "Evidence Quality Assessment를 찾을 수 없습니다.",
                )
            return {
                "assessment_id": str(row["assessment_id"]),
                "assessment_scope": str(row["assessment_scope"]),
                "assessment_as_of": str(row["assessment_as_of"]),
                "event_id": str(row["event_id"]),
                "event_version": int(row["event_version"]),
                "entity_id": str(row["entity_id"]),
                "relevance_id": str(row["relevance_id"]),
                "relation_type": str(row["relation_type"]),
                "quality_state": str(row["quality_state"]),
                "rights_state": str(row["rights_state"]),
                "integrity_state": str(row["integrity_state"]),
                "temporal_state": str(row["temporal_state"]),
                "relevance_state": str(row["relevance_state"]),
                "resolution_state": str(row["resolution_state"]),
                "revision_state": str(row["revision_state"]),
                "corroboration_state": str(row["corroboration_state"]),
                "source_count": int(row["source_count"]),
                "distinct_source_origin_count": int(
                    row["distinct_source_origin_count"]
                ),
                "blocking_reasons": json.loads(
                    str(row["blocking_reasons_json"])
                ),
                "insufficient_reasons": json.loads(
                    str(row["insufficient_reasons_json"])
                ),
                "limitations": json.loads(str(row["limitations_json"])),
                "quality_hash": str(row["quality_hash"]),
                "quality": json.loads(str(row["quality_json"])),
                "created_at": str(row["created_at"]),
            }

    def list_assessments(
        self,
        *,
        event_id: str | None = None,
        entity_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if event_id is not None:
            clauses.append("event_id=?")
            params.append(event_id)
        if entity_id is not None:
            clauses.append("entity_id=?")
            params.append(entity_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            self._require_ready(conn)
            rows = conn.execute(
                """
                SELECT assessment_id
                FROM event_evidence_quality_assessment
                """
                + where
                + " ORDER BY assessment_as_of,assessment_id",
                tuple(params),
            ).fetchall()
        return [
            self.get_assessment(str(row["assessment_id"]))
            for row in rows
        ]

    def verify_assessment(self, assessment_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_quality_assessment
                WHERE assessment_id=?
                """,
                (assessment_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_NOT_FOUND",
                    "Evidence Quality Assessment를 찾을 수 없습니다.",
                )
            payload = json.loads(str(row["quality_json"]))
            if _digest(payload) != str(row["quality_hash"]):
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_INTEGRITY_MISMATCH",
                    "Quality Assessment hash가 저장 내용과 일치하지 않습니다.",
                )

            event = self._event_row(
                conn,
                str(row["event_id"]),
                int(row["event_version"]),
            )
            entity = self._entity_row(conn, str(row["entity_id"]))
            relevance = conn.execute(
                """
                SELECT * FROM event_evidence_entity_relevance
                WHERE relevance_id=?
                """,
                (row["relevance_id"],),
            ).fetchone()
            if relevance is None:
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_RELEVANCE_NOT_FOUND",
                    "Assessment가 참조하는 Relevance가 없습니다.",
                )

            if str(event["event_hash"]) != str(row["event_hash"]):
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_EVENT_HASH_MISMATCH",
                    "Assessment의 Event hash pin이 현재 immutable Event와 다릅니다.",
                )
            if str(event["source_bundle_hash"]) != str(
                row["source_bundle_hash"]
            ):
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_SOURCE_BUNDLE_MISMATCH",
                    "Assessment의 source bundle hash pin이 다릅니다.",
                )
            if str(entity["identity_hash"]) != str(row["entity_hash"]):
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_ENTITY_HASH_MISMATCH",
                    "Assessment의 Entity hash pin이 다릅니다.",
                )
            if str(relevance["relation_hash"]) != str(row["relevance_hash"]):
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_RELEVANCE_HASH_MISMATCH",
                    "Assessment의 Relevance hash pin이 다릅니다.",
                )

            source_refs = list(payload.get("source_refs") or [])
            current_policy_bundle: list[dict[str, str]] = []
            for item in source_refs:
                source = conn.execute(
                    """
                    SELECT sr.source_ref_hash,sr.rights_policy_id,
                           p.policy_hash,p.policy_json
                    FROM event_evidence_source_ref sr
                    JOIN event_evidence_policy_snapshot p
                      ON p.policy_id=sr.rights_policy_id
                    WHERE sr.source_ref_id=?
                    """,
                    (item["source_ref_id"],),
                ).fetchone()
                if source is None:
                    raise EventEvidenceContractError(
                        "EVENT_QUALITY_SOURCE_REF_MISSING",
                        "Assessment가 pin한 SourceRef가 없습니다.",
                    )
                if str(source["source_ref_hash"]) != str(
                    item["source_ref_hash"]
                ):
                    raise EventEvidenceContractError(
                        "EVENT_QUALITY_SOURCE_REF_HASH_MISMATCH",
                        "Assessment의 SourceRef hash pin이 다릅니다.",
                    )
                if str(source["rights_policy_id"]) != str(
                    item["rights_policy_id"]
                ):
                    raise EventEvidenceContractError(
                        "EVENT_QUALITY_POLICY_REFERENCE_MISMATCH",
                        "Assessment의 rights policy reference가 다릅니다.",
                    )
                policy_payload = json.loads(str(source["policy_json"]))
                if _digest(policy_payload) != str(source["policy_hash"]):
                    raise EventEvidenceContractError(
                        "EVENT_QUALITY_POLICY_INTEGRITY_MISMATCH",
                        "Assessment가 참조하는 policy snapshot hash가 깨졌습니다.",
                    )
                if str(source["policy_hash"]) != str(item["policy_hash"]):
                    raise EventEvidenceContractError(
                        "EVENT_QUALITY_POLICY_HASH_MISMATCH",
                        "Assessment의 policy hash pin이 다릅니다.",
                    )
                current_policy_bundle.append(
                    {
                        "policy_id": str(source["rights_policy_id"]),
                        "policy_hash": str(source["policy_hash"]),
                    }
                )

            unique_policy_bundle = {
                (item["policy_id"], item["policy_hash"])
                for item in current_policy_bundle
            }
            expected_policy_hash = _digest(
                [
                    {"policy_id": policy_id, "policy_hash": policy_hash}
                    for policy_id, policy_hash in sorted(unique_policy_bundle)
                ]
            )
            if expected_policy_hash != str(row["rights_policy_bundle_hash"]):
                raise EventEvidenceContractError(
                    "EVENT_QUALITY_POLICY_BUNDLE_MISMATCH",
                    "Assessment의 rights policy bundle hash가 다릅니다.",
                )

            if row["canonical_event_id"] is not None:
                resolution = conn.execute(
                    """
                    SELECT * FROM event_evidence_resolution
                    WHERE event_id=? AND event_version=?
                    """,
                    (row["event_id"], row["event_version"]),
                ).fetchone()
                if resolution is None:
                    raise EventEvidenceContractError(
                        "EVENT_QUALITY_RESOLUTION_MISSING",
                        "Assessment가 pin한 Resolution이 없습니다.",
                    )
                group, _ = self._verify_resolution_row(conn, resolution)
                if str(group["canonical_hash"]) != str(row["canonical_hash"]):
                    raise EventEvidenceContractError(
                        "EVENT_QUALITY_CANONICAL_HASH_MISMATCH",
                        "Assessment의 canonical hash pin이 다릅니다.",
                    )
                if str(resolution["resolution_hash"]) != str(
                    row["resolution_hash"]
                ):
                    raise EventEvidenceContractError(
                        "EVENT_QUALITY_RESOLUTION_HASH_MISMATCH",
                        "Assessment의 resolution hash pin이 다릅니다.",
                    )

            return {
                "status": "MATCH",
                "assessment_id": str(row["assessment_id"]),
                "quality_hash": str(row["quality_hash"]),
                "quality_state": str(row["quality_state"]),
            }
