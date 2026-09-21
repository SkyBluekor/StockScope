from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from app.simulation.sim3_market_provider import HistoricalMarketStoreProvider

from .models import decimal_text
from .service import RecommendationTrackingService, TrackingError
from .store import RecommendationTrackingRepository


class ScannerTrackRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=100)
    market: str = Field(min_length=1, max_length=24)
    recommendation_date: date
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


class LegacyTrackRecommendationRequest(ScannerTrackRequest):
    # Kept for one release so older frontends do not crash. The server still
    # refuses MANUAL through this endpoint and forces SCANNER provenance.
    source: str = "SCANNER"


class ManualTrackRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=100)
    market: str = Field(min_length=1, max_length=24)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _service() -> RecommendationTrackingService:
    default_db = _project_root() / "backend" / "runtime" / "tracking" / "recommendation_tracking.db"
    db = Path(os.getenv("STOCKSCOPE_TRACKING_DB", str(default_db)))
    return RecommendationTrackingService(RecommendationTrackingRepository(db), HistoricalMarketStoreProvider())


def _raise(error: TrackingError) -> None:
    if error.code == "TRACK_NOT_FOUND":
        status = 404
    elif error.code in {
        "TRACK_ITEM_CLOSED",
        "TRACK_SNAPSHOT_INTEGRITY_ERROR",
        "TRACK_SOURCE_SPOOF",
        "TRACK_MANUAL_SAME_DAY_REOPEN",
        "TRACK_DELETE_ACTIVE",
    }:
        status = 409
    else:
        status = 422
    raise HTTPException(status_code=status, detail={"code": error.code, "message": error.message})


def _dump(request: BaseModel) -> dict[str, Any]:
    return request.model_dump() if hasattr(request, "model_dump") else request.dict()


def _item_payload(service: RecommendationTrackingService, item) -> dict[str, Any]:
    payload = item.to_dict()
    performance = service.repository.get_performance(item.id)
    payload["performance"] = performance.to_dict() if performance else None
    return payload


def create_scanner_tracked_item(request: ScannerTrackRequest):
    service = _service()
    try:
        item, created = service.create_scanner(_dump(request))
    except TrackingError as error:
        _raise(error)
    return {"created": created, "item": _item_payload(service, item)}


def create_manual_tracked_item(request: ManualTrackRequest):
    service = _service()
    try:
        item, created = service.create_manual(_dump(request))
    except TrackingError as error:
        _raise(error)
    return {"created": created, "item": _item_payload(service, item)}


def preview_manual_tracked_item(
    ticker: str = Query(min_length=1, max_length=16),
    name: str = Query(min_length=1, max_length=100),
    market: str = Query(min_length=1, max_length=24),
):
    service = _service()
    try:
        preview = service.resolve_manual_reference({"ticker": ticker, "name": name, "market": market})
    except TrackingError as error:
        _raise(error)
    return {
        "ticker": preview["ticker"],
        "name": preview["name"],
        "market": preview["market"],
        "reference_date": preview["recommendation_date"].isoformat(),
        "reference_price": decimal_text(preview["reference_price"]),
    }


def create_tracked_recommendation(request: LegacyTrackRecommendationRequest):
    service = _service()
    try:
        item, created = service.create(_dump(request))
    except TrackingError as error:
        _raise(error)
    return {"created": created, "item": _item_payload(service, item)}


def list_tracked_recommendations(
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
):
    try:
        return _service().list_with_performance(status=status, source=source)
    except TrackingError as error:
        _raise(error)


def close_tracked_recommendation(recommendation_id: str):
    service = _service()
    try:
        item = service.close(recommendation_id)
    except TrackingError as error:
        _raise(error)
    return _item_payload(service, item)


def delete_tracked_recommendation(recommendation_id: str):
    service = _service()
    try:
        service.delete(recommendation_id)
    except TrackingError as error:
        _raise(error)
    return {"deleted": True, "id": recommendation_id}


def refresh_tracked_recommendation(recommendation_id: str):
    service = _service()
    try:
        performance = service.refresh(recommendation_id)
        item = service.repository.get(recommendation_id)
    except TrackingError as error:
        _raise(error)
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "TRACK_NOT_FOUND", "message": "Tracked item not found"})
    payload = item.to_dict()
    payload["performance"] = performance.to_dict()
    return payload


def refresh_active_recommendations():
    try:
        return _service().refresh_active()
    except TrackingError as error:
        _raise(error)
