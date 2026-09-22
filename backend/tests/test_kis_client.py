from __future__ import annotations

import pytest

from app.core.config import Settings
from app.integrations.kis.client import (
    KisConfigurationError,
    base_url,
    normalize_environment,
    validate_account_settings,
    validate_settings,
)


def _settings(**overrides):
    values = {
        "kis_app_key": "app-key",
        "kis_app_secret": "app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_env": "real",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_kis_environment_mapping():
    assert normalize_environment("real") == "real"
    assert normalize_environment("prod") == "real"
    assert normalize_environment("virtual") == "virtual"
    assert normalize_environment("vps") == "virtual"
    assert base_url("real") == "https://openapi.koreainvestment.com:9443"
    assert base_url("virtual") == "https://openapivts.koreainvestment.com:29443"


def test_kis_credentials_are_required():
    with pytest.raises(KisConfigurationError):
        validate_settings(_settings(kis_app_key=None))


def test_kis_account_shape_is_validated():
    assert validate_account_settings(_settings()).kis_account_no == "12345678"

    with pytest.raises(KisConfigurationError):
        validate_account_settings(_settings(kis_account_no="1234-5678"))

    with pytest.raises(KisConfigurationError):
        validate_account_settings(_settings(kis_account_product_code="1"))
