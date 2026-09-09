from __future__ import annotations

import gzip
import json

import pytest

from app.market.providers.krx import KrxProvider


class _FakeResponse:
    status_code = 200

    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"OutBlock_1": self._rows}


class _FakeClient:
    responses = []
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        type(self).calls += 1
        return _FakeResponse(type(self).responses.pop(0))


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch, tmp_path):
    KrxProvider._rows_cache.clear()
    KrxProvider._cache_expiry.clear()
    monkeypatch.setattr(KrxProvider, "_cache_dir", tmp_path)
    monkeypatch.setattr("app.market.providers.krx.httpx.AsyncClient", _FakeClient)
    _FakeClient.responses = []
    _FakeClient.calls = 0


@pytest.mark.asyncio
async def test_empty_response_is_only_temporarily_cached(monkeypatch):
    provider = KrxProvider("test-key")
    endpoint = provider.INDEX_ENDPOINTS["KOSPI"]
    bas_dd = provider._today_kst().strftime("%Y%m%d")
    _FakeClient.responses = [[], [{"BAS_DD": bas_dd, "IDX_NM": "코스피"}]]

    first = await provider._get_rows(endpoint, bas_dd)
    assert first == []
    assert _FakeClient.calls == 1
    assert not provider._disk_cache_path(endpoint, bas_dd).exists()

    # TTL 안에서는 불필요한 재호출을 막습니다.
    second = await provider._get_rows(endpoint, bas_dd)
    assert second == []
    assert _FakeClient.calls == 1

    # TTL 만료를 흉내 내면 KRX를 다시 확인하고 새 데이터를 받아옵니다.
    key = (endpoint.path, bas_dd)
    provider._cache_expiry[key] = 0
    third = await provider._get_rows(endpoint, bas_dd)
    assert third[0]["IDX_NM"] == "코스피"
    assert _FakeClient.calls == 2


def test_legacy_empty_disk_cache_is_discarded(tmp_path, monkeypatch):
    provider = KrxProvider("test-key")
    endpoint = provider.INDEX_ENDPOINTS["KOSPI"]
    bas_dd = "20260102"
    path = provider._disk_cache_path(endpoint, bas_dd)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fp:
        json.dump([], fp)

    assert provider._load_disk_cache(endpoint, bas_dd) is None
    assert not path.exists()
