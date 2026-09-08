from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


KisEnvironment = Literal["real", "demo"]


class KisCredentials(BaseModel):
    app_key: str = Field(min_length=1, max_length=256)
    app_secret: str = Field(min_length=1, max_length=512)
    environment: KisEnvironment = "real"


class KisSessionResponse(BaseModel):
    session_id: str
    environment: KisEnvironment
    expires_in: int
    read_only: bool = True


class KisSessionStatus(BaseModel):
    connected: bool
    environment: KisEnvironment | None = None
    expires_in: int = 0
    read_only: bool = True


class StockQuote(BaseModel):
    symbol: str
    name: str | None = None
    market: str = "KRX"
    price: int
    change: int | None = None
    change_rate: float | None = None
    open: int | None = None
    high: int | None = None
    low: int | None = None
    volume: int | None = None


class DailyBar(BaseModel):
    trading_date: date
    open: int
    high: int
    low: int
    close: int
    volume: int


class DailyChartResponse(BaseModel):
    symbol: str
    period: Literal["D", "W", "M", "Y"]
    adjusted: bool
    bars: list[DailyBar]


class DailyChartQuery(BaseModel):
    start_date: date
    end_date: date
    period: Literal["D", "W", "M", "Y"] = "D"
    adjusted: bool = True

    @field_validator("end_date")
    @classmethod
    def end_not_before_start(cls, value: date, info):
        start = info.data.get("start_date")
        if start and value < start:
            raise ValueError("end_date must be on or after start_date")
        return value
