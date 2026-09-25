import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.holdings.chart import HoldingsChartError, HoldingsChartService
from app.holdings.chart_prepare import HoldingsChartPrepareError, HoldingsChartPrepareService
from app.market.providers import KrxProvider, OpenDartProvider
from app.market.providers.base import ProviderError, ProviderNotConfigured
from app.market.service import MarketDataService
from app.strategy.service import StrategyAnalysisService

router = APIRouter(tags=["market-data"])


def _today_kst_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


def _providers() -> tuple[KrxProvider, OpenDartProvider]:
    settings = get_settings()
    return KrxProvider(settings.krx_api_key), OpenDartProvider(settings.dart_api_key)


def _service() -> MarketDataService:
    krx, dart = _providers()
    return MarketDataService(krx, dart)


def _market_store_path() -> Path | None:
    raw = os.getenv("STOCKSCOPE_MARKET_STORE_DB")
    return Path(raw) if raw else None


def _stock_chart_service() -> HoldingsChartService:
    return HoldingsChartService(_market_store_path())


def _stock_chart_prepare_service() -> HoldingsChartPrepareService:
    settings = get_settings()
    return HoldingsChartPrepareService(
        krx_api_key=settings.krx_api_key,
        market_store_db=_market_store_path(),
    )


def _raise_provider_error(exc: Exception) -> None:
    if isinstance(exc, ProviderNotConfigured):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/providers/status")
async def provider_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "krx": {"configured": bool(settings.krx_api_key), "role": "시장/일별 시세/지수"},
        "dart": {"configured": bool(settings.dart_api_key), "role": "기업/공시/재무"},
        "naver_news": {
            "configured": bool((settings.naver_news_client_id or "").strip() and (settings.naver_news_client_secret or "").strip()),
            "provider_kind": settings.naver_news_provider_kind,
            "role": "종목 최근 뉴스",
        },
        "kis": {"enabled": False, "role": "optional provider - 현재 비활성"},
        "real_trading": False,
    }


@router.get("/krx/stocks/{code}/daily")
async def krx_stock_daily(
    code: str,
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI",
    bas_date: str | None = Query(default=None, description="생략 시 한국시간 오늘 날짜를 조회합니다."),
) -> dict[str, Any]:
    krx, _ = _providers()
    target_date = bas_date or _today_kst_iso()
    try:
        result = await krx.stock_daily(market, target_date, code)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)
    if result["count"] == 0:
        raise HTTPException(
            status_code=404,
            detail="해당 날짜/시장/종목 데이터가 없습니다. 휴장일이거나 시장 구분이 다를 수 있습니다.",
        )
    return result


@router.get("/krx/stocks/{code}/latest")
async def krx_stock_latest(
    code: str,
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI",
    as_of: str | None = Query(default=None),
) -> dict[str, Any]:
    krx, _ = _providers()
    try:
        return await krx.latest_stock_daily(market, code, as_of)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/krx/index/{market}/daily")
async def krx_index_daily(
    market: Literal["KOSPI", "KOSDAQ"],
    bas_date: str | None = Query(default=None, description="생략 시 한국시간 오늘 날짜를 조회합니다."),
) -> dict[str, Any]:
    krx, _ = _providers()
    target_date = bas_date or _today_kst_iso()
    try:
        return await krx.index_daily(market, target_date)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/market/snapshot")
async def market_snapshot(as_of: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        return await _service().market_snapshot(as_of)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/market/dashboard")
async def market_dashboard(
    as_of: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        return await _service().market_dashboard(as_of)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/market/history")
async def market_history(
    as_of: str | None = Query(default=None),
    points: int = Query(default=7, ge=3, le=12),
) -> dict[str, Any]:
    try:
        return await _service().market_history(as_of, points)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/stocks/{code}/chart")
def stock_chart(
    code: str,
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI",
    chart_range: Literal["1m", "3m", "6m", "1y"] = Query(default="3m", alias="range"),
) -> dict[str, Any]:
    """Read confirmed-EOD OHLCV for any stock already present in Market Store."""
    try:
        return _stock_chart_service().load(
            market=market,
            ticker=code,
            chart_range=chart_range,
        ).to_dict()
    except HoldingsChartError as exc:
        status = 404 if exc.code in {"HOLD_CHART_STOCK_NOT_FOUND", "HOLD_CHART_CONFIRMED_DATE_NOT_FOUND"} else 400
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc


@router.post("/stocks/{code}/chart/prepare-stream")
async def prepare_stock_chart_stream(
    code: str,
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI",
    chart_range: Literal["1m", "3m", "6m", "1y"] = Query(alias="range"),
) -> StreamingResponse:
    """Prepare only the selected stock/range; never runs Scanner ranking."""
    async def event_stream():
        def line(payload: dict[str, Any]) -> str:
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def on_progress(payload: dict[str, Any]) -> None:
            queue.put_nowait({"type": "progress", **payload})

        task = asyncio.create_task(
            _stock_chart_prepare_service().prepare(
                market=market,
                ticker=code,
                chart_range=chart_range,
                progress=on_progress,
            )
        )
        try:
            while not task.done() or not queue.empty():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.15)
                except asyncio.TimeoutError:
                    continue
                yield line(item)

            result = await task
            yield line({"type": "complete", "stage": "complete", "message": result.message, "result": result.to_dict()})
        except HoldingsChartPrepareError as exc:
            payload: dict[str, Any] = {"type": "error", "stage": "error", "code": exc.code, "message": exc.message}
            payload.update(exc.details)
            yield line(payload)

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/dart/company/{corp_code}")
async def dart_company(corp_code: str) -> dict[str, Any]:
    _, dart = _providers()
    try:
        return await dart.company(corp_code)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/dart/corp-code/{stock_code}")
async def dart_corp_code(stock_code: str) -> dict[str, str]:
    _, dart = _providers()
    try:
        return {"stock_code": stock_code, "corp_code": await dart.resolve_corp_code(stock_code)}
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/dart/disclosures/{corp_code}")
async def dart_disclosures(
    corp_code: str,
    begin_date: str = Query(...),
    end_date: str = Query(...),
    page_count: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    _, dart = _providers()
    try:
        return await dart.disclosures(corp_code, begin_date, end_date, page_count)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/stocks/search")
async def stock_search(
    q: str = Query(..., min_length=1, max_length=50),
    market: Literal["KOSPI", "KOSDAQ"] | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=30),
) -> dict[str, Any]:
    krx, _ = _providers()
    try:
        return await krx.search_stocks(q, market, limit)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/stocks/{code}/context")
async def stock_context(
    code: str,
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI",
    as_of: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        return await _service().stock_context(code, market, as_of)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/stocks/{code}/strategy-analysis")
async def stock_strategy_analysis(
    code: str,
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI",
    as_of: str | None = Query(default=None),
    history_points: int = Query(default=60, ge=20, le=60),
    reference_price: float | None = Query(default=None, gt=0),
    reference_high: float | None = Query(default=None, gt=0),
    reference_low: float | None = Query(default=None, gt=0),
    reference_volume: float | None = Query(default=None, ge=0),
    position_mode: Literal["NOT_HELD", "HOLDING"] = "NOT_HELD",
    average_price: float | None = Query(default=None, gt=0),
    quantity: float | None = Query(default=None, gt=0),
) -> dict[str, Any]:
    krx, dart = _providers()
    service = StrategyAnalysisService(krx, dart)
    try:
        return await service.analyze(
            code,
            market,
            as_of,
            history_points,
            reference_price,
            reference_high,
            reference_low,
            reference_volume,
            position_mode,
            average_price,
            quantity,
        )
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)
