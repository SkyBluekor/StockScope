from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.management import HoldingManagementService
from app.holdings.recovery import HoldingRecoveryService
from app.quotes.models import QuoteSnapshot
from app.watch import WatchPolicy, WatchService, load_active_plan_watch_demands
from app.feedback import FeedbackCatalog, FeedbackEvidence
from app.prospective import (
    EvaluationProtocolSpec,
    ProspectiveCaptureRequest,
    ProspectiveCatalog,
)
from app.simulation.execution_catalog import HistoricalExecutionCatalog
from app.simulation.sim1_store import SimulationRepository
from app.simulation.validation_catalog import HistoricalValidationCatalog
from app.tracking.store import RecommendationTrackingRepository
from tools.data import backup_runtime as backup_module
from tools.data.backup_runtime import create_backup
from tools.data.bootstrap_runtime import bootstrap_runtime
from tools.data.common import (
    DataToolError,
    holdings_counts,
    sha256_file,
)
from tools.data.doctor import collect_report
from tools.data import restore_runtime as restore_module
from tools.data.restore_runtime import restore_backup
from tools.data.migrate_feedback_vnp2s1 import migrate_feedback_store
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.data.migrate_holdings_decision_vnp3s1 import (
    HOLDING_DECISION_POLICY_VERSION,
    HOLDING_PLAN_CONTEXT_VERSION,
    migrate_holdings_decision_store,
)
from tools.data.migrate_holdings_recovery_vnp3s2 import (
    RECOVERY_SCHEMA_VERSION,
    migrate_holdings_recovery_store,
)
from tools.data.migrate_watch_vnp4s1 import migrate_watch_store
from app.watch.policy import WATCH_POLICY_CONTRACT_VERSION
from app.watch.storage import WATCH_SCHEMA_VERSION
from app.strategy import StrategyName
from app.strategy.production_selection_policy import (
    ProductionStrategySelectionRegistry,
)
from tools.data.migrate_strategy_governance_vnp5s1 import (
    migrate_strategy_governance_store,
)


T0 = "2026-09-24T09:00:00+09:00"
T1 = "2026-09-24T10:00:00+09:00"


def _holdings_db(path: Path) -> Path:
    catalog = HoldingsCatalog(path)
    catalog.initialize()
    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동 기록",
    )
    opened = PositionLifecycleService(catalog).register_initial_holding(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        position_account_id=account.id,
        quantity="10",
        average_price="100",
        effective_at=T0,
    )
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=opened.stock_id,
        market_date="2026-09-24",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="data1-fixture",
        strategy_key="trend_following",
        action_state="READY",
        risk_state="READY",
        reference_price="100",
        stop_price="90",
        target1_price="120",
        target2_price="130",
        scanner_version="test",
        analysis_engine_version="test",
        policy_version="test",
        source_versions={},
        snapshot={},
        computed_at="2026-09-24T00:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )
    HoldingManagementService(catalog).apply_analysis_plan(
        position_id=opened.position.id,
        analysis_revision_id=revision.id,
        applied_at=T1,
    )
    return path


