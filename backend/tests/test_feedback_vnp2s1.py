from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from app.feedback import EvidenceSelector, FeedbackCatalogError, FeedbackEvidenceAdapter, FeedbackService
from app.simulation.execution_catalog import HistoricalExecutionCatalog
from app.simulation.validation_catalog import HistoricalValidationCatalog
from app.tracking.store import RecommendationTrackingRepository, canonical_snapshot, snapshot_digest
from tools.data.common import DataToolError
from tools.data.migrate_feedback_vnp2s1 import migrate_feedback_store


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tracking_fixture(path: Path) -> Path:
    repo = RecommendationTrackingRepository(path)
    repo.initialize()
    scanner_snapshot = {
        "code": "005930",
        "market": "KOSPI",
        "action": "ENTRY_CANDIDATE",
    }
    manual_snapshot = {
        "kind": "MANUAL_TRACKING",
        "instrument": {"ticker": "000660", "market": "KOSPI"},
    }
    with repo.connect() as conn:
        conn.execute(
            """
            INSERT INTO tracked_recommendation(
                id,ticker,name,market,source,recommendation_date,reference_price,
                scanner_version,scanner_baseline,strategy,decision_status,rank,
                entry_price,stop_price,target1_price,target2_price,
                snapshot_json,snapshot_schema_version,snapshot_hash,
                has_scanner_source,has_manual_source,
                scanner_snapshot_json,scanner_snapshot_hash,scanner_attached_at,
                status,created_at,closed_at,closed_market_date,close_performance_status
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "track-scanner","005930","삼성전자","KOSPI","SCANNER","2026-09-01","70000",
                "0.21.3.7","BASELINE_A","pullback","READY",1,
                "70000","66500","73500","77000",
                canonical_snapshot(scanner_snapshot),1,snapshot_digest(scanner_snapshot),
                1,0,canonical_snapshot(scanner_snapshot),snapshot_digest(scanner_snapshot),
                "2026-09-01T08:00:00+00:00",
                "ACTIVE","2026-09-01T08:00:00+00:00",None,None,None,
            ),
        )
        conn.execute(
            """
            INSERT INTO recommendation_performance(
                recommendation_id,market_date,latest_date,latest_close,price_status,
                trading_days,current_return_pct,mfe_pct,mae_pct,
                highest_price,highest_date,lowest_price,lowest_date,
                return_5d,return_10d,return_20d,
                entry_touched,entry_touch_date,stop_touched,stop_touch_date,
                target1_touched,target1_touch_date,target2_touched,target2_touch_date,
                updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "track-scanner","2026-09-01","2026-09-25","73500","READY",
                20,"5.0","8.0","-3.0",
                "75600","2026-09-18","67900","2026-09-04",
                "2.0","4.0","5.0",
                1,"2026-09-02",0,None,1,"2026-09-18",0,None,
                "2026-09-25T08:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO tracked_recommendation(
                id,ticker,name,market,source,recommendation_date,reference_price,
                snapshot_json,snapshot_schema_version,snapshot_hash,
                has_scanner_source,has_manual_source,status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "track-manual","000660","SK하이닉스","KOSPI","MANUAL","2026-09-01","200000",
                canonical_snapshot(manual_snapshot),1,snapshot_digest(manual_snapshot),
                0,1,"ACTIVE","2026-09-01T08:10:00+00:00",
            ),
        )
    return path


def _simulation_fixture(path: Path):
    validation = HistoricalValidationCatalog(path)
    validation.initialize()
    draft = validation.create_draft(
        name="P2-S1 source",
        market_scope="KOSPI",
        requested_period_type="custom",
        requested_start_month="2026-09",
        requested_end_month="2026-09",
        resolved_start_date="2026-09-01",
        resolved_end_date="2026-09-01",
        trading_day_count=1,
    )
    validation.save_completed_day(
        validation_id=draft.id,
        trading_date="2026-09-01",
        scanner_version=draft.scanner_version,
        market_scope="KOSPI",
        scanner_cache_hit=False,
        partial_data=False,
        input_fingerprint={"id": "p2s1"},
        market_summary=[],
        summary={"candidate_count": 1},
        methodology={"mode": "point-in-time"},
        diagnostics={"network_requests": 0},
        candidates=[
            {
                "market": "KOSPI",
                "ticker": "005930",
                "name": "삼성전자",
                "rank": 1,
                "result_bucket": "TOP",
                "strategy": "pullback",
                "decision_status": "READY",
                "snapshot": {
                    "code": "005930",
                    "market": "KOSPI",
                    "action": "ENTRY_CANDIDATE",
                },
            }
        ],
    )
    validation.mark_replay_completed(draft.id)

    execution = HistoricalExecutionCatalog(path)
    execution.initialize()
    run_a = execution.create_run(
        validation_id=draft.id,
        market_data_cutoff_date="2026-09-25",
        production_exit_policy_token="POLICY-A",
    )
    execution.save_outcome(
        execution_run_id=run_a.id,
        signal_date="2026-09-01",
        market="KOSPI",
        ticker="005930",
        outcome_status="CLOSED",
        entry_date="2026-09-02",
        entry_price=70000,
        exit_date="2026-09-15",
        exit_price=73500,
        exit_reason="TARGET_1",
        holding_days=10,
        gross_return_pct=5.0,
        net_return_pct=4.8,
        fee_pct=0.1,
        tax_pct=0.1,
        slippage_pct=0.0,
    )
    execution.mark_completed(run_a.id)

    run_b = execution.create_run(
        validation_id=draft.id,
        market_data_cutoff_date="2026-09-26",
        production_exit_policy_token="POLICY-B",
    )
    execution.save_outcome(
        execution_run_id=run_b.id,
        signal_date="2026-09-01",
        market="KOSPI",
        ticker="005930",
        outcome_status="CENSORED",
        outcome_reason="MARKET_DATA_CUTOFF",
        entry_date="2026-09-02",
        entry_price=70000,
        holding_days=18,
        fee_pct=0.1,
        tax_pct=0.1,
        slippage_pct=0.0,
        mark_date="2026-09-26",
        mark_price=72100,
        mark_return_pct=3.0,
    )
    execution.mark_completed(run_b.id)
    return draft, run_a, run_b


