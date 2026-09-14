from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.backtest import BacktestConfig, BacktestService
from app.backtest.jobs import BacktestJobCancelled, backtest_jobs
from app.backtest.risk_validation import RiskPolicyValidationService
from app.backtest.scanner import StockScannerService
from app.core.config import get_settings
from app.market.providers import KrxProvider
from app.market.providers.base import ProviderError, ProviderNotConfigured

router = APIRouter(prefix="/backtest", tags=["backtest"])




class ScannerRequest(BaseModel):
    market_scope: Literal["ALL", "KOSPI", "KOSDAQ"] = "ALL"
    as_of_date: str | None = None
    candidate_limit: int = Field(default=5, ge=1, le=10)
    force_refresh: bool = False
    allow_large_sync: bool = False

class PullbackBacktestRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=12)
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI"
    start_date: str
    end_date: str
    initial_capital: float = Field(default=10_000_000, gt=0, le=1_000_000_000_000)
    max_holding_days: int = Field(default=20, ge=1, le=120)
    round_trip_cost_pct: float = Field(default=0.0, ge=0, le=5)


def _config(payload: PullbackBacktestRequest) -> BacktestConfig:
    return BacktestConfig(
        code=payload.code,
        market=payload.market,
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_capital=payload.initial_capital,
        max_holding_days=payload.max_holding_days,
        round_trip_cost_pct=payload.round_trip_cost_pct,
    )


@router.post("/pullback")
async def pullback_backtest(payload: PullbackBacktestRequest) -> dict:
    """Compatibility endpoint. New UI uses the cancellable job API below."""
    settings = get_settings()
    service = BacktestService(KrxProvider(settings.krx_api_key))
    try:
        return await service.run_pullback(_config(payload))
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _run_job(job_id: str, config: BacktestConfig, api_key: str | None) -> None:
    service = BacktestService(KrxProvider(api_key))

    def update_progress(payload: dict) -> None:
        # asyncio.to_thread cannot forcibly kill a running Python thread. Raising from
        # its periodic progress callback makes the calculation stop at the next small
        # checkpoint after a user cancellation.
        if backtest_jobs.is_cancelled(job_id):
            raise BacktestJobCancelled()
        backtest_jobs.update_progress(job_id, payload)

    try:
        result = await service.run_pullback(
            config,
            progress=update_progress,
        )
    except BacktestJobCancelled:
        backtest_jobs.mark_cancelled(job_id)
    except asyncio.CancelledError:
        backtest_jobs.mark_cancelled(job_id)
        raise
    except (ProviderNotConfigured, ProviderError, ValueError) as exc:
        backtest_jobs.fail(job_id, str(exc))
    except Exception as exc:  # pragma: no cover - final containment for background jobs
        backtest_jobs.fail(job_id, f"백테스트 처리 중 예상하지 못한 오류가 발생했습니다: {exc}")
    else:
        backtest_jobs.complete(job_id, result)


@router.post("/pullback/jobs", status_code=202)
async def create_pullback_backtest_job(payload: PullbackBacktestRequest) -> dict:
    settings = get_settings()
    job = backtest_jobs.create()
    task = asyncio.create_task(_run_job(job.job_id, _config(payload), settings.krx_api_key))
    backtest_jobs.attach_task(job.job_id, task)
    return job.public()


async def _run_risk_policy_validation_job(job_id: str, config: BacktestConfig, api_key: str | None) -> None:
    service = RiskPolicyValidationService(KrxProvider(api_key))

    def update_progress(payload: dict) -> None:
        if backtest_jobs.is_cancelled(job_id):
            raise BacktestJobCancelled()
        backtest_jobs.update_progress(job_id, payload)

    try:
        result = await service.run(config, progress=update_progress)
    except BacktestJobCancelled:
        backtest_jobs.mark_cancelled(job_id)
    except asyncio.CancelledError:
        backtest_jobs.mark_cancelled(job_id)
        raise
    except (ProviderNotConfigured, ProviderError, ValueError) as exc:
        backtest_jobs.fail(job_id, str(exc))
    except Exception as exc:  # pragma: no cover - final containment for background jobs
        backtest_jobs.fail(job_id, f"Risk 정책 교차검증 중 예상하지 못한 오류가 발생했습니다: {exc}")
    else:
        backtest_jobs.complete(job_id, result)


