from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.event_evidence import (
    DuplicateClassification,
    EventEntityRef,
    EventEntityRelevance,
    EventEntityService,
    EventEvidenceContractError,
    EventEvidenceSourcePolicy,
    EventEvidenceSourceRef,
    EventEvidenceState,
    EventEvidenceStore,
    EventResolutionService,
    EventRevisionIdentity,
    EvidenceTimeQuality,
    RelevanceEvidenceKind,
    RelevanceRelation,
    RelevanceState,
    TemporalEvidence,
)
from tools.data.migrate_event_evidence_vnp6s1 import migrate_event_evidence_store


NOW = "2026-09-28T05:40:00+00:00"


def _policy() -> EventEvidenceSourcePolicy:
    return EventEvidenceSourcePolicy(
        policy_id="TEST-P6-C-RESOLUTION-V1",
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


def _temporal(
    minute: int,
    *,
    event_time: str = "2026-09-28T09:00:00+09:00",
) -> TemporalEvidence:
    return TemporalEvidence(
        event_time=event_time,
        source_published_at=f"2026-09-28T09:{max(0, minute-3):02d}:00+09:00",
        provider_published_at=f"2026-09-28T09:{max(0, minute-1):02d}:00+09:00",
        first_seen_at=f"2026-09-28T09:{minute:02d}:00+09:00",
        available_at=f"2026-09-28T09:{minute:02d}:00+09:00",
        fetched_at=f"2026-09-28T09:{minute:02d}:03+09:00",
        time_quality=EvidenceTimeQuality.EXACT,
    )


def _base(tmp_path: Path):
    db = tmp_path / "simulation.db"
    sqlite3.connect(db).close()
    migrate_event_evidence_store(db)
    policy = _policy()
    store = EventEvidenceStore(db, clock=lambda: NOW)
    entities = EventEntityService(db, clock=lambda: NOW)
    resolver = EventResolutionService(db, clock=lambda: NOW)
    company = entities.register_entity(
        EventEntityRef.listed_company(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            identity_source="KRX_MASTER",
            identity_as_of="2026-09-28T00:00:00+09:00",
        )
    )
    other = entities.register_entity(
        EventEntityRef.listed_company(
            market="KOSPI",
            ticker="000660",
            name="SK하이닉스",
            identity_source="KRX_MASTER",
            identity_as_of="2026-09-28T00:00:00+09:00",
        )
    )
    return db, policy, store, entities, resolver, company, other


def _add_event(
    *,
    policy,
    store,
    entities,
    event_id: str,
    source_id: str,
    minute: int,
    company,
    official_id: str | None,
    content_char: str,
    source_native_id: str | None = None,
    event_type: str = "RIGHTS_ISSUE",
    core_facts: dict | None = None,
):
    source = EventEvidenceSourceRef(
        source_ref_id=source_id,
        source_kind=policy.source_kind,
        source_native_id=source_native_id or f"native-{source_id}",
        rights_policy_id=policy.policy_id,
        content_hash=content_char * 64,
        temporal=_temporal(minute),
    )
    store.store_source_ref(policy=policy, source_ref=source)
    payload = {}
    if official_id is not None:
        payload["official_event_id"] = official_id
    if core_facts is not None:
        payload["core_facts"] = core_facts
    store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id=event_id,
            version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type=event_type,
        scope="COMPANY",
        temporal=_temporal(minute),
        event_payload=payload,
        source_ref_ids=[source_id],
    )
    entities.attach_relevance(
        EventEntityRelevance(
            event_id=event_id,
            event_version=1,
            entity_id=company["entity_id"],
            relation_type=RelevanceRelation.DIRECT_COMPANY,
            relevance_state=RelevanceState.CONFIRMED,
            evidence_kind=RelevanceEvidenceKind.SOURCE_DIRECT,
            evidence_ref=f"source:{source_id}",
            evidence_as_of=f"2026-09-28T09:{minute:02d}:00+09:00",
            relation_payload={"source_ref_id": source_id},
        )
    )


def test_official_identity_is_exact_duplicate_and_can_be_canonicalized(tmp_path: Path):
    _, policy, store, entities, resolver, company, _ = _base(tmp_path)
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-A",
        source_id="SRC-A",minute=10,company=company,official_id="DART-123",
        content_char="a",
    )
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-B",
        source_id="SRC-B",minute=20,company=company,official_id="DART-123",
        content_char="b",
    )

    classified = resolver.classify_duplicate("EVENT-A",1,"EVENT-B",1)
    assert classified["classification"] == DuplicateClassification.EXACT_DUPLICATE.value
    assert classified["basis"] == "OFFICIAL_IDENTITY_MATCH"

    group = resolver.resolve_duplicate("EVENT-A",1,"EVENT-B",1)
    assert len(group["members"]) == 2
    assert {row["resolution_type"] for row in group["members"]} == {
        "CANONICAL","EXACT_DUPLICATE"
    }


