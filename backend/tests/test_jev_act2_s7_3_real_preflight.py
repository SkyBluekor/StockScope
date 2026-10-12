"""S7.3 real market local preparation and provider no-call regressions."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import sqlite3

import pytest

from app.jev.decision_reviewer_offline import DecisionReviewContractError
import app.jev.scanner_shadow_s7_3 as s73
from app.prospective.models import digest_json
from tools.data.jev_s7_shadow import build_parser, display, execute


CAPTURE_ID = "real-capture-01"
DATA_DATE = "2026-10-08"
RECORDED_AT = "2026-10-12T09:14:00+09:00"


def _actual_shaped_sample(*, action="ENTRY_CANDIDATE"):
    source = [
        {
            "condition_id": "c1", "source_condition": "RSI_14",
            "observed_meaning": "Strategy momentum confirmation is present.",
        },
        {
            "condition_id": "c2", "source_condition": "TREND_STRUCTURE",
            "observed_meaning": "Trend structure is consistent with the setup.",
        },
    ]
    snap = {
        "action": action, "code": "003490", "name": "대한항공",
        "market": "KOSPI", "strategy": "trend_following",
        "decision_status": "READY", "candidate_state": "READY",
        "data_date": DATA_DATE, "priority": {"rank": 1},
        "conditions": {"passed": 2, "total": 2, "missing": 0},
        "risk": {"status": "READY", "warning": False},
        "entry_risk_guide": {"price_rule": {"kind": "RANGE"}},
        "strategy_version_id": None,
        "strategy_definition_hash": None,
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
            "conditions": {"items": source},
        },
        # Real repro audit IDs belong to the engine namespace, while
        # semantic_source_v2 issues its own condition-01 etc. They are NOT
        # required to be equal: the common identity is source_condition.
        "semantic_condition_evidence": {
            "source": s73.ENGINE_CONDITION_SOURCE,
            "strategy_key": "trend_following",
            "passed": len(source), "total": len(source), "missing": 0,
            "items": [
                {
                    "status": "PASS", "source_condition": it["source_condition"],
                    "condition_id": f"repro-engine-pass-{n+1}",
                } for n, it in enumerate(source)
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
        "id": CAPTURE_ID, "status": "COMPLETE",
        "actual_data_date": DATA_DATE, "completed_at": RECORDED_AT,
        "scanner_version": "0.21.3.9",
        "horizon_intent": "LEGACY_UNSPECIFIED", "horizon_policy_version": None,
        "request_json": json.dumps({
            "selection_policy_id": "legacy-policy",
            "selection_policy_hash": "legacy-policy-hash",
        }),
    }
    sample = {
        "capture_run_id": CAPTURE_ID, "sample_index": 0,
        "signal_date": DATA_DATE, "snapshot": snap, "snapshot_hash": digest_json(snap),
        "ticker": "003490", "name": "대한항공",
        "strategy": snap["strategy"], "action": action,
        "rank": 1, "market": "KOSPI", "decision_status": "READY",
        "candidate_state": "READY",
    }
    return capture, sample


def _validated_legacy(monkeypatch):
    # S7.1's independent legacy and strict-S3 contract were already exercised
    # in S7.1 suites. Here isolate the S7.3 packet structure and safety gates.
    monkeypatch.setattr(s73, "assess_frozen_candidate",
                        lambda c, s: {
                            "category": "LEGACY_LIMITED",
                            "codes": ["LEGACY_DERIVED_IDENTITY",
                                      "STRATEGY_IDENTITY_MISMATCH"],
                        })


def test_s7_3_legacy_real_packet_has_explicit_derived_provenance(monkeypatch):
    _validated_legacy(monkeypatch)
    capture, sample = _actual_shaped_sample()
    original = deepcopy(sample["snapshot"])
    prepared = s73.prepare_shadow_candidate(capture, sample)
    assert prepared["status"] == "LOCAL_PACKET_READY"
    assert prepared["category"] == "LEGACY_LIMITED"
    assert prepared["identity"]["ticker"] == "003490"
    assert prepared["temporal_status"] == "RETROSPECTIVE_CAPTURE"
    state = prepared["packet"]
    strategy = state["baseline"]["strategy_identity"]
    assert strategy["origin"] == "LEGACY_DERIVED"
    assert strategy["original_version"] is None
    assert strategy["original_definition_hash"] is None
    assert strategy["derived_version"] == "engine-v1"
    assert strategy["derived_evidence_source"] == s73.ENGINE_VERIFIED_SOURCE
    assert state["evidence"][0]["source_available_at"] is None
    assert state["evidence"][-1]["source"] == "SCANNER_RISK_DERIVED"
    assert "003490" not in json.dumps(state, ensure_ascii=False)
    assert "대한항공" not in json.dumps(state, ensure_ascii=False)
    assert state["input_hash"] == digest_json({
        k: v for k, v in state.items() if k != "input_hash"
    })
    assert sample["snapshot"] == original


def test_s7_3_real_engine_ids_differ_from_semantic_ids_but_sources_match(monkeypatch):
    """Real producer emits unrelated per-layer IDs; strong source bijection works."""
    _validated_legacy(monkeypatch)
    capture, sample = _actual_shaped_sample()
    original = deepcopy(sample["snapshot"])
    semantic = original["semantic_source_v2"]["conditions"]["items"]
    repro = original["semantic_condition_evidence"]["items"]
    assert all(a["condition_id"] != b["condition_id"]
               for a, b in zip(semantic, repro))
    prepared = s73.prepare_shadow_candidate(capture, sample)
    assert prepared["status"] == "LOCAL_PACKET_READY"
    assert prepared["category"] == "LEGACY_LIMITED"
    assert len(prepared["packet"]["evidence"]) == len(semantic) + 1
    assert prepared["packet"]["input_hash"] == digest_json({
        k: v for k, v in prepared["packet"].items() if k != "input_hash"
    })
    assert sample["snapshot"] == original
    hold = s73.preflight_shadow_candidate(prepared)
    assert hold["status"] == "PROVIDER_HOLD"
    assert hold["actual_provider_calls"] == 0


@pytest.mark.parametrize("mutation", (
    "duplicate_source", "duplicate_engine_id", "engine_not_passed",
    "unknown_source", "blank_id", "unverified_engine_source",
))
def test_s7_3_engine_proof_bijection_rejects_bad_source_or_fake_pass(
    monkeypatch, mutation,
):
    _validated_legacy(monkeypatch)
    capture, sample = _actual_shaped_sample()
    evidence = sample["snapshot"]["semantic_condition_evidence"]
    items = evidence["items"]
    if mutation == "duplicate_source":
        items[1]["source_condition"] = items[0]["source_condition"]
    elif mutation == "duplicate_engine_id":
        items[1]["condition_id"] = items[0]["condition_id"]
    elif mutation == "engine_not_passed":
        items[0]["status"] = "FAIL"
    elif mutation == "unknown_source":
        items[0]["source_condition"] = "UNKNOWN_UNSUPPORTED_CONDITION"
    elif mutation == "blank_id":
        items[0]["condition_id"] = ""
    elif mutation == "unverified_engine_source":
        evidence["source"] = "NOT_SCANNER_REPRO"
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    with pytest.raises(
        DecisionReviewContractError, match="S7_3_ENGINE_PASS_PROOF_MISMATCH"
    ):
        s73.prepare_shadow_candidate(capture, sample)


def test_s7_3_preflight_is_hold_with_complete_blocker_explanations(monkeypatch):
    _validated_legacy(monkeypatch)
    capture, sample = _actual_shaped_sample()
    prepared = s73.prepare_shadow_candidate(capture, sample)
    check = s73.preflight_shadow_candidate(prepared)
    assert check["status"] == "PROVIDER_HOLD"
    assert set([
        "SOURCE_RELEASE_TIME_UNVERIFIED",
        "SOURCE_RIGHTS_UNVERIFIED",
        "LEGACY_HORIZON_UNDEFINED",
        "REAL_MARKET_PROVIDER_NOT_AUTHORIZED",
        "PINNED_MODEL_AND_BILLING_NOT_VERIFIED",
        "EXPLICIT_EXECUTION_APPROVAL_MISSING",
    ]).issubset(set(check["blocking_reasons"]))
    assert check["temporal_status"] == "RETROSPECTIVE_CAPTURE"
    assert check["actual_provider_calls"] == 0
    assert check["eligible_for_real_market_provider"] is False
    assert all(check["blocking_explanations"].values())


def test_s7_3_forged_identity_or_engine_proof_never_accepted(monkeypatch):
    _validated_legacy(monkeypatch)
    capture, sample = _actual_shaped_sample()
    sample["snapshot"]["semantic_strategy_identity"]["source"] = "UNVERIFIED"
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    with pytest.raises(DecisionReviewContractError, match="S7_3_LEGACY_ORIGIN_MISMATCH"):
        s73.prepare_shadow_candidate(capture, sample)
    capture, sample = _actual_shaped_sample()
    sample["snapshot"]["semantic_condition_evidence"]["items"][0]["status"] = "FAIL"
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    with pytest.raises(DecisionReviewContractError, match="S7_3_ENGINE_PASS_PROOF_MISMATCH"):
        s73.prepare_shadow_candidate(capture, sample)
    capture, sample = _actual_shaped_sample()
    sample["snapshot"]["risk"]["warning"] = True  # changes source hash
    with pytest.raises(DecisionReviewContractError, match="S7_3_ORIGINAL_CAPTURE_INVALID"):
        s73.prepare_shadow_candidate(capture, sample)


def test_s7_3_strict_validator_failure_is_local_hold():
    capture, sample = _actual_shaped_sample()
    result = s73.prepare_shadow_candidate(capture, sample)
    assert result["status"] == "LOCAL_HOLD"
    assert result["real_provider_eligible"] is False
    gate = s73.preflight_shadow_candidate(result)
    assert gate["status"] == "PROVIDER_HOLD"
    assert "LOCAL_INTEGRITY_NOT_VERIFIED" in gate["blocking_reasons"]


def test_s7_3_reference_not_provider_eligible():
    capture, sample = _actual_shaped_sample(action="REFERENCE_ONLY")
    result = s73.prepare_shadow_candidate(capture, sample)
    assert result["category"] == "REFERENCE_ONLY"
    assert result["packet"] is None
    assert result["status"] == "REFERENCE_ONLY"


def test_s7_3_disabled_actual_runner_fails_before_api_key_or_transport(monkeypatch):
    _validated_legacy(monkeypatch)
    capture, sample = _actual_shaped_sample()
    prepared = s73.prepare_shadow_candidate(capture, sample)
    monkeypatch.setenv("JEV_API_KEY", "fake-key")
    monkeypatch.setenv("TYPESAFE_JEV_API_KEY", "fake-key")
    async def run():
        return await s73.S73DisabledActualProvider().submit(
            prepared, owner_approval="APPROVED", api_key="fake-key", model="jev-latest"
        )
    with pytest.raises(DecisionReviewContractError, match="S7_3_REAL_PROVIDER_HOLD"):
        asyncio.run(run())
    assert s73.REAL_MARKET_PROVIDER_ENABLED is False


def test_s7_3_real_response_validation_separates_synthetic_alias():
    raw = {
        "model": "jev-1.13.0",
        "answers": {"review_decision": {
            "type": "choice", "choice": "REVIEW_REQUIRED",
            "confidence": 0.9,
            "probabilities": {
                "REVIEW_REQUIRED": 0.9, "PASS_THROUGH": 0.02, "ABSTAIN": 0.08,
            },
        }},
        "usage": {"input_tokens": 12, "output_tokens": 0},
    }
    valid = s73.validate_shadow_choice_response(
        raw, requested_model="jev-1.13.0", pinned_returned_model="jev-1.13.0"
    )
    assert valid["choice"] == "REVIEW_REQUIRED"
    assert valid["model_reasoning_provided"] is False
    with pytest.raises(DecisionReviewContractError, match="S7_3_MODEL_REVISION_UNVERIFIED"):
        s73.validate_shadow_choice_response(
            raw, requested_model="jev-latest", pinned_returned_model="jev-1.13.0"
        )
    forged = deepcopy(raw)
    forged["answers"]["review_decision"]["probabilities"]["REVIEW_REQUIRED"] = 2.0
    with pytest.raises(DecisionReviewContractError, match="S7_3_RESPONSE_INVALID"):
        s73.validate_shadow_choice_response(
            forged, requested_model="jev-1.13.0", pinned_returned_model="jev-1.13.0"
        )


def _capture_db(tmp_path):
    capture, sample = _actual_shaped_sample()
    db = tmp_path / "sim.db"
    with sqlite3.connect(db) as conn:
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
            "INSERT INTO prospective_capture_run VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (capture["id"], "COMPLETE", None, "source-identity",
             capture["scanner_version"], "frozen", "fingerprint",
             DATA_DATE, "LEGACY_UNSPECIFIED", None, RECORDED_AT,
             capture["request_json"]),
        )
        conn.execute(
            "INSERT INTO prospective_recommendation_sample VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                CAPTURE_ID, 0, json.dumps(sample["snapshot"], ensure_ascii=False),
                sample["snapshot_hash"], DATA_DATE, "KOSPI", "003490",
                "대한항공", "trend_following", "ENTRY_CANDIDATE", 1,
                "READY", "READY",
            ),
        )
    return db


def test_s7_3_cli_prepare_preflight_and_immutable_journal(tmp_path, monkeypatch, capsys):
    _validated_legacy(monkeypatch)
    source = _capture_db(tmp_path)
    before = source.read_bytes()
    journal = tmp_path / "research" / "shadow.db"
    prep = build_parser().parse_args([
        "prepare", "--capture-id", CAPTURE_ID, "--simulation-db", str(source),
    ])
    one = execute(prep, research_db=journal)
    assert one["local_packets_ready"] == 1
    assert one["legacy_limited"] == 1
    assert one["real_provider_calls"] == 0
    assert not journal.exists()
    display(one)
    assert "로컬 JEV 입력 준비 1건" in capsys.readouterr().out
    preflight = build_parser().parse_args([
        "preflight", "--capture-id", CAPTURE_ID,
        "--simulation-db", str(source), "--save-preflight",
    ])
    first = execute(preflight, research_db=journal)
    second = execute(preflight, research_db=journal)
    assert first["research_write"] == {
        "inserted": 1, "reused": 0, "provider_calls": 0,
    }
    assert second["research_write"]["reused"] == 1
    assert first["records"][0]["status"] == "PROVIDER_HOLD"
    assert source.read_bytes() == before
    with sqlite3.connect(journal) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM jev_s7_3_preflight")
    with pytest.raises(DecisionReviewContractError, match="S7_3_SAMPLE_NOT_FOUND"):
        s73.prepare_capture(source, capture_id=CAPTURE_ID, sample_index=1)


def test_s7_3_preflight_tampered_local_packet_fails_closed(monkeypatch):
    _validated_legacy(monkeypatch)
    capture, sample = _actual_shaped_sample()
    prepared = s73.prepare_shadow_candidate(capture, sample)
    prepared["packet"]["evidence"][0]["source_available_at"] = RECORDED_AT
    verdict = s73.preflight_shadow_candidate(prepared)
    assert "LOCAL_INTEGRITY_NOT_VERIFIED" in verdict["blocking_reasons"]
    assert verdict["eligible_for_real_market_provider"] is False
