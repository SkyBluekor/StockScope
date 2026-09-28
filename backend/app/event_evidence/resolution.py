from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from app.event_evidence.entity import EventEntityService
from app.event_evidence.errors import EventEvidenceContractError


EVENT_RESOLUTION_CONTRACT_VERSION = "VN_P6_S1_EVENT_RESOLUTION_V1"

RESOLUTION_TABLES = frozenset(
    {
        "event_evidence_canonical_group",
        "event_evidence_resolution",
    }
)


class DuplicateClassification(str, Enum):
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    SAME_EVENT_CANDIDATE = "SAME_EVENT_CANDIDATE"
    DISTINCT = "DISTINCT"


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
            "EVENT_RESOLUTION_JSON_INVALID",
            "Event Resolution payload는 canonical JSON으로 직렬화할 수 있어야 합니다.",
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
            "EVENT_RESOLUTION_TIME_INVALID",
            f"{field_name}은 timezone이 포함된 ISO-8601 시각이어야 합니다.",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventEvidenceContractError(
            "EVENT_RESOLUTION_TIMEZONE_REQUIRED",
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


class EventResolutionService:
    def __init__(
        self,
        simulation_db: Path,
        *,
        clock: Callable[[], str],
    ) -> None:
        self.simulation_db = Path(simulation_db)
        self.clock = clock
        self.entities = EventEntityService(simulation_db, clock=clock)

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
        required = RESOLUTION_TABLES | {
            "event_evidence_record",
            "event_evidence_record_source",
            "event_evidence_source_ref",
            "event_evidence_entity",
            "event_evidence_entity_relevance",
        }
        missing = sorted(required - self._tables(conn))
        if missing:
            raise EventEvidenceContractError(
                "EVENT_RESOLUTION_MIGRATION_REQUIRED",
                "P6 Event Resolution schema가 준비되지 않았습니다: "
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
    def _source_identity(
        conn: sqlite3.Connection,
        event_id: str,
        event_version: int,
    ) -> tuple[set[str], set[str]]:
        rows = conn.execute(
            """
            SELECT sr.source_kind,sr.source_native_id,sr.content_hash
            FROM event_evidence_record_source rs
            JOIN event_evidence_source_ref sr
              ON sr.source_ref_id=rs.source_ref_id
            WHERE rs.event_id=? AND rs.event_version=?
            """,
            (event_id, event_version),
        ).fetchall()
        native = {
            f"{row['source_kind']}:{row['source_native_id']}"
            for row in rows
        }
        hashes = {str(row["content_hash"]) for row in rows}
        return native, hashes

    @staticmethod
    def _direct_entities(
        conn: sqlite3.Connection,
        event_id: str,
        event_version: int,
    ) -> set[str]:
        rows = conn.execute(
            """
            SELECT e.entity_key
            FROM event_evidence_entity_relevance r
            JOIN event_evidence_entity e ON e.entity_id=r.entity_id
            WHERE r.event_id=? AND r.event_version=?
              AND r.relation_type='DIRECT_COMPANY'
              AND r.relevance_state IN ('CONFIRMED','SUPPORTED')
            """,
            (event_id, event_version),
        ).fetchall()
        return {str(row["entity_key"]) for row in rows}

    def _context(
        self,
        conn: sqlite3.Connection,
        event_id: str,
        event_version: int,
    ) -> dict[str, Any]:
        row = self._event_row(conn, event_id, event_version)
        payload = json.loads(str(row["event_payload_json"]))
        native_ids, content_hashes = self._source_identity(
            conn,
            event_id,
            event_version,
        )
        direct_entities = self._direct_entities(
            conn,
            event_id,
            event_version,
        )
        stable_ids = _stable_ids(payload)
        fingerprint_payload = {
            "event_type": str(row["event_type"]),
            "direct_entities": sorted(direct_entities),
            "event_date": _event_date(row["event_time"] or row["available_at"]),
            "stable_identifiers": sorted(stable_ids),
            "core_facts": payload.get("core_facts")
            if isinstance(payload.get("core_facts"), dict)
            else None,
        }
        return {
            "row": row,
            "payload": payload,
            "native_ids": native_ids,
            "content_hashes": content_hashes,
            "direct_entities": direct_entities,
            "stable_ids": stable_ids,
            "fingerprint_payload": fingerprint_payload,
            "fingerprint": _digest(fingerprint_payload),
        }

    def classify_duplicate(
        self,
        event_a_id: str,
        event_a_version: int,
        event_b_id: str,
        event_b_version: int,
    ) -> dict[str, Any]:
        if (
            event_a_id == event_b_id
            and event_a_version == event_b_version
        ):
            return {
                "classification": DuplicateClassification.EXACT_DUPLICATE.value,
                "basis": "SAME_EVENT_REVISION",
            }

        with self._connect() as conn:
            self._require_ready(conn)
            a = self._context(conn, event_a_id, event_a_version)
            b = self._context(conn, event_b_id, event_b_version)

        type_a = str(a["row"]["event_type"])
        type_b = str(b["row"]["event_type"])
        if type_a != type_b:
            return {
                "classification": DuplicateClassification.DISTINCT.value,
                "basis": "EVENT_TYPE_DIFFERS",
                "fingerprint_a": a["fingerprint"],
                "fingerprint_b": b["fingerprint"],
            }

        direct_a = a["direct_entities"]
        direct_b = b["direct_entities"]
        if direct_a and direct_b and direct_a.isdisjoint(direct_b):
            return {
                "classification": DuplicateClassification.DISTINCT.value,
                "basis": "DIRECT_ENTITY_DIFFERS",
                "fingerprint_a": a["fingerprint"],
                "fingerprint_b": b["fingerprint"],
            }

        shared_stable = a["stable_ids"] & b["stable_ids"]
        shared_native = a["native_ids"] & b["native_ids"]
        shared_content = a["content_hashes"] & b["content_hashes"]

        if shared_stable:
            core_a = a["payload"].get("core_facts")
            core_b = b["payload"].get("core_facts")
            if (
                isinstance(core_a, dict)
                and isinstance(core_b, dict)
                and _canonical_json(core_a) != _canonical_json(core_b)
            ):
                raise EventEvidenceContractError(
                    "CONFLICTING_SOURCE_FACTS",
                    "동일 official identity의 core facts가 서로 충돌합니다.",
                )
            return {
                "classification": DuplicateClassification.EXACT_DUPLICATE.value,
                "basis": "OFFICIAL_IDENTITY_MATCH",
                "shared_identity": sorted(shared_stable),
                "fingerprint_a": a["fingerprint"],
                "fingerprint_b": b["fingerprint"],
            }

        if shared_native or shared_content:
            return {
                "classification": DuplicateClassification.EXACT_DUPLICATE.value,
                "basis": (
                    "SOURCE_NATIVE_ID_MATCH"
                    if shared_native
                    else "SOURCE_CONTENT_HASH_MATCH"
                ),
                "fingerprint_a": a["fingerprint"],
                "fingerprint_b": b["fingerprint"],
            }

        date_a = _event_date(
            a["row"]["event_time"] or a["row"]["available_at"]
        )
        date_b = _event_date(
            b["row"]["event_time"] or b["row"]["available_at"]
        )
        if (
            direct_a
            and direct_b
            and bool(direct_a & direct_b)
            and date_a is not None
            and date_a == date_b
        ):
            return {
                "classification": DuplicateClassification.SAME_EVENT_CANDIDATE.value,
                "basis": "TYPE_ENTITY_DATE_MATCH_WITHOUT_STABLE_IDENTITY",
                "fingerprint_a": a["fingerprint"],
                "fingerprint_b": b["fingerprint"],
            }

        return {
            "classification": DuplicateClassification.DISTINCT.value,
            "basis": "NO_EXACT_IDENTITY_EVIDENCE",
            "fingerprint_a": a["fingerprint"],
            "fingerprint_b": b["fingerprint"],
        }

    @staticmethod
    def _group_id(event_id: str, event_version: int) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                (
                    "stockscope:canonical-event:"
                    f"{EVENT_RESOLUTION_CONTRACT_VERSION}:"
                    f"{event_id}:{event_version}"
                ),
            )
        )

    def _existing_resolution(
        self,
        conn: sqlite3.Connection,
        event_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT * FROM event_evidence_resolution
            WHERE event_id=?
            ORDER BY event_version
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()

    def resolve_duplicate(
        self,
        event_a_id: str,
        event_a_version: int,
        event_b_id: str,
        event_b_version: int,
    ) -> dict[str, Any]:
        classification = self.classify_duplicate(
            event_a_id,
            event_a_version,
            event_b_id,
            event_b_version,
        )
        if classification["classification"] != DuplicateClassification.EXACT_DUPLICATE.value:
            raise EventEvidenceContractError(
                "EVENT_DUPLICATE_NOT_EXACT",
                "EXACT_DUPLICATE만 canonical group으로 자동 병합할 수 있습니다.",
            )

        pair = sorted(
            [
                (event_a_id, event_a_version),
                (event_b_id, event_b_version),
            ]
        )
        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing_a = self._existing_resolution(conn, event_a_id)
            existing_b = self._existing_resolution(conn, event_b_id)
            group_ids = {
                str(row["canonical_event_id"])
                for row in (existing_a, existing_b)
                if row is not None
            }
            if len(group_ids) > 1:
                raise EventEvidenceContractError(
                    "EVENT_RESOLUTION_CONFLICT",
                    "두 Event가 이미 서로 다른 canonical group에 속해 있습니다.",
                )

            if group_ids:
                group_id = next(iter(group_ids))
                group = conn.execute(
                    """
                    SELECT * FROM event_evidence_canonical_group
                    WHERE canonical_event_id=? AND canonical_version=1
                    """,
                    (group_id,),
                ).fetchone()
                if group is None:
                    raise EventEvidenceContractError(
                        "EVENT_CANONICAL_GROUP_MISSING",
                        "기존 resolution이 참조하는 canonical group이 없습니다.",
                    )
                representative = (
                    str(group["representative_event_id"]),
                    int(group["representative_event_version"]),
                )
            else:
                representative = pair[0]
                group_id = self._group_id(*representative)
                rep_context = self._context(conn, *representative)
                group_payload = {
                    "contract_version": EVENT_RESOLUTION_CONTRACT_VERSION,
                    "canonical_event_id": group_id,
                    "canonical_version": 1,
                    "representative_event_id": representative[0],
                    "representative_event_version": representative[1],
                    "resolution_method": classification["basis"],
                    "resolution_confidence": "EXACT_IDENTITY",
                    "canonical_fingerprint": rep_context["fingerprint"],
                }
                canonical_hash = _digest(group_payload)
                conn.execute(
                    """
                    INSERT INTO event_evidence_canonical_group(
                        canonical_event_id,canonical_version,
                        resolution_contract_version,
                        representative_event_id,representative_event_version,
                        resolution_method,resolution_confidence,
                        canonical_fingerprint,canonical_hash,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        group_id,
                        1,
                        EVENT_RESOLUTION_CONTRACT_VERSION,
                        representative[0],
                        representative[1],
                        classification["basis"],
                        "EXACT_IDENTITY",
                        rep_context["fingerprint"],
                        canonical_hash,
                        self.clock(),
                    ),
                )

            for event_id, event_version in pair:
                current = self._existing_resolution(conn, event_id)
                if current is not None:
                    if str(current["canonical_event_id"]) != group_id:
                        raise EventEvidenceContractError(
                            "EVENT_RESOLUTION_CONFLICT",
                            "Event가 다른 canonical group에 이미 연결되어 있습니다.",
                        )
                    continue

                resolution_type = (
                    "CANONICAL"
                    if (event_id, event_version) == representative
                    else "EXACT_DUPLICATE"
                )
                basis = {
                    "contract_version": EVENT_RESOLUTION_CONTRACT_VERSION,
                    "classification": classification["classification"],
                    "basis": classification["basis"],
                    "representative_event_id": representative[0],
                    "representative_event_version": representative[1],
                }
                resolution_hash = _digest(basis)
                resolution_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        (
                            "stockscope:event-resolution:"
                            f"{EVENT_RESOLUTION_CONTRACT_VERSION}:"
                            f"{event_id}:{event_version}:{group_id}"
                        ),
                    )
                )
                conn.execute(
                    """
                    INSERT INTO event_evidence_resolution(
                        resolution_id,resolution_contract_version,
                        event_id,event_version,
                        canonical_event_id,canonical_version,
                        resolution_type,resolution_basis_json,
                        resolution_hash,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        resolution_id,
                        EVENT_RESOLUTION_CONTRACT_VERSION,
                        event_id,
                        event_version,
                        group_id,
                        1,
                        resolution_type,
                        _canonical_json(basis),
                        resolution_hash,
                        self.clock(),
                    ),
                )
            conn.commit()
        return self.get_canonical_event(group_id)

    def get_canonical_event(self, canonical_event_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            group = conn.execute(
                """
                SELECT * FROM event_evidence_canonical_group
                WHERE canonical_event_id=? AND canonical_version=1
                """,
                (canonical_event_id,),
            ).fetchone()
            if group is None:
                raise EventEvidenceContractError(
                    "EVENT_CANONICAL_GROUP_NOT_FOUND",
                    "Canonical Event group을 찾을 수 없습니다.",
                )
            members = conn.execute(
                """
                SELECT event_id,event_version,resolution_type,
                       resolution_hash,created_at
                FROM event_evidence_resolution
                WHERE canonical_event_id=? AND canonical_version=1
                ORDER BY event_id,event_version
                """,
                (canonical_event_id,),
            ).fetchall()
            return {
                "canonical_event_id": str(group["canonical_event_id"]),
                "canonical_version": int(group["canonical_version"]),
                "representative_event_id": str(group["representative_event_id"]),
                "representative_event_version": int(
                    group["representative_event_version"]
                ),
                "resolution_method": str(group["resolution_method"]),
                "resolution_confidence": str(group["resolution_confidence"]),
                "canonical_fingerprint": str(group["canonical_fingerprint"]),
                "canonical_hash": str(group["canonical_hash"]),
                "members": [
                    {
                        "event_id": str(row["event_id"]),
                        "event_version": int(row["event_version"]),
                        "resolution_type": str(row["resolution_type"]),
                        "resolution_hash": str(row["resolution_hash"]),
                    }
                    for row in members
                ],
            }

    def resolve_event_as_of(
        self,
        event_id: str,
        cutoff: str,
    ) -> dict[str, Any] | None:
        cutoff_dt = _parse_aware(cutoff, "cutoff")
        with self._connect() as conn:
            self._require_ready(conn)
            rows = conn.execute(
                """
                SELECT * FROM event_evidence_record
                WHERE event_id=?
                ORDER BY event_version
                """,
                (event_id,),
            ).fetchall()
            eligible = [
                row
                for row in rows
                if _parse_aware(str(row["available_at"]), "available_at")
                <= cutoff_dt
            ]
            if not eligible:
                return None
            current = max(eligible, key=lambda row: int(row["event_version"]))
            source_rows = conn.execute(
                """
                SELECT sr.source_ref_id,sr.source_kind,sr.source_native_id,
                       sr.source_ref_hash,sr.available_at
                FROM event_evidence_record_source rs
                JOIN event_evidence_source_ref sr
                  ON sr.source_ref_id=rs.source_ref_id
                WHERE rs.event_id=? AND rs.event_version=?
                ORDER BY sr.source_ref_id
                """,
                (event_id, int(current["event_version"])),
            ).fetchall()

        visible_sources = [
            {
                "source_ref_id": str(row["source_ref_id"]),
                "source_kind": str(row["source_kind"]),
                "source_native_id": str(row["source_native_id"]),
                "source_ref_hash": str(row["source_ref_hash"]),
                "available_at": str(row["available_at"]),
            }
            for row in source_rows
            if _parse_aware(str(row["available_at"]), "source.available_at")
            <= cutoff_dt
        ]
        entities = self.entities.list_event_entities(
            event_id,
            int(current["event_version"]),
            cutoff=cutoff,
        )
        return {
            "event_id": str(current["event_id"]),
            "event_version": int(current["event_version"]),
            "event_state": str(current["event_state"]),
            "supersedes_version": (
                int(current["supersedes_version"])
                if current["supersedes_version"] is not None
                else None
            ),
            "event_type": str(current["event_type"]),
            "scope": str(current["scope"]),
            "event_time": current["event_time"],
            "available_at": str(current["available_at"]),
            "time_quality": str(current["time_quality"]),
            "event_payload": json.loads(str(current["event_payload_json"])),
            "event_hash": str(current["event_hash"]),
            "visible_sources": visible_sources,
            "entities": entities,
            "as_of": cutoff,
        }

    def resolve_canonical_event_as_of(
        self,
        canonical_event_id: str,
        cutoff: str,
    ) -> dict[str, Any]:
        group = self.get_canonical_event(canonical_event_id)
        event_ids = sorted({member["event_id"] for member in group["members"]})
        resolved = [
            item
            for event_id in event_ids
            if (item := self.resolve_event_as_of(event_id, cutoff)) is not None
        ]
        source_map: dict[str, dict[str, Any]] = {}
        for event in resolved:
            for source in event["visible_sources"]:
                source_map[source["source_ref_id"]] = source
        return {
            **group,
            "as_of": cutoff,
            "visible_events": resolved,
            "visible_sources": [
                source_map[key] for key in sorted(source_map)
            ],
        }
