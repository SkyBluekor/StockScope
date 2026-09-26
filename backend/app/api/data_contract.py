from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Path, Query, Response

from app.data_contract import ReadOnlyDataStateReader
from app.data_contract.builder import build_stock_data_contract
from app.data_contract.schema import ChartRange, StockDataContract


router = APIRouter(prefix="/data-contract", tags=["data-contract"])


@router.get("/stocks/{ticker}", response_model=StockDataContract)
def stock_data_contract(
    response: Response,
    ticker: str = Path(..., pattern=r"^\d{6}$"),
    market: Literal["KOSPI", "KOSDAQ"] = Query(...),
    chart_range: ChartRange | None = Query(default=None, alias="range"),
    job_id: str | None = Query(default=None, min_length=1, max_length=128),
) -> StockDataContract:
    """Return a read-only snapshot of already-existing stock resources.

    This endpoint does not prepare data, run analysis, call providers, create jobs,
    issue brokerage tokens, or mutate local persistence.
    """
    response.headers["Cache-Control"] = "no-store"
    reader = ReadOnlyDataStateReader()
    observed = reader.read_stock_state(
        market,
        ticker,
        known_job_id=job_id,
    )
    return build_stock_data_contract(
        observed,
        chart_range=chart_range,
        job_id=job_id,
    )
