from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.routing import APIRoute

import app.api.simulation as simulation_api
from app.simulation.validation_catalog import HistoricalValidationCatalog
from app.simulation.validation_replay import HistoricalValidationReplayService


def _draft(catalog: HistoricalValidationCatalog):
    return catalog.create_draft(
        name="VAL.1-C API",
        market_scope="ALL",
        requested_period_type="custom",
        requested_start_month="2026-01",
        requested_end_month="2026-01",
        resolved_start_date="2026-01-05",
        resolved_end_date="2026-01-07",
        trading_day_count=3,
    )


def _routes():
    return {
        (route.path, tuple(sorted(route.methods)), route.status_code)
        for route in simulation_api.router.routes
        if isinstance(route, APIRoute)
    }


@pytest_asyncio.fixture(autouse=True)
async def _clear_runtime_tasks():
    for task in list(simulation_api._validation_replay_tasks.values()):
        if not task.done():
            task.cancel()
    if simulation_api._validation_replay_tasks:
        await asyncio.gather(
            *list(simulation_api._validation_replay_tasks.values()),
            return_exceptions=True,
        )
    simulation_api._validation_replay_tasks.clear()
    yield
    for task in list(simulation_api._validation_replay_tasks.values()):
        if not task.done():
            task.cancel()
    if simulation_api._validation_replay_tasks:
        await asyncio.gather(
            *list(simulation_api._validation_replay_tasks.values()),
            return_exceptions=True,
        )
    simulation_api._validation_replay_tasks.clear()


def test_val1c_router_exposes_run_cancel_and_days_contracts():
    routes = _routes()
    assert (
        "/simulation/validations/{validation_id}/run",
        ("POST",),
        202,
    ) in routes
    assert (
        "/simulation/validations/{validation_id}/cancel",
        ("POST",),
        202,
    ) in routes
    assert any(
        path == "/simulation/validations/{validation_id}/days" and "GET" in methods
        for path, methods, _ in routes
    )


@pytest.mark.asyncio
async def test_run_claims_immediately_blocks_duplicate_and_background_completes(
    tmp_path: Path,
    monkeypatch,
):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = _draft(catalog)
    release = asyncio.Event()
    calls = []

    class FakeReplayService:
        async def run(self, validation_id: str, *, preclaimed: bool = False):
            calls.append((validation_id, preclaimed))
            await release.wait()
            return catalog.mark_replay_completed(validation_id)

    monkeypatch.setattr(simulation_api, "_validation_catalog", lambda: catalog)
    monkeypatch.setattr(simulation_api, "_validation_replay_service", lambda: FakeReplayService())

    response = await simulation_api.run_validation_replay(draft.id)
    assert response == {"accepted": True, "id": draft.id, "status": "RUNNING"}

    current = catalog.get(draft.id)
    assert current is not None
    assert current.status == "RUNNING"
    assert simulation_api._validation_task_active(draft.id) is True

    with pytest.raises(HTTPException) as caught:
        await simulation_api.run_validation_replay(draft.id)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "VAL_REPLAY_ALREADY_RUNNING"

    release.set()
    task = simulation_api._validation_replay_tasks[draft.id]
    await task
    assert calls == [(draft.id, True)]
    assert catalog.get(draft.id).status == "COMPLETED"
    assert simulation_api._validation_task_active(draft.id) is False


@pytest.mark.asyncio
async def test_cancel_requests_active_task_and_orphan_running_is_cancelled(
    tmp_path: Path,
    monkeypatch,
):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    active = _draft(catalog)
    release = asyncio.Event()

    class FakeReplayService:
        async def run(self, validation_id: str, *, preclaimed: bool = False):
            await release.wait()
            if catalog.cancel_requested(validation_id):
                return catalog.mark_replay_cancelled(validation_id)
            return catalog.mark_replay_completed(validation_id)

    monkeypatch.setattr(simulation_api, "_validation_catalog", lambda: catalog)
    monkeypatch.setattr(simulation_api, "_validation_replay_service", lambda: FakeReplayService())

    await simulation_api.run_validation_replay(active.id)
    cancelled = await simulation_api.cancel_validation_replay(active.id)
    assert cancelled["status"] == "RUNNING"
    assert cancelled["cancel_requested"] is True

    release.set()
    await simulation_api._validation_replay_tasks[active.id]
    assert catalog.get(active.id).status == "CANCELLED"

    orphan = _draft(catalog)
    catalog.begin_replay(orphan.id)
    orphan_response = await simulation_api.cancel_validation_replay(orphan.id)
    assert orphan_response["status"] == "CANCELLED"
    assert catalog.get(orphan.id).status == "CANCELLED"


@pytest.mark.asyncio
async def test_orphan_running_run_is_recovered_and_resumed(
    tmp_path: Path,
    monkeypatch,
):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = _draft(catalog)
    catalog.begin_replay(draft.id)

    release = asyncio.Event()

    class FakeReplayService:
        async def run(self, validation_id: str, *, preclaimed: bool = False):
            assert preclaimed is True
            await release.wait()
            return catalog.mark_replay_completed(validation_id)

    monkeypatch.setattr(simulation_api, "_validation_catalog", lambda: catalog)
    monkeypatch.setattr(simulation_api, "_validation_replay_service", lambda: FakeReplayService())

    response = await simulation_api.run_validation_replay(draft.id)
    assert response["status"] == "RUNNING"
    current = catalog.get(draft.id)
    assert current is not None
    assert current.status == "RUNNING"
    assert current.started_at is not None

    release.set()
    await simulation_api._validation_replay_tasks[draft.id]
    assert catalog.get(draft.id).status == "COMPLETED"


def test_detail_and_days_expose_progress_and_runtime_state(tmp_path: Path, monkeypatch):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = _draft(catalog)

    catalog.save_completed_day(
        validation_id=draft.id,
        trading_date="2026-01-05",
        scanner_version=draft.scanner_version,
        market_scope="ALL",
        scanner_cache_hit=False,
        partial_data=False,
        input_fingerprint={"id": "fp"},
        market_summary=[],
        summary={"candidate_count": 1},
        methodology={"mode": "point-in-time"},
        diagnostics={"network_requests": 0},
        candidates=[
            {
                "market": "KOSPI",
                "ticker": "005930",
                "name": "삼성전자",
                "rank": None,
                "result_bucket": "TOP",
                "strategy": "PULLBACK",
                "decision_status": "READY",
                "snapshot": {
                    "code": "005930",
                    "name": "삼성전자",
                    "market": "KOSPI",
                    "data_date": "2026-01-05",
                },
            }
        ],
    )

    monkeypatch.setattr(simulation_api, "_validation_catalog", lambda: catalog)

    detail = simulation_api.get_validation_draft(draft.id)
    assert detail["processed_day_count"] == 1
    assert detail["candidate_count"] == 1
    assert detail["runtime_active"] is False

    days = simulation_api.list_validation_days(draft.id)
    assert len(days) == 1
    assert days[0]["trading_date"] == "2026-01-05"
    assert days[0]["candidate_count"] == 1
    assert days[0]["diagnostics"]["network_requests"] == 0


def test_replay_service_accepts_preclaimed_run_parameter():
    import inspect

    params = inspect.signature(HistoricalValidationReplayService.run).parameters
    assert "preclaimed" in params
