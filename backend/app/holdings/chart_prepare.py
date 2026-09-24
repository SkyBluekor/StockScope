from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from app.backtest.history_store import HistoricalStore, HistorySeries
from app.backtest.market_store import HistoricalMarketStore
from app.core.config import PROJECT_ROOT
from app.holdings.chart import ChartRange, RANGE_BARS
from app.market.providers import KrxProvider
from app.market.providers.base import ProviderError

DEFAULT_MARKET_STORE_DB = PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"


class HoldingsChartPrepareError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class HoldingsChartPrepareResult:
    status: str
    market: str
    ticker: str
    chart_range: str
    latest_confirmed_date: str
    existing_rows: int
    prepared_rows: int
    final_rows: int
    required_rows: int
    network_requests: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["range"] = payload.pop("chart_range")
        return payload


def _row_key(row: dict[str, Any]) -> str | None:
    raw = str(row.get("date") or "").strip().replace("-", "")
    return raw if len(raw) == 8 and raw.isdigit() else None


def _iso_from_dd(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


class HoldingsChartPrepareService:
    # Extend only one selected stock's OHLCV history for chart display.
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
        chart_range: ChartRange,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> HoldingsChartPrepareResult:
        clean_market = (market or "").strip().upper()
        clean_ticker = (ticker or "").strip()
        if clean_market not in {"KOSPI", "KOSDAQ"}:
            raise HoldingsChartPrepareError("HOLD_CHART_PREPARE_INVALID", "차트 데이터 준비 대상 시장이 올바르지 않습니다.")
        if len(clean_ticker) != 6 or not clean_ticker.isdigit():
            raise HoldingsChartPrepareError("HOLD_CHART_PREPARE_INVALID", "차트 데이터 준비 대상 종목코드가 올바르지 않습니다.")
        if chart_range not in RANGE_BARS:
            raise HoldingsChartPrepareError("HOLD_CHART_PREPARE_INVALID", "차트 기간은 1m, 3m, 6m, 1y 중 하나여야 합니다.")

        required = int(RANGE_BARS[chart_range])
        store = HistoricalMarketStore(self.market_store_db)
        latest_dd = store.latest_complete_date(clean_market, "stock")
        if latest_dd is None:
            raise HoldingsChartPrepareError(
                "HOLD_CHART_PREPARE_CONFIRMED_DATE_MISSING",
                "최신 확정 일봉 기준일이 없어 차트 기간을 확장할 수 없습니다. 먼저 종목 분석 데이터를 준비해주세요.",
            )
        target_date = date.fromisoformat(_iso_from_dd(latest_dd))

        def emit(stage: str, message: str, current: int, *, status: str | None = None) -> None:
            if progress is None:
                return
            payload: dict[str, Any] = {
                "stage": stage,
                "message": message,
                "current": min(max(0, int(current)), required),
                "required": required,
            }
            if status is not None:
                payload["status"] = status
            progress(payload)

        cached = self.history_store.load_stock(clean_market, clean_ticker)
        cached_rows = {key: row for key, row in cached.rows.items() if key <= latest_dd and isinstance(row, dict)}
        if cached_rows:
            store.import_legacy_stock(clean_market, clean_ticker, HistorySeries(rows=cached_rows, checked_dates=set()))

        existing_series = store.stock_series(clean_market, clean_ticker, end_dd=latest_dd)
        existing_rows = len(existing_series.rows)
        emit("local_check", f"저장된 차트 데이터 {min(existing_rows, required)} / {required}거래일을 확인했습니다.", existing_rows)
        if existing_rows >= required:
            return HoldingsChartPrepareResult(
                status="READY", market=clean_market, ticker=clean_ticker, chart_range=chart_range,
                latest_confirmed_date=target_date.isoformat(), existing_rows=existing_rows,
                prepared_rows=0, final_rows=existing_rows, required_rows=required, network_requests=0,
                message="선택한 기간의 차트 데이터가 이미 준비되어 있습니다.",
            )

        if existing_series.rows:
            oldest_dd = min(existing_series.rows)
            cursor = date.fromisoformat(_iso_from_dd(oldest_dd)) - timedelta(days=1)
        else:
            cursor = target_date

        horizon_days = max(120, int(required * 2.2) + 45)
        minimum_date = target_date - timedelta(days=horizon_days)
        provider = self.provider_factory(self.krx_api_key)
        before = provider.request_stats() if hasattr(provider, "request_stats") else {"network_requests": 0}
        opened = False
        empty_windows = 0

        try:
            if hasattr(provider, "open_session"):
                await provider.open_session()
                opened = True

            current_rows = existing_rows
            while current_rows < required and cursor >= minimum_date:
                remaining = required - current_rows
                points = min(120, max(20, remaining))
                lookback_days = max(60, int(points * 2.1) + 21)
                floor = max(minimum_date, cursor - timedelta(days=lookback_days))
                before_chunk = current_rows

                def provider_progress(found: int, wanted: int) -> None:
                    emit(
                        "history_fetch",
                        f"과거 가격 데이터 {min(required, before_chunk + found)} / {required}거래일을 준비하고 있습니다.",
                        before_chunk + found,
                    )

                rows = await provider.stock_history(
                    clean_market,
                    clean_ticker,
                    as_of=cursor,
                    points=points,
                    lookback_days=(cursor - floor).days + 1,
                    concurrency=8,
                    progress=provider_progress,
                )
                normalized = {key: row for row in rows if (key := _row_key(row)) is not None and key <= latest_dd}

                if normalized:
                    store.import_legacy_stock(clean_market, clean_ticker, HistorySeries(rows=normalized, checked_dates=set()))
                    refreshed = store.stock_series(clean_market, clean_ticker, end_dd=latest_dd)
                    current_rows = len(refreshed.rows)
                    oldest_fetched = min(normalized)
                    cursor = date.fromisoformat(_iso_from_dd(oldest_fetched)) - timedelta(days=1)
                    empty_windows = 0
                    emit("history_saved", f"차트 데이터 {min(current_rows, required)} / {required}거래일을 확보했습니다.", current_rows)
                else:
                    cursor = floor - timedelta(days=1)
                    empty_windows += 1
                    if empty_windows >= 3:
                        break

        except ProviderError as exc:
            current = len(store.stock_series(clean_market, clean_ticker, end_dd=latest_dd).rows)
            raise HoldingsChartPrepareError(
                "HOLD_CHART_PREPARE_FAILED",
                "과거 차트 데이터를 가져오지 못했습니다. 기존에 저장된 차트 데이터는 그대로 유지됩니다.",
                details={"current_rows": current, "required_rows": required},
            ) from exc
        except Exception as exc:
            current = len(store.stock_series(clean_market, clean_ticker, end_dd=latest_dd).rows)
            raise HoldingsChartPrepareError(
                "HOLD_CHART_PREPARE_FAILED",
                f"차트 데이터 준비에 실패했습니다: {exc}",
                details={"current_rows": current, "required_rows": required},
            ) from exc
        finally:
            if opened and hasattr(provider, "close_session"):
                await provider.close_session()

        final_rows = len(store.stock_series(clean_market, clean_ticker, end_dd=latest_dd).rows)
        after = provider.request_stats() if hasattr(provider, "request_stats") else before
        network_requests = max(0, int(after.get("network_requests", 0)) - int(before.get("network_requests", 0)))

        if final_rows >= required:
            emit("complete", "선택한 차트 기간의 데이터 준비를 완료했습니다.", final_rows, status="READY")
            return HoldingsChartPrepareResult(
                status="READY", market=clean_market, ticker=clean_ticker, chart_range=chart_range,
                latest_confirmed_date=target_date.isoformat(), existing_rows=existing_rows,
                prepared_rows=max(0, final_rows - existing_rows), final_rows=final_rows,
                required_rows=required, network_requests=network_requests,
                message="선택한 기간의 차트 데이터를 준비했습니다.",
            )

        emit("max_available", f"현재 확보 가능한 데이터는 {final_rows}거래일입니다.", final_rows, status="PARTIAL_MAX_AVAILABLE")
        return HoldingsChartPrepareResult(
            status="PARTIAL_MAX_AVAILABLE", market=clean_market, ticker=clean_ticker, chart_range=chart_range,
            latest_confirmed_date=target_date.isoformat(), existing_rows=existing_rows,
            prepared_rows=max(0, final_rows - existing_rows), final_rows=final_rows,
            required_rows=required, network_requests=network_requests,
            message="현재 확보 가능한 전체 기간을 표시하고 있습니다.",
        )
