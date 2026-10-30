"""P6-F: prospective OpenDART disclosure -> EventEvidence connector.

Preparation works on authenticated P6-E response rows but performs no writes.
The persisted pipeline reuses the existing SourceRef / EventRevision / Entity /
Relevance / Quality contracts. It is intentionally *not* wired to a live
endpoint: current OpenDART policy rejects DERIVED_RETENTION. An isolated
test-only entry point demonstrates the complete pipeline without making that
policy an operational permission grant.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from app.event_evidence.entity import (
    EventEntityRef, EventEntityRelevance, EventEntityService,
    RelevanceRelation, RelevanceState, RelevanceEvidenceKind,
)
from app.event_evidence.models import (
    EventEvidenceSourceRef, EventRevisionIdentity, EventEvidenceState,
)
from app.event_evidence.policy import (
    EventEvidenceSourcePolicy, EvidenceCapability, opendart_event_evidence_policy,
)
from app.event_evidence.quality import EventEvidenceQualityService, EvidenceQualityScope
from app.event_evidence.store import EventEvidenceStore
from app.event_evidence.time import TemporalEvidence, EvidenceTimeQuality
from app.event_evidence.errors import EventEvidenceContractError

VERSION = "JEV_P6F_DISCLOSURE_INGEST_CONTRACT_V1"
CODE = re.compile(r"^\d{6}$")
CORP = re.compile(r"^\d{8}$")
RECEIPT = re.compile(r"^\d{14}$")
MARKETS = frozenset({"KOSPI", "KOSDAQ"})


def _utc(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("P6F_OBSERVATION_TIME_REQUIRED")
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("P6F_OBSERVATION_TIME_INVALID") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("P6F_OBSERVATION_TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc).isoformat()


def _digest(obj: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PreparedDisclosure:
    receipt_no: str
    corp_code: str
    ticker: str
    market: str
    corp_name: str
    receipt_date: str
    first_seen_at: str
    official_url: str
    metadata_hash: str

    @property
    def source_ref_id(self) -> str:
        return "OPENDART-RECEIPT:" + self.receipt_no

    @property
    def event_id(self) -> str:
        return "OPENDART-EVENT:" + self.receipt_no


def prepare_disclosure(
    row: dict[str, Any], *, ticker: str, market: str,
    corp_code: str, first_seen_at: str,
) -> PreparedDisclosure:
    """Normalize minimum provenance; no date-only publication time fabrication."""
    if not isinstance(row, dict):
        raise ValueError("P6F_ROW_INVALID")
    normalized_ticker = str(ticker or "").strip()
    normalized_market = str(market or "").strip().upper()
    normalized_corp = str(corp_code or "").strip()
    if (
        not CODE.fullmatch(normalized_ticker)
        or normalized_market not in MARKETS
        or not CORP.fullmatch(normalized_corp)
    ):
        raise ValueError("P6F_COMPANY_IDENTITY_INVALID")
    receipt = str(row.get("receipt_no") or "")
    receipt_date = str(row.get("receipt_date") or "")
    if not RECEIPT.fullmatch(receipt) or not re.fullmatch(r"\d{8}", receipt_date):
        raise ValueError("P6F_RECEIPT_IDENTITY_INVALID")
    try:
        parsed_date = date.fromisoformat(receipt_date)
    except ValueError as exc:
        raise ValueError("P6F_RECEIPT_DATE_INVALID") from exc
    if str(row.get("corp_code") or "") != normalized_corp:
        raise ValueError("P6F_CORP_CODE_MISMATCH")
    upstream_ticker = str(row.get("stock_code") or "")
    if upstream_ticker and upstream_ticker != normalized_ticker:
        raise ValueError("P6F_TICKER_MISMATCH")
    name = str(row.get("corp_name") or "").strip()
    if not name or len(name) > 100:
        raise ValueError("P6F_CORP_NAME_INVALID")
    report_name = str(row.get("report_name") or "").strip()
    if not report_name or len(report_name) > 300:
        raise ValueError("P6F_REPORT_NAME_INVALID")
    url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"
    if row.get("viewer_url") not in (None, url):
        raise ValueError("P6F_ORIGINAL_URL_MISMATCH")
    # A date-only API value is NOT a verified publication timestamp.
    if row.get("source_published_at") not in (None, ""):
        raise ValueError("P6F_UNVERIFIED_SOURCE_PUBLICATION_TIME")
    if row.get("source_time_quality") not in (None, "DATE_ONLY"):
        raise ValueError("P6F_TIME_QUALITY_MISMATCH")
    observed = _utc(first_seen_at)
    normalized_fields = {
        "source_kind": "OPENDART_DISCLOSURE",
        "receipt_no": receipt,
        "corp_code": normalized_corp,
        "stock_code": normalized_ticker,
        "receipt_date": parsed_date.isoformat(),
        "report_name": report_name,
    }
    return PreparedDisclosure(
        receipt_no=receipt, corp_code=normalized_corp,
        ticker=normalized_ticker, market=normalized_market,
        corp_name=name, receipt_date=parsed_date.isoformat(),
        first_seen_at=observed, official_url=url,
        metadata_hash=_digest(normalized_fields),
    )


def prepare_disclosure_batch(
    response: dict[str, Any], *, market: str,
) -> list[PreparedDisclosure]:
    """Require the actual P6-E verified lookup boundary and unique receipts."""
    if (
        not isinstance(response, dict)
        or response.get("provider") != "OpenDART"
        or response.get("event_evidence_storage") != "NOT_PERSISTED_RIGHTS_UNVERIFIED"
        or response.get("external_ai_transfer") != "BLOCKED"
        or response.get("db_writes") != 0
        or response.get("source_publication_time_verified") is not False
        or response.get("time_quality") != "DATE_ONLY"
    ):
        raise ValueError("P6F_SOURCE_RESPONSE_CONTRACT_INVALID")
    rows = response.get("rows")
    if not isinstance(rows, list) or len(rows) > 150:
        raise ValueError("P6F_SOURCE_BATCH_INVALID")
    if response.get("count") != len(rows):
        raise ValueError("P6F_SOURCE_BATCH_COUNT_MISMATCH")
    observed = response.get("fetched_at")
    result = [
        prepare_disclosure(
            item, ticker=response.get("stock_code"), market=market,
            corp_code=response.get("corp_code"), first_seen_at=observed,
        )
        for item in rows
    ]
    if len({item.receipt_no for item in result}) != len(result):
        raise ValueError("P6F_DUPLICATE_RECEIPT")
    return result


def _present(db: Path, table: str, field: str, value: str) -> bool:
    if not db.is_file():
        raise FileNotFoundError("P6F_EXISTING_DB_REQUIRED")
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        return conn.execute(
            f"SELECT 1 FROM {table} WHERE {field}=? LIMIT 1", (value,),
        ).fetchone() is not None


def _persist_authorized(
    db: Path, prepared: PreparedDisclosure, *, policy: EventEvidenceSourcePolicy,
) -> dict[str, Any]:
    """Unexposed internal pipeline; caller must establish actual source rights."""
    policy.require(EvidenceCapability.DERIVED_RETENTION)
    if policy.source_kind != "OPENDART_DISCLOSURE":
        raise ValueError("P6F_SOURCE_POLICY_MISMATCH")
    if not db.is_file():
        raise FileNotFoundError("P6F_EXISTING_DB_REQUIRED")

    store = EventEvidenceStore(db)
    entities = EventEntityService(db)
    quality = EventEvidenceQualityService(db)
    source_exists = _present(db, "event_evidence_source_ref", "source_ref_id", prepared.source_ref_id)
    if source_exists:
        original = store.verify_source_ref(prepared.source_ref_id)
        if original["status"] != "MATCH":
            raise ValueError("P6F_PREEXISTING_SOURCE_INTEGRITY_FAILURE")
        source = store.get_source_ref(prepared.source_ref_id)
        if source["content_hash"] != prepared.metadata_hash:
            raise ValueError("P6F_EXISTING_CONTENT_CONFLICT")
        if source["source"]["source_native_id"] != prepared.receipt_no:
            raise ValueError("P6F_EXISTING_RECEIPT_CONFLICT")
        prior_policy = source["source"]["rights_policy_id"]
        if prior_policy != policy.policy_id:
            raise ValueError("P6F_EXISTING_POLICY_CONFLICT")
        temporal = TemporalEvidence(**source["source"]["temporal"])
    else:
        temporal = TemporalEvidence(
            event_time=prepared.receipt_date,
            time_quality=EvidenceTimeQuality.DATE_ONLY,
            source_published_at=None, provider_published_at=None,
            first_seen_at=prepared.first_seen_at,
            available_at=prepared.first_seen_at,
            fetched_at=prepared.first_seen_at,
        )
        source = store.store_source_ref(
            policy=policy,
            source_ref=EventEvidenceSourceRef(
                source_ref_id=prepared.source_ref_id,
                source_kind=policy.source_kind,
                source_native_id=prepared.receipt_no,
                rights_policy_id=policy.policy_id,
                content_hash=prepared.metadata_hash,
                temporal=temporal,
                source_url=prepared.official_url, source_name="OpenDART",
            ),
        )
    event = store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id=prepared.event_id, version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type="DISCLOSURE_LISTING", scope="COMPANY",
        temporal=temporal,
        event_payload={
            "receipt_no": prepared.receipt_no,
            "corp_code": prepared.corp_code,
            "receipt_date": prepared.receipt_date,
        },
        source_ref_ids=[prepared.source_ref_id],
    )
    existing_entity = None
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        existing_entity = conn.execute(
            "SELECT entity_id FROM event_evidence_entity WHERE entity_key=?",
            (prepared.market + ":" + prepared.ticker,),
        ).fetchone()
    if existing_entity:
        company = entities.get_entity(str(existing_entity["entity_id"]))
    else:
        company = entities.register_entity(
            EventEntityRef.listed_company(
                market=prepared.market, ticker=prepared.ticker,
                name=prepared.corp_name, identity_source="OPENDART_CORP_CODE_MAPPING",
                identity_as_of=temporal.first_seen_at or temporal.available_at,
            )
        )
    relevance = entities.attach_relevance(EventEntityRelevance(
        event_id=prepared.event_id, event_version=1,
        entity_id=company["entity_id"],
        relation_type=RelevanceRelation.DIRECT_COMPANY,
        relevance_state=RelevanceState.CONFIRMED,
        evidence_kind=RelevanceEvidenceKind.CORP_CODE_MAPPING,
        evidence_ref="source:" + prepared.source_ref_id,
        evidence_as_of=temporal.first_seen_at or temporal.available_at,
        relation_payload={
            "source_ref_id": prepared.source_ref_id,
            "corp_code": prepared.corp_code,
        },
    ))
    assessment = quality.assess_event_entity(
        event_id=prepared.event_id,
        entity_id=company["entity_id"],
        assessment_scope=EvidenceQualityScope.REFERENCE,
        assessment_as_of=temporal.available_at,
        relevance_id=relevance["relevance_id"],
    )
    return {
        "contract_version": VERSION,
        "event_id": prepared.event_id,
        "source_ref_id": prepared.source_ref_id,
        "source_hash": source["source_ref_hash"],
        "event_hash": event["event_hash"],
        "entity_id": company["entity_id"],
        "relevance_id": relevance["relevance_id"],
        "quality_state": assessment["quality_state"],
        "quality_assessment_id": assessment["assessment_id"],
        "first_seen_at": temporal.first_seen_at,
        "time_quality": temporal.time_quality.value,
        "ai_transmission_allowed": False,
    }


def persist_test_fixture_only(
    db: Path, prepared: PreparedDisclosure, *,
    test_policy: EventEvidenceSourcePolicy,
) -> dict[str, Any]:
    """Explicitly isolated test-only mode; never callable from API or real fetch."""
    if (
        test_policy.policy_id != "P6F-ISOLATED-TEST-OPENDART-V1"
        or test_policy.policy_version != "p6f-isolated-test-v1"
        or not test_policy.policy_basis.startswith("TEST_ONLY:")
        or test_policy.ai_transform_allowed
        or test_policy.historical_evaluation_allowed
        or test_policy.prediction_input_allowed
        or test_policy.raw_retention_allowed
        or not Path(db).name.startswith("p6f-test-")
    ):
        raise ValueError("P6F_TEST_ISOLATION_REQUIRED")
    return _persist_authorized(Path(db), prepared, policy=test_policy)


def live_storage_decision() -> dict[str, Any]:
    """Current production capability only; never fabricate rights from config."""
    policy = opendart_event_evidence_policy()
    return {
        "contract_version": VERSION,
        "source_kind": policy.source_kind,
        "policy_id": policy.policy_id,
        "storage_allowed": policy.allows(EvidenceCapability.DERIVED_RETENTION),
        "ai_transmission_allowed": policy.allows(EvidenceCapability.AI_TRANSFORM),
        "status": "NOT_APPROVED" if not policy.allows(EvidenceCapability.DERIVED_RETENTION) else "SOURCE_POLICY_REVIEW_REQUIRED",
        "actual_db_writes": 0,
        "actual_provider_calls": 0,
    }
