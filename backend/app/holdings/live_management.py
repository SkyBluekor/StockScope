from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from app.quotes.models import CachedQuoteObservation
from app.quotes.service import observe_cached_quote

from .catalog import DEFAULT_HOLDINGS_DB, HoldingsCatalog
from .management import (
    HoldingManagementService,
    HoldingsManagementError,
    management_distance,
)
from .read_only_catalog import ReadOnlyHoldingsCatalog


LiveManagementState = Literal["FRESH", "STALE", "UNAVAILABLE"]


@dataclass(frozen=True, slots=True)
class LiveManagementQuote:
    provider: str
    mode: str
    venue: str
    price: str
    provider_timestamp: str | None
    received_at: str
    age_ms: int
    freshness_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "mode": self.mode,
            "venue": self.venue,
            "price": self.price,
            "provider_timestamp": self.provider_timestamp,
            "received_at": self.received_at,
            "age_ms": self.age_ms,
            "freshness_seconds": self.freshness_seconds,
        }


@dataclass(frozen=True, slots=True)
class LiveManagementPosition:
    position_id: str
    active_plan_id: str | None
    plan_version: int | None
    distances: dict[str, dict[str, str | None]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "active_plan_id": self.active_plan_id,
            "plan_version": self.plan_version,
            "distances": self.distances,
        }


@dataclass(frozen=True, slots=True)
class LiveManagementProximity:
    stock_id: str
    market: str
    ticker: str
    available: bool
    state: LiveManagementState
    reason_code: str | None
    quote: LiveManagementQuote | None
    positions: tuple[LiveManagementPosition, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_id": self.stock_id,
            "market": self.market,
            "ticker": self.ticker,
            "available": self.available,
            "state": self.state,
            "reason_code": self.reason_code,
            "quote": self.quote.to_dict() if self.quote is not None else None,
            "positions": [item.to_dict() for item in self.positions],
        }


class HoldingsLiveManagementService:
    """Read-only price proximity to already-applied holding management plans."""

    def __init__(
        self,
        holdings_db: Path | None = None,
        *,
        catalog: HoldingsCatalog | None = None,
        quote_observer: Callable[..., CachedQuoteObservation] = observe_cached_quote,
    ) -> None:
        self.catalog = catalog or ReadOnlyHoldingsCatalog(
            Path(holdings_db or DEFAULT_HOLDINGS_DB)
        )
        self.quote_observer = quote_observer
        self.management = HoldingManagementService(self.catalog)

    @staticmethod
    def _empty_distances() -> dict[str, dict[str, str | None]]:
        empty = {"level": None, "amount": None, "pct": None}
        return {
            "stop": dict(empty),
            "target1": dict(empty),
            "target2": dict(empty),
        }

    @staticmethod
    def _distance(level, price) -> dict[str, str | None]:
        result = management_distance(level, price)
        return {
            "level": None if level is None else format(level, "f"),
            "amount": result["amount"],
            "pct": result["pct"],
        }

    def calculate(self, stock_id: str) -> LiveManagementProximity:
        stock = self.catalog.get_monitored_stock(stock_id)
        if stock is None:
            raise HoldingsManagementError(
                "HOLD_STOCK_NOT_FOUND",
                "등록된 종목을 찾을 수 없습니다.",
            )

        open_positions = self.catalog.list_positions(stock.id, status="OPEN")
        if not open_positions:
            return LiveManagementProximity(
                stock_id=stock.id,
                market=stock.market,
                ticker=stock.ticker,
                available=False,
                state="UNAVAILABLE",
                reason_code="HOLD_POSITION_ABSENT",
                quote=None,
                positions=(),
            )

        active_by_position = {
            position.id: self.management.get_active_plan(position.id)
            for position in open_positions
        }
        if not any(active_by_position.values()):
            return LiveManagementProximity(
                stock_id=stock.id,
                market=stock.market,
                ticker=stock.ticker,
                available=False,
                state="UNAVAILABLE",
                reason_code="ACTIVE_PLAN_ABSENT",
                quote=None,
                positions=tuple(
                    LiveManagementPosition(
                        position_id=position.id,
                        active_plan_id=None,
                        plan_version=None,
                        distances=self._empty_distances(),
                    )
                    for position in open_positions
                ),
            )

        observed = self.quote_observer(
            market=stock.market,
            ticker=stock.ticker,
            venue="INTEGRATED",
        )
        if not observed.capable:
            return LiveManagementProximity(
                stock_id=stock.id,
                market=stock.market,
                ticker=stock.ticker,
                available=False,
                state="UNAVAILABLE",
                reason_code=observed.reason or "KIS_QUOTE_NOT_CONFIGURED",
                quote=None,
                positions=(),
            )
        if (
            not observed.present
            or observed.current_price is None
            or observed.current_price <= 0
            or observed.received_at is None
            or observed.age_ms is None
            or observed.freshness_seconds is None
        ):
            return LiveManagementProximity(
                stock_id=stock.id,
                market=stock.market,
                ticker=stock.ticker,
                available=False,
                state="UNAVAILABLE",
                reason_code=observed.reason or "QUOTE_NOT_OBSERVED",
                quote=None,
                positions=(),
            )

        state: LiveManagementState = (
            "STALE"
            if observed.age_ms > int(observed.freshness_seconds * 1000)
            else "FRESH"
        )
        price = observed.current_price
        rows: list[LiveManagementPosition] = []
        for position in open_positions:
            active = active_by_position[position.id]
            if active is None:
                rows.append(
                    LiveManagementPosition(
                        position_id=position.id,
                        active_plan_id=None,
                        plan_version=None,
                        distances=self._empty_distances(),
                    )
                )
                continue
            rows.append(
                LiveManagementPosition(
                    position_id=position.id,
                    active_plan_id=active.id,
                    plan_version=active.plan_version,
                    distances={
                        "stop": self._distance(active.stop_price, price),
                        "target1": self._distance(active.target1_price, price),
                        "target2": self._distance(active.target2_price, price),
                    },
                )
            )

        quote = LiveManagementQuote(
            provider=observed.provider or "KIS",
            mode=observed.mode or "SNAPSHOT",
            venue=observed.venue,
            price=format(price, "f"),
            provider_timestamp=observed.provider_timestamp,
            received_at=observed.received_at.isoformat(),
            age_ms=observed.age_ms,
            freshness_seconds=observed.freshness_seconds,
        )
        return LiveManagementProximity(
            stock_id=stock.id,
            market=stock.market,
            ticker=stock.ticker,
            available=True,
            state=state,
            reason_code="QUOTE_SNAPSHOT_STALE" if state == "STALE" else None,
            quote=quote,
            positions=tuple(rows),
        )
