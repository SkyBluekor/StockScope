from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.market.providers import KrxProvider
from app.news import NaverNewsProvider, NewsError, NewsService, policy_for

router = APIRouter(tags=["news"])


def _service() -> NewsService:
    settings = get_settings()
    try:
        policy = policy_for(settings.naver_news_provider_kind)
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "NEWS_NOT_CONFIGURED",
                    "message": str(exc),
                    "retryable": False,
                    "retry_after": None,
                    "request_id": uuid4().hex,
                }
            },
        ) from exc
    provider = NaverNewsProvider(
        settings.naver_news_client_id,
        settings.naver_news_client_secret,
        settings.naver_news_provider_kind,
        policy,
    )
    return NewsService(KrxProvider(settings.krx_api_key), provider, policy)


def _raise_news_error(exc: NewsError) -> None:
    status_map = {
        "STOCK_NOT_FOUND": 404,
        "NEWS_QUERY_INVALID": 400,
        "NEWS_AUTH_FAILED": 502,
        "NEWS_PROVIDER_FAILED": 502,
        "NEWS_NOT_CONFIGURED": 503,
        "NEWS_RATE_LIMITED": 503,
        "NEWS_USAGE_NOT_ALLOWED": 503,
        "NEWS_TIMEOUT": 504,
    }
    raise HTTPException(
        status_code=status_map.get(exc.code, 502),
        detail={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
                "retry_after": exc.retry_after,
                "request_id": uuid4().hex,
            }
        },
    ) from exc


@router.get("/stocks/{code}/news")
async def stock_news(
    code: str,
    market: Literal["KOSPI", "KOSDAQ"] = "KOSPI",
    limit: int = Query(default=10, ge=1, le=10),
) -> dict[str, Any]:
    try:
        return (await _service().get_stock_news(code, market, limit)).to_dict()
    except NewsError as exc:
        _raise_news_error(exc)
