from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import PROJECT_ROOT
from app.feedback import (
    EvidenceSelector,
    FeedbackAdapterError,
    FeedbackCatalogError,
    FeedbackService,
)


router = APIRouter(prefix="/simulation/feedback", tags=["simulation-feedback"])

DEFAULT_SIMULATION_DB = PROJECT_ROOT / "backend" / "runtime" / "simulation" / "simulation.db"
DEFAULT_TRACKING_DB = PROJECT_ROOT / "backend" / "runtime" / "tracking" / "recommendation_tracking.db"


class FeedbackSelectorRequest(BaseModel):
    source_type: Literal["TRACKING", "VALIDATION", "EXECUTION", "BACKTEST"]
    source_id: str = Field(min_length=1, max_length=200)
    date_from: str | None = None
    date_to: str | None = None
    market: Literal["KOSPI", "KOSDAQ"] | None = None
    strategy: str | None = Field(default=None, max_length=100)

    def domain(self) -> EvidenceSelector:
        return EvidenceSelector(
            source_type=self.source_type,
            source_id=self.source_id,
            date_from=self.date_from,
            date_to=self.date_to,
            market=self.market,
            strategy=self.strategy,
        )


class FeedbackCohortRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    sources: list[FeedbackSelectorRequest] = Field(min_length=1, max_length=12)
    filters: dict = Field(default_factory=dict)


class FeedbackReportRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=200)


def _simulation_path() -> Path:
    return Path(
        os.getenv("STOCKSCOPE_SIM_DB")
        or DEFAULT_SIMULATION_DB
    )


def _tracking_path() -> Path:
    return Path(
        os.getenv("STOCKSCOPE_TRACKING_DB")
        or DEFAULT_TRACKING_DB
    )


def _service() -> FeedbackService:
    return FeedbackService(
        _simulation_path(),
        _tracking_path(),
    )


def _raise(error: Exception) -> None:
    code = getattr(error, "code", "FEEDBACK_ERROR")
    message = getattr(error, "message", str(error))
    if code in {
        "FEEDBACK_COHORT_NOT_FOUND",
        "FEEDBACK_REPORT_NOT_FOUND",
        "FEEDBACK_VALIDATION_NOT_FOUND",
        "FEEDBACK_EXECUTION_NOT_FOUND",
        "FEEDBACK_BACKTEST_JOB_NOT_FOUND",
        "FEEDBACK_SOURCE_STORE_NOT_FOUND",
    }:
        status = 404
    elif code in {
        "FEEDBACK_MIGRATION_REQUIRED",
        "FEEDBACK_SCHEMA_UNSUPPORTED",
        "FEEDBACK_TRACKING_SCHEMA_UNAVAILABLE",
        "FEEDBACK_VALIDATION_SCHEMA_UNAVAILABLE",
        "FEEDBACK_EXECUTION_SCHEMA_UNAVAILABLE",
        "FEEDBACK_BACKTEST_NOT_COMPLETED",
    }:
        status = 409
    else:
        status = 422
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
    ) from error


@router.get("/evidence")
def get_feedback_evidence(
    source_type: Literal["TRACKING", "VALIDATION", "EXECUTION", "BACKTEST"],
    source_id: str = Query(min_length=1, max_length=200),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    market: Literal["KOSPI", "KOSDAQ"] | None = Query(default=None),
    strategy: str | None = Query(default=None, max_length=100),
):
    try:
        return _service().evidence(
            EvidenceSelector(
                source_type=source_type,
                source_id=source_id,
                date_from=date_from,
                date_to=date_to,
                market=market,
                strategy=strategy,
            )
        )
    except (FeedbackAdapterError, FeedbackCatalogError) as error:
        _raise(error)


@router.post("/cohorts", status_code=201)
def create_feedback_cohort(request: FeedbackCohortRequest):
    try:
        return _service().create_cohort(
            client_request_id=request.client_request_id,
            name=request.name,
            selectors=[source.domain() for source in request.sources],
            filters=dict(request.filters),
        )
    except (FeedbackAdapterError, FeedbackCatalogError) as error:
        _raise(error)


@router.get("/cohorts")
def list_feedback_cohorts():
    try:
        return _service().catalog.list_cohorts()
    except FeedbackCatalogError as error:
        _raise(error)


@router.get("/cohorts/{cohort_id}")
def get_feedback_cohort(cohort_id: str):
    try:
        return _service().get_cohort(cohort_id)
    except (FeedbackAdapterError, FeedbackCatalogError) as error:
        _raise(error)


@router.post("/cohorts/{cohort_id}/reports", status_code=201)
def create_feedback_report(
    cohort_id: str,
    request: FeedbackReportRequest,
):
    try:
        return _service().create_report(
            cohort_id=cohort_id,
            client_request_id=request.client_request_id,
        )
    except (FeedbackAdapterError, FeedbackCatalogError) as error:
        _raise(error)


@router.get("/reports/{report_id}")
def get_feedback_report(report_id: str):
    try:
        return _service().get_report(report_id)
    except (FeedbackAdapterError, FeedbackCatalogError) as error:
        _raise(error)
