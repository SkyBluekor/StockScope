from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.integrations.kis.account import KisAccountError, inquire_domestic_balance
from app.integrations.kis.client import KisConfigurationError
from app.market.providers import KrxProvider, OpenDartProvider
from app.market.providers.base import ProviderError, ProviderNotConfigured


router = APIRouter(prefix="/integrations", tags=["integrations"])
ProviderName = Literal["kis", "krx", "dart"]


def _configured(settings: Settings) -> dict[str, bool]:
    return {
        "kis": bool(
            settings.kis_app_key
            and settings.kis_app_secret
            and settings.kis_account_no
            and settings.kis_account_product_code
        ),
        "krx": bool(settings.krx_api_key),
        "dart": bool(settings.dart_api_key),
    }


def _status_payload(settings: Settings) -> dict[str, Any]:
    configured = _configured(settings)
    return {
        "kis": {
            "configured": configured["kis"],
            "status": "CONFIGURED" if configured["kis"] else "NOT_CONFIGURED",
            "role": "실계좌 잔고 · 현재가 · 실시간 시세",
            "check_supported": True,
        },
        "krx": {
            "configured": configured["krx"],
            "status": "CONFIGURED" if configured["krx"] else "NOT_CONFIGURED",
            "role": "시장 · 종목 · 일별 시세 · 지수",
            "check_supported": True,
        },
        "dart": {
            "configured": configured["dart"],
            "status": "CONFIGURED" if configured["dart"] else "NOT_CONFIGURED",
            "role": "기업 · 공시 · 재무 정보",
            "check_supported": True,
        },
    }


@router.get("/status")
def integration_status() -> dict[str, Any]:
    return _status_payload(get_settings())


async def _check_kis(settings: Settings) -> dict[str, Any]:
    balance = await run_in_threadpool(inquire_domestic_balance, settings)
    return {
        "configured": True,
        "reachable": True,
        "holding_count": len(balance.holdings),
        "page_count": balance.page_count,
    }


async def _check_krx(settings: Settings) -> dict[str, Any]:
    provider = KrxProvider(settings.krx_api_key)
    try:
        result = await provider.latest_basic_info("KOSPI")
    finally:
        await provider.close_session()
    return {
        "configured": True,
        "reachable": True,
        "date": result.get("date"),
        "count": result.get("count"),
    }


async def _check_dart(settings: Settings) -> dict[str, Any]:
    provider = OpenDartProvider(settings.dart_api_key)
    result = await provider.company("00126380")
    return {
        "configured": True,
        "reachable": True,
        "provider": "OpenDART",
        "sample_stock_code": result.get("stock_code"),
    }


@router.post("/{provider}/check")
async def check_integration(provider: ProviderName) -> dict[str, Any]:
    settings = get_settings()
    configured = _configured(settings)
    if not configured[provider]:
        raise HTTPException(
            status_code=409,
            detail={
                "code": f"{provider.upper()}_NOT_CONFIGURED",
                "message": f"{provider.upper()} 연동 설정이 필요합니다.",
            },
        )

    try:
        if provider == "kis":
            result = await _check_kis(settings)
        elif provider == "krx":
            result = await _check_krx(settings)
        else:
            result = await _check_dart(settings)
    except (KisConfigurationError, ProviderNotConfigured) as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": f"{provider.upper()}_NOT_CONFIGURED",
                "message": str(exc),
            },
        ) from exc
    except (KisAccountError, ProviderError) as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": f"{provider.upper()}_CONNECTION_FAILED",
                "message": str(exc),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": f"{provider.upper()}_CHECK_INVALID",
                "message": str(exc),
            },
        ) from exc

    return {
        "provider": provider,
        "status": "CONNECTED",
        **result,
    }
