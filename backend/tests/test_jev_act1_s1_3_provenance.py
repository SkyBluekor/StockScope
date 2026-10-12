"""S1.3 policy provenance: real Scanner-shaped result + immutable pin + SQLite."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from app.jev.semantic_scope_diagnostic import inspect_stored_semantic_source
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest, digest_json
from app.simulation.strategy_governance import strategy_definition
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName
from app.strategy.production_selection_policy import (
    ProductionStrategySelectionRegistry,
    SelectionPolicyPin,
    SelectionPolicyResolution,
    legacy_selection_policy,
)
from app.strategy.semantic_policy_provenance import (
    validate_pinned_selection_policy,
    verify_candidate_policy_binding,
)
from app.strategy.semantic_source_v2 import verify_semantic_source_v2
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


STRATEGY = StrategyName.TREND_FOLLOWING.value


def _pin(source="LEGACY_CURRENT_10_FALLBACK"):
    if source == "LEGACY_CURRENT_10_FALLBACK":
        return ProductionStrategySelectionRegistry._pin_from_resolution(
            SelectionPolicyResolution(
                policy=legacy_selection_policy(), policy_source=source,
                fallback_used=True, fallback_reason=None,
                active_reference_valid=False, policy_hash_valid=True,
            )
        )
    version = strategy_definition(StrategyName(STRATEGY))
    return SelectionPolicyPin(
        policy_id="SS-SELECT-V1-test", policy_hash="synthetic-hash",
        policy_contract_version="VN_P5_S1_SELECTION_POLICY_V1",
        policy_source=source, fallback_used=source == "ROLLBACK_FALLBACK",
        fallback_reason=("TEST_ROLLBACK" if source == "ROLLBACK_FALLBACK" else None),
        operating_strategies=((version.strategy_version_id, STRATEGY, version.definition_hash),),
        scanner_baseline_id="synthetic-baseline",
        production_fingerprint="synthetic-production-fingerprint",
        production_policy_fingerprint="synthetic-policy-fingerprint",
    )


def _candidate(pin):
    n = len(condition_sources(STRATEGY))
    version = pin.strategy_reference(STRATEGY)
    return {
        "market": "KOSPI", "code": "000001", "name": "synthetic-only",
        "strategy": STRATEGY, "action": "ENTRY_CANDIDATE",
        "candidate_state": "READY", "data_date": "2026-10-10",
        "current_price": 100, "strategy_version_id": version["strategy_version_id"],
        "strategy_definition_hash": version["definition_hash"],
        "priority": {"rank": 1, "tier": "READY"},
        "conditions": {"passed": n, "total": n, "missing": 0, "top_missing": []},
        "risk": {"status": "READY", "warning": False},
        "entry_risk_guide": {},
    }


def _fixture(tmp_path: Path, monkeypatch, pin=None):
    from app.strategy import semantic_identity_bridge as bridge

    monkeypatch.setattr(bridge, "REPRO_ROOT", tmp_path)
    pin = pin or _pin()
    candidate = _candidate(pin)
    filename = "scanner-repro_synthetic_20261010-100000_analysis-20261010.json"
    path = tmp_path / filename
    row = {
        key: deepcopy(candidate[key])
        for key in (
            "market", "code", "strategy", "action", "candidate_state",
            "data_date", "current_price", "conditions", "risk",
        )
    }
    row["rank"] = candidate["priority"]["rank"]
    row["scanner_inputs"] = {
        "condition_details": [
            {"raw": raw, "status": "PASS", "condition_id": f"pass-{i}"}
            for i, raw in enumerate(condition_sources(STRATEGY), 1)
        ]
    }
    result = {
        "version": "synthetic-v1", "scanner_cache_hit": False,
        "requested_as_of": "2026-10-10", "market_scope": "ALL",
        "data_dates": {"KOSPI": "2026-10-10"},
        "input_fingerprint": {"synthetic": True}, "partial_data": False,
        "summary": {"candidate_count": 1}, "candidates": [candidate],
        "more_candidates": [], "strategy_selection_policy": pin.metadata(),
        "diagnostics": {"reproducibility_audit": {
            "written": True, "filename": filename, "path": str(path),
            "analysis_date": "2026-10-10", "candidate_count": 1,
            "result_source": "fresh_analysis",
        }},
    }
    repro = {
        "result_source": "fresh_analysis", "scanner_version": result["version"],
        "analysis_date": result["requested_as_of"], "market_scope": "ALL",
        "existing_latest_day_fingerprint": result["input_fingerprint"],
        "candidate_pool_complete": True, "candidate_count": 1,
        "candidates": [row],
    }
    path.write_text(json.dumps(repro), encoding="utf-8")
    request = ProspectiveCaptureRequest(
        market_scope="ALL", requested_as_of="2026-10-10", candidate_limit=5,
        horizon_intent="LEGACY_UNSPECIFIED", horizon_policy_version=None,
        selection_policy_id=pin.policy_id, selection_policy_hash=pin.policy_hash,
    )
    return pin, candidate, result, request, path


def _catalog(tmp_path):
    db = tmp_path / "simulation.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE placeholder(id INTEGER PRIMARY KEY)")
    migrate_prospective_store(db)
    return ProspectiveCatalog(db)


def _store(catalog, pin, result, request, job):
    catalog.begin_capture(source_job_id=job, request=request)
    return catalog.finalize_capture(
        source_job_id=job, request=request, result=result,
        selection_policy_pin=pin,
    )


@pytest.mark.parametrize("source", [
    "LEGACY_CURRENT_10_FALLBACK", "ACTIVE_SELECTION_POLICY", "ROLLBACK_FALLBACK",
])
def test_pinned_policy_and_actual_condition_proof_complete_offline(
    tmp_path, monkeypatch, source,
):
    pin, candidate, result, request, _ = _fixture(tmp_path, monkeypatch, _pin(source))
    original = deepcopy(candidate)
    valid, reason = validate_pinned_selection_policy(
        scanner_policy=result["strategy_selection_policy"],
        request_policy_id=request.selection_policy_id,
        request_policy_hash=request.selection_policy_hash, pin=pin,
    )
    assert valid and reason == "POLICY_PIN_VERIFIED"
    catalog = _catalog(tmp_path)
    first = _store(catalog, pin, result, request, "first")
    assert first["status"] == "COMPLETE"
    [stored] = catalog.list_samples(capture_run_id=first["id"])
    snapshot = stored["snapshot"]
    assert stored["rank"] == original["priority"]["rank"]
    assert snapshot["semantic_policy_provenance"]["status"] == "VERIFIED_PINNED_EXECUTION"
    assert snapshot["semantic_policy_provenance"]["policy_id"] == pin.policy_id
    assert snapshot["semantic_condition_evidence"]["passed"] == len(condition_sources(STRATEGY))
    assert snapshot["semantic_source_v2"]["readiness"]["local_semantic_status"] != "LOCAL_INCOMPLETE"
    assert verify_semantic_source_v2(snapshot["semantic_source_v2"]) == (True, None)
    assert inspect_stored_semantic_source(snapshot, stored_snapshot_hash=stored["snapshot_hash"]) not in {
        "SEMANTIC_SOURCE_MISSING", "SEMANTIC_SOURCE_INVALID",
    }
    for key in ("strategy_version_id", "strategy_definition_hash", "risk", "priority", "action"):
        assert snapshot[key] == original[key]
    assert candidate == original
    second = _store(catalog, pin, result, request, "duplicate")
    assert second["status"] == "DUPLICATE"
    assert second["canonical_capture_id"] == first["id"]
    assert len(catalog.list_samples()) == 1


@pytest.mark.parametrize("failure", [
    "metadata_hash", "request_hash", "legacy_forged_hash",
    "missing_pin", "unknown_source", "candidate_strategy_version",
    "audit_condition", "audit_input_fingerprint", "cached",
])
def test_mismatched_provenance_never_completes_semantics(tmp_path, monkeypatch, failure):
    pin, candidate, result, request, path = _fixture(tmp_path, monkeypatch)
    if failure == "metadata_hash":
        result["strategy_selection_policy"]["policy_hash"] = "tampered"
    elif failure == "request_hash":
        request = ProspectiveCaptureRequest(
            market_scope="ALL", requested_as_of="2026-10-10", candidate_limit=5,
            horizon_intent="LEGACY_UNSPECIFIED", horizon_policy_version=None,
            selection_policy_id=pin.policy_id, selection_policy_hash="tampered",
        )
    elif failure == "legacy_forged_hash":
        from dataclasses import replace
        pin = replace(pin, policy_hash="tampered")
        result["strategy_selection_policy"] = pin.metadata()
        request = ProspectiveCaptureRequest(
            market_scope="ALL", requested_as_of="2026-10-10", candidate_limit=5,
            horizon_intent="LEGACY_UNSPECIFIED", horizon_policy_version=None,
            selection_policy_id=pin.policy_id, selection_policy_hash=pin.policy_hash,
        )
    elif failure == "missing_pin":
        pin = None
    elif failure == "unknown_source":
        from dataclasses import replace
        pin = replace(pin, policy_source="UNKNOWN")
        result["strategy_selection_policy"] = pin.metadata()
    elif failure == "candidate_strategy_version":
        candidate["strategy_version_id"] = "fabricated"
    elif failure in {"audit_condition", "audit_input_fingerprint"}:
        audit = json.loads(path.read_text(encoding="utf-8"))
        if failure == "audit_condition":
            audit["candidates"][0]["scanner_inputs"]["condition_details"][0]["status"] = "FAIL"
        else:
            audit["existing_latest_day_fingerprint"] = {"mismatch": True}
        path.write_text(json.dumps(audit), encoding="utf-8")
    else:
        result["scanner_cache_hit"] = True
    catalog = _catalog(tmp_path)
    capture = _store(catalog, pin, result, request, "first")
    assert capture["status"] == "COMPLETE"
    [stored] = catalog.list_samples(capture_run_id=capture["id"])
    snap = stored["snapshot"]
    assert "semantic_condition_evidence" not in snap
    assert snap["semantic_source_v2"]["readiness"]["local_semantic_status"] == "LOCAL_INCOMPLETE"
    assert snap["action"] == candidate["action"]
    assert snap["risk"] == candidate["risk"]
    assert snap["priority"] == candidate["priority"]
    assert snap["strategy_version_id"] == candidate["strategy_version_id"]
    assert stored["snapshot_hash"] == digest_json(snap)


def test_unverified_active_policy_candidate_cannot_use_original_version(tmp_path, monkeypatch):
    pin, candidate, result, request, _ = _fixture(
        tmp_path, monkeypatch, _pin("ACTIVE_SELECTION_POLICY"),
    )
    candidate["strategy_definition_hash"] = "invalid"
    catalog = _catalog(tmp_path)
    capture = _store(catalog, pin, result, request, "first")
    [stored] = catalog.list_samples(capture_run_id=capture["id"])
    assert stored["snapshot"]["semantic_policy_provenance"]["status"] == "UNVERIFIED"
    assert stored["snapshot"]["semantic_source_v2"]["readiness"]["local_semantic_status"] == "LOCAL_INCOMPLETE"
    assert stored["snapshot"]["strategy_definition_hash"] == "invalid"


def test_read_only_diagnostic_distinguishes_historical_proof_and_policy(tmp_path, monkeypatch):
    from tools.data.audit_jev_act1_s1_3_provenance import audit_policy_provenance

    pin, _, result, request, _ = _fixture(tmp_path, monkeypatch)
    catalog = _catalog(tmp_path)
    _store(catalog, pin, result, request, "fresh")
    output = audit_policy_provenance(catalog.db_path, tmp_path)
    assert output["capture_statuses"] == {"COMPLETE": 1}
    [group] = output["by_analysis_date"]
    assert group["entry_candidates"] == 1
    assert group["historical_engine_conditions_match"] == 1
    assert group["policy_provenance_attested_new_record"] == 1
    assert output["db_writes"] == 0
    assert output["external_provider_calls"] == 0

    # A separate historical/unattested database must remain UNKNOWN even when
    # exactly the same condition evidence exists in the local audit directory.
    old_dir = tmp_path / "unattested"
    old_dir.mkdir()
    old_catalog = _catalog(old_dir)
    _store(old_catalog, None, result, request, "unattested")
    after = audit_policy_provenance(old_catalog.db_path, tmp_path)
    assert after["capture_statuses"]["COMPLETE"] == 1
    assert after["by_analysis_date"][0]["policy_provenance_unverified_or_mismatch"] == 1
    assert after["by_analysis_date"][0]["historical_engine_conditions_match"] == 1


def test_uat_inspector_passes_only_with_full_original_proof_and_before_state(
    tmp_path, monkeypatch,
):
    from tools.data.audit_jev_act1_s1_3_uat import baseline, inspect

    pin, candidate, result, request, _ = _fixture(tmp_path, monkeypatch)
    catalog = _catalog(tmp_path)
    before = baseline(catalog.db_path)
    capture = _store(catalog, pin, result, request, "uat-one")
    original = deepcopy(result)
    original["prospective_capture"] = {
        "capture_id": capture["id"], "status": "COMPLETE",
    }
    db_mtime = catalog.db_path.stat().st_mtime_ns
    verdict = inspect(
        db=catalog.db_path, repro_root=tmp_path,
        capture_id=capture["id"], before=before, scanner_result=original,
    )
    assert verdict["status"] == "PASS", verdict
    assert verdict["rank_column_match"] == 1
    assert verdict["policy_attested"] == 1
    assert verdict["engine_evidence_stored"] == 1
    assert verdict["semantic_v2_complete"] == 1
    assert verdict["preexisting_captures_unchanged"] is True
    assert catalog.db_path.stat().st_mtime_ns == db_mtime

    no_proof = inspect(db=catalog.db_path, repro_root=tmp_path, capture_id=capture["id"])
    assert no_proof["status"] == "INCONCLUSIVE"
    assert "ORIGINAL_SCANNER_RESULT_NOT_SUPPLIED" in no_proof["inconclusive_reasons"]

    altered = deepcopy(original)
    altered["input_fingerprint"] = {"mismatch": True}
    mismatch = inspect(
        db=catalog.db_path, repro_root=tmp_path,
        capture_id=capture["id"], before=before, scanner_result=altered,
    )
    assert mismatch["status"] != "PASS"
    assert "ORIGINAL_REPRO_FULL_ATTESTATION_MISSING" in mismatch["inconclusive_reasons"]


def test_uat_inspector_rejects_duplicate_and_detects_old_capture_changes(tmp_path, monkeypatch):
    from tools.data.audit_jev_act1_s1_3_uat import baseline, inspect

    pin, _, result, request, _ = _fixture(tmp_path, monkeypatch)
    catalog = _catalog(tmp_path)
    first = _store(catalog, pin, result, request, "first")
    before = baseline(catalog.db_path)
    second = _store(catalog, pin, result, request, "duplicate")
    assert second["status"] == "DUPLICATE"
    outcome = inspect(db=catalog.db_path, repro_root=tmp_path, capture_id=second["id"], before=before)
    assert outcome["status"] == "INCONCLUSIVE"
    assert "NEW_COMPLETE_CAPTURE_REQUIRED" in outcome["inconclusive_reasons"]
    assert outcome["preexisting_captures_unchanged"] is True

    # An earlier canonical COMPLETE may never be silently mutated.
    with sqlite3.connect(catalog.db_path) as conn:
        conn.execute(
            "UPDATE prospective_recommendation_sample SET rank=? WHERE capture_run_id=?",
            (99, first["id"]),
        )
    corrupted = inspect(
        db=catalog.db_path, repro_root=tmp_path,
        capture_id=second["id"], before=before,
    )
    assert "PRE_EXISTING_CAPTURES_MUTATED" in corrupted["reasons"]


def test_uat_preflight_uses_existing_market_rows_without_network(
    tmp_path, monkeypatch,
):
    from datetime import date as Date, timedelta
    from tools.data.audit_jev_act1_s1_3_uat import preflight

    pin = _pin()
    catalog = _catalog(tmp_path)
    market_db = tmp_path / "market.db"
    with sqlite3.connect(market_db) as conn:
        conn.executescript("""
            CREATE TABLE day_status(market TEXT, bas_dd TEXT, kind TEXT, status TEXT);
            CREATE TABLE stock_daily(market TEXT, bas_dd TEXT, stock_code TEXT, row_json TEXT);
            CREATE TABLE main_index_daily(market TEXT, bas_dd TEXT, row_json TEXT);
        """)
        end = Date(2026, 10, 9)
        start = end - timedelta(days=220)
        rows = []
        for i in range((end - start).days + 1):
            d = start + timedelta(days=i)
            if d.weekday() < 5:
                key = d.strftime("%Y%m%d")
                for market in ("KOSPI", "KOSDAQ"):
                    rows += [(market, key, "stock", "data"), (market, key, "index", "data")]
        conn.executemany("INSERT INTO day_status VALUES(?,?,?,?)", rows)
        for market in ("KOSPI", "KOSDAQ"):
            conn.execute("INSERT INTO stock_daily VALUES(?,?,?,?)", (market, "20261009", "synthetic", "{}"))
            conn.execute("INSERT INTO main_index_daily VALUES(?,?,?)", (market, "20261009", "{}"))
    previous_market_mtime = market_db.stat().st_mtime_ns
    previous_sim_mtime = catalog.db_path.stat().st_mtime_ns
    pre = preflight(
        db=catalog.db_path, market_db=market_db,
        analysis_date="2026-10-09", today=Date(2026, 10, 12),
        pin_resolver=lambda: pin, check_git=False,
        repro_root=tmp_path / "no-repro", cache_root=tmp_path / "no-cache",
    )
    assert pre["status"] == "READY_FOR_APPROVAL_NOT_EXECUTION", pre
    assert pre["missing_market_store_slots_total"] == 0
    assert pre["requested_date_complete"] == {"KOSPI": True, "KOSDAQ": True}
    assert market_db.stat().st_mtime_ns == previous_market_mtime
    assert catalog.db_path.stat().st_mtime_ns == previous_sim_mtime

    with sqlite3.connect(market_db) as conn:
        conn.execute("DELETE FROM day_status WHERE market='KOSPI' AND bas_dd='20261009'")
    blocked = preflight(
        db=catalog.db_path, market_db=market_db,
        analysis_date="2026-10-09", today=Date(2026, 10, 12),
        pin_resolver=lambda: pin, check_git=False,
        repro_root=tmp_path / "no-repro", cache_root=tmp_path / "no-cache",
    )
    assert blocked["status"] == "BLOCKED"
    assert "REQUESTED_DATE_MISSING_KOSPI" in blocked["reasons"]


def test_no_pin_or_wrong_baseline_is_fail_closed():
    pin = _pin()
    assert not validate_pinned_selection_policy(
        scanner_policy=pin.metadata(),
        request_policy_id=pin.policy_id,
        request_policy_hash=pin.policy_hash, pin=None,
    )[0]
    from dataclasses import replace
    forged = replace(pin, production_fingerprint="tampered")
    assert not validate_pinned_selection_policy(
        scanner_policy=forged.metadata(),
        request_policy_id=forged.policy_id,
        request_policy_hash=forged.policy_hash, pin=forged,
    )[0]
    assert verify_candidate_policy_binding({"strategy": "other"}, pin)[0] is False
