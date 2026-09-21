from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


class ValidationPeriodError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _month(value: str) -> tuple[int, int]:
    try:
        year_text, month_text = value.strip().split("-", 1)
        year, month = int(year_text), int(month_text)
        if year < 1990 or month < 1 or month > 12:
            raise ValueError
        return year, month
    except Exception as exc:
        raise ValidationPeriodError("SIM_VALIDATION_INVALID_MONTH", f"Invalid YYYY-MM value: {value!r}") from exc


def _month_key(day: date) -> str:
    return day.strftime("%Y-%m")


def _first_day(value: str) -> date:
    year, month = _month(value)
    return date(year, month, 1)


def _last_day(value: str) -> date:
    year, month = _month(value)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return next_month - timedelta(days=1)


def _shift_month(value: str, delta: int) -> str:
    year, month = _month(value)
    serial = year * 12 + (month - 1) + delta
    return f"{serial // 12:04d}-{serial % 12 + 1:02d}"


def _compact_to_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    compact = str(value).replace("-", "")
    if len(compact) != 8 or not compact.isdigit():
        return None
    return date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))


@dataclass(frozen=True, slots=True)
class HistoricalValidationPeriodResolver:
    store: Any
    minimum_trading_days: int = 60

    def _markets(self, market_scope: str) -> tuple[str, ...]:
        scope = market_scope.strip().upper()
        if scope == "ALL":
            return ("KOSPI", "KOSDAQ")
        if scope in {"KOSPI", "KOSDAQ"}:
            return (scope,)
        raise ValidationPeriodError("SIM_VALIDATION_INVALID_MARKET", "market_scope must be ALL, KOSPI or KOSDAQ")

    def latest_common_date(self, market_scope: str) -> date:
        latest_dates: list[date] = []
        as_of = date.today().strftime("%Y%m%d")
        for market in self._markets(market_scope):
            parsed = _compact_to_date(self.store.latest_complete_date(market, "stock", as_of))
            if parsed is None:
                raise ValidationPeriodError(
                    "SIM_VALIDATION_MARKET_DATA_MISSING",
                    f"No complete Market Store date is available for {market}",
                )
            latest_dates.append(parsed)
        return min(latest_dates)

    def _is_complete_day(self, day: date, markets: tuple[str, ...]) -> bool:
        if day.weekday() >= 5:
            return False
        key = day.strftime("%Y%m%d")
        return all(self.store.latest_complete_date(market, "stock", key) == key for market in markets)

    def preview(
        self,
        *,
        market_scope: str = "ALL",
        preset: str | None = None,
        start_month: str | None = None,
        end_month: str | None = None,
    ) -> dict[str, Any]:
        markets = self._markets(market_scope)
        latest = self.latest_common_date(market_scope)
        latest_month = _month_key(latest)

        if preset:
            normalized = preset.strip().lower()
            months = {"6m": 6, "1y": 12, "2y": 24}.get(normalized)
            if months is None:
                raise ValidationPeriodError("SIM_VALIDATION_INVALID_PRESET", "preset must be 6m, 1y or 2y")
            requested_end = latest_month
            requested_start = _shift_month(latest_month, -(months - 1))
        else:
            if not start_month or not end_month:
                raise ValidationPeriodError(
                    "SIM_VALIDATION_MONTH_REQUIRED",
                    "start_month and end_month are required for direct selection",
                )
            _month(start_month)
            _month(end_month)
            requested_start = start_month
            requested_end = end_month

        if _first_day(requested_start) > _first_day(requested_end):
            raise ValidationPeriodError("SIM_VALIDATION_REVERSED_PERIOD", "Start month must not be after end month")
        if _first_day(requested_end) > _first_day(latest_month):
            raise ValidationPeriodError(
                "SIM_VALIDATION_FUTURE_MONTH",
                f"Market Store data is only available through {latest_month}",
            )

        calendar_start = _first_day(requested_start)
        calendar_end = min(_last_day(requested_end), latest)
        trading_days: list[date] = []
        cursor = calendar_start
        while cursor <= calendar_end:
            if self._is_complete_day(cursor, markets):
                trading_days.append(cursor)
            cursor += timedelta(days=1)

        if not trading_days:
            raise ValidationPeriodError(
                "SIM_VALIDATION_MARKET_DATA_MISSING",
                "No complete trading days exist in the selected range",
            )
        if _month_key(trading_days[0]) != requested_start:
            raise ValidationPeriodError(
                "SIM_VALIDATION_START_MONTH_DATA_MISSING",
                f"No complete Market Store trading day exists in start month {requested_start}",
            )
        if _month_key(trading_days[-1]) != requested_end:
            raise ValidationPeriodError(
                "SIM_VALIDATION_END_MONTH_DATA_MISSING",
                f"No complete Market Store trading day exists in end month {requested_end}",
            )

        count = len(trading_days)
        return {
            "market_scope": market_scope.strip().upper(),
            "preset": preset.strip().lower() if preset else None,
            "requested_start_month": requested_start,
            "requested_end_month": requested_end,
            "resolved_start_date": trading_days[0].isoformat(),
            "resolved_end_date": trading_days[-1].isoformat(),
            "trading_days": count,
            "minimum_trading_days": self.minimum_trading_days,
            "valid": count >= self.minimum_trading_days,
            "market_data_latest_date": latest.isoformat(),
            "partial_end_month": requested_end == latest_month and latest < _last_day(latest_month),
        }

    def require_valid(self, **kwargs: Any) -> dict[str, Any]:
        result = self.preview(**kwargs)
        if not result["valid"]:
            raise ValidationPeriodError(
                "SIM_VALIDATION_PERIOD_TOO_SHORT",
                f"Historical validation requires at least {self.minimum_trading_days} trading days; selected {result['trading_days']}",
            )
        return result
