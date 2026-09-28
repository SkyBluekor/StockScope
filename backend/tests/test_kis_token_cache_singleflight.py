from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.core.config import Settings
from app.integrations.kis.client import KisAccessToken
import app.integrations.kis.token_cache as token_cache


def _settings(**overrides) -> Settings:
    values = {
        "kis_app_key": "app-key",
        "kis_app_secret": "app-secret",
        "kis_env": "real",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _token(value: str) -> KisAccessToken:
    return KisAccessToken(
        access_token=value,
        token_type="Bearer",
        expires_in=3600,
        expires_at=None,
    )


def test_token_cache_is_process_single_flight(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(token_cache, "_CACHE_PATH", tmp_path / "access_token.json")
    calls = {"count": 0}

    def issue(_settings):
        calls["count"] += 1
        time.sleep(0.05)
        return _token("shared-token")

    monkeypatch.setattr(token_cache, "issue_access_token", issue)
    settings = _settings()

    with ThreadPoolExecutor(max_workers=10) as pool:
        tokens = list(pool.map(lambda _index: token_cache.get_access_token(settings), range(10)))

    assert calls["count"] == 1
    assert {item.access_token for item in tokens} == {"shared-token"}


def test_token_fingerprint_changes_when_secret_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(token_cache, "_CACHE_PATH", tmp_path / "access_token.json")
    issued: list[str] = []

    def issue(settings):
        value = f"token-{len(issued) + 1}"
        issued.append(settings.kis_app_secret or "")
        return _token(value)

    monkeypatch.setattr(token_cache, "issue_access_token", issue)

    first = token_cache.get_access_token(_settings(kis_app_secret="secret-a"))
    second = token_cache.get_access_token(_settings(kis_app_secret="secret-b"))

    assert first.access_token == "token-1"
    assert second.access_token == "token-2"
    assert issued == ["secret-a", "secret-b"]


def test_invalidation_only_removes_the_failed_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(token_cache, "_CACHE_PATH", tmp_path / "access_token.json")
    monkeypatch.setattr(token_cache, "issue_access_token", lambda _settings: _token("fresh-token"))
    settings = _settings()

    assert token_cache.get_access_token(settings).access_token == "fresh-token"
    assert token_cache.invalidate_access_token(
        settings,
        expected_access_token="old-token",
    ) is False
    assert token_cache.get_access_token(settings).access_token == "fresh-token"

    assert token_cache.invalidate_access_token(
        settings,
        expected_access_token="fresh-token",
    ) is True
    assert not token_cache._CACHE_PATH.exists()


def test_token_cache_write_is_atomic_and_leaves_no_temp_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cache_path = tmp_path / "runtime" / "access_token.json"
    monkeypatch.setattr(token_cache, "_CACHE_PATH", cache_path)
    monkeypatch.setattr(token_cache, "issue_access_token", lambda _settings: _token("atomic-token"))

    result = token_cache.get_access_token(_settings())

    assert result.access_token == "atomic-token"
    assert cache_path.is_file()
    assert list(cache_path.parent.glob("*.tmp")) == []