def test_feedback_migration_is_repeatable_without_touching_source_rows(
    tmp_path: Path,
) -> None:
    simulation_db = tmp_path / "simulation.db"
    draft, run_a, run_b = _simulation_fixture(simulation_db)

    with sqlite3.connect(simulation_db) as conn:
        before = {
            "validation_runs": conn.execute(
                "SELECT COUNT(*) FROM historical_validation_run"
            ).fetchone()[0],
            "execution_runs": conn.execute(
                "SELECT COUNT(*) FROM historical_execution_run"
            ).fetchone()[0],
            "execution_outcomes": conn.execute(
                "SELECT COUNT(*) FROM historical_execution_outcome"
            ).fetchone()[0],
        }

    first = migrate_feedback_store(simulation_db)
    second = migrate_feedback_store(simulation_db)

    assert first == second
    with sqlite3.connect(simulation_db) as conn:
        after = {
            "validation_runs": conn.execute(
                "SELECT COUNT(*) FROM historical_validation_run"
            ).fetchone()[0],
            "execution_runs": conn.execute(
                "SELECT COUNT(*) FROM historical_execution_run"
            ).fetchone()[0],
            "execution_outcomes": conn.execute(
                "SELECT COUNT(*) FROM historical_execution_outcome"
            ).fetchone()[0],
        }
        assert conn.execute(
            "SELECT COUNT(*) FROM feedback_source_ref"
        ).fetchone()[0] == 0
    assert before == after
    assert draft.id
    assert run_a.id != run_b.id


def test_feedback_migration_rolls_back_new_objects_on_incompatible_schema(
    tmp_path: Path,
) -> None:
    simulation_db = tmp_path / "simulation.db"
    _simulation_fixture(simulation_db)
    with sqlite3.connect(simulation_db) as conn:
        conn.execute(
            "CREATE TABLE feedback_source_ref(id TEXT PRIMARY KEY)"
        )

    with pytest.raises(DataToolError):
        migrate_feedback_store(simulation_db)

    with sqlite3.connect(simulation_db) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "feedback_source_ref" in names
        assert "feedback_schema_meta" not in names
        assert "feedback_cohort" not in names
        assert "feedback_report" not in names


def test_tracking_adapter_is_read_only_and_manual_only_is_excluded(tmp_path: Path) -> None:
    tracking_db = _tracking_fixture(tmp_path / "tracking.db")
    simulation_db = tmp_path / "simulation.db"
    HistoricalExecutionCatalog(simulation_db).initialize()

    before = _sha(tracking_db)
    adapter = FeedbackEvidenceAdapter(
        simulation_db=simulation_db,
        tracking_db=tracking_db,
    )
    rows = adapter.resolve(EvidenceSelector("TRACKING", "ALL"))
    after = _sha(tracking_db)

    assert before == after
    assert len(rows) == 2
    scanner = next(row for row in rows if row.source_item_id == "track-scanner")
    manual = next(row for row in rows if row.source_item_id == "track-manual")
    assert scanner.inclusion_status == "INCLUDED"
    assert scanner.maturity_status == "MATURE"
    assert scanner.metadata["reached_price_is_execution"] is False
    assert manual.inclusion_status == "EXCLUDED"
    assert manual.exclusion_reason == "MANUAL_ONLY"


