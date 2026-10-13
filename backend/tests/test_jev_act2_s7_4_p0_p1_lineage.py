"""S7.4 P0/P1 source- and snapshot-safe lineage diagnostics."""
from __future__ import annotations

import json
from copy import deepcopy
import sqlite3

import pytest

import app.jev.scanner_shadow_s7_3 as s73
from app.jev.decision_reviewer_offline import DecisionReviewContractError
import app.jev.scanner_lineage_s7_4 as lineage
import app.jev.scanner_v4_readiness_s7_5 as v45
from app.jev.scanner_lineage_s7_4 import (
    FIELDS, _leaves, diagnose_capture, diagnose_prepared, source_audit,
)
from app.prospective.models import digest_json
from tools.data.jev_s7_shadow import build_parser, display, execute


def _real_shaped():
    condition_items = [
        {"condition_id": "semantic-01", "source_condition": "RSI_14",
         "observed_meaning": "Momentum condition verified."},
        {"condition_id": "semantic-02", "source_condition": "TREND_STRUCTURE",
         "observed_meaning": "Trend condition verified."},
    ]
    snapshot = {
        "action": "ENTRY_CANDIDATE", "code": "003490", "name": "대한항공",
        "market": "KOSPI", "strategy": "trend_following",
        "decision_status": "READY", "candidate_state": "READY",
        "data_date": "2026-10-08", "priority": {"rank": 1},
        "conditions": {"passed": 2, "total": 2, "missing": 0},
        "risk": {"status": "READY", "warning": False},
        "entry_risk_guide": {"price_rule": {"kind": "RANGE"}},
        "strategy_version_id": None, "strategy_definition_hash": None,
        "semantic_policy_provenance": {
            "status": "VERIFIED_PINNED_EXECUTION",
            "policy_source": "LEGACY_CURRENT_10_FALLBACK",
            "policy_id": "legacy-policy", "policy_hash": "legacy-policy-hash",
        },
        "semantic_source_v2": {
            "strategy": {
                "strategy_version_id": "engine-v1",
                "strategy_definition_hash": "engine-definition-hash",
            },
            "readiness": {"q2_status": "COMPLETE"},
            "conditions": {"items": condition_items},
        },
        "semantic_condition_evidence": {
            "source": s73.ENGINE_CONDITION_SOURCE,
            "strategy_key": "trend_following", "passed": 2,
            "total": 2, "missing": 0,
            "items": [
                {"status": "PASS", "source_condition": it["source_condition"],
                 "condition_id": f"engine-audit-{n}"}
                for n, it in enumerate(condition_items)
            ],
        },
        "semantic_strategy_identity": {
            "source": s73.ENGINE_VERIFIED_SOURCE,
            "strategy_key": "trend_following",
            "strategy_version_id": "engine-v1",
            "strategy_definition_hash": "engine-definition-hash",
            "selection_policy_id": "legacy-policy",
            "selection_policy_hash": "legacy-policy-hash",
        },
    }
    capture = {
        "id": "capt-local-01", "status": "COMPLETE",
        "actual_data_date": "2026-10-08",
        "completed_at": "2026-10-12T09:14:00+09:00",
        "scanner_version": "0.21.3.9",
        "horizon_intent": "LEGACY_UNSPECIFIED",
        "horizon_policy_version": None,
        "request_json": json.dumps({
            "selection_policy_id": "legacy-policy",
            "selection_policy_hash": "legacy-policy-hash",
        }),
    }
    sample = {
        "capture_run_id": capture["id"], "sample_index": 0,
        "signal_date": "2026-10-08", "snapshot": snapshot,
        "snapshot_hash": digest_json(snapshot), "ticker": "003490",
        "name": "대한항공", "strategy": "trend_following",
        "action": "ENTRY_CANDIDATE", "rank": 1, "market": "KOSPI",
    }
    return capture, sample


