from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.market.providers import KrxProvider, OpenDartProvider
from app.market.providers.base import ProviderError, ProviderNotConfigured
from app.market.service import MarketDataService

router = APIRouter(tags=["market-data"])


def _providers() -> tuple[KrxProvider, OpenDartProvider]:
    settings = get_settings()
    return KrxProvider(settings.krx_api_key), OpenDartProvider(settings.dart_api_key)


def _service() -> MarketDataService:
    krx, dart = _providers()
    return MarketDataService(krx, dart)


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
        "kis": {"enabled": False, "role": "optional provider - 현재 비활성"},
        "real_trading": False,
    }


@router.get("/krx/stocks/{code}/daily")
async def krx_stock_daily(
    code: str,
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI",
    bas_date: str = Query(default=(date.today() - timedelta(days=1)).isoformat()),
) -> dict[str, Any]:
    krx, _ = _providers()
    try:
        result = await krx.stock_daily(market, bas_date, code)
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
    bas_date: str = Query(default=(date.today() - timedelta(days=1)).isoformat()),
) -> dict[str, Any]:
    krx, _ = _providers()
    try:
        return await krx.index_daily(market, bas_date)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


@router.get("/market/snapshot")
async def market_snapshot(as_of: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        return await _service().market_snapshot(as_of)
    except (ProviderError, ValueError) as exc:
        _raise_provider_error(exc)


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