def _market_db(path: Path, rows: int = 70) -> Path:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE stock_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,stock_code)
            );
            CREATE TABLE main_index_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd)
            );
            CREATE TABLE day_status(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,kind)
            );
            """
        )
        cursor = date(2026, 6, 1)
        dates = []
        while len(dates) < rows:
            if cursor.weekday() < 5:
                dates.append(cursor.strftime("%Y%m%d"))
            cursor += timedelta(days=1)
        for bas_dd in dates:
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "005930", "{}"),
            )
            conn.execute(
                "INSERT INTO main_index_daily VALUES(?,?,?)",
                ("KOSPI", bas_dd, "{}"),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "stock", "data"),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "index", "data"),
            )
    return path


def _simulation_db(path: Path) -> Path:
    SimulationRepository(path).initialize()
    HistoricalValidationCatalog(path).initialize()
    return path


def _tracking_db(path: Path) -> Path:
    RecommendationTrackingRepository(path).initialize()
    return path


def test_default_backup_excludes_market_and_secrets(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    market = _market_db(tmp_path / "market.db")
    backup = create_backup(
        destination=tmp_path / "backup",
        include_market=False,
        holdings_db=holdings,
        market_db=market,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    assert (backup / "holdings.db").is_file()
    assert not (backup / "market_history.db").exists()
    assert manifest["contents"]["market_history_db"] is False
    assert manifest["secret_files_included"] == []
    assert not any(path.name == ".env" for path in backup.rglob("*"))


def test_backup_falls_back_when_windows_blocks_directory_rename(
    tmp_path,
    monkeypatch,
):
    holdings = _holdings_db(tmp_path / "holdings.db")
    destination = tmp_path / "backup"

    real_replace = backup_module.os.replace

    def blocked_directory_replace(src, dst):
        src_path = Path(src)
        dst_path = Path(dst)
        if (
            src_path.name.startswith(".backup.")
            and dst_path == destination
        ):
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(
        backup_module.os,
        "replace",
        blocked_directory_replace,
    )

    backup = create_backup(
        destination=destination,
        holdings_db=holdings,
    )

    assert backup == destination
    assert (backup / "holdings.db").is_file()
    assert (backup / "backup_manifest.json").is_file()
    assert not any(
        path.name.startswith(".backup.")
        for path in tmp_path.iterdir()
    )


def test_full_backup_includes_market_and_plan_counts(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    market = _market_db(tmp_path / "market.db")
    backup = create_backup(
        destination=tmp_path / "full",
        include_market=True,
        holdings_db=holdings,
        market_db=market,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    assert (backup / "market_history.db").is_file()
    assert manifest["contents"]["market_history_db"] is True
    assert manifest["counts"]["holding_management_plan"] == 1
    assert manifest["counts"]["holding_position_event"] >= 1


def test_backup_and_restore_include_existing_simulation_and_tracking(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    simulation = _simulation_db(tmp_path / "simulation.db")
    tracking = _tracking_db(tmp_path / "tracking.db")

    backup = create_backup(
        destination=tmp_path / "runtime-backup",
        holdings_db=holdings,
        simulation_db=simulation,
        tracking_db=tracking,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["contents"]["simulation_db"] is True
    assert manifest["contents"]["tracking_db"] is True
    assert (backup / "simulation.db").is_file()
    assert (backup / "recommendation_tracking.db").is_file()

    target_holdings = tmp_path / "restored-holdings.db"
    target_simulation = tmp_path / "restored-simulation.db"
    target_tracking = tmp_path / "restored-tracking.db"
    result = restore_backup(
        backup,
        restore_simulation=True,
        restore_tracking=True,
        target_holdings=target_holdings,
        target_simulation=target_simulation,
        target_tracking=target_tracking,
    )

    assert target_holdings.is_file()
    assert target_simulation.is_file()
    assert target_tracking.is_file()
    assert result["simulation_db"] == str(target_simulation)
    assert result["tracking_db"] == str(target_tracking)


def test_feedback_store_roundtrip_is_declared_and_restored(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    simulation = _simulation_db(tmp_path / "simulation.db")
    HistoricalExecutionCatalog(simulation).initialize()
    migrate_feedback_store(simulation)

    catalog = FeedbackCatalog(simulation)
    evidence = FeedbackEvidence(
        source_type="EXECUTION",
        source_owner="SIMULATION_DB",
        source_id="run-fixture",
        source_item_id="2026-09-01|KOSPI|005930",
        source_hash="source-hash-fixture",
        durability="DURABLE",
        origin_kind="VIRTUAL_EXECUTION",
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        signal_date="2026-09-01",
        strategy="pullback",
        decision_status="READY",
        scanner_version="0.21.3.7",
        scanner_baseline="BASELINE_A",
        horizon_intent="LEGACY_UNSPECIFIED",
        horizon_policy_version=None,
        metric_definition="VAL2_VIRTUAL_EXECUTION_V1",
        execution_policy_version="EXECUTION_V1",
        exit_policy_token="POLICY-A",
        fee_pct=0.1,
        tax_pct=0.1,
        slippage_pct=0.0,
        maturity_status="MATURE_REALIZED",
        inclusion_status="INCLUDED",
        exclusion_reason=None,
        available_trading_days=10,
        metrics={"net_return_pct": 4.8},
        source_observed_at="2026-09-25T00:00:00+00:00",
        metadata={
            "selection_method": "HISTORICAL_EXECUTION_VALIDATION",
            "evaluation_window": "ENTRY_TO_EXIT_OR_CUTOFF",
        },
    )
    cohort = catalog.create_cohort(
        client_request_id="backup-cohort",
        name="backup fixture",
        filters={"purpose": "backup-test"},
        selector_results=[
            {
                "source_type": "EXECUTION",
                "source_id": "run-fixture",
                "selector": {"source_type": "EXECUTION", "source_id": "run-fixture"},
                "status": "READY",
                "evidence_count": 1,
            }
        ],
        evidence=[evidence],
        created_at="2026-09-27T00:00:00+00:00",
    )
    catalog.create_report(
        cohort_id=cohort["id"],
        client_request_id="backup-report",
        summary={"evidence_state": "SAMPLE_SIZE_POLICY_UNDEFINED"},
        source_set_hash=catalog.source_set_hash(cohort["id"]),
        status="READY",
        created_at="2026-09-27T00:01:00+00:00",
    )

    backup = create_backup(
        destination=tmp_path / "feedback-backup",
        holdings_db=holdings,
        simulation_db=simulation,
        include_tracking=False,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    feedback_manifest = manifest["extensions"]["feedback_v1"]
    assert feedback_manifest["present"] is True
    assert feedback_manifest["restorable"] is True
    assert set(feedback_manifest["tables"]) == {
        "feedback_schema_meta",
        "feedback_source_ref",
        "feedback_cohort",
        "feedback_cohort_source",
        "feedback_cohort_member",
        "feedback_report",
    }

    restored_holdings = tmp_path / "restored-holdings.db"
    restored_simulation = tmp_path / "restored-simulation.db"
    result = restore_backup(
        backup,
        restore_simulation=True,
        target_holdings=restored_holdings,
        target_simulation=restored_simulation,
    )

    assert result["feedback"]["store_present_in_backup"] is True
    assert result["feedback"]["store_restored"] is True
    with sqlite3.connect(restored_simulation) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM feedback_source_ref"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM feedback_cohort"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM feedback_report"
        ).fetchone()[0] == 1


def test_prospective_store_roundtrip_is_declared_and_restored(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    simulation = _simulation_db(tmp_path / "simulation.db")
    migrate_prospective_store(simulation)
    catalog = ProspectiveCatalog(simulation)

    request = ProspectiveCaptureRequest(
        market_scope="ALL",
        requested_as_of="2026-09-23",
        candidate_limit=5,
        horizon_intent="LEGACY_UNSPECIFIED",
        horizon_policy_version="VN_P1_S2_HORIZON_CONTEXT_V1",
    )
    catalog.begin_capture(
        source_job_id="backup-scanner-job",
        request=request,
        created_at="2026-09-27T00:00:00+00:00",
    )
    capture = catalog.finalize_capture(
        source_job_id="backup-scanner-job",
        request=request,
        result={
            "version": "0.21.3.7",
            "requested_as_of": "2026-09-23",
            "market_scope": "ALL",
            "data_dates": {"KOSPI": "2026-09-23"},
            "input_fingerprint": "backup-input",
            "partial_data": False,
            "summary": {"candidate_count": 1, "shown_count": 1},
            "candidates": [{
                "market": "KOSPI",
                "code": "005930",
                "name": "삼성전자",
                "rank": 1,
                "strategy": "pullback",
                "decision_status": "WATCH",
                "candidate_state": "WATCH",
                "action": "WAIT",
            }],
            "more_candidates": [],
        },
        completed_at="2026-09-27T00:01:00+00:00",
    )
    protocol = catalog.create_protocol(
        client_request_id="backup-protocol",
        spec=EvaluationProtocolSpec(
            name="backup fixture",
            market_scope="ALL",
            strategy=None,
            development_start="2026-01-01",
            development_end="2026-03-31",
            holdout_start="2026-05-01",
            holdout_end="2026-07-31",
            execution_mode="OBSERVATION_ONLY",
            exit_policy_token=None,
        ),
        created_at="2026-09-27T00:02:00+00:00",
    )
    run = catalog.create_evaluation_run(
        protocol_id=protocol["id"],
        client_request_id="backup-evaluation",
        created_at="2026-09-27T00:03:00+00:00",
    )
    catalog.begin_evaluation_run(run["id"])
    catalog.replace_evaluation_units(
        run_id=run["id"],
        units=[{
            "capture_run_id": capture["id"],
            "sample_index": 0,
            "split": "HOLDOUT",
            "maturity_status": "MATURE",
            "exclusion_reason": None,
            "signal_date": "2026-09-23",
            "market": "KOSPI",
            "ticker": "005930",
            "strategy": "pullback",
            "available_trading_days": 20,
            "evaluated_through": "2026-10-22",
            "return_5d": 1.0,
            "return_10d": 2.0,
            "return_20d": 3.0,
            "mfe_pct": 4.0,
            "mae_pct": -2.0,
            "entry_comparable": 1,
            "entry_touched": 1,
            "stop_comparable": 1,
            "stop_touched": 0,
            "target1_comparable": 1,
            "target1_touched": 0,
            "target2_comparable": 1,
            "target2_touched": 0,
            "execution_status": "NOT_EXECUTED",
            "execution_reason": "SCANNER_WAIT",
            "entry_date": None,
            "entry_price": None,
            "exit_date": None,
            "exit_price": None,
            "exit_reason": None,
            "holding_days": None,
            "gross_return_pct": None,
            "net_return_pct": None,
            "mark_return_pct": None,
            "details": {"fixture": True},
            "computed_at": "2026-09-27T00:04:00+00:00",
        }],
        counts={
            "source_capture_count": 1,
            "source_sample_count": 1,
            "development_count": 0,
            "holdout_count": 1,
            "purged_count": 0,
            "mature_count": 1,
            "immature_count": 0,
            "excluded_count": 0,
            "failed_count": 0,
        },
        report_summary={"evidence_state": "SAMPLE_SIZE_POLICY_UNDEFINED"},
        completed_at="2026-09-27T00:05:00+00:00",
    )

    backup = create_backup(
        destination=tmp_path / "prospective-backup",
        holdings_db=holdings,
        simulation_db=simulation,
        include_tracking=False,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    extension = manifest["extensions"]["prospective_evaluation_v1"]
    assert extension["present"] is True
    assert extension["restorable"] is True

    restored_holdings = tmp_path / "restored-holdings.db"
    restored_simulation = tmp_path / "restored-simulation.db"
    result = restore_backup(
        backup,
        restore_simulation=True,
        target_holdings=restored_holdings,
        target_simulation=restored_simulation,
    )

    assert result["prospective_evaluation"]["store_present_in_backup"] is True
    assert result["prospective_evaluation"]["store_restored"] is True
    with sqlite3.connect(restored_simulation) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM prospective_capture_run"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM prospective_recommendation_sample"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM prospective_evaluation_protocol"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM prospective_evaluation_report"
        ).fetchone()[0] == 1


def test_holding_decision_store_roundtrip_is_declared_and_restored(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    migrate_holdings_decision_store(holdings)

    with sqlite3.connect(holdings) as conn:
        conn.row_factory = sqlite3.Row
        position = conn.execute(
            "SELECT * FROM holding_position WHERE status='OPEN' LIMIT 1"
        ).fetchone()
        revision = conn.execute(
            """
            SELECT r.* FROM stock_analysis_revision r
            JOIN stock_analysis_day d ON d.id=r.analysis_day_id
            WHERE d.monitored_stock_id=?
            ORDER BY d.market_date DESC,r.revision_no DESC
            LIMIT 1
            """,
            (position["monitored_stock_id"],),
        ).fetchone()
        plan = conn.execute(
            """
            SELECT * FROM holding_management_plan
            WHERE position_id=? AND status='ACTIVE'
            LIMIT 1
            """,
            (position["id"],),
        ).fetchone()

        conn.execute(
            """
            INSERT INTO holding_decision_record(
                id,position_id,decision_policy_version,status,primary_action,
                source_analysis_revision_id,source_active_plan_id,
                source_active_plan_version,source_position_status,
                source_position_quantity,source_position_average_price,
                valuation_market_date,valuation_price,valuation_source,
                horizon_intent,horizon_policy_version,input_fingerprint,
                evidence_json,alternatives_json,limitations_json,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "decision-backup-fixture",
                position["id"],
                HOLDING_DECISION_POLICY_VERSION,
                "ACTIONABLE",
                "HOLD",
                revision["id"],
                plan["id"],
                int(plan["plan_version"]),
                position["status"],
                position["current_quantity"],
                position["current_average_price"],
                "2026-09-24",
                "100",
                "MARKET_STORE_CONFIRMED_EOD",
                "LEGACY_UNSPECIFIED",
                None,
                "fixture-fingerprint",
                json.dumps({"plan_state": "WITHIN_PLAN"}),
                json.dumps([{
                    "action": "HOLD",
                    "state": "AVAILABLE",
                    "reason": "fixture",
                }]),
                json.dumps([{
                    "code": "ADD_POLICY_UNDEFINED",
                    "message": "fixture",
                }]),
                "2026-09-27T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO holding_decision_resolution(
                id,decision_id,selected_action,resolution_type,note,
                resulting_plan_id,created_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                "resolution-backup-fixture",
                "decision-backup-fixture",
                "HOLD",
                "APPLY_NEW_PLAN",
                "fixture",
                plan["id"],
                "2026-09-27T00:01:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO holding_management_plan_context_vnp3s1(
                plan_id,context_version,source_decision_id,selected_action,
                review_cycle_trading_days,time_stop_trading_days,
                adjustment_context_json,created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                plan["id"],
                HOLDING_PLAN_CONTEXT_VERSION,
                "decision-backup-fixture",
                "HOLD",
                None,
                None,
                json.dumps({
                    "numeric_horizon_policy_approved": False,
                    "fixture": True,
                }),
                "2026-09-27T00:01:00+00:00",
            ),
        )

    backup = create_backup(
        destination=tmp_path / "decision-backup",
        holdings_db=holdings,
        include_simulation=False,
        include_tracking=False,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    extension = manifest["extensions"]["holding_decision_v1"]
    assert extension["present"] is True
    assert extension["restorable"] is True

    restored_holdings = tmp_path / "restored-holdings.db"
    result = restore_backup(
        backup,
        target_holdings=restored_holdings,
    )

    assert result["holding_decision"]["store_present_in_backup"] is True
    assert result["holding_decision"]["store_restored"] is True
    with sqlite3.connect(restored_holdings) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_decision_record"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_decision_resolution"
        ).fetchone()[0] == 1
        row = conn.execute(
            """
            SELECT review_cycle_trading_days,time_stop_trading_days
            FROM holding_management_plan_context_vnp3s1
            """
        ).fetchone()
        assert row == (None, None)


