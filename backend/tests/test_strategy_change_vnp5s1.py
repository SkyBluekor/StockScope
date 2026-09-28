from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.prospective.models import (
    PROSPECTIVE_EVALUATION_VERSION,
    PROSPECTIVE_PROTOCOL_VERSION,
    PROSPECTIVE_REPORT_VERSION,
    digest_json,
)
from app.simulation.strategy_change import (
    STRATEGY_APPROVAL_ARTIFACT_VERSION,
    STRATEGY_CHANGE_PROPOSAL_VERSION,
    StrategyChangeError,
    StrategyChangeService,
    production_blocked_approval_protocol,
    test_only_approval_protocol,
)
from app.simulation.strategy_evidence import StrategyEvidenceService
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.data.migrate_strategy_governance_vnp5s1 import (
    migrate_strategy_governance_store,
)


NOW = "2026-09-28T01:00:00+00:00"


def _baseline(
    suffix: str = "A",
) -> dict[str, str]:
    return {
        "scanner_baseline_id": f"BASELINE-{suffix}",
        "production_fingerprint": f"PROD-{suffix}",
        "production_policy_fingerprint": f"POLICY-{suffix}",
    }


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "simulation.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)"
        )
    migrate_prospective_store(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE feedback_report(id TEXT PRIMARY KEY)"
        )
    migrate_strategy_governance_store(path)
    return path


