from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.integrations as integrations_api


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(integrations_api.router, prefix="/api")
    return TestClient(app)


def _settings(**overrides):
    values = {
        "kis_app_key": "kis-key",
        "kis_app_secret": "kis-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_env": "real",
        "krx_api_key": "krx-secret",
        "dart_api_key": "dart-secret",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_status_reports_configuration_without_exposing_secrets(client, monkeypatch):
    settings = _settings(dart_api_key=None)
    monkeypatch.setattr(integrations_api, "get_settings", lambda: settings)

    response = client.get("/api/integrations/status")
    assert response.status_code == 200
    body = response.json()
    assert body["kis"]["status"] == "CONFIGURED"
    assert body["krx"]["status"] == "CONFIGURED"
    assert body["dart"]["status"] == "NOT_CONFIGURED"

    serialized = response.text
    for secret in (
        "kis-key",
        "kis-secret",
        "12345678",
        "krx-secret",
        "dart-secret",
    ):
        assert secret not in serialized


def test_check_requires_configuration(client, monkeypatch):
    settings = _settings(
        kis_app_key=None,
        kis_app_secret=None,
        kis_account_no=None,
    )
    monkeypatch.setattr(integrations_api, "get_settings", lambda: settings)

    response = client.post("/api/integrations/kis/check")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "KIS_NOT_CONFIGURED"


@pytest.mark.parametrize("provider", ["kis", "krx", "dart"])
def test_explicit_check_delegates_to_read_only_provider_check(
    client,
    monkeypatch,
    provider,
):
    settings = _settings()
    monkeypatch.setattr(integrations_api, "get_settings", lambda: settings)

    calls = []
    async def fake_check(value):
        calls.append(value)
        return {"configured": True, "reachable": True}

    monkeypatch.setattr(integrations_api, f"_check_{provider}", fake_check)
    response = client.post(f"/api/integrations/{provider}/check")
    assert response.status_code == 200
    assert response.json()["provider"] == provider
    assert response.json()["status"] == "CONNECTED"
    assert response.json()["reachable"] is True
    assert calls == [settings]


def test_status_api_does_not_write_env_file():
    source = open("backend/app/api/integrations.py", encoding="utf-8").read()
    assert "write_text" not in source
    assert "dotenv" not in source.lower()
    assert ".env" not in source
