from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from app.core.config import PROJECT_ROOT


ChartRange = Literal["1m", "3m", "6m", "1y"]
RANGE_BARS: dict[str, int] = {
    "1m": 22,
    "3m": 66,
    "6m": 132,
    "1y": 252,
}
DEFAULT_MARKET_STORE_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
)


class HoldingsChartError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class HoldingChartBar:
    date: str
    open: str
    high: str
    low: str
    close: str
    volume: str


@dataclass(frozen=True, slots=True)
class HoldingChartSeries:
    market: str
    ticker: str
    chart_range: str
    source: str
    from_date: str
    to_date: str
    requested_bars: int
    count: int
    bars: tuple[HoldingChartBar, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["range"] = payload.pop("chart_range")
        payload["bars"] = [asdict(bar) for bar in self.bars]
        return payload


def _normalize_market(market: str) -> str:
    value = (market or "").strip().upper()
    if value not in {"KOSPI", "KOSDAQ"}:
        raise HoldingsChartError(
            "HOLD_CHART_MARKET_INVALID",
            "market은 KOSPI 또는 KOSDAQ이어야 합니다.",
        )
    return value


def _normalize_ticker(ticker: str) -> str:
    value = (ticker or "").strip()
    if len(value) != 6 or not value.isdigit():
        raise HoldingsChartError(
            "HOLD_CHART_TICKER_INVALID",
            "국내주식 종목코드는 6자리 숫자여야 합니다.",
        )
    return value


def _decimal_text(value: Any, *, field: str, allow_zero: bool = False) -> str:
    if value in (None, ""):
        raise HoldingsChartError(
            "HOLD_CHART_DATA_INVALID",
            f"Market Store 차트 데이터에 {field} 값이 없습니다.",
        )
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise HoldingsChartError(
            "HOLD_CHART_DATA_INVALID",
            f"Market Store 차트 데이터의 {field} 값이 숫자가 아닙니다.",
        ) from exc
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise HoldingsChartError(
            "HOLD_CHART_DATA_INVALID",
            f"Market Store 차트 데이터의 {field} 값이 올바르지 않습니다.",
        )
    return format(number, "f")


def _iso_date(raw: Any, bas_dd: str) -> str:
    value = str(raw or "").strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    if len(bas_dd) == 8 and bas_dd.isdigit():
        return f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}"
    raise HoldingsChartError(
        "HOLD_CHART_DATA_INVALID",
        "Market Store 차트 데이터의 날짜 형식이 올바르지 않습니다.",
    )


class HoldingsChartService:
    """Read-only confirmed-EOD OHLCV reader for the HOLD UI chart."""

    def __init__(self, market_store_db: Path | None = None) -> None:
        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)

    def _connect(self) -> sqlite3.Connection:
        if not self.market_store_db.is_file():
            raise HoldingsChartError(
                "HOLD_CHART_MARKET_STORE_NOT_FOUND",
                f"Market Store를 찾을 수 없습니다: {self.market_store_db}",
            )
        uri = self.market_store_db.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=20.0)
        conn.row_factory = sqlite3.Row
        return conn

    def load(
        self,
        *,
        market: str,
        ticker: str,
        chart_range: ChartRange,
    ) -> HoldingChartSeries:
        clean_market = _normalize_market(market)
        clean_ticker = _normalize_ticker(ticker)
        if chart_range not in RANGE_BARS:
            raise HoldingsChartError(
                "HOLD_CHART_RANGE_INVALID",
                "차트 기간은 1m, 3m, 6m, 1y 중 하나여야 합니다.",
            )
        limit = RANGE_BARS[chart_range]

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.bas_dd,s.row_json
                FROM stock_daily s
                JOIN day_status d
                  ON d.market=s.market
                 AND d.bas_dd=s.bas_dd
                 AND d.kind='stock'
                 AND d.status='data'
                WHERE s.market=? AND s.stock_code=?
                ORDER BY s.bas_dd DESC
                LIMIT ?
                """,
                (clean_market, clean_ticker, limit),
            ).fetchall()

        if not rows:
            raise HoldingsChartError(
                "HOLD_CHART_STOCK_NOT_FOUND",
                f"{clean_market}/{clean_ticker}의 확정 일봉 데이터를 찾을 수 없습니다.",
            )

        bars: list[HoldingChartBar] = []
        for row in reversed(rows):
            try:
                payload = json.loads(str(row["row_json"]))
            except json.JSONDecodeError as exc:
                raise HoldingsChartError(
                    "HOLD_CHART_DATA_INVALID",
                    "Market Store 차트 데이터 JSON을 읽을 수 없습니다.",
                ) from exc
            if not isinstance(payload, dict):
                raise HoldingsChartError(
                    "HOLD_CHART_DATA_INVALID",
                    "Market Store 차트 데이터 형식이 올바르지 않습니다.",
                )

            open_text = _decimal_text(payload.get("open"), field="시가")
            high_text = _decimal_text(payload.get("high"), field="고가")
            low_text = _decimal_text(payload.get("low"), field="저가")
            close_text = _decimal_text(payload.get("close"), field="종가")
            volume_text = _decimal_text(
                payload.get("volume"),
                field="거래량",
                allow_zero=True,
            )

            open_value = Decimal(open_text)
            high_value = Decimal(high_text)
            low_value = Decimal(low_text)
            close_value = Decimal(close_text)
            if high_value < max(open_value, close_value) or low_value > min(open_value, close_value) or high_value < low_value:
                raise HoldingsChartError(
                    "HOLD_CHART_DATA_INVALID",
                    "Market Store OHLC 가격 관계가 올바르지 않습니다.",
                )

            bars.append(
                HoldingChartBar(
                    date=_iso_date(payload.get("date"), str(row["bas_dd"])),
                    open=open_text,
                    high=high_text,
                    low=low_text,
                    close=close_text,
                    volume=volume_text,
                )
            )

        return HoldingChartSeries(
            market=clean_market,
            ticker=clean_ticker,
            chart_range=chart_range,
            source="MARKET_STORE_CONFIRMED_EOD",
            from_date=bars[0].date,
            to_date=bars[-1].date,
            requested_bars=limit,
            count=len(bars),
            bars=tuple(bars),
        )
