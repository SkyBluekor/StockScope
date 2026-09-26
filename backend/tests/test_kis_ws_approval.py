from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.core.config import Settings
import app.integrations.kis.ws_approval as ws_approval


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        kis_app_key="app-key",
        kis_app_secret="app-secret",
        kis_env="real",
    )


def test_approval_request_uses_dedicated_kis_contract() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"approval_key": "ws-approval"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    issued = ws_approval.issue_ws_approval_key(_settings(), http_client=client)

    assert seen["path"] == "/oauth2/Approval"
    assert '"grant_type":"client_credentials"' in seen["body"].replace(" ", "")
    assert '"appkey":"app-key"' in seen["body"].replace(" ", "")
    assert '"secretkey":"app-secret"' in seen["body"].replace(" ", "")
    assert issued.approval_key == "ws-approval"


def test_approval_cache_is_process_memory_single_flight(monkeypatch) -> None:
    settings = _settings()
    ws_approval._APPROVAL_CACHE.clear()
    calls = {"count": 0}

    def issue(current_settings):
        calls["count"] += 1
        time.sleep(0.03)
        return ws_approval.KisWebSocketApproval(
            approval_key="one-key",
            credential_fingerprint=ws_approval.credential_fingerprint(current_settings),
        )

    monkeypatch.setattr(ws_approval, "issue_ws_approval_key", issue)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _index: ws_approval.get_ws_approval_key(settings), range(10)))

    assert calls["count"] == 1
    assert {item.approval_key for item in results} == {"one-key"}

    assert ws_approval.invalidate_ws_approval_key(
        settings,
        expected_approval_key="wrong-key",
    ) is False
    assert ws_approval.invalidate_ws_approval_key(
        settings,
        expected_approval_key="one-key",
    ) is True
