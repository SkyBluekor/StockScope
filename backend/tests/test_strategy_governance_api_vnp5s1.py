from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.strategy_governance import router
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.data.migrate_strategy_governance_vnp5s1 import (
    migrate_strategy_governance_store,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _simulation_db(tmp_path: Path) -> Path:
    path = tmp_path / "simulation.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)"
        )
    migrate_prospective_store(path)
    migrate_strategy_governance_store(path)
    return path


def test_overview_requires_explicit_p5_migration(
    tmp_path: Path,
    monkeypatch,
):
    path = tmp_path / "unmigrated.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE placeholder(id INTEGER PRIMARY KEY)")
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(path))
    monkeypatch.setenv(
        "STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR",
        str(tmp_path / "selection"),
    )

    response = _client().get("/api/simulation/strategy-governance/overview")

    assert response.status_code == 409
    assert (
        response.json()["detail"]["code"]
        == "STRATEGY_GOVERNANCE_SCHEMA_NOT_READY"
    )


def test_overview_exposes_current_ten_and_legacy_fallback_without_writes(
    tmp_path: Path,
    monkeypatch,
):
    path = _simulation_db(tmp_path)
    runtime = tmp_path / "selection"
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(path))
    monkeypatch.setenv(
        "STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR",
        str(runtime),
    )

    response = _client().get("/api/simulation/strategy-governance/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_ready"] is True
    assert payload["registry"]["operating_count"] == 10
    assert payload["registry"]["candidate_count"] == 0
    assert (
        payload["production_policy"]["policy_id"]
        == "LEGACY_CURRENT_10_FALLBACK"
    )
    assert (
        payload["production_policy"]["policy_source"]
        == "LEGACY_CURRENT_10_FALLBACK"
    )
    assert payload["production_policy"]["operating_strategy_count"] == 10
    assert payload["production_policy"]["rollback_available"] is False
    assert payload["scanner_baseline"]["scanner_version"] == "0.21.3.8"
    assert payload["scanner_baseline"]["baseline_id"].startswith(
        "SS-SCANNER-0.21.3.8-"
    )
    assert not (runtime / "active.json").exists()


def test_registry_never_exposes_no_trade_as_strategy(
    tmp_path: Path,
    monkeypatch,
):
    path = _simulation_db(tmp_path)
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(path))
    monkeypatch.setenv(
        "STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR",
        str(tmp_path / "selection"),
    )

    response = _client().get("/api/simulation/strategy-governance/registry")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 10
    assert "no_trade" not in {row["strategy_key"] for row in rows}


def test_production_approval_endpoint_preserves_q7_block(
    tmp_path: Path,
    monkeypatch,
):
    path = _simulation_db(tmp_path)
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(path))
    monkeypatch.setenv(
        "STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR",
        str(tmp_path / "selection"),
    )

    response = _client().post(
        "/api/simulation/strategy-governance/proposals/anything/approve",
        json={"approved_by": "LOCAL_USER"},
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]["code"]
        == "Q7_APPROVAL_PROTOCOL_UNAPPROVED"
    )


def test_activation_contract_rejects_arbitrary_strategy_list(
    tmp_path: Path,
    monkeypatch,
):
    path = _simulation_db(tmp_path)
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(path))
    monkeypatch.setenv(
        "STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR",
        str(tmp_path / "selection"),
    )

    response = _client().post(
        "/api/simulation/strategy-governance/production-policy/activate",
        json={
            "approval_artifact_id": "approval-1",
            "expected_active_policy_id": None,
            "strategies": ["breakout"],
        },
    )

    assert response.status_code == 422


def test_activation_cannot_skip_immutable_approval(
    tmp_path: Path,
    monkeypatch,
):
    path = _simulation_db(tmp_path)
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(path))
    monkeypatch.setenv(
        "STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR",
        str(tmp_path / "selection"),
    )

    response = _client().post(
        "/api/simulation/strategy-governance/production-policy/activate",
        json={
            "approval_artifact_id": "missing-approval",
            "expected_active_policy_id": None,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "APPROVAL_ARTIFACT_NOT_AVAILABLE"


def test_rollback_requires_existing_active_reference(
    tmp_path: Path,
    monkeypatch,
):
    path = _simulation_db(tmp_path)
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(path))
    monkeypatch.setenv(
        "STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR",
        str(tmp_path / "selection"),
    )

    response = _client().post(
        "/api/simulation/strategy-governance/production-policy/rollback",
        json={"expected_active_policy_id": "anything"},
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]["code"]
        == "ACTIVE_REFERENCE_NOT_AVAILABLE"
    )
