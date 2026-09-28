from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.event_evidence import (
    EntityType,
    EventEntityRef,
    EventEntityRelevance,
    EventEntityService,
    EventEvidenceContractError,
    EventEvidenceSourcePolicy,
    EventEvidenceSourceRef,
    EventEvidenceState,
    EventEvidenceStore,
    EventRevisionIdentity,
    EvidenceTimeQuality,
    RelevanceEvidenceKind,
    RelevanceRelation,
    RelevanceState,
    TemporalEvidence,
)
from tools.data.migrate_event_evidence_vnp6s1 import migrate_event_evidence_store


NOW = "2026-09-28T05:30:00+00:00"


def _policy() -> EventEvidenceSourcePolicy:
    return EventEvidenceSourcePolicy(
        policy_id="TEST-P6-C-RETENTION-V1",
        source_kind="TEST_SYNTHETIC",
        policy_version="test-v1",
        display_allowed=True,
        normalization_allowed=True,
        raw_retention_allowed=False,
        derived_retention_allowed=True,
        ai_transform_allowed=False,
        historical_evaluation_allowed=False,
        prediction_input_allowed=False,
        attribution_required=False,
        policy_basis="TEST_FIXTURE_ONLY",
    )


def _temporal(minute: int = 10) -> TemporalEvidence:
    return TemporalEvidence(
        event_time="2026-09-28T09:00:00+09:00",
        source_published_at="2026-09-28T09:02:00+09:00",
        provider_published_at="2026-09-28T09:05:00+09:00",
        first_seen_at=f"2026-09-28T09:{minute:02d}:00+09:00",
        available_at=f"2026-09-28T09:{minute:02d}:00+09:00",
        fetched_at=f"2026-09-28T09:{minute:02d}:03+09:00",
        time_quality=EvidenceTimeQuality.EXACT,
    )


def _fixture(tmp_path: Path):
    db = tmp_path / "simulation.db"
    sqlite3.connect(db).close()
    migrate_event_evidence_store(db)
    policy = _policy()
    store = EventEvidenceStore(db, clock=lambda: NOW)
    source = EventEvidenceSourceRef(
        source_ref_id="SRC-1",
        source_kind=policy.source_kind,
        source_native_id="official-1",
        rights_policy_id=policy.policy_id,
        content_hash="a" * 64,
        temporal=_temporal(),
    )
    store.store_source_ref(policy=policy, source_ref=source)
    store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-1",
            version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type="RIGHTS_ISSUE",
        scope="COMPANY",
        temporal=_temporal(),
        event_payload={"official_event_id": "OFFICIAL-1"},
        source_ref_ids=["SRC-1"],
    )
    entities = EventEntityService(db, clock=lambda: NOW)
    return db, entities


def test_listed_company_uses_market_ticker_canonical_identity(tmp_path: Path):
    _, entities = _fixture(tmp_path)
    company = EventEntityRef.listed_company(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        identity_source="KRX_MASTER",
        identity_as_of="2026-09-28T00:00:00+09:00",
    )
    first = entities.register_entity(company)
    second = entities.register_entity(company)

    assert first["entity_key"] == "KOSPI:005930"
    assert first["entity_id"] == second["entity_id"]
    assert first["identity_hash"] == second["identity_hash"]

    with pytest.raises(EventEvidenceContractError) as bad:
        EventEntityRef(
            entity_type=EntityType.LISTED_COMPANY,
            entity_key="삼성전자",
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            identity_source="KRX_MASTER",
            identity_as_of="2026-09-28T00:00:00+09:00",
        )
    assert bad.value.code == "EVENT_ENTITY_CANONICAL_KEY_MISMATCH"


def test_direct_relevance_requires_strong_identity_evidence(tmp_path: Path):
    _, entities = _fixture(tmp_path)
    company = entities.register_entity(
        EventEntityRef.listed_company(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            identity_source="CORP_CODE_MAPPING",
            identity_as_of="2026-09-28T00:00:00+09:00",
        )
    )

    rel = entities.attach_relevance(
        EventEntityRelevance(
            event_id="EVENT-1",
            event_version=1,
            entity_id=company["entity_id"],
            relation_type=RelevanceRelation.DIRECT_COMPANY,
            relevance_state=RelevanceState.CONFIRMED,
            evidence_kind=RelevanceEvidenceKind.CORP_CODE_MAPPING,
            evidence_ref="corp:00126380",
            evidence_as_of="2026-09-28T09:10:00+09:00",
            relation_payload={"corp_code": "00126380"},
        )
    )
    assert rel["relevance_state"] == "CONFIRMED"

    with pytest.raises(EventEvidenceContractError) as title_only:
        EventEntityRelevance(
            event_id="EVENT-1",
            event_version=1,
            entity_id=company["entity_id"],
            relation_type=RelevanceRelation.DIRECT_COMPANY,
            relevance_state=RelevanceState.CONFIRMED,
            evidence_kind=RelevanceEvidenceKind.TITLE_HINT,
            evidence_ref="title:삼성전자",
            evidence_as_of="2026-09-28T09:10:00+09:00",
            relation_payload={"mention": "삼성전자"},
        )
    assert title_only.value.code == "EVENT_RELEVANCE_CONFIRMATION_UNSUPPORTED"


