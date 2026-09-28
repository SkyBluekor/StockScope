from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.event_evidence.errors import EventEvidenceContractError
from app.event_evidence.models import (
    EventEvidenceSourceRef,
    EventRevisionIdentity,
)
from app.event_evidence.policy import (
    EvidenceCapability,
    EventEvidenceSourcePolicy,
)
from app.event_evidence.time import TemporalEvidence


EVENT_EVIDENCE_STORE_SCHEMA_VERSION = "VN_P6_S1_EVENT_EVIDENCE_STORE_V1"
EVENT_EVIDENCE_RECORD_VERSION = "VN_P6_S1_EVENT_RECORD_V1"
EVENT_EVIDENCE_HASH_CONTRACT_VERSION = "VN_P6_S1_EVENT_HASH_V1"

EVENT_EVIDENCE_TABLES = frozenset(
    {
        "event_evidence_schema_meta",
        "event_evidence_policy_snapshot",
        "event_evidence_source_ref",
        "event_evidence_record",
        "event_evidence_record_source",
    }
)

_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_BLOCKED_RAW_KEYS = frozenset(
    {
        "raw_content",
        "article_body",
        "full_article",
        "full_text",
        "document_text",
        "raw_html",
    }
)


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
            "EVENT_EVIDENCE_JSON_INVALID",
            "Event Evidence payload는 canonical JSON으로 직렬화할 수 있어야 합니다.",
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reject_raw_content(value: Any, *, path: str = "event_payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _BLOCKED_RAW_KEYS:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_RAW_CONTENT_FORBIDDEN",
                    f"{path}.{key}에는 원문/전문 데이터를 저장할 수 없습니다.",
                )
            _reject_raw_content(item, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_raw_content(item, path=f"{path}[{index}]")


def _identifier(value: str, field_name: str) -> str:
    normalized = str(value or "").strip().upper()
    if not _IDENTIFIER.fullmatch(normalized):
        raise EventEvidenceContractError(
            "EVENT_EVIDENCE_IDENTIFIER_INVALID",
            f"{field_name}은 대문자 영숫자/underscore identifier여야 합니다.",
        )
    return normalized


class EventEvidenceStore:
    """Immutable P6 event-evidence ledger.

    The store does not fetch external data, infer entity relevance, score news,
    alter Strategy/Risk/Scanner behavior, or grant data rights. A SourceRef can
    be persisted only when its exact policy explicitly permits DERIVED_RETENTION.
    """

    def __init__(
        self,
        simulation_db: Path,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.simulation_db = Path(simulation_db)
        self.clock = clock or _now

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
        missing = sorted(EVENT_EVIDENCE_TABLES - self._tables(conn))
        if missing:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_MIGRATION_REQUIRED",
                "P6 Event Evidence schema가 준비되지 않았습니다: "
                + ", ".join(missing),
            )
        row = conn.execute(
            """
            SELECT value FROM event_evidence_schema_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if row is None or str(row["value"]) != EVENT_EVIDENCE_STORE_SCHEMA_VERSION:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_SCHEMA_VERSION_MISMATCH",
                "P6 Event Evidence schema version이 현재 코드와 다릅니다.",
            )

    @staticmethod
    def _policy_payload(policy: EventEvidenceSourcePolicy) -> dict[str, Any]:
        return policy.to_dict()

    def _snapshot_policy(
        self,
        conn: sqlite3.Connection,
        policy: EventEvidenceSourcePolicy,
    ) -> tuple[str, str]:
        payload = self._policy_payload(policy)
        policy_json = _canonical_json(payload)
        policy_hash = _digest(payload)
        row = conn.execute(
            """
            SELECT policy_hash,policy_json
            FROM event_evidence_policy_snapshot
            WHERE policy_id=?
            """,
            (policy.policy_id,),
        ).fetchone()
        if row is not None:
            if (
                str(row["policy_hash"]) != policy_hash
                or str(row["policy_json"]) != policy_json
            ):
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_POLICY_IDENTITY_CONFLICT",
                    "같은 policy_id가 다른 내용으로 이미 저장되어 있습니다.",
                )
            return policy.policy_id, policy_hash

        conn.execute(
            """
            INSERT INTO event_evidence_policy_snapshot(
                policy_id,policy_contract_version,source_kind,policy_version,
                display_allowed,normalization_allowed,raw_retention_allowed,
                derived_retention_allowed,ai_transform_allowed,
                historical_evaluation_allowed,prediction_input_allowed,
                attribution_required,effective_from,policy_basis,
                policy_json,policy_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                policy.policy_id,
                policy.contract_version,
                policy.source_kind,
                policy.policy_version,
                int(policy.display_allowed),
                int(policy.normalization_allowed),
                int(policy.raw_retention_allowed),
                int(policy.derived_retention_allowed),
                int(policy.ai_transform_allowed),
                int(policy.historical_evaluation_allowed),
                int(policy.prediction_input_allowed),
                int(policy.attribution_required),
                policy.effective_from,
                policy.policy_basis,
                policy_json,
                policy_hash,
                self.clock(),
            ),
        )
        return policy.policy_id, policy_hash

    def snapshot_policy(
        self,
        policy: EventEvidenceSourcePolicy,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            policy_id, policy_hash = self._snapshot_policy(conn, policy)
            conn.commit()
            return {
                "policy_id": policy_id,
                "policy_hash": policy_hash,
                "policy": self._policy_payload(policy),
            }

    @staticmethod
    def _source_payload(ref: EventEvidenceSourceRef) -> dict[str, Any]:
        return ref.to_dict()

    def store_source_ref(
        self,
        *,
        policy: EventEvidenceSourcePolicy,
        source_ref: EventEvidenceSourceRef,
    ) -> dict[str, Any]:
        policy.require(EvidenceCapability.DERIVED_RETENTION)
        if source_ref.source_kind != policy.source_kind:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_POLICY_SOURCE_MISMATCH",
                "SourceRef source_kind가 rights policy source_kind와 다릅니다.",
            )
        if source_ref.rights_policy_id != policy.policy_id:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_POLICY_REFERENCE_MISMATCH",
                "SourceRef rights_policy_id가 전달된 policy와 다릅니다.",
            )

        payload = self._source_payload(source_ref)
        source_json = _canonical_json(payload)
        source_hash = _digest(payload)
        temporal = source_ref.temporal

        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            _, policy_hash = self._snapshot_policy(conn, policy)

            existing = conn.execute(
                """
                SELECT source_ref_hash,source_ref_json
                FROM event_evidence_source_ref
                WHERE source_ref_id=?
                """,
                (source_ref.source_ref_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["source_ref_hash"]) == source_hash
                    and str(existing["source_ref_json"]) == source_json
                ):
                    conn.commit()
                    return self.get_source_ref(source_ref.source_ref_id)
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_SOURCE_IDENTITY_CONFLICT",
                    "같은 source_ref_id가 다른 내용으로 이미 저장되어 있습니다.",
                )

            conn.execute(
                """
                INSERT INTO event_evidence_source_ref(
                    source_ref_id,source_ref_contract_version,
                    source_kind,source_native_id,
                    rights_policy_id,rights_policy_hash,
                    source_url,source_name,content_hash,
                    event_time,source_published_at,provider_published_at,
                    first_seen_at,available_at,fetched_at,corrected_at,
                    time_quality,temporal_contract_version,
                    source_ref_json,source_ref_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    source_ref.source_ref_id,
                    source_ref.contract_version,
                    source_ref.source_kind,
                    source_ref.source_native_id,
                    source_ref.rights_policy_id,
                    policy_hash,
                    source_ref.source_url,
                    source_ref.source_name,
                    source_ref.content_hash,
                    temporal.event_time,
                    temporal.source_published_at,
                    temporal.provider_published_at,
                    temporal.first_seen_at,
                    temporal.available_at,
                    temporal.fetched_at,
                    temporal.corrected_at,
                    temporal.time_quality.value,
                    temporal.contract_version,
                    source_json,
                    source_hash,
                    self.clock(),
                ),
            )
            conn.commit()

        return self.get_source_ref(source_ref.source_ref_id)

    def get_source_ref(self, source_ref_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_source_ref
                WHERE source_ref_id=?
                """,
                (source_ref_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_SOURCE_REF_NOT_FOUND",
                    "Event Evidence SourceRef를 찾을 수 없습니다.",
                )
            return {
                "source_ref_id": str(row["source_ref_id"]),
                "source_kind": str(row["source_kind"]),
                "source_native_id": str(row["source_native_id"]),
                "rights_policy_id": str(row["rights_policy_id"]),
                "rights_policy_hash": str(row["rights_policy_hash"]),
                "content_hash": str(row["content_hash"]),
                "source_ref_hash": str(row["source_ref_hash"]),
                "source": json.loads(str(row["source_ref_json"])),
                "created_at": str(row["created_at"]),
            }

    @staticmethod
    def _verify_source_row(
        conn: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> dict[str, Any]:
        source_payload = json.loads(str(row["source_ref_json"]))
        actual_source_hash = _digest(source_payload)
        if actual_source_hash != str(row["source_ref_hash"]):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_SOURCE_INTEGRITY_MISMATCH",
                "SourceRef hash가 저장 내용과 일치하지 않습니다.",
            )

        policy = conn.execute(
            """
            SELECT policy_json,policy_hash
            FROM event_evidence_policy_snapshot
            WHERE policy_id=?
            """,
            (row["rights_policy_id"],),
        ).fetchone()
        if policy is None:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_POLICY_SNAPSHOT_MISSING",
                "SourceRef가 참조하는 rights policy snapshot이 없습니다.",
            )
        actual_policy_hash = _digest(json.loads(str(policy["policy_json"])))
        if (
            actual_policy_hash != str(policy["policy_hash"])
            or str(row["rights_policy_hash"]) != str(policy["policy_hash"])
        ):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_POLICY_INTEGRITY_MISMATCH",
                "SourceRef rights policy hash가 snapshot과 일치하지 않습니다.",
            )
        return {
            "status": "MATCH",
            "source_ref_id": str(row["source_ref_id"]),
            "source_ref_hash": str(row["source_ref_hash"]),
            "rights_policy_id": str(row["rights_policy_id"]),
            "rights_policy_hash": str(row["rights_policy_hash"]),
        }

    def verify_source_ref(self, source_ref_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_source_ref
                WHERE source_ref_id=?
                """,
                (source_ref_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_SOURCE_REF_NOT_FOUND",
                    "Event Evidence SourceRef를 찾을 수 없습니다.",
                )
            return self._verify_source_row(conn, row)

    @staticmethod
    def _source_bundle(
        rows: list[sqlite3.Row],
    ) -> tuple[list[dict[str, str]], str]:
        bundle = sorted(
            (
                {
                    "source_ref_id": str(row["source_ref_id"]),
                    "source_ref_hash": str(row["source_ref_hash"]),
                }
                for row in rows
            ),
            key=lambda item: (item["source_ref_id"], item["source_ref_hash"]),
        )
        return bundle, _digest(bundle)

    def create_event_revision(
        self,
        *,
        identity: EventRevisionIdentity,
        event_type: str,
        scope: str,
        temporal: TemporalEvidence,
        event_payload: dict[str, Any],
        source_ref_ids: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        normalized_type = _identifier(event_type, "event_type")
        normalized_scope = _identifier(scope, "scope")
        if not isinstance(event_payload, dict):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PAYLOAD_INVALID",
                "event_payload는 object여야 합니다.",
            )
        _reject_raw_content(event_payload)
        source_ids = [str(item).strip() for item in source_ref_ids if str(item).strip()]
        if not source_ids:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_SOURCE_REQUIRED",
                "Event Evidence revision에는 SourceRef가 하나 이상 필요합니다.",
            )
        if len(source_ids) != len(set(source_ids)):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_SOURCE_DUPLICATE",
                "같은 SourceRef를 한 Event revision에 중복 연결할 수 없습니다.",
            )

        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")

            placeholders = ",".join("?" for _ in source_ids)
            rows = conn.execute(
                f"""
                SELECT * FROM event_evidence_source_ref
                WHERE source_ref_id IN ({placeholders})
                """,
                tuple(source_ids),
            ).fetchall()
            if len(rows) != len(source_ids):
                found = {str(row["source_ref_id"]) for row in rows}
                missing = sorted(set(source_ids) - found)
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_SOURCE_REF_NOT_FOUND",
                    "Event revision SourceRef를 찾을 수 없습니다: "
                    + ", ".join(missing),
                )
            for row in rows:
                self._verify_source_row(conn, row)

            bundle, source_bundle_hash = self._source_bundle(rows)
            revision = identity.to_dict()
            record_payload = {
                "record_version": EVENT_EVIDENCE_RECORD_VERSION,
                "hash_contract_version": EVENT_EVIDENCE_HASH_CONTRACT_VERSION,
                "revision": revision,
                "event_type": normalized_type,
                "scope": normalized_scope,
                "temporal": temporal.to_dict(),
                "event_payload": event_payload,
                "source_bundle_hash": source_bundle_hash,
            }
            event_hash = _digest(record_payload)
            event_payload_json = _canonical_json(event_payload)
            temporal_json = _canonical_json(temporal.to_dict())

            existing = conn.execute(
                """
                SELECT event_hash FROM event_evidence_record
                WHERE event_id=? AND event_version=?
                """,
                (identity.event_id, identity.version),
            ).fetchone()
            if existing is not None:
                if str(existing["event_hash"]) == event_hash:
                    conn.commit()
                    return self.get_event_revision(
                        identity.event_id,
                        identity.version,
                    )
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_IDENTITY_CONFLICT",
                    "같은 Event revision identity가 다른 내용으로 이미 저장되어 있습니다.",
                )

            latest = conn.execute(
                """
                SELECT event_version,event_state
                FROM event_evidence_record
                WHERE event_id=?
                ORDER BY event_version DESC
                LIMIT 1
                """,
                (identity.event_id,),
            ).fetchone()
            if identity.version == 1:
                if latest is not None:
                    raise EventEvidenceContractError(
                        "EVENT_EVIDENCE_REVISION_CONFLICT",
                        "이미 revision chain이 있는 event_id에 version 1을 추가할 수 없습니다.",
                    )
            else:
                if latest is None:
                    raise EventEvidenceContractError(
                        "EVENT_EVIDENCE_PREVIOUS_REVISION_MISSING",
                        "정정/철회/대체 revision의 이전 version이 없습니다.",
                    )
                latest_version = int(latest["event_version"])
                if (
                    identity.version != latest_version + 1
                    or identity.supersedes_version != latest_version
                ):
                    raise EventEvidenceContractError(
                        "EVENT_EVIDENCE_REVISION_CHAIN_CONFLICT",
                        "새 revision은 현재 latest revision을 바로 supersede해야 합니다.",
                    )

            conn.execute(
                """
                INSERT INTO event_evidence_record(
                    event_id,event_version,record_version,
                    hash_contract_version,event_state,supersedes_version,
                    event_type,scope,event_time,available_at,time_quality,
                    temporal_json,event_payload_json,
                    source_bundle_hash,event_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    identity.event_id,
                    identity.version,
                    EVENT_EVIDENCE_RECORD_VERSION,
                    EVENT_EVIDENCE_HASH_CONTRACT_VERSION,
                    identity.state.value,
                    identity.supersedes_version,
                    normalized_type,
                    normalized_scope,
                    temporal.event_time,
                    temporal.available_at,
                    temporal.time_quality.value,
                    temporal_json,
                    event_payload_json,
                    source_bundle_hash,
                    event_hash,
                    self.clock(),
                ),
            )
            for sequence, item in enumerate(bundle, start=1):
                conn.execute(
                    """
                    INSERT INTO event_evidence_record_source(
                        event_id,event_version,sequence,
                        source_ref_id,source_ref_hash
                    ) VALUES(?,?,?,?,?)
                    """,
                    (
                        identity.event_id,
                        identity.version,
                        sequence,
                        item["source_ref_id"],
                        item["source_ref_hash"],
                    ),
                )
            conn.commit()

        return self.get_event_revision(identity.event_id, identity.version)

    def get_event_revision(
        self,
        event_id: str,
        version: int,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_record
                WHERE event_id=? AND event_version=?
                """,
                (event_id, version),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_NOT_FOUND",
                    "Event Evidence revision을 찾을 수 없습니다.",
                )
            sources = conn.execute(
                """
                SELECT sequence,source_ref_id,source_ref_hash
                FROM event_evidence_record_source
                WHERE event_id=? AND event_version=?
                ORDER BY sequence
                """,
                (event_id, version),
            ).fetchall()
            return {
                "event_id": str(row["event_id"]),
                "event_version": int(row["event_version"]),
                "event_state": str(row["event_state"]),
                "supersedes_version": (
                    int(row["supersedes_version"])
                    if row["supersedes_version"] is not None
                    else None
                ),
                "event_type": str(row["event_type"]),
                "scope": str(row["scope"]),
                "temporal": json.loads(str(row["temporal_json"])),
                "event_payload": json.loads(str(row["event_payload_json"])),
                "source_bundle_hash": str(row["source_bundle_hash"]),
                "event_hash": str(row["event_hash"]),
                "sources": [
                    {
                        "sequence": int(item["sequence"]),
                        "source_ref_id": str(item["source_ref_id"]),
                        "source_ref_hash": str(item["source_ref_hash"]),
                    }
                    for item in sources
                ],
                "created_at": str(row["created_at"]),
            }

    def list_event_revisions(self, event_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_ready(conn)
            versions = [
                int(row["event_version"])
                for row in conn.execute(
                    """
                    SELECT event_version FROM event_evidence_record
                    WHERE event_id=?
                    ORDER BY event_version
                    """,
                    (event_id,),
                ).fetchall()
            ]
        return [self.get_event_revision(event_id, version) for version in versions]

    def verify_event_revision(
        self,
        event_id: str,
        version: int,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_record
                WHERE event_id=? AND event_version=?
                """,
                (event_id, version),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_NOT_FOUND",
                    "Event Evidence revision을 찾을 수 없습니다.",
                )
            link_rows = conn.execute(
                """
                SELECT rs.sequence,rs.source_ref_id,
                       rs.source_ref_hash AS linked_source_ref_hash,
                       sr.*
                FROM event_evidence_record_source rs
                JOIN event_evidence_source_ref sr
                  ON sr.source_ref_id=rs.source_ref_id
                WHERE rs.event_id=? AND rs.event_version=?
                ORDER BY rs.sequence
                """,
                (event_id, version),
            ).fetchall()
            if not link_rows:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_SOURCE_REQUIRED",
                    "Event Evidence revision에 SourceRef가 없습니다.",
                )

            source_rows: list[sqlite3.Row] = []
            for source_row in link_rows:
                self._verify_source_row(conn, source_row)
                if str(source_row["linked_source_ref_hash"]) != str(
                    source_row["source_ref_hash"]
                ):
                    raise EventEvidenceContractError(
                        "EVENT_EVIDENCE_SOURCE_LINK_MISMATCH",
                        "Event-source link hash가 SourceRef와 일치하지 않습니다.",
                    )
                source_rows.append(source_row)

            bundle, actual_bundle_hash = self._source_bundle(source_rows)
            linked = [
                {
                    "source_ref_id": str(item["source_ref_id"]),
                    "source_ref_hash": str(item["linked_source_ref_hash"]),
                }
                for item in link_rows
            ]
            if sorted(
                linked,
                key=lambda item: (item["source_ref_id"], item["source_ref_hash"]),
            ) != bundle:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_SOURCE_LINK_MISMATCH",
                    "Event-source link가 SourceRef snapshot과 일치하지 않습니다.",
                )
            if actual_bundle_hash != str(row["source_bundle_hash"]):
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_SOURCE_BUNDLE_MISMATCH",
                    "Event source bundle hash가 일치하지 않습니다.",
                )

            revision = {
                "contract_version": "VN_P6_S1_EVENT_REVISION_IDENTITY_V1",
                "event_id": str(row["event_id"]),
                "version": int(row["event_version"]),
                "state": str(row["event_state"]),
                "supersedes_version": (
                    int(row["supersedes_version"])
                    if row["supersedes_version"] is not None
                    else None
                ),
            }
            record_payload = {
                "record_version": str(row["record_version"]),
                "hash_contract_version": str(row["hash_contract_version"]),
                "revision": revision,
                "event_type": str(row["event_type"]),
                "scope": str(row["scope"]),
                "temporal": json.loads(str(row["temporal_json"])),
                "event_payload": json.loads(str(row["event_payload_json"])),
                "source_bundle_hash": str(row["source_bundle_hash"]),
            }
            actual_event_hash = _digest(record_payload)
            if actual_event_hash != str(row["event_hash"]):
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_INTEGRITY_MISMATCH",
                    "Event Evidence hash가 저장 내용과 일치하지 않습니다.",
                )
            return {
                "status": "MATCH",
                "event_id": str(row["event_id"]),
                "event_version": int(row["event_version"]),
                "event_hash": str(row["event_hash"]),
                "source_bundle_hash": str(row["source_bundle_hash"]),
            }
