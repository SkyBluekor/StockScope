from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.holdings.catalog import DEFAULT_HOLDINGS_DB, HoldingsCatalog
from app.watch import WatchService


router = APIRouter(prefix="/watch", tags=["watch"])


def _service() -> WatchService:
    raw = os.getenv("STOCKSCOPE_HOLDINGS_DB")
    path = Path(raw) if raw else DEFAULT_HOLDINGS_DB
    return WatchService(HoldingsCatalog(path))


@router.get("/status")
def watch_status() -> dict[str, object]:
    return _service().get_status()


@router.get("/positions/{position_id}")
def watch_position(position_id: str) -> dict[str, object]:
    return _service().get_position_status(position_id)


@router.get("/notifications")
def watch_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
) -> dict[str, object]:
    rows = _service().list_notifications(
        limit=limit,
        unread_only=unread_only,
    )
    return {
        "items": rows,
        "count": len(rows),
    }


@router.post("/notifications/{notification_id}/read")
def read_watch_notification(notification_id: str) -> dict[str, object]:
    result = _service().mark_notification_read(notification_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "WATCH_NOTIFICATION_NOT_FOUND",
                "message": "해당 Watch 알림을 찾을 수 없습니다.",
            },
        )
    return result
