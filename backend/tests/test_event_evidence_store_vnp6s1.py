from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.event_evidence import (
    EvidenceTimeQuality,
    EventEvidenceContractError,
    EventEvidenceSourcePolicy,
    EventEvidenceSourceRef,
    EventEvidenceState,
    EventEvidenceStore,
    EventRevisionIdentity,
    TemporalEvidence,
    opendart_event_evidence_policy,
    policy_for_event_source,
)
from tools.data.migrate_event_evidence_vnp6s1 import (
    migrate_event_evidence_store,
)


NOW = "2026-09-28T05:10:00+00:00"


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "simulation.db"
    sqlite3.connect(path).close()
    migrate_event_evidence_store(path)
    return path


def _temporal(
    *,
    minute: int = 12,
    quality: EvidenceTimeQuality = EvidenceTimeQuality.EXACT,
) -> TemporalEvidence:
    return TemporalEvidence(
        event_time=(
            "2026-09-28"
            if quality is EvidenceTimeQuality.DATE_ONLY
            else f"2026-09-28T09:00:00+09:00"
        ),
        source_published_at=f"2026-09-28T09:05:00+09:00",
        provider_published_at=f"2026-09-28T09:11:00+09:00",
        first_seen_at=f"2026-09-28T09:{minute:02d}:00+09:00",
        available_at=f"2026-09-28T09:{minute:02d}:00+09:00",
        fetched_at=f"2026-09-28T09:{minute:02d}:03+09:00",
        time_quality=quality,
    )


