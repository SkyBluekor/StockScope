from __future__ import annotations

from dataclasses import asdict, dataclass
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
    status: str
    created_at: datetime
    closed_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "name": self.name,
            "market": self.market,
            "source": self.source,
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
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }
