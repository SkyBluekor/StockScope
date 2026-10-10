"""ACT1-S1.1: immutable legacy-horizon semantic diagnostics, not AI activation."""
from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from app.horizon import resolve_horizon_context
from app.jev.semantic_scope_diagnostic import (
    RESIDUAL_REVIEW_OBSERVED,
    SEMANTIC_SOURCE_INVALID,
    SEMANTIC_SOURCE_MISSING,
    inspect_stored_semantic_source,
)
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import route_typesafe_state_v4
from app.prospective.models import PROSPECTIVE_SCHEMA_VERSION, digest_json
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName
from app.strategy.semantic_composition import (
    LOCAL_AMBIGUOUS, LOCAL_CONFLICT, LOCAL_INCOMPLETE, LOCAL_MATCH,
)
from app.strategy.semantic_source_v2 import build_semantic_source_v2
from tools.data.audit_jev_act1_readiness import (
    _categorize, audit_stored_prospective, run_readiness_audit,
)

LOCAL_STATUSES = {LOCAL_MATCH, LOCAL_CONFLICT, LOCAL_INCOMPLETE, LOCAL_AMBIGUOUS}


def _source() -> dict:
    strategy = StrategyName.TREND_FOLLOWING.value
    binding = next(
        x for x in current_strategy_definitions()
        if x.strategy_key == strategy
    )
    count = len(condition_sources(strategy))
    return build_semantic_source_v2({
        "market": "KOSPI", "code": "000001", "name": "synthetic-legacy",
        "strategy": strategy,
        "strategy_version_id": binding.strategy_version_id,
        "strategy_definition_hash": binding.definition_hash,
        "decision_status": "READY", "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE",
        "conditions": {
            "passed": count, "total": count, "missing": 0, "top_missing": [],
        },
    })


def _make_db(db: Path) -> Path:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE prospective_schema_meta(key TEXT PRIMARY KEY,value TEXT)"
        )
        conn.execute(
            "INSERT INTO prospective_schema_meta VALUES('schema_version',?)",
            (PROSPECTIVE_SCHEMA_VERSION,),
        )
        conn.execute(
            "CREATE TABLE prospective_capture_run("
            "id TEXT PRIMARY KEY,status TEXT,horizon_intent TEXT)"
        )
        conn.execute(
            "CREATE TABLE prospective_recommendation_sample("
            "capture_run_id TEXT,sample_index INTEGER,market TEXT,strategy TEXT,"
            "action TEXT,snapshot_json TEXT,snapshot_hash TEXT)"
        )
    return db


def _insert(
    db: Path, index: int, *, action: str = "ENTRY_CANDIDATE",
    horizon: str = "LEGACY_UNSPECIFIED", source: dict | None = None,
    snapshot_hash: str | None = None, capture_id: str = "legacy",
    raw_json: str | None = None,
) -> None:
    snapshot = {"semantic_source_v2": source} if source is not None else {}
    body = raw_json or json.dumps(snapshot, ensure_ascii=False)
    stored_hash = snapshot_hash if snapshot_hash is not None else digest_json(snapshot)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO prospective_capture_run VALUES(?,?,?)",
            (capture_id, "COMPLETE", horizon),
        )
        conn.execute(
            "INSERT INTO prospective_recommendation_sample VALUES(?,?,?,?,?,?,?)",
            (capture_id, index, "KOSPI", "trend_following", action, body, stored_hash),
        )


def test_existing_scanner_legacy_is_a_valid_horizon_not_short_alias() -> None:
    legacy = resolve_horizon_context(None)
    assert legacy.intent == "LEGACY_UNSPECIFIED"
    assert legacy.policy_version is None
    assert resolve_horizon_context("SHORT").support_status == "EVALUATION_PENDING"
    assert _categorize({
        "action": "ENTRY_CANDIDATE",
        "horizon_intent": "LEGACY_UNSPECIFIED",
        "snapshot": {"semantic_source_v2": _source()},
    }) == "LEGACY_HORIZON_BLOCKED"


def test_legacy_local_inspection_accepts_authored_source_without_provider() -> None:
    source = _source()
    snapshot = {"semantic_source_v2": source}
    result = inspect_stored_semantic_source(
        snapshot, stored_snapshot_hash=digest_json(snapshot)
    )
    assert result in LOCAL_STATUSES
    # Legacy local inspection must not silently become approved V4 provider route.
    with pytest.raises(TypeSafeStateProjectionError, match="OUT_OF_SCOPE_HORIZON"):
        route_typesafe_state_v4({
            "action": "ENTRY_CANDIDATE",
            "horizon_intent": "LEGACY_UNSPECIFIED",
            "snapshot": snapshot,
        })


