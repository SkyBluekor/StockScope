"""P6-F end-to-end isolated EventEvidence chain; NEVER persist real DART."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from app.event_evidence.dart_ingest_p6f import (
    prepare_disclosure, prepare_disclosure_batch,
    persist_test_fixture_only, live_storage_decision,
)
from app.event_evidence.policy import (
    EventEvidenceSourcePolicy, opendart_event_evidence_policy,
)
from app.event_evidence.asof import EventEvidenceAsOfReader
from app.event_evidence.quality import EventEvidenceQualityService
from tools.data.migrate_event_evidence_vnp6s1 import migrate_event_evidence_store

RECEIPT_1 = "20261012900154"
RECEIPT_2 = "20261012900140"


def _row(receipt=RECEIPT_1, **kw):
    row = {
        "receipt_no": receipt,
        "receipt_date": "20261012",
        "corp_code": "12345678",
        "stock_code": "086450",
        "corp_name": "가상검증법인",
        "report_name": "가상 임시주주총회 결정",
        "viewer_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
        "source_time_quality": "DATE_ONLY",
        "source_published_at": None,
    }
    row.update(kw)
    return row


def _response(rows, timestamp=None):
    return {
        "provider": "OpenDART", "corp_code": "12345678",
        "stock_code": "086450", "count": len(rows), "rows": rows,
        "fetched_at": timestamp or datetime.now(timezone.utc).isoformat(),
        "time_quality": "DATE_ONLY",
        "source_publication_time_verified": False,
        "event_evidence_storage": "NOT_PERSISTED_RIGHTS_UNVERIFIED",
        "external_ai_transfer": "BLOCKED", "db_writes": 0,
    }


def _policy():
    return EventEvidenceSourcePolicy(
        policy_id="P6F-ISOLATED-TEST-OPENDART-V1",
        source_kind="OPENDART_DISCLOSURE",
        policy_version="p6f-isolated-test-v1",
        display_allowed=True, normalization_allowed=True,
        raw_retention_allowed=False, derived_retention_allowed=True,
        ai_transform_allowed=False, historical_evaluation_allowed=False,
        prediction_input_allowed=False, attribution_required=True,
        policy_basis="TEST_ONLY:never-approved-for-real-OpenDART",
    )


def _db(tmp_path):
    path = tmp_path / "p6f-test-simulation.db"
    sqlite3.connect(path).close()
    migrate_event_evidence_store(path)
    return path


def _count(db, table):
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]


def test_real_production_storage_remains_unapproved():
    status = live_storage_decision()
    assert status["status"] == "NOT_APPROVED"
    assert status["storage_allowed"] is False
    assert status["ai_transmission_allowed"] is False
    assert status["actual_db_writes"] == status["actual_provider_calls"] == 0


def test_actual_dart_shape_two_fictional_records_to_full_isolated_chain(tmp_path):
    db = _db(tmp_path)
    observations = prepare_disclosure_batch(
        _response([_row(), _row(RECEIPT_2)]), market="KOSDAQ",
    )
    assert len(observations) == 2
    assert observations[0].first_seen_at.endswith("+00:00")
    output = [
        persist_test_fixture_only(db, item, test_policy=_policy())
        for item in observations
    ]
    assert [x["event_id"] for x in output] == [
        f"OPENDART-EVENT:{RECEIPT_1}", f"OPENDART-EVENT:{RECEIPT_2}",
    ]
    assert all(x["time_quality"] == "DATE_ONLY" for x in output)
    assert all(x["ai_transmission_allowed"] is False for x in output)
    assert output[0]["entity_id"] == output[1]["entity_id"]
    assert _count(db, "event_evidence_source_ref") == 2
    assert _count(db, "event_evidence_record") == 2
    assert _count(db, "event_evidence_entity") == 1
    assert _count(db, "event_evidence_entity_relevance") == 2
    assert _count(db, "event_evidence_quality_assessment") == 2
    assert all(x["quality_state"] != "BLOCKED" for x in output)
    reader = EventEvidenceAsOfReader(db)
    projection = reader.stock_reference_as_of(
        "086450", "KOSDAQ",
        (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(),
    )
    assert projection["event_evidence"]["status"] in {
        "REFERENCE_LIMITED", "REFERENCE_AVAILABLE",
    }
    assert len(projection["event_evidence"]["items"]) == 2


def test_repeated_capture_does_not_replace_first_seen_or_duplicate(tmp_path):
    db = _db(tmp_path)
    instant = datetime.now(timezone.utc) - timedelta(minutes=1)
    first = prepare_disclosure(
        _row(), ticker="086450", market="KOSDAQ",
        corp_code="12345678", first_seen_at=instant.isoformat(),
    )
    original = persist_test_fixture_only(db, first, test_policy=_policy())
    later = prepare_disclosure(
        _row(), ticker="086450", market="KOSDAQ",
        corp_code="12345678",
        first_seen_at=(instant + timedelta(minutes=10)).isoformat(),
    )
    repeated = persist_test_fixture_only(db, later, test_policy=_policy())
    assert repeated["source_hash"] == original["source_hash"]
    assert repeated["event_hash"] == original["event_hash"]
    assert repeated["first_seen_at"] == original["first_seen_at"]
    assert repeated["quality_assessment_id"] == original["quality_assessment_id"]
    assert _count(db, "event_evidence_source_ref") == 1
    assert _count(db, "event_evidence_record") == 1
    assert _count(db, "event_evidence_quality_assessment") == 1


def test_missing_rights_no_effect_on_database(tmp_path):
    db = _db(tmp_path)
    before = db.read_bytes()
    item = prepare_disclosure_batch(_response([_row()]), market="KOSDAQ")[0]
    with pytest.raises(ValueError, match="P6F_TEST_ISOLATION_REQUIRED"):
        persist_test_fixture_only(
            db, item, test_policy=opendart_event_evidence_policy(),
        )
    assert db.read_bytes() == before
    assert _count(db, "event_evidence_source_ref") == 0


@pytest.mark.parametrize("change,reason", [
    ({"corp_code": "87654321"}, "P6F_CORP_CODE_MISMATCH"),
    ({"stock_code": "005930"}, "P6F_TICKER_MISMATCH"),
    ({"receipt_no": "bogus"}, "P6F_RECEIPT_IDENTITY_INVALID"),
    ({"receipt_date": "20260230"}, "P6F_RECEIPT_DATE_INVALID"),
    ({"viewer_url": "https://evil.example/redirect"}, "P6F_ORIGINAL_URL_MISMATCH"),
    ({"source_published_at": "2026-10-12T00:00:00+00:00"}, "P6F_UNVERIFIED_SOURCE_PUBLICATION_TIME"),
    ({"source_time_quality": "EXACT"}, "P6F_TIME_QUALITY_MISMATCH"),
])
def test_rejects_unverified_identity_date_or_invented_publication(change, reason):
    with pytest.raises(ValueError, match=reason):
        prepare_disclosure(
            _row(**change), ticker="086450", market="KOSDAQ",
            corp_code="12345678",
            first_seen_at=datetime.now(timezone.utc).isoformat(),
        )


def test_duplicate_receipts_or_untrusted_response_not_stored(tmp_path):
    db = _db(tmp_path)
    with pytest.raises(ValueError, match="P6F_DUPLICATE_RECEIPT"):
        prepare_disclosure_batch(_response([_row(), _row()]), market="KOSDAQ")
    with pytest.raises(ValueError, match="P6F_SOURCE_RESPONSE_CONTRACT_INVALID"):
        prepare_disclosure_batch(
            {**_response([_row()]), "external_ai_transfer": "ALLOWED"},
            market="KOSDAQ",
        )
    assert _count(db, "event_evidence_source_ref") == 0


def test_content_conflict_rejected_without_overwriting_first_observation(tmp_path):
    db = _db(tmp_path)
    first = prepare_disclosure_batch(_response([_row()]), market="KOSDAQ")[0]
    persist_test_fixture_only(db, first, test_policy=_policy())
    changed = prepare_disclosure_batch(
        _response([_row(report_name="변경된 가상 표제")]), market="KOSDAQ",
    )[0]
    before = _count(db, "event_evidence_record")
    with pytest.raises(ValueError, match="P6F_EXISTING_CONTENT_CONFLICT"):
        persist_test_fixture_only(db, changed, test_policy=_policy())
    assert _count(db, "event_evidence_record") == before
    assert _count(db, "event_evidence_source_ref") == 1


def test_test_policy_cannot_be_used_with_nonisolated_filename(tmp_path):
    path = tmp_path / "production.db"
    sqlite3.connect(path).close()
    migrate_event_evidence_store(path)
    prepared = prepare_disclosure_batch(_response([_row()]), market="KOSDAQ")[0]
    with pytest.raises(ValueError, match="P6F_TEST_ISOLATION_REQUIRED"):
        persist_test_fixture_only(path, prepared, test_policy=_policy())
    assert _count(path, "event_evidence_source_ref") == 0
