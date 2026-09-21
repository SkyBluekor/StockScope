from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True, slots=True)
class TrackedRecommendation:
    id: str
    ticker: str
    name: str
    market: str
    source: str
    recommendation_date: date
    reference_price: Decimal
    scanner_version: str | None
    scanner_baseline: str | None
    strategy: str | None
    decision_status: str | None
    rank: int | None
    entry_price: Decimal | None
    stop_price: Decimal | None
    target1_price: Decimal | None
    target2_price: Decimal | None
    snapshot: dict[str, Any]
    snapshot_schema_version: int
    snapshot_hash: str
    status: str
    created_at: datetime
    closed_at: datetime | None
    closed_market_date: date | None
    close_performance_status: str | None
    has_scanner_source: bool = False
    has_manual_source: bool = False
    scanner_snapshot: dict[str, Any] = field(default_factory=dict)
    scanner_snapshot_hash: str | None = None
    scanner_attached_at: datetime | None = None

    @property
    def scanner_source(self) -> bool:
        return self.has_scanner_source or self.source == "SCANNER"

    @property
    def manual_source(self) -> bool:
        return self.has_manual_source or self.source == "MANUAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "name": self.name,
            "market": self.market,
            "source": self.source,
            "has_scanner_source": self.scanner_source,
            "has_manual_source": self.manual_source,
            "sources": [
                source
                for source, enabled in (("SCANNER", self.scanner_source), ("MANUAL", self.manual_source))
                if enabled
            ],
            "recommendation_date": self.recommendation_date.isoformat(),
            "reference_price": decimal_text(self.reference_price),
            "scanner_version": self.scanner_version,
            "scanner_baseline": self.scanner_baseline,
            "strategy": self.strategy,
            "decision_status": self.decision_status,
            "rank": self.rank,
            "entry_price": decimal_text(self.entry_price),
            "stop_price": decimal_text(self.stop_price),
            "target1_price": decimal_text(self.target1_price),
            "target2_price": decimal_text(self.target2_price),
            "snapshot": self.snapshot,
            "snapshot_schema_version": self.snapshot_schema_version,
            "snapshot_hash": self.snapshot_hash,
            "scanner_snapshot": self.scanner_snapshot,
            "scanner_snapshot_hash": self.scanner_snapshot_hash,
            "scanner_attached_at": self.scanner_attached_at.isoformat() if self.scanner_attached_at else None,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "closed_market_date": self.closed_market_date.isoformat() if self.closed_market_date else None,
            "close_performance_status": self.close_performance_status,
        }


@dataclass(frozen=True, slots=True)
class RecommendationPerformance:
    recommendation_id: str
    market_date: date | None
    latest_date: date | None
    latest_close: Decimal | None
    price_status: str
    trading_days: int
    current_return_pct: Decimal | None
    mfe_pct: Decimal | None
    mae_pct: Decimal | None
    highest_price: Decimal | None
    highest_date: date | None
    lowest_price: Decimal | None
    lowest_date: date | None
    return_5d: Decimal | None
    return_10d: Decimal | None
    return_20d: Decimal | None
    entry_touched: bool
    entry_touch_date: date | None
    stop_touched: bool
    stop_touch_date: date | None
    target1_touched: bool
    target1_touch_date: date | None
    target2_touched: bool
    target2_touch_date: date | None
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "market_date": self.market_date.isoformat() if self.market_date else None,
            "latest_date": self.latest_date.isoformat() if self.latest_date else None,
            "latest_close": decimal_text(self.latest_close),
            "price_status": self.price_status,
            "trading_days": self.trading_days,
            "current_return_pct": decimal_text(self.current_return_pct),
            "mfe_pct": decimal_text(self.mfe_pct),
            "mae_pct": decimal_text(self.mae_pct),
            "highest_price": decimal_text(self.highest_price),
            "highest_date": self.highest_date.isoformat() if self.highest_date else None,
            "lowest_price": decimal_text(self.lowest_price),
            "lowest_date": self.lowest_date.isoformat() if self.lowest_date else None,
            "return_5d": decimal_text(self.return_5d),
            "return_10d": decimal_text(self.return_10d),
            "return_20d": decimal_text(self.return_20d),
            "entry_touched": self.entry_touched,
            "entry_touch_date": self.entry_touch_date.isoformat() if self.entry_touch_date else None,
            "stop_touched": self.stop_touched,
            "stop_touch_date": self.stop_touch_date.isoformat() if self.stop_touch_date else None,
            "target1_touched": self.target1_touched,
            "target1_touch_date": self.target1_touch_date.isoformat() if self.target1_touch_date else None,
            "target2_touched": self.target2_touched,
            "target2_touch_date": self.target2_touch_date.isoformat() if self.target2_touch_date else None,
            "updated_at": self.updated_at.isoformat(),
        }
