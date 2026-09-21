from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from .models import RecommendationPerformance, TrackedRecommendation


@dataclass(frozen=True, slots=True)
class TradingObservation:
    trading_date: date
    bar: Any | None


def _pct(value: Decimal, reference: Decimal) -> Decimal:
    return ((value - reference) / reference * Decimal("100")).quantize(Decimal("0.0001"))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dec(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except Exception:
        return None
    return result if result.is_finite() and result > 0 else None


def _entry_touched_from_snapshot(item: TrackedRecommendation, *, low: Decimal, high: Decimal) -> bool | None:
    """Return True/False when the Scanner snapshot declares entry semantics.

    Legacy snapshots that only contain a naked entry price are intentionally not
    interpreted. A price plan can be RANGE, ABOVE (breakout), or AT_OR_BELOW
    (pullback/limit-style condition). Tracking records only whether price reached
    the declared condition; it does not claim an execution/fill.
    """
    if not (item.has_scanner_source or item.source == "SCANNER"):
        return None
    source_snapshot = item.scanner_snapshot if item.scanner_snapshot else item.snapshot
    candidate = _as_dict(source_snapshot.get("candidate"))
    guide = _as_dict(candidate.get("entry_risk_guide"))
    rule = _as_dict(guide.get("price_rule"))
    kind = str(rule.get("kind") or "").strip().upper()
    if kind == "RANGE":
        lower = _dec(rule.get("display_range_low") or rule.get("range_low"))
        upper = _dec(rule.get("display_range_high") or rule.get("range_high"))
        if lower is None or upper is None:
            return None
        if lower > upper:
            lower, upper = upper, lower
        return high >= lower and low <= upper
    if kind == "ABOVE":
        trigger = _dec(rule.get("display_trigger_price") or rule.get("trigger_price"))
        return None if trigger is None else high >= trigger
    if kind == "AT_OR_BELOW":
        trigger = _dec(rule.get("display_trigger_price") or rule.get("trigger_price"))
        return None if trigger is None else low <= trigger
    return None


def calculate_performance(
    recommendation: TrackedRecommendation,
    observations: Iterable[TradingObservation],
    *,
    updated_at: datetime,
) -> RecommendationPerformance:
    """Calculate post-tracking performance using D+1 and later only.

    `observations` represent market trading days. A market day may have no stock
    bar (suspension/missing data); it still counts toward 5D/10D/20D. The start
    day itself is excluded defensively even if supplied.
    """
    ordered = sorted(
        (obs for obs in observations if obs.trading_date > recommendation.recommendation_date),
        key=lambda obs: obs.trading_date,
    )

    latest_date: date | None = None
    latest_close: Decimal | None = None
    highest_price: Decimal | None = None
    highest_date: date | None = None
    lowest_price: Decimal | None = None
    lowest_date: date | None = None
    return_5d: Decimal | None = None
    return_10d: Decimal | None = None
    return_20d: Decimal | None = None

    entry_touched = False
    entry_touch_date: date | None = None
    stop_touched = False
    stop_touch_date: date | None = None
    target1_touched = False
    target1_touch_date: date | None = None
    target2_touched = False
    target2_touch_date: date | None = None

    reference = recommendation.reference_price

    for index, obs in enumerate(ordered, start=1):
        bar = obs.bar
        if bar is None:
            continue

        high = Decimal(str(bar.high))
        low = Decimal(str(bar.low))
        close = Decimal(str(bar.close))

        latest_date = obs.trading_date
        latest_close = close

        if highest_price is None or high > highest_price:
            highest_price = high
            highest_date = obs.trading_date
        if lowest_price is None or low < lowest_price:
            lowest_price = low
            lowest_date = obs.trading_date

        # Horizon index is based on market trading days, not days with a stock bar.
        if index == 5:
            return_5d = _pct(close, reference)
        elif index == 10:
            return_10d = _pct(close, reference)
        elif index == 20:
            return_20d = _pct(close, reference)

        if not entry_touched:
            entry_result = _entry_touched_from_snapshot(recommendation, low=low, high=high)
            if entry_result is True:
                entry_touched = True
                entry_touch_date = obs.trading_date

        if not stop_touched and recommendation.stop_price is not None and low <= recommendation.stop_price:
            stop_touched = True
            stop_touch_date = obs.trading_date

        if not target1_touched and recommendation.target1_price is not None and high >= recommendation.target1_price:
            target1_touched = True
            target1_touch_date = obs.trading_date

        if not target2_touched and recommendation.target2_price is not None and high >= recommendation.target2_price:
            target2_touched = True
            target2_touch_date = obs.trading_date

    market_date = ordered[-1].trading_date if ordered else None
    price_status = "WAITING" if latest_close is None else ("FRESH" if latest_date == market_date else "STALE")

    return RecommendationPerformance(
        recommendation_id=recommendation.id,
        market_date=market_date,
        latest_date=latest_date,
        latest_close=latest_close,
        price_status=price_status,
        trading_days=len(ordered),
        current_return_pct=_pct(latest_close, reference) if latest_close is not None else None,
        mfe_pct=_pct(highest_price, reference) if highest_price is not None else None,
        mae_pct=_pct(lowest_price, reference) if lowest_price is not None else None,
        highest_price=highest_price,
        highest_date=highest_date,
        lowest_price=lowest_price,
        lowest_date=lowest_date,
        return_5d=return_5d,
        return_10d=return_10d,
        return_20d=return_20d,
        entry_touched=entry_touched,
        entry_touch_date=entry_touch_date,
        stop_touched=stop_touched,
        stop_touch_date=stop_touch_date,
        target1_touched=target1_touched,
        target1_touch_date=target1_touch_date,
        target2_touched=target2_touched,
        target2_touch_date=target2_touch_date,
        updated_at=updated_at,
    )
