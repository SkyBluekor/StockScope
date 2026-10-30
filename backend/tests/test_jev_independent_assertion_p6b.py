"""P6-B synthetic assertions: binding, as-of, dedup, safety, endpoint."""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.jev import independent_assertion_p6b as p6b

CUTOFF = "2026-10-28T01:00:00+00:00"
SOURCE_HASH = "a" * 64
EVENT_HASH = "b" * 64
QUALITY_HASH = "c" * 64
CONTENT_HASH = "d" * 64
SNAPSHOT_HASH = "e" * 64
PROJECTION_HASH = "f" * 64


def _ref(status="EVIDENCE_UNCERTAIN"):
    return {
        "status": status, "capture_id": "authored-cap", "sample_index": 0,
        "snapshot_hash": SNAPSHOT_HASH, "ticker": "068270", "market": "KOSPI",
        "decision_cutoff": CUTOFF, "projection_hash": PROJECTION_HASH,
        "reference_count": 1, "reason_codes": [],
        "source_kinds": ["OPENDART_DISCLOSURE"],
        "ai_input_rights": "NOT_APPROVED", "read_only": True,
    }


def _project():
    return {
        "projection_hash": PROJECTION_HASH,
        "event_evidence": {"items": [{
            "quality_state": "USABLE", "revision_state": "ORIGINAL",
            "source_kinds": ["OPENDART_DISCLOSURE"],
        }]},
        "_internal_pins": [{
            "sample_identity": "canonical-event", "event_id": "event-1",
            "event_version": 1, "event_hash": EVENT_HASH,
            "quality_hash": QUALITY_HASH,
            "source_refs": [{"source_ref_id": "ref-1",
                             "source_ref_hash": SOURCE_HASH,
                             "content_hash": CONTENT_HASH}],
        }],
    }


def _v2():
    return {
        "source_snapshot_hash": "1" * 64,
        "strategy": {"strategy_key": "pullback"},
        "relations": {
            "relation_contract_hash": "2" * 64,
            "strategy_key": "pullback",
            "concepts": [{"concept_id": "support_integrity"}],
        },
    }


def _claim(relation="CONTRADICTS", **updates):
    body = {
        "contract_version": p6b.VERSION,
        "assertion_id": "review-1", "capture_id": "authored-cap",
        "sample_index": 0, "snapshot_hash": SNAPSHOT_HASH,
        "market": "KOSPI", "ticker": "068270",
        "event_id": "event-1", "event_version": 1,
        "event_hash": EVENT_HASH, "quality_hash": QUALITY_HASH,
        "source_ref_id": "ref-1", "source_ref_hash": SOURCE_HASH,
        "content_hash": CONTENT_HASH, "projection_hash": PROJECTION_HASH,
        "strategy_source_hash": "1" * 64, "strategy_key": "pullback",
        "claim_id": "support_integrity", "relation": relation,
        "fact_statement": "Author-written statement requiring independent review.",
        "review_note": "Authored, not inferred from a headline.",
        "approval_state": "APPROVED", "approved_by": "fixture-reviewer",
        "created_at": "2026-10-28T00:30:00+00:00",
        "approved_at": "2026-10-28T00:45:00+00:00",
    }
    body.update(updates)
    return {**body, "assertion_hash": p6b._digest(body)}


@pytest.fixture(autouse=True)
def _verified_authored_v2(monkeypatch):
    monkeypatch.setattr(p6b, "verify_semantic_source_v2", lambda _: (True, None))


def _run(records, **kwargs):
    return p6b.evaluate_local_assertions(
        reference=_ref(), projection=_project(), source_v2=_v2(),
        records=records, enforce_source_retention=False, **kwargs,
    )


@pytest.mark.parametrize("stance,status", [
    ("CONTRADICTS", "EVIDENCE_CONFLICT"),
    ("SUPPORTS", "EVIDENCE_COMPATIBLE"),
    ("UNRESOLVED", "EVIDENCE_UNCERTAIN"),
])
def test_explicit_pinned_and_author_reviewed_relations(stance, status):
    result = _run([_claim(stance)])
    assert result["status"] == status
    assert result["approved_assertion_count"] == 1
    assert result["reviewed_assertion_refs"][0]["event_id"] == "event-1"
    assert result["reviewed_assertion_refs"][0]["event_version"] == 1
    assert result["reviewed_assertion_refs"][0]["source_ref_hash"] == SOURCE_HASH
    assert result["model_review_executed"] is False
    assert result["external_model_call_allowed"] is False
    assert result["independent_conflict_proven"] is False


def test_no_assertions_keeps_reference_uncertain():
    result = _run([])
    assert result["status"] == "EVIDENCE_UNCERTAIN"
    assert result["independent_review_candidate"] is False
    assert result["approved_assertion_count"] == 0


