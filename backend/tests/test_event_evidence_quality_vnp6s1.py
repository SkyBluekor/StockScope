from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.event_evidence import (
    EvidenceQualityScope,
    EvidenceTimeQuality,
    EventEntityRef,
    EventEntityRelevance,
    EventEntityService,
    EventEvidenceQualityService,
    EventEvidenceSourcePolicy,
    EventEvidenceSourceRef,
    EventEvidenceState,
    EventEvidenceStore,
    EventResolutionService,
    EventRevisionIdentity,
    RelevanceEvidenceKind,
    RelevanceRelation,
    RelevanceState,
    TemporalEvidence,
)
from tools.data.migrate_event_evidence_vnp6s1 import migrate_event_evidence_store


NOW = "2026-09-28T05:50:00+00:00"


def _policy(*, historical: bool = True) -> EventEvidenceSourcePolicy:
    return EventEvidenceSourcePolicy(
        policy_id=(
            "TEST-P6-D-HIST-V1" if historical else "TEST-P6-D-REF-ONLY-V1"
        ),
        source_kind="TEST_SYNTHETIC",
        policy_version="test-v1",
        display_allowed=True,
        normalization_allowed=True,
        raw_retention_allowed=False,
        derived_retention_allowed=True,
        ai_transform_allowed=False,
        historical_evaluation_allowed=historical,
        prediction_input_allowed=False,
        attribution_required=False,
        policy_basis="TEST_FIXTURE_ONLY",
    )


def _temporal(
    available_at: str,
    *,
    quality: EvidenceTimeQuality = EvidenceTimeQuality.EXACT,
    corrected: bool = False,
) -> TemporalEvidence:
    event_time = (
        "2026-09-28"
        if quality is EvidenceTimeQuality.DATE_ONLY
        else "2026-09-28T09:00:00+09:00"
    )
    return TemporalEvidence(
        event_time=event_time,
        source_published_at=available_at,
        provider_published_at=available_at,
        first_seen_at=available_at,
        available_at=available_at,
        fetched_at=available_at,
        corrected_at=available_at if corrected else None,
        time_quality=quality,
    )


def _base(tmp_path: Path, *, historical: bool = True):
    db = tmp_path / "simulation.db"
    sqlite3.connect(db).close()
    migrate_event_evidence_store(db)
    policy = _policy(historical=historical)
    store = EventEvidenceStore(db, clock=lambda: NOW)
    entities = EventEntityService(db, clock=lambda: NOW)
    resolver = EventResolutionService(db, clock=lambda: NOW)
    quality = EventEvidenceQualityService(db, clock=lambda: NOW)
    company = entities.register_entity(
        EventEntityRef.listed_company(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            identity_source="KRX_MASTER",
            identity_as_of="2026-09-28T00:00:00+09:00",
        )
    )
    return db, policy, store, entities, resolver, quality, company


def _add_event(
    *,
    policy: EventEvidenceSourcePolicy,
    store: EventEvidenceStore,
    entities: EventEntityService,
    company: dict,
    event_id: str,
    version: int = 1,
    state: EventEvidenceState = EventEvidenceState.ORIGINAL,
    supersedes_version: int | None = None,
    source_id: str,
    content_char: str,
    available_at: str,
    quality: EvidenceTimeQuality = EvidenceTimeQuality.EXACT,
    relevance_state: RelevanceState = RelevanceState.CONFIRMED,
    evidence_kind: RelevanceEvidenceKind = RelevanceEvidenceKind.SOURCE_DIRECT,
    evidence_as_of: str | None = None,
    official_id: str | None = None,
):
    temporal = _temporal(
        available_at,
        quality=quality,
        corrected=version > 1,
    )
    source = EventEvidenceSourceRef(
        source_ref_id=source_id,
        source_kind=policy.source_kind,
        source_native_id=f"native-{source_id}",
        rights_policy_id=policy.policy_id,
        content_hash=content_char * 64,
        source_name=f"origin-{source_id}",
        temporal=temporal,
    )
    store.store_source_ref(policy=policy, source_ref=source)
    payload = {}
    if official_id is not None:
        payload["official_event_id"] = official_id
    event = store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id=event_id,
            version=version,
            state=state,
            supersedes_version=supersedes_version,
        ),
        event_type="RIGHTS_ISSUE",
        scope="COMPANY",
        temporal=temporal,
        event_payload=payload,
        source_ref_ids=[source_id],
    )
    relevance = entities.attach_relevance(
        EventEntityRelevance(
            event_id=event_id,
            event_version=version,
            entity_id=company["entity_id"],
            relation_type=RelevanceRelation.DIRECT_COMPANY,
            relevance_state=relevance_state,
            evidence_kind=evidence_kind,
            evidence_ref=f"source:{source_id}",
            evidence_as_of=evidence_as_of or available_at,
            relation_payload={"source_ref_id": source_id},
        )
    )
    return event, relevance


