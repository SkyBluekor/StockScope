from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from app.simulation.sim3_market_provider import HistoricalMarketStoreProvider

from .service import RecommendationTrackingService, TrackingError
from .store import RecommendationTrackingRepository


class TrackRecommendationRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=100)
    market: str = Field(min_length=1, max_length=24)
    recommendation_date: date
    source: str = "SCANNER"
    scanner_version: str | None = None
    scanner_baseline: str | None = None
    strategy: str | None = None
    decision_status: str | None = None
    rank: int | None = None
    entry_price: str | float | int | None = None
    stop_price: str | float | int | None = None
    target1_price: str | float | int | None = None
    target2_price: str | float | int | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _service() -> RecommendationTrackingService:
    default_db = _project_root() / "backend" / "runtime" / "tracking" / "recommendation_tracking.db"
    db = Path(os.getenv("STOCKSCOPE_TRACKING_DB", str(default_db)))
    return RecommendationTrackingService(RecommendationTrackingRepository(db), HistoricalMarketStoreProvider())


def _raise(error: TrackingError) -> None:
    status = 404 if error.code == "TRACK_NOT_FOUND" else 422
    raise HTTPException(status_code=status, detail={"code": error.code, "message": error.message})


def create_tracked_recommendation(request: TrackRecommendationRequest):
    try:
        item, created = _service().create(request.model_dump() if hasattr(request, "model_dump") else request.dict())
    except TrackingError as error:
        _raise(error)
    return {"created": created, "item": item.to_dict()}


def list_tracked_recommendations(status: str | None = Query(default=None)):
    try:
        rows = _service().list(status=status)
    except TrackingError as error:
        _raise(error)
    return [row.to_dict() for row in rows]


def close_tracked_recommendation(recommendation_id: str):
    try:
        item = _service().close(recommendation_id)
    except TrackingError as error:
        _raise(error)
    return item.to_dict()