def test_holding_recovery_store_roundtrip_is_declared_and_restored(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    migrate_holdings_decision_store(holdings)
    migrate_holdings_recovery_store(holdings)
    catalog = HoldingsCatalog(holdings)

    with sqlite3.connect(holdings) as conn:
        position_id = str(
            conn.execute(
                "SELECT id FROM holding_position WHERE status='OPEN' LIMIT 1"
            ).fetchone()[0]
        )

    service = HoldingRecoveryService(
        catalog,
        clock=lambda: "2026-09-27T03:00:00+00:00",
    )
    review = service.start_review(
        position_id=position_id,
        note="backup recovery fixture",
    )["review"]
    assessment = service.record_assessment(
        review_id=review["review_id"],
        thesis_state="WEAKENED",
        review_action="REDUCE",
        reason_note="backup roundtrip fixture",
        valuation_market_date="2026-09-24",
        valuation_price="80",
        unrealized_pnl="-200",
        unrealized_return_pct="-20",
        limitations=["COMPANY_EVIDENCE_NOT_CONNECTED"],
        evidence={"fixture": True},
    )

    backup = create_backup(
        destination=tmp_path / "recovery-backup",
        holdings_db=holdings,
        include_simulation=False,
        include_tracking=False,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    extension = manifest["extensions"]["holding_recovery_v1"]

    assert extension["schema_version"] == RECOVERY_SCHEMA_VERSION
    assert extension["present"] is True
    assert extension["restorable"] is True
    assert set(extension["tables"]) == {
        "holding_recovery_schema_meta",
        "holding_recovery_review",
        "holding_recovery_assessment",
    }

    restored_holdings = tmp_path / "restored-recovery-holdings.db"
    result = restore_backup(
        backup,
        target_holdings=restored_holdings,
    )

    assert result["holding_recovery"]["schema_version"] == RECOVERY_SCHEMA_VERSION
    assert result["holding_recovery"]["store_present_in_backup"] is True
    assert result["holding_recovery"]["store_restored"] is True

    with sqlite3.connect(restored_holdings) as conn:
        conn.row_factory = sqlite3.Row
        restored_review = conn.execute(
            "SELECT * FROM holding_recovery_review WHERE id=?",
            (review["review_id"],),
        ).fetchone()
        restored_assessment = conn.execute(
            "SELECT * FROM holding_recovery_assessment WHERE id=?",
            (assessment["assessment_id"],),
        ).fetchone()

    assert restored_review is not None
    assert restored_review["status"] == "OPEN"
    assert restored_review["opened_note"] == "backup recovery fixture"
    assert restored_assessment is not None
    assert restored_assessment["thesis_state"] == "WEAKENED"
    assert restored_assessment["review_action"] == "REDUCE"
    assert restored_assessment["valuation_price"] == "80"
    assert restored_assessment["unrealized_pnl"] == "-200"


def test_holding_watch_store_roundtrip_is_declared_and_restored(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    migrate_holdings_decision_store(holdings)
    migrate_watch_store(holdings)
    catalog = HoldingsCatalog(holdings)
    demand = load_active_plan_watch_demands(catalog)[0]
    policy = WatchPolicy(
        policy_version="TEST_BACKUP_ONLY",
        enabled=True,
        confirmation_observations=2,
        rearm_observations=2,
        rearm_distance_bps=100,
        max_quote_age_seconds=60,
    )
    now = datetime(2026, 9, 28, 0, 0, 10, tzinfo=timezone.utc)
    service = WatchService(
        catalog,
        policy_provider=lambda: policy,
        clock=lambda: now,
    )
    service.reconcile([demand])

    def snapshot(seconds: int, price: str) -> QuoteSnapshot:
        return QuoteSnapshot(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            venue="INTEGRATED",
            provider_market_division="UN",
            environment="virtual",
            current_price=Decimal(price),
            change_amount=Decimal("0"),
            change_rate=Decimal("0"),
            change_sign="3",
            open_price=Decimal("100"),
            high_price=Decimal("100"),
            low_price=Decimal(price),
            base_price=Decimal("100"),
            accumulated_volume=Decimal("1000"),
            provider_timestamp=None,
            received_at=now - timedelta(seconds=10-seconds),
            transport="WEBSOCKET",
        )

    service.process_quote(demand, snapshot(1, "89"))
    service.process_quote(demand, snapshot(2, "88"))
    service.record_coverage_issue(
        demand,
        "WS_RECONNECT",
        detail={"fixture": True},
    )

    with sqlite3.connect(holdings) as conn:
        conn.row_factory = sqlite3.Row
        setting = conn.execute(
            "SELECT * FROM holding_watch_setting WHERE status='ACTIVE'"
        ).fetchone()
        stop_rule = conn.execute(
            """
            SELECT * FROM holding_watch_rule
            WHERE rule_kind='STOP'
            """
        ).fetchone()
        episode = conn.execute(
            "SELECT * FROM holding_watch_episode"
        ).fetchone()
        gap = conn.execute(
            "SELECT * FROM holding_watch_coverage_gap"
        ).fetchone()
        notification = conn.execute(
            "SELECT * FROM holding_watch_notification_outbox"
        ).fetchone()

    assert setting is not None
    assert stop_rule is not None
    assert episode is not None
    assert gap is not None
    assert notification is not None

    backup = create_backup(
        destination=tmp_path / "watch-backup",
        holdings_db=holdings,
        include_simulation=False,
        include_tracking=False,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    extension = manifest["extensions"]["holding_watch_v1"]

    assert extension["schema_version"] == WATCH_SCHEMA_VERSION
    assert extension["policy_contract_version"] == WATCH_POLICY_CONTRACT_VERSION
    assert extension["present"] is True
    assert extension["restorable"] is True
    assert set(extension["tables"]) == {
        "holding_watch_schema_meta",
        "holding_watch_setting",
        "holding_watch_rule",
        "holding_watch_episode",
        "holding_watch_coverage_gap",
        "holding_watch_notification_outbox",
    }

    restored_holdings = tmp_path / "restored-watch-holdings.db"
    result = restore_backup(
        backup,
        target_holdings=restored_holdings,
    )

    assert result["holding_watch"]["schema_version"] == WATCH_SCHEMA_VERSION
    assert (
        result["holding_watch"]["policy_contract_version"]
        == WATCH_POLICY_CONTRACT_VERSION
    )
    assert result["holding_watch"]["store_present_in_backup"] is True
    assert result["holding_watch"]["store_restored"] is True
    assert result["holding_watch"]["live_quote_replay_performed"] is False

    with sqlite3.connect(restored_holdings) as conn:
        conn.row_factory = sqlite3.Row
        restored_setting = conn.execute(
            "SELECT * FROM holding_watch_setting WHERE id=?",
            (setting["id"],),
        ).fetchone()
        restored_rule = conn.execute(
            "SELECT * FROM holding_watch_rule WHERE id=?",
            (stop_rule["id"],),
        ).fetchone()
        restored_episode = conn.execute(
            "SELECT * FROM holding_watch_episode WHERE id=?",
            (episode["id"],),
        ).fetchone()
        restored_gap = conn.execute(
            "SELECT * FROM holding_watch_coverage_gap WHERE id=?",
            (gap["id"],),
        ).fetchone()
        restored_notification = conn.execute(
            "SELECT * FROM holding_watch_notification_outbox WHERE id=?",
            (notification["id"],),
        ).fetchone()

    assert restored_setting is not None
    assert restored_setting["plan_id"] == setting["plan_id"]
    assert restored_rule is not None
    assert restored_rule["state"] == "CONFIRMED"
    assert restored_episode is not None
    assert restored_episode["confirmed_at"] is not None
    assert restored_gap is not None
    assert restored_gap["status"] == "OPEN"
    assert restored_notification is not None
    assert restored_notification["delivery_status"] == "PENDING"


def test_restore_roundtrip_preserves_holdings_and_creates_pre_restore_backup(tmp_path):
    source = _holdings_db(tmp_path / "source.db")
    backup = create_backup(
        destination=tmp_path / "backup",
        holdings_db=source,
        include_market=False,
    )
    target = tmp_path / "target.db"
    HoldingsCatalog(target).initialize()
    before_source = holdings_counts(source)

    result = restore_backup(
        backup,
        target_holdings=target,
    )
    assert holdings_counts(target) == before_source
    pre = result["pre_restore_backups"]["holdings"]
    assert pre is not None
    assert Path(pre).is_file()


def test_full_restore_rolls_back_new_first_target_when_second_replace_fails(
    tmp_path,
    monkeypatch,
):
    source_holdings = _holdings_db(tmp_path / "source-holdings.db")
    source_market = _market_db(tmp_path / "source-market.db")
    backup = create_backup(
        destination=tmp_path / "full-backup",
        include_market=True,
        holdings_db=source_holdings,
        market_db=source_market,
    )
    target_holdings = tmp_path / "restored-holdings.db"
    target_market = tmp_path / "restored-market.db"
    real_replace = restore_module.os.replace

    def fail_second_target(src, dst):
        if Path(dst) == target_market:
            raise OSError("simulated second-target replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(restore_module.os, "replace", fail_second_target)

    with pytest.raises(OSError, match="simulated second-target"):
        restore_backup(
            backup,
            restore_market=True,
            target_holdings=target_holdings,
            target_market=target_market,
        )

    assert not target_holdings.exists()
    assert not target_market.exists()


def test_corrupt_backup_is_blocked_before_target_change(tmp_path):
    source = _holdings_db(tmp_path / "source.db")
    backup = create_backup(
        destination=tmp_path / "backup",
        holdings_db=source,
    )
    target = tmp_path / "target.db"
    HoldingsCatalog(target).initialize()
    before_hash = sha256_file(target)

    with (backup / "holdings.db").open("ab") as fp:
        fp.write(b"corrupt")

    with pytest.raises(DataToolError):
        restore_backup(
            backup,
            target_holdings=target,
        )
    assert sha256_file(target) == before_hash


def test_doctor_is_read_only_and_makes_no_network_request(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    market = _market_db(tmp_path / "market.db")
    before_h = sha256_file(holdings)
    before_m = sha256_file(market)

    report = collect_report(
        holdings_path=holdings,
        market_path=market,
    )

    assert report["network_requests"] == 0
    assert report["read_only_preserved"] is True
    assert sha256_file(holdings) == before_h
    assert sha256_file(market) == before_m
    assert report["holdings"]["status"] == "PASS"
    assert report["market_store"]["status"] == "PASS"
    assert report["requirements"]["analysis_min_rows"] > 0
    assert report["requirements"]["analysis_calendar_days"] > 0
    assert report["requirements"]["full_chart_rows"] >= 252


def test_bootstrap_runtime_is_repeatable_and_does_not_create_market_db(tmp_path, monkeypatch):
    holdings = tmp_path / "runtime" / "holdings.db"
    market = tmp_path / "runtime" / "market_history.db"
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market))

    backup_root = tmp_path / "backups"
    first = bootstrap_runtime(backup_root=backup_root)
    second = bootstrap_runtime(backup_root=backup_root)

    assert holdings.is_file()
    assert not market.exists()
    assert first["holdings_db"] == second["holdings_db"]


def test_data_tools_do_not_run_scanner_ranking_or_delete_market_store():
    root = Path(__file__).resolve().parents[2]
    prepare_source = (
        root / "tools" / "data" / "prepare.py"
    ).read_text(encoding="utf-8")
    doctor_source = (
        root / "tools" / "data" / "doctor.py"
    ).read_text(encoding="utf-8")
    restore_source = (
        root / "tools" / "data" / "restore_runtime.py"
    ).read_text(encoding="utf-8")

    assert "scanner.run(" not in prepare_source
    assert "StockScannerService.run" not in prepare_source
    assert "KrxProvider" not in doctor_source
    assert "httpx" not in doctor_source
    assert 'market_history.db").unlink' not in restore_source


def test_setup_and_env_template_expose_data1_entrypoints():
    root = Path(__file__).resolve().parents[2]
    setup = (root / "setup.ps1").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")

    assert "DATA.1 runtime bootstrap" in setup
    assert "tools\\data\\bootstrap_runtime.py" in setup
    assert "tools\\data\\doctor.py" in setup
    assert "STOCKSCOPE_HOLDINGS_DB=" in env_example
    assert "STOCKSCOPE_MARKET_STORE_DB=" in env_example



def _p5_simulation_db(path: Path) -> Path:
    simulation = _simulation_db(path)
    migrate_prospective_store(simulation)
    migrate_strategy_governance_store(simulation)
    return simulation


def _selection_runtime_with_active_policy(
    runtime: Path,
    simulation: Path,
) -> dict:
    registry = ProductionStrategySelectionRegistry(
        runtime_dir=runtime,
        simulation_db=simulation,
        clock=lambda: "2026-09-28T03:10:00+00:00",
    )
    snapshot = registry._build_snapshot(  # noqa: SLF001
        source_kind="TEST_BACKUP_FIXTURE",
        operating_strategies=[
            {
                "strategy_version_id": f"version-{strategy.value}",
                "strategy_key": strategy.value,
                "definition_hash": f"hash-{strategy.value}",
            }
            for strategy in StrategyName
            if strategy is not StrategyName.NO_TRADE
        ],
        selection_semantics={
            "risk_gate_preserved": True,
            "no_trade_safety_path_preserved": True,
            "score_formula_changed": False,
            "candidate_priority_changed": False,
        },
        scanner_baseline_id="BASELINE-A",
        production_fingerprint="PROD-A",
        production_policy_fingerprint="POLICY-A",
        proposal_id="proposal-backup-fixture",
        proposal_hash="proposal-hash",
        approval_artifact_id="approval-backup-fixture",
        approval_hash="approval-hash",
        created_at="2026-09-28T03:10:00+00:00",
    )
    registry._publish_snapshot(snapshot)  # noqa: SLF001
    registry._publish_reference(  # noqa: SLF001
        {
            "schema_version": 1,
            "active_policy_id": snapshot["policy_id"],
            "active_policy_hash": snapshot["policy_hash"],
            "rollback_policy_id": None,
            "rollback_policy_hash": None,
            "last_deactivated_policy_id": None,
            "activation_source": "TEST_BACKUP_FIXTURE",
            "approval_artifact_id": "approval-backup-fixture",
            "approval_hash": "approval-hash",
            "activated_at": "2026-09-28T03:10:00+00:00",
            "generation": 1,
        }
    )
    return snapshot


def test_p5_backup_declares_legacy_fallback_without_creating_runtime(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    simulation = _p5_simulation_db(tmp_path / "simulation.db")
    runtime = tmp_path / "strategy_selection"

    backup = create_backup(
        destination=tmp_path / "p5-legacy-backup",
        holdings_db=holdings,
        simulation_db=simulation,
        include_tracking=False,
        strategy_selection_runtime=runtime,
    )

    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    governance = manifest["extensions"]["strategy_governance_v1"]
    selection = manifest["extensions"]["strategy_selection_v1"]

    assert governance["present"] is True
    assert governance["restorable"] is True
    assert selection["runtime_present"] is False
    assert selection["active_reference_present"] is False
    assert selection["policy_snapshot_count"] == 0
    assert selection["resolved_policy_source"] == "LEGACY_CURRENT_10_FALLBACK"
    assert manifest["contents"]["strategy_selection_runtime"] is False
    assert not (backup / "strategy_selection").exists()
    assert not runtime.exists()


def test_p5_backup_copies_valid_active_selection_runtime_with_hashes(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    simulation = _p5_simulation_db(tmp_path / "simulation.db")
    runtime = tmp_path / "strategy_selection"
    snapshot = _selection_runtime_with_active_policy(runtime, simulation)

    backup = create_backup(
        destination=tmp_path / "p5-active-backup",
        holdings_db=holdings,
        simulation_db=simulation,
        include_tracking=False,
        strategy_selection_runtime=runtime,
    )

    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    selection = manifest["extensions"]["strategy_selection_v1"]
    copied_active = backup / "strategy_selection" / "active.json"
    copied_policy = (
        backup
        / "strategy_selection"
        / "policies"
        / f"{snapshot['policy_id']}.json"
    )

    assert selection["runtime_present"] is True
    assert selection["active_reference_present"] is True
    assert selection["policy_snapshot_count"] == 1
    assert selection["resolved_policy_source"] == "ACTIVE_SELECTION_POLICY"
    assert selection["resolved_policy_id"] == snapshot["policy_id"]
    assert manifest["contents"]["strategy_selection_runtime"] is True
    assert copied_active.is_file()
    assert copied_policy.is_file()
    assert "strategy_selection/active.json" in manifest["files"]
    assert (
        f"strategy_selection/policies/{snapshot['policy_id']}.json"
        in manifest["files"]
    )
    assert (
        manifest["files"]["strategy_selection/active.json"]["sha256"]
        == sha256_file(copied_active)
    )


def test_p5_backup_rejects_corrupt_selection_policy_before_publication(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    simulation = _p5_simulation_db(tmp_path / "simulation.db")
    runtime = tmp_path / "strategy_selection"
    snapshot = _selection_runtime_with_active_policy(runtime, simulation)
    policy_path = runtime / "policies" / f"{snapshot['policy_id']}.json"
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    payload["operating_strategies"] = payload["operating_strategies"][:-1]
    policy_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    destination = tmp_path / "corrupt-selection-backup"

    with pytest.raises(DataToolError, match="Selection Policy 검증 실패"):
        create_backup(
            destination=destination,
            holdings_db=holdings,
            simulation_db=simulation,
            include_tracking=False,
            strategy_selection_runtime=runtime,
        )

    assert not destination.exists()
