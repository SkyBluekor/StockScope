from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.prospective.models import (
    PROSPECTIVE_CAPTURE_VERSION,
    PROSPECTIVE_EVALUATION_VERSION,
    PROSPECTIVE_PROTOCOL_VERSION,
    PROSPECTIVE_REPORT_VERSION,
    digest_json,
)
from app.simulation.strategy_change import (
    StrategyChangeService,
    test_only_approval_protocol as make_test_approval_protocol,
)
from app.simulation.strategy_evidence import StrategyEvidenceService
from app.strategy import MarketRegime, StrategyEngine, StrategyInput, StrategyName
from app.strategy.production_selection_policy import (
    ProductionStrategySelectionRegistry,
    SelectionPolicyError,
)
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.data.migrate_strategy_governance_vnp5s1 import (
    migrate_strategy_governance_store,
)


NOW = "2026-09-28T03:20:00+00:00"
BASELINE = {
    "scanner_baseline_id": "BASELINE-G-LIFECYCLE",
    "production_fingerprint": "PROD-G-LIFECYCLE",
    "production_policy_fingerprint": "POLICY-G-LIFECYCLE",
}


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "simulation.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)")
    migrate_prospective_store(path)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE feedback_report(id TEXT PRIMARY KEY)")
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


def _seed_report(path: Path, *, strategy: str) -> str:
    report_id = f"{strategy}-g-lifecycle-report"
    protocol_id = f"{report_id}-protocol"
    run_id = f"{report_id}-run"
    spec = {
        "name": "P5-S1-G lifecycle fixture",
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
                "sample_count": 10,
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
                "execution_status": {"CLOSED": 7, "CENSORED": 3},
            }
        ],
        "virtual_execution": {"censored_is_realized_return": False},
        "minimum_sample_policy_defined": False,
        "performance_conclusion_allowed": False,
        "strategy_promotion_allowed": False,
        "adaptive_rotation_enabled": False,
        "evidence_state": "SAMPLE_SIZE_POLICY_UNDEFINED",
        "notes": ["Synthetic G lifecycle evidence only."],
    }
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        strategy_identity = conn.execute(
            """
            SELECT strategy_version_id,definition_hash
            FROM strategy_registry_version
            WHERE strategy_key=?
            """,
            (strategy,),
        ).fetchone()
        assert strategy_identity is not None
        strategy_version_id = str(strategy_identity[0])
        strategy_definition_hash = str(strategy_identity[1])
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
                "P5-S1-G lifecycle fixture",
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
                f"{report_id}-source-set",
                json.dumps(summary, sort_keys=True, separators=(",", ":")),
                NOW,
            ),
        )

        capture_id = f"{report_id}-capture"
        conn.execute(
            """
            INSERT INTO prospective_capture_run(
                id,capture_version,source_job_id,status,request_json,
                market_scope,actual_data_date,horizon_intent,candidate_limit,
                actionable_candidate_count,returned_candidate_count,
                created_at,started_at,completed_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                capture_id,
                PROSPECTIVE_CAPTURE_VERSION,
                f"{capture_id}-job",
                "COMPLETE",
                "{}",
                "KOSPI",
                "2026-06-01",
                "MEDIUM",
                12,
                12,
                12,
                NOW,
                NOW,
                NOW,
                NOW,
            ),
        )
        for index in range(12):
            snapshot = {
                "market": "KOSPI",
                "code": f"00{index:04d}",
                "name": f"fixture-{index}",
                "strategy": strategy,
                "strategy_version_id": strategy_version_id,
                "strategy_definition_hash": strategy_definition_hash,
                "action": "ENTRY_CANDIDATE",
                "candidate_state": "READY",
            }
            snapshot_json = json.dumps(
                snapshot,
                sort_keys=True,
                separators=(",", ":"),
            )
            conn.execute(
                """
                INSERT INTO prospective_recommendation_sample(
                    capture_run_id,sample_index,market,ticker,name,rank,
                    strategy,decision_status,candidate_state,action,
                    signal_date,snapshot_json,snapshot_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    capture_id,
                    index,
                    "KOSPI",
                    f"00{index:04d}",
                    f"fixture-{index}",
                    index + 1,
                    strategy,
                    "READY",
                    "READY",
                    "ENTRY_CANDIDATE",
                    "2026-06-01",
                    snapshot_json,
                    digest_json(snapshot),
                    NOW,
                ),
            )
            split = "DEVELOPMENT" if index < 6 else "HOLDOUT" if index < 10 else "PURGED"
            maturity = "MATURE" if index < 8 else "IMMATURE" if index < 10 else "EXCLUDED"
            conn.execute(
                """
                INSERT INTO prospective_evaluation_unit(
                    evaluation_run_id,capture_run_id,sample_index,split,
                    maturity_status,signal_date,market,ticker,strategy,
                    execution_status,details_json,computed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    run_id,
                    capture_id,
                    index,
                    split,
                    maturity,
                    "2026-06-01",
                    "KOSPI",
                    f"00{index:04d}",
                    strategy,
                    "CLOSED" if index < 7 else "CENSORED",
                    "{}",
                    NOW,
                ),
            )
    return report_id


def _risk_input() -> StrategyInput:
    return StrategyInput(
        code="005930",
        market="KOSPI",
        current_price=100,
        ma20=95,
        ma60=90,
        ma120=85,
        ma20_slope_pct=2.0,
        rsi14=65,
        atr_pct=3.0,
        volume_ratio_20=2.0,
        distance_to_20d_high_pct=1.0,
        support_distance_pct=5.0,
        resistance_distance_pct=1.0,
        higher_high=True,
        higher_low=True,
        relative_strength_market_pct=3.0,
        relative_strength_sector_pct=2.0,
        market_regime=MarketRegime.TREND_UP,
        event_risk=True,
    )


def test_synthetic_evidence_to_activation_run_pin_and_rollback(tmp_path: Path):
    simulation = _db(tmp_path)
    runtime = tmp_path / "strategy_selection"
    breakout_version = _strategy_version(simulation, "breakout")
    report_id = _seed_report(simulation, strategy="breakout")

    evidence_service = StrategyEvidenceService(
        simulation,
        clock=lambda: NOW,
    )
    artifact = evidence_service.create_from_prospective(
        strategy_version_id=breakout_version,
        report_id=report_id,
    )
    checked_artifact = evidence_service.get_artifact(
        artifact["id"],
        verify_source=True,
    )
    assert checked_artifact["artifact_integrity"] == "MATCH"
    assert checked_artifact["current_source_status"] == "CURRENT"

    protocol = make_test_approval_protocol()
    change = StrategyChangeService(
        simulation,
        evidence_service=evidence_service,
        baseline_provider=lambda: dict(BASELINE),
        clock=lambda: NOW,
        allow_test_protocol=True,
    )
    proposal = change.create_proposal(
        client_request_id="g-lifecycle-proposal",
        changes=[
            {
                "strategy_version_id": breakout_version,
                "expected_operational_status": "OPERATING",
                "proposed_operational_status": "ON_HOLD",
            }
        ],
        evidence_artifact_ids=[artifact["id"]],
        affected_horizons=["LEGACY_UNSPECIFIED"],
        affected_regimes=["UNKNOWN"],
        approval_protocol=protocol,
    )
    assert proposal["approval_gate_state"] == "APPROVAL_ELIGIBLE"
    assert change.verify_proposal(proposal["id"])["status"] == "CURRENT"

    approval = change.approve_proposal(
        proposal_id=proposal["id"],
        protocol=protocol,
        approved_by="TEST_FIXTURE",
    )
    assert change.get_approval(approval["id"])["approval_integrity"] == "MATCH"

    selection = ProductionStrategySelectionRegistry(
        runtime_dir=runtime,
        simulation_db=simulation,
        change_service=change,
        allow_test_activation=True,
        clock=lambda: NOW,
        baseline_identity_provider=lambda: dict(BASELINE),
    )

    with pytest.raises(SelectionPolicyError) as stale_activation:
        selection.activate_approved_policy(
            approval_artifact_id=approval["id"],
            expected_active_policy_id="STALE-POLICY",
        )
    assert stale_activation.value.code == "ACTIVE_POLICY_CONFLICT"
    assert not (runtime / "active.json").exists()

    activated = selection.activate_approved_policy(
        approval_artifact_id=approval["id"],
        expected_active_policy_id=None,
    )
    active_id = activated["active_policy"]["policy_id"]
    assert activated["changed"] is True
    assert (runtime / "active.json").is_file()
    assert "breakout" not in {
        row["strategy_key"]
        for row in activated["active_policy"]["operating_strategies"]
    }
    assert len(activated["active_policy"]["operating_strategies"]) == 9

    run_pin = selection.pin_active_selection_policy()
    assert run_pin.policy_id == active_id
    assert run_pin.policy_source == "ACTIVE_SELECTION_POLICY"
    assert "breakout" not in run_pin.operating_strategy_keys
    assert StrategyName.NO_TRADE.value not in run_pin.operating_strategy_keys

    allowed = frozenset(
        StrategyName(key)
        for key in run_pin.operating_strategy_keys
    )
    risk_result = StrategyEngine().evaluate_all(
        _risk_input(),
        allowed_strategies=allowed,
    )
    assert risk_result[0].strategy is StrategyName.NO_TRADE
    assert all(
        item.strategy is not StrategyName.BREAKOUT
        for item in risk_result
    )

    with pytest.raises(SelectionPolicyError) as stale_rollback:
        selection.rollback_selection_policy(
            expected_active_policy_id="STALE-POLICY"
        )
    assert stale_rollback.value.code == "ACTIVE_POLICY_CONFLICT"
    assert selection.pin_active_selection_policy().policy_id == active_id

    rolled = selection.rollback_selection_policy(
        expected_active_policy_id=active_id,
    )
    rollback_id = rolled["active_policy"]["policy_id"]
    assert rolled["changed"] is True
    assert rollback_id != active_id
    assert len(rolled["active_policy"]["operating_strategies"]) == 10
    assert {
        row["strategy_key"]
        for row in rolled["active_policy"]["operating_strategies"]
    } == {
        item.value
        for item in StrategyName
        if item is not StrategyName.NO_TRADE
    }

    fresh_pin = selection.pin_active_selection_policy()
    assert fresh_pin.policy_id == rollback_id
    assert "breakout" in fresh_pin.operating_strategy_keys

    # A pin is immutable run identity: changing active state later does not
    # rewrite the pin already handed to a started Scanner/analysis run.
    assert run_pin.policy_id == active_id
    assert "breakout" not in run_pin.operating_strategy_keys

    with pytest.raises(SelectionPolicyError) as second_rollback:
        selection.rollback_selection_policy(
            expected_active_policy_id=rollback_id,
        )
    assert second_rollback.value.code == "ROLLBACK_POLICY_NOT_AVAILABLE"

    with sqlite3.connect(simulation) as conn:
        row = conn.execute(
            """
            SELECT operational_status,validation_status
            FROM strategy_registry_version
            WHERE strategy_version_id=?
            """,
            (breakout_version,),
        ).fetchone()
    assert row == ("OPERATING", "UNVERIFIED")
