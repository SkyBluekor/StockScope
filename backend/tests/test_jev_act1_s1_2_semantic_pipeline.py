"""JEV ACT1-S1.2: read existing Scanner reproducibility evidence, not new Scanner code."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from app.jev.semantic_scope_diagnostic import inspect_stored_semantic_source
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import route_typesafe_state_v4
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest, digest_json
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName
from app.strategy.semantic_identity_bridge import (
    LEGACY_SELECTION_SOURCE,
    scanner_repro_candidate_key,
    semantic_projection_candidate,
    verified_scanner_repro_rows,
)
from app.strategy.semantic_source_v2 import verify_semantic_source_v2
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


STRATEGY = StrategyName.TREND_FOLLOWING.value
POLICY = {
    "policy_id": "LEGACY-CURRENT-TEST",
    "policy_hash": "test-policy-hash",
    "policy_source": LEGACY_SELECTION_SOURCE,
    "fallback_used": True,
}


def _candidate() -> dict:
    n = len(condition_sources(STRATEGY))
    return {
        "market": "KOSPI", "code": "000001", "name": "synthetic-only",
        "strategy": STRATEGY,
        "strategy_version_id": None, "strategy_definition_hash": None,
        "data_date": "2026-10-10", "current_price": 100,
        "candidate_state": "READY", "action": "ENTRY_CANDIDATE",
        "conditions": {"passed": n, "total": n, "missing": 0, "top_missing": []},
        "risk": {"status": "READY", "warning": False},
        "entry_risk_guide": {}, "priority": {"tier": "READY", "rank": 1},
    }


def _audit_row(candidate: dict) -> dict:
    row = {
        key: deepcopy(candidate[key])
        for key in (
            "market", "code", "strategy", "action",
            "candidate_state", "data_date", "current_price", "conditions", "risk",
        )
    }
    row["rank"] = candidate["priority"]["rank"]
    row["scanner_inputs"] = {
        "condition_details": [
            {"raw": raw, "status": "PASS", "condition_id": f"pass-{i}"}
            for i, raw in enumerate(condition_sources(STRATEGY), 1)
        ],
    }
    return row


def _result(candidate: dict, *, path: Path, filename: str) -> dict:
    return {
        "version": "0.21.3.9",
        "scanner_cache_hit": False,
        "requested_as_of": "2026-10-10",
        "market_scope": "ALL",
        "data_dates": {"KOSPI": "2026-10-10"},
        "input_fingerprint": {"synthetic": True},
        "partial_data": False,
        "summary": {"candidate_count": 1, "shown_count": 1},
        "candidates": [candidate],
        "more_candidates": [],
        "strategy_selection_policy": dict(POLICY),
        "diagnostics": {
            "reproducibility_audit": {
                "written": True, "path": str(path), "filename": filename,
                "analysis_date": "2026-10-10",
                "candidate_count": 1, "result_source": "fresh_analysis",
            },
        },
    }


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.strategy import semantic_identity_bridge as bridge
    monkeypatch.setattr(bridge, "REPRO_ROOT", tmp_path)
    candidate = _candidate()
    filename = "scanner-repro_synthetic_20261010-100000_analysis-20261010.json"
    path = tmp_path / filename
    data = _result(candidate, path=path, filename=filename)
    repro = {
        "result_source": "fresh_analysis",
        "scanner_version": data["version"],
        "analysis_date": data["requested_as_of"],
        "market_scope": data["market_scope"],
        "existing_latest_day_fingerprint": data["input_fingerprint"],
        "candidate_pool_complete": True,
        "candidate_count": 1,
        "candidates": [_audit_row(candidate)],
    }
    path.write_text(json.dumps(repro, ensure_ascii=False), encoding="utf-8")
    return candidate, data, path


def test_real_scanner_rank_location_and_conflicting_rank_fail_closed():
    candidate = _candidate()
    audit = _audit_row(candidate)
    assert "rank" not in candidate  # Actual Scanner ranks in priority, not at top level.
    assert candidate["priority"]["rank"] == 1
    assert audit["rank"] == 1
    assert scanner_repro_candidate_key(candidate) == ("KOSPI", "000001", "1")
    assert scanner_repro_candidate_key(audit) == ("KOSPI", "000001", "1")
    tampered = deepcopy(candidate)
    tampered["rank"] = 2
    assert scanner_repro_candidate_key(tampered) == ("", "", "")
    tampered = deepcopy(candidate)
    tampered["priority"]["rank"] = 2
    assert semantic_projection_candidate(
        tampered, selection_policy=POLICY, audited=audit,
    )["strategy_version_id"] is None


def test_valid_repro_audit_enriches_only_semantic_source(tmp_path: Path, monkeypatch):
    candidate, data, path = _fixture(tmp_path, monkeypatch)
    rows = verified_scanner_repro_rows(data)
    assert len(rows) == 1
    audited = next(iter(rows.values()))
    before = deepcopy(candidate)
    projection = semantic_projection_candidate(candidate, selection_policy=POLICY, audited=audited)
    assert projection["strategy_version_id"]
    assert projection["strategy_definition_hash"]
    assert candidate == before
    snapshot = ProspectiveCatalog._candidate_snapshot(
        candidate, selection_policy=POLICY, audited=audited,
    )
    assert snapshot["strategy_version_id"] is None
    assert snapshot["strategy_definition_hash"] is None
    assert snapshot["action"] == before["action"]
    assert snapshot["priority"]["rank"] == before["priority"]["rank"]
    assert "rank" not in snapshot
    assert snapshot["risk"] == before["risk"]
    assert snapshot["semantic_condition_evidence"]["passed"] == len(condition_sources(STRATEGY))
    v2 = snapshot["semantic_source_v2"]
    assert v2["readiness"]["local_semantic_status"] != "LOCAL_INCOMPLETE"
    assert verify_semantic_source_v2(v2) == (True, None)
    assert inspect_stored_semantic_source(snapshot, stored_snapshot_hash=digest_json(snapshot)) not in {
        "SEMANTIC_SOURCE_INVALID", "SEMANTIC_SOURCE_MISSING",
    }


@pytest.mark.parametrize("bad", [
    "wrong_hash", "wrong_action", "condition_fail", "condition_duplicate",
    "condition_missing", "condition_unmapped", "stale_version",
])
def test_bad_audit_never_promotes_semantic_source(tmp_path: Path, monkeypatch, bad):
    candidate, data, path = _fixture(tmp_path, monkeypatch)
    repro = json.loads(path.read_text(encoding="utf-8"))
    row = repro["candidates"][0]
    if bad == "wrong_hash":
        repro["existing_latest_day_fingerprint"] = {"wrong": True}
    elif bad == "wrong_action":
        row["action"] = "WAIT"
    elif bad == "condition_fail":
        row["scanner_inputs"]["condition_details"][0]["status"] = "FAIL"
    elif bad == "condition_duplicate":
        row["scanner_inputs"]["condition_details"][0] = deepcopy(
            row["scanner_inputs"]["condition_details"][1]
        )
    elif bad == "condition_missing":
        row["scanner_inputs"]["condition_details"].pop()
    elif bad == "condition_unmapped":
        row["scanner_inputs"]["condition_details"][0]["raw"] = "not an authored condition"
    else:
        repro["scanner_version"] = "old-version"
    path.write_text(json.dumps(repro, ensure_ascii=False), encoding="utf-8")
    rows = verified_scanner_repro_rows(data)
    audited = rows.get(("KOSPI", "000001", "1"))
    snapshot = ProspectiveCatalog._candidate_snapshot(
        candidate, selection_policy=POLICY, audited=audited,
    )
    assert snapshot["semantic_source_v2"]["readiness"]["local_semantic_status"] == "LOCAL_INCOMPLETE"
    assert "semantic_strategy_identity" not in snapshot


def test_cached_foreign_and_active_policy_do_not_backfill(tmp_path: Path, monkeypatch):
    candidate, data, path = _fixture(tmp_path, monkeypatch)
    data["scanner_cache_hit"] = True
    assert verified_scanner_repro_rows(data) == {}
    data["scanner_cache_hit"] = False
    assert len(verified_scanner_repro_rows(data)) == 1
    audited = next(iter(verified_scanner_repro_rows(data).values()))
    active = dict(POLICY, policy_source="ACTIVE_SELECTION_POLICY", fallback_used=False)
    assert semantic_projection_candidate(
        candidate, selection_policy=active, audited=audited,
    )["strategy_version_id"] is None
    stale = deepcopy(candidate)
    stale["strategy_version_id"] = "stale"
    assert semantic_projection_candidate(
        stale, selection_policy=POLICY, audited=audited,
    )["strategy_version_id"] == "stale"
    with pytest.raises(TypeSafeStateProjectionError, match="OUT_OF_SCOPE_HORIZON"):
        route_typesafe_state_v4({
            "action": "ENTRY_CANDIDATE", "horizon_intent": "LEGACY_UNSPECIFIED",
            "snapshot": ProspectiveCatalog._candidate_snapshot(
                candidate, selection_policy=POLICY, audited=audited,
            ),
        })


def test_traversal_audit_path_rejected(tmp_path: Path, monkeypatch):
    candidate, data, path = _fixture(tmp_path, monkeypatch)
    data["diagnostics"]["reproducibility_audit"]["path"] = str(tmp_path.parent / path.name)
    assert verified_scanner_repro_rows(data) == {}


def test_real_sqlite_prospective_capture_and_dedup(tmp_path: Path, monkeypatch):
    candidate, data, path = _fixture(tmp_path, monkeypatch)
    db = tmp_path / "simulation.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)")
    migrate_prospective_store(db)
    catalog = ProspectiveCatalog(db)
    request = ProspectiveCaptureRequest(
        market_scope="ALL", requested_as_of="2026-10-10", candidate_limit=5,
        horizon_intent="LEGACY_UNSPECIFIED", horizon_policy_version=None,
    )
    catalog.begin_capture(source_job_id="test-1", request=request)
    first = catalog.finalize_capture(
        source_job_id="test-1", request=request, result=data,
    )
    assert first["status"] == "COMPLETE"
    samples = catalog.list_samples(capture_run_id=first["id"])
    assert len(samples) == 1
    stored = samples[0]["snapshot"]
    assert samples[0]["snapshot_hash"] == digest_json(stored)
    assert stored["strategy_version_id"] is None
    assert stored["priority"]["rank"] == 1
    assert "rank" not in stored
    assert stored["semantic_source_v2"]["readiness"]["local_semantic_status"] != "LOCAL_INCOMPLETE"
    assert stored["semantic_strategy_identity"]["source"] == "LEGACY_ENGINE_IDENTITY_VERIFIED"
    original_risk = deepcopy(candidate["risk"])
    assert stored["risk"] == original_risk
    catalog.begin_capture(source_job_id="test-2", request=request)
    second = catalog.finalize_capture(
        source_job_id="test-2", request=request, result=data,
    )
    assert second["status"] == "DUPLICATE"
    assert second["canonical_capture_id"] == first["id"]
    assert len(catalog.list_samples()) == 1


def test_no_external_network_dependency(tmp_path: Path, monkeypatch):
    import socket
    monkeypatch.setattr(
        socket, "create_connection",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no external network")),
    )
    candidate, data, path = _fixture(tmp_path, monkeypatch)
    assert len(verified_scanner_repro_rows(data)) == 1
