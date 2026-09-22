from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.simulation.execution_catalog import (
    EXECUTION_POLICY_VERSION,
    ExecutionCatalogError,
    HistoricalExecutionCatalog,
)
from app.simulation.validation_catalog import HistoricalValidationCatalog


def _completed_source(db: Path):
    source = HistoricalValidationCatalog(db)
    source.initialize()
    draft = source.create_draft(
        name="VAL.2 source",
        market_scope="ALL",
        requested_period_type="custom",
        requested_start_month="2026-01",
        requested_end_month="2026-01",
        resolved_start_date="2026-01-02",
        resolved_end_date="2026-01-02",
        trading_day_count=1,
    )
    day = source.save_completed_day(
        validation_id=draft.id,
        trading_date="2026-01-02",
        scanner_version="0.21.3.7",
        market_scope="ALL",
        scanner_cache_hit=False,
        partial_data=False,
        input_fingerprint={"fp": "source"},
        market_summary=[],
        summary={"candidate_count": 2},
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
                    "data_date": "2026-01-02",
                    "action": "ENTRY_CANDIDATE",
                },
            },
            {
                "market": "KOSDAQ",
                "ticker": "035900",
                "name": "JYP Ent.",
                "rank": 6,
                "result_bucket": "MORE",
                "strategy": "breakout",
                "decision_status": "WATCH",
                "snapshot": {
                    "code": "035900",
                    "data_date": "2026-01-02",
                    "action": "WAIT",
                },
            },
        ],
    )
    source.mark_replay_completed(draft.id)
    return source, source.get(draft.id), day


def test_val2b_initialize_and_run_preserve_completed_val1_source(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source, validation, day = _completed_source(db)
    assert validation is not None
    before = [
        (row.ticker, row.snapshot_hash)
        for row in source.list_candidates(validation.id)
    ]

    catalog = HistoricalExecutionCatalog(db)
    catalog.initialize()
    run = catalog.create_run(
        validation_id=validation.id,
        market_data_cutoff_date="2026-02-03",
        production_exit_policy_token="EXIT_PRODUCTION_V2-test",
    )

    assert run.validation_id == validation.id
    assert run.execution_policy_version == EXECUTION_POLICY_VERSION
    assert run.source_candidate_count == 2
    assert run.processed_candidate_count == 0
    assert run.status == "DRAFT"

    after = [
        (row.ticker, row.snapshot_hash)
        for row in source.list_candidates(validation.id)
    ]
    assert after == before
    assert source.get_day(validation.id, "2026-01-02").result_hash == day.result_hash

    same = catalog.create_run(
        validation_id=validation.id,
        market_data_cutoff_date="2026-02-03",
        production_exit_policy_token="EXIT_PRODUCTION_V2-test",
    )
    assert same.id == run.id


def test_val2b_requires_completed_val1_source(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source = HistoricalValidationCatalog(db)
    source.initialize()
    draft = source.create_draft(
        name="unfinished",
        market_scope="KOSPI",
        requested_period_type="custom",
        requested_start_month="2026-01",
        requested_end_month="2026-01",
        resolved_start_date="2026-01-02",
        resolved_end_date="2026-01-02",
        trading_day_count=1,
    )

    catalog = HistoricalExecutionCatalog(db)
    catalog.initialize()
    with pytest.raises(ExecutionCatalogError) as exc:
        catalog.create_run(
            validation_id=draft.id,
            market_data_cutoff_date="2026-02-03",
            production_exit_policy_token="EXIT_PRODUCTION_V2-test",
        )
    assert exc.value.code == "VAL2_SOURCE_NOT_COMPLETED"


def test_val2b_outcome_captures_val1_provenance_and_is_immutable(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source, validation, day = _completed_source(db)
    assert validation is not None

    catalog = HistoricalExecutionCatalog(db)
    catalog.initialize()
    run = catalog.create_run(
        validation_id=validation.id,
        market_data_cutoff_date="2026-02-03",
        production_exit_policy_token="EXIT_PRODUCTION_V2-test",
    )

    outcome = catalog.save_outcome(
        execution_run_id=run.id,
        signal_date="2026-01-02",
        market="KOSPI",
        ticker="005930",
        outcome_status="CLOSED",
        entry_reference_date="2026-01-05",
        entry_reference_price=70000,
        entry_date="2026-01-05",
        entry_price=70000,
        stop_price=66500,
        target1_price=77000,
        target2_price=80500,
        exit_date="2026-01-09",
        exit_price=77000,
        exit_reason="TARGET_1",
        holding_days=5,
        gross_return_pct=10.0,
        net_return_pct=10.0,
        details={"policy": "D+1_OPEN"},
    )

    candidate = source.list_candidates(validation.id, "2026-01-02")[0]
    assert outcome.candidate_snapshot_hash == candidate.snapshot_hash
    assert outcome.day_result_hash == day.result_hash
    assert outcome.action == "ENTRY_CANDIDATE"
    assert outcome.strategy == "pullback"
    assert outcome.result_bucket == "TOP"
    assert outcome.outcome_hash

    refreshed = catalog.get_run(run.id)
    assert refreshed is not None
    assert refreshed.processed_candidate_count == 1
    assert refreshed.closed_count == 1
    assert len(catalog.pending_candidates(run.id)) == 1

    original_hash = outcome.outcome_hash
    same = catalog.save_outcome(
        execution_run_id=run.id,
        signal_date="2026-01-02",
        market="KOSPI",
        ticker="005930",
        outcome_status="CLOSED",
        entry_date="2099-01-01",
        entry_price=1,
        exit_date="2099-01-02",
        exit_price=999999,
        exit_reason="MUST_NOT_OVERWRITE",
    )
    assert same.outcome_hash == original_hash
    assert same.entry_date == "2026-01-05"
    assert same.exit_reason == "TARGET_1"


def test_val2b_status_counts_and_validation_delete_cascade(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source, validation, _ = _completed_source(db)
    assert validation is not None

    catalog = HistoricalExecutionCatalog(db)
    catalog.initialize()
    run = catalog.create_run(
        validation_id=validation.id,
        market_data_cutoff_date="2026-02-03",
        production_exit_policy_token="EXIT_PRODUCTION_V2-test",
    )

    catalog.save_outcome(
        execution_run_id=run.id,
        signal_date="2026-01-02",
        market="KOSPI",
        ticker="005930",
        outcome_status="CENSORED",
        entry_date="2026-01-05",
        entry_price=70000,
        stop_price=66500,
        target1_price=77000,
        mark_date="2026-02-03",
        mark_price=73500,
        mark_return_pct=5.0,
    )
    catalog.save_outcome(
        execution_run_id=run.id,
        signal_date="2026-01-02",
        market="KOSDAQ",
        ticker="035900",
        outcome_status="NOT_EXECUTED",
        outcome_reason="SCANNER_WAIT",
    )

    refreshed = catalog.get_run(run.id)
    assert refreshed is not None
    assert refreshed.processed_candidate_count == 2
    assert refreshed.censored_count == 1
    assert refreshed.not_executed_count == 1
    assert len(catalog.pending_candidates(run.id)) == 0

    assert source.delete(validation.id) is True
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM historical_execution_run WHERE id=?",
            (run.id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM historical_execution_outcome WHERE execution_run_id=?",
            (run.id,),
        ).fetchone()[0] == 0
