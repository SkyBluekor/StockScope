from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

import httpx

from app.core.config import Settings, get_settings

from .client import base_url, validate_settings
from .token_cache import credential_fingerprint


_APPROVAL_PATH = "/oauth2/Approval"
_APPROVAL_LOCK = Lock()
_APPROVAL_CACHE: dict[str, str] = {}


class KisWebSocketApprovalError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class KisWebSocketApproval:
    approval_key: str
    credential_fingerprint: str


def issue_ws_approval_key(
    settings: Settings | None = None,
    *,
    timeout_seconds: float = 15.0,
    http_client: httpx.Client | None = None,
) -> KisWebSocketApproval:
    settings = validate_settings(settings or get_settings())
    payload = {
        "grant_type": "client_credentials",
        "appkey": settings.kis_app_key,
        "secretkey": settings.kis_app_secret,
    }
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds)
    try:
        try:
            response = client.post(
                f"{base_url(settings.kis_env)}{_APPROVAL_PATH}",
                headers={"content-type": "application/json"},
                json=payload,
                timeout=timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise KisWebSocketApprovalError(
                f"KIS websocket approval request failed before receiving a response: {exc}"
            ) from exc

        if response.status_code != 200:
            raise KisWebSocketApprovalError(
                "KIS websocket approval issuance failed.",
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise KisWebSocketApprovalError(
                "KIS websocket approval response was not valid JSON.",
                status_code=response.status_code,
            ) from exc
        if not isinstance(body, dict):
            raise KisWebSocketApprovalError(
                "KIS websocket approval response had an unexpected shape."
            )
        approval_key = str(body.get("approval_key") or "").strip()
        if not approval_key:
            raise KisWebSocketApprovalError(
                "KIS websocket approval response did not contain approval_key."
            )
        return KisWebSocketApproval(
            approval_key=approval_key,
            credential_fingerprint=credential_fingerprint(settings),
        )
    finally:
        if owns_client:
            client.close()


def get_ws_approval_key(settings: Settings | None = None) -> KisWebSocketApproval:
    settings = validate_settings(settings or get_settings())
    fingerprint = credential_fingerprint(settings)
    cached = _APPROVAL_CACHE.get(fingerprint)
    if cached:
        return KisWebSocketApproval(cached, fingerprint)

    # Same-process single-flight: only one thread issues a key per credentials.
    with _APPROVAL_LOCK:
        cached = _APPROVAL_CACHE.get(fingerprint)
        if cached:
            return KisWebSocketApproval(cached, fingerprint)
        issued = issue_ws_approval_key(settings)
        _APPROVAL_CACHE[fingerprint] = issued.approval_key
        return issued


def invalidate_ws_approval_key(
    settings: Settings | None = None,
    *,
    expected_approval_key: str | None = None,
) -> bool:
    settings = validate_settings(settings or get_settings())
    fingerprint = credential_fingerprint(settings)
    with _APPROVAL_LOCK:
        cached = _APPROVAL_CACHE.get(fingerprint)
        if cached is None:
            return False
        if expected_approval_key is not None and cached != expected_approval_key:
            return False
        _APPROVAL_CACHE.pop(fingerprint, None)
        return True
