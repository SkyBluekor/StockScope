from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from app.backtest.production_exit_policy import production_policy_cache_token
from app.horizon import resolve_horizon_context
from app.simulation.execution_catalog import EXECUTION_POLICY_VERSION

from .catalog import ProspectiveCatalog, ProspectiveCatalogError
from .evaluation import ProspectiveEvaluationError, ProspectiveEvaluator
from .models import EvaluationProtocolSpec, ProspectiveCaptureRequest


class ProspectiveService:
    def __init__(
        self,
        simulation_db: Path,
        market_store_db: Path,
    ) -> None:
        self.catalog = ProspectiveCatalog(simulation_db)
        self.evaluator = ProspectiveEvaluator(market_store_db)

    @staticmethod
    def capture_request_from_scanner_payload(payload: Any) -> ProspectiveCaptureRequest:
        horizon = resolve_horizon_context(getattr(payload, "horizon_intent", None))
        return ProspectiveCaptureRequest(
            market_scope=str(getattr(payload, "market_scope", "ALL") or "ALL").upper(),
            requested_as_of=getattr(payload, "as_of_date", None),
            candidate_limit=int(getattr(payload, "candidate_limit", 5) or 5),
            horizon_intent=horizon.intent,
            horizon_policy_version=horizon.policy_version,
        )

    def try_begin_scanner_capture(
        self,
        *,
        source_job_id: str,
        payload: Any,
    ) -> dict[str, Any]:
        request = self.capture_request_from_scanner_payload(payload)
        try:
            capture = self.catalog.begin_capture(
                source_job_id=source_job_id,
                request=request,
            )
        except ProspectiveCatalogError as exc:
            if exc.code in {
                "PROSPECTIVE_MIGRATION_REQUIRED",
                "PROSPECTIVE_SCHEMA_UNSUPPORTED",
            }:
                return {
                    "status": "NOT_READY",
                    "code": exc.code,
                    "message": exc.message,
                }
            raise
        return {
            "status": capture["status"],
            "capture_id": capture["id"],
        }

    def try_finalize_scanner_capture(
        self,
        *,
        source_job_id: str,
        payload: Any,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        request = self.capture_request_from_scanner_payload(payload)
        try:
            capture = self.catalog.finalize_capture(
                source_job_id=source_job_id,
                request=request,
                result=result,
            )
        except ProspectiveCatalogError as exc:
            if exc.code in {
                "PROSPECTIVE_MIGRATION_REQUIRED",
                "PROSPECTIVE_SCHEMA_UNSUPPORTED",
            }:
                return {
                    "status": "NOT_READY",
                    "code": exc.code,
                    "message": exc.message,
                }
            try:
                self.catalog.mark_capture_terminal(
                    source_job_id,
                    status="FAILED",
                    error_code=exc.code,
                    error_message=exc.message,
                )
            except Exception:
                pass
            return {
                "status": "FAILED",
                "code": exc.code,
                "message": exc.message,
            }
        except Exception as exc:
            try:
                self.catalog.mark_capture_terminal(
                    source_job_id,
                    status="FAILED",
                    error_code="PROSPECTIVE_CAPTURE_FAILED",
                    error_message=str(exc),
                )
            except Exception:
                pass
            return {
                "status": "FAILED",
                "code": "PROSPECTIVE_CAPTURE_FAILED",
                "message": str(exc),
            }
        return {
            "status": capture["status"],
            "capture_id": capture["id"],
            "canonical_capture_id": capture["canonical_capture_id"],
            "returned_candidate_count": capture["returned_candidate_count"],
        }

    def try_mark_scanner_capture_terminal(
        self,
        *,
        source_job_id: str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        try:
            self.catalog.mark_capture_terminal(
                source_job_id,
                status=status,
                error_code=error_code,
                error_message=error_message,
            )
        except ProspectiveCatalogError as exc:
            if exc.code not in {
                "PROSPECTIVE_MIGRATION_REQUIRED",
                "PROSPECTIVE_SCHEMA_UNSUPPORTED",
            }:
                raise

    @staticmethod
    def _parse_date(value: str | None, label: str) -> str | None:
        if value in (None, ""):
            return None
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError as exc:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_PROTOCOL_DATE_INVALID",
                f"{label}은 YYYY-MM-DD 형식이어야 합니다.",
            ) from exc

    def create_protocol(
        self,
        *,
        client_request_id: str,
        name: str,
        market_scope: str,
        strategy: str | None,
        development_start: str | None,
        development_end: str | None,
        holdout_start: str | None,
        holdout_end: str | None,
        purge_trading_days: int = 20,
        max_holding_days: int = 20,
        round_trip_cost_pct: float = 0.0,
        fee_pct: float = 0.0,
        tax_pct: float = 0.0,
        slippage_pct: float = 0.0,
        execution_mode: str = "PRODUCTION_POLICY",
    ) -> dict[str, Any]:
        market = market_scope.strip().upper()
        if market not in {"ALL", "KOSPI", "KOSDAQ"}:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_PROTOCOL_MARKET_INVALID",
                "market_scope은 ALL, KOSPI, KOSDAQ 중 하나여야 합니다.",
            )
        dev_start = self._parse_date(development_start, "development_start")
        dev_end = self._parse_date(development_end, "development_end")
        hold_start = self._parse_date(holdout_start, "holdout_start")
        hold_end = self._parse_date(holdout_end, "holdout_end")

        if not all((dev_start, dev_end, hold_start, hold_end)):
            raise ProspectiveCatalogError(
                "PROSPECTIVE_TIME_SPLIT_REQUIRED",
                "시간 분리 평가에는 Development와 Holdout 시작/종료일이 모두 필요합니다.",
            )
        if bool(dev_start) != bool(dev_end):
            raise ProspectiveCatalogError(
                "PROSPECTIVE_DEVELOPMENT_RANGE_INCOMPLETE",
                "Development 시작일과 종료일을 함께 지정해야 합니다.",
            )
        if bool(hold_start) != bool(hold_end):
            raise ProspectiveCatalogError(
                "PROSPECTIVE_HOLDOUT_RANGE_INCOMPLETE",
                "Holdout 시작일과 종료일을 함께 지정해야 합니다.",
            )
        if dev_start and dev_end and dev_start > dev_end:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_DEVELOPMENT_RANGE_INVALID",
                "Development 시작일은 종료일보다 늦을 수 없습니다.",
            )
        if hold_start and hold_end and hold_start > hold_end:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_HOLDOUT_RANGE_INVALID",
                "Holdout 시작일은 종료일보다 늦을 수 없습니다.",
            )
        if dev_end and hold_start and dev_end >= hold_start:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_SPLIT_OVERLAP",
                "Development 종료일은 Holdout 시작일보다 앞서야 합니다.",
            )
        if purge_trading_days < 20:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_PURGE_TOO_SHORT",
                "현재 D+20 관찰 정의를 사용할 때 purge는 최소 20거래일이어야 합니다.",
            )
        if max_holding_days < 1 or max_holding_days > 120:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_MAX_HOLD_INVALID",
                "max_holding_days는 1~120이어야 합니다.",
            )
        for label, value in {
            "round_trip_cost_pct": round_trip_cost_pct,
            "fee_pct": fee_pct,
            "tax_pct": tax_pct,
            "slippage_pct": slippage_pct,
        }.items():
            if value < 0 or value > 5:
                raise ProspectiveCatalogError(
                    "PROSPECTIVE_COST_INVALID",
                    f"{label}은 0~5 범위여야 합니다.",
                )
        mode = execution_mode.strip().upper()
        if mode not in {"PRODUCTION_POLICY", "OBSERVATION_ONLY"}:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_EXECUTION_MODE_INVALID",
                "execution_mode는 PRODUCTION_POLICY 또는 OBSERVATION_ONLY여야 합니다.",
            )

        spec = EvaluationProtocolSpec(
            name=name.strip() or "Prospective 평가",
            market_scope=market,
            strategy=strategy.strip() if strategy and strategy.strip() else None,
            development_start=dev_start,
            development_end=dev_end,
            holdout_start=hold_start,
            holdout_end=hold_end,
            observation_windows=(5, 10, 20),
            purge_trading_days=int(purge_trading_days),
            execution_mode=mode,
            max_holding_days=int(max_holding_days),
            round_trip_cost_pct=float(round_trip_cost_pct),
            fee_pct=float(fee_pct),
            tax_pct=float(tax_pct),
            slippage_pct=float(slippage_pct),
            execution_policy_version=EXECUTION_POLICY_VERSION,
            exit_policy_token=(
                production_policy_cache_token()
                if mode == "PRODUCTION_POLICY"
                else None
            ),
        )
        return self.catalog.create_protocol(
            client_request_id=client_request_id.strip(),
            spec=spec,
        )

    def create_evaluation_run(
        self,
        *,
        protocol_id: str,
        client_request_id: str,
    ) -> dict[str, Any]:
        return self.catalog.create_evaluation_run(
            protocol_id=protocol_id,
            client_request_id=client_request_id,
        )

    def execute_evaluation_run(self, run_id: str) -> dict[str, Any]:
        run = self.catalog.begin_evaluation_run(run_id)
        if run["status"] == "COMPLETED":
            return self.evaluation_detail(run_id)

        protocol = self.catalog.get_protocol(run["protocol_id"])
        if protocol is None:
            self.catalog.fail_evaluation_run(
                run_id,
                error_code="PROSPECTIVE_PROTOCOL_NOT_FOUND",
                error_message="평가 protocol을 찾을 수 없습니다.",
            )
            raise ProspectiveCatalogError(
                "PROSPECTIVE_PROTOCOL_NOT_FOUND",
                "평가 protocol을 찾을 수 없습니다.",
            )

        spec = dict(protocol["spec"])
        try:
            samples = self.catalog.list_samples(
                date_from=(
                    spec.get("development_start")
                    or spec.get("holdout_start")
                ),
                date_to=(
                    spec.get("holdout_end")
                    or spec.get("development_end")
                ),
                market_scope=spec.get("market_scope"),
                strategy=spec.get("strategy"),
            )
            units: list[dict[str, Any]] = []
            for index, sample in enumerate(samples, start=1):
                if self.catalog.evaluation_cancel_requested(run_id):
                    self.catalog.mark_evaluation_cancelled(run_id)
                    return self.evaluation_detail(run_id)
                units.append(
                    self.evaluator.evaluate_sample(sample=sample, spec=spec)
                )
                self.catalog.update_evaluation_progress(run_id, index)
            counts, summary = self.evaluator.summarize(
                protocol=protocol,
                units=units,
            )
            self.catalog.replace_evaluation_units(
                run_id=run_id,
                units=units,
                counts=counts,
                report_summary=summary,
            )
        except (ProspectiveCatalogError, ProspectiveEvaluationError) as exc:
            self.catalog.fail_evaluation_run(
                run_id,
                error_code=exc.code,
                error_message=exc.message,
            )
            raise
        except Exception as exc:
            self.catalog.fail_evaluation_run(
                run_id,
                error_code="PROSPECTIVE_EVALUATION_FAILED",
                error_message=str(exc),
            )
            raise ProspectiveEvaluationError(
                "PROSPECTIVE_EVALUATION_FAILED",
                str(exc),
            ) from exc
        return self.evaluation_detail(run_id)

    def cancel_evaluation_run(self, run_id: str) -> dict[str, Any]:
        return self.catalog.request_evaluation_cancel(run_id)

    def evaluation_detail(self, run_id: str) -> dict[str, Any]:
        run = self.catalog.get_evaluation_run(run_id)
        if run is None:
            raise ProspectiveCatalogError(
                "PROSPECTIVE_EVALUATION_RUN_NOT_FOUND",
                "평가 run을 찾을 수 없습니다.",
            )
        return {
            "run": run,
            "protocol": self.catalog.get_protocol(run["protocol_id"]),
            "report": self.catalog.get_report_for_run(run_id),
            "units": self.catalog.list_units(run_id) if run["status"] == "COMPLETED" else [],
        }
