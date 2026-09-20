from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class HistoricalMarketBar:
    stock_code: str
    market: str
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        if not self.stock_code.strip() or not self.market.strip():
            raise ValueError("market bar stock_code and market are required")
        for name in ("open", "high", "low", "close"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ValueError(f"{name} must be a positive Decimal")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high is below another OHLC value")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low is above another OHLC value")
        if self.volume < 0:
            raise ValueError("volume must not be negative")


@runtime_checkable
class SimulationMarketDataProvider(Protocol):
    def has_trading_day(self, day: date) -> bool: ...
    def next_trading_day(self, day: date) -> date | None: ...
    def previous_trading_day(self, day: date) -> date | None: ...
    def get_bar(self, market: str, stock_code: str, trading_date: date) -> HistoricalMarketBar | None: ...


def _compact(day: date) -> str:
    return day.strftime("%Y%m%d")


def _to_decimal(value: Any, *, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"invalid {field}: {value!r}")
    return result


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


class HistoricalMarketStoreProvider:
    """Offline adapter over StockScope HistoricalMarketStore.

    It never calls KRX/KIS/NAVER. It only consumes local rows already available
    through HistoricalMarketStore.
    """

    def __init__(self, store: Any | None = None, *, calendar_markets: tuple[str, ...] = ("KOSPI", "KOSDAQ")):
        if store is None:
            from app.backtest.market_store import HistoricalMarketStore  # local import: optional in isolated tests
            store = HistoricalMarketStore()
        self.store = store
        self.calendar_markets = tuple(calendar_markets)
        if not self.calendar_markets:
            raise ValueError("calendar_markets must not be empty")

    def has_trading_day(self, day: date) -> bool:
        key = _compact(day)
        return all(self.store.latest_complete_date(market, "stock", key) == key for market in self.calendar_markets)

    def next_trading_day(self, day: date) -> date | None:
        current = day + timedelta(days=1)
        for _ in range(370):
            if current.weekday() < 5 and self.has_trading_day(current):
                return current
            current += timedelta(days=1)
        return None

    def previous_trading_day(self, day: date) -> date | None:
        current = day - timedelta(days=1)
        for _ in range(370):
            if current.weekday() < 5 and self.has_trading_day(current):
                return current
            current -= timedelta(days=1)
        return None

    def get_bar(self, market: str, stock_code: str, trading_date: date) -> HistoricalMarketBar | None:
        key = _compact(trading_date)
        markets = self.calendar_markets if market.upper() in {"KRX", "ALL"} else (market.upper(),)
        for candidate_market in markets:
            series_map = self.store.stock_series_many(candidate_market, [stock_code], key, key)
            series = (series_map or {}).get(stock_code)
            if series is None:
                continue
            rows = list(getattr(series, "rows", {}).values())
            for raw in rows:
                row = dict(raw)
                row_day = str(_first(row, "date", "trading_date", "bas_dd") or "").replace("-", "")
                if row_day and row_day != key:
                    continue
                try:
                    return HistoricalMarketBar(
                        stock_code=stock_code,
                        market=candidate_market,
                        trading_date=trading_date,
                        open=_to_decimal(_first(row, "open", "open_price", "opn_prc"), field="open"),
                        high=_to_decimal(_first(row, "high", "high_price", "hgpr"), field="high"),
                        low=_to_decimal(_first(row, "low", "low_price", "lwpr"), field="low"),
                        close=_to_decimal(_first(row, "close", "close_price", "clpr"), field="close"),
                        volume=int(Decimal(str(_first(row, "volume", "acc_trdvol", "trdvol") or 0))),
                    )
                except (ValueError, InvalidOperation):
                    return None
        return None
