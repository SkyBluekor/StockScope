from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from app.event_evidence.errors import EventEvidenceContractError


ENTITY_IDENTITY_CONTRACT_VERSION = "VN_P6_S1_ENTITY_IDENTITY_V1"
EVENT_RELEVANCE_CONTRACT_VERSION = "VN_P6_S1_EVENT_RELEVANCE_V1"

ENTITY_TABLES = frozenset(
    {
        "event_evidence_entity",
        "event_evidence_entity_relevance",
    }
)

_MARKET = re.compile(r"^[A-Z][A-Z0-9_]{1,15}$")
_TICKER = re.compile(r"^[0-9]{6}$")


class EntityType(str, Enum):
    LISTED_COMPANY = "LISTED_COMPANY"
    INDUSTRY = "INDUSTRY"
    POLICY = "POLICY"
    MACRO = "MACRO"
    COUNTRY = "COUNTRY"
    COMMODITY = "COMMODITY"
    OTHER = "OTHER"


class RelevanceRelation(str, Enum):
    DIRECT_COMPANY = "DIRECT_COMPANY"
    SUBSIDIARY = "SUBSIDIARY"
    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"
    COMPETITOR = "COMPETITOR"
    INDUSTRY = "INDUSTRY"
    POLICY_EXPOSURE = "POLICY_EXPOSURE"
    MACRO_EXPOSURE = "MACRO_EXPOSURE"


class RelevanceState(str, Enum):
    CONFIRMED = "CONFIRMED"
    SUPPORTED = "SUPPORTED"
    WEAK = "WEAK"
    UNKNOWN = "UNKNOWN"
    REJECTED = "REJECTED"


class RelevanceEvidenceKind(str, Enum):
    SOURCE_DIRECT = "SOURCE_DIRECT"
    CORP_CODE_MAPPING = "CORP_CODE_MAPPING"
    STRUCTURED_RELATION = "STRUCTURED_RELATION"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    TITLE_HINT = "TITLE_HINT"


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
            "EVENT_ENTITY_JSON_INVALID",
            "Entity/Relevance payload는 canonical JSON으로 직렬화할 수 있어야 합니다.",
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
            "EVENT_ENTITY_TIME_INVALID",
            f"{field_name}은 timezone이 포함된 ISO-8601 시각이어야 합니다.",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventEvidenceContractError(
            "EVENT_ENTITY_TIMEZONE_REQUIRED",
            f"{field_name}에는 timezone offset이 필요합니다.",
        )
    return parsed