def _strategy_version(path: Path, strategy_key: str) -> str:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT strategy_version_id
            FROM strategy_registry_version
            WHERE strategy_key=?
            """,
            (strategy_key,),
        ).fetchone()
    assert row is not None
    return str(row[0])


def _seed_prospective_report(
    path: Path,
    *,
    strategy: str,
    report_id: str,
) -> None:
    protocol_id = f"{report_id}-protocol"
    run_id = f"{report_id}-run"
    spec = {
        "name": "P5-S1-C fixture",
        "market_scope": "KOSPI",
        "strategy": strategy,
        "development_start": "2026-01-01",
        "development_end": "2026-05-31",
        "holdout_start": "2026-06-01",
        "holdout_end": "2026-08-31",
        "observation_windows": [5, 10, 20],
        "purge_trading_days": 20,
        "round_trip_cost_pct": 0.0,
    }
    spec_hash = digest_json(spec)
    summary = {
        "protocol_id": protocol_id,
        "protocol_version": PROSPECTIVE_PROTOCOL_VERSION,
        "protocol_spec_hash": spec_hash,
        "protocol": spec,
        "counts": {
            "source_capture_count": 4,
            "source_sample_count": 12,
            "development_count": 6,
            "holdout_count": 4,
            "purged_count": 2,
            "mature_count": 8,
            "immature_count": 2,
            "excluded_count": 2,
            "failed_count": 0,
        },
        "split_counts": {
            "DEVELOPMENT": 6,
            "HOLDOUT": 4,
            "PURGED": 2,
        },
        "maturity_counts": {
            "MATURE": 8,
            "IMMATURE": 2,
            "EXCLUDED": 2,
        },
        "execution_counts": {"CLOSED": 7, "CENSORED": 3},
        "market_counts": {"KOSPI": 12},
        "strategy_counts": {strategy: 12},
        "strategy_breakdown": [
            {
                "strategy": strategy,
                "sample_count": 12,
                "mature_count": 8,
                "return_20d": {
                    "sample_count": 8,
                    "average_pct": 3.2,
                    "median_pct": 2.8,
                },
                "realized_net_return": {
                    "sample_count": 7,
                    "average_pct": 2.4,
                    "median_pct": 2.1,
                },
                "execution_status": {
                    "CLOSED": 7,
                    "CENSORED": 3,
                },
            }
        ],
        "virtual_execution": {
            "censored_is_realized_return": False,
        },
        "minimum_sample_policy_defined": False,
        "performance_conclusion_allowed": False,
        "strategy_promotion_allowed": False,
        "adaptive_rotation_enabled": False,
        "evidence_state": "SAMPLE_SIZE_POLICY_UNDEFINED",
        "notes": [
            "최소 표본·승격/강등 기준이 미정이므로 전략 우수 결론을 내리지 않습니다."
        ],
    }
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            INSERT INTO prospective_evaluation_protocol(
                id,client_request_id,protocol_version,name,status,
                spec_json,spec_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                protocol_id,
                f"{protocol_id}-request",
                PROSPECTIVE_PROTOCOL_VERSION,
                "P5-S1-C fixture",
                "READY",
                json.dumps(spec, sort_keys=True, separators=(",", ":")),
                spec_hash,
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO prospective_evaluation_run(
                id,protocol_id,client_request_id,evaluation_version,status,
                created_at,started_at,completed_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                protocol_id,
                f"{run_id}-request",
                PROSPECTIVE_EVALUATION_VERSION,
                "COMPLETED",
                NOW,
                NOW,
                NOW,
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO prospective_evaluation_report(
                id,evaluation_run_id,report_version,source_set_hash,
                summary_json,created_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                report_id,
                run_id,
                PROSPECTIVE_REPORT_VERSION,
                f"{report_id}-source-hash",
                json.dumps(summary, sort_keys=True, separators=(",", ":")),
                NOW,
            ),
        )


def _artifact(
    path: Path,
    *,
    strategy: str = "breakout",
    report_id: str = "breakout-report",
) -> tuple[str, str]:
    version_id = _strategy_version(path, strategy)
    _seed_prospective_report(
        path,
        strategy=strategy,
        report_id=report_id,
    )
    artifact = StrategyEvidenceService(
        path,
        clock=lambda: NOW,
    ).create_from_prospective(
        strategy_version_id=version_id,
        report_id=report_id,
    )
    return version_id, artifact["id"]


def _service(
    path: Path,
    *,
    baseline_state: dict[str, str] | None = None,
    allow_test_protocol: bool = False,
) -> StrategyChangeService:
    state = baseline_state or _baseline()
    return StrategyChangeService(
        path,
        baseline_provider=lambda: dict(state),
        clock=lambda: NOW,
        allow_test_protocol=allow_test_protocol,
    )


def _proposal(
    service: StrategyChangeService,
    *,
    version_id: str,
    artifact_id: str,
    protocol=None,
    request_id: str = "proposal-1",
    horizons=("LEGACY_UNSPECIFIED",),
):
    return service.create_proposal(
        client_request_id=request_id,
        changes=[
            {
                "strategy_version_id": version_id,
                "expected_operational_status": "OPERATING",
                "proposed_operational_status": "ON_HOLD",
            }
        ],
        evidence_artifact_ids=[artifact_id],
        affected_horizons=list(horizons),
        affected_regimes=["UNKNOWN"],
        approval_protocol=protocol,
    )


def test_default_proposal_is_review_only_and_does_not_mutate_registry(
    tmp_path: Path,
):
    path = _db(tmp_path)
    version_id, artifact_id = _artifact(path)
    service = _service(path)

    with sqlite3.connect(path) as conn:
        before = conn.execute(
            """
            SELECT operational_status,validation_status
            FROM strategy_registry_version
            WHERE strategy_version_id=?
            """,
            (version_id,),
        ).fetchone()

    first = _proposal(
        service,
        version_id=version_id,
        artifact_id=artifact_id,
    )
    second = _proposal(
        service,
        version_id=version_id,
        artifact_id=artifact_id,
    )

    assert first == second
    assert first["proposal_version"] == STRATEGY_CHANGE_PROPOSAL_VERSION
    assert first["approval_gate_state"] == "REVIEW_ONLY_Q7_UNAPPROVED"
    assert first["limitations"]["q7_protocol_approved"] is False
    assert first["candidate_policy_intent"]["risk_gate_preserved"] is True
    assert (
        first["candidate_policy_intent"][
            "no_trade_safety_path_preserved"
        ]
        is True
    )
    assert first["candidate_policy_intent"]["score_formula_changed"] is False
    assert (
        first["candidate_policy_intent"][
            "production_activation_performed"
        ]
        is False
    )
    assert service.verify_proposal(first["id"])["status"] == "CURRENT"

    with sqlite3.connect(path) as conn:
        after = conn.execute(
            """
            SELECT operational_status,validation_status
            FROM strategy_registry_version
            WHERE strategy_version_id=?
            """,
            (version_id,),
        ).fetchone()
        assert after == before
        assert conn.execute(
            "SELECT COUNT(*) FROM strategy_approval_artifact"
        ).fetchone()[0] == 0


def test_q7_unapproved_proposal_cannot_be_approved(tmp_path: Path):
    path = _db(tmp_path)
    version_id, artifact_id = _artifact(path)
    service = _service(path)
    proposal = _proposal(
        service,
        version_id=version_id,
        artifact_id=artifact_id,
    )

    with pytest.raises(StrategyChangeError) as exc:
        service.approve_proposal(proposal_id=proposal["id"])
    assert exc.value.code == "Q7_APPROVAL_PROTOCOL_UNAPPROVED"

    test_protocol = test_only_approval_protocol()
    service_with_test = _service(path, allow_test_protocol=True)
    with pytest.raises(StrategyChangeError) as changed:
        service_with_test.approve_proposal(
            proposal_id=proposal["id"],
            protocol=test_protocol,
        )
    assert (
        changed.value.code
        == "APPROVAL_PROTOCOL_CHANGED_SINCE_PROPOSAL"
    )


def test_test_only_precommitted_protocol_exercises_immutable_approval(
    tmp_path: Path,
):
    path = _db(tmp_path)
    version_id, artifact_id = _artifact(path)
    protocol = test_only_approval_protocol()
    service = _service(path, allow_test_protocol=True)

    proposal = _proposal(
        service,
        version_id=version_id,
        artifact_id=artifact_id,
        protocol=protocol,
        request_id="test-approved-proposal",
    )
    assert proposal["approval_gate_state"] == "APPROVAL_ELIGIBLE"

    approval_a = service.approve_proposal(
        proposal_id=proposal["id"],
        protocol=protocol,
        approved_by="TEST_FIXTURE",
    )
    approval_b = service.approve_proposal(
        proposal_id=proposal["id"],
        protocol=protocol,
        approved_by="TEST_FIXTURE",
    )

    assert approval_a == approval_b
    assert (
        approval_a["approval_version"]
        == STRATEGY_APPROVAL_ARTIFACT_VERSION
    )
    checked = service.get_approval(approval_a["id"])
    assert checked["approval_integrity"] == "MATCH"
    assert (
        checked["approval_context"]["research_validation_approval_only"]
        is True
    )
    assert (
        checked["approval_context"]["production_activation_performed"]
        is False
    )
    assert (
        checked["approval_context"]["automatic_rotation_enabled"]
        is False
    )

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT operational_status,validation_status
            FROM strategy_registry_version
            WHERE strategy_version_id=?
            """,
            (version_id,),
        ).fetchone()
        assert row == ("OPERATING", "UNVERIFIED")

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE strategy_change_proposal
                SET approval_gate_state='APPROVAL_ELIGIBLE'
                WHERE id=?
                """,
                (proposal["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                DELETE FROM strategy_change_proposal_evidence
                WHERE proposal_id=?
                """,
                (proposal["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE strategy_approval_artifact
                SET approved_at='2099-01-01T00:00:00+00:00'
                WHERE id=?
                """,
                (approval_a["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                DELETE FROM strategy_approval_artifact
                WHERE id=?
                """,
                (approval_a["id"],),
            )


def test_proposal_requires_current_evidence_for_every_changed_version(
    tmp_path: Path,
):
    path = _db(tmp_path)
    breakout_id, breakout_artifact = _artifact(path)
    pullback_id, _ = _artifact(
        path,
        strategy="pullback",
        report_id="pullback-report",
    )
    service = _service(path)

    with pytest.raises(StrategyChangeError) as no_evidence:
        service.create_proposal(
            client_request_id="no-evidence",
            changes=[
                {
                    "strategy_version_id": breakout_id,
                    "proposed_operational_status": "ON_HOLD",
                }
            ],
            evidence_artifact_ids=[],
            affected_horizons=["LEGACY_UNSPECIFIED"],
            affected_regimes=["UNKNOWN"],
        )
    assert no_evidence.value.code == "PROPOSAL_EVIDENCE_REQUIRED"

    with pytest.raises(StrategyChangeError) as incomplete:
        service.create_proposal(
            client_request_id="incomplete-evidence",
            changes=[
                {
                    "strategy_version_id": breakout_id,
                    "proposed_operational_status": "ON_HOLD",
                },
                {
                    "strategy_version_id": pullback_id,
                    "proposed_operational_status": "ON_HOLD",
                },
            ],
            evidence_artifact_ids=[breakout_artifact],
            affected_horizons=["LEGACY_UNSPECIFIED"],
            affected_regimes=["UNKNOWN"],
        )
    assert (
        incomplete.value.code
        == "PROPOSAL_EVIDENCE_COVERAGE_INCOMPLETE"
    )


def test_registry_change_makes_existing_proposal_stale(tmp_path: Path):
    path = _db(tmp_path)
    version_id, artifact_id = _artifact(path)
    protocol = test_only_approval_protocol()
    service = _service(path, allow_test_protocol=True)
    proposal = _proposal(
        service,
        version_id=version_id,
        artifact_id=artifact_id,
        protocol=protocol,
    )

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE strategy_registry_version
            SET validation_status='EVALUATING'
            WHERE strategy_version_id=?
            """,
            (version_id,),
        )
        conn.commit()

    verification = service.verify_proposal(proposal["id"])
    assert verification["status"] == "STALE"
    assert "REGISTRY_SNAPSHOT_CHANGED" in verification["reasons"]

    with pytest.raises(StrategyChangeError) as exc:
        service.approve_proposal(
            proposal_id=proposal["id"],
            protocol=protocol,
            approved_by="TEST_FIXTURE",
        )
    assert exc.value.code == "PROPOSAL_STALE"


def test_baseline_change_makes_existing_proposal_stale(tmp_path: Path):
    path = _db(tmp_path)
    version_id, artifact_id = _artifact(path)
    baseline_state = _baseline("A")
    protocol = test_only_approval_protocol()
    service = _service(
        path,
        baseline_state=baseline_state,
        allow_test_protocol=True,
    )
    proposal = _proposal(
        service,
        version_id=version_id,
        artifact_id=artifact_id,
        protocol=protocol,
    )

    baseline_state.update(_baseline("B"))
    verification = service.verify_proposal(proposal["id"])
    assert verification["status"] == "STALE"
    assert "PRODUCTION_BASELINE_CHANGED" in verification["reasons"]


def test_explicit_horizon_remains_blocked_even_with_test_protocol(
    tmp_path: Path,
):
    path = _db(tmp_path)
    version_id, artifact_id = _artifact(path)
    protocol = test_only_approval_protocol()
    service = _service(path, allow_test_protocol=True)

    proposal = _proposal(
        service,
        version_id=version_id,
        artifact_id=artifact_id,
        protocol=protocol,
        request_id="explicit-horizon",
        horizons=("SHORT",),
    )
    assert proposal["approval_gate_state"] == "BLOCKED_HORIZON_POLICY"

    with pytest.raises(StrategyChangeError) as exc:
        service.approve_proposal(
            proposal_id=proposal["id"],
            protocol=protocol,
            approved_by="TEST_FIXTURE",
        )
    assert exc.value.code == "PROPOSAL_NOT_APPROVAL_ELIGIBLE"


def test_proposal_and_approval_migration_is_additive_and_idempotent(
    tmp_path: Path,
):
    path = _db(tmp_path)
    result = migrate_strategy_governance_store(path)

    assert (
        result["change_proposal_version"]
        == STRATEGY_CHANGE_PROPOSAL_VERSION
    )
    assert (
        result["approval_artifact_version"]
        == STRATEGY_APPROVAL_ARTIFACT_VERSION
    )
    assert result["change_proposal_count"] == 0
    assert result["approval_artifact_count"] == 0

    with sqlite3.connect(path) as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "strategy_change_proposal" in tables
    assert "strategy_change_proposal_evidence" in tables
    assert "strategy_approval_artifact" in tables


def test_test_protocol_is_forbidden_without_explicit_test_mode(
    tmp_path: Path,
):
    path = _db(tmp_path)
    version_id, artifact_id = _artifact(path)
    protocol = test_only_approval_protocol()
    service = _service(path, allow_test_protocol=False)

    with pytest.raises(StrategyChangeError) as exc:
        _proposal(
            service,
            version_id=version_id,
            artifact_id=artifact_id,
            protocol=protocol,
        )
    assert exc.value.code == "TEST_APPROVAL_PROTOCOL_FORBIDDEN"
