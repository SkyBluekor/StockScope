from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class NewsSourcePolicy:
    provider_kind: str
    policy_version: str
    display_allowed: bool
    display_normalization_allowed: bool
    transform_allowed: bool
    ai_allowed: bool
    retention_policy: str
    server_cache_seconds: int
    attribution_required: bool

    def to_public_dict(self) -> dict[str, object]:
        return asdict(self)


_POLICIES = {
    "developer_center": NewsSourcePolicy(
        provider_kind="developer_center",
        policy_version="naver-developer-search-terms-2026-09-07",
        display_allowed=True,
        display_normalization_allowed=True,
        transform_allowed=False,
        ai_allowed=False,
        retention_policy="TEMPORARY_SERVER_CACHE_ONLY_WITHIN_SEARCH_API_TERMS",
        server_cache_seconds=300,
        attribution_required=True,
    ),
    "api_hub": NewsSourcePolicy(
        provider_kind="api_hub",
        policy_version="naver-api-hub-news1-conservative-2026-09-25",
        display_allowed=True,
        display_normalization_allowed=True,
        transform_allowed=False,
        ai_allowed=False,
        retention_policy="NO_SERVER_RESULT_CACHE_UNTIL_API_HUB_RETENTION_TERMS_ARE_CONFIRMED",
        server_cache_seconds=0,
        attribution_required=True,
    ),
}


def policy_for(provider_kind: str) -> NewsSourcePolicy:
    key = (provider_kind or "").strip().lower()
    policy = _POLICIES.get(key)
    if policy is None:
        raise ValueError("NAVER_NEWS_PROVIDER_KIND는 developer_center 또는 api_hub여야 합니다.")
    return policy