@pytest.fixture
def real_prepared(monkeypatch):
    # The original S7.1 checker is separately covered. Keep the *real*
    # packet builder and its independent engine/semantic-source bijection.
    monkeypatch.setattr(
        s73, "assess_frozen_candidate",
        lambda c, s: {"category": "LEGACY_LIMITED", "codes": ["LEGACY_DERIVED_IDENTITY"]},
    )
    capture, sample = _real_shaped()
    frozen = deepcopy(sample["snapshot"])
    prepared = s73.prepare_shadow_candidate(capture, sample)
    assert frozen == sample["snapshot"]
    return prepared


def test_p0_inventory_is_non_authorizing_without_external_access(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "not-to-be-read")
    report = source_audit()
    assert report["status"] == "SOURCE_AUDIT_PROVIDER_HOLD"
    assert len(report["products"]) == 4
    assert all(p["actual_row_provenance"] == "UNVERIFIED" for p in report["products"])
    assert all(p["derived_ai_transmission"] == "UNVERIFIED" for p in report["products"])
    assert report["verified_allowed_real_market_fields"] == 0
    assert report["actual_provider_calls"] == report["db_writes"] == 0
    assert "JEV_API_KEY" not in json.dumps(report)


def test_p1_packet_covers_every_leaf_and_keeps_unknown_sources(real_prepared):
    original = deepcopy(real_prepared)
    report = diagnose_prepared(real_prepared)
    assert report["status"] == "LINEAGE_DIAGNOSTIC_PROVIDER_HOLD"
    assert report["integrity_status"] == "LOCAL_PACKET_READY"
    assert report["category"] == "LEGACY_LIMITED"
    assert report["lineage_analysis_status"] == "COMPLETE"
    assert report["unclassified_fields"] == 0
    assert report["field_count"] == len(list(_leaves(real_prepared["packet"])))
    assert set(f["path"] for f in report["field_diagnostics"]) == {
        path for path, _ in _leaves(real_prepared["packet"])
    }
    assert len(FIELDS) >= 35
    assert report["actual_provider_calls"] == 0
    assert report["real_provider_eligible"] is False
    assert real_prepared == original
    # Actual engine IDs and semantic IDs differ in the genuine producer.
    statements = [f for f in report["field_diagnostics"]
                  if f["path"].endswith(".statement")]
    assert len(statements) == 3
    assert statements[-1]["expected_parents"][0] == "SCANNER_RISK_PLAN"
    assert statements[0]["expected_parents"][0] == "SCANNER_ENGINE_PASS"
    assert all(f["actual_source"] == "UNVERIFIED" for f in statements)
    assert statements[0]["local_source_ref"] == (
        "snapshot.semantic_source_v2.conditions.items[0]"
    )
    assert "scanner_shadow_s7_3.py" in statements[0]["producer_ref"]
    assert all("LINEAGE_PARENT_UNVERIFIED" in f["reason_codes"] for f in statements)
    assert "Momentum condition verified." not in json.dumps(report)


def test_p1_rank_requires_candidate_cohort_provenance(real_prepared):
    report = diagnose_prepared(real_prepared)
    rank = next(f for f in report["field_diagnostics"]
                if f["path"] == "baseline.rank")
    assert "SCANNER_COMPARISON_COHORT" in rank["expected_parents"]
    assert "SOURCE_ORIGIN_UNVERIFIED" in rank["reason_codes"]
    assert rank["rights_status"] == "UNVERIFIED"


def test_p1_unclassified_nested_value_stays_blocked(real_prepared):
    candidate = deepcopy(real_prepared)
    candidate["packet"]["baseline"]["extra"] = {"leaky": ["secret example"]}
    new_hash = digest_json({k: v for k, v in candidate["packet"].items()
                            if k != "input_hash"})
    candidate["packet"]["input_hash"] = new_hash
    candidate["packet_hash"] = new_hash
    report = diagnose_prepared(candidate)
    assert report["unclassified_fields"] == 1
    assert "UNKNOWN_OUTBOUND_FIELD" in report["reason_codes"]
    assert "secret example" not in json.dumps(report)
    assert report["real_provider_eligible"] is False


def test_p1_rejects_tampered_hash_without_emitting_untrusted_fields(real_prepared):
    candidate = deepcopy(real_prepared)
    candidate["packet"]["evidence"][0]["statement"] = "FORGED SECRET"
    report = diagnose_prepared(candidate)
    assert report["field_count"] == 0
    assert "PACKET_HASH_MISMATCH" in report["reason_codes"]
    assert "FORGED SECRET" not in json.dumps(report)


