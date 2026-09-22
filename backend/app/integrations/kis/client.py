from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

from app.core.config import Settings, get_settings


KisEnvironment = Literal["real", "virtual"]

_REAL_BASE_URL = "https://openapi.koreainvestment.com:9443"
_VIRTUAL_BASE_URL = "https://openapivts.koreainvestment.com:29443"
_TOKEN_PATH = "/oauth2/tokenP"


class KisConfigurationError(RuntimeError):
    pass


class KisAuthenticationError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class KisAccessToken:
    access_token: str
    token_type: str | None
    expires_in: int | None
    expires_at: str | None


def normalize_environment(value: str | None) -> KisEnvironment:
    normalized = (value or "real").strip().lower()
    aliases = {
        "real": "real",
        "prod": "real",
        "production": "real",
        "virtual": "virtual",
        "paper": "virtual",
        "vps": "virtual",
        "mock": "virtual",
    }
    resolved = aliases.get(normalized)
    if resolved is None:
        raise KisConfigurationError(
            "KIS_ENV must be one of real/prod/production or virtual/paper/vps/mock."
        )
    return resolved  # type: ignore[return-value]


def base_url(environment: str | None) -> str:
    return _REAL_BASE_URL if normalize_environment(environment) == "real" else _VIRTUAL_BASE_URL


def validate_settings(settings: Settings | None = None) -> Settings:
    settings = settings or get_settings()
    missing: list[str] = []
    if not settings.kis_app_key:
        missing.append("KIS_APP_KEY")
    if not settings.kis_app_secret:
        missing.append("KIS_APP_SECRET")
    if missing:
        raise KisConfigurationError(
            "Missing KIS environment variables: " + ", ".join(missing)
        )
    normalize_environment(settings.kis_env)
    return settings


def validate_account_settings(settings: Settings | None = None) -> Settings:
    settings = validate_settings(settings)
    missing: list[str] = []
    if not settings.kis_account_no:
        missing.append("KIS_ACCOUNT_NO")
    if not settings.kis_account_product_code:
        missing.append("KIS_ACCOUNT_PRODUCT_CODE")
    if missing:
        raise KisConfigurationError(
            "Missing KIS account environment variables: " + ", ".join(missing)
        )

    account = settings.kis_account_no.strip()
    product = settings.kis_account_product_code.strip()

    if not account.isdigit() or len(account) != 8:
        raise KisConfigurationError(
            "KIS_ACCOUNT_NO must contain the first 8 digits of the account number."
        )
    if not product.isdigit() or len(product) != 2:
        raise KisConfigurationError(
            "KIS_ACCOUNT_PRODUCT_CODE must contain the last 2 digits."
        )
    return settings


def issue_access_token(
    settings: Settings | None = None,
    *,
    timeout_seconds: float = 15.0,
) -> KisAccessToken:
    settings = validate_settings(settings)

    payload = {
        "grant_type": "client_credentials",
        "appkey": settings.kis_app_key,
        "appsecret": settings.kis_app_secret,
    }

    try:
        response = httpx.post(
            f"{base_url(settings.kis_env)}{_TOKEN_PATH}",
            headers={"content-type": "application/json"},
            json=payload,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KisAuthenticationError(
            f"KIS token request failed before receiving a response: {exc}"
        ) from exc

    if response.status_code != 200:
        message = "KIS access-token issuance failed"
        try:
            body = response.json()
            if isinstance(body, dict):
                safe_parts = [
                    str(body.get(key))
                    for key in ("error_description", "msg1", "msg_cd", "error")
                    if body.get(key)
                ]
                if safe_parts:
                    message += ": " + " / ".join(safe_parts)
        except Exception:
            pass
        raise KisAuthenticationError(message, status_code=response.status_code)

    try:
        data = response.json()
    except ValueError as exc:
        raise KisAuthenticationError(
            "KIS token response was not valid JSON.",
            status_code=response.status_code,
        ) from exc

    token = str(data.get("access_token") or "")
    if not token:
        raise KisAuthenticationError(
            "KIS token response did not contain access_token.",
            status_code=response.status_code,
        )

    expires_in_raw = data.get("expires_in")
    try:
        expires_in = int(expires_in_raw) if expires_in_raw is not None else None
    except (TypeError, ValueError):
        expires_in = None

    return KisAccessToken(
        access_token=token,
        token_type=str(data.get("token_type")) if data.get("token_type") else None,
        expires_in=expires_in,
        expires_at=(
            str(data.get("access_token_token_expired"))
            if data.get("access_token_token_expired")
            else None
        ),
    )
