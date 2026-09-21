from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from .models import RecommendationPerformance, TrackedRecommendation
from .performance import TradingObservation, calculate_performance
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
    MAX_REFRESH_TRADING_DAYS = 5200

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

    def list_with_performance(self, *, status: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in self.list(status=status):
            payload = item.to_dict()
            performance = self.repository.get_performance(item.id)
            payload["performance"] = performance.to_dict() if performance else None
            rows.append(payload)
        return rows

    def close(self, item_id: str) -> TrackedRecommendation:
        item = self.repository.get(item_id)
        if item is None:
            raise TrackingError("TRACK_NOT_FOUND", f"Tracked recommendation not found: {item_id}")
        if item.status == "CLOSED":
            return item
        # Best effort: freeze the most recent available performance before closing.
        # A market-data gap must not prevent the user from closing a recommendation.
        try:
            self.refresh(item_id)
        except Exception:
            pass
        updated = self.repository.close(item_id, datetime.now(timezone.utc))
        if updated is None:
            raise TrackingError("TRACK_NOT_FOUND", f"Tracked recommendation not found: {item_id}")
        return updated

    def _observations(self, item: TrackedRecommendation) -> list[TradingObservation]:
        observations: list[TradingObservation] = []
        current = item.recommendation_date
        for _ in range(self.MAX_REFRESH_TRADING_DAYS):
            next_day = self.market_provider.next_trading_day(current)
            if next_day is None:
                break
            observations.append(
                TradingObservation(
                    trading_date=next_day,
                    bar=self.market_provider.get_bar(item.market, item.ticker, next_day),
                )
            )
            current = next_day
        else:
            raise TrackingError("TRACK_REFRESH_LIMIT", "Tracking refresh exceeded the supported trading-day range")
        return observations

    def refresh(self, item_id: str) -> RecommendationPerformance:
        item = self.repository.get(item_id)
        if item is None:
            raise TrackingError("TRACK_NOT_FOUND", f"Tracked recommendation not found: {item_id}")

        performance = calculate_performance(
            item,
            self._observations(item),
            updated_at=datetime.now(timezone.utc),
        )
        self.repository.upsert_performance(performance)
        return performance

    def refresh_active(self) -> dict[str, Any]:
        active = self.repository.list(status="ACTIVE")
        updated = 0
        unchanged = 0
        failed = 0
        latest_market_date: date | None = None
        errors: list[dict[str, str]] = []

        for item in active:
            before = self.repository.get_performance(item.id)
            try:
                after = self.refresh(item.id)
            except Exception as exc:  # isolate one recommendation from the bulk refresh
                failed += 1
                errors.append({"id": item.id, "ticker": item.ticker, "message": str(exc)})
                continue

            if after.market_date and (latest_market_date is None or after.market_date > latest_market_date):
                latest_market_date = after.market_date

            comparable_before = before.to_dict() if before else None
            comparable_after = after.to_dict()
            if comparable_before:
                comparable_before.pop("updated_at", None)
            comparable_after.pop("updated_at", None)
            if comparable_before == comparable_after:
                unchanged += 1
            else:
                updated += 1

        return {
            "updated": updated,
            "unchanged": unchanged,
            "failed": failed,
            "latest_market_date": latest_market_date.isoformat() if latest_market_date else None,
            "errors": errors,
        }
