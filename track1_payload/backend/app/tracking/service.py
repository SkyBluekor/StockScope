from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from .models import TrackedRecommendation
from .store import RecommendationTrackingRepository


class TrackingError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _money(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TrackingError("TRACK_INVALID_PRICE", f"Invalid price: {value!r}") from exc
    if not result.is_finite() or result <= 0:
        raise TrackingError("TRACK_INVALID_PRICE", f"Invalid price: {value!r}")
    return result


class RecommendationTrackingService:
    def __init__(self, repository: RecommendationTrackingRepository, market_provider: Any):
        self.repository = repository
        self.market_provider = market_provider
        self.repository.initialize()

    def create(self, payload: dict[str, Any]) -> tuple[TrackedRecommendation, bool]:
        ticker = str(payload.get("ticker") or "").strip()
        name = str(payload.get("name") or "").strip()
        market = str(payload.get("market") or "").strip().upper()
        source = str(payload.get("source") or "SCANNER").strip().upper()
        day = payload.get("recommendation_date")
        if isinstance(day, str):
            day = date.fromisoformat(day)
        if not ticker or not name or not market or not isinstance(day, date):
            raise TrackingError("TRACK_REQUIRED_FIELD", "ticker, name, market and recommendation_date are required")
        if source not in {"SCANNER", "MANUAL"}:
            raise TrackingError("TRACK_INVALID_SOURCE", "source must be SCANNER or MANUAL")

        existing = self.repository.find_duplicate(source=source, market=market, ticker=ticker, recommendation_date=day)
        if existing:
            return existing, False

        bar = self.market_provider.get_bar(market, ticker, day)
        if bar is None:
            raise TrackingError(
                "TRACK_REFERENCE_PRICE_MISSING",
                f"No confirmed market close for {ticker} on {day.isoformat()}",
            )

        snapshot = payload.get("snapshot")
        if not isinstance(snapshot, dict):
            snapshot = {}
        now = datetime.now(timezone.utc)
        item = TrackedRecommendation(
            id=str(uuid4()), ticker=ticker, name=name, market=bar.market, source=source,
            recommendation_date=day, reference_price=bar.close,
            scanner_version=(str(payload["scanner_version"]).strip() if payload.get("scanner_version") else None),
            scanner_baseline=(str(payload["scanner_baseline"]).strip() if payload.get("scanner_baseline") else None),
            strategy=(str(payload["strategy"]).strip() if payload.get("strategy") else None),
            decision_status=(str(payload["decision_status"]).strip() if payload.get("decision_status") else None),
            rank=int(payload["rank"]) if payload.get("rank") not in (None, "") else None,
            entry_price=_money(payload.get("entry_price")), stop_price=_money(payload.get("stop_price")),
            target1_price=_money(payload.get("target1_price")), target2_price=_money(payload.get("target2_price")),
            snapshot=snapshot, status="ACTIVE", created_at=now, closed_at=None,
        )
        self.repository.insert(item)
        return item, True

    def list(self, *, status: str | None = None) -> list[TrackedRecommendation]:
        normalized = status.strip().upper() if status else None
        if normalized and normalized not in {"ACTIVE", "CLOSED"}:
            raise TrackingError("TRACK_INVALID_STATUS", "status must be ACTIVE or CLOSED")
        return self.repository.list(status=normalized)

    def close(self, item_id: str) -> TrackedRecommendation:
        item = self.repository.get(item_id)
        if item is None:
            raise TrackingError("TRACK_NOT_FOUND", f"Tracked recommendation not found: {item_id}")
        if item.status == "CLOSED":
            return item
        updated = self.repository.close(item_id, datetime.now(timezone.utc))
        if updated is None:
            raise TrackingError("TRACK_NOT_FOUND", f"Tracked recommendation not found: {item_id}")
        return updated