@router.post("/pullback/risk-policy-validation/jobs", status_code=202)
async def create_risk_policy_validation_job(payload: PullbackBacktestRequest) -> dict:
    """Automatically validate all v0.19.5 Risk-policy experiments on same-market peers."""
    settings = get_settings()
    job = backtest_jobs.create()
    task = asyncio.create_task(
        _run_risk_policy_validation_job(job.job_id, _config(payload), settings.krx_api_key)
    )
    backtest_jobs.attach_task(job.job_id, task)
    return job.public()


@router.post("/multi-strategy")
async def multi_strategy_backtest(payload: PullbackBacktestRequest) -> dict:
    """Compare all supported strategies on one shared historical dataset."""
    settings = get_settings()
    service = BacktestService(KrxProvider(settings.krx_api_key))
    try:
        return await service.run_multi_strategy(_config(payload))
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _run_multi_strategy_job(job_id: str, config: BacktestConfig, api_key: str | None) -> None:
    service = BacktestService(KrxProvider(api_key))

    def update_progress(payload: dict) -> None:
        if backtest_jobs.is_cancelled(job_id):
            raise BacktestJobCancelled()
        backtest_jobs.update_progress(job_id, payload)

    try:
        result = await service.run_multi_strategy(config, progress=update_progress)
    except BacktestJobCancelled:
        backtest_jobs.mark_cancelled(job_id)
    except asyncio.CancelledError:
        backtest_jobs.mark_cancelled(job_id)
        raise
    except (ProviderNotConfigured, ProviderError, ValueError) as exc:
        backtest_jobs.fail(job_id, str(exc))
    except Exception as exc:  # pragma: no cover
        backtest_jobs.fail(job_id, f"전체 전략 검증 중 예상하지 못한 오류가 발생했습니다: {exc}")
    else:
        backtest_jobs.complete(job_id, result)


@router.post("/multi-strategy/jobs", status_code=202)
async def create_multi_strategy_backtest_job(payload: PullbackBacktestRequest) -> dict:
    settings = get_settings()
    job = backtest_jobs.create()
    task = asyncio.create_task(_run_multi_strategy_job(job.job_id, _config(payload), settings.krx_api_key))
    backtest_jobs.attach_task(job.job_id, task)
    return job.public()


async def _run_scanner_job(job_id: str, payload: ScannerRequest, api_key: str | None) -> None:
    service = StockScannerService(KrxProvider(api_key))

    def update_progress(progress_payload: dict) -> None:
        if backtest_jobs.is_cancelled(job_id):
            raise BacktestJobCancelled()
        backtest_jobs.update_progress(job_id, progress_payload)

    try:
        result = await service.run(
            market_scope=payload.market_scope,
            as_of_date=payload.as_of_date,
            candidate_limit=payload.candidate_limit,
            force_refresh=payload.force_refresh,
            allow_large_sync=payload.allow_large_sync,
            progress=update_progress,
        )
    except BacktestJobCancelled:
        backtest_jobs.mark_cancelled(job_id)
    except asyncio.CancelledError:
        backtest_jobs.mark_cancelled(job_id)
        raise
    except (ProviderNotConfigured, ProviderError, ValueError) as exc:
        backtest_jobs.fail(job_id, str(exc))
    except Exception as exc:  # pragma: no cover
        backtest_jobs.fail(job_id, f"종목 찾기 처리 중 예상하지 못한 오류가 발생했습니다: {exc}")
    else:
        backtest_jobs.complete(job_id, result)


@router.post("/scanner/jobs", status_code=202)
async def create_scanner_job(payload: ScannerRequest) -> dict:
    settings = get_settings()
    job = backtest_jobs.create()
    task = asyncio.create_task(_run_scanner_job(job.job_id, payload, settings.krx_api_key))
    backtest_jobs.attach_task(job.job_id, task)
    return job.public()


@router.get("/jobs/{job_id}")
async def get_backtest_job(job_id: str) -> dict:
    job = backtest_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="백테스트 작업을 찾을 수 없습니다. 서버가 재시작되었을 수 있습니다.")
    return job.public()


@router.delete("/jobs/{job_id}")
async def cancel_backtest_job(job_id: str) -> dict:
    job = backtest_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="백테스트 작업을 찾을 수 없습니다.")
    backtest_jobs.cancel(job_id)
    updated = backtest_jobs.get(job_id)
    return updated.public() if updated is not None else {"job_id": job_id, "status": "cancelled"}
