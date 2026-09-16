from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.backtest import BacktestConfig, BacktestService
from app.backtest.jobs import BacktestJobCancelled, backtest_jobs
from app.backtest.exit_policy_selection import ExitPolicySelectionConfig
from app.backtest.exit_policy_validation_runner import (
    ExitPolicyValidationCheckpoint,
    ExitPolicyValidationRunnerConfig,
)
from app.backtest.risk_validation import RiskPolicyValidationService
from app.backtest.scanner import StockScannerService
from app.backtest.production_exit_policy import ProductionExitPolicyRegistry
from app.backtest.research_audit import ExitPolicyResearchAuditor, ExitPolicyResearchAuditStore
from app.backtest.expanded_sample_validation import (
    ALLOWED_EXPANDED_TARGETS,
    ExpandedSamplePlanner,
    ExpandedSamplePreparationService,
    compare_validation_reports,
    validation_config_from_report,
)
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


class ScannerFreshnessRequest(BaseModel):
    market_scope: Literal["ALL", "KOSPI", "KOSDAQ"] = "ALL"
    known_data_date: str | None = None

class PullbackBacktestRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=12)
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI"
    start_date: str
    end_date: str
    initial_capital: float = Field(default=10_000_000, gt=0, le=1_000_000_000_000)
    max_holding_days: int = Field(default=20, ge=1, le=120)
    round_trip_cost_pct: float = Field(default=0.0, ge=0, le=5)


class ExitPolicySelectionStock(BaseModel):
    code: str = Field(..., min_length=1, max_length=12)
    market: Literal["KOSPI", "KOSDAQ"]


class ExitPolicySelectionRequest(BaseModel):
    stocks: list[ExitPolicySelectionStock]
    start_date: str
    end_date: str
    initial_capital: float = Field(default=10_000_000, gt=0, le=1_000_000_000_000)
    max_holding_days: int = Field(default=20, ge=1, le=120)
    round_trip_cost_pct: float = Field(default=0.0, ge=0, le=5)
    minimum_stock_count: int = Field(default=3, ge=2, le=30)
    minimum_total_trades: int = Field(default=30, ge=10, le=10000)
    post_target2_research_days: int = Field(default=60, ge=1, le=240)


class ExitPolicyValidationRunnerRequest(BaseModel):
    start_date: str
    end_date: str
    markets: list[Literal["KOSPI", "KOSDAQ"]] = Field(default_factory=lambda: ["KOSPI", "KOSDAQ"])
    max_stocks: int = Field(default=20, ge=2, le=60)
    minimum_coverage_pct: float = Field(default=90.0, ge=50, le=100)
    initial_capital: float = Field(default=10_000_000, gt=0, le=1_000_000_000_000)
    max_holding_days: int = Field(default=20, ge=1, le=120)
    round_trip_cost_pct: float = Field(default=0.0, ge=0, le=5)
    minimum_stock_count: int = Field(default=3, ge=2, le=30)
    minimum_total_trades: int = Field(default=30, ge=10, le=10000)
    post_target2_research_days: int = Field(default=60, ge=1, le=240)
    force_refresh: bool = False


class ExpandedSampleRequest(BaseModel):
    target_stocks: int = 40
    base_signature: str | None = None
    force_refresh: bool = False


def _validation_runner_config(payload: ExitPolicyValidationRunnerRequest) -> ExitPolicyValidationRunnerConfig:
    markets = tuple(dict.fromkeys(payload.markets))
    return ExitPolicyValidationRunnerConfig(
        start_date=payload.start_date,
        end_date=payload.end_date,
        markets=markets,
        max_stocks=payload.max_stocks,
        minimum_coverage_pct=payload.minimum_coverage_pct,
        initial_capital=payload.initial_capital,
        max_holding_days=payload.max_holding_days,
        round_trip_cost_pct=payload.round_trip_cost_pct,
        minimum_stock_count=payload.minimum_stock_count,
        minimum_total_trades=payload.minimum_total_trades,
        post_target2_research_days=payload.post_target2_research_days,
    )


def _selection_configs(payload: ExitPolicySelectionRequest) -> list[BacktestConfig]:
    if len(payload.stocks) < 2 or len(payload.stocks) > 30:
        raise ValueError("Exit 정책 선택 검증 종목은 2~30개여야 합니다.")
    return [
        BacktestConfig(
            code=stock.code,
            market=stock.market,
            start_date=payload.start_date,
            end_date=payload.end_date,
            initial_capital=payload.initial_capital,
            max_holding_days=payload.max_holding_days,
            round_trip_cost_pct=payload.round_trip_cost_pct,
        )
        for stock in payload.stocks
    ]


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


