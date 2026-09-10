from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.backtest import BacktestConfig, BacktestService
from app.backtest.jobs import BacktestJobCancelled, backtest_jobs
from app.core.config import get_settings
from app.market.providers import KrxProvider
from app.market.providers.base import ProviderError, ProviderNotConfigured

router = APIRouter(prefix="/backtest", tags=["backtest"])


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
