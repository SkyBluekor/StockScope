from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class NewsError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class NewsItem:
    id: str
    title: str
    description: str
    url: str
    source_url: str
    source_name: str | None
    source_domain: str | None
    provider: str
    published_at: str | None
    timestamp_kind: str
    query: str
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NewsResponse:
    code: str
    market: str
    company_name: str
    query: str
    fetched_at: str
    status: str
    items: tuple[NewsItem, ...]
    cache_hit: bool
    cache_stale: bool
    discarded_items: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "market": self.market,
            "company_name": self.company_name,
            "query": self.query,
            "fetched_at": self.fetched_at,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "count": len(self.items),
            "cache": {"hit": self.cache_hit, "stale": self.cache_stale},
            "discarded_items": self.discarded_items,
        }
