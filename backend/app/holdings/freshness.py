from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.backtest.market_store import HistoricalMarketStore
from app.backtest.scanner import StockScannerService
from app.core.config import PROJECT_ROOT
from app.market.providers import KrxProvider


DEFAULT_MARKET_STORE_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
)


class HoldingsMarketFreshnessError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class HoldingsMarketFreshnessResult:
    status: str
    market: str
    requested_date: str | None
    latest_confirmed_date: str | None
    resolved_as_of_date: str
    known_data_date: str | None
    market_data_updated: bool
    date_changed: bool
    network_requests: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "market": self.market,
            "requested_date": self.requested_date,
            "latest_confirmed_date": self.latest_confirmed_date,
            "resolved_as_of_date": self.resolved_as_of_date,
            "known_data_date": self.known_data_date,
            "market_data_updated": self.market_data_updated,
            "date_changed": self.date_changed,
            "network_requests": self.network_requests,
            "message": self.message,
        }


class HoldingsMarketFreshnessService:
    """Prepare the selected market's latest confirmed EOD data without running Scanner ranking."""

    def __init__(
        self,
        *,
        krx_api_key: str | None,
        market_store_db: Path | None = None,
        scanner_factory: Callable[[Any, HistoricalMarketStore], Any] | None = None,
    ) -> None:
        self.krx_api_key = krx_api_key
        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)
        self.scanner_factory = scanner_factory

    async def prepare(
        self,
        *,
        market: str,
        known_data_date: str | None,
    ) -> HoldingsMarketFreshnessResult:
        clean_market = (market or "").strip().upper()
        if clean_market not in {"KOSPI", "KOSDAQ"}:
            raise HoldingsMarketFreshnessError(
                "HOLD_MARKET_FRESHNESS_MARKET_INVALID",
                "최신 시세 확인 대상 시장이 올바르지 않습니다.",
            )

        store = HistoricalMarketStore(self.market_store_db)
        provider = KrxProvider(self.krx_api_key)
        scanner = (
            self.scanner_factory(provider, store)
            if self.scanner_factory is not None
            else StockScannerService(provider, market_store=store)
        )

        payload = await scanner.prepare_latest_confirmed_data(
            market_scope=clean_market,
            known_data_date=known_data_date,
        )
        status = str(payload.get("status") or "")
        resolved = str(payload.get("resolved_as_of_date") or "").strip()
        if status not in {"READY", "UPDATED"} or not resolved:
            raise HoldingsMarketFreshnessError(
                "HOLD_MARKET_FRESHNESS_UPDATE_FAILED",
                str(payload.get("message") or "최신 확정 시세를 확인하지 못했습니다."),
            )

        diagnostics = payload.get("diagnostics") or {}
        return HoldingsMarketFreshnessResult(
            status=status,
            market=clean_market,
            requested_date=payload.get("requested_date"),
            latest_confirmed_date=payload.get("latest_confirmed_date"),
            resolved_as_of_date=resolved,
            known_data_date=payload.get("known_data_date"),
            market_data_updated=bool(payload.get("market_data_updated")),
            date_changed=bool(payload.get("date_changed")),
            network_requests=int(diagnostics.get("network_requests") or 0),
            message=str(payload.get("message") or f"{resolved} 확정 일봉 기준으로 분석할 수 있습니다."),
        )
