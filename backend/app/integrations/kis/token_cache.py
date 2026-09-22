from __future__ import annotations

import hashlib
import json
import time

from app.core.config import PROJECT_ROOT, Settings, get_settings

from .client import KisAccessToken, issue_access_token, normalize_environment, validate_settings


_CACHE_PATH = PROJECT_ROOT / "backend" / "runtime" / "kis" / "access_token.json"
_REFRESH_MARGIN_SECONDS = 300


def _credential_fingerprint(settings: Settings) -> str:
    raw = f"{normalize_environment(settings.kis_env)}:{settings.kis_app_key or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_cached(settings: Settings) -> KisAccessToken | None:
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None

    if data.get("credential_fingerprint") != _credential_fingerprint(settings):
        return None

    try:
        usable_until = float(data.get("usable_until_epoch") or 0)
    except (TypeError, ValueError):
        return None

    if usable_until <= time.time():
        return None

    token = str(data.get("access_token") or "")
    if not token:
        return None

    expires_in_raw = data.get("expires_in")
    try:
        expires_in = int(expires_in_raw) if expires_in_raw is not None else None
    except (TypeError, ValueError):
        expires_in = None

    return KisAccessToken(
        access_token=token,
        token_type=str(data.get("token_type")) if data.get("token_type") else None,
        expires_in=expires_in,
        expires_at=str(data.get("expires_at")) if data.get("expires_at") else None,
    )


def _save_cached(settings: Settings, token: KisAccessToken) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lifetime = token.expires_in if token.expires_in and token.expires_in > 0 else 86400
    usable_until = time.time() + max(60, lifetime - _REFRESH_MARGIN_SECONDS)

    payload = {
        "credential_fingerprint": _credential_fingerprint(settings),
        "access_token": token.access_token,
        "token_type": token.token_type,
        "expires_in": token.expires_in,
        "expires_at": token.expires_at,
        "usable_until_epoch": usable_until,
    }
    _CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_access_token(settings: Settings | None = None) -> KisAccessToken:
    settings = validate_settings(settings or get_settings())

    cached = _load_cached(settings)
    if cached is not None:
        return cached

    token = issue_access_token(settings)
    _save_cached(settings, token)
    return token
