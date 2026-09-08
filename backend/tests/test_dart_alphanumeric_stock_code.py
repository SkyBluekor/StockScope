import pytest

from app.market.providers.dart import OpenDartProvider


@pytest.mark.asyncio
async def test_dart_resolve_accepts_alphanumeric_stock_code(monkeypatch):
    provider = OpenDartProvider("test")

    async def fake_mapping():
        return {"0011A0": "12345678"}

    monkeypatch.setattr(provider, "_load_stock_corp_map", fake_mapping)
    assert await provider.resolve_corp_code("0011a0") == "12345678"