@router.post("/exit-policy-audit")
async def exit_policy_audit(payload: PullbackBacktestRequest) -> dict:
    """Research-only comparison. Does not change the live/Scanner exit policy."""
    settings = get_settings()
    service = BacktestService(KrxProvider(settings.krx_api_key))
    try:
        return await service.run_exit_policy_audit(_config(payload))
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _run_exit_policy_audit_job(job_id: str, config: BacktestConfig, api_key: str | None) -> None:
    service = BacktestService(KrxProvider(api_key))

    def update_progress(payload: dict) -> None:
        if backtest_jobs.is_cancelled(job_id):
            raise BacktestJobCancelled()
        backtest_jobs.update_progress(job_id, payload)

    try:
        result = await service.run_exit_policy_audit(config, progress=update_progress)
    except BacktestJobCancelled:
        backtest_jobs.mark_cancelled(job_id)
    except asyncio.CancelledError:
        backtest_jobs.mark_cancelled(job_id)
        raise
    except (ProviderNotConfigured, ProviderError, ValueError) as exc:
        backtest_jobs.fail(job_id, str(exc))
    except Exception as exc:  # pragma: no cover
        backtest_jobs.fail(job_id, f"Exit 정책 연구 중 예상하지 못한 오류가 발생했습니다: {exc}")
    else:
        backtest_jobs.complete(job_id, result)


@router.post("/exit-policy-audit/jobs", status_code=202)
async def create_exit_policy_audit_job(payload: PullbackBacktestRequest) -> dict:
    settings = get_settings()
    job = backtest_jobs.create()
    task = asyncio.create_task(_run_exit_policy_audit_job(job.job_id, _config(payload), settings.krx_api_key))
    backtest_jobs.attach_task(job.job_id, task)
    return job.public()


