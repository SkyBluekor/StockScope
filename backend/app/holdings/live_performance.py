from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from app.quotes.models import CachedQuoteObservation
from app.quotes.service import observe_cached_quote

from .catalog import DEFAULT_HOLDINGS_DB, HoldingsCatalog, HoldingsCatalogError
from .performance import (
    HoldingPerformance,
    HoldingPerformanceService,
    HoldingValuation,
    HoldingsPerformanceError,
)


LivePerformanceState = Literal["FRESH", "STALE", "UNAVAILABLE"]


def _decimal_text(value) -> str | None:
    return None if value is None else format(value, "f")


class ReadOnlyHoldingsCatalog(HoldingsCatalog):
    """HoldingsCatalog read surface backed by SQLite mode=ro with no initialization."""

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise HoldingsCatalogError(
                "HOLDINGS_STORE_NOT_FOUND",
                "Holdings 저장소를 찾을 수 없습니다.",
            )
        uri = f"file:{self.db_path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


@dataclass(frozen=True, slots=True)
class LiveQuoteBasis:
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
class LiveHoldingPerformance:
    stock_id: str
    market: str
    ticker: str
    available: bool
    state: LivePerformanceState
    reason_code: str | None
    quote: LiveQuoteBasis | None
    performance: HoldingPerformance | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_id": self.stock_id,
            "market": self.market,
            "ticker": self.ticker,
            "available": self.available,
            "state": self.state,
            "reason_code": self.reason_code,
            "quote": self.quote.to_dict() if self.quote is not None else None,
            "performance": (
                self.performance.to_dict()
                if self.performance is not None
                else None
            ),
        }


class HoldingsLivePerformanceService:
    """Read-only live valuation over ledger state and an already-observed quote."""

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
        self.performance = HoldingPerformanceService(self.catalog)

    def calculate(self, stock_id: str) -> LiveHoldingPerformance:
        stock = self.catalog.get_monitored_stock(stock_id)
        if stock is None:
            raise HoldingsPerformanceError(
                "HOLD_STOCK_NOT_FOUND",
                "등록된 종목을 찾을 수 없습니다.",
            )

        open_positions = self.catalog.list_positions(stock.id, status="OPEN")
        if not open_positions:
            return LiveHoldingPerformance(
                stock_id=stock.id,
                market=stock.market,
                ticker=stock.ticker,
                available=False,
                state="UNAVAILABLE",
                reason_code="HOLD_POSITION_ABSENT",
                quote=None,
                performance=None,
            )

        observed = self.quote_observer(
            market=stock.market,
            ticker=stock.ticker,
            venue="INTEGRATED",
        )
        if not observed.capable:
            return LiveHoldingPerformance(
                stock_id=stock.id,
                market=stock.market,
                ticker=stock.ticker,
                available=False,
                state="UNAVAILABLE",
                reason_code=observed.reason or "KIS_QUOTE_NOT_CONFIGURED",
                quote=None,
                performance=None,
            )
        if (
            not observed.present
            or observed.current_price is None
            or observed.received_at is None
            or observed.age_ms is None
            or observed.freshness_seconds is None
        ):
            return LiveHoldingPerformance(
                stock_id=stock.id,
                market=stock.market,
                ticker=stock.ticker,
                available=False,
                state="UNAVAILABLE",
                reason_code=observed.reason or "QUOTE_NOT_OBSERVED",
                quote=None,
                performance=None,
            )

        state: LivePerformanceState = (
            "STALE"
            if observed.age_ms > int(observed.freshness_seconds * 1000)
            else "FRESH"
        )
        valuation = HoldingValuation(
            available=True,
            market_date=None,
            price=observed.current_price,
            source="KIS_REST_SNAPSHOT",
            message=None,
        )
        calculated = self.performance.calculate_with_valuation(
            stock.id,
            valuation,
        )
        quote = LiveQuoteBasis(
            provider=observed.provider or "KIS",
            mode=observed.mode or "SNAPSHOT",
            venue=observed.venue,
            price=_decimal_text(observed.current_price) or "0",
            provider_timestamp=observed.provider_timestamp,
            received_at=observed.received_at.isoformat(),
            age_ms=observed.age_ms,
            freshness_seconds=observed.freshness_seconds,
        )
        return LiveHoldingPerformance(
            stock_id=stock.id,
            market=stock.market,
            ticker=stock.ticker,
            available=True,
            state=state,
            reason_code="QUOTE_SNAPSHOT_STALE" if state == "STALE" else None,
            quote=quote,
            performance=calculated,
        )
