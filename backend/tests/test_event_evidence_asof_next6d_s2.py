from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from app.event_evidence import (
    EVENT_REFERENCE_AS_OF_CONTRACT_VERSION,
    EVENT_REFERENCE_AS_OF_MODE,
    EventEvidenceAsOfReader,
)
from tools.data.migrate_event_evidence_vnp6s1 import (
    migrate_event_evidence_store,
)


CUTOFF = "2026-09-30T11:00:00+00:00"
BEFORE = "2026-09-30T08:00:00+00:00"
BEFORE_2 = "2026-09-30T09:00:00+00:00"
AFTER = "2026-10-01T08:00:00+00:00"
ENTITY_ID = "ENTITY-005930"
ENTITY_HASH = "1" * 64


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "simulation.db"
    sqlite3.connect(path).close()
    migrate_event_evidence_store(path)
    return path


def _ensure_entity(
    db: Path,
    *,
    identity_as_of: str = BEFORE,
    created_at: str = BEFORE,
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            INSERT OR IGNORE INTO event_evidence_entity(
                entity_id,entity_contract_version,entity_type,entity_key,
                market,ticker,name,identity_source,identity_as_of,
                identity_json,identity_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ENTITY_ID,
                "TEST_ENTITY",
                "LISTED_COMPANY",
                "KOSPI:005930",
                "KOSPI",
                "005930",
                "삼성전자",
                "TEST_MASTER",
                identity_as_of,
                _canonical_json({"market": "KOSPI", "ticker": "005930"}),
                ENTITY_HASH,
                created_at,
            ),
        )