def test_invalid_and_inconsistent_semantic_snapshots_fail_closed() -> None:
    source = _source()
    snapshot = {"semantic_source_v2": source}
    assert inspect_stored_semantic_source({}) == SEMANTIC_SOURCE_MISSING
    assert inspect_stored_semantic_source(None) == SEMANTIC_SOURCE_INVALID
    assert inspect_stored_semantic_source(
        snapshot, stored_snapshot_hash="0" * 64
    ) == SEMANTIC_SOURCE_INVALID

    tampered = deepcopy(snapshot)
    tampered["semantic_source_v2"]["readiness"]["residual_review_eligible"] = True
    # Even when the outer snapshot hash matches a tampered version, V2 source hash fails.
    assert inspect_stored_semantic_source(
        tampered, stored_snapshot_hash=digest_json(tampered)
    ) == SEMANTIC_SOURCE_INVALID

    mismatch = deepcopy(snapshot)
    mismatch["semantic_source_v2"]["source_snapshot_hash"] = "f" * 64
    assert inspect_stored_semantic_source(mismatch) == SEMANTIC_SOURCE_INVALID


def test_legacy_21_entry_9_wait_counts_are_disjoint_and_readonly(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "fixture.db")
    source = _source()
    for index in range(21):
        _insert(db, index, source=source)
    for index in range(21, 30):
        _insert(db, index, action="WAIT", source=source)
    with sqlite3.connect(db) as conn:
        original = "\n".join(conn.iterdump())
    output = run_readiness_audit(db)
    audit, gate = output["audit"], output["activation_readiness"]
    assert audit["total_samples"] == 30
    assert audit["total_captures"] == 1
    assert audit["categories"]["LEGACY_HORIZON_BLOCKED"] == 21
    assert audit["categories"]["ACTION_OUT_OF_SCOPE"] == 9
    assert sum(audit["categories"].values()) == 30
    legacy = audit["legacy_local_inspection"]
    assert legacy["total"] == legacy["inspectable"] == 21
    assert sum(legacy["categories"].values()) == 21
    assert legacy["provider_eligible"] == 0
    assert audit["provider_eligible"] == audit["v4_compatible"] == 0
    assert gate["activation_verdict"] == "HOLD"
    assert gate["can_activate_user_feature"] is False
    checks = {x["code"]: x for x in gate["checks"]}
    assert checks["HORIZON_SCOPE_COMPATIBILITY"]["status"] == "HOLD"
    assert checks["PRODUCTION_REACHABILITY"]["explanation"] == (
        "LEGACY_LOCAL_REVIEW_ONLY_NO_PROVIDER_ELIGIBLE"
    )
    assert audit["db_writes"] == audit["external_network_requests"] == 0
    rendered = json.dumps(output, ensure_ascii=False)
    assert "synthetic-legacy" not in rendered and "000001" not in rendered
    with sqlite3.connect(db) as conn:
        assert "\n".join(conn.iterdump()) == original


def test_legacy_mixed_source_integrity_and_horizon_scope(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "fixture.db")
    _insert(db, 0, source=_source())
    _insert(db, 1, source=None)
    _insert(db, 2, source=_source(), snapshot_hash="BAD")
    _insert(db, 3, source=_source(), raw_json="{malformed")
    _insert(db, 4, source=_source(), horizon="LONG", capture_id="long")
    _insert(db, 5, action="WAIT", source=_source())
    report = audit_stored_prospective(db)
    assert report["categories"]["LEGACY_HORIZON_BLOCKED"] == 4
    assert report["categories"]["ACTION_OUT_OF_SCOPE"] == 1
    assert report["categories"]["EXPLICIT_HORIZON_UNSUPPORTED"] == 1
    local = report["legacy_local_inspection"]
    assert local["inspectable"] == 1
    assert local["categories"]["SEMANTIC_SOURCE_MISSING"] == 1
    assert local["categories"]["SEMANTIC_SOURCE_INVALID"] == 2
    assert report["provider_eligible"] == 0


def test_local_residual_is_observed_but_cannot_be_provider_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.data import audit_jev_act1_readiness as audit_module
    db = _make_db(tmp_path / "fixture.db")
    _insert(db, 0, source=_source())
    monkeypatch.setattr(
        audit_module, "inspect_stored_semantic_source",
        lambda snapshot, **kwargs: RESIDUAL_REVIEW_OBSERVED,
    )
    monkeypatch.setattr(
        audit_module, "route_typesafe_state_v4",
        lambda sample: (_ for _ in ()).throw(AssertionError("provider route forbidden")),
    )
    result = run_readiness_audit(db)
    assert result["audit"]["legacy_local_inspection"]["residual_observed"] == 1
    assert result["audit"]["provider_eligible"] == 0
    assert next(
        x["explanation"] for x in result["activation_readiness"]["checks"]
        if x["code"] == "PRODUCTION_REACHABILITY"
    ) == "LEGACY_RESIDUAL_OBSERVED_PROVIDER_NOT_AUTHORIZED"


def test_explicit_v4_path_is_preserved_and_not_counted_as_legacy(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "fixture.db")
    _insert(db, 0, source=_source(), horizon="SHORT", capture_id="short")
    report = audit_stored_prospective(db)
    assert report["total_samples"] == 1
    assert report["legacy_local_inspection"]["total"] == 0
    assert report["v4_compatible"] == 1
    assert report["provider_eligible"] == 0


def test_audit_is_repeatable_and_does_not_need_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import socket
    monkeypatch.setattr(
        socket, "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    db = _make_db(tmp_path / "fixture.db")
    _insert(db, 0, source=_source())
    assert run_readiness_audit(db) == run_readiness_audit(db)
