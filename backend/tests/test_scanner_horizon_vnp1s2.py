from __future__ import annotations

import pytest
from fastapi import HTTPException

import app.api.backtest as backtest_api


@pytest.mark.asyncio
async def test_scanner_rejects_unapproved_horizon_before_job_creation(monkeypatch):
    def forbidden_create(*args, **kwargs):
        raise AssertionError("scanner job must not be created for an unapproved Horizon")

    monkeypatch.setattr(backtest_api.backtest_jobs, "create", forbidden_create)

    payload = backtest_api.ScannerRequest(
        market_scope="ALL",
        horizon_intent="SHORT",
    )

    with pytest.raises(HTTPException) as caught:
        await backtest_api.create_scanner_job(payload)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "HORIZON_POLICY_NOT_ACTIVE"