def _insert_reference(
    db: Path,
    *,
    suffix: str,
    event_id: str | None = None,
    event_version: int = 1,
    event_state: str = "ORIGINAL",
    available_at: str = BEFORE,
    event_created_at: str = BEFORE,
    relevance_as_of: str = BEFORE,
    relevance_created_at: str = BEFORE,
    assessment_as_of: str = BEFORE_2,
    quality_created_at: str = BEFORE_2,
    source_available_at: str = BEFORE,
    source_created_at: str = BEFORE,
    policy_created_at: str = BEFORE,
    source_kind: str = "OPENDART_DISCLOSURE",
    quality_state: str = "USABLE",
    canonical_event_id: str | None = None,
) -> None:
    _ensure_entity(db)

    event_key = event_id or f"EVENT-{suffix}"
    policy_id = f"POL-{suffix}-V{event_version}"
    policy_hash = hashlib.sha256(
        f"policy:{suffix}:{event_version}".encode()
    ).hexdigest()
    source_id = f"SRC-{suffix}-V{event_version}"
    source_hash = hashlib.sha256(
        f"source:{suffix}:{event_version}".encode()
    ).hexdigest()
    event_hash = hashlib.sha256(
        f"event:{event_key}:{event_version}".encode()
    ).hexdigest()
    source_bundle_hash = hashlib.sha256(
        f"bundle:{event_key}:{event_version}".encode()
    ).hexdigest()
    relevance_id = f"REL-{suffix}-V{event_version}"
    relevance_hash = hashlib.sha256(
        f"relevance:{suffix}:{event_version}".encode()
    ).hexdigest()
    assessment_id = f"QA-{suffix}-V{event_version}"

    quality_payload = {
        "assessment_id": assessment_id,
        "source_refs": [
            {
                "source_ref_id": source_id,
                "source_ref_hash": source_hash,
                "rights_policy_id": policy_id,
                "policy_hash": policy_hash,
            }
        ],
    }
    quality_hash = _digest(quality_payload)

    canonical_version = None
    canonical_hash = None
    resolution_hash = None

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
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
                policy_id,
                "TEST_POLICY",
                source_kind,
                "v1",
                1,1,0,1,0,0,0,0,
                None,
                "TEST_ONLY",
                _canonical_json({"policy_id": policy_id}),
                policy_hash,
                policy_created_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_source_ref(
                source_ref_id,source_ref_contract_version,source_kind,
                source_native_id,rights_policy_id,rights_policy_hash,
                source_url,source_name,content_hash,event_time,
                source_published_at,provider_published_at,first_seen_at,
                available_at,fetched_at,corrected_at,time_quality,
                temporal_contract_version,source_ref_json,source_ref_hash,
                created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                source_id,
                "TEST_SOURCE",
                source_kind,
                f"native-{suffix}-{event_version}",
                policy_id,
                policy_hash,
                None,
                "Fixture",
                "9" * 64,
                available_at,
                available_at,
                available_at,
                available_at,
                source_available_at,
                max(source_available_at, source_created_at),
                None,
                "EXACT",
                "TEST_TEMPORAL",
                _canonical_json({"source_ref_id": source_id}),
                source_hash,
                source_created_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_record(
                event_id,event_version,record_version,hash_contract_version,
                event_state,supersedes_version,event_type,scope,event_time,
                available_at,time_quality,temporal_json,event_payload_json,
                source_bundle_hash,event_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_key,
                event_version,
                "TEST_RECORD",
                "TEST_HASH",
                event_state,
                event_version - 1 if event_version > 1 else None,
                "RIGHTS_ISSUE",
                "COMPANY",
                available_at,
                available_at,
                "EXACT",
                _canonical_json({"available_at": available_at}),
                "{}",
                source_bundle_hash,
                event_hash,
                event_created_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_record_source(
                event_id,event_version,sequence,source_ref_id,source_ref_hash
            ) VALUES(?,?,?,?,?)
            """,
            (event_key, event_version, 1, source_id, source_hash),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_entity_relevance(
                relevance_id,relevance_contract_version,event_id,event_version,
                event_hash,entity_id,entity_hash,relation_type,
                relevance_state,evidence_kind,evidence_ref,evidence_as_of,
                relation_json,relation_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                relevance_id,
                "TEST_REL",
                event_key,
                event_version,
                event_hash,
                ENTITY_ID,
                ENTITY_HASH,
                "DIRECT_COMPANY",
                "CONFIRMED",
                "SOURCE_DIRECT",
                f"source:{source_id}",
                relevance_as_of,
                _canonical_json({"source_ref_id": source_id}),
                relevance_hash,
                relevance_created_at,
            ),
        )

        if canonical_event_id is not None:
            canonical_version = 1
            canonical_hash = hashlib.sha256(
                f"canonical:{canonical_event_id}".encode()
            ).hexdigest()
            resolution_hash = hashlib.sha256(
                f"resolution:{event_key}:{event_version}".encode()
            ).hexdigest()
            existing = conn.execute(
                """
                SELECT 1
                FROM event_evidence_canonical_group
                WHERE canonical_event_id=? AND canonical_version=1
                """,
                (canonical_event_id,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO event_evidence_canonical_group(
                        canonical_event_id,canonical_version,
                        resolution_contract_version,representative_event_id,
                        representative_event_version,resolution_method,
                        resolution_confidence,canonical_fingerprint,
                        canonical_hash,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        canonical_event_id,
                        1,
                        "TEST_RESOLUTION",
                        event_key,
                        event_version,
                        "TEST_METHOD",
                        "HIGH",
                        hashlib.sha256(
                            canonical_event_id.encode()
                        ).hexdigest(),
                        canonical_hash,
                        BEFORE,
                    ),
                )
            conn.execute(
                """
                INSERT INTO event_evidence_resolution(
                    resolution_id,resolution_contract_version,event_id,
                    event_version,canonical_event_id,canonical_version,
                    resolution_type,resolution_basis_json,resolution_hash,
                    created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    f"RES-{suffix}-V{event_version}",
                    "TEST_RESOLUTION",
                    event_key,
                    event_version,
                    canonical_event_id,
                    1,
                    "CANONICAL",
                    "{}",
                    resolution_hash,
                    BEFORE,
                ),
            )

        conn.execute(
            """
            INSERT INTO event_evidence_quality_assessment(
                assessment_id,quality_contract_version,assessment_scope,
                assessment_as_of,event_id,event_version,event_hash,
                source_bundle_hash,entity_id,entity_hash,relevance_id,
                relevance_hash,relation_type,rights_policy_bundle_hash,
                canonical_event_id,canonical_version,canonical_hash,
                resolution_hash,rights_state,integrity_state,temporal_state,
                relevance_state,resolution_state,revision_state,
                corroboration_state,source_count,distinct_source_origin_count,
                quality_state,blocking_reasons_json,insufficient_reasons_json,
                limitations_json,quality_json,quality_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                assessment_id,
                "TEST_QUALITY",
                "REFERENCE",
                assessment_as_of,
                event_key,
                event_version,
                event_hash,
                source_bundle_hash,
                ENTITY_ID,
                ENTITY_HASH,
                relevance_id,
                relevance_hash,
                "DIRECT_COMPANY",
                "7" * 64,
                canonical_event_id,
                canonical_version,
                canonical_hash,
                resolution_hash,
                "ALLOWED",
                "MATCH",
                "ELIGIBLE",
                "CONFIRMED",
                "DISTINCT" if canonical_event_id is None else "CANONICAL",
                event_state,
                "SINGLE_SOURCE",
                1,
                1,
                quality_state,
                "[]",
                "[]",
                "[]",
                _canonical_json(quality_payload),
                quality_hash,
                quality_created_at,
            ),
        )


def test_asof_reader_returns_cutoff_observed_reference_read_only(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path)
    _insert_reference(db, suffix="BASE")

    before = db.stat()
    result = EventEvidenceAsOfReader(db).stock_reference_as_of(
        "005930",
        "KOSPI",
        CUTOFF,
    )
    after = db.stat()

    assert result["contract_version"] == EVENT_REFERENCE_AS_OF_CONTRACT_VERSION
    assert result["status"] == "AVAILABLE"
    assert result["projection_id"].startswith("EVASOF-")
    assert len(result["projection_hash"]) == 64
    assert result["temporal_projection"] == {
        "mode": EVENT_REFERENCE_AS_OF_MODE,
        "decision_cutoff": CUTOFF,
        "storage_observation_cutoff_enforced": True,
        "historical_source_completeness_proven": False,
        "historical_evaluation_approved": False,
    }
    assert result["event_evidence"]["status"] == "REFERENCE_AVAILABLE"
    assert result["event_evidence"]["reference_count"] == 1
    assert result["event_evidence"]["projected_reference_count"] == 1
    assert result["event_evidence"]["items"][0]["quality_state"] == "USABLE"
    assert result["value_validation"] == {
        "status": "NOT_PROJECTED_AS_OF",
        "product_scope": "RESEARCH_ONLY",
    }
    assert result["prediction"]["status"] == "NOT_VALIDATED"
    assert result["governance"]["network_access"] is False
    assert result["governance"]["database_write"] is False
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_cutoff_filter_happens_before_reference_limit(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _insert_reference(
        db,
        suffix="OLD",
        assessment_as_of="2026-09-29T09:00:00+00:00",
    )
    for index in range(3):
        future = f"2026-10-0{index + 1}T09:00:00+00:00"
        _insert_reference(
            db,
            suffix=f"FUTURE{index}",
            available_at=future,
            event_created_at=future,
            relevance_as_of=future,
            relevance_created_at=future,
            assessment_as_of=future,
            quality_created_at=future,
            source_available_at=future,
            source_created_at=future,
            policy_created_at=future,
        )

    result = EventEvidenceAsOfReader(db).stock_reference_as_of(
        "005930",
        "KOSPI",
        CUTOFF,
        limit=3,
    )

    assert result["event_evidence"]["projected_reference_count"] == 1
    assert result["event_evidence"]["items"][0]["assessment_as_of"] == (
        "2026-09-29T09:00:00+00:00"
    )
    assert result["event_evidence"]["diagnostics"][
        "excluded_after_cutoff_count"
    ] >= 3


def test_late_backfill_does_not_rewrite_past_projection_identity(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path)
    _insert_reference(db, suffix="BASE")
    reader = EventEvidenceAsOfReader(db)

    before = reader.stock_reference_as_of("005930", "KOSPI", CUTOFF)

    _insert_reference(
        db,
        suffix="BACKFILL",
        available_at="2026-09-29T08:00:00+00:00",
        event_created_at=AFTER,
        relevance_as_of="2026-09-29T08:30:00+00:00",
        relevance_created_at=AFTER,
        assessment_as_of="2026-09-29T09:00:00+00:00",
        quality_created_at=AFTER,
        source_available_at="2026-09-29T08:00:00+00:00",
        source_created_at=AFTER,
        policy_created_at=AFTER,
    )

    after = reader.stock_reference_as_of("005930", "KOSPI", CUTOFF)

    assert after["projection_id"] == before["projection_id"]
    assert after["projection_hash"] == before["projection_hash"]
    assert after["event_evidence"]["items"] == before["event_evidence"]["items"]
    assert after["event_evidence"]["diagnostics"][
        "excluded_late_ingest_count"
    ] > 0


def test_revision_selection_is_cutoff_safe_for_correction(tmp_path: Path) -> None:
    db = _db(tmp_path)
    event_id = "EVENT-REV"
    _insert_reference(
        db,
        suffix="REV1",
        event_id=event_id,
        event_version=1,
        event_state="ORIGINAL",
        assessment_as_of="2026-09-29T09:00:00+00:00",
    )
    _insert_reference(
        db,
        suffix="REV2",
        event_id=event_id,
        event_version=2,
        event_state="CORRECTED",
        available_at=AFTER,
        event_created_at=AFTER,
        relevance_as_of=AFTER,
        relevance_created_at=AFTER,
        assessment_as_of=AFTER,
        quality_created_at=AFTER,
        source_available_at=AFTER,
        source_created_at=AFTER,
        policy_created_at=AFTER,
    )

    reader = EventEvidenceAsOfReader(db)
    past = reader.stock_reference_as_of("005930", "KOSPI", CUTOFF)
    future = reader.stock_reference_as_of(
        "005930",
        "KOSPI",
        "2026-10-02T11:00:00+00:00",
    )

    assert past["event_evidence"]["items"][0]["revision_state"] == "ORIGINAL"
    assert future["event_evidence"]["items"][0]["revision_state"] == "CORRECTED"


def test_withdrawal_before_cutoff_removes_event_but_future_withdrawal_does_not(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path)
    event_id = "EVENT-WD"
    _insert_reference(
        db,
        suffix="WD1",
        event_id=event_id,
        event_version=1,
        event_state="ORIGINAL",
    )
    _insert_reference(
        db,
        suffix="WD2",
        event_id=event_id,
        event_version=2,
        event_state="WITHDRAWN",
        available_at=AFTER,
        event_created_at=AFTER,
        relevance_as_of=AFTER,
        relevance_created_at=AFTER,
        assessment_as_of=AFTER,
        quality_created_at=AFTER,
        source_available_at=AFTER,
        source_created_at=AFTER,
        policy_created_at=AFTER,
    )

    reader = EventEvidenceAsOfReader(db)
    before_withdrawal = reader.stock_reference_as_of(
        "005930",
        "KOSPI",
        CUTOFF,
    )
    after_withdrawal = reader.stock_reference_as_of(
        "005930",
        "KOSPI",
        "2026-10-02T11:00:00+00:00",
    )

    assert before_withdrawal["event_evidence"]["reference_count"] == 1
    assert after_withdrawal["event_evidence"]["reference_count"] == 0
    assert after_withdrawal["event_evidence"]["diagnostics"][
        "excluded_inactive_revision_count"
    ] == 1


def test_entity_observed_after_cutoff_is_not_backfilled_into_past(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path)
    _ensure_entity(
        db,
        identity_as_of=AFTER,
        created_at=AFTER,
    )

    result = EventEvidenceAsOfReader(db).stock_reference_as_of(
        "005930",
        "KOSPI",
        CUTOFF,
    )

    assert result["status"] == "PARTIAL"
    assert result["event_evidence"]["status"] == (
        "NO_OBSERVED_ENTITY_BY_CUTOFF"
    )
    assert result["event_evidence"]["items"] == []


def test_source_time_and_storage_time_are_both_enforced(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _insert_reference(
        db,
        suffix="SRCFUTURE",
        source_available_at=AFTER,
        source_created_at=AFTER,
        policy_created_at=AFTER,
    )

    result = EventEvidenceAsOfReader(db).stock_reference_as_of(
        "005930",
        "KOSPI",
        CUTOFF,
    )

    assert result["event_evidence"]["reference_count"] == 0
    diagnostics = result["event_evidence"]["diagnostics"]
    assert (
        diagnostics["excluded_after_cutoff_count"] > 0
        or diagnostics["excluded_late_ingest_count"] > 0
    )


def test_synthetic_is_excluded_and_limited_quality_is_preserved(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path)
    _insert_reference(
        db,
        suffix="SYN",
        source_kind="TEST_SYNTHETIC",
    )
    _insert_reference(
        db,
        suffix="LIMITED",
        quality_state="LIMITED",
        assessment_as_of="2026-09-30T10:00:00+00:00",
    )

    result = EventEvidenceAsOfReader(db).stock_reference_as_of(
        "005930",
        "KOSPI",
        CUTOFF,
    )

    assert result["status"] == "PARTIAL"
    assert result["event_evidence"]["status"] == "REFERENCE_LIMITED"
    assert result["event_evidence"]["reference_count"] == 1
    assert result["event_evidence"]["items"][0]["quality_state"] == "LIMITED"
    assert result["event_evidence"]["diagnostics"][
        "excluded_synthetic_count"
    ] == 1


def test_integrity_mismatch_fails_closed(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _insert_reference(db, suffix="BROKEN")

    with sqlite3.connect(db) as conn:
        conn.execute("DROP TRIGGER trg_event_quality_immutable_update")
        conn.execute(
            """
            UPDATE event_evidence_quality_assessment
            SET quality_json='{"corrupt":true}'
            WHERE assessment_id='QA-BROKEN-V1'
            """
        )

    result = EventEvidenceAsOfReader(db).stock_reference_as_of(
        "005930",
        "KOSPI",
        CUTOFF,
    )

    assert result["event_evidence"]["status"] == "EVIDENCE_BLOCKED"
    assert result["event_evidence"]["reference_count"] == 0
    assert result["event_evidence"]["diagnostics"][
        "excluded_integrity_count"
    ] == 1


def test_cutoff_safe_canonical_dedup_keeps_one_reference(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _insert_reference(
        db,
        suffix="CAN1",
        canonical_event_id="CANONICAL-SAME",
        assessment_as_of="2026-09-30T09:00:00+00:00",
    )
    _insert_reference(
        db,
        suffix="CAN2",
        canonical_event_id="CANONICAL-SAME",
        assessment_as_of="2026-09-30T10:00:00+00:00",
    )

    result = EventEvidenceAsOfReader(db).stock_reference_as_of(
        "005930",
        "KOSPI",
        CUTOFF,
    )

    assert result["event_evidence"]["reference_count"] == 1
    assert result["event_evidence"]["projected_reference_count"] == 1
    assert result["event_evidence"]["diagnostics"][
        "excluded_duplicate_count"
    ] == 1


def test_naive_cutoff_and_missing_store_fail_closed(tmp_path: Path) -> None:
    db = _db(tmp_path)
    reader = EventEvidenceAsOfReader(db)

    with pytest.raises(Exception, match="timezone"):
        reader.stock_reference_as_of(
            "005930",
            "KOSPI",
            "2026-09-30T11:00:00",
        )

    missing = tmp_path / "missing" / "simulation.db"
    with pytest.raises(Exception, match="Simulation DB not found"):
        EventEvidenceAsOfReader(missing).stock_reference_as_of(
            "005930",
            "KOSPI",
            CUTOFF,
        )
    assert not missing.exists()