def test_same_type_entity_date_without_stable_identity_is_candidate_only(tmp_path: Path):
    _, policy, store, entities, resolver, company, _ = _base(tmp_path)
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-A",
        source_id="SRC-A",minute=10,company=company,official_id=None,
        content_char="a",
    )
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-B",
        source_id="SRC-B",minute=20,company=company,official_id=None,
        content_char="b",
    )

    classified = resolver.classify_duplicate("EVENT-A",1,"EVENT-B",1)
    assert classified["classification"] == DuplicateClassification.SAME_EVENT_CANDIDATE.value
    with pytest.raises(EventEvidenceContractError) as blocked:
        resolver.resolve_duplicate("EVENT-A",1,"EVENT-B",1)
    assert blocked.value.code == "EVENT_DUPLICATE_NOT_EXACT"

    with sqlite3.connect(resolver.simulation_db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM event_evidence_canonical_group"
        ).fetchone()[0] == 0


def test_same_event_type_different_direct_entities_are_distinct(tmp_path: Path):
    _, policy, store, entities, resolver, company, other = _base(tmp_path)
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-A",
        source_id="SRC-A",minute=10,company=company,official_id=None,
        content_char="a",
    )
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-B",
        source_id="SRC-B",minute=20,company=other,official_id=None,
        content_char="b",
    )

    classified = resolver.classify_duplicate("EVENT-A",1,"EVENT-B",1)
    assert classified == {
        "classification": DuplicateClassification.DISTINCT.value,
        "basis": "DIRECT_ENTITY_DIFFERS",
        "fingerprint_a": classified["fingerprint_a"],
        "fingerprint_b": classified["fingerprint_b"],
    }


def test_same_official_identity_with_conflicting_core_facts_fails_closed(tmp_path: Path):
    _, policy, store, entities, resolver, company, _ = _base(tmp_path)
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-A",
        source_id="SRC-A",minute=10,company=company,official_id="OFF-1",
        content_char="a",core_facts={"amount": 100},
    )
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-B",
        source_id="SRC-B",minute=20,company=company,official_id="OFF-1",
        content_char="b",core_facts={"amount": 200},
    )
    with pytest.raises(EventEvidenceContractError) as conflict:
        resolver.classify_duplicate("EVENT-A",1,"EVENT-B",1)
    assert conflict.value.code == "CONFLICTING_SOURCE_FACTS"


