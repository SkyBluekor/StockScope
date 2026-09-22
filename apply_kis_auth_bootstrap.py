from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
CONFIG = ROOT / "backend" / "app" / "core" / "config.py"
KIS_DIR = ROOT / "backend" / "app" / "integrations" / "kis"
KIS_INIT = KIS_DIR / "__init__.py"
KIS_CLIENT = KIS_DIR / "client.py"
TEST = ROOT / "backend" / "tests" / "test_kis_client.py"

CLIENT = r"""from __future__ import annotations

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
"""

INIT = """from .client import (
    KisAccessToken,
    KisAuthenticationError,
    KisConfigurationError,
    base_url,
    issue_access_token,
    normalize_environment,
    validate_account_settings,
    validate_settings,
)

__all__ = [
    "KisAccessToken",
    "KisAuthenticationError",
    "KisConfigurationError",
    "base_url",
    "issue_access_token",
    "normalize_environment",
    "validate_account_settings",
    "validate_settings",
]
"""

TEST_CONTENT = r"""from __future__ import annotations

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
"""


def fail(message: str) -> None:
    raise RuntimeError(message)


def patch_config(text: str) -> str:
    if "kis_app_key:" in text:
        return text

    anchor = """    krx_api_key: str | None = None
    dart_api_key: str | None = None
    llm_api_key: str | None = None
"""
    replacement = anchor + """
    # KIS Open API credentials are loaded only from the project-root .env.
    # Never expose these values through frontend VITE_* variables.
    kis_app_key: str | None = None
    kis_app_secret: str | None = None
    kis_account_no: str | None = None
    kis_account_product_code: str = "01"
    kis_env: str = "real"
"""
    if text.count(anchor) != 1:
        fail("config.py KIS insertion anchor was not found exactly once.")
    return text.replace(anchor, replacement, 1)


def run(cmd: list[str], label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def main() -> int:
    if not CONFIG.is_file():
        fail(f"Missing config file: {CONFIG}")

    original = CONFIG.read_text(encoding="utf-8-sig")
    patched = patch_config(original)
    compile(patched, str(CONFIG), "exec")
    compile(CLIENT, str(KIS_CLIENT), "exec")
    compile(TEST_CONTENT, str(TEST), "exec")

    KIS_DIR.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    config_changed = patched != original

    try:
        if config_changed:
            CONFIG.write_text(patched, encoding="utf-8", newline="\n")

        if not KIS_INIT.exists():
            KIS_INIT.write_text(INIT, encoding="utf-8", newline="\n")
            created.append(KIS_INIT)

        if KIS_CLIENT.exists():
            fail(f"Target already exists: {KIS_CLIENT}")
        KIS_CLIENT.write_text(CLIENT, encoding="utf-8", newline="\n")
        created.append(KIS_CLIENT)

        if TEST.exists():
            fail(f"Target already exists: {TEST}")
        TEST.write_text(TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(TEST)

        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        python_exe = str(venv_python if venv_python.is_file() else Path(sys.executable))

        run(
            [python_exe, "-m", "pytest", "backend/tests/test_kis_client.py", "-q"],
            "KIS local configuration tests",
        )

        check_code = (
            "import sys; sys.path.insert(0,'backend'); "
            "from app.core.config import get_settings; "
            "from app.integrations.kis.client import validate_account_settings; "
            "s=validate_account_settings(get_settings()); "
            "print('APP_KEY: SET'); "
            "print('APP_SECRET: SET'); "
            "print('ACCOUNT: SET'); "
            "print('PRODUCT:', s.kis_account_product_code); "
            "print('ENV:', s.kis_env)"
        )
        run([python_exe, "-c", check_code], "KIS .env validation")

        smoke_code = (
            "import sys; sys.path.insert(0,'backend'); "
            "from app.integrations.kis.client import issue_access_token; "
            "t=issue_access_token(); "
            "print('TOKEN: ISSUED'); "
            "print('TYPE:', t.token_type or '-'); "
            "print('EXPIRES_IN:', t.expires_in if t.expires_in is not None else '-'); "
            "print('EXPIRES_AT:', t.expires_at or '-')"
        )
        run([python_exe, "-c", smoke_code], "KIS access-token smoke")

        print()
        print("KIS AUTH BOOTSTRAP COMPLETE")
        print("Modified:")
        if config_changed:
            print(" - backend/app/core/config.py")
        print("Added:")
        print(" - backend/app/integrations/kis/__init__.py")
        print(" - backend/app/integrations/kis/client.py")
        print(" - backend/tests/test_kis_client.py")
        print("Secrets printed: NO")
        print("Frontend exposure: NO")
        print("Account API called: NO")
        print("Order API called: NO")
        return 0

    except Exception:
        if config_changed:
            CONFIG.write_text(original, encoding="utf-8", newline="\n")
        for path in reversed(created):
            if path.exists():
                path.unlink()
        print()
        print("FAILED — KIS bootstrap changes were restored.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