def test_quality_migration_is_idempotent_and_does_not_backfill(tmp_path: Path):
    db = tmp_path / "simulation.db"
    sqlite3.connect(db).close()
    first = migrate_event_evidence_store(db)
    second = migrate_event_evidence_store(db)

    assert first["quality_assessment_count"] == 0
    assert second["quality_assessment_count"] == 0
    assert first["news_backfill_performed"] is False
    assert first["dart_eventrisk_backfill_performed"] is False
    assert first["external_network_requests"] == 0


def test_confirmed_exact_evidence_is_usable_for_reference_and_historical(
    tmp_path: Path,
):
    db, policy, store, entities, _, quality, company = _base(tmp_path)
    _, relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-1",
        source_id="SRC-1",
        content_char="a",
        available_at="2026-09-28T09:10:00+09:00",
    )

    reference = quality.assess_event_entity(
        event_id="EVENT-1",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope=EvidenceQualityScope.REFERENCE,
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )
    historical = quality.assess_event_entity(
        event_id="EVENT-1",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope=EvidenceQualityScope.HISTORICAL_EVALUATION,
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )

    assert reference["quality_state"] == "USABLE"
    assert historical["quality_state"] == "USABLE"
    assert "SINGLE_SOURCE_ONLY" in reference["limitations"]
    assert quality.verify_assessment(reference["assessment_id"])["status"] == "MATCH"

    with sqlite3.connect(db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE event_evidence_quality_assessment
                SET quality_state='BLOCKED'
                WHERE assessment_id=?
                """,
                (reference["assessment_id"],),
            )


def test_reference_rights_do_not_grant_historical_evaluation_rights(
    tmp_path: Path,
):
    _, policy, store, entities, _, quality, company = _base(
        tmp_path,
        historical=False,
    )
    _, relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-RIGHTS",
        source_id="SRC-RIGHTS",
        content_char="b",
        available_at="2026-09-28T09:10:00+09:00",
    )

    reference = quality.assess_event_entity(
        event_id="EVENT-RIGHTS",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )
    historical = quality.assess_event_entity(
        event_id="EVENT-RIGHTS",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope="HISTORICAL_EVALUATION",
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )

    assert reference["quality_state"] == "USABLE"
    assert historical["quality_state"] == "BLOCKED"
    assert (
        "HISTORICAL_EVALUATION_RIGHTS_NOT_ALLOWED"
        in historical["blocking_reasons"]
    )


def test_date_only_is_limited_for_reference_and_blocked_for_historical(
    tmp_path: Path,
):
    _, policy, store, entities, _, quality, company = _base(tmp_path)
    _, relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-DATE",
        source_id="SRC-DATE",
        content_char="c",
        available_at="2026-09-28T09:10:00+09:00",
        quality=EvidenceTimeQuality.DATE_ONLY,
    )

    reference = quality.assess_event_entity(
        event_id="EVENT-DATE",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )
    historical = quality.assess_event_entity(
        event_id="EVENT-DATE",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope="HISTORICAL_EVALUATION",
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )

    assert reference["quality_state"] == "LIMITED"
    assert "TIME_DATE_ONLY" in reference["limitations"]
    assert historical["quality_state"] == "BLOCKED"
    assert "TIME_DATE_ONLY" in historical["blocking_reasons"]


@pytest.mark.parametrize(
    ("state", "expected", "reason"),
    [
        (RelevanceState.SUPPORTED, "LIMITED", "SUPPORTED_RELATION"),
        (RelevanceState.WEAK, "INSUFFICIENT", "RELEVANCE_WEAK"),
        (RelevanceState.UNKNOWN, "INSUFFICIENT", "RELEVANCE_UNKNOWN"),
        (RelevanceState.REJECTED, "BLOCKED", "RELEVANCE_REJECTED"),
    ],
)
def test_relevance_quality_states_are_not_market_scores(
    tmp_path: Path,
    state: RelevanceState,
    expected: str,
    reason: str,
):
    _, policy, store, entities, _, quality, company = _base(tmp_path)
    _, relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id=f"EVENT-{state.value}",
        source_id=f"SRC-{state.value}",
        content_char="d",
        available_at="2026-09-28T09:10:00+09:00",
        relevance_state=state,
        evidence_kind=(
            RelevanceEvidenceKind.STRUCTURED_RELATION
            if state is RelevanceState.SUPPORTED
            else RelevanceEvidenceKind.MANUAL_REVIEW
        ),
    )
    result = quality.assess_event_entity(
        event_id=f"EVENT-{state.value}",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )

    assert result["quality_state"] == expected
    all_reasons = (
        result["blocking_reasons"]
        + result["insufficient_reasons"]
        + result["limitations"]
    )
    assert reason in all_reasons
    assert "score" not in result["quality"]


def test_future_relevance_is_blocked_until_its_evidence_time(tmp_path: Path):
    _, policy, store, entities, _, quality, company = _base(tmp_path)
    _, relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-FUTURE-REL",
        source_id="SRC-FUTURE-REL",
        content_char="e",
        available_at="2026-09-28T09:10:00+09:00",
        evidence_as_of="2026-09-28T11:00:00+09:00",
    )

    before = quality.assess_event_entity(
        event_id="EVENT-FUTURE-REL",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )
    after = quality.assess_event_entity(
        event_id="EVENT-FUTURE-REL",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T12:00:00+09:00",
    )

    assert before["quality_state"] == "BLOCKED"
    assert "FUTURE_RELEVANCE" in before["blocking_reasons"]
    assert after["quality_state"] == "USABLE"


def test_correction_and_withdrawal_are_resolved_as_of(tmp_path: Path):
    _, policy, store, entities, _, quality, company = _base(tmp_path)
    _, rel1 = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-REV",
        source_id="SRC-REV-1",
        content_char="a",
        available_at="2026-09-28T09:10:00+09:00",
        official_id="OFF-REV",
    )
    _, rel2 = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-REV",
        version=2,
        state=EventEvidenceState.CORRECTED,
        supersedes_version=1,
        source_id="SRC-REV-2",
        content_char="b",
        available_at="2026-09-28T11:30:00+09:00",
        official_id="OFF-REV",
    )

    before = quality.assess_event_entity(
        event_id="EVENT-REV",
        entity_id=company["entity_id"],
        relevance_id=rel1["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )
    after = quality.assess_event_entity(
        event_id="EVENT-REV",
        entity_id=company["entity_id"],
        relevance_id=rel2["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T12:00:00+09:00",
    )
    assert before["event_version"] == 1
    assert before["revision_state"] == "ORIGINAL"
    assert after["event_version"] == 2
    assert after["revision_state"] == "CORRECTED"

    _, rel3 = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-REV",
        version=3,
        state=EventEvidenceState.WITHDRAWN,
        supersedes_version=2,
        source_id="SRC-REV-3",
        content_char="c",
        available_at="2026-09-28T13:30:00+09:00",
        official_id="OFF-REV",
    )
    withdrawn = quality.assess_event_entity(
        event_id="EVENT-REV",
        entity_id=company["entity_id"],
        relevance_id=rel3["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T14:00:00+09:00",
    )
    assert withdrawn["quality_state"] == "BLOCKED"
    assert "EVENT_WITHDRAWN" in withdrawn["blocking_reasons"]


def test_unresolved_duplicate_is_limited_but_exact_canonical_is_usable(
    tmp_path: Path,
):
    _, policy, store, entities, resolver, quality, company = _base(tmp_path)
    _, rel_a = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-A",
        source_id="SRC-A",
        content_char="a",
        available_at="2026-09-28T09:10:00+09:00",
    )
    _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-B",
        source_id="SRC-B",
        content_char="b",
        available_at="2026-09-28T09:20:00+09:00",
    )
    candidate = quality.assess_event_entity(
        event_id="EVENT-A",
        entity_id=company["entity_id"],
        relevance_id=rel_a["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )
    assert candidate["quality_state"] == "LIMITED"
    assert candidate["resolution_state"] == "CANDIDATE_DUPLICATE"

    _, rel_c = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-C",
        source_id="SRC-C",
        content_char="c",
        available_at="2026-09-28T09:30:00+09:00",
        official_id="OFF-EXACT",
    )
    _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-D",
        source_id="SRC-D",
        content_char="d",
        available_at="2026-09-28T09:40:00+09:00",
        official_id="OFF-EXACT",
    )
    resolver.resolve_duplicate("EVENT-C", 1, "EVENT-D", 1)
    exact = quality.assess_event_entity(
        event_id="EVENT-C",
        entity_id=company["entity_id"],
        relevance_id=rel_c["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )
    assert exact["resolution_state"] == "CANONICAL"
    assert exact["quality_state"] == "USABLE"


def test_corrupt_event_is_fail_closed_as_blocked_quality(tmp_path: Path):
    db, policy, store, entities, _, quality, company = _base(tmp_path)
    _, relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-CORRUPT",
        source_id="SRC-CORRUPT",
        content_char="f",
        available_at="2026-09-28T09:10:00+09:00",
    )

    with sqlite3.connect(db) as conn:
        conn.execute("DROP TRIGGER trg_event_record_immutable_update")
        conn.execute(
            """
            UPDATE event_evidence_record
            SET event_hash=?
            WHERE event_id='EVENT-CORRUPT' AND event_version=1
            """,
            ("0" * 64,),
        )

    result = quality.assess_event_entity(
        event_id="EVENT-CORRUPT",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope="REFERENCE",
        assessment_as_of="2026-09-28T10:00:00+09:00",
    )
    assert result["quality_state"] == "BLOCKED"
    assert result["integrity_state"] == "MISMATCH"
    assert "INTEGRITY_MISMATCH" in result["blocking_reasons"]
