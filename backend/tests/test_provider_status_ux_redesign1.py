from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.api.data_sources as data_sources_api


def _settings(**overrides):
    values = {
        "krx_api_key": "krx-secret",
        "dart_api_key": "dart-secret",
        "naver_news_client_id": "news-id",
        "naver_news_client_secret": "news-secret",
        "naver_news_provider_kind": "api_hub",
        "kis_app_key": "kis-key",
        "kis_app_secret": "kis-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_provider_status_reports_configured_kis_without_secrets(monkeypatch) -> None:
    settings = _settings()
    monkeypatch.setattr(data_sources_api, "get_settings", lambda: settings)

    body = asyncio.run(data_sources_api.provider_status())

    assert body["kis"]["enabled"] is True
    assert body["kis"]["role"] == "실계좌 잔고 · 현재가 · 실시간 시세"
    assert body["naver_news"]["configured"] is True

    serialized = repr(body)
    for secret in ("krx-secret", "dart-secret", "news-secret", "kis-key", "kis-secret", "12345678"):
        assert secret not in serialized


def test_provider_status_treats_unconfigured_kis_as_optional_disabled(monkeypatch) -> None:
    settings = _settings(kis_app_key=None, kis_app_secret=None, kis_account_no=None)
    monkeypatch.setattr(data_sources_api, "get_settings", lambda: settings)

    body = asyncio.run(data_sources_api.provider_status())

    assert body["kis"]["enabled"] is False
