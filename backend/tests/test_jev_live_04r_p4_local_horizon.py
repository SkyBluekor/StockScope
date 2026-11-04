"""P4 real Scanner request contract: local Horizon can be recorded, not activated.

No stock data, KRX download, outgoing AI call, policy approval, or real DB.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

import app.api.backtest as scanner_api
from app.horizon import resolve_horizon_context
from app.jev.synthetic_live_01 import prepare_synthetic_service
from app.prospective.catalog import ProspectiveCatalog, ProspectiveCatalogError
from app.prospective.models import ProspectiveCaptureRequest
from app.prospective.service import ProspectiveService


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", ["SHORT", "MEDIUM", "LONG"])
async def test_only_explicit_local_purpose_allows_pending_horizon(
    monkeypatch, intent,
):
    class Jobs:
        def __init__(self):
            self.tasks = []
        def create(self):
            return SimpleNamespace(job_id="authored-p4-job", public=lambda: {"job_id": "authored-p4-job"})
        def attach_task(self, _job_id, task):
            self.tasks.append(task)

    jobs = Jobs()
    captured = []

    class CatalogStub:
        def try_begin_scanner_capture(self, **kwargs):
            captured.append(kwargs)
            return {"status": "PENDING"}

    class RegistryStub:
        def pin_active_selection_policy(self):
            return SimpleNamespace(
                policy_id="authored-policy", policy_hash="authored-hash",
            )

    async def no_market_run(*_args, **_kwargs):
        return None

    monkeypatch.setattr(scanner_api, "backtest_jobs", jobs)
    monkeypatch.setattr(scanner_api, "_prospective_service", lambda: CatalogStub())
    monkeypatch.setattr(scanner_api, "ProductionStrategySelectionRegistry", RegistryStub)
    monkeypatch.setattr(scanner_api, "get_settings", lambda: SimpleNamespace(krx_api_key=None))
    monkeypatch.setattr(scanner_api, "_run_scanner_job", no_market_run)
    app = FastAPI()
    app.include_router(scanner_api.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.post("/backtest/scanner/jobs", json={
            "market_scope": "KOSPI", "horizon_intent": intent,
            "horizon_purpose": "LOCAL_REVIEW_ONLY",
        })
        assert response.status_code == 202, response.text
        assert response.json()["job_id"] == "authored-p4-job"
        blocked = await client.post("/backtest/scanner/jobs", json={
            "market_scope": "KOSPI", "horizon_intent": intent,
        })
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "HORIZON_POLICY_NOT_ACTIVE"
        legacy = await client.post("/backtest/scanner/jobs", json={
            "horizon_purpose": "LOCAL_REVIEW_ONLY",
        })
        assert legacy.status_code == 409
        assert legacy.json()["detail"]["code"] == "HORIZON_LOCAL_REVIEW_REQUIRES_EXPLICIT_INTENT"
        invalid = await client.post("/backtest/scanner/jobs", json={
            "horizon_purpose": "ARBITRARY", "horizon_intent": intent,
        })
        assert invalid.status_code == 422
        bad_horizon = await client.post("/backtest/scanner/jobs", json={
            "horizon_purpose": "LOCAL_REVIEW_ONLY", "horizon_intent": "DECADES",
        })
        assert bad_horizon.status_code == 409
        assert bad_horizon.json()["detail"]["code"] == "HORIZON_INTENT_INVALID"
    assert len(captured) == 1
    assert captured[0]["payload"].horizon_purpose == "LOCAL_REVIEW_ONLY"
    assert captured[0]["payload"].horizon_intent == intent
    await asyncio.gather(*jobs.tasks)
    assert resolve_horizon_context(intent).support_status == "EVALUATION_PENDING"


@pytest.fixture()
def catalog(tmp_path):
    db = tmp_path / "p4-original-synthetic.db"
    prepare_synthetic_service(
        db, model_requested="jev-latest", expected_model_returned="jev-mock-returned",
        evidence={
            "provider_policy_checked_at": "MOCK_ONLY",
            "retention_status": "MOCK_ONLY",
            "model_discovery_ref": "MOCK_ONLY",
            "model_discovery_hash": "MOCK_ONLY",
        },
    )
    return ProspectiveCatalog(db), db


def _result(purpose, intent):
    context = resolve_horizon_context(intent).to_dict()
    context["purpose"] = purpose
    return {
        "version": "AUTHORED-P4-SCANNER", "market_scope": "KOSPI",
        "requested_as_of": "2026-10-28",
        "input_fingerprint": "same-authored-market-input",
        "summary": {"candidate_count": 0},
        "candidates": [], "more_candidates": [],
        "partial_data": False, "horizon_context": context,
    }


def _request(intent, purpose):
    horizon = resolve_horizon_context(intent)
    return ProspectiveCaptureRequest(
        market_scope="KOSPI", requested_as_of="2026-10-28",
        candidate_limit=5, horizon_intent=horizon.intent,
        horizon_policy_version=horizon.policy_version,
        horizon_purpose=purpose,
    )


def test_begin_finalize_freezes_purpose_and_separates_horizon_dedup(catalog):
    store, db = catalog
    initial = None
    captured = []
    for index, (intent, purpose) in enumerate([
        ("SHORT", "LOCAL_REVIEW_ONLY"),
        ("MEDIUM", "LOCAL_REVIEW_ONLY"),
        ("SHORT", "PRODUCTION_POLICY"),
        ("SHORT", "LOCAL_REVIEW_ONLY"),
    ]):
        request = _request(intent, purpose)
        result = _result(purpose, intent)
        job = f"authored-p4-job-{index}"
        started = store.begin_capture(source_job_id=job, request=request)
        frozen = store.finalize_capture(source_job_id=job, request=request, result=result)
        assert frozen["request"]["horizon_purpose"] == purpose
        assert frozen["request"]["horizon_intent"] == intent
        assert frozen["horizon_intent"] == intent
        assert frozen["horizon_policy_version"] == "VN_P1_S2_HORIZON_CONTEXT_V1"
        captured.append(frozen)
        if index == 0:
            initial = frozen
    assert [item["status"] for item in captured] == [
        "COMPLETE", "COMPLETE", "COMPLETE", "DUPLICATE",
    ]
    assert captured[3]["canonical_capture_id"] == initial["id"]
    assert captured[0]["source_execution_key"] != captured[1]["source_execution_key"]
    assert captured[0]["source_execution_key"] != captured[2]["source_execution_key"]
    assert store.get_capture(initial["id"])["request"]["horizon_purpose"] == "LOCAL_REVIEW_ONLY"

    altered = replace(_request("SHORT", "LOCAL_REVIEW_ONLY"), horizon_purpose="PRODUCTION_POLICY")
    begun = store.begin_capture(source_job_id="authored-p4-drift", request=_request("SHORT", "LOCAL_REVIEW_ONLY"))
    with pytest.raises(ProspectiveCatalogError) as exc:
        store.finalize_capture(
            source_job_id="authored-p4-drift", request=altered,
            result=_result("PRODUCTION_POLICY", "SHORT"),
        )
    assert exc.value.code == "PROSPECTIVE_CAPTURE_REQUEST_DRIFT"
    assert store.get_capture(begun["id"])["status"] == "PENDING"


def test_service_preserves_purpose_and_numeric_policy_stays_unapproved():
    for intent in ("SHORT", "MEDIUM", "LONG"):
        source = SimpleNamespace(
            market_scope="KOSPI", as_of_date="2026-10-28",
            candidate_limit=5, horizon_intent=intent,
            horizon_purpose="LOCAL_REVIEW_ONLY",
        )
        request = ProspectiveService.capture_request_from_scanner_payload(source)
        assert request.horizon_intent == intent
        assert request.horizon_purpose == "LOCAL_REVIEW_ONLY"
        assert resolve_horizon_context(intent).review_cycle_trading_days is None
        assert resolve_horizon_context(intent).time_stop_trading_days is None


def test_scanner_selection_registry_uses_governance_runtime_binding(
    tmp_path, monkeypatch,
):
    # No policy activation; this only verifies both paths resolve the same
    # explicit runtime when configured, rather than silently using defaults.
    from app.api import strategy_governance
    monkeypatch.setenv("STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR", str(tmp_path))
    assert scanner_api._selection_policy_registry().runtime_dir == tmp_path
    assert strategy_governance._selection_registry().runtime_dir == tmp_path
    assert scanner_api._selection_policy_registry().pin_active_selection_policy().policy_source == "LEGACY_CURRENT_10_FALLBACK"
