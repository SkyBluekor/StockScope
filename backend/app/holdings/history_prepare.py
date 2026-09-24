from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from app.backtest.history_store import HistoricalStore, HistorySeries
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.scanner import StockScannerService
from app.core.config import PROJECT_ROOT
from app.market.providers import KrxProvider
from app.market.providers.base import ProviderError


DEFAULT_MARKET_STORE_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
)


class HoldingsHistoryPrepareError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class HoldingsHistoryPrepareResult:
    status: str
    market: str
    ticker: str
    market_date: str
    existing_rows: int
    prepared_rows: int
    final_rows: int
    required_rows: int
    network_requests: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _row_key(row: dict[str, Any]) -> str | None:
    raw = str(row.get("date") or "").strip().replace("-", "")
    return raw if len(raw) == 8 and raw.isdigit() else None


def _window_series(series: HistorySeries, start_dd: str, end_dd: str) -> HistorySeries:
    return HistorySeries(
        rows={
            key: row
            for key, row in series.rows.items()
            if start_dd <= key <= end_dd
        },
        checked_dates=set(),
    )


class HoldingsHistoryPrepareService:
    """Prepare only the selected stock + benchmark history needed by HOLD analysis.

    KRX raw day payloads may contain the whole market, but this service never promotes
    those peer rows into Market Store. It imports only the requested symbol and the
    selected main index, and intentionally leaves market-wide ``day_status`` untouched.
    """

    def __init__(
        self,
        *,
        krx_api_key: str | None,
        market_store_db: Path | None = None,
        history_store: HistoricalStore | None = None,
        provider_factory: Callable[[str | None], Any] | None = None,
    ) -> None:
        self.krx_api_key = krx_api_key
        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)
        self.history_store = history_store or HistoricalStore()
        self.provider_factory = provider_factory or (lambda key: KrxProvider(key))

    async def prepare(
        self,
        *,
        market: str,
        ticker: str,
        market_date: str,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> HoldingsHistoryPrepareResult:
        clean_market = (market or "").strip().upper()
        clean_ticker = (ticker or "").strip()
        if clean_market not in {"KOSPI", "KOSDAQ"}:
            raise HoldingsHistoryPrepareError(
                "HOLD_ANALYSIS_HISTORY_PREPARE_INVALID",
                "분석 데이터 준비 대상 시장이 올바르지 않습니다.",
            )
        if len(clean_ticker) != 6 or not clean_ticker.isdigit():
            raise HoldingsHistoryPrepareError(
                "HOLD_ANALYSIS_HISTORY_PREPARE_INVALID",
                "분석 데이터 준비 대상 종목코드가 올바르지 않습니다.",
            )
        try:
            target_date = date.fromisoformat((market_date or "").strip())
        except ValueError as exc:
            raise HoldingsHistoryPrepareError(
                "HOLD_ANALYSIS_HISTORY_PREPARE_INVALID",
                "분석 기준일이 올바르지 않습니다.",
            ) from exc

        required = int(StockScannerService.MIN_HISTORY_ROWS)
        start_date = target_date - timedelta(days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS)
        start_dd = start_date.strftime("%Y%m%d")
        end_dd = target_date.strftime("%Y%m%d")
        store = HistoricalMarketStore(self.market_store_db)

        # Reuse compact local history first. Import rows only; checked_dates are
        # intentionally blank so a partial symbol import never claims a full market day.
        cached_stock = _window_series(
            self.history_store.load_stock(clean_market, clean_ticker),
            start_dd,
            end_dd,
        )
        cached_index = _window_series(
            self.history_store.load_index(clean_market),
            start_dd,
            end_dd,
        )
        if cached_stock.rows:
            store.import_legacy_stock(clean_market, clean_ticker, cached_stock)
        if cached_index.rows:
            store.import_legacy_index(clean_market, cached_index)

        current_stock = store.stock_series(clean_market, clean_ticker, start_dd, end_dd)
        current_index = store.index_series(clean_market, start_dd, end_dd)
        existing_rows = len(current_stock.rows)
        existing_index_rows = len(current_index.rows)
        stock_progress = min(existing_rows, required)
        index_progress = min(existing_index_rows, required)

        def emit(stage: str, message: str) -> None:
            if progress is None:
                return
            progress({
                "stage": stage,
                "message": message,
                "stock_current": stock_progress,
                "stock_required": required,
                "index_current": index_progress,
                "index_required": required,
            })

        emit("history_check", "저장된 과거 데이터를 확인했습니다.")

        if existing_rows >= required and existing_index_rows >= required:
            return HoldingsHistoryPrepareResult(
                status="READY",
                market=clean_market,
                ticker=clean_ticker,
                market_date=target_date.isoformat(),
                existing_rows=existing_rows,
                prepared_rows=0,
                final_rows=existing_rows,
                required_rows=required,
                network_requests=0,
                message="이미 분석에 필요한 과거 가격 데이터가 준비되어 있습니다.",
            )

        provider = self.provider_factory(self.krx_api_key)
        before = provider.request_stats() if hasattr(provider, "request_stats") else {"network_requests": 0}
        opened = False
        try:
            if hasattr(provider, "open_session"):
                await provider.open_session()
                opened = True

            def stock_callback(current: int, total: int) -> None:
                nonlocal stock_progress
                stock_progress = min(required, max(existing_rows, int(current)))
                emit("history_fetch", "종목 가격 이력을 준비하고 있습니다.")

            def index_callback(current: int, total: int) -> None:
                nonlocal index_progress
                index_progress = min(required, max(existing_index_rows, int(current)))
                emit("history_fetch", "시장지수 이력을 함께 준비하고 있습니다.")

            async def load_stock_rows() -> list[dict[str, Any]]:
                if existing_rows >= required:
                    return []
                return await provider.stock_history(
                    clean_market,
                    clean_ticker,
                    as_of=target_date,
                    points=required,
                    lookback_days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS + 1,
                    concurrency=8,
                    progress=stock_callback,
                )

            async def load_index_rows() -> list[dict[str, Any]]:
                if existing_index_rows >= required:
                    return []
                return await provider.index_history(
                    clean_market,
                    as_of=target_date,
                    points=required,
                    lookback_days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS + 1,
                    concurrency=8,
                    progress=index_callback,
                )

            emit("history_fetch", "필요한 과거 가격 데이터를 준비하고 있습니다.")

            stock_rows, index_rows = await asyncio.gather(
                load_stock_rows(),
                load_index_rows(),
            )
        except ProviderError as exc:
            raise HoldingsHistoryPrepareError(
                "HOLD_ANALYSIS_HISTORY_PREPARE_FAILED",
                "과거 가격 데이터를 가져오지 못했습니다. 연결 상태와 KRX 설정을 확인한 뒤 다시 시도해주세요.",
            ) from exc
        except Exception as exc:
            raise HoldingsHistoryPrepareError(
                "HOLD_ANALYSIS_HISTORY_PREPARE_FAILED",
                f"과거 가격 데이터 준비에 실패했습니다: {exc}",
            ) from exc
        finally:
            if opened and hasattr(provider, "close_session"):
                await provider.close_session()

        # Persist only the selected symbol and selected benchmark rows. Do not mark
        # market-wide day_status from this partial recovery path.
        fetched_stock_series = HistorySeries(
            rows={key: row for row in stock_rows if (key := _row_key(row)) is not None},
            checked_dates=set(),
        )
        fetched_index_series = HistorySeries(
            rows={key: row for row in index_rows if (key := _row_key(row)) is not None},
            checked_dates=set(),
        )
        if fetched_stock_series.rows:
            store.import_legacy_stock(clean_market, clean_ticker, fetched_stock_series)
            self.history_store.save_stock(clean_market, clean_ticker, fetched_stock_series)
        if fetched_index_series.rows:
            store.import_legacy_index(clean_market, fetched_index_series)
            self.history_store.save_index(clean_market, fetched_index_series)

        final_stock = store.stock_series(clean_market, clean_ticker, start_dd, end_dd)
        final_index = store.index_series(clean_market, start_dd, end_dd)
        final_rows = len(final_stock.rows)
        final_index_rows = len(final_index.rows)
        stock_progress = min(final_rows, required)
        index_progress = min(final_index_rows, required)
        emit("history_ready", "과거 가격 데이터 준비를 확인했습니다.")
        after = provider.request_stats() if hasattr(provider, "request_stats") else before
        network_requests = max(
            0,
            int(after.get("network_requests", 0)) - int(before.get("network_requests", 0)),
        )

        if final_rows < required:
            raise HoldingsHistoryPrepareError(
                "HOLD_ANALYSIS_HISTORY_INSUFFICIENT",
                (
                    "아직 분석에 필요한 거래 이력이 충분하지 않습니다. "
                    f"현재 {final_rows}거래일 · 필요 {required}거래일"
                ),
                details={
                    "current_rows": final_rows,
                    "required_rows": required,
                    "market_date": target_date.isoformat(),
                },
            )
        if final_index_rows < required:
            raise HoldingsHistoryPrepareError(
                "HOLD_ANALYSIS_BENCHMARK_MISSING",
                "분석에 필요한 시장지수 이력이 충분하지 않습니다.",
                details={
                    "current_rows": final_index_rows,
                    "required_rows": required,
                    "market_date": target_date.isoformat(),
                },
            )

        return HoldingsHistoryPrepareResult(
            status="UPDATED",
            market=clean_market,
            ticker=clean_ticker,
            market_date=target_date.isoformat(),
            existing_rows=existing_rows,
            prepared_rows=max(0, final_rows - existing_rows),
            final_rows=final_rows,
            required_rows=required,
            network_requests=network_requests,
            message="분석에 필요한 과거 가격 데이터를 준비했습니다.",
        )
