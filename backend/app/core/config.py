from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "StockScope API"
    app_version: str = "0.5.0"
    environment: str = "development"

    krx_api_key: str | None = None
    dart_api_key: str | None = None
    llm_api_key: str | None = None

    # NAVER Search News API credentials are backend-only.
    # provider_kind: "api_hub" (NCP) or "developer_center" (legacy).
    naver_news_client_id: str | None = None
    naver_news_client_secret: str | None = None
    naver_news_provider_kind: str = "api_hub"

    # KIS Open API credentials are loaded only from the project-root .env.
    # Never expose these values through frontend VITE_* variables.
    kis_app_key: str | None = None
    kis_app_secret: str | None = None
    kis_account_no: str | None = None
    kis_account_product_code: str = "01"
    kis_env: str = "real"
    kis_quote_cache_ttl_seconds: float = 2.0
    kis_quote_freshness_seconds: float = 15.0
    kis_quote_min_upstream_interval_seconds: float = 0.25
    kis_ws_enabled: bool = True
    kis_ws_real_url: str = "ws://ops.koreainvestment.com:21000"
    kis_ws_virtual_url: str = "ws://ops.koreainvestment.com:31000"
    kis_ws_max_subscriptions: int = 40
    kis_ws_demand_ttl_seconds: float = 45.0
    kis_ws_reconnect_base_seconds: float = 1.0
    kis_ws_reconnect_max_seconds: float = 30.0

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
