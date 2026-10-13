"""ACT2-S7.2 — fresh Scanner→Prospective evidence, no model/API calls."""
from __future__ import annotations

from copy import deepcopy
import json
import sqlite3

import pytest

from app.backtest.candidate_priority import rank_candidates
from app.jev.scanner_shadow_s7 import S7ShadowJournal
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest, digest_json
from app.strategy.condition_semantics import condition_sources
from app.strategy.production_selection_policy import (
    SELECTION_POLICY_CONTRACT_VERSION, SelectionPolicyPin,
)
from app.strategy.semantic_identity_bridge import scanner_repro_candidate_key
import app.strategy.semantic_identity_bridge as bridge


AS_OF = "2026-10-08"
STRATEGY = "trend_following"


def _catalog(tmp_path, monkeypatch):
    db = tmp_path / "sim.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
        CREATE TABLE prospective_capture_run(
            id TEXT PRIMARY KEY, capture_version TEXT,
            source_job_id TEXT UNIQUE, status TEXT, request_json TEXT,
            market_scope TEXT, requested_as_of TEXT, candidate_limit INTEGER,
            horizon_intent TEXT, horizon_policy_version TEXT,
            created_at TEXT, started_at TEXT, updated_at TEXT,
            source_execution_key TEXT, canonical_capture_id TEXT,
            scanner_version TEXT, scanner_baseline TEXT, actual_data_date TEXT,
            input_fingerprint TEXT, actionable_candidate_count INTEGER,
            returned_candidate_count INTEGER, result_hash TEXT,
            source_snapshot_hash TEXT, completed_at TEXT,
            error_code TEXT, error_message TEXT
        );
        CREATE TABLE prospective_recommendation_sample(
            capture_run_id TEXT, sample_index INTEGER, market TEXT,
            ticker TEXT, name TEXT, rank INTEGER, strategy TEXT,
            decision_status TEXT, candidate_state TEXT, action TEXT,
            signal_date TEXT, snapshot_json TEXT, snapshot_hash TEXT,
            created_at TEXT,
            PRIMARY KEY(capture_run_id, sample_index)
        );
        """)
    # This fixture exercises real SQL writer paths, only bypasses unrelated
    # runtime schema-migration checks on its deliberately minimal test DB.
    monkeypatch.setattr(ProspectiveCatalog, "require_ready",
                        lambda self, conn=None: None)
    return ProspectiveCatalog(db)


def _pin():
    return SelectionPolicyPin(
        policy_id="active-test-1", policy_hash="active-test-proof-1",
        policy_contract_version=SELECTION_POLICY_CONTRACT_VERSION,
        policy_source="ACTIVE_SELECTION_POLICY", fallback_used=False,
        fallback_reason=None,
        operating_strategies=(("v1", STRATEGY, "strategy-hash-v1"),),
        scanner_baseline_id="baseline-test",
        production_fingerprint="production-test",
        production_policy_fingerprint="policy-fingerprint-test",
    )


def _request(pin):
    return ProspectiveCaptureRequest(
        market_scope="KOSPI", requested_as_of=AS_OF,
        candidate_limit=2, horizon_intent="SHORT",
        horizon_policy_version="VN_P1_S2_HORIZON_CONTEXT_V1",
        selection_policy_id=pin.policy_id, selection_policy_hash=pin.policy_hash,
    )


def _ranked_candidate(code="005930"):
    expected_conditions = condition_sources(STRATEGY)
    assert expected_conditions, "Real strategy condition contract required"
    n = len(expected_conditions)
    candidate = {
        "market": "KOSPI", "code": code, "name": "테스트종목",
        "strategy": STRATEGY, "strategy_version_id": "v1",
        "strategy_definition_hash": "strategy-hash-v1",
        "action": "ENTRY_CANDIDATE", "decision_status": "READY",
        "candidate_state": "READY", "data_date": AS_OF,
        "current_price": 101.0,
        "conditions": {"passed": n, "total": n, "missing": 0},
        "risk": {"status": "READY", "warning": False},
        "entry_risk_guide": {
            "price_rule": {"kind": "RANGE", "range_low": 100, "range_high": 102},
            "risk": {"invalidation_price": 93, "target1_price": 114},
        },
    }
    ranked, _ = rank_candidates([candidate])
    assert ranked[0]["priority"]["rank"] == 1
    return ranked[0]


def _result(pin, candidate):
    return {
        "version": "0.21.3.9", "requested_as_of": AS_OF,
        "market_scope": "KOSPI", "data_dates": {"KOSPI": AS_OF},
        "input_fingerprint": "actual-input-fingerprint",
        "scanner_cache_hit": False, "partial_data": False,
        "summary": {"candidate_count": 1},
        "strategy_selection_policy": pin.metadata(),
        "candidates": [candidate], "more_candidates": [],
    }


def _attach_real_shaped_repro_audit(tmp_path, monkeypatch, result, candidate):
    """Create a real matching local audit file; do not fake verification."""
    audit_root = tmp_path / "scanner-repro"
    audit_root.mkdir()
    monkeypatch.setattr(bridge, "REPRO_ROOT", audit_root)
    details = [
        {"raw": source, "condition_id": f"condition-{i}", "status": "PASS"}
        for i, source in enumerate(condition_sources(STRATEGY), 1)
    ]
    audited = deepcopy(candidate)
    audited["rank"] = candidate["priority"]["rank"]
    audited["scanner_inputs"] = {"condition_details": details}
    filename = "scanner-repro_test.json"
    location = audit_root / filename
    location.write_text(json.dumps({
        "result_source": "fresh_analysis",
        "scanner_version": result["version"],
        "analysis_date": result["requested_as_of"],
        "market_scope": result["market_scope"],
        "existing_latest_day_fingerprint": result["input_fingerprint"],
        "candidate_pool_complete": True,
        "candidate_count": 1,
        "candidates": [audited],
    }, ensure_ascii=False), encoding="utf-8")
    result["diagnostics"] = {"reproducibility_audit": {
        "written": True, "result_source": "fresh_analysis",
        "analysis_date": AS_OF,
        "filename": filename, "path": str(location),
        "candidate_count": 1,
    }}
    assert scanner_repro_candidate_key(candidate) == scanner_repro_candidate_key(audited)


def _finalize(catalog, request, result, pin):
    catalog.begin_capture(source_job_id="new-job", request=request)
    return catalog.finalize_capture(
        source_job_id="new-job", request=request, result=result,
        selection_policy_pin=pin,
    )


def test_fresh_scan_rank_and_policy_proof_survive_single_snapshot(tmp_path, monkeypatch):
    catalog = _catalog(tmp_path, monkeypatch)
    pin = _pin()
    request = _request(pin)
    candidate = _ranked_candidate()
    result = _result(pin, candidate)
    _attach_real_shaped_repro_audit(tmp_path, monkeypatch, result, candidate)

    original = ProspectiveCatalog._candidate_snapshot
    calls = []
    def count_projections(item, **kwargs):
        calls.append(item.get("code"))
        return original(item, **kwargs)
    monkeypatch.setattr(ProspectiveCatalog, "_candidate_snapshot",
                        staticmethod(count_projections))
    capture = _finalize(catalog, request, result, pin)
    assert capture["status"] == "COMPLETE"
    assert calls == ["005930"]  # exactly one enrichment, never twice
    stored = catalog.list_samples(capture_run_id=capture["id"])
    assert len(stored) == 1
    sample = stored[0]
    snap = sample["snapshot"]
    assert sample["rank"] == snap["priority"]["rank"] == 1
    assert sample["snapshot_hash"] == digest_json(snap)
    assert snap["strategy_version_id"] == candidate["strategy_version_id"]
    assert snap["strategy_definition_hash"] == candidate["strategy_definition_hash"]
    assert snap["semantic_policy_provenance"]["status"] == "VERIFIED_PINNED_EXECUTION"
    assert snap["semantic_condition_evidence"]["items"]
    assert snap["semantic_condition_evidence"]["passed"] > 0
    assert snap["semantic_source_v2"]["source_snapshot_hash"]
    assert capture["source_snapshot_hash"] == catalog._result_identity(
        request=request, result=result, candidates=[snap],
    )[1]
    # The original Scanner output was not altered by prospective enrichment.
    assert "semantic_policy_provenance" not in candidate


def test_cached_scanner_result_does_not_inherit_fresh_engine_proof(tmp_path, monkeypatch):
    catalog = _catalog(tmp_path, monkeypatch)
    pin = _pin()
    request = _request(pin)
    candidate = _ranked_candidate()
    result = _result(pin, candidate)
    _attach_real_shaped_repro_audit(tmp_path, monkeypatch, result, candidate)
    result["scanner_cache_hit"] = True
    capture = _finalize(catalog, request, result, pin)
    snap = catalog.list_samples(capture_run_id=capture["id"])[0]["snapshot"]
    assert "semantic_condition_evidence" not in snap
    assert snap["semantic_source_v2"]["source_snapshot_hash"]
    assert snap["priority"]["rank"] == 1


def test_missing_rank_remains_missing_without_list_index_backfill(tmp_path, monkeypatch):
    catalog = _catalog(tmp_path, monkeypatch)
    pin = _pin()
    candidate = _ranked_candidate()
    del candidate["priority"]["rank"]
    result = _result(pin, candidate)
    capture = _finalize(catalog, _request(pin), result, pin)
    sample = catalog.list_samples(capture_run_id=capture["id"])[0]
    assert sample["rank"] is None
    assert sample["snapshot"]["priority"].get("rank") is None
    assert sample["snapshot_hash"] == digest_json(sample["snapshot"])


def test_s7_report_only_entry_denominators_and_missing_price_types():
    def row(action, status, n_days=None, ret_5=None, category="INVALID"):
        return {
            "baseline_action": action, "blockers": [],
            "integrity": {"category": category},
            "observation": {
                "status": status, "available_trading_days": n_days,
                "return_5d": ret_5, "return_10d": None,
                "return_20d": None,
            },
        }
    items = [
        row("ENTRY_CANDIDATE", "OBSERVATION_ONLY", 5, 3.0, "LOCAL_VALIDATED"),
        row("ENTRY_CANDIDATE", "OBSERVATION_ONLY", 2, None, "LEGACY_LIMITED"),
        row("ENTRY_CANDIDATE", "UNAVAILABLE", 8, None, "INVALID"),
        row("REFERENCE_ONLY", "NOT_ENTRY_CANDIDATE", None),
        row("REFERENCE_ONLY", "NOT_ENTRY_CANDIDATE", None),
    ]
    summary = S7ShadowJournal._summary(items)
    assert summary["candidate_count"] == 5
    assert summary["entry_candidate_count"] == 3
    assert summary["reference_count"] == 2
    five = summary["window_summaries"]["5d"]
    assert five["observed"] == 1
    assert five["entry_candidate_denominator"] == 3
    assert five["not_yet_observed"] == 2
    assert five["awaiting_future_trading_days"] == 1
    assert five["price_unavailable_or_incomplete"] == 1
    assert five["average_signal_close_change_pct"] == 3.0
    assert summary["window_summaries"]["10d"]["not_yet_observed"] == 3
    assert summary["entry_window_summaries_by_integrity"]["LOCAL_VALIDATED"]["5d"]["observed"] == 1
    assert summary["entry_window_summaries_by_integrity"]["LEGACY_LIMITED"]["5d"]["observed"] == 0
    assert summary["actual_jev_reviews"] == 0
    assert summary["economic_uplift_proven"] is False


def _s13_authentic_active_fixture():
    """Use the actual strategy registry + Q2 entry contract, not made-up 'v1'."""
    from dataclasses import replace
    from app.simulation.strategy_governance import strategy_definition
    from app.strategy.models import StrategyName

    definition = strategy_definition(StrategyName(STRATEGY))
    pin = replace(
        _pin(),
        operating_strategies=((
            definition.strategy_version_id, STRATEGY, definition.definition_hash,
        ),),
    )
    candidate = _ranked_candidate()
    candidate["strategy_version_id"] = definition.strategy_version_id
    candidate["strategy_definition_hash"] = definition.definition_hash
    candidate["entry_risk_guide"]["price_rule"].update({
        "basis": "현재가가 20일선 위",
        "semantic_role": "STRATEGY_REFERENCE",
        "executable_entry_range": False,
    })
    return pin, candidate


def test_s13_full_active_fresh_capture_is_locally_validated_but_provider_held(
    tmp_path, monkeypatch,
):
    """End-to-end: real pin + rank + fresh repro audit + frozen SQL + S7.1/S3."""
    from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
    from app.jev.decision_reviewer_offline import build_scanner_review_input

    catalog = _catalog(tmp_path, monkeypatch)
    pin, candidate = _s13_authentic_active_fixture()
    request = _request(pin)
    result = _result(pin, candidate)
    _attach_real_shaped_repro_audit(tmp_path, monkeypatch, result, candidate)
    capture = _finalize(catalog, request, result, pin)
    assert capture["status"] == "COMPLETE"
    sample = catalog.list_samples(capture_run_id=capture["id"])[0]

    verdict = assess_frozen_candidate(capture, sample)
    assert verdict["category"] == "LOCAL_VALIDATED", verdict
    assert verdict["codes"] == []
    assert verdict["locally_validated"] is True
    assert verdict["external_provider_eligible"] is False

    projection = build_scanner_review_input(
        capture, sample, protocol_id="S13_SYNTHETIC_TEST_ONLY",
    )
    assert projection["status"] == "OFFLINE_INSPECTABLE_ONLY"
    assert projection["actual_provider_eligible"] is False
    assert projection["external_requests"] == 0


def test_s13_cached_capture_does_not_become_locally_validated(
    tmp_path, monkeypatch,
):
    """A cached or unaudited Scanner result cannot invent engine PASS evidence."""
    from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate

    catalog = _catalog(tmp_path, monkeypatch)
    pin, candidate = _s13_authentic_active_fixture()
    request = _request(pin)
    result = _result(pin, candidate)
    _attach_real_shaped_repro_audit(tmp_path, monkeypatch, result, candidate)
    result["scanner_cache_hit"] = True
    capture = _finalize(catalog, request, result, pin)
    sample = catalog.list_samples(capture_run_id=capture["id"])[0]
    verdict = assess_frozen_candidate(capture, sample)
    assert verdict["category"] == "INVALID"
    assert "ENGINE_EVIDENCE_INCOMPLETE" in verdict["codes"]
    assert verdict["external_provider_eligible"] is False