@dataclass(frozen=True, slots=True)
class EventEntityRef:
    entity_type: EntityType
    entity_key: str
    name: str
    identity_source: str
    identity_as_of: str
    market: str | None = None
    ticker: str | None = None
    contract_version: str = ENTITY_IDENTITY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != ENTITY_IDENTITY_CONTRACT_VERSION:
            raise EventEvidenceContractError(
                "EVENT_ENTITY_CONTRACT_MISMATCH",
                "Entity Identity contract version이 현재 코드와 다릅니다.",
            )
        try:
            entity_type = (
                self.entity_type
                if isinstance(self.entity_type, EntityType)
                else EntityType(str(self.entity_type))
            )
        except ValueError as exc:
            raise EventEvidenceContractError(
                "EVENT_ENTITY_TYPE_INVALID",
                f"알 수 없는 entity_type입니다: {self.entity_type}",
            ) from exc
        object.__setattr__(self, "entity_type", entity_type)

        key = str(self.entity_key or "").strip().upper()
        name = str(self.name or "").strip()
        source = str(self.identity_source or "").strip().upper()
        if not key or not name or not source:
            raise EventEvidenceContractError(
                "EVENT_ENTITY_IDENTITY_INVALID",
                "entity_key/name/identity_source 값이 필요합니다.",
            )
        _parse_aware(self.identity_as_of, "identity_as_of")

        market = str(self.market or "").strip().upper() or None
        ticker = str(self.ticker or "").strip() or None
        if entity_type is EntityType.LISTED_COMPANY:
            if market is None or ticker is None:
                raise EventEvidenceContractError(
                    "EVENT_ENTITY_LISTED_IDENTITY_REQUIRED",
                    "LISTED_COMPANY는 market과 ticker가 필요합니다.",
                )
            if not _MARKET.fullmatch(market) or not _TICKER.fullmatch(ticker):
                raise EventEvidenceContractError(
                    "EVENT_ENTITY_LISTED_IDENTITY_INVALID",
                    "LISTED_COMPANY market/ticker 형식이 올바르지 않습니다.",
                )
            expected = f"{market}:{ticker}"
            if key != expected:
                raise EventEvidenceContractError(
                    "EVENT_ENTITY_CANONICAL_KEY_MISMATCH",
                    f"LISTED_COMPANY entity_key는 {expected}여야 합니다.",
                )
        object.__setattr__(self, "entity_key", key)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "identity_source", source)
        object.__setattr__(self, "market", market)
        object.__setattr__(self, "ticker", ticker)

    @classmethod
    def listed_company(
        cls,
        *,
        market: str,
        ticker: str,
        name: str,
        identity_source: str,
        identity_as_of: str,
    ) -> "EventEntityRef":
        normalized_market = str(market or "").strip().upper()
        normalized_ticker = str(ticker or "").strip()
        return cls(
            entity_type=EntityType.LISTED_COMPANY,
            entity_key=f"{normalized_market}:{normalized_ticker}",
            market=normalized_market,
            ticker=normalized_ticker,
            name=name,
            identity_source=identity_source,
            identity_as_of=identity_as_of,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entity_type"] = self.entity_type.value
        return payload


@dataclass(frozen=True, slots=True)
class EventEntityRelevance:
    event_id: str
    event_version: int
    entity_id: str
    relation_type: RelevanceRelation
    relevance_state: RelevanceState
    evidence_kind: RelevanceEvidenceKind
    evidence_ref: str
    evidence_as_of: str
    relation_payload: dict[str, Any]
    contract_version: str = EVENT_RELEVANCE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != EVENT_RELEVANCE_CONTRACT_VERSION:
            raise EventEvidenceContractError(
                "EVENT_RELEVANCE_CONTRACT_MISMATCH",
                "Event Relevance contract version이 현재 코드와 다릅니다.",
            )
        if not str(self.event_id or "").strip() or self.event_version < 1:
            raise EventEvidenceContractError(
                "EVENT_RELEVANCE_EVENT_INVALID",
                "유효한 event_id/event_version이 필요합니다.",
            )
        if not str(self.entity_id or "").strip():
            raise EventEvidenceContractError(
                "EVENT_RELEVANCE_ENTITY_REQUIRED",
                "entity_id가 필요합니다.",
            )
        try:
            relation = (
                self.relation_type
                if isinstance(self.relation_type, RelevanceRelation)
                else RelevanceRelation(str(self.relation_type))
            )
            state = (
                self.relevance_state
                if isinstance(self.relevance_state, RelevanceState)
                else RelevanceState(str(self.relevance_state))
            )
            evidence_kind = (
                self.evidence_kind
                if isinstance(self.evidence_kind, RelevanceEvidenceKind)
                else RelevanceEvidenceKind(str(self.evidence_kind))
            )
        except ValueError as exc:
            raise EventEvidenceContractError(
                "EVENT_RELEVANCE_VALUE_INVALID",
                "알 수 없는 relevance relation/state/evidence kind입니다.",
            ) from exc
        object.__setattr__(self, "relation_type", relation)
        object.__setattr__(self, "relevance_state", state)
        object.__setattr__(self, "evidence_kind", evidence_kind)

        if not str(self.evidence_ref or "").strip():
            raise EventEvidenceContractError(
                "EVENT_RELEVANCE_EVIDENCE_REF_REQUIRED",
                "relevance evidence_ref가 필요합니다.",
            )
        _parse_aware(self.evidence_as_of, "evidence_as_of")
        if not isinstance(self.relation_payload, dict):
            raise EventEvidenceContractError(
                "EVENT_RELEVANCE_PAYLOAD_INVALID",
                "relation_payload는 object여야 합니다.",
            )

        if state is RelevanceState.CONFIRMED and evidence_kind not in {
            RelevanceEvidenceKind.SOURCE_DIRECT,
            RelevanceEvidenceKind.CORP_CODE_MAPPING,
        }:
            raise EventEvidenceContractError(
                "EVENT_RELEVANCE_CONFIRMATION_UNSUPPORTED",
                "CONFIRMED는 직접 source 또는 corp-code mapping 근거가 필요합니다.",
            )
        if evidence_kind is RelevanceEvidenceKind.TITLE_HINT and state in {
            RelevanceState.CONFIRMED,
            RelevanceState.SUPPORTED,
        }:
            raise EventEvidenceContractError(
                "EVENT_RELEVANCE_TITLE_HINT_TOO_STRONG",
                "제목 언급만으로 CONFIRMED/SUPPORTED 관련성을 만들 수 없습니다.",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "event_id": self.event_id,
            "event_version": self.event_version,
            "entity_id": self.entity_id,
            "relation_type": self.relation_type.value,
            "relevance_state": self.relevance_state.value,
            "evidence_kind": self.evidence_kind.value,
            "evidence_ref": self.evidence_ref,
            "evidence_as_of": self.evidence_as_of,
            "relation_payload": self.relation_payload,
        }


class EventEntityService:
    def __init__(
        self,
        simulation_db: Path,
        *,
        clock: Callable[[], str],
    ) -> None:
        self.simulation_db = Path(simulation_db)
        self.clock = clock

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
        missing = sorted(ENTITY_TABLES - self._tables(conn))
        if missing:
            raise EventEvidenceContractError(
                "EVENT_ENTITY_MIGRATION_REQUIRED",
                "P6 Entity/Relevance schema가 준비되지 않았습니다: "
                + ", ".join(missing),
            )

    @staticmethod
    def _entity_id(entity: EventEntityRef) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                (
                    "stockscope:event-entity:"
                    f"{ENTITY_IDENTITY_CONTRACT_VERSION}:"
                    f"{entity.entity_type.value}:{entity.entity_key}"
                ),
            )
        )

    def register_entity(self, entity: EventEntityRef) -> dict[str, Any]:
        payload = entity.to_dict()
        entity_json = _canonical_json(payload)
        entity_hash = _digest(payload)
        entity_id = self._entity_id(entity)

        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT entity_id,identity_json,identity_hash
                FROM event_evidence_entity
                WHERE entity_type=? AND entity_key=?
                """,
                (entity.entity_type.value, entity.entity_key),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["entity_id"]) == entity_id
                    and str(existing["identity_hash"]) == entity_hash
                    and str(existing["identity_json"]) == entity_json
                ):
                    conn.commit()
                    return self.get_entity(entity_id)
                raise EventEvidenceContractError(
                    "EVENT_ENTITY_IDENTITY_CONFLICT",
                    "같은 Entity canonical key가 다른 identity로 이미 저장되어 있습니다.",
                )

            conn.execute(
                """
                INSERT INTO event_evidence_entity(
                    entity_id,entity_contract_version,entity_type,entity_key,
                    market,ticker,name,identity_source,identity_as_of,
                    identity_json,identity_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    entity_id,
                    entity.contract_version,
                    entity.entity_type.value,
                    entity.entity_key,
                    entity.market,
                    entity.ticker,
                    entity.name,
                    entity.identity_source,
                    entity.identity_as_of,
                    entity_json,
                    entity_hash,
                    self.clock(),
                ),
            )
            conn.commit()
        return self.get_entity(entity_id)

    def get_entity(self, entity_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                "SELECT * FROM event_evidence_entity WHERE entity_id=?",
                (entity_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_ENTITY_NOT_FOUND",
                    "Event Entity를 찾을 수 없습니다.",
                )
            return {
                "entity_id": str(row["entity_id"]),
                "entity_type": str(row["entity_type"]),
                "entity_key": str(row["entity_key"]),
                "market": row["market"],
                "ticker": row["ticker"],
                "name": str(row["name"]),
                "identity_source": str(row["identity_source"]),
                "identity_as_of": str(row["identity_as_of"]),
                "identity_hash": str(row["identity_hash"]),
                "identity": json.loads(str(row["identity_json"])),
                "created_at": str(row["created_at"]),
            }

    @staticmethod
    def _relevance_id(relevance: EventEntityRelevance) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                (
                    "stockscope:event-relevance:"
                    f"{EVENT_RELEVANCE_CONTRACT_VERSION}:"
                    f"{relevance.event_id}:{relevance.event_version}:"
                    f"{relevance.entity_id}:{relevance.relation_type.value}"
                ),
            )
        )

    def attach_relevance(
        self,
        relevance: EventEntityRelevance,
    ) -> dict[str, Any]:
        payload = relevance.to_dict()
        relation_json = _canonical_json(payload)
        relation_hash = _digest(payload)
        relevance_id = self._relevance_id(relevance)

        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            event = conn.execute(
                """
                SELECT event_hash FROM event_evidence_record
                WHERE event_id=? AND event_version=?
                """,
                (relevance.event_id, relevance.event_version),
            ).fetchone()
            if event is None:
                raise EventEvidenceContractError(
                    "EVENT_RELEVANCE_EVENT_NOT_FOUND",
                    "Relevance가 참조하는 Event revision을 찾을 수 없습니다.",
                )
            entity = conn.execute(
                """
                SELECT identity_hash FROM event_evidence_entity
                WHERE entity_id=?
                """,
                (relevance.entity_id,),
            ).fetchone()
            if entity is None:
                raise EventEvidenceContractError(
                    "EVENT_RELEVANCE_ENTITY_NOT_FOUND",
                    "Relevance가 참조하는 Entity를 찾을 수 없습니다.",
                )

            existing = conn.execute(
                """
                SELECT relevance_id,relation_hash,relation_json
                FROM event_evidence_entity_relevance
                WHERE event_id=? AND event_version=?
                  AND entity_id=? AND relation_type=?
                """,
                (
                    relevance.event_id,
                    relevance.event_version,
                    relevance.entity_id,
                    relevance.relation_type.value,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["relevance_id"]) == relevance_id
                    and str(existing["relation_hash"]) == relation_hash
                    and str(existing["relation_json"]) == relation_json
                ):
                    conn.commit()
                    return self.get_relevance(relevance_id)
                raise EventEvidenceContractError(
                    "EVENT_RELEVANCE_IDENTITY_CONFLICT",
                    "같은 Event/Entity/Relation identity가 다른 근거로 이미 저장되어 있습니다.",
                )

            conn.execute(
                """
                INSERT INTO event_evidence_entity_relevance(
                    relevance_id,relevance_contract_version,
                    event_id,event_version,event_hash,
                    entity_id,entity_hash,
                    relation_type,relevance_state,
                    evidence_kind,evidence_ref,evidence_as_of,
                    relation_json,relation_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    relevance_id,
                    relevance.contract_version,
                    relevance.event_id,
                    relevance.event_version,
                    str(event["event_hash"]),
                    relevance.entity_id,
                    str(entity["identity_hash"]),
                    relevance.relation_type.value,
                    relevance.relevance_state.value,
                    relevance.evidence_kind.value,
                    relevance.evidence_ref,
                    relevance.evidence_as_of,
                    relation_json,
                    relation_hash,
                    self.clock(),
                ),
            )
            conn.commit()
        return self.get_relevance(relevance_id)

    def get_relevance(self, relevance_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_entity_relevance
                WHERE relevance_id=?
                """,
                (relevance_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_RELEVANCE_NOT_FOUND",
                    "Event Entity Relevance를 찾을 수 없습니다.",
                )
            return {
                "relevance_id": str(row["relevance_id"]),
                "event_id": str(row["event_id"]),
                "event_version": int(row["event_version"]),
                "entity_id": str(row["entity_id"]),
                "relation_type": str(row["relation_type"]),
                "relevance_state": str(row["relevance_state"]),
                "evidence_kind": str(row["evidence_kind"]),
                "evidence_ref": str(row["evidence_ref"]),
                "evidence_as_of": str(row["evidence_as_of"]),
                "relation_hash": str(row["relation_hash"]),
                "relation": json.loads(str(row["relation_json"])),
                "created_at": str(row["created_at"]),
            }

    def list_event_entities(
        self,
        event_id: str,
        event_version: int,
        *,
        cutoff: str | None = None,
    ) -> list[dict[str, Any]]:
        cutoff_dt = _parse_aware(cutoff, "cutoff") if cutoff is not None else None
        with self._connect() as conn:
            self._require_ready(conn)
            rows = conn.execute(
                """
                SELECT r.*,e.entity_type,e.entity_key,e.market,e.ticker,e.name
                FROM event_evidence_entity_relevance r
                JOIN event_evidence_entity e ON e.entity_id=r.entity_id
                WHERE r.event_id=? AND r.event_version=?
                ORDER BY e.entity_type,e.entity_key,r.relation_type
                """,
                (event_id, event_version),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            if cutoff_dt is not None and _parse_aware(
                str(row["evidence_as_of"]),
                "evidence_as_of",
            ) > cutoff_dt:
                continue
            results.append(
                {
                    "entity_id": str(row["entity_id"]),
                    "entity_type": str(row["entity_type"]),
                    "entity_key": str(row["entity_key"]),
                    "market": row["market"],
                    "ticker": row["ticker"],
                    "name": str(row["name"]),
                    "relation_type": str(row["relation_type"]),
                    "relevance_state": str(row["relevance_state"]),
                    "evidence_kind": str(row["evidence_kind"]),
                    "evidence_ref": str(row["evidence_ref"]),
                    "evidence_as_of": str(row["evidence_as_of"]),
                }
            )
        return results
