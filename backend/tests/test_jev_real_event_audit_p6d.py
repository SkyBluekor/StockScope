"""P6-D real-data audit: empty vs missing vs migrated vs blocked; no writes."""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.jev import real_event_audit_p6d as p6d
from tools.data.migrate_event_evidence_vnp6s1 import migrate_event_evidence_store


CAPTURE_ID = "capture-p6d-existing"
CUTOFF = "2026-10-28T01:00:00+00:00"


def _pairs():
    capture = {"id": CAPTURE_ID, "created_at": CUTOFF}
    samples = [
        {"sample_index": 0, "snapshot_hash": "a" * 64, "market": "KOSPI",
         "ticker": "068270", "action": "ENTRY_CANDIDATE"},
        {"sample_index": 1, "snapshot_hash": "b" * 64, "market": "KOSPI",
         "ticker": "011200", "action": "ENTRY_CANDIDATE"},
        {"sample_index": 2, "snapshot_hash": "c" * 64, "market": "KOSPI",
         "ticker": "373220", "action": "REFERENCE_ONLY"},
    ]
    return [(capture, sample) for sample in samples]


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(p6d, "load_frozen_candidates", lambda *a, **k: _pairs())
    import app.jev.independent_event_reference_p6 as reference
    monkeypatch.setattr(reference, "load_frozen_candidates", lambda *a, **k: _pairs())
    monkeypatch.delenv("STOCKSCOPE_JEV_P6_ASSERTIONS_FILE", raising=False)


def test_missing_database_is_not_reported_as_empty(frozen, tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError, match="P6D_SIMULATION_DB_NOT_FOUND"):
        p6d.audit_existing_capture(missing, capture_id=CAPTURE_ID)
    assert not missing.exists()


def test_missing_schema_reports_unknown_counts_and_preserves_bytes(frozen, tmp_path):
    db = tmp_path / "existing.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE preserved (v INTEGER)")
        conn.execute("INSERT INTO preserved VALUES (99)")
    before = db.read_bytes()
    report = p6d.audit_existing_capture(db, capture_id=CAPTURE_ID)
    assert report["entry_count"] == 2
    assert report["store"]["status"] == "SCHEMA_MISSING"
    assert report["store"]["stored_counts_not_asof"]["source_refs"] is None
    assert report["cause_counts"] == {"SCHEMA_MISSING": 2}
    assert all(row["reference_count"] is None for row in report["rows"])
    assert report["ready_for_live_jev"] is False
    assert report["real_market_model_calls"] == report["db_writes"] == 0
    assert db.read_bytes() == before


def test_partial_event_schema_never_claims_empty_references(frozen, tmp_path):
    db = tmp_path / "partial.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE event_evidence_source_ref (source_kind TEXT)")
    report = p6d.audit_existing_capture(db, capture_id=CAPTURE_ID)
    assert report["store"]["status"] == "SCHEMA_INCOMPLETE"
    assert report["store"]["missing_tables"]
    assert report["cause_counts"]["SCHEMA_INCOMPLETE"] == 2
    assert report["store"]["stored_counts_not_asof"]["source_refs"] is None


def test_migrated_but_empty_store_is_distinct_from_missing_schema(frozen, tmp_path):
    db = tmp_path / "schema-present.db"
    sqlite3.connect(db).close()
    migrate_event_evidence_store(db)
    before = db.read_bytes()
    report = p6d.audit_existing_capture(db, capture_id=CAPTURE_ID)
    assert report["store"]["status"] == "READY"
    assert report["store"]["stored_counts_not_asof"]["source_refs"] == 0
    assert report["store"]["stored_counts_not_asof"]["event_revisions"] == 0
    assert report["entry_count"] == 2
    assert report["canonical_capture_id"] == CAPTURE_ID
    assert all(row["reference_status"] == "NO_INDEPENDENT_EVIDENCE" for row in report["rows"])
    assert all(row["assertion_status"] == "NO_INDEPENDENT_EVIDENCE" for row in report["rows"])
    assert all(row["v5_route"] == "SKIPPED_NO_EVIDENCE" for row in report["rows"])
    assert report["cause_counts"] == {"ENTITY_NOT_LINKED": 2}
    assert report["real_market_model_calls"] == 0
    assert report["mock_model_calls"] == 0
    assert db.read_bytes() == before


def test_authorized_p6_sources_not_inferred_from_display_rights():
    rights = p6d._local_source_rights(
        ["OPENDART_DISCLOSURE", "NAVER_NEWS", "UNKNOWN_VENDOR"],
        naver_provider_kind="developer_center",
    )
    assert rights["OPENDART_DISCLOSURE"]["known_policy"] is True
    assert rights["OPENDART_DISCLOSURE"]["ai_transform"] is False
    assert rights["NAVER_NEWS"]["ai_transform"] is False
    assert rights["NAVER_NEWS"]["derived_retention"] is False
    assert rights["UNKNOWN_VENDOR"]["known_policy"] is False


def test_cli_requires_explicit_existing_db_and_prints_machine_readable_error(frozen, tmp_path, capsys):
    from tools.data.jev_p6d_real_audit import main
    exit_code = main([
        "--simulation-db", str(tmp_path / "missing.db"),
        "--capture-id", CAPTURE_ID,
    ])
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert data["status"] == "AUDIT_UNAVAILABLE"
    assert data["read_only"] is True
    assert not (tmp_path / "missing.db").exists()
