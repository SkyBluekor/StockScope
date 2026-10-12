"""S7.4 P0/P1 source- and snapshot-safe lineage diagnostics."""
from __future__ import annotations

import json
from copy import deepcopy
import sqlite3

import pytest

import app.jev.scanner_shadow_s7_3 as s73
from app.jev.decision_reviewer_offline import DecisionReviewContractError
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
    assert "LOCAL_INTEGRITY_NOT_VERIFIED" in report["reason_codes"]
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
