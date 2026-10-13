"""S8 rights/time evidence triage. Offline and zero provider calls."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

import app.jev.scanner_eligibility_s8 as s8
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from tools.data.jev_s7_shadow import build_parser, display, execute


def _record(*, reference=False, v4_status="BLOCKED_HORIZON"):
    return {
        "identity": {"name": "synthetic-only", "ticker": "000001"},
        "category": "REFERENCE_ONLY" if reference else "LEGACY_LIMITED",
        "local_v4_status": "REFERENCE_ONLY" if reference else v4_status,
        "v4_state_hash": "a" * 64 if v4_status == "LOCAL_V4_PROJECTABLE" else None,
        "reason_codes": ["LEGACY_HORIZON_UNDEFINED"] if not reference else [
            "NOT_ENTRY_CANDIDATE"
        ],
        "lineage_analysis_status": "NOT_APPLICABLE" if reference else "COMPLETE",
        "s73_lineage_field_count": 0 if reference else 42,
        "s73_lineage_unclassified_fields": 0,
        "v4_outbound_lineage_status": (
            "NOT_AUDITED" if not reference and v4_status == "LOCAL_V4_PROJECTABLE"
            else "NOT_APPLICABLE"
        ),
        "v4_wire_contract_verified": False,
    }


def _patch_candidate(monkeypatch, *, reference=False, v4_status="BLOCKED_HORIZON"):
    monkeypatch.setattr(
        s8, "diagnose_v4_candidate",
        lambda capture, sample: deepcopy(_record(reference=reference, v4_status=v4_status)),
    )


def test_s8_krx_public_rights_are_not_derived_or_account_grants():
    assert s8.RIGHTS_ACTIONS["KRX_OPEN_API_RAW_THIRD_PARTY"] == (
        "VERIFIED_PROHIBITED_PUBLIC_TERMS"
    )
    assert s8.RIGHTS_ACTIONS["KRX_OPEN_API_DERIVED_TYPESAFE_AI"] == "UNVERIFIED"
    assert s8.RIGHTS_ACTIONS["TYPESAFE_ACCOUNT_PROCESSING_CONDITIONS"] == "UNVERIFIED"
    assert s8.KRX_TERMS_URL.endswith("OPPINFO002.jsp")


@pytest.mark.parametrize("v4_status", [
    "LOCAL_V4_PROJECTABLE", "BLOCKED_HORIZON", "BLOCKED_SEMANTIC_SOURCE",
])
def test_s8_actual_capture_class_never_authorizes_provider(monkeypatch, v4_status):
    _patch_candidate(monkeypatch, v4_status=v4_status)
    sample = {"capture_run_id": "synthetic", "sample_index": 0}
    prior = deepcopy(sample)
    result = s8.diagnose_candidate({"id": "synthetic"}, sample)
    assert sample == prior
    assert result["v4_local_status"] == v4_status
    assert result["data_eligibility"] == "HOLD_UNVERIFIED"
    assert result["transmission_decision"] == "NO_GO"
    assert result["rights_status"] == "UNVERIFIED"
    assert result["source_revision_status"] == "UNVERIFIED"
    assert result["publication_time_status"] == "UNKNOWN"
    assert result["acquisition_time_status"] == "UNKNOWN"
    assert "RIGHTS_AUTHENTICITY_UNVERIFIED" in result["reason_codes"]
    assert "OUTBOUND_BODY_NOT_APPROVED" in result["reason_codes"]
    assert result["actual_provider_calls"] == result["db_writes"] == 0


def test_s8_reference_not_confused_with_v4_local_skip(monkeypatch):
    _patch_candidate(monkeypatch, reference=True)
    result = s8.diagnose_candidate({"id": "synthetic"}, {"sample_index": 1})
    assert result["data_eligibility"] == "NOT_APPLICABLE"
    assert result["transmission_decision"] == "NOT_APPLICABLE"
    assert result["source_origin_status"] == "NOT_APPLICABLE"
    assert result["reason_codes"] == ["NOT_ENTRY_CANDIDATE"]


def test_s8_unclassified_lineage_stays_blocked(monkeypatch):
    _patch_candidate(monkeypatch, v4_status="LOCAL_V4_PROJECTABLE")
    bad = _record(v4_status="LOCAL_V4_PROJECTABLE")
    bad["lineage_analysis_status"] = "PARTIAL"
    bad["s73_lineage_field_count"] = 12
    bad["s73_lineage_unclassified_fields"] = 2
    monkeypatch.setattr(s8, "diagnose_v4_candidate", lambda *_a: deepcopy(bad))
    result = s8.diagnose_candidate({}, {})
    assert result["unclassified_fields"] == 2
    assert "UNCLASSIFIED_OUTBOUND_FIELD" in result["reason_codes"]
    assert "LINEAGE_INCOMPLETE" in result["reason_codes"]
    assert result["transmission_decision"] == "NO_GO"


def _events():
    return {
        "source_published_at": "2026-10-12T01:00:00Z",
        "source_available_at": "2026-10-12T10:10:00+09:00",
        "request_started_at": "2026-10-12T01:12:00Z",
        "retrieved_at": "2026-10-12T10:13:00+09:00",
        "known_to_system_at": "2026-10-12T01:14:00+00:00",
        "scanner_input_frozen_at": "2026-10-12T01:15:00Z",
        "revision_binding_verified": True,
        "trusted_event_evidence_ref": "synthetic-proof-only",
    }


def test_s8_time_sequence_can_be_consistent_but_is_not_authenticated():
    value = s8.inspect_temporal_chain(_events())
    assert value["sequence"] == "CONSISTENT_ONLY"
    assert value["reason_codes"] == []
    assert value["authenticity_verified"] is False
    assert value["source_release_verified"] is False
    assert value["forward_asof_verified"] is False


@pytest.mark.parametrize("field,value,reason", [
    ("source_published_at", "2026-10-12T12:00:00Z", "SOURCE_TIME_INCONSISTENT"),
    ("request_started_at", "2026-10-12T14:00:00Z", "SOURCE_TIME_INCONSISTENT"),
    ("known_to_system_at", "2026-10-11T01:14:00Z", "SOURCE_TIME_INCONSISTENT"),
    ("source_available_at", "2026-10-12T10:10:00", "TIMEZONE_UNVERIFIED"),
    ("source_available_at", None, "SOURCE_TIME_EVENT_MISSING"),
])
def test_s8_time_bad_evidence_fails_closed(field, value, reason):
    events = _events()
    events[field] = value
    result = s8.inspect_temporal_chain(events)
    assert result["sequence"] == "INCOMPLETE_OR_INCONSISTENT"
    assert reason in result["reason_codes"]
    assert not result["forward_asof_verified"]


def test_s8_client_provided_flags_do_not_establish_trusted_time():
    events = _events()
    events.pop("trusted_event_evidence_ref")
    events.pop("revision_binding_verified")
    events["rights_status"] = "VERIFIED_ALLOWED"
    report = s8.inspect_temporal_chain(events)
    assert "REVISION_ASOF_UNPROVEN" in report["reason_codes"]
    assert "SOURCE_TIME_AUTHENTICITY_UNVERIFIED" in report["reason_codes"]
    assert report["authenticity_verified"] is False


def test_s8_strict_body_hash_is_version_sensitive_and_never_an_approval():
    from app.jev.typesafe_canary_v4 import _sample_from_spec
    from app.jev.typesafe_canary_v4_fixtures import FIXTURE_SPECS
    from app.jev.typesafe_state_v4 import project_typesafe_state_v4
    from app.jev.typesafe_questions_v4 import build_typesafe_questions_v4

    sample = _sample_from_spec(FIXTURE_SPECS[0])
    request = {
        "state": project_typesafe_state_v4(sample).state,
        "questions": build_typesafe_questions_v4(),
        "model": "FAKE",
    }
    original = deepcopy(request)
    h1 = s8.hash_local_outbound_candidate(request)
    changed_question = deepcopy(request)
    changed_question["questions"]["strategy_relation_conflict"]["instructions"] = "changed"
    changed_model = {**request, "model": "OTHER-FAKE"}
    with pytest.raises(ValueError, match="OUTBOUND_V4_QUESTION_CONTRACT_MISMATCH"):
        s8.hash_local_outbound_candidate(changed_question)
    assert h1 != s8.hash_local_outbound_candidate(changed_model)
    changed_state = deepcopy(request)
    changed_state["state"]["strategy_intent"]["text"] = "changed"
    assert h1 != s8.hash_local_outbound_candidate(changed_state)
    assert not s8.RIGHTS_ACTIONS["KRX_OPEN_API_DERIVED_TYPESAFE_AI"] == "VERIFIED_ALLOWED"
    assert request == original
    assert len(h1) == 64


@pytest.mark.parametrize("bad", [
    {"state": {}, "questions": {}, "model": "FAKE"},
    {"state": {}, "questions": {"q": {}}, "model": "FAKE", "extra": "secret"},
    {"state": {"q": float("nan")}, "questions": {"q": {}}, "model": "FAKE"},
    {"state": {"q": object()}, "questions": {"q": {}}, "model": "FAKE"},
    {"state": {}, "questions": {"q": {}}, "model": ""},
    {"state": {}, "questions": {"q": {}}, "model": "UNFROZEN"},
])
def test_s8_body_rejects_unsafe_or_changed_envelopes(bad):
    with pytest.raises(ValueError, match="OUTBOUND_BODY"):
        s8.hash_local_outbound_candidate(bad)


def test_s8_cli_scope_and_korean_output_read_only(monkeypatch, tmp_path, capsys):
    _patch_candidate(monkeypatch)
    capture = {"id": "synthetic"}
    entry = {"sample_index": 0}
    reference = {"sample_index": 1}
    monkeypatch.setattr(
        s8, "load_frozen_candidates",
        lambda *a, **kw: [(capture, entry), (capture, reference)],
    )
    # Select one entry: the real code never constructs an external provider.
    path = tmp_path / "no_db_created.sqlite3"
    args = build_parser().parse_args([
        "s8-readiness", "--capture-id", "synthetic", "--sample-index", "0",
        "--simulation-db", str(path),
    ])
    result = execute(args)
    assert result["total_records"] == 1
    assert result["entry_candidates"] == 1
    assert result["rights_unverified_count"] == 1
    assert result["source_time_unverified_count"] == 1
    assert result["no_go_count"] == 1
    assert result["data_eligibility"] == "HOLD_UNVERIFIED"
    assert result["actual_provider_calls"] == result["db_writes"] == 0
    assert path.exists() is False
    display(result)
    printed = capsys.readouterr().out
    assert "파생정보의 TypeSafe 처리 권한" in printed
    assert "실제 시장 데이터 전송 0건" in printed
    display(result, as_json=True)
    encoded = json.loads(capsys.readouterr().out)
    assert encoded["records"][0]["transmission_decision"] == "NO_GO"
    assert "raw_market_prices" not in json.dumps(encoded)


def test_s8_cli_no_missing_capture_or_writes():
    with pytest.raises(DecisionReviewContractError, match="S8_CAPTURE_ID_REQUIRED"):
        s8.diagnose_capture("unused.db", capture_id=None)
    with pytest.raises(DecisionReviewContractError, match="S8_SAMPLE_INDEX_INVALID"):
        s8.diagnose_capture("unused.db", capture_id="synthetic", sample_index=-1)


def test_s8_strict_json_rejects_duplicate_keys_and_nonfinite_literals():
    with pytest.raises(ValueError, match="OUTBOUND_BODY_DUPLICATE_KEY"):
        s8.hash_local_outbound_candidate(
            '{"state":{},"questions":{"q":{}},"model":"FAKE","state":{}}'
        )
    with pytest.raises(ValueError, match="OUTBOUND_BODY_NONFINITE"):
        s8.hash_local_outbound_candidate(
            '{"state":{"value":NaN},"questions":{"q":{}},"model":"FAKE"}'
        )

def test_s8_local_v4_semantic_skip_does_not_count_as_external_no_go(monkeypatch):
    _patch_candidate(monkeypatch, v4_status="SKIPPED_LOCAL")
    result = s8.diagnose_candidate({"id": "synthetic"}, {"sample_index": 0})
    assert result["transmission_decision"] == "NOT_REQUIRED"
    assert result["data_eligibility"] == "NOT_APPLICABLE"
    assert result["v4_outbound_lineage_status"] == "NOT_APPLICABLE"


def test_s8_projectable_candidate_explicitly_lacks_v4_wire_lineage(monkeypatch):
    _patch_candidate(monkeypatch, v4_status="LOCAL_V4_PROJECTABLE")
    result = s8.diagnose_candidate({"id": "synthetic"}, {"sample_index": 0})
    assert result["lineage_analysis_status"] == "COMPLETE"
    assert result["lineage_field_count"] == 42
    assert result["v4_outbound_lineage_status"] == "NOT_AUDITED"
    assert result["v4_wire_contract_verified"] is False
    assert "V4_OUTBOUND_LINEAGE_NOT_AUDITED" in result["reason_codes"]
    assert "V4_WIRE_CONTRACT_UNVERIFIED" in result["reason_codes"]
    assert result["transmission_decision"] == "NO_GO"
