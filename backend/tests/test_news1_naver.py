from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import news as news_api
from app.news.models import NewsError, NewsItem, NewsResponse
from app.news.naver import NaverNewsProvider
from app.news.policy import NewsSourcePolicy, policy_for
from app.news.service import NewsService


@pytest.fixture(autouse=True)
def _clear_news_runtime() -> None:
    NewsService._cache.clear()
    NewsService._inflight.clear()


def _payload() -> dict:
    return {
        "lastBuildDate": "Fri, 25 Sep 2026 14:30:00 +0900",
        "total": 2,
        "start": 1,
        "display": 2,
        "items": [
            {
                "title": "<b>삼성전자</b> 신제품 공개 &amp; 공급 확대",
                "originallink": "https://example.com/news/1?utm_source=naver&id=77",
                "link": "https://n.news.naver.com/article/001/0001",
                "description": "<b>삼성전자</b>가 신제품을 공개했습니다.",
                "pubDate": "Fri, 25 Sep 2026 13:10:00 +0900",
            },
            {
                "title": "두 번째 기사",
                "originallink": "javascript:alert(1)",
                "link": "https://n.news.naver.com/article/002/0002",
                "description": "정상 발췌문",
                "pubDate": "broken-date",
            },
        ],
    }


@pytest.mark.asyncio
async def test_api_hub_uses_only_ncp_host_and_headers() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["headers"] = dict(request.headers)
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json=_payload())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        policy = policy_for("api_hub")
        provider = NaverNewsProvider("id-value", "secret-value", "api_hub", policy, client=client)
        items, _, discarded = await provider.search("삼성전자", 2)
    finally:
        await client.aclose()

    assert seen["host"] == "naverapihub.apigw.ntruss.com"
    assert seen["path"] == "/search/v1/news"
    headers = seen["headers"]
    assert headers["x-ncp-apigw-api-key-id"] == "id-value"
    assert headers["x-ncp-apigw-api-key"] == "secret-value"
    assert "x-naver-client-id" not in headers
    assert "x-naver-client-secret" not in headers
    assert seen["query"]["sort"] == "date"
    assert seen["query"]["display"] == "2"
    assert seen["query"]["format"] == "json"
    assert discarded == 0
    assert len(items) == 2
    assert items[0].title == "삼성전자 신제품 공개 & 공급 확대"
    assert items[0].description == "삼성전자가 신제품을 공개했습니다."
    assert items[0].url == "https://example.com/news/1?id=77"
    assert items[1].url == "https://n.news.naver.com/article/002/0002"
    assert items[1].published_at is None


@pytest.mark.asyncio
async def test_developer_center_uses_only_legacy_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "openapi.naver.com"
        assert request.url.path == "/v1/search/news.json"
        assert request.headers["X-Naver-Client-Id"] == "legacy-id"
        assert request.headers["X-Naver-Client-Secret"] == "legacy-secret"
        assert "X-NCP-APIGW-API-KEY-ID" not in request.headers
        return httpx.Response(200, json={"items": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        provider = NaverNewsProvider(
            "legacy-id",
            "legacy-secret",
            "developer_center",
            policy_for("developer_center"),
            client=client,
        )
        items, _, discarded = await provider.search("SK하이닉스", 10)
    finally:
        await client.aclose()

    assert items == ()
    assert discarded == 0


@pytest.mark.asyncio
async def test_provider_rejects_missing_key_and_maps_auth_rate_limit() -> None:
    provider = NaverNewsProvider("", "", "api_hub", policy_for("api_hub"))
    with pytest.raises(NewsError) as missing:
        await provider.search("삼성전자", 10)
    assert missing.value.code == "NEWS_NOT_CONFIGURED"

    async def assert_status(status: int, expected: str, headers: dict[str, str] | None = None) -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(status, headers=headers or {}))
        )
        try:
            p = NaverNewsProvider("id", "secret", "api_hub", policy_for("api_hub"), client=client)
            with pytest.raises(NewsError) as caught:
                await p.search("삼성전자", 10)
            assert caught.value.code == expected
            if status == 429:
                assert caught.value.retry_after == 45
        finally:
            await client.aclose()

    await assert_status(401, "NEWS_AUTH_FAILED")
    await assert_status(403, "NEWS_AUTH_FAILED")
    await assert_status(429, "NEWS_RATE_LIMITED", {"Retry-After": "45"})


@pytest.mark.asyncio
async def test_malformed_items_are_dropped_but_bad_payload_fails() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "items": [
                        {"title": "bad", "link": "data:text/html,x", "originallink": ""},
                        {"title": "", "link": "https://example.com/2"},
                    ]
                },
            )
        )
    )
    try:
        provider = NaverNewsProvider("id", "secret", "api_hub", policy_for("api_hub"), client=client)
        items, _, discarded = await provider.search("삼성전자", 10)
    finally:
        await client.aclose()
    assert items == ()
    assert discarded == 2

    bad_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"not_items": []}))
    )
    try:
        provider = NaverNewsProvider("id", "secret", "api_hub", policy_for("api_hub"), client=bad_client)
        with pytest.raises(NewsError) as caught:
            await provider.search("삼성전자", 10)
        assert caught.value.code == "NEWS_PROVIDER_FAILED"
    finally:
        await bad_client.aclose()