@pytest.mark.parametrize("change", [
    {"ticker": "373220"}, {"snapshot_hash": "0" * 64},
    {"event_version": 2}, {"event_hash": "0" * 64},
    {"source_ref_id": "ref-other"}, {"source_ref_hash": "0" * 64},
    {"content_hash": "0" * 64}, {"quality_hash": "0" * 64},
    {"projection_hash": "0" * 64},
    {"claim_id": "claim_not_authored"}, {"strategy_source_hash": "0" * 64},
    {"approval_state": "PENDING"}, {"approved_by": ""},
    {"event_version": []}, {"claim_id": []}, {"relation": []},
])
def test_forged_or_unmatched_pins_fail_closed(change):
    result = _run([_claim(**change)])
    assert result["status"] == "EVIDENCE_NOT_USABLE"
    assert result["approved_assertion_count"] == 0


def test_invalid_hash_cannot_claim_approval():
    record = _claim()
    record["review_note"] = "mutated after approval"
    assert _run([record])["status"] == "EVIDENCE_NOT_USABLE"


def test_approval_after_cutoff_not_historically_available():
    result = _run([_claim(approved_at="2026-10-29T01:00:00+00:00")])
    assert result["status"] == "EVIDENCE_UNCERTAIN"
    assert result["retrospective_assertion_count"] == 1
    assert result["approved_assertion_count"] == 0


def test_conflicting_assertions_for_same_event_cannot_be_two_votes():
    result = _run([_claim("CONTRADICTS"), _claim("SUPPORTS", assertion_id="review-2")])
    assert result["status"] == "EVIDENCE_UNCERTAIN"
    assert result["approved_assertion_count"] == 1
    assert result["reviewed_event_count"] == 1


def test_repeated_same_event_does_not_inflate_count():
    result = _run([_claim(), _claim(assertion_id="review-2")])
    assert result["status"] == "EVIDENCE_CONFLICT"
    assert result["reviewed_event_count"] == 1


def test_real_source_requires_derived_retention_not_just_display():
    result = p6b.evaluate_local_assertions(
        reference=_ref(), projection=_project(), source_v2=_v2(),
        records=[_claim()], naver_provider_kind="developer_center",
    )
    assert result["status"] == "EVIDENCE_NOT_USABLE"
    assert "P6B_SOURCE_DERIVED_RETENTION_NOT_APPROVED" in result["reason_codes"]


def test_missing_original_v2_binding_is_not_an_approved_conflict(monkeypatch):
    monkeypatch.setattr(p6b, "verify_semantic_source_v2", lambda _: (False, "SOURCE_INVALID"))
    result = _run([_claim()])
    assert result["status"] == "EVIDENCE_UNCERTAIN"
    assert result["assertion_status"] == "NO_VERIFIED_STRATEGY_BINDING"


def test_missing_internal_pins_fails_closed():
    projection = _project()
    projection["_internal_pins"] = []
    result = p6b.evaluate_local_assertions(
        reference=_ref(), projection=projection, source_v2=_v2(),
        records=[_claim()], enforce_source_retention=False,
    )
    assert result["status"] == "EVIDENCE_NOT_USABLE"


def test_explicit_local_registry_file_is_opt_in(monkeypatch, tmp_path):
    monkeypatch.delenv("STOCKSCOPE_JEV_P6_ASSERTIONS_FILE", raising=False)
    assert p6b._registry() == ([], None)
    manifest = tmp_path / "local-authored.json"
    manifest.write_text(json.dumps({
        "version": p6b.MANIFEST_VERSION, "assertions": [_claim()],
    }), encoding="utf-8")
    monkeypatch.setenv("STOCKSCOPE_JEV_P6_ASSERTIONS_FILE", str(manifest))
    records, error = p6b._registry()
    assert error is None and len(records) == 1
    assert records[0]["assertion_hash"] == _claim()["assertion_hash"]


def test_readonly_api_with_missing_event_schema(monkeypatch, tmp_path):
    import app.api.jev as api
    import app.jev.independent_event_reference_p6 as reference_module
    db = tmp_path / "preserve.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE preserved (value INTEGER)")
        conn.execute("INSERT INTO preserved VALUES (42)")
    before = db.read_bytes()
    monkeypatch.setattr(api, "_db", lambda: db)
    monkeypatch.setattr(reference_module, "load_frozen_candidates", lambda *a, **k: [
        ({"id": "authored-cap", "created_at": CUTOFF},
         {"sample_index": 0, "snapshot_hash": SNAPSHOT_HASH,
          "market": "KOSPI", "ticker": "068270", "action": "ENTRY_CANDIDATE"}),
    ])
    result = api.jev_independent_event_assessment("authored-cap", 0)
    assert result["status"] == "EVIDENCE_NOT_USABLE"
    assert result["actual_provider_calls"] == result["db_writes"] == 0
    assert db.read_bytes() == before