@router.post("/exit-policy-selection")
async def exit_policy_selection(payload: ExitPolicySelectionRequest) -> dict:
    """Research-only multi-stock validation. Production Exit policy stays unchanged."""
    settings = get_settings()
    service = BacktestService(KrxProvider(settings.krx_api_key))
    try:
        return await service.run_exit_policy_selection(
            _selection_configs(payload),
            selection_config=ExitPolicySelectionConfig(
                minimum_stock_count=payload.minimum_stock_count,
                minimum_total_trades=payload.minimum_total_trades,
            ),
            post_target2_research_days=payload.post_target2_research_days,
        )
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _run_exit_policy_selection_job(
    job_id: str,
    configs: list[BacktestConfig],
    selection_config: ExitPolicySelectionConfig,
    post_target2_research_days: int,
    api_key: str | None,
) -> None:
    service = BacktestService(KrxProvider(api_key))

    def update_progress(payload: dict) -> None:
        if backtest_jobs.is_cancelled(job_id):
            raise BacktestJobCancelled()
        backtest_jobs.update_progress(job_id, payload)

    try:
        result = await service.run_exit_policy_selection(
            configs,
            selection_config=selection_config,
            post_target2_research_days=post_target2_research_days,
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
        backtest_jobs.fail(job_id, f"Exit 정책 선택 검증 중 예상하지 못한 오류가 발생했습니다: {exc}")
    else:
        backtest_jobs.complete(job_id, result)


@router.post("/exit-policy-selection/jobs", status_code=202)
async def create_exit_policy_selection_job(payload: ExitPolicySelectionRequest) -> dict:
    settings = get_settings()
    try:
        configs = _selection_configs(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    selection_config = ExitPolicySelectionConfig(
        minimum_stock_count=payload.minimum_stock_count,
        minimum_total_trades=payload.minimum_total_trades,
    )
    job = backtest_jobs.create()
    task = asyncio.create_task(
        _run_exit_policy_selection_job(
            job.job_id,
            configs,
            selection_config,
            payload.post_target2_research_days,
            settings.krx_api_key,
        )
    )
    backtest_jobs.attach_task(job.job_id, task)
    return job.public()


async def _run_exit_policy_validation_runner_job(
    job_id: str,
    runner_config: ExitPolicyValidationRunnerConfig,
    force_refresh: bool,
    api_key: str | None,
) -> None:
    service = BacktestService(KrxProvider(api_key))

    def update_progress(payload: dict) -> None:
        if backtest_jobs.is_cancelled(job_id):
            raise BacktestJobCancelled()
        backtest_jobs.update_progress(job_id, payload)

    try:
        result = await service.run_exit_policy_validation_runner(
            runner_config,
            force_refresh=force_refresh,
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
        backtest_jobs.fail(job_id, f"Exit 정책 검증 리포트 처리 중 예상하지 못한 오류가 발생했습니다: {exc}")
    else:
        backtest_jobs.complete(job_id, result)


@router.post("/exit-policy-validation/jobs", status_code=202)
async def create_exit_policy_validation_runner_job(payload: ExitPolicyValidationRunnerRequest) -> dict:
    settings = get_settings()
    try:
        runner_config = _validation_runner_config(payload)
        runner_config.validate()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = backtest_jobs.create()
    task = asyncio.create_task(
        _run_exit_policy_validation_runner_job(
            job.job_id,
            runner_config,
            payload.force_refresh,
            settings.krx_api_key,
        )
    )
    backtest_jobs.attach_task(job.job_id, task)
    return job.public()


@router.get("/exit-policy-validation/latest")
async def latest_exit_policy_validation_report() -> dict:
    report = ExitPolicyValidationCheckpoint().load_report()
    if report is None:
        return {"available": False, "report": None}
    return {"available": True, "report": report}


@router.get("/exit-policy-validation/report/{signature}")
async def exit_policy_validation_report_by_signature(signature: str) -> dict:
    cleaned = signature.strip().lower()
    if len(cleaned) != 20 or any(ch not in "0123456789abcdef" for ch in cleaned):
        raise HTTPException(status_code=400, detail="연구 결과 식별자가 올바르지 않습니다.")
    report = ExitPolicyValidationCheckpoint().load_report(cleaned)
    if report is None:
        return {"available": False, "report": None}
    return {"available": True, "report": report}


@router.get("/exit-policy-validation/history")
async def exit_policy_validation_history(limit: int = 20) -> dict:
    safe_limit = max(1, min(int(limit), 100))
    rows = ExitPolicyValidationCheckpoint().list_reports(safe_limit)
    return {"available": bool(rows), "rows": rows}


@router.post("/exit-policy-validation/audit")
async def run_exit_policy_validation_audit() -> dict:
    """Local-only reliability review of the latest completed validation report."""
    return await asyncio.to_thread(ExitPolicyResearchAuditor().run)


@router.get("/exit-policy-validation/audit/latest")
async def latest_exit_policy_validation_audit() -> dict:
    report = ExitPolicyResearchAuditStore().load()
    if report is None:
        return {"available": False, "report": None}
    return {"available": True, "report": report}


def _expanded_base_report(expected_signature: str | None = None) -> dict:
    report = ExitPolicyValidationCheckpoint().load_report()
    if report is None or str(report.get("status") or "") != "COMPLETED":
        raise ValueError("완료된 매도 기준 연구 결과가 있어야 확대 표본 검증을 진행할 수 있습니다.")
    signature = str(report.get("signature") or "")
    if expected_signature and expected_signature != signature:
        raise ValueError("화면에 표시된 연구 결과와 서버의 최신 연구 결과가 다릅니다. 화면을 새로고침한 뒤 다시 시도해 주세요.")
    return report


def _expanded_target(value: int) -> int:
    target = int(value)
    if target not in ALLOWED_EXPANDED_TARGETS:
        raise ValueError("확대 검증 종목 수는 20, 40, 60 중 하나여야 합니다.")
    return target


@router.post("/exit-policy-validation/expanded/plan")
async def plan_expanded_exit_policy_validation(payload: ExpandedSampleRequest) -> dict:
    settings = get_settings()
    try:
        base_report = _expanded_base_report(payload.base_signature)
        target = _expanded_target(payload.target_stocks)
        planner = ExpandedSamplePlanner(provider=KrxProvider(settings.krx_api_key))
        return await asyncio.to_thread(planner.plan, base_report, target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _run_expanded_sample_prepare_job(
    job_id: str,
    target_stocks: int,
    base_signature: str | None,
    api_key: str | None,
) -> None:
    def update_progress(payload: dict) -> None:
        if backtest_jobs.is_cancelled(job_id):
            raise BacktestJobCancelled()
        backtest_jobs.update_progress(job_id, payload)

    try:
        base_report = _expanded_base_report(base_signature)
        service = ExpandedSamplePreparationService(KrxProvider(api_key))
        result = await service.prepare(base_report, target_stocks, progress=update_progress)
    except BacktestJobCancelled:
        backtest_jobs.mark_cancelled(job_id)
    except asyncio.CancelledError:
        backtest_jobs.mark_cancelled(job_id)
        raise
    except (ProviderNotConfigured, ProviderError, ValueError) as exc:
        backtest_jobs.fail(job_id, str(exc))
    except Exception as exc:  # pragma: no cover
        backtest_jobs.fail(job_id, f"확대 표본 검증 데이터 준비 중 예상하지 못한 오류가 발생했습니다: {exc}")
    else:
        backtest_jobs.complete(job_id, result)


@router.post("/exit-policy-validation/expanded/prepare/jobs", status_code=202)
async def create_expanded_sample_prepare_job(payload: ExpandedSampleRequest) -> dict:
    settings = get_settings()
    try:
        _expanded_base_report(payload.base_signature)
        target = _expanded_target(payload.target_stocks)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = backtest_jobs.create()
    task = asyncio.create_task(
        _run_expanded_sample_prepare_job(job.job_id, target, payload.base_signature, settings.krx_api_key)
    )
    backtest_jobs.attach_task(job.job_id, task)
    return job.public()


async def _run_expanded_validation_job(
    job_id: str,
    target_stocks: int,
    base_signature: str | None,
    force_refresh: bool,
    api_key: str | None,
) -> None:
    def update_progress(payload: dict) -> None:
        if backtest_jobs.is_cancelled(job_id):
            raise BacktestJobCancelled()
        backtest_jobs.update_progress(job_id, payload)

    try:
        store = ExitPolicyValidationCheckpoint()
        base_report = _expanded_base_report(base_signature)
        target = _expanded_target(target_stocks)
        store.archive_report(base_report)
        planner = ExpandedSamplePlanner(provider=KrxProvider(api_key))
        plan = await asyncio.to_thread(planner.plan, base_report, target)
        if not plan.get("ready_to_run"):
            raise ValueError("확대 표본 검증에 필요한 저장 시세가 아직 충분하지 않습니다. 먼저 검증 데이터를 준비해 주세요.")
        runner_config = validation_config_from_report(base_report, target)
        service = BacktestService(KrxProvider(api_key))
        result = await service.run_exit_policy_validation_runner(
            runner_config,
            force_refresh=force_refresh,
            progress=update_progress,
            checkpoint_store=store,
            selected_candidates=list(plan.get("selected_stocks") or []),
        )
        if str(result.get("status") or "") == "COMPLETED":
            audit = ExitPolicyResearchAuditStore().load()
            comparison = compare_validation_reports(base_report, result, audit)
            result["expanded_revalidation"] = {
                **comparison,
                "target_stock_count": target,
                "sample_plan": {
                    "base_market_counts": plan.get("base_market_counts"),
                    "target_market_counts": plan.get("target_market_counts"),
                    "ready_stock_count": plan.get("ready_stock_count"),
                },
            }
            store.save_report(result)
    except BacktestJobCancelled:
        backtest_jobs.mark_cancelled(job_id)
    except asyncio.CancelledError:
        backtest_jobs.mark_cancelled(job_id)
        raise
    except (ProviderNotConfigured, ProviderError, ValueError) as exc:
        backtest_jobs.fail(job_id, str(exc))
    except Exception as exc:  # pragma: no cover
        backtest_jobs.fail(job_id, f"확대 표본 재검증 중 예상하지 못한 오류가 발생했습니다: {exc}")
    else:
        backtest_jobs.complete(job_id, result)


@router.post("/exit-policy-validation/expanded/jobs", status_code=202)
async def create_expanded_validation_job(payload: ExpandedSampleRequest) -> dict:
    settings = get_settings()
    try:
        _expanded_base_report(payload.base_signature)
        target = _expanded_target(payload.target_stocks)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = backtest_jobs.create()
    task = asyncio.create_task(
        _run_expanded_validation_job(
            job.job_id,
            target,
            payload.base_signature,
            payload.force_refresh,
            settings.krx_api_key,
        )
    )
    backtest_jobs.attach_task(job.job_id, task)
    return job.public()


@router.get("/exit-policy-production/status")
async def exit_policy_production_status() -> dict:
    return ProductionExitPolicyRegistry().status()


@router.post("/exit-policy-production/activate")
async def activate_exit_policy_production(force: bool = False) -> dict:
    try:
        mapping = ProductionExitPolicyRegistry().activate_from_latest_validation(force=force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "activated": True,
        "policy_version": mapping.get("policy_version"),
        "production_policy_changed": bool(mapping.get("production_policy_changed")),
        "validation_signature": mapping.get("validation_signature"),
        "strategies": mapping.get("strategies") or {},
    }


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


@router.post("/scanner/freshness")
async def prepare_scanner_freshness(payload: ScannerFreshnessRequest) -> dict:
    """Resolve and persist the latest confirmed EOD before a user starts Scanner analysis."""
    settings = get_settings()
    service = StockScannerService(KrxProvider(settings.krx_api_key))
    try:
        return await service.prepare_latest_confirmed_data(
            market_scope=payload.market_scope,
            known_data_date=payload.known_data_date,
        )
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
