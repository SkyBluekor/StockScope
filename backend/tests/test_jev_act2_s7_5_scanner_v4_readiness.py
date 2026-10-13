"""S7.5 real-shaped capture -> V4 Noul local readiness integration.

Fixtures are SYNTHETIC; the CLI itself also accepts unmodified real SQLite
captures. This test never reads the user's Runtime or calls a real provider.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import sqlite3

import pytest

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_v4_readiness_s7_5 import diagnose_candidate, diagnose_capture
from app.jev.typesafe_canary_v4 import _digest, _source_from_spec
from app.jev.typesafe_canary_v4_fixtures import FIXTURE_SPECS
from app.jev.typesafe_provider import FakeTypeSafeJevProvider
from app.jev.typesafe_questions_v4 import STRATEGY_RELATION_CONFLICT
from app.jev.typesafe_service import review_once
from app.prospective.models import digest_json
from tools.data.jev_s7_shadow import build_parser, display, execute


def _pair(*, local_status="RESIDUAL_SEMANTIC_REVIEW", horizon="SHORT", action="ENTRY_CANDIDATE"):
    spec = next(
        s for s in FIXTURE_SPECS
        if s["expected_local_status"] == local_status
    )
    source = deepcopy(_source_from_spec(spec))
    # Canary fixture uses SYNTHETIC as Q2 readiness: this synthetic integrated
    # row explicitly models the existing Scanner's verified engine PASS facts.
    source["readiness"]["q2_status"] = "COMPLETE"
    source["source_snapshot_hash"] = _digest({
        k: v for k, v in source.items() if k != "source_snapshot_hash"
    })
    strategy = source["strategy"]
    name = "SYNTHETIC_ONLY"
    snapshot = {
        "action": action,
        "code": "000001", "name": name, "market": "KOSPI",
        "strategy": strategy["strategy_key"],
        "strategy_version_id": strategy["strategy_version_id"],
        "strategy_definition_hash": strategy["strategy_definition_hash"],
        "decision_status": "READY", "candidate_state": "READY",
        "data_date": "2026-10-08",
        "priority": {"rank": 1, "tier": "READY"},
        "conditions": {
            "passed": len(source["conditions"]["items"]),
            "total": len(source["conditions"]["items"]),
            "missing": 0,
        },
        "risk": {"status": "READY", "warning": False},
        "entry_risk_guide": {"price_rule": {"kind": "RANGE"}, "action": {"status": "READY"}},
        "semantic_policy_provenance": {
            "status": "VERIFIED_PINNED_EXECUTION",
            "policy_source": "ACTIVE",
            "policy_id": "synthetic-policy",
            "policy_hash": "synthetic-policy-hash",
        },
        "semantic_source_v2": source,
        "semantic_condition_evidence": {
            "source": "SCANNER_ENGINE_CONDITION_EVIDENCE_V1",
            "strategy_key": strategy["strategy_key"],
            "passed": len(source["conditions"]["items"]),
            "total": len(source["conditions"]["items"]),
            "missing": 0,
            "items": [
                {"status": "PASS", "condition_id": f"engine-{i:02d}",
                 "source_condition": item["source_condition"]}
                for i, item in enumerate(source["conditions"]["items"], start=1)
            ],
        },
    }
    capture = {
        "id": "synthetic-v4-capture", "status": "COMPLETE",
        "actual_data_date": "2026-10-08",
        "completed_at": "2026-10-12T09:14:00+09:00",
        "scanner_version": "synthetic-only", "horizon_intent": horizon,
        "horizon_policy_version": "synthetic-only",
        "request_json": json.dumps({
            "selection_policy_id": "synthetic-policy",
            "selection_policy_hash": "synthetic-policy-hash",
        }),
    }
    sample = {
        "capture_run_id": capture["id"], "sample_index": 0,
        "signal_date": "2026-10-08", "snapshot": snapshot,
        "snapshot_hash": digest_json(snapshot),
        "market": "KOSPI", "ticker": "000001", "name": name,
        "strategy": strategy["strategy_key"],
        "decision_status": "READY", "candidate_state": "READY",
        "action": action, "rank": 1,
    }
    return capture, sample


def _rehashed(sample):
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    return sample


def _db(tmp_path, capture, samples):
    path = tmp_path / "synthetic_only.sqlite3"
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
        conn.execute(
            "INSERT INTO prospective_capture_run VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (capture["id"], "COMPLETE", None, "synthetic-key",
             capture["scanner_version"], "synthetic-baseline", "synthetic-input",
             capture["actual_data_date"], capture["horizon_intent"],
             capture["horizon_policy_version"], capture["completed_at"],
             capture["request_json"]),
        )
        for sample in samples:
            conn.execute(
                "INSERT INTO prospective_recommendation_sample VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sample["capture_run_id"], sample["sample_index"],
                 json.dumps(sample["snapshot"], ensure_ascii=False),
                 sample["snapshot_hash"], sample["signal_date"],
                 sample["market"], sample["ticker"], sample["name"],
                 sample["strategy"], sample["action"], sample["rank"],
                 sample["decision_status"], sample["candidate_state"]),
            )
    return path


def test_v4_projectable_uses_original_snapshot_and_only_one_noul():
    capture, sample = _pair()
    before = deepcopy((capture, sample))
    report = diagnose_candidate(capture, sample)
    assert (capture, sample) == before
    assert report["integrity_category"] == "LOCAL_VALIDATED", report
    assert report["s7_3_packet_lineage_status"] == "COMPLETE"
    assert report["status"] == "LOCAL_V4_PROJECTABLE", report
    assert report["v4_question_id"] == STRATEGY_RELATION_CONFLICT
    assert report["v4_state_hash"] and report["v4_state_bytes"] > 0
    assert report["v4_source_lineage_status"] == "UNVERIFIED"
    assert report["real_provider_eligible"] is False
    assert report["actual_provider_calls"] == report["db_writes"] == 0
    assert "state" not in report
    assert source_secret_free(report)


def source_secret_free(report):
    return "the supplied support meaning" not in json.dumps(report)


def test_v4_skipped_local_not_forwarded():
    capture, sample = _pair(local_status="LOCAL_MATCH")
    report = diagnose_candidate(capture, sample)
    assert report["status"] == "SKIPPED_LOCAL", report
    assert report["v4_local_status"] == "LOCAL_MATCH"
    assert report["v4_state_hash"] is None
    assert report["actual_provider_calls"] == 0


def test_v4_legacy_horizon_cannot_be_inferred():
    capture, sample = _pair(horizon="LEGACY_UNSPECIFIED")
    report = diagnose_candidate(capture, sample)
    assert report["status"] == "BLOCKED_HORIZON", report
    assert "LEGACY_HORIZON_UNDEFINED" in report["reason_codes"]
    assert report["v4_state_hash"] is None


def test_invalid_rank_retains_original_checker_failure():
    capture, sample = _pair()
    sample["rank"] = None
    report = diagnose_candidate(capture, sample)
    assert report["status"] == "BLOCKED_INTEGRITY", report
    assert "RANK_MISSING" in report["integrity_reason_codes"]
    assert report["v4_local_status"] is None


def test_v4_semantic_mismatch_fails_closed():
    capture, sample = _pair()
    source = sample["snapshot"]["semantic_source_v2"]
    source["readiness"]["local_semantic_status"] = "LOCAL_MATCH"
    source["readiness"]["residual_review_eligible"] = False
    source["source_snapshot_hash"] = _digest({
        k: v for k, v in source.items() if k != "source_snapshot_hash"
    })
    _rehashed(sample)
    report = diagnose_candidate(capture, sample)
    assert report["integrity_category"] == "LOCAL_VALIDATED", report
    assert report["status"] == "BLOCKED_SEMANTIC_SOURCE", report
    assert "SEMANTIC_LOCAL_STATUS_MISMATCH" in report["reason_codes"]


def test_reference_only_stays_reference_only():
    capture, sample = _pair(action="REFERENCE_ONLY")
    report = diagnose_candidate(capture, sample)
    assert report["status"] == "REFERENCE_ONLY"
    assert report["v4_state_hash"] is None
    assert report["real_provider_eligible"] is False


def test_cli_readonly_real_schema_json_and_scope(tmp_path, capsys):
    capture, item = _pair()
    valid = deepcopy(item)
    invalid = deepcopy(item)
    invalid["sample_index"] = 1
    invalid["rank"] = None
    ref = deepcopy(item)
    ref["sample_index"] = 2
    ref["action"] = "REFERENCE_ONLY"
    ref["snapshot"]["action"] = "REFERENCE_ONLY"
    _rehashed(ref)
    db = _db(tmp_path, capture, [valid, invalid, ref])
    previous = db.read_bytes()
    args = build_parser().parse_args([
        "v4-readiness", "--capture-id", capture["id"],
        "--simulation-db", str(db),
    ])
    result = execute(args, research_db=tmp_path / "never-written.db")
    assert result["total_records"] == 3
    assert result["entry_candidates"] == 2
    assert result["local_v4_projectable"] == 1, result
    assert result["blocked_integrity"] == 1
    assert result["reference_only"] == 1
    assert result["actual_provider_calls"] == result["db_writes"] == 0
    assert result["s7_3_packet_is_v4_wire"] is False
    assert db.read_bytes() == previous
    assert not (tmp_path / "never-written.db").exists()
    display(result)
    visible = capsys.readouterr().out
    assert "V4 질문: strategy_relation_conflict" in visible
    assert "실제 TypeSafe 전송: 보류" in visible
    display(result, as_json=True)
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["records"][1]["status"] == "BLOCKED_INTEGRITY"
    assert db.read_bytes() == previous

    only = build_parser().parse_args([
        "v4-readiness", "--capture-id", capture["id"],
        "--simulation-db", str(db), "--sample-index", "1",
    ])
    assert execute(only)["blocked_integrity"] == 1


def test_v4_readiness_never_writes_preflight_or_missing_database(tmp_path):
    args = build_parser().parse_args([
        "v4-readiness", "--capture-id", "nothing", "--save-preflight"
    ])
    with pytest.raises(DecisionReviewContractError, match="S7_4_DIAGNOSTIC_READ_ONLY"):
        execute(args, research_db=tmp_path / "research.db")
    with pytest.raises(DecisionReviewContractError, match="S7_SOURCE_DB_NOT_FOUND"):
        diagnose_capture(tmp_path / "missing.db", capture_id="nothing")


@pytest.mark.parametrize(("prob", "expected"), [
    (0.10, "PASS_THROUGH"), (0.95, "REVIEW_REQUIRED"),
])
def test_existing_v4_fake_noul_end_to_end_without_market_provider(prob, expected):
    capture, sample = _pair()
    readiness = diagnose_candidate(capture, sample)
    assert readiness["status"] == "LOCAL_V4_PROJECTABLE"
    v4_sample = dict(sample, horizon_intent=capture["horizon_intent"])
    protocol = {
        "question_contract_version": "JEV_TYPESAFE_QUESTIONS_V4",
        "disposition_policy_version": "JEV_TYPESAFE_DISPOSITION_POLICY_V4",
        "model_requested": "FAKE-S7.5",
        "expected_model_returned": "FAKE-S7.5",
        "threshold_strategy": 0.5,
    }
    provider = FakeTypeSafeJevProvider(
        probabilities={STRATEGY_RELATION_CONFLICT: prob},
        returned_model="FAKE-S7.5",
    )
    outcome = asyncio.run(review_once(v4_sample, protocol, provider))
    assert outcome.disposition == expected
    assert set(outcome.request["questions"]) == {STRATEGY_RELATION_CONFLICT}
    assert outcome.projection.state_hash == readiness["v4_state_hash"]
    # Explicit fake invocation does NOT change the real-data provider hold.
    assert readiness["actual_provider_calls"] == 0
    assert readiness["real_provider_eligible"] is False