def test_correction_resolution_is_as_of_and_withdrawal_is_not_deleted(tmp_path: Path):
    _, policy, store, entities, resolver, company, _ = _base(tmp_path)
    source1 = EventEvidenceSourceRef(
        source_ref_id="SRC-V1",
        source_kind=policy.source_kind,
        source_native_id="notice-v1",
        rights_policy_id=policy.policy_id,
        content_hash="a" * 64,
        temporal=_temporal(10),
    )
    store.store_source_ref(policy=policy, source_ref=source1)
    store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-CORRECTION",
            version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type="RIGHTS_ISSUE",
        scope="COMPANY",
        temporal=_temporal(10),
        event_payload={"official_event_id":"OFF-C","value":1},
        source_ref_ids=["SRC-V1"],
    )
    entities.attach_relevance(
        EventEntityRelevance(
            event_id="EVENT-CORRECTION",event_version=1,
            entity_id=company["entity_id"],
            relation_type=RelevanceRelation.DIRECT_COMPANY,
            relevance_state=RelevanceState.CONFIRMED,
            evidence_kind=RelevanceEvidenceKind.SOURCE_DIRECT,
            evidence_ref="SRC-V1",
            evidence_as_of="2026-09-28T09:10:00+09:00",
            relation_payload={},
        )
    )

    source2 = EventEvidenceSourceRef(
        source_ref_id="SRC-V2",
        source_kind=policy.source_kind,
        source_native_id="notice-v2",
        rights_policy_id=policy.policy_id,
        content_hash="b" * 64,
        temporal=TemporalEvidence(
            event_time="2026-09-28T09:00:00+09:00",
            source_published_at="2026-09-28T11:20:00+09:00",
            provider_published_at="2026-09-28T11:25:00+09:00",
            first_seen_at="2026-09-28T11:30:00+09:00",
            available_at="2026-09-28T11:30:00+09:00",
            fetched_at="2026-09-28T11:30:03+09:00",
            corrected_at="2026-09-28T11:30:00+09:00",
            time_quality=EvidenceTimeQuality.EXACT,
        ),
    )
    store.store_source_ref(policy=policy, source_ref=source2)
    store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-CORRECTION",
            version=2,
            state=EventEvidenceState.CORRECTED,
            supersedes_version=1,
        ),
        event_type="RIGHTS_ISSUE",
        scope="COMPANY",
        temporal=source2.temporal,
        event_payload={"official_event_id":"OFF-C","value":2},
        source_ref_ids=["SRC-V2"],
    )

    before = resolver.resolve_event_as_of(
        "EVENT-CORRECTION","2026-09-28T10:00:00+09:00"
    )
    after = resolver.resolve_event_as_of(
        "EVENT-CORRECTION","2026-09-28T12:00:00+09:00"
    )
    assert before is not None and before["event_version"] == 1
    assert after is not None and after["event_version"] == 2
    assert after["event_state"] == "CORRECTED"

    source3 = EventEvidenceSourceRef(
        source_ref_id="SRC-V3",
        source_kind=policy.source_kind,
        source_native_id="notice-v3",
        rights_policy_id=policy.policy_id,
        content_hash="c" * 64,
        temporal=TemporalEvidence(
            event_time="2026-09-28T09:00:00+09:00",
            source_published_at="2026-09-28T13:20:00+09:00",
            provider_published_at="2026-09-28T13:25:00+09:00",
            first_seen_at="2026-09-28T13:30:00+09:00",
            available_at="2026-09-28T13:30:00+09:00",
            fetched_at="2026-09-28T13:30:03+09:00",
            corrected_at="2026-09-28T13:30:00+09:00",
            time_quality=EvidenceTimeQuality.EXACT,
        ),
    )
    store.store_source_ref(policy=policy, source_ref=source3)
    store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-CORRECTION",
            version=3,
            state=EventEvidenceState.WITHDRAWN,
            supersedes_version=2,
        ),
        event_type="RIGHTS_ISSUE",
        scope="COMPANY",
        temporal=source3.temporal,
        event_payload={"official_event_id":"OFF-C","withdrawn":True},
        source_ref_ids=["SRC-V3"],
    )
    current = resolver.resolve_event_as_of(
        "EVENT-CORRECTION","2026-09-28T14:00:00+09:00"
    )
    assert current is not None
    assert current["event_version"] == 3
    assert current["event_state"] == "WITHDRAWN"


def test_canonical_as_of_hides_later_duplicate_source(tmp_path: Path):
    _, policy, store, entities, resolver, company, _ = _base(tmp_path)
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-A",
        source_id="SRC-A",minute=10,company=company,official_id="OFF-1",
        content_char="a",
    )
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-B",
        source_id="SRC-B",minute=40,company=company,official_id="OFF-1",
        content_char="b",
    )
    group = resolver.resolve_duplicate("EVENT-A",1,"EVENT-B",1)

    early = resolver.resolve_canonical_event_as_of(
        group["canonical_event_id"],
        "2026-09-28T09:20:00+09:00",
    )
    late = resolver.resolve_canonical_event_as_of(
        group["canonical_event_id"],
        "2026-09-28T10:00:00+09:00",
    )
    assert [s["source_ref_id"] for s in early["visible_sources"]] == ["SRC-A"]
    assert [s["source_ref_id"] for s in late["visible_sources"]] == [
        "SRC-A","SRC-B"
    ]


def test_resolution_rows_are_immutable(tmp_path: Path):
    db, policy, store, entities, resolver, company, _ = _base(tmp_path)
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-A",
        source_id="SRC-A",minute=10,company=company,official_id="OFF-1",
        content_char="a",
    )
    _add_event(
        policy=policy,store=store,entities=entities,event_id="EVENT-B",
        source_id="SRC-B",minute=20,company=company,official_id="OFF-1",
        content_char="b",
    )
    group = resolver.resolve_duplicate("EVENT-A",1,"EVENT-B",1)
    with sqlite3.connect(db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE event_evidence_canonical_group
                SET resolution_confidence='CHANGED'
                WHERE canonical_event_id=?
                """,
                (group["canonical_event_id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                DELETE FROM event_evidence_resolution
                WHERE canonical_event_id=?
                """,
                (group["canonical_event_id"],),
            )
