from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.routing import APIRoute

import app.api.simulation as simulation_api
from app.simulation.execution_catalog import HistoricalExecutionCatalog
from app.simulation.execution_service import HistoricalExecutionValidationService
from app.simulation.validation_catalog import HistoricalValidationCatalog


def _completed_validation(
    db: Path,
    *,
    candidate_count: int = 0,
):
    source = HistoricalValidationCatalog(db)
    source.initialize()
    draft = source.create_draft(
        name="VAL.2-D source",
        market_scope="KOSPI",
        requested_period_type="custom",
        requested_start_month="2026-01",
        requested_end_month="2026-01",
        resolved_start_date="2026-01-02",
        resolved_end_date="2026-01-02",
        trading_day_count=1,
    )
    candidates = []
    if candidate_count >= 1:
        candidates.append(
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
            }
        )
    if candidate_count >= 2:
        candidates.append(
            {
                "market": "KOSPI",
                "ticker": "000660",
                "name": "SK하이닉스",
                "rank": 2,
                "result_bucket": "TOP",
                "strategy": "breakout",
                "decision_status": "WATCH",
                "snapshot": {
                    "code": "000660",
                    "data_date": "2026-01-02",
                    "action": "WAIT",
                },
            }
        )

    source.save_completed_day(
        validation_id=draft.id,
        trading_date="2026-01-02",
        scanner_version=draft.scanner_version,
        market_scope="KOSPI",
        scanner_cache_hit=False,
        partial_data=False,
        input_fingerprint={"fp": "val2d"},
        market_summary=[],
        summary={"candidate_count": len(candidates)},
        methodology={},
        diagnostics={"network_requests": 0},
        candidates=candidates,
    )
    source.mark_replay_completed(draft.id)
    return source, source.get(draft.id)


def _execution_run(
    db: Path,
    validation_id: str,
    *,
    token: str = "TOKEN",
):
    catalog = HistoricalExecutionCatalog(db)
    catalog.initialize()
    run = catalog.create_run(
        validation_id=validation_id,
        market_data_cutoff_date="2026-02-03",
        production_exit_policy_token=token,
    )
    return catalog, run


def _routes():
    return {
        (route.path, tuple(sorted(route.methods)), route.status_code)
        for route in simulation_api.router.routes
        if isinstance(route, APIRoute)
    }


@pytest_asyncio.fixture(autouse=True)
async def _clear_execution_tasks():
    for task in list(simulation_api._execution_validation_tasks.values()):
        if not task.done():
            task.cancel()
    if simulation_api._execution_validation_tasks:
        await asyncio.gather(
            *list(simulation_api._execution_validation_tasks.values()),
            return_exceptions=True,
        )
    simulation_api._execution_validation_tasks.clear()
    yield
    for task in list(simulation_api._execution_validation_tasks.values()):
        if not task.done():
            task.cancel()
    if simulation_api._execution_validation_tasks:
        await asyncio.gather(
            *list(simulation_api._execution_validation_tasks.values()),
            return_exceptions=True,
        )
    simulation_api._execution_validation_tasks.clear()


def test_val2d_router_exposes_execution_contracts():
    routes = _routes()
    assert (
        "/simulation/validations/{validation_id}/executions",
        ("POST",),
        201,
    ) in routes
    assert any(
        path == "/simulation/validations/{validation_id}/executions"
        and "GET" in methods
        for path, methods, _ in routes
    )
    assert any(
        path == "/simulation/executions/{execution_run_id}"
        and "GET" in methods
        for path, methods, _ in routes
    )
    assert (
        "/simulation/executions/{execution_run_id}/run",
        ("POST",),
        202,
    ) in routes
    assert (
        "/simulation/executions/{execution_run_id}/cancel",
        ("POST",),
        202,
    ) in routes
    assert any(
        path == "/simulation/executions/{execution_run_id}/outcomes"
        and "GET" in methods
        for path, methods, _ in routes
    )


