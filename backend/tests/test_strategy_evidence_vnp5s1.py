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
from app.simulation.strategy_evidence import (
    SOURCE_FEEDBACK_REPORT,
    SOURCE_PROSPECTIVE_REPORT,
    STRATEGY_EVALUATION_ARTIFACT_VERSION,
    StrategyEvidenceError,
    StrategyEvidenceService,
)
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.data.migrate_strategy_governance_vnp5s1 import (
    migrate_strategy_governance_store,
)


NOW = "2026-09-28T00:00:00+00:00"


class _FakeFeedbackService:
    def __init__(self, report: dict):
        self.report = report

    def get_report(self, report_id: str) -> dict:
        if report_id != self.report["id"]:
            raise RuntimeError("not found")
        return self.report


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "simulation.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)"
        )
    migrate_prospective_store(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE feedback_report(
                id TEXT PRIMARY KEY
            )
            """
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
    report_id: str = "pros-report-1",
    strategy: str = "breakout",
    run_status: str = "COMPLETED",
    promotion_allowed: bool = False,
) -> None:
    protocol_id = f"{report_id}-protocol"
    run_id = f"{report_id}-run"
    spec = {
        "name": "P5-S1 evidence fixture",
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
        "maturity_counts": {"MATURE": 8, "IMMATURE": 2, "EXCLUDED": 2},
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
                "execution_status": {"CLOSED": 7, "CENSORED": 3},
            }
        ],
        "virtual_execution": {
            "censored_is_realized_return": False,
        },
        "minimum_sample_policy_defined": False,
        "performance_conclusion_allowed": False,
        "strategy_promotion_allowed": promotion_allowed,
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
                "P5 evidence fixture",
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
                run_status,
                NOW,
                NOW,
                NOW if run_status == "COMPLETED" else None,
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


def _feedback_report(
    *,
    report_id: str = "feedback-report-1",
    strategy: str = "breakout",
    source_status: str = "MATCH",
) -> dict:
    source_invalid = source_status != "MATCH"
    summary = {
        "counts": {
            "included_count": 10,
            "excluded_count": 2,
            "comparison_group_count": 2,
            "metric_sample_count": 8,
        },
        "source_types": {"VALIDATION": 6, "EXECUTION": 6},
        "maturity": {"MATURE": 8, "CENSORED": 2},
        "exclusion_reasons": {"UNSPECIFIED": 2},
        "comparison": {
            "groups": [
                {
                    "comparison_key": "group-a",
                    "comparison_dimensions": {
                        "strategy": strategy,
                        "market": "KOSPI",
                        "metric_definition": "RETURN_20D",
                    },
                    "metric_sample_count": 5,
                    "metrics": {
                        "return_20d": {
                            "sample_count": 5,
                            "average_pct": 2.0,
                            "median_pct": 1.5,
                        }
                    },
                },
                {
                    "comparison_key": "group-b",
                    "comparison_dimensions": {
                        "strategy": strategy,
                        "market": "KOSDAQ",
                        "metric_definition": "RETURN_20D",
                    },
                    "metric_sample_count": 3,
                    "metrics": {
                        "return_20d": {
                            "sample_count": 3,
                            "average_pct": 4.0,
                            "median_pct": 3.0,
                        }
                    },
                },
            ],
            "cross_group_aggregation_allowed": False,
            "different_comparison_keys_are_not_merged": True,
        },
        "evidence_state": "SAMPLE_SIZE_POLICY_UNDEFINED",
        "minimum_sample_policy_defined": False,
        "performance_conclusion_allowed": False,
        "notes": [
            "Tracking 관찰, 가상 Execution, Backtest 결과는 계산 정의가 다르면 합산하지 않습니다."
        ],
    }
    return {
        "id": report_id,
        "cohort_id": "cohort-1",
        "report_version": "VN_P2_S1_REPORT_V1",
        "report_sequence": 1,
        "source_set_hash": "feedback-source-hash",
        "status": "READY",
        "summary": summary,
        "source_verification_current": {
            "status": source_status,
            "counts": {"MATCH": 2} if not source_invalid else {"SOURCE_CHANGED": 1},
            "sources": (
                [
                    {
                        "source_ref_id": "src-1",
                        "state": "MATCH",
                    },
                    {
                        "source_ref_id": "src-2",
                        "state": "MATCH",
                    },
                ]
                if not source_invalid
                else [
                    {
                        "source_ref_id": "src-1",
                        "state": "SOURCE_CHANGED",
                    }
                ]
            ),
        },
        "effective_status": "READY" if not source_invalid else "SOURCE_INVALID",
        "source_changed_or_missing": source_invalid,
    }


def test_prospective_report_creates_idempotent_immutable_artifact(tmp_path: Path):
    path = _db(tmp_path)
    version_id = _strategy_version(path, "breakout")
    _seed_prospective_report(path)
    service = StrategyEvidenceService(path, clock=lambda: NOW)

    before = None
    with sqlite3.connect(path) as conn:
        before = conn.execute(
            """
            SELECT operational_status,validation_status
            FROM strategy_registry_version
            WHERE strategy_version_id=?
            """,
            (version_id,),
        ).fetchone()

    first = service.create_from_prospective(
        strategy_version_id=version_id,
        report_id="pros-report-1",
    )
    second = service.create_from_prospective(
        strategy_version_id=version_id,
        report_id="pros-report-1",
    )

    assert first == second
    assert first["source_kind"] == SOURCE_PROSPECTIVE_REPORT
    assert first["artifact_version"] == STRATEGY_EVALUATION_ARTIFACT_VERSION
    assert first["strategy_key"] == "breakout"
    assert first["evidence_state"] == "SAMPLE_SIZE_POLICY_UNDEFINED"
    assert first["limitations"]["minimum_sample_policy_defined"] is False
    assert first["limitations"]["performance_conclusion_allowed"] is False
    assert first["limitations"]["strategy_promotion_allowed"] is False
    assert first["limitations"]["adaptive_rotation_enabled"] is False
    assert first["limitations"]["censored_is_realized_return"] is False

    checked = service.get_artifact(first["id"])
    assert checked["artifact_integrity"] == "MATCH"
    assert checked["current_source_status"] == "CURRENT"

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
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE strategy_evaluation_artifact
                SET evidence_state='VALIDATED'
                WHERE id=?
                """,
                (first["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "DELETE FROM strategy_evaluation_artifact WHERE id=?",
                (first["id"],),
            )


def test_prospective_requires_completed_run_and_strategy_breakdown(tmp_path: Path):
    path = _db(tmp_path)
    version_id = _strategy_version(path, "breakout")
    service = StrategyEvidenceService(path, clock=lambda: NOW)

    _seed_prospective_report(
        path,
        report_id="running-report",
        run_status="RUNNING",
    )
    with pytest.raises(StrategyEvidenceError) as running:
        service.create_from_prospective(
            strategy_version_id=version_id,
            report_id="running-report",
        )
    assert running.value.code == "PROSPECTIVE_RUN_NOT_COMPLETED"

    _seed_prospective_report(
        path,
        report_id="pullback-report",
        strategy="pullback",
    )
    with pytest.raises(StrategyEvidenceError) as missing:
        service.create_from_prospective(
            strategy_version_id=version_id,
            report_id="pullback-report",
        )
    assert missing.value.code == "PROSPECTIVE_STRATEGY_EVIDENCE_MISSING"


def test_prospective_cannot_turn_p2_report_into_promotion_permission(tmp_path: Path):
    path = _db(tmp_path)
    version_id = _strategy_version(path, "breakout")
    _seed_prospective_report(
        path,
        report_id="promotion-report",
        promotion_allowed=True,
    )
    service = StrategyEvidenceService(path)

    with pytest.raises(StrategyEvidenceError) as exc:
        service.create_from_prospective(
            strategy_version_id=version_id,
            report_id="promotion-report",
        )
    assert exc.value.code == "PROSPECTIVE_PROMOTION_GUARD_VIOLATION"

    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM strategy_evaluation_artifact"
        ).fetchone()[0] == 0


def test_feedback_keeps_comparison_groups_separate_and_blocks_stale_source(
    tmp_path: Path,
):
    path = _db(tmp_path)
    version_id = _strategy_version(path, "breakout")
    report = _feedback_report()
    service = StrategyEvidenceService(
        path,
        feedback_service=_FakeFeedbackService(report),
        clock=lambda: NOW,
    )

    artifact = service.create_from_feedback(
        strategy_version_id=version_id,
        report_id=report["id"],
    )

    assert artifact["source_kind"] == SOURCE_FEEDBACK_REPORT
    assert len(artifact["evidence"]["comparison_groups"]) == 2
    assert (
        artifact["limitations"]["cross_group_aggregation_allowed"]
        is False
    )
    assert (
        artifact["limitations"]["different_comparison_keys_are_not_merged"]
        is True
    )
    assert artifact["limitations"]["performance_conclusion_allowed"] is False

    checked = service.get_artifact(artifact["id"])
    assert checked["current_source_status"] == "CURRENT"

    stale = _feedback_report(source_status="SOURCE_INVALID")
    stale_service = StrategyEvidenceService(
        path,
        feedback_service=_FakeFeedbackService(stale),
    )
    with pytest.raises(StrategyEvidenceError) as exc:
        stale_service.create_from_feedback(
            strategy_version_id=version_id,
            report_id=stale["id"],
        )
    assert exc.value.code == "FEEDBACK_SOURCE_INVALID"


def test_deleted_prospective_source_is_reported_missing_without_mutating_artifact(
    tmp_path: Path,
):
    path = _db(tmp_path)
    version_id = _strategy_version(path, "breakout")
    _seed_prospective_report(path)
    service = StrategyEvidenceService(path, clock=lambda: NOW)
    artifact = service.create_from_prospective(
        strategy_version_id=version_id,
        report_id="pros-report-1",
    )

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            DELETE FROM prospective_evaluation_report
            WHERE id='pros-report-1'
            """
        )
        conn.commit()

    checked = service.get_artifact(artifact["id"])
    assert checked["artifact_integrity"] == "MATCH"
    assert checked["current_source_status"] == "SOURCE_MISSING"


def test_unknown_strategy_version_is_blocked(tmp_path: Path):
    path = _db(tmp_path)
    _seed_prospective_report(path)
    service = StrategyEvidenceService(path)

    with pytest.raises(StrategyEvidenceError) as exc:
        service.create_from_prospective(
            strategy_version_id="missing-version",
            report_id="pros-report-1",
        )
    assert exc.value.code == "STRATEGY_VERSION_NOT_FOUND"
