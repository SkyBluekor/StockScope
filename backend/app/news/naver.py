from __future__ import annotations

import asyncio
import hashlib
import html
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx

from app.news.models import NewsError, NewsItem
from app.news.policy import NewsSourcePolicy

_TAG_RE = re.compile(r"<[^>]+>")
_TRACKING_PARAMS = {"fbclid", "gclid", "igshid"}


class NaverNewsProvider:
    _ENDPOINTS = {
        "developer_center": "https://openapi.naver.com/v1/search/news.json",
        "api_hub": "https://naverapihub.apigw.ntruss.com/search/v1/news",
    }

    def __init__(
        self,
        client_id: str | None,
        client_secret: str | None,
        provider_kind: str,
        policy: NewsSourcePolicy,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.provider_kind = (provider_kind or "").strip().lower()
        self.policy = policy
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _require_configured(self) -> None:
        if not self.configured:
            raise NewsError("NEWS_NOT_CONFIGURED", "네이버 뉴스 API 키가 설정되지 않았습니다.")

    def _headers(self) -> dict[str, str]:
        self._require_configured()
        if self.provider_kind == "developer_center":
            return {
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret,
                "Accept": "application/json",
            }
        if self.provider_kind == "api_hub":
            return {
                "X-NCP-APIGW-API-KEY-ID": self.client_id,
                "X-NCP-APIGW-API-KEY": self.client_secret,
                "Accept": "application/json",
            }
        raise NewsError("NEWS_NOT_CONFIGURED", "네이버 뉴스 provider 종류가 올바르지 않습니다.")

    @staticmethod
    def _plain_text(value: Any) -> str:
        text = html.unescape(str(value or ""))
        text = _TAG_RE.sub("", text)
        return " ".join(text.split()).strip()

    @staticmethod
    def _safe_url(value: Any) -> str | None:
        raw = html.unescape(str(value or "")).strip()
        if not raw:
            return None
        try:
            parsed = urlsplit(raw)
        except ValueError:
            return None
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        filtered_query = [
            (key, val)
            for key, val in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
        ]
        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc,
                parsed.path,
                urlencode(filtered_query, doseq=True),
                "",
            )
        )

    @staticmethod
    def _published_at(value: Any) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            dt = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return dt.astimezone(ZoneInfo("Asia/Seoul")).isoformat()

    @staticmethod
    def _retry_after(response: httpx.Response) -> int | None:
        raw = response.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return max(0, int(raw))
        except ValueError:
            return None

    async def _request(self, query: str, limit: int) -> httpx.Response:
        endpoint = self._ENDPOINTS.get(self.provider_kind)
        if endpoint is None:
            raise NewsError("NEWS_NOT_CONFIGURED", "네이버 뉴스 provider 종류가 올바르지 않습니다.")
        params: dict[str, Any] = {
            "query": query,
            "display": limit,
            "start": 1,
            "sort": "date",
        }
        if self.provider_kind == "api_hub":
            params["format"] = "json"

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=4.0),
            follow_redirects=False,
        )
        try:
            last_error: Exception | None = None
            for attempt in range(2):
                try:
                    response = await client.get(endpoint, params=params, headers=self._headers())
                except httpx.TimeoutException as exc:
                    last_error = exc
                    if attempt == 0:
                        await asyncio.sleep(0.2)
                        continue
                    raise NewsError("NEWS_TIMEOUT", "네이버 뉴스 응답 시간이 초과되었습니다.", retryable=True) from exc
                except httpx.RequestError as exc:
                    last_error = exc
                    if attempt == 0:
                        await asyncio.sleep(0.2)
                        continue
                    raise NewsError("NEWS_PROVIDER_FAILED", "네이버 뉴스 서비스에 연결하지 못했습니다.", retryable=True) from exc

                if response.status_code in {401, 403}:
                    raise NewsError("NEWS_AUTH_FAILED", "네이버 뉴스 API 인증에 실패했습니다.")
                if response.status_code == 429:
                    raise NewsError(
                        "NEWS_RATE_LIMITED",
                        "네이버 뉴스 API 호출 한도에 도달했습니다.",
                        retry_after=self._retry_after(response),
                    )
                if 500 <= response.status_code < 600:
                    if attempt == 0:
                        await asyncio.sleep(0.2)
                        continue
                    raise NewsError("NEWS_PROVIDER_FAILED", "네이버 뉴스 서비스가 일시적으로 응답하지 않습니다.", retryable=True)
                if response.status_code >= 400:
                    raise NewsError("NEWS_PROVIDER_FAILED", f"네이버 뉴스 요청을 처리하지 못했습니다. ({response.status_code})")
                return response

            raise NewsError("NEWS_PROVIDER_FAILED", "네이버 뉴스 요청을 처리하지 못했습니다.", retryable=True) from last_error
        finally:
            if owns_client:
                await client.aclose()

    def _parse_item(self, raw: Any, query: str, fetched_at: str) -> NewsItem | None:
        if not isinstance(raw, dict):
            return None
        title = self._plain_text(raw.get("title"))
        description = self._plain_text(raw.get("description"))
        source_url = self._safe_url(raw.get("link"))
        original_url = self._safe_url(raw.get("originallink"))
        url = original_url or source_url
        if not title or not url or not source_url:
            return None
        domain = urlsplit(url).hostname
        stable_key = f"{self.provider_kind}|{source_url}|{url}".encode("utf-8")
        return NewsItem(
            id=hashlib.sha256(stable_key).hexdigest()[:24],
            title=title,
            description=description,
            url=url,
            source_url=source_url,
            source_name=None,
            source_domain=domain.lower() if domain else None,
            provider=f"NAVER_{self.provider_kind.upper()}",
            published_at=self._published_at(raw.get("pubDate")),
            timestamp_kind="NAVER_PROVIDER_PUBDATE",
            query=query,
            fetched_at=fetched_at,
        )

    async def search(self, query: str, limit: int) -> tuple[tuple[NewsItem, ...], str, int]:
        if not self.policy.display_allowed:
            raise NewsError("NEWS_USAGE_NOT_ALLOWED", "현재 source 정책에서는 뉴스 표시가 허용되지 않습니다.")
        normalized_query = " ".join((query or "").split()).strip()
        if len(normalized_query) < 2:
            raise NewsError("NEWS_QUERY_INVALID", "뉴스 검색에 사용할 유효한 회사명을 확인하지 못했습니다.")
        if not 1 <= limit <= 10:
            raise NewsError("NEWS_QUERY_INVALID", "뉴스 조회 개수는 1~10이어야 합니다.")

        response = await self._request(normalized_query, limit)
        try:
            payload = response.json()
        except ValueError as exc:
            raise NewsError("NEWS_PROVIDER_FAILED", "네이버 뉴스 응답 형식이 올바르지 않습니다.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise NewsError("NEWS_PROVIDER_FAILED", "네이버 뉴스 응답 구조가 올바르지 않습니다.")

        fetched_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
        items: list[NewsItem] = []
        discarded = 0
        for raw in payload["items"]:
            parsed = self._parse_item(raw, normalized_query, fetched_at)
            if parsed is None:
                discarded += 1
                continue
            items.append(parsed)
        return tuple(items), fetched_at, discarded