def test_create_and_detail_freeze_policy_token_and_progress(
    tmp_path: Path,
    monkeypatch,
):
    db = tmp_path / "simulation.db"
    _, validation = _completed_validation(db, candidate_count=1)
    assert validation is not None
    catalog = HistoricalExecutionCatalog(db)
    catalog.initialize()

    monkeypatch.setattr(simulation_api, "_execution_catalog", lambda: catalog)
    monkeypatch.setattr(
        simulation_api,
        "_validation_catalog",
        lambda: catalog.validation_catalog,
    )
    monkeypatch.setattr(
        simulation_api,
        "production_policy_cache_token",
        lambda: "FROZEN-TOKEN",
    )

    request = simulation_api.ExecutionValidationRequest(
        market_data_cutoff_date="2026-02-03"
    )
    created = simulation_api.create_execution_validation(
        validation.id,
        request,
    )
    assert created["status"] == "DRAFT"
    assert created["source_candidate_count"] == 1
    assert created["processed_candidate_count"] == 0
    assert created["production_exit_policy_token"] == "FROZEN-TOKEN"
    assert created["runtime_active"] is False

    listed = simulation_api.list_execution_validations(validation.id)
    assert len(listed) == 1
    detail = simulation_api.get_execution_validation(created["id"])
    assert detail["id"] == created["id"]
    assert detail["runtime_active"] is False


@pytest.mark.asyncio
async def test_run_claims_immediately_blocks_duplicate_and_background_completes(
    tmp_path: Path,
    monkeypatch,
):
    db = tmp_path / "simulation.db"
    _, validation = _completed_validation(db, candidate_count=0)
    assert validation is not None
    catalog, run = _execution_run(db, validation.id)
    release = asyncio.Event()
    calls = []

    class FakeService:
        async def run(self, execution_run_id: str, *, preclaimed: bool = False):
            calls.append((execution_run_id, preclaimed))
            await release.wait()
            return catalog.mark_completed(execution_run_id)

    monkeypatch.setattr(simulation_api, "_execution_catalog", lambda: catalog)
    monkeypatch.setattr(
        simulation_api,
        "_execution_validation_service",
        lambda: FakeService(),
    )

    response = await simulation_api.run_execution_validation(run.id)
    assert response == {
        "accepted": True,
        "id": run.id,
        "status": "RUNNING",
    }
    assert catalog.get_run(run.id).status == "RUNNING"
    assert simulation_api._execution_task_active(run.id) is True

    with pytest.raises(HTTPException) as caught:
        await simulation_api.run_execution_validation(run.id)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "VAL2_RUN_ALREADY_RUNNING"

    release.set()
    await simulation_api._execution_validation_tasks[run.id]
    assert calls == [(run.id, True)]
    assert catalog.get_run(run.id).status == "COMPLETED"
    assert simulation_api._execution_task_active(run.id) is False


@pytest.mark.asyncio
async def test_cancel_requests_active_task_and_orphan_running_is_cancelled(
    tmp_path: Path,
    monkeypatch,
):
    db = tmp_path / "simulation.db"
    _, validation = _completed_validation(db, candidate_count=0)
    assert validation is not None
    catalog, active = _execution_run(db, validation.id)
    release = asyncio.Event()

    class FakeService:
        async def run(self, execution_run_id: str, *, preclaimed: bool = False):
            await release.wait()
            if catalog.cancel_requested(execution_run_id):
                return catalog.mark_cancelled(execution_run_id)
            return catalog.mark_completed(execution_run_id)

    monkeypatch.setattr(simulation_api, "_execution_catalog", lambda: catalog)
    monkeypatch.setattr(
        simulation_api,
        "_execution_validation_service",
        lambda: FakeService(),
    )

    await simulation_api.run_execution_validation(active.id)
    cancelled = await simulation_api.cancel_execution_validation(active.id)
    assert cancelled["status"] == "RUNNING"
    assert cancelled["cancel_requested"] is True

    release.set()
    await simulation_api._execution_validation_tasks[active.id]
    assert catalog.get_run(active.id).status == "CANCELLED"

    orphan = catalog.create_run(
        validation_id=validation.id,
        market_data_cutoff_date="2026-02-04",
        production_exit_policy_token="TOKEN",
    )
    catalog.begin_run(orphan.id)
    response = await simulation_api.cancel_execution_validation(orphan.id)
    assert response["status"] == "CANCELLED"
    assert catalog.get_run(orphan.id).status == "CANCELLED"


