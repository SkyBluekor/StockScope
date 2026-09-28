from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException

from app.core.config import PROJECT_ROOT
from app.event_evidence import EventEvidenceContractError, EventEvidenceProductQuery


router = APIRouter(tags=["event-evidence"])


def _simulation_db() -> Path:
    return Path(
        os.getenv("STOCKSCOPE_SIM_DB")
        or PROJECT_ROOT
        / "backend"
        / "runtime"
        / "simulation"
        / "simulation.db"
    )


def _query() -> EventEvidenceProductQuery:
    return EventEvidenceProductQuery(_simulation_db())


def _raise(error: EventEvidenceContractError) -> None:
    if error.code == "EVENT_EVIDENCE_STORE_NOT_FOUND":
        status = 503
    elif error.code == "EVENT_EVIDENCE_SCHEMA_NOT_READY":
        status = 409
    elif error.code in {
        "EVENT_EVIDENCE_MARKET_INVALID",
        "STOCK_CODE_INVALID",
    }:
        status = 400
    else:
        status = 422
    raise HTTPException(
        status_code=status,
        detail={
            "code": error.code,
            "message": error.message,
        },
    ) from error


@router.get("/stocks/{code}/event-evidence")
def stock_event_evidence(
    code: str,
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI",
):
    try:
        return _query().stock_status(code, market)
    except EventEvidenceContractError as error:
        _raise(error)
