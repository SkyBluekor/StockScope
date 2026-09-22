from __future__ import annotations

import asyncio
from typing import Any

from .execution_catalog import (
    ExecutionCatalogError,
    HistoricalExecutionCatalog,
    HistoricalExecutionRun,
)
from .execution_engine import ExecutionEngineError, HistoricalExecutionEngine


class ExecutionValidationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class HistoricalExecutionValidationService:
    """Run/resume one frozen VAL.2 execution validation cooperatively."""

    def __init__(
        self,
        catalog: HistoricalExecutionCatalog,
        engine: HistoricalExecutionEngine,
    ) -> None:
        self.catalog = catalog
        self.catalog.initialize()
        self.engine = engine

    async def run(
        self,
        execution_run_id: str,
        *,
        preclaimed: bool = False,
    ) -> HistoricalExecutionRun:
        run = self.catalog.get_run(execution_run_id)
        if run is None:
            raise ExecutionValidationError(
                "VAL2_RUN_NOT_FOUND",
                f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
            )

        if preclaimed:
            if run.status != "RUNNING":
                raise ExecutionValidationError(
                    "VAL2_RUN_INVALID_STATUS",
                    f"API에서 선점한 Execution Validation은 RUNNING이어야 합니다: "
                    f"{run.status}",
                )
        else:
            if run.status == "RUNNING":
                raise ExecutionValidationError(
                    "VAL2_RUN_ALREADY_RUNNING",
                    "이미 실행 중인 Execution Validation입니다.",
                )
            if run.status == "COMPLETED":
                raise ExecutionValidationError(
                    "VAL2_RUN_ALREADY_COMPLETED",
                    "이미 완료된 Execution Validation입니다.",
                )
            try:
                run = self.catalog.begin_run(execution_run_id)
            except ExecutionCatalogError as exc:
                raise ExecutionValidationError(exc.code, exc.message) from exc

        pending = self.catalog.pending_candidates(execution_run_id)
        for candidate in pending:
            if self.catalog.cancel_requested(execution_run_id):
                return self.catalog.mark_cancelled(execution_run_id)

            try:
                await asyncio.to_thread(
                    self.engine.evaluate_candidate,
                    execution_run_id,
                    candidate,
                )
            except ExecutionEngineError as exc:
                self.catalog.mark_failed(
                    execution_run_id,
                    exc.code,
                    exc.message,
                )
                raise ExecutionValidationError(exc.code, exc.message) from exc
            except ExecutionCatalogError as exc:
                self.catalog.mark_failed(
                    execution_run_id,
                    exc.code,
                    exc.message,
                )
                raise ExecutionValidationError(exc.code, exc.message) from exc
            except Exception as exc:
                code = "VAL2_EXECUTION_UNEXPECTED"
                message = (
                    "Execution Validation 후보 처리 중 예상하지 못한 오류가 "
                    f"발생했습니다: {exc}"
                )
                self.catalog.mark_failed(
                    execution_run_id,
                    code,
                    message,
                )
                raise ExecutionValidationError(code, message) from exc

            if self.catalog.cancel_requested(execution_run_id):
                return self.catalog.mark_cancelled(execution_run_id)

        final = self.catalog.get_run(execution_run_id)
        if final is None:
            raise ExecutionValidationError(
                "VAL2_RUN_NOT_FOUND",
                f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
            )
        if final.processed_candidate_count != final.source_candidate_count:
            code = "VAL2_RUN_INCOMPLETE"
            message = (
                "Execution Validation 처리 건수가 source candidate 수와 "
                f"일치하지 않습니다: "
                f"{final.processed_candidate_count}/{final.source_candidate_count}"
            )
            self.catalog.mark_failed(execution_run_id, code, message)
            raise ExecutionValidationError(code, message)

        try:
            return self.catalog.mark_completed(execution_run_id)
        except ExecutionCatalogError as exc:
            raise ExecutionValidationError(exc.code, exc.message) from exc