@pytest.mark.asyncio
async def test_execution_service_resumes_pending_and_completes(
    tmp_path: Path,
):
    db = tmp_path / "simulation.db"
    source, validation = _completed_validation(db, candidate_count=2)
    assert validation is not None
    catalog, run = _execution_run(db, validation.id)

    first = source.list_candidates(validation.id)[0]
    catalog.save_outcome(
        execution_run_id=run.id,
        signal_date=first.trading_date,
        market=first.market,
        ticker=first.ticker,
        outcome_status="NOT_EXECUTED",
        outcome_reason="PREEXISTING",
    )
    claimed = catalog.begin_run(run.id)
    assert claimed.processed_candidate_count == 1

    class FakeEngine:
        def evaluate_candidate(self, execution_run_id, candidate):
            return catalog.save_outcome(
                execution_run_id=execution_run_id,
                signal_date=candidate.trading_date,
                market=candidate.market,
                ticker=candidate.ticker,
                outcome_status="NOT_EXECUTED",
                outcome_reason="FAKE",
            )

    service = HistoricalExecutionValidationService(catalog, FakeEngine())
    completed = await service.run(run.id, preclaimed=True)

    assert completed.status == "COMPLETED"
    assert completed.processed_candidate_count == 2
    assert completed.source_candidate_count == 2
    assert len(catalog.list_outcomes(run.id)) == 2


def test_outcomes_endpoint_exposes_persisted_result(
    tmp_path: Path,
    monkeypatch,
):
    db = tmp_path / "simulation.db"
    source, validation = _completed_validation(db, candidate_count=1)
    assert validation is not None
    catalog, run = _execution_run(db, validation.id)
    candidate = source.list_candidates(validation.id)[0]

    catalog.save_outcome(
        execution_run_id=run.id,
        signal_date=candidate.trading_date,
        market=candidate.market,
        ticker=candidate.ticker,
        outcome_status="CLOSED",
        outcome_reason="TARGET_1",
        entry_date="2026-01-05",
        entry_price=100.0,
        exit_date="2026-01-06",
        exit_price=120.0,
        exit_reason="TARGET_1",
        gross_return_pct=20.0,
        net_return_pct=20.0,
    )

    monkeypatch.setattr(simulation_api, "_execution_catalog", lambda: catalog)
    rows = simulation_api.list_execution_outcomes(run.id, outcome_status="CLOSED")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "005930"
    assert rows[0]["outcome_status"] == "CLOSED"
    assert rows[0]["candidate_snapshot_hash"]
    assert rows[0]["day_result_hash"]


def test_delete_val1_is_blocked_while_execution_run_is_running(
    tmp_path: Path,
    monkeypatch,
):
    db = tmp_path / "simulation.db"
    source, validation = _completed_validation(db, candidate_count=0)
    assert validation is not None
    catalog, run = _execution_run(db, validation.id)
    catalog.begin_run(run.id)

    monkeypatch.setattr(simulation_api, "_execution_catalog", lambda: catalog)
    monkeypatch.setattr(simulation_api, "_validation_catalog", lambda: source)

    with pytest.raises(HTTPException) as caught:
        simulation_api.delete_validation_draft(validation.id)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "VAL2_SOURCE_EXECUTION_RUNNING"
    assert source.get(validation.id) is not None
