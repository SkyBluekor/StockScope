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

    # KIS Open API credentials are loaded only from the project-root .env.
    # Never expose these values through frontend VITE_* variables.
    kis_app_key: str | None = None
    kis_app_secret: str | None = None
    kis_account_no: str | None = None
    kis_account_product_code: str = "01"
    kis_env: str = "real"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