def test_p1_empty_and_reference_are_local_only():
    report = diagnose_prepared({
        "identity": {"capture_id": "ref", "sample_index": 3},
        "category": "REFERENCE_ONLY", "status": "REFERENCE_ONLY",
        "packet": None, "temporal_status": "TIME_UNVERIFIED",
    })
    assert report["field_count"] == 0
    assert report["lineage_analysis_status"] == "NOT_APPLICABLE"
    assert "LOCAL_INTEGRITY_NOT_VERIFIED" not in report["reason_codes"]
    assert report["actual_provider_calls"] == 0
    simple = {"version": s73.PACKET_VERSION,
              "question_hash": s73.QUESTION_HASH, "weird_empty": {}}
    simple["input_hash"] = digest_json(simple)
    result = diagnose_prepared({
        "identity": {}, "category": "LEGACY_LIMITED",
        "status": "LOCAL_PACKET_READY", "packet": simple,
        "packet_hash": simple["input_hash"],
    })
    assert "UNKNOWN_OUTBOUND_FIELD" in result["reason_codes"]
    assert result["unclassified_fields"] == 1


def _capture_db(tmp_path):
    capture, sample = _real_shaped()
    path = tmp_path / "sim.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE prospective_capture_run (
                id TEXT PRIMARY KEY,status TEXT,canonical_capture_id TEXT,
                source_execution_key TEXT,scanner_version TEXT,
                scanner_baseline TEXT,input_fingerprint TEXT,actual_data_date TEXT,
                horizon_intent TEXT,horizon_policy_version TEXT,completed_at TEXT,
                request_json TEXT
            );
            CREATE TABLE prospective_recommendation_sample (
                capture_run_id TEXT,sample_index INTEGER,snapshot_json TEXT,
                snapshot_hash TEXT,signal_date TEXT,market TEXT,ticker TEXT,
                name TEXT,strategy TEXT,action TEXT,rank INTEGER,
                decision_status TEXT,candidate_state TEXT
            );
        """)
        conn.execute("INSERT INTO prospective_capture_run VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
            capture["id"], capture["status"], None, "source-id",
            capture["scanner_version"], "frozen", "fingerprint",
            capture["actual_data_date"], capture["horizon_intent"],
            capture["horizon_policy_version"], capture["completed_at"],
            capture["request_json"],
        ))
        conn.execute("INSERT INTO prospective_recommendation_sample VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            sample["capture_run_id"], 0,
            json.dumps(sample["snapshot"], ensure_ascii=False),
            sample["snapshot_hash"], sample["signal_date"], "KOSPI",
            "003490", "대한항공", sample["strategy"], sample["action"],
            1, "READY", "READY",
        ))
    return path


def test_p1_cli_readonly_fixture_and_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        s73, "assess_frozen_candidate",
        lambda c, s: {"category": "LEGACY_LIMITED", "codes": ["LEGACY_DERIVED_IDENTITY"]},
    )
    db = _capture_db(tmp_path)
    before = db.read_bytes()
    research = tmp_path / "research.db"
    opts = build_parser().parse_args([
        "lineage", "--capture-id", "capt-local-01",
        "--simulation-db", str(db),
    ])
    result = execute(opts, research_db=research)
    assert result["total_records"] == result["local_packets_ready"] == 1
    assert result["unclassified_fields"] == 0
    assert result["actual_provider_calls"] == 0
    assert not research.exists()
    assert db.read_bytes() == before
    display(result)
    stdout = capsys.readouterr().out
    assert "예상 의존" in stdout and "외부 호출은 0건" in stdout
    assert "Momentum condition verified." not in stdout
    display(result, as_json=True)
    assert json.loads(capsys.readouterr().out)["total_records"] == 1
    audit_opts = build_parser().parse_args(["source-audit"])
    display(execute(audit_opts, research_db=research))
    assert "공개 약관상 제한" in capsys.readouterr().out
    assert db.read_bytes() == before
    assert not research.exists()


def test_p1_disallow_preflight_journal_and_missing_capture(tmp_path):
    options = build_parser().parse_args([
        "lineage", "--capture-id", "missing", "--save-preflight",
    ])
    with pytest.raises(DecisionReviewContractError, match="S7_4_DIAGNOSTIC_READ_ONLY"):
        execute(options)
    source = build_parser().parse_args(["source-audit", "--sample-index", "0"])
    with pytest.raises(DecisionReviewContractError, match="S7_4_SOURCE_AUDIT_ARGUMENT_INVALID"):
        execute(source)
    with pytest.raises(DecisionReviewContractError, match="S7_SOURCE_DB_NOT_FOUND"):
        diagnose_capture(tmp_path / "missing.db", capture_id="missing")


# P1.1: an old real-shaped Capture may have six INVALID entries and no
# inspection-ready local packets. This is a *known missing evidence* condition,
# not "all fields classified".
OLD_CAPTURE_CODES = [
    "BASELINE_RANK_MISMATCH",
    "ENGINE_EVIDENCE_INCOMPLETE",
    "POLICY_PROVENANCE_UNVERIFIED",
    "RANK_MISSING",
    "STRATEGY_IDENTITY_MISSING",
]


def test_p11_preserves_five_original_failure_codes_and_korean_display(capsys):
    prepared = {
        "identity": {"name": "대한항공", "ticker": "003490", "sample_index": 1},
        "category": "INVALID", "status": "LOCAL_HOLD",
        "reason_codes": OLD_CAPTURE_CODES.copy(),
        "packet": None, "temporal_status": "RETROSPECTIVE_CAPTURE",
    }
    frozen = deepcopy(prepared)
    result = diagnose_prepared(prepared)
    assert prepared == frozen
    assert result["lineage_analysis_status"] == "NOT_RUN"
    assert result["integrity_reason_codes"] == OLD_CAPTURE_CODES
    assert set(OLD_CAPTURE_CODES).issubset(set(result["reason_codes"]))
    assert result["field_count"] == result["unclassified_fields"] == 0
    assert result["real_provider_eligible"] is False
    report = {
        "status": "LINEAGE_DIAGNOSTIC_PROVIDER_HOLD",
        "total_records": 1, "entry_candidates": 1, "local_packets_ready": 0,
        "invalid_count": 1, "reference_count": 0, "lineage_examined_count": 0,
        "lineage_not_run_count": 1, "lineage_partial_count": 0,
        "lineage_analysis_status": "NOT_RUN", "unclassified_fields": 0,
        "records": [result],
    }
    display(report)
    output = capsys.readouterr().out
    assert "계보 검사 미수행" in output
    assert "미분류 필드: 검사 미수행" in output
    for code in OLD_CAPTURE_CODES:
        assert f"[{code}]" in output
    assert "원본 정합성" in output
    display(report, as_json=True)
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["records"][0]["integrity_reason_codes"] == OLD_CAPTURE_CODES


def _mixed_15(monkeypatch, *, first_ready: bool):
    capture, sample = _real_shaped()
    rows = []
    for index in range(15):
        entry = deepcopy(sample)
        entry["sample_index"] = index
        entry["ticker"] = f"{index + 1:06d}"
        entry["name"] = f"fixture-{index}"
        if index >= 6:
            entry["action"] = "REFERENCE_ONLY"
            entry["snapshot"]["action"] = "REFERENCE_ONLY"
            entry["snapshot_hash"] = digest_json(entry["snapshot"])
        rows.append((capture, entry))

    def fake_check(_capture, entry):
        if entry["action"] == "REFERENCE_ONLY":
            return {"category": "REFERENCE_ONLY", "codes": ["NOT_ENTRY_CANDIDATE"]}
        if first_ready and entry["sample_index"] == 0:
            return {"category": "LEGACY_LIMITED", "codes": ["LEGACY_DERIVED_IDENTITY"]}
        return {"category": "INVALID", "codes": OLD_CAPTURE_CODES.copy()}

    monkeypatch.setattr(s73, "assess_frozen_candidate", fake_check)
    monkeypatch.setattr(lineage, "load_frozen_candidates", lambda *a, **kw: rows)
    return capture["id"]


@pytest.mark.parametrize(
    ("first_ready", "expected_status", "examined"),
    [(False, "NOT_RUN", 0), (True, "PARTIAL", 1)],
)
def test_p11_mixed_15_categorizes_reference_vs_failure(
    monkeypatch, capsys, tmp_path, first_ready, expected_status, examined,
):
    capture_id = _mixed_15(monkeypatch, first_ready=first_ready)
    result = diagnose_capture(tmp_path / "no-database-created.db", capture_id=capture_id)
    assert result["total_records"] == 15
    assert result["entry_candidates"] == 6
    assert result["invalid_count"] == 6 - examined
    assert result["reference_count"] == 9
    assert result["lineage_not_run_count"] == 6 - examined
    assert result["lineage_examined_count"] == examined
    assert result["local_packets_ready"] == examined
    assert result["lineage_analysis_status"] == expected_status
    assert result["unclassified_fields"] == 0
    assert all(
        rec["lineage_analysis_status"] == "NOT_APPLICABLE"
        for rec in result["records"][6:]
    )
    assert all(
        rec["integrity_reason_codes"] == OLD_CAPTURE_CODES
        for rec in result["records"][examined:6]
    )
    assert result["actual_provider_calls"] == 0
    assert not (tmp_path / "no-database-created.db").exists()
    display(result)
    output = capsys.readouterr().out
    assert "정합성 제외" in output
    assert "계보 검사 미수행" in output
    assert "외부 호출은 0건" in output
    if examined == 0:
        assert "미분류 필드: 검사 미수행" in output
        assert "분류를 검사한 패킷의 미분류 필드" not in output
    else:
        assert "분류를 검사한 패킷의 미분류 필드: 0건" in output
    display(result, as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert data["lineage_analysis_status"] == expected_status


def test_p11_tampered_hash_never_reports_complete(real_prepared):
    candidate = deepcopy(real_prepared)
    candidate["packet"]["evidence"][0]["statement"] = "NOT TRUSTED"
    result = diagnose_prepared(candidate)
    assert result["lineage_analysis_status"] == "NOT_RUN"
    assert "PACKET_HASH_MISMATCH" in result["reason_codes"]
    assert result["field_diagnostics"] == []
    assert "NOT TRUSTED" not in json.dumps(result)


def test_p11_unbounded_nesting_fails_closed_as_partial(real_prepared):
    candidate = deepcopy(real_prepared)
    child = "private raw evidence"
    for _ in range(18):
        child = {"x": child}
    candidate["packet"]["deep"] = child
    candidate["packet"]["input_hash"] = digest_json({
        key: val for key, val in candidate["packet"].items() if key != "input_hash"
    })
    candidate["packet_hash"] = candidate["packet"]["input_hash"]
    report = diagnose_prepared(candidate)
    assert report["lineage_analysis_status"] == "PARTIAL"
    assert "S7_4_LINEAGE_DEPTH_EXCEEDED" in report["reason_codes"]
    assert report["field_count"] == 0
    assert "private raw evidence" not in json.dumps(report)


def test_p11_preparation_zero_packets_is_explicit(capsys):
    display({
        "status": "LOCAL_PREPARATION_READY_PROVIDER_HOLD",
        "total_records": 15, "entry_candidates": 6,
        "local_packets_ready": 0, "local_validated": 0,
        "legacy_limited": 0, "invalid": 6, "references": 9,
        "records": [],
    })
    output = capsys.readouterr().out
    assert "로컬 JEV 패킷 0건" in output
    assert "준비된 입력이 없어" in output


def test_s75_existing_legacy_capture_is_not_promoted_to_v4(monkeypatch):
    capture, sample = _real_shaped()
    # The legacy source was independently known to be S7.3 inspectable only.
    monkeypatch.setattr(
        s73, "assess_frozen_candidate",
        lambda _c, _s: {"category": "LEGACY_LIMITED", "codes": ["STRATEGY_IDENTITY_MISMATCH"]},
    )
    monkeypatch.setattr(
        v45, "assess_frozen_candidate",
        lambda _c, _s: {"category": "LEGACY_LIMITED", "codes": ["STRATEGY_IDENTITY_MISMATCH"]},
    )
    before = deepcopy((capture, sample))
    report = v45.diagnose_candidate(capture, sample)
    assert (capture, sample) == before
    assert report["category"] == "LEGACY_LIMITED"
    assert report["lineage_analysis_status"] == "COMPLETE"
    assert report["local_v4_status"] == "BLOCKED_HORIZON"
    assert "V4_HORIZON_UNSUPPORTED" in report["reason_codes"]
    assert report["provider_status"] == "PROVIDER_HOLD"
    assert report["real_provider_eligible"] is False
    assert report["actual_provider_calls"] == report["db_writes"] == 0
    assert "Momentum condition verified." not in json.dumps(report)


def test_s75_invalid_candidate_preserves_all_observed_codes(monkeypatch):
    capture, sample = _real_shaped()
    monkeypatch.setattr(
        s73, "assess_frozen_candidate",
        lambda _c, _s: {"category": "INVALID", "codes": OLD_CAPTURE_CODES.copy()},
    )
    monkeypatch.setattr(
        v45, "assess_frozen_candidate",
        lambda _c, _s: {"category": "INVALID", "codes": OLD_CAPTURE_CODES.copy()},
    )
    result = v45.diagnose_candidate(capture, sample)
    assert result["local_v4_status"] == "BLOCKED_INTEGRITY"
    assert set(OLD_CAPTURE_CODES).issubset(result["reason_codes"])
    assert result["integrity_reason_codes"] == OLD_CAPTURE_CODES
    assert result["lineage_analysis_status"] == "NOT_RUN"
    assert result["v4_state_hash"] is None
    assert result["actual_provider_calls"] == 0


def test_s75_v4_route_and_projector_reuse_existing_contract(monkeypatch, real_prepared):
    from app.jev.typesafe_canary_v4 import _sample_from_spec
    from app.jev.typesafe_canary_v4_fixtures import FIXTURE_SPECS
    from app.jev.typesafe_state_v4 import route_typesafe_state_v4

    residual_spec = next(
        item for item in FIXTURE_SPECS
        if item["expected_local_status"] == "RESIDUAL_SEMANTIC_REVIEW"
    )
    v4_sample = _sample_from_spec(residual_spec)
    assert route_typesafe_state_v4(v4_sample).provider_eligible
    capture, _sample = _real_shaped()
    capture["horizon_intent"] = "SHORT"
    v4_sample["horizon_intent"] = "SHORT"
    v4_sample["snapshot_hash"] = digest_json(v4_sample["snapshot"])
    monkeypatch.setattr(v45, "prepare_shadow_candidate", lambda _c, _s: deepcopy(real_prepared))
    monkeypatch.setattr(v45, "assess_frozen_candidate", lambda _c, _s: {
        "category": "LOCAL_VALIDATED", "codes": [],
    })
    monkeypatch.setattr(v45, "diagnose_prepared", lambda _p: {
        "lineage_analysis_status": "COMPLETE", "reason_codes": [],
    })
    original = deepcopy(v4_sample)
    report = v45.diagnose_candidate(capture, v4_sample)
    assert v4_sample == original
    assert report["local_v4_status"] == "LOCAL_V4_PROJECTABLE"
    assert report["v4_outbound_lineage_status"] == "NOT_AUDITED"
    assert report["v4_wire_contract_verified"] is False
    assert len(report["v4_state_hash"]) == 64
    assert report["v4_state_bytes"] > 0
    assert report["provider_status"] == "PROVIDER_HOLD"
    assert report["s73_lineage_field_count"] > 0
    assert report["s73_lineage_unclassified_fields"] == 0
    assert report["v4_outbound_lineage_status"] == "NOT_APPLICABLE"
    assert report["v4_wire_contract_verified"] is False
    assert report["actual_provider_calls"] == report["db_writes"] == 0
    assert "strategy_intent" not in json.dumps(report)


def test_s75_cli_read_only_json_and_display(monkeypatch, tmp_path, capsys):
    capture, sample = _real_shaped()
    monkeypatch.setattr(v45, "load_frozen_candidates", lambda *_a, **_kw: [(capture, sample)])
    monkeypatch.setattr(s73, "assess_frozen_candidate", lambda _c, _s: {
        "category": "INVALID", "codes": ["POLICY_PROVENANCE_UNVERIFIED"],
    })
    monkeypatch.setattr(v45, "assess_frozen_candidate", lambda _c, _s: {
        "category": "INVALID", "codes": ["POLICY_PROVENANCE_UNVERIFIED"],
    })
    missing = tmp_path / "not_created.sqlite3"
    args = build_parser().parse_args([
        "v4-readiness", "--capture-id", capture["id"], "--simulation-db", str(missing),
    ])
    result = execute(args)
    assert result["counts"]["BLOCKED_INTEGRITY"] == 1
    assert result["actual_provider_calls"] == result["db_writes"] == 0
    assert not missing.exists()
    display(result)
    msg = capsys.readouterr().out
    assert "정합성 차단 1건" in msg
    assert "POLICY_PROVENANCE_UNVERIFIED" in msg
    assert "DB 쓰기 0건" in msg
    display(result, as_json=True)
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["records"][0]["local_v4_status"] == "BLOCKED_INTEGRITY"


def test_s75_reference_only_is_not_reported_as_v4_semantic_skip(monkeypatch, tmp_path, capsys):
    capture, sample = _real_shaped()
    sample["action"] = "REFERENCE_ONLY"
    sample["snapshot"]["action"] = "REFERENCE_ONLY"
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    monkeypatch.setattr(v45, "load_frozen_candidates", lambda *_a, **_kw: [(capture, sample)])

    db = tmp_path / "not_created.sqlite3"
    report = v45.diagnose_capture(db, capture_id=capture["id"])
    assert report["entry_candidates"] == 0
    assert report["counts"]["REFERENCE_ONLY"] == 1
    assert report["counts"]["SKIPPED_LOCAL"] == 0
    assert report["counts"]["LOCAL_V4_PROJECTABLE"] == 0
    assert report["records"][0]["lineage_analysis_status"] == "NOT_APPLICABLE"
    assert report["actual_provider_calls"] == report["db_writes"] == 0
    assert not db.exists()
    display(report)
    output = capsys.readouterr().out
    assert "단순 참고 1건" in output
    assert "V4 로컬 의미 판단으로 생략 0건" in output


def test_s75_legacy_cli_shows_primary_blocker_not_false_identity_difference(monkeypatch, capsys):
    capture, sample = _real_shaped()
    monkeypatch.setattr(s73, "assess_frozen_candidate", lambda _c, _s: {
        "category": "LEGACY_LIMITED",
        "codes": ["LEGACY_DERIVED_IDENTITY", "STRATEGY_IDENTITY_MISMATCH"],
    })
    monkeypatch.setattr(v45, "assess_frozen_candidate", lambda _c, _s: {
        "category": "LEGACY_LIMITED",
        "codes": ["LEGACY_DERIVED_IDENTITY", "STRATEGY_IDENTITY_MISMATCH"],
    })
    report = {
        "status": "V4_READINESS_PROVIDER_HOLD",
        "total_records": 1, "entry_candidates": 1,
        "counts": {name: 1 if name == "BLOCKED_HORIZON" else 0 for name in (
            "LOCAL_V4_PROJECTABLE", "SKIPPED_LOCAL", "REFERENCE_ONLY",
            "BLOCKED_INTEGRITY", "BLOCKED_HORIZON", "BLOCKED_SEMANTIC_SOURCE",
        )},
        "records": [v45.diagnose_candidate(capture, sample)],
    }
    assert "STRATEGY_IDENTITY_MISMATCH" in report["records"][0]["reason_codes"]
    display(report)
    output = capsys.readouterr().out
    assert "당시 투자 기간이 단기·중기로 확정되지 않아" in output
    assert "원본 제한: 당시 전략 버전이 없고" in output
    assert "원본 전략 버전과 의미 분석용 전략 버전이 다릅니다" not in output
    assert "모든 원본 진단 코드는 --json 출력" in output
