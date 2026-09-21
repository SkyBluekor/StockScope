from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from .models import RecommendationPerformance, TrackedRecommendation
from .performance import TradingObservation, calculate_performance
from .store import RecommendationTrackingRepository, snapshot_digest


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


def _day(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise TrackingError("TRACK_INVALID_DATE", f"Invalid date: {value!r}") from exc
    return None


class RecommendationTrackingService:
    MAX_REFRESH_TRADING_DAYS = 5200
    SNAPSHOT_SCHEMA_VERSION = 1

    def __init__(self, repository: RecommendationTrackingRepository, market_provider: Any):
        self.repository = repository
        self.market_provider = market_provider
        self.repository.initialize()

    @staticmethod
    def _identity(payload: dict[str, Any]) -> tuple[str, str, str]:
        ticker = str(payload.get("ticker") or "").strip()
        name = str(payload.get("name") or "").strip()
        market = str(payload.get("market") or "").strip().upper()
        if not ticker or not name or not market:
            raise TrackingError("TRACK_REQUIRED_FIELD", "ticker, name and market are required")
        return ticker, name, market

    def _latest_market_day(self, market: str) -> date:
        store = getattr(self.market_provider, "store", None)
        latest_complete = getattr(store, "latest_complete_date", None)
        if callable(latest_complete):
            raw = latest_complete(market, "stock", date.today().strftime("%Y%m%d"))
            if raw:
                compact = str(raw).replace("-", "")
                if len(compact) == 8 and compact.isdigit():
                    return date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))
        cursor = date.today()
        for _ in range(370):
            if self.market_provider.has_trading_day(cursor):
                return cursor
            cursor = date.fromordinal(cursor.toordinal() - 1)
        raise TrackingError("TRACK_MARKET_DATE_MISSING", f"No confirmed market date is available for {market}")

    def resolve_manual_reference(self, payload: dict[str, Any]) -> dict[str, Any]:
        ticker, name, market = self._identity(payload)
        day = self._latest_market_day(market)
        bar = self.market_provider.get_bar(market, ticker, day)
        if bar is None:
            raise TrackingError(
                "TRACK_REFERENCE_PRICE_MISSING",
                f"No confirmed market close for {ticker} on {day.isoformat()}",
            )
        return {
            "ticker": ticker,
            "name": name,
            "market": bar.market,
            "recommendation_date": day,
            "reference_price": bar.close,
        }

    @staticmethod
    def _scanner_metadata(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "scanner_version": str(payload["scanner_version"]).strip() if payload.get("scanner_version") else None,
            "scanner_baseline": str(payload["scanner_baseline"]).strip() if payload.get("scanner_baseline") else None,
            "strategy": str(payload["strategy"]).strip() if payload.get("strategy") else None,
            "decision_status": str(payload["decision_status"]).strip() if payload.get("decision_status") else None,
            "rank": int(payload["rank"]) if payload.get("rank") not in (None, "") else None,
            "entry_price": _money(payload.get("entry_price")),
            "stop_price": _money(payload.get("stop_price")),
            "target1_price": _money(payload.get("target1_price")),
            "target2_price": _money(payload.get("target2_price")),
        }

    def create_scanner(self, payload: dict[str, Any]) -> tuple[TrackedRecommendation, bool]:
        ticker, name, market = self._identity(payload)
        day = _day(payload.get("recommendation_date"))
        if day is None:
            raise TrackingError("TRACK_REQUIRED_FIELD", "recommendation_date is required for Scanner tracking")
        if day > date.today():
            raise TrackingError("TRACK_FUTURE_DATE", "Future recommendation dates are not allowed")

        bar = self.market_provider.get_bar(market, ticker, day)
        if bar is None:
            raise TrackingError(
                "TRACK_REFERENCE_PRICE_MISSING",
                f"No confirmed market close for {ticker} on {day.isoformat()}",
            )
        snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
        metadata = self._scanner_metadata(payload)

        same_baseline = self.repository.find_same_baseline(
            market=bar.market, ticker=ticker, recommendation_date=day, reference_price=bar.close
        )
        if same_baseline is not None:
            if same_baseline.scanner_source:
                return same_baseline, False
            attached = self.repository.attach_scanner(
                same_baseline.id,
                metadata=metadata,
                snapshot=snapshot,
                attached_at=datetime.now(timezone.utc),
            )
            return attached, False

        existing = self.repository.find_duplicate(source="SCANNER", market=bar.market, ticker=ticker, recommendation_date=day)
        if existing:
            return existing, False

        now = datetime.now(timezone.utc)
        item = TrackedRecommendation(
            id=str(uuid4()), ticker=ticker, name=name, market=bar.market, source="SCANNER",
            recommendation_date=day, reference_price=bar.close,
            scanner_version=metadata["scanner_version"], scanner_baseline=metadata["scanner_baseline"],
            strategy=metadata["strategy"], decision_status=metadata["decision_status"], rank=metadata["rank"],
            entry_price=metadata["entry_price"], stop_price=metadata["stop_price"],
            target1_price=metadata["target1_price"], target2_price=metadata["target2_price"],
            snapshot=snapshot, snapshot_schema_version=self.SNAPSHOT_SCHEMA_VERSION,
            snapshot_hash=snapshot_digest(snapshot), status="ACTIVE", created_at=now, closed_at=None,
            closed_market_date=None, close_performance_status=None,
            has_scanner_source=True, has_manual_source=False,
            scanner_snapshot=snapshot, scanner_snapshot_hash=snapshot_digest(snapshot), scanner_attached_at=now,
        )
        self.repository.insert(item)
        return item, True

    def create_manual(self, payload: dict[str, Any]) -> tuple[TrackedRecommendation, bool]:
        ticker, name, market = self._identity(payload)
        resolved = self.resolve_manual_reference({"ticker": ticker, "name": name, "market": market})
        day = resolved["recommendation_date"]
        reference_price = resolved["reference_price"]

        same_baseline = self.repository.find_same_baseline(
            market=resolved["market"], ticker=ticker, recommendation_date=day, reference_price=reference_price
        )
        if same_baseline is not None:
            if same_baseline.manual_source:
                if same_baseline.status == "CLOSED":
                    raise TrackingError(
                        "TRACK_MANUAL_SAME_DAY_REOPEN",
                        "같은 확정 거래일에 종료한 종목은 다음 거래일 데이터가 생긴 뒤 다시 추적할 수 있습니다.",
                    )
                return same_baseline, False
            if same_baseline.status == "CLOSED":
                raise TrackingError(
                    "TRACK_MANUAL_SAME_DAY_REOPEN",
                    "같은 기준일·기준가의 추적 기록이 이미 종료되었습니다. 다음 거래일부터 다시 추적할 수 있습니다.",
                )
            return self.repository.attach_manual(same_baseline.id), False

        active = self.repository.find_active_manual(market=resolved["market"], ticker=ticker)
        if active:
            return active, False

        existing_same_day = self.repository.find_duplicate(
            source="MANUAL", market=resolved["market"], ticker=ticker, recommendation_date=day
        )
        if existing_same_day:
            if existing_same_day.status == "CLOSED":
                raise TrackingError(
                    "TRACK_MANUAL_SAME_DAY_REOPEN",
                    "같은 확정 거래일에 종료한 종목은 다음 거래일 데이터가 생긴 뒤 다시 추적할 수 있습니다.",
                )
            return existing_same_day, False

        snapshot = {
            "kind": "MANUAL_TRACKING",
            "instrument": {"ticker": ticker, "name": name, "market": resolved["market"]},
            "reference_market_date": day.isoformat(),
        }
        now = datetime.now(timezone.utc)
        item = TrackedRecommendation(
            id=str(uuid4()), ticker=ticker, name=name, market=resolved["market"], source="MANUAL",
            recommendation_date=day, reference_price=reference_price,
            scanner_version=None, scanner_baseline=None, strategy=None, decision_status=None, rank=None,
            entry_price=None, stop_price=None, target1_price=None, target2_price=None,
            snapshot=snapshot, snapshot_schema_version=self.SNAPSHOT_SCHEMA_VERSION,
            snapshot_hash=snapshot_digest(snapshot), status="ACTIVE", created_at=now, closed_at=None,
            closed_market_date=None, close_performance_status=None,
            has_scanner_source=False, has_manual_source=True,
        )
        self.repository.insert(item)
        return item, True

    def create(self, payload: dict[str, Any]) -> tuple[TrackedRecommendation, bool]:
        requested_source = str(payload.get("source") or "SCANNER").strip().upper()
        if requested_source != "SCANNER":
            raise TrackingError("TRACK_SOURCE_SPOOF", "Use the manual tracking endpoint for directly selected stocks")
        return self.create_scanner(payload)

    def list(self, *, status: str | None = None, source: str | None = None) -> list[TrackedRecommendation]:
        normalized_status = status.strip().upper() if status else None
        normalized_source = source.strip().upper() if source else None
        if normalized_status and normalized_status not in {"ACTIVE", "CLOSED"}:
            raise TrackingError("TRACK_INVALID_STATUS", "status must be ACTIVE or CLOSED")
        if normalized_source and normalized_source not in {"SCANNER", "MANUAL"}:
            raise TrackingError("TRACK_INVALID_SOURCE", "source must be SCANNER or MANUAL")
        return self.repository.list(status=normalized_status, source=normalized_source)

    def list_with_performance(self, *, status: str | None = None, source: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in self.list(status=status, source=source):
            payload = item.to_dict()
            performance = self.repository.get_performance(item.id)
            payload["performance"] = performance.to_dict() if performance else None
            rows.append(payload)
        return rows

    def close(self, item_id: str) -> TrackedRecommendation:
        item = self.repository.get(item_id)
        if item is None:
            raise TrackingError("TRACK_NOT_FOUND", f"Tracked item not found: {item_id}")
        if item.status == "CLOSED":
            return item
        try:
            performance = self.refresh(item_id)
        except TrackingError as exc:
            if exc.code in {"TRACK_SNAPSHOT_INTEGRITY_ERROR", "TRACK_ITEM_CLOSED"}:
                raise
            performance = self.repository.get_performance(item_id)
        except Exception:
            performance = self.repository.get_performance(item_id)
        closed_market_date = performance.market_date if performance else None
        updated = self.repository.close(item_id, datetime.now(timezone.utc), closed_market_date)
        if updated is None:
            raise TrackingError("TRACK_NOT_FOUND", f"Tracked item not found: {item_id}")
        return updated

    def delete(self, item_id: str) -> None:
        item = self.repository.get(item_id)
        if item is None:
            raise TrackingError("TRACK_NOT_FOUND", f"Tracked item not found: {item_id}")
        if item.status != "CLOSED":
            raise TrackingError("TRACK_DELETE_ACTIVE", "추적 중인 기록은 먼저 종료한 뒤 삭제할 수 있습니다.")
        if not self.repository.delete(item_id):
            raise TrackingError("TRACK_NOT_FOUND", f"Tracked item not found: {item_id}")

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
            raise TrackingError("TRACK_NOT_FOUND", f"Tracked item not found: {item_id}")
        if item.status == "CLOSED":
            raise TrackingError("TRACK_ITEM_CLOSED", "종료된 추적 기록은 성과를 다시 갱신하지 않습니다.")
        if not self.repository.verify_snapshot(item):
            raise TrackingError("TRACK_SNAPSHOT_INTEGRITY_ERROR", "저장된 추적 Snapshot 무결성 검증에 실패했습니다.")

        performance = calculate_performance(item, self._observations(item), updated_at=datetime.now(timezone.utc))
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
            except Exception as exc:
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