def _test_policy(policy_id: str = "TEST-P6-RETENTION-V1") -> EventEvidenceSourcePolicy:
    return EventEvidenceSourcePolicy(
        policy_id=policy_id,
        source_kind="TEST_SYNTHETIC",
        policy_version="test-synthetic-retention-v1",
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


def _source(
    source_ref_id: str,
    *,
    policy: EventEvidenceSourcePolicy | None = None,
    content_hash: str = "a" * 64,
    minute: int = 12,
) -> EventEvidenceSourceRef:
    resolved = policy or _test_policy()
    return EventEvidenceSourceRef(
        source_ref_id=source_ref_id,
        source_kind=resolved.source_kind,
        source_native_id=f"native-{source_ref_id}",
        rights_policy_id=resolved.policy_id,
        content_hash=content_hash,
        source_url=f"https://example.test/{source_ref_id}",
        source_name="fixture",
        temporal=_temporal(minute=minute),
    )


def test_migration_is_idempotent_and_performs_no_backfill(tmp_path: Path):
    path = tmp_path / "simulation.db"
    sqlite3.connect(path).close()

    first = migrate_event_evidence_store(path)
    second = migrate_event_evidence_store(path)

    assert first["schema_version"] == "VN_P6_S1_EVENT_EVIDENCE_STORE_V1"
    assert first["policy_snapshot_count"] == 0
    assert first["source_ref_count"] == 0
    assert first["event_evidence_count"] == 0
    assert first["historical_backfill_performed"] is False
    assert first["news_backfill_performed"] is False
    assert first["dart_eventrisk_backfill_performed"] is False
    assert first["external_network_requests"] == 0
    assert second["policy_snapshot_count"] == 0
    assert second["source_ref_count"] == 0
    assert second["event_evidence_count"] == 0


@pytest.mark.parametrize(
    ("policy", "source_kind"),
    [
        (
            policy_for_event_source("NAVER_NEWS", provider_kind="api_hub"),
            "NAVER_NEWS",
        ),
        (
            opendart_event_evidence_policy(),
            "OPENDART_DISCLOSURE",
        ),
    ],
)
def test_current_production_sources_cannot_be_retained_as_p6_evidence(
    tmp_path: Path,
    policy: EventEvidenceSourcePolicy,
    source_kind: str,
):
    store = EventEvidenceStore(_db(tmp_path), clock=lambda: NOW)
    source = EventEvidenceSourceRef(
        source_ref_id=f"SRC-{source_kind}",
        source_kind=source_kind,
        source_native_id="native-1",
        rights_policy_id=policy.policy_id,
        content_hash="b" * 64,
        temporal=_temporal(),
    )

    with pytest.raises(EventEvidenceContractError) as blocked:
        store.store_source_ref(policy=policy, source_ref=source)
    assert blocked.value.code == "EVENT_EVIDENCE_CAPABILITY_NOT_ALLOWED"

    with sqlite3.connect(store.simulation_db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM event_evidence_policy_snapshot"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM event_evidence_source_ref"
        ).fetchone()[0] == 0


def test_source_ref_snapshots_policy_is_idempotent_and_immutable(tmp_path: Path):
    db = _db(tmp_path)
    store = EventEvidenceStore(db, clock=lambda: NOW)
    policy = _test_policy()
    source = _source("SRC-1", policy=policy)

    first = store.store_source_ref(policy=policy, source_ref=source)
    second = store.store_source_ref(policy=policy, source_ref=source)

    assert first["source_ref_hash"] == second["source_ref_hash"]
    assert store.verify_source_ref("SRC-1")["status"] == "MATCH"

    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM event_evidence_policy_snapshot"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM event_evidence_source_ref"
        ).fetchone()[0] == 1

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE event_evidence_policy_snapshot
                SET policy_basis='changed'
                WHERE policy_id=?
                """,
                (policy.policy_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE event_evidence_source_ref
                SET source_name='changed'
                WHERE source_ref_id='SRC-1'
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "DELETE FROM event_evidence_source_ref WHERE source_ref_id='SRC-1'"
            )


def test_source_policy_identity_and_source_identity_conflicts_fail_closed(
    tmp_path: Path,
):
    store = EventEvidenceStore(_db(tmp_path), clock=lambda: NOW)
    policy = _test_policy()

    wrong_kind = EventEvidenceSourceRef(
        source_ref_id="SRC-WRONG-KIND",
        source_kind="OTHER_SOURCE",
        source_native_id="native",
        rights_policy_id=policy.policy_id,
        content_hash="c" * 64,
        temporal=_temporal(),
    )
    with pytest.raises(EventEvidenceContractError) as kind:
        store.store_source_ref(policy=policy, source_ref=wrong_kind)
    assert kind.value.code == "EVENT_EVIDENCE_POLICY_SOURCE_MISMATCH"

    wrong_policy = EventEvidenceSourceRef(
        source_ref_id="SRC-WRONG-POLICY",
        source_kind=policy.source_kind,
        source_native_id="native",
        rights_policy_id="SOME-OTHER-POLICY",
        content_hash="c" * 64,
        temporal=_temporal(),
    )
    with pytest.raises(EventEvidenceContractError) as policy_mismatch:
        store.store_source_ref(policy=policy, source_ref=wrong_policy)
    assert policy_mismatch.value.code == "EVENT_EVIDENCE_POLICY_REFERENCE_MISMATCH"

    store.store_source_ref(policy=policy, source_ref=_source("SRC-1", policy=policy))
    changed = _source(
        "SRC-1",
        policy=policy,
        content_hash="d" * 64,
    )
    with pytest.raises(EventEvidenceContractError) as conflict:
        store.store_source_ref(policy=policy, source_ref=changed)
    assert conflict.value.code == "EVENT_EVIDENCE_SOURCE_IDENTITY_CONFLICT"


def test_event_revision_chain_hashes_sources_and_preserves_idempotency(
    tmp_path: Path,
):
    db = _db(tmp_path)
    store = EventEvidenceStore(db, clock=lambda: NOW)
    policy = _test_policy()
    for ref in (
        _source("SRC-A", policy=policy, content_hash="a" * 64, minute=12),
        _source("SRC-B", policy=policy, content_hash="b" * 64, minute=13),
    ):
        store.store_source_ref(policy=policy, source_ref=ref)

    original = store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-1",
            version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type="RIGHTS_ISSUE",
        scope="COMPANY",
        temporal=_temporal(minute=13),
        event_payload={"summary": "synthetic normalized event"},
        source_ref_ids=["SRC-B", "SRC-A"],
    )
    repeated = store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-1",
            version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type="RIGHTS_ISSUE",
        scope="COMPANY",
        temporal=_temporal(minute=13),
        event_payload={"summary": "synthetic normalized event"},
        source_ref_ids=["SRC-A", "SRC-B"],
    )

    assert original["event_hash"] == repeated["event_hash"]
    assert original["source_bundle_hash"] == repeated["source_bundle_hash"]
    assert [row["source_ref_id"] for row in original["sources"]] == [
        "SRC-A",
        "SRC-B",
    ]
    assert store.verify_event_revision("EVENT-1", 1)["status"] == "MATCH"

    corrected = store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-1",
            version=2,
            state=EventEvidenceState.CORRECTED,
            supersedes_version=1,
        ),
        event_type="RIGHTS_ISSUE",
        scope="COMPANY",
        temporal=_temporal(minute=13),
        event_payload={"summary": "synthetic corrected event"},
        source_ref_ids=["SRC-A", "SRC-B"],
    )
    assert corrected["supersedes_version"] == 1
    assert [row["event_version"] for row in store.list_event_revisions("EVENT-1")] == [
        1,
        2,
    ]

    with pytest.raises(EventEvidenceContractError) as branch:
        store.create_event_revision(
            identity=EventRevisionIdentity(
                event_id="EVENT-1",
                version=3,
                state=EventEvidenceState.SUPERSEDED,
                supersedes_version=1,
            ),
            event_type="RIGHTS_ISSUE",
            scope="COMPANY",
            temporal=_temporal(minute=13),
            event_payload={"summary": "branch attempt"},
            source_ref_ids=["SRC-A"],
        )
    assert branch.value.code == "EVENT_EVIDENCE_REVISION_CHAIN_CONFLICT"

    with pytest.raises(EventEvidenceContractError) as identity_conflict:
        store.create_event_revision(
            identity=EventRevisionIdentity(
                event_id="EVENT-1",
                version=2,
                state=EventEvidenceState.CORRECTED,
                supersedes_version=1,
            ),
            event_type="RIGHTS_ISSUE",
            scope="COMPANY",
            temporal=_temporal(minute=13),
            event_payload={"summary": "different same identity"},
            source_ref_ids=["SRC-A", "SRC-B"],
        )
    assert identity_conflict.value.code == "EVENT_EVIDENCE_IDENTITY_CONFLICT"


def test_source_bundle_hash_is_independent_of_input_order(tmp_path: Path):
    store = EventEvidenceStore(_db(tmp_path), clock=lambda: NOW)
    policy = _test_policy()
    store.store_source_ref(policy=policy, source_ref=_source("SRC-A", policy=policy))
    store.store_source_ref(
        policy=policy,
        source_ref=_source("SRC-B", policy=policy, content_hash="b" * 64),
    )

    first = store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-A",
            version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type="LARGE_CONTRACT",
        scope="COMPANY",
        temporal=_temporal(),
        event_payload={"kind": "fixture"},
        source_ref_ids=["SRC-A", "SRC-B"],
    )
    second = store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-B",
            version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type="LARGE_CONTRACT",
        scope="COMPANY",
        temporal=_temporal(),
        event_payload={"kind": "fixture"},
        source_ref_ids=["SRC-B", "SRC-A"],
    )
    assert first["source_bundle_hash"] == second["source_bundle_hash"]


@pytest.mark.parametrize(
    "blocked_key",
    [
        "raw_content",
        "article_body",
        "full_article",
        "full_text",
        "document_text",
        "raw_html",
    ],
)
def test_event_payload_cannot_hide_raw_article_or_document_content(
    tmp_path: Path,
    blocked_key: str,
):
    store = EventEvidenceStore(_db(tmp_path), clock=lambda: NOW)
    policy = _test_policy()
    store.store_source_ref(policy=policy, source_ref=_source("SRC-1", policy=policy))

    with pytest.raises(EventEvidenceContractError) as blocked:
        store.create_event_revision(
            identity=EventRevisionIdentity(
                event_id=f"EVENT-{blocked_key.upper()}",
                version=1,
                state=EventEvidenceState.ORIGINAL,
            ),
            event_type="OTHER_DISCLOSURE",
            scope="COMPANY",
            temporal=_temporal(),
            event_payload={"nested": {blocked_key: "do not persist this"}},
            source_ref_ids=["SRC-1"],
        )
    assert blocked.value.code == "EVENT_EVIDENCE_RAW_CONTENT_FORBIDDEN"


def test_event_and_links_are_db_immutable_and_fk_protected(tmp_path: Path):
    db = _db(tmp_path)
    store = EventEvidenceStore(db, clock=lambda: NOW)
    policy = _test_policy()
    store.store_source_ref(policy=policy, source_ref=_source("SRC-1", policy=policy))
    event = store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-IMMUTABLE",
            version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type="OTHER_DISCLOSURE",
        scope="COMPANY",
        temporal=_temporal(),
        event_payload={"summary": "fixture"},
        source_ref_ids=["SRC-1"],
    )

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE event_evidence_record
                SET event_type='CHANGED'
                WHERE event_id='EVENT-IMMUTABLE' AND event_version=1
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                DELETE FROM event_evidence_record
                WHERE event_id='EVENT-IMMUTABLE' AND event_version=1
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE event_evidence_record_source
                SET source_ref_hash=?
                WHERE event_id='EVENT-IMMUTABLE' AND event_version=1
                """,
                ("0" * 64,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO event_evidence_record_source(
                    event_id,event_version,sequence,source_ref_id,source_ref_hash
                ) VALUES('EVENT-IMMUTABLE',1,99,'MISSING',?)
                """,
                ("0" * 64,),
            )

    assert store.verify_event_revision(
        event["event_id"],
        event["event_version"],
    )["status"] == "MATCH"