def test_title_hint_cannot_auto_promote_supported_relevance(tmp_path: Path):
    _, entities = _fixture(tmp_path)
    company = entities.register_entity(
        EventEntityRef.listed_company(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            identity_source="KRX_MASTER",
            identity_as_of="2026-09-28T00:00:00+09:00",
        )
    )
    with pytest.raises(EventEvidenceContractError) as caught:
        EventEntityRelevance(
            event_id="EVENT-1",
            event_version=1,
            entity_id=company["entity_id"],
            relation_type=RelevanceRelation.DIRECT_COMPANY,
            relevance_state=RelevanceState.SUPPORTED,
            evidence_kind=RelevanceEvidenceKind.TITLE_HINT,
            evidence_ref="title-only",
            evidence_as_of="2026-09-28T09:10:00+09:00",
            relation_payload={},
        )
    assert caught.value.code == "EVENT_RELEVANCE_TITLE_HINT_TOO_STRONG"


def test_relevance_requires_existing_event_and_entity_and_is_immutable(tmp_path: Path):
    db, entities = _fixture(tmp_path)
    company = entities.register_entity(
        EventEntityRef.listed_company(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            identity_source="KRX_MASTER",
            identity_as_of="2026-09-28T00:00:00+09:00",
        )
    )
    relevance = EventEntityRelevance(
        event_id="EVENT-1",
        event_version=1,
        entity_id=company["entity_id"],
        relation_type=RelevanceRelation.DIRECT_COMPANY,
        relevance_state=RelevanceState.CONFIRMED,
        evidence_kind=RelevanceEvidenceKind.SOURCE_DIRECT,
        evidence_ref="source:SRC-1",
        evidence_as_of="2026-09-28T09:10:00+09:00",
        relation_payload={"source_ref_id": "SRC-1"},
    )
    stored = entities.attach_relevance(relevance)
    repeated = entities.attach_relevance(relevance)
    assert stored["relation_hash"] == repeated["relation_hash"]

    missing_event = EventEntityRelevance(
        event_id="MISSING",
        event_version=1,
        entity_id=company["entity_id"],
        relation_type=RelevanceRelation.DIRECT_COMPANY,
        relevance_state=RelevanceState.CONFIRMED,
        evidence_kind=RelevanceEvidenceKind.SOURCE_DIRECT,
        evidence_ref="source:SRC-1",
        evidence_as_of="2026-09-28T09:10:00+09:00",
        relation_payload={},
    )
    with pytest.raises(EventEvidenceContractError) as event_missing:
        entities.attach_relevance(missing_event)
    assert event_missing.value.code == "EVENT_RELEVANCE_EVENT_NOT_FOUND"

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE event_evidence_entity SET name='changed' WHERE entity_id=?",
                (company["entity_id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "DELETE FROM event_evidence_entity_relevance WHERE relevance_id=?",
                (stored["relevance_id"],),
            )


def test_relevance_as_of_hides_future_relation_evidence(tmp_path: Path):
    _, entities = _fixture(tmp_path)
    company = entities.register_entity(
        EventEntityRef.listed_company(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            identity_source="KRX_MASTER",
            identity_as_of="2026-09-28T00:00:00+09:00",
        )
    )
    entities.attach_relevance(
        EventEntityRelevance(
            event_id="EVENT-1",
            event_version=1,
            entity_id=company["entity_id"],
            relation_type=RelevanceRelation.DIRECT_COMPANY,
            relevance_state=RelevanceState.CONFIRMED,
            evidence_kind=RelevanceEvidenceKind.SOURCE_DIRECT,
            evidence_ref="late-proof",
            evidence_as_of="2026-09-28T11:00:00+09:00",
            relation_payload={},
        )
    )
    assert entities.list_event_entities(
        "EVENT-1",
        1,
        cutoff="2026-09-28T10:00:00+09:00",
    ) == []
    assert len(
        entities.list_event_entities(
            "EVENT-1",
            1,
            cutoff="2026-09-28T12:00:00+09:00",
        )
    ) == 1
