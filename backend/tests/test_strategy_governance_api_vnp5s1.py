from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.api.strategy_governance import router
from app.simulation.strategy_governance_query import StrategyGovernanceQueryService
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


def test_production_status_uses_same_baseline_aware_pin_as_scanner(
    tmp_path: Path,
    monkeypatch,
):
    class FakeRegistry:
        def __init__(self, **_kwargs):
            pass

        def resolve_active_selection_policy(self):
            return SimpleNamespace(
                active_reference_valid=True,
                policy_hash_valid=True,
            )

        def pin_active_selection_policy(self):
            return SimpleNamespace(
                policy_id="LEGACY_CURRENT_10_FALLBACK",
                policy_hash="legacy-hash",
                policy_contract_version="VN_P5_S1_SELECTION_POLICY_V1",
                policy_source="LEGACY_CURRENT_10_FALLBACK",
                fallback_used=True,
                fallback_reason="ACTIVE_POLICY_BASELINE_MISMATCH",
                operating_strategies=(
                    (None, "trend_following", None),
                    (None, "pullback", None),
                ),
            )

        def _load_reference(self):
            return (
                {
                    "active_policy_id": "ACTIVE-OLD-BASELINE",
                    "active_policy_hash": "active-hash",
                    "rollback_policy_id": None,
                    "rollback_policy_hash": None,
                    "generation": 3,
                    "activation_source": "EXPLICIT_APPROVAL",
                },
                None,
            )

    monkeypatch.setattr(
        "app.simulation.strategy_governance_query.ProductionStrategySelectionRegistry",
        FakeRegistry,
    )

    status = StrategyGovernanceQueryService(
        tmp_path / "simulation.db",
        runtime_dir=tmp_path / "selection",
    ).production_policy()

    assert status["policy_id"] == "LEGACY_CURRENT_10_FALLBACK"
    assert status["policy_source"] == "LEGACY_CURRENT_10_FALLBACK"
    assert status["fallback_used"] is True
    assert status["fallback_reason"] == "ACTIVE_POLICY_BASELINE_MISMATCH"
    assert status["operating_strategy_count"] == 2
    assert status["generation"] == 3


def test_evidence_eligibility_endpoint_exposes_exact_source_identity(monkeypatch):
    payload = {
        "source_kind": "PROSPECTIVE_REPORT",
        "source_report_id": "report-1",
        "source_status": "CURRENT",
        "report_version": "VN_P2_S2_REPORT_V1",
        "evidence_state": "SAMPLE_SIZE_POLICY_UNDEFINED",
        "restrictions": {
            "minimum_sample_policy_defined": False,
            "performance_conclusion_allowed": False,
            "strategy_promotion_allowed": False,
            "adaptive_rotation_enabled": False,
        },
        "strategies": [
            {
                "strategy_key": "breakout",
                "sample_count": 10,
                "mature_count": 8,
                "evidence_state": "SAMPLE_SIZE_POLICY_UNDEFINED",
                "identity_status": "EXACT",
                "block_reason": None,
                "creation_allowed": True,
                "strategy_version_id": "strategy-v1",
                "definition_hash": "a" * 64,
                "observed_sample_count": 10,
                "existing_artifact_id": None,
            }
        ],
    }
    monkeypatch.setattr(
        "app.api.strategy_governance._query_service",
        lambda: SimpleNamespace(
            evidence_eligibility=lambda **_kwargs: payload
        ),
    )

    response = _client().get(
        "/api/simulation/strategy-governance/evidence/eligibility",
        params={
            "source_kind": "PROSPECTIVE_REPORT",
            "source_report_id": "report-1",
        },
    )

    assert response.status_code == 200
    assert response.json() == payload


def test_evidence_create_endpoint_is_explicit_and_does_not_accept_feedback(monkeypatch):
    created = {
        "id": "artifact-1",
        "strategy_version_id": "strategy-v1",
        "strategy_key": "breakout",
        "evidence_state": "SAMPLE_SIZE_POLICY_UNDEFINED",
        "artifact_hash": "b" * 64,
        "created_at": "2026-09-29T00:00:00+00:00",
    }
    calls = []
    monkeypatch.setattr(
        "app.api.strategy_governance._evidence_service",
        lambda: SimpleNamespace(
            create_from_prospective=lambda **kwargs: (
                calls.append(kwargs) or created
            )
        ),
    )

    response = _client().post(
        "/api/simulation/strategy-governance/evidence",
        json={
            "source_kind": "PROSPECTIVE_REPORT",
            "source_report_id": "report-1",
            "strategy_version_id": "strategy-v1",
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == "artifact-1"
    assert calls == [
        {
            "strategy_version_id": "strategy-v1",
            "report_id": "report-1",
        }
    ]

    blocked = _client().post(
        "/api/simulation/strategy-governance/evidence",
        json={
            "source_kind": "FEEDBACK_REPORT",
            "source_report_id": "feedback-1",
            "strategy_version_id": "strategy-v1",
        },
    )
    assert blocked.status_code == 409
    assert (
        blocked.json()["detail"]["code"]
        == "STRATEGY_EVIDENCE_SOURCE_NOT_ENABLED"
    )
