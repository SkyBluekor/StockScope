"""JEV-ACT1-S1: safe, non-networked local production-readiness diagnostics."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.jev.activation_readiness import assess_jev_act1_readiness
from app.jev.typesafe_canary_v4 import (
    TypeSafeCanaryV4Error,
    load_frozen_canary_v4_protocol,
)
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.prospective.models import PROSPECTIVE_SCHEMA_VERSION
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName
from app.strategy.semantic_source_v2 import build_semantic_source_v2
from tools.data.audit_jev_act1_readiness import (
    _categorize,
    audit_stored_prospective,
    run_readiness_audit,
)
from tools.data.common import DataToolError


def _source() -> dict:
    strategy = StrategyName.TREND_FOLLOWING.value
    binding = next(
        item for item in current_strategy_definitions()
        if item.strategy_key == strategy
    )
    total = len(condition_sources(strategy))
    candidate = {
        "market": "KOSPI", "code": "000001", "name": "synthetic-test",
        "strategy": strategy,
        "strategy_version_id": binding.strategy_version_id,
        "strategy_definition_hash": binding.definition_hash,
        "decision_status": "READY", "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE",
        "conditions": {"passed": total, "total": total, "missing": 0, "top_missing": []},
    }
    return build_semantic_source_v2(candidate)


def _db(path: Path, *, valid: bool = True) -> Path:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE prospective_schema_meta(key TEXT PRIMARY KEY,value TEXT)")
        conn.execute(
            "INSERT INTO prospective_schema_meta(key,value) VALUES('schema_version',?)",
            (PROSPECTIVE_SCHEMA_VERSION if valid else "incorrect",),
        )
        conn.execute("CREATE TABLE prospective_capture_run(id TEXT PRIMARY KEY,status TEXT,horizon_intent TEXT)")
        conn.execute(
            "CREATE TABLE prospective_recommendation_sample("
            "capture_run_id TEXT,sample_index INTEGER,market TEXT,strategy TEXT,"
            "action TEXT,snapshot_json TEXT)"
        )
    return path


def _sample(db: Path, *, index: int, horizon: str = "SHORT",
            action: str = "ENTRY_CANDIDATE", source: dict | None = None,
            capture: str = "capture", market: str = "KOSPI", status: str = "COMPLETE",
            raw: str | None = None) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO prospective_capture_run VALUES(?,?,?)",
            (capture, status, horizon),
        )
        value = raw if raw is not None else json.dumps(
            {"semantic_source_v2": source} if source is not None else {},
            ensure_ascii=False,
        )
        conn.execute(
            "INSERT INTO prospective_recommendation_sample VALUES(?,?,?,?,?,?)",
            (capture, index, market, "synthetic-trend", action, value),
        )


def test_real_v4_semantic_source_classification_matches_existing_router() -> None:
    real_source = _source()
    category = _categorize({
        "action": "ENTRY_CANDIDATE", "horizon_intent": "SHORT",
        "snapshot": {"semantic_source_v2": real_source},
    })
    assert category in {
        "LOCAL_MATCH", "LOCAL_CONFLICT", "LOCAL_INCOMPLETE",
        "LOCAL_AMBIGUOUS", "PROVIDER_ELIGIBLE",
    }


def test_readonly_audit_is_aggregate_and_does_not_change_original_db(tmp_path: Path) -> None:
    db = _db(tmp_path / "synthetic.db")
    _sample(db, index=0, source=_source())
    _sample(db, index=1, source=None)
    _sample(db, index=2, horizon="LONG", capture="outside", source=_source())
    _sample(db, index=3, capture="broken", raw="{broken")
    _sample(db, index=4, capture="pending", status="PENDING", source=_source())
    with sqlite3.connect(db) as conn:
        before = conn.iterdump()
        snapshot = "\n".join(before)
    result = run_readiness_audit(db)
    audit = result["audit"]
    assert audit["total_samples"] == 4
    assert audit["total_captures"] == 3
    assert audit["categories"]["LEGACY_SOURCE_MISSING"] == 1
    assert audit["categories"]["UNSUPPORTED_SCOPE"] == 1
    assert audit["categories"]["INVALID_SEMANTIC_SOURCE"] == 1
    assert audit["v4_compatible"] == 1
    assert audit["external_network_requests"] == audit["provider_calls"] == audit["db_writes"] == 0
    assert set(audit["by_market_strategy"][0]) == {
        "market", "strategy", "samples", "provider_eligible", "categories",
    }
    encoded = json.dumps(result, ensure_ascii=False)
    assert "000001" not in encoded and "synthetic-test" not in encoded
    assert result["activation_readiness"]["activation_verdict"] == "HOLD"
    assert result["activation_readiness"]["can_activate_user_feature"] is False
    with sqlite3.connect(db) as conn:
        assert "\n".join(conn.iterdump()) == snapshot


def test_provider_eligible_requires_usable_wire_and_is_not_created_for_local_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.data import audit_jev_act1_readiness as module
    db = _db(tmp_path / "synthetic.db")
    _sample(db, index=0, source=_source())
    monkeypatch.setattr(
        module, "route_typesafe_state_v4",
        lambda sample: SimpleNamespace(local_status="RESIDUAL_SEMANTIC_REVIEW", provider_eligible=True),
    )
    monkeypatch.setattr(module, "project_typesafe_state_v4", lambda sample: {"valid": True})
    assert audit_stored_prospective(db)["provider_eligible"] == 1
    monkeypatch.setattr(
        module, "project_typesafe_state_v4",
        lambda sample: (_ for _ in ()).throw(TypeSafeStateProjectionError("STATE_LIMIT_EXCEEDED")),
    )
    fail_closed = audit_stored_prospective(db)
    assert fail_closed["provider_eligible"] == 0
    assert fail_closed["categories"]["INVALID_SEMANTIC_SOURCE"] == 1


def test_no_data_not_mistaken_for_provider_value(tmp_path: Path) -> None:
    db = _db(tmp_path / "empty.db")
    result = run_readiness_audit(db)
    assert result["audit"]["total_samples"] == 0
    item = next(x for x in result["activation_readiness"]["checks"] if x["code"] == "PRODUCTION_REACHABILITY")
    assert item["status"] == "HOLD"
    assert item["explanation"] == "NO_PROSPECTIVE_SAMPLES"


def test_legacy_and_unsupported_scope_are_not_counted_as_model_eligible() -> None:
    assert _categorize({"action": "ENTRY_CANDIDATE", "horizon_intent": "SHORT", "snapshot": {}}) == "LEGACY_SOURCE_MISSING"
    assert _categorize({"action": "ENTRY_CANDIDATE", "horizon_intent": "LONG", "snapshot": {}}) == "UNSUPPORTED_SCOPE"
    assert _categorize({"action": "NO_TRADE", "horizon_intent": "SHORT", "snapshot": {}}) == "UNSUPPORTED_SCOPE"
    assert _categorize({"action": "ENTRY_CANDIDATE", "horizon_intent": "SHORT", "snapshot": {"semantic_source_v2": {"bad": True}}}) == "INVALID_SEMANTIC_SOURCE"


def test_unsupported_db_fails_without_creating_tables(tmp_path: Path) -> None:
    path = _db(tmp_path / "old.db", valid=False)
    with pytest.raises(DataToolError, match="PROSPECTIVE_SCHEMA_UNSUPPORTED"):
        audit_stored_prospective(path)
    with pytest.raises(DataToolError, match="SQLite DB"):
        audit_stored_prospective(tmp_path / "no-file.db")
    assert not (tmp_path / "no-file.db").exists()


def test_frozen_canary_preflight_is_not_an_actual_provider_pass() -> None:
    artifact = load_frozen_canary_v4_protocol()
    assert artifact["status"] == "FROZEN_BEFORE_REAL_CALLS"
    result = assess_jev_act1_readiness()
    assert result["activation_verdict"] == "HOLD"
    assert result["actual_canary_executed"] is False
    assert result["can_activate_user_feature"] is False
    checks = {x["code"]: x for x in result["checks"]}
    assert checks["V4_PROTOCOL"]["status"] == "PASS"
    assert checks["V4_PLANNED_LIMITS"]["status"] == "PASS"
    assert checks["V4_ACTUAL_CANARY"]["status"] == "HOLD"
    assert checks["LIVE_PRICING_ACCOUNT_TERMS"]["status"] == "HOLD"


def test_protocol_tamper_is_a_block_and_can_never_activate() -> None:
    result = assess_jev_act1_readiness(
        audit={"total_samples": 10, "provider_eligible": 2},
        protocol_loader=lambda: (_ for _ in ()).throw(TypeSafeCanaryV4Error("CANARY_V4_PROTOCOL_DRIFT")),
    )
    assert result["activation_verdict"] == "BLOCK"
    assert result["can_activate_user_feature"] is False
    assert next(x for x in result["checks"] if x["code"] == "V4_PROTOCOL")["status"] == "BLOCK"


def test_provider_calls_are_not_performed_even_with_eligible_samples(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import socket
    def no_network(*args, **kwargs):
        raise AssertionError("network forbidden in ACT1-S1")
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "socket", no_network)
    db = _db(tmp_path / "synthetic.db")
    _sample(db, index=0, source=_source())
    result = run_readiness_audit(db)
    assert result["audit"]["provider_calls"] == 0
    assert result["activation_readiness"]["external_network_requests"] == 0