class _FakeKrx:
    async def search_stocks(self, query: str, market: str, limit: int):
        return {
            "rows": [
                {"code": "005930", "market": "KOSPI", "name": "삼성전자", "full_name": "삼성전자"}
            ]
        }


class _FakeProvider:
    provider_kind = "developer_center"

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query: str, limit: int):
        self.calls += 1
        await asyncio.sleep(0.01)
        fetched = "2026-09-25T14:30:00+09:00"
        item = NewsItem(
            id="item-1",
            title="기사",
            description="설명",
            url="https://example.com/a",
            source_url="https://search.example/a",
            source_name=None,
            source_domain="example.com",
            provider="NAVER_DEVELOPER_CENTER",
            published_at=fetched,
            timestamp_kind="NAVER_PROVIDER_PUBDATE",
            query=query,
            fetched_at=fetched,
        )
        return (item,), fetched, 0


@pytest.mark.asyncio
async def test_service_cache_and_inflight_share_one_upstream_call() -> None:
    provider = _FakeProvider()
    policy = NewsSourcePolicy(
        provider_kind="developer_center",
        policy_version="test",
        display_allowed=True,
        display_normalization_allowed=True,
        transform_allowed=False,
        ai_allowed=False,
        retention_policy="TEST",
        server_cache_seconds=300,
        attribution_required=True,
    )
    service = NewsService(_FakeKrx(), provider, policy)

    first, second = await asyncio.gather(
        service.get_stock_news("005930", "KOSPI", 10),
        service.get_stock_news("005930", "KOSPI", 10),
    )
    assert provider.calls == 1
    assert first.count if hasattr(first, "count") else len(first.items) == 1
    assert len(second.items) == 1

    cached = await service.get_stock_news("005930", "KOSPI", 10)
    assert provider.calls == 1
    assert cached.cache_hit is True
    assert cached.fetched_at == first.fetched_at


@pytest.mark.asyncio
async def test_api_hub_policy_disables_result_cache_until_retention_terms_are_confirmed() -> None:
    assert policy_for("api_hub").server_cache_seconds == 0
    assert policy_for("api_hub").ai_allowed is False
    assert policy_for("api_hub").transform_allowed is False


def test_news_api_error_contract_does_not_expose_secret(monkeypatch) -> None:
    class BrokenService:
        async def get_stock_news(self, code: str, market: str, limit: int):
            raise NewsError("NEWS_AUTH_FAILED", "네이버 뉴스 API 인증에 실패했습니다.")

    monkeypatch.setattr(news_api, "_service", lambda: BrokenService())
    app = FastAPI()
    app.include_router(news_api.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/stocks/005930/news?market=KOSPI&limit=10")
    assert response.status_code == 502
    body = response.json()["detail"]["error"]
    assert body["code"] == "NEWS_AUTH_FAILED"
    assert "secret" not in str(body).lower()
    assert body["request_id"]


def test_news1_frontend_and_env_contract() -> None:
    api = Path("frontend/src/services/api.ts").read_text(encoding="utf-8")
    panel = Path("frontend/src/components/StockNewsPanel.tsx").read_text(encoding="utf-8")
    workspace = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")
    env_example = Path(".env.example").read_text(encoding="utf-8")
    config = Path("backend/app/core/config.py").read_text(encoding="utf-8")

    assert "fetchStockNews" in api
    assert "StockNewsResponse" in api
    assert "AbortController" in panel
    assert "requestIdRef" in panel
    assert 'target="_blank"' in panel
    assert 'rel="noopener noreferrer"' in panel
    assert "최근 뉴스" in panel
    assert "slice(0, expanded ? 10 : 5)" in panel
    assert "Strategy·Scanner·Ranking·Risk 계산을 변경하지 않습니다." in panel
    assert "StockNewsPanel" in workspace
    assert workspace.index("stock-analysis-company-summary") < workspace.index("StockNewsPanel")
    assert workspace.index("StockNewsPanel") < workspace.index("stock-analysis-style-section")
    assert "VITE_NAVER_" not in api + panel + workspace
    assert "NAVER_NEWS_CLIENT_ID=" in env_example
    assert "NAVER_NEWS_CLIENT_SECRET=" in env_example
    assert "NAVER_CLIENT_ID=" not in env_example
    assert "NAVER_CLIENT_SECRET=" not in env_example
    assert "naver_news_client_id" in config
    assert "naver_news_client_secret" in config
