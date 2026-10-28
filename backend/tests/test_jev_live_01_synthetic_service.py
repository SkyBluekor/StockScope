"""LIVE-01 service-path tests: all HTTP is MockTransport, zero paid traffic."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from app.jev.review_models import REVIEW_REQUIRED
from app.jev.synthetic_live_01 import (
    FIXTURE_ID, prepare_synthetic_service, execute_synthetic_service,
)
from app.jev.typesafe_provider import TYPESAFE_SYSTEM_ONE_URL
from app.jev.typesafe_questions_v4 import STRATEGY_RELATION_CONFLICT
from app.jev.typesafe_models import canonical_json


def _evidence():
    return {
        "provider_policy_checked_at": "MOCK_ONLY",
        "retention_status": "MOCK_ONLY",
        "model_discovery_ref": "MOCK_ONLY",
        "model_discovery_hash": "MOCK_ONLY",
    }


def _prepare(tmp_path: Path, **kwargs):
    return prepare_synthetic_service(
        tmp_path / "only-synthetic-jev.db",
        model_requested="jev-latest",
        expected_model_returned="jev-mock-returned",
        evidence=_evidence(),
        **kwargs,
    )


def _ok(request: httpx.Request, *, model: str = "jev-mock-returned", usage=True):
    assert request.method == "POST"
    assert str(request.url) == TYPESAFE_SYSTEM_ONE_URL
    assert request.headers["authorization"] == "Bearer mock-only-secret"
    body = json.loads(request.content)
    assert set(body) == {"state", "questions", "model"}
    assert body["model"] == "jev-latest"
    assert "999991" not in str(body)
    assert FIXTURE_ID not in str(body)
    response = {
        "model": model,
        "answers": {
            key: {"type": "noul", "noul": 0.82 if key == STRATEGY_RELATION_CONFLICT else 0.05}
            for key in body["questions"]
        },
    }
    if usage:
        response["usage"] = {"input_tokens": 123, "output_tokens": 12}
    return body, response


@pytest.mark.asyncio
async def test_mock_http_reaches_real_v4_service_catalog_once_and_preserves_baseline(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("JEV_API_KEY", "mock-only-secret")
    service, preview = _prepare(tmp_path)
    assert preview["synthetic_only"] is True
    assert preview["market_data_outbound_allowed"] is False
    assert preview["max_calls"] == 1
    assert "[FIXED SYNTHETIC" in preview["masked_wire_preview"]["state"]
    baseline_before = service.prospective.list_samples(
        capture_run_id=preview["capture_id"]
    )[0]["snapshot_hash"]
    requests = []

    def handler(request):
        wire, response = _ok(request)
        requests.append(wire)
        assert hashlib.sha256(
            canonical_json(wire).encode("utf-8")
        ).hexdigest() == preview["wire_sha256"]
        return httpx.Response(200, json=response)

    result = await execute_synthetic_service(
        service, preview, transport=httpx.MockTransport(handler)
    )
    assert result["result"]["status"] == REVIEW_REQUIRED
    assert result["stored_status"] == "VALID"
    assert result["stored_disposition"] == REVIEW_REQUIRED
    assert result["model_returned"] == "jev-mock-returned"
    assert result["model_identity_status"] == "MATCHED"
    assert result["usage"] == {"input_tokens": 123, "output_tokens": 12}
    assert result["cost_usd"] is None and result["cost_unknown"] is True
    assert len(requests) == 1

    repeat = await service.request_review(
        capture_id=preview["capture_id"], sample_index=preview["sample_index"]
    )
    assert repeat["reused"] is True
    assert repeat["review_id"] == result["result"]["review_id"]
    assert len(requests) == 1
    assert service.prospective.list_samples(
        capture_run_id=preview["capture_id"]
    )[0]["snapshot_hash"] == baseline_before
    assert len(service.typesafe.list_monitor_items(preview["capture_id"])) == 1


@pytest.mark.parametrize("case,expected", [
    ("401", "TYPESAFE_PROVIDER_AUTH_ERROR"),
    ("422", "TYPESAFE_PROVIDER_REQUEST_REJECTED"),
    ("429", "TYPESAFE_PROVIDER_RATE_LIMIT"),
    ("500", "TYPESAFE_PROVIDER_UNAVAILABLE"),
    ("timeout", "TYPESAFE_PROVIDER_TIMEOUT"),
    ("bad-json", "TYPESAFE_RESPONSE_INVALID_JSON"),
    ("wrong-model", "TYPESAFE_MODEL_IDENTITY_CHANGED"),
    ("missing-usage", "TYPESAFE_USAGE_MISSING"),
])
@pytest.mark.asyncio
async def test_provider_failures_store_terminal_error_and_never_retry(
    case, expected, tmp_path, monkeypatch,
):
    monkeypatch.setenv("JEV_API_KEY", "mock-only-secret")
    service, preview = _prepare(tmp_path)
    calls = []

    def handler(request):
        calls.append(request)
        _, result = _ok(request)
        if case == "timeout":
            raise httpx.ReadTimeout("synthetic mock timeout", request=request)
        if case == "bad-json":
            return httpx.Response(200, content=b"not-json")
        if case == "wrong-model":
            result["model"] = "unexpected-version"
        if case == "missing-usage":
            del result["usage"]
        if case in {"401", "422", "429", "500"}:
            return httpx.Response(int(case))
        return httpx.Response(200, json=result)

    outcome = await execute_synthetic_service(
        service, preview, transport=httpx.MockTransport(handler)
    )
    assert len(calls) == 1
    assert outcome["result"]["status"] == "ERROR"
    assert outcome["stored_status"] == "ERROR"
    assert outcome["failure_code"] == expected
    assert outcome["stored_disposition"] is None
    assert outcome["cost_unknown"] is True
    second = await service.request_review(
        capture_id=preview["capture_id"], sample_index=preview["sample_index"]
    )
    assert second["reused"] is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_changed_preview_and_nonfresh_service_fail_before_http(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "mock-only-secret")
    service, preview = _prepare(tmp_path)
    preview["wire_sha256"] = "tampered"
    called = []
    transport = httpx.MockTransport(
        lambda request: (called.append(request), httpx.Response(200))[1]
    )
    with pytest.raises(ValueError, match="WIRE_CHANGED"):
        await execute_synthetic_service(service, preview, transport=transport)
    assert called == []


def test_no_existing_operational_or_prior_synthetic_db_can_be_opened(tmp_path):
    db = tmp_path / "only-synthetic-jev.db"
    db.write_bytes(b"DO-NOT-MODIFY")
    with pytest.raises(ValueError, match="DB_MUST_NOT_EXIST"):
        _prepare(tmp_path)
    assert db.read_bytes() == b"DO-NOT-MODIFY"


def test_budget_and_evidence_are_required_before_db_creation(tmp_path):
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        _prepare(tmp_path, reservation_usd=2.0, budget_usd=1.0)
    assert not (tmp_path / "only-synthetic-jev.db").exists()
    with pytest.raises(ValueError, match="EVIDENCE_REQUIRED"):
        prepare_synthetic_service(
            tmp_path / "only-synthetic-jev.db",
            model_requested="jev-latest",
            expected_model_returned="jev-mock-returned",
            evidence={},
        )
    assert not (tmp_path / "only-synthetic-jev.db").exists()