def test_report_splits_incompatible_execution_policies_and_never_realizes_censored(
    tmp_path: Path,
) -> None:
    simulation_db = tmp_path / "simulation.db"
    tracking_db = _tracking_fixture(tmp_path / "tracking.db")
    _, run_a, run_b = _simulation_fixture(simulation_db)
    migrate_feedback_store(simulation_db)

    service = FeedbackService(simulation_db, tracking_db)
    cohort = service.create_cohort(
        client_request_id="cohort-1",
        name="Execution policy comparison",
        selectors=[
            EvidenceSelector("EXECUTION", run_a.id),
            EvidenceSelector("EXECUTION", run_b.id),
        ],
    )
    report = service.create_report(
        cohort_id=cohort["id"],
        client_request_id="report-1",
    )
    summary = report["summary"]

    assert summary["counts"]["comparison_group_count"] == 2
    assert summary["comparison"]["cross_group_aggregation_allowed"] is False
    assert summary["maturity"]["MATURE_REALIZED"] == 1
    assert summary["maturity"]["CENSORED"] == 1

    groups = summary["comparison"]["groups"]
    realized_samples = sum(
        group["metrics"]["realized_net_return"]["sample_count"]
        for group in groups
    )
    censored_mark_samples = sum(
        group["metrics"]["censored_mark_return"]["sample_count"]
        for group in groups
    )
    assert realized_samples == 1
    assert censored_mark_samples == 1
    assert all(group["censored_is_realized_return"] is False for group in groups)
    assert summary["performance_conclusion_allowed"] is False
    assert summary["minimum_sample_policy_defined"] is False


def test_source_deletion_invalidates_existing_report_without_rewriting_it(
    tmp_path: Path,
) -> None:
    simulation_db = tmp_path / "simulation.db"
    tracking_db = _tracking_fixture(tmp_path / "tracking.db")
    _, run_a, _ = _simulation_fixture(simulation_db)
    migrate_feedback_store(simulation_db)

    service = FeedbackService(simulation_db, tracking_db)
    cohort = service.create_cohort(
        client_request_id="cohort-delete",
        name="Deletion check",
        selectors=[EvidenceSelector("EXECUTION", run_a.id)],
    )
    created = service.create_report(
        cohort_id=cohort["id"],
        client_request_id="report-delete",
    )
    assert created["effective_status"] == "READY"

    with sqlite3.connect(simulation_db) as conn:
        conn.execute("DELETE FROM historical_execution_run WHERE id=?", (run_a.id,))

    current = service.get_report(created["id"])
    assert current["effective_status"] == "SOURCE_INVALID"
    assert current["source_changed_or_missing"] is True
    assert current["source_verification_current"]["counts"]["SOURCE_MISSING"] == 1
    assert current["summary"] == created["summary"]


def test_active_tracking_revision_change_marks_report_stale(tmp_path: Path) -> None:
    simulation_db = tmp_path / "simulation.db"
    HistoricalExecutionCatalog(simulation_db).initialize()
    tracking_db = _tracking_fixture(tmp_path / "tracking.db")
    migrate_feedback_store(simulation_db)

    service = FeedbackService(simulation_db, tracking_db)
    cohort = service.create_cohort(
        client_request_id="cohort-track",
        name="Tracking active revision",
        selectors=[EvidenceSelector("TRACKING", "ALL")],
    )
    report = service.create_report(
        cohort_id=cohort["id"],
        client_request_id="report-track",
    )
    assert report["effective_status"] == "READY"

    with sqlite3.connect(tracking_db) as conn:
        conn.execute(
            """
            UPDATE recommendation_performance
            SET current_return_pct='6.5',updated_at='2026-09-26T08:00:00+00:00'
            WHERE recommendation_id='track-scanner'
            """
        )

    current = service.get_report(report["id"])
    assert current["effective_status"] == "SOURCE_INVALID"
    assert current["source_verification_current"]["counts"]["SOURCE_CHANGED"] == 1


def test_cohort_and_report_retries_are_idempotent(tmp_path: Path) -> None:
    simulation_db = tmp_path / "simulation.db"
    tracking_db = _tracking_fixture(tmp_path / "tracking.db")
    _, run_a, _ = _simulation_fixture(simulation_db)
    migrate_feedback_store(simulation_db)
    service = FeedbackService(simulation_db, tracking_db)

    first = service.create_cohort(
        client_request_id="same-cohort",
        name="same",
        selectors=[EvidenceSelector("EXECUTION", run_a.id)],
    )
    second = service.create_cohort(
        client_request_id="same-cohort",
        name="ignored retry body",
        selectors=[EvidenceSelector("TRACKING", "ALL")],
    )
    assert first["id"] == second["id"]

    report_a = service.create_report(
        cohort_id=first["id"],
        client_request_id="same-report",
    )
    report_b = service.create_report(
        cohort_id=first["id"],
        client_request_id="same-report",
    )
    assert report_a["id"] == report_b["id"]
    assert report_a["report_sequence"] == 1


def test_catalog_requires_explicit_migration_and_does_not_create_missing_db(
    tmp_path: Path,
) -> None:
    simulation_db = tmp_path / "missing" / "simulation.db"
    service = FeedbackService(
        simulation_db,
        tmp_path / "tracking.db",
    )

    with pytest.raises(FeedbackCatalogError) as caught:
        service.catalog.list_cohorts()

    assert caught.value.code == "FEEDBACK_MIGRATION_REQUIRED"
    assert not simulation_db.exists()
    assert not simulation_db.parent.exists()
