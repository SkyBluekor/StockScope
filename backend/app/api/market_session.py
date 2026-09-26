from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Query, Response
from starlette.concurrency import run_in_threadpool

from app.market_session import DomesticMarketSessionResponse, market_session_service


router = APIRouter(prefix="/market-session", tags=["market-session"])


@router.get("/domestic", response_model=DomesticMarketSessionResponse)
async def domestic_market_session(
    response: Response,
    venue: Literal["INTEGRATED"] = Query("INTEGRATED"),
) -> DomesticMarketSessionResponse:
    response.headers["Cache-Control"] = "no-store"
    session = await run_in_threadpool(
        market_session_service.get_session,
        venue,
    )
    return DomesticMarketSessionResponse(**asdict(session))
