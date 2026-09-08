import io
from datetime import date
from zipfile import ZipFile

import pytest

from app.market.providers.dart import OpenDartProvider
from app.market.providers.krx import KrxProvider


@pytest.mark.asyncio
async def test_latest_stock_falls_back_to_previous_business_day(monkeypatch):
    provider = KrxProvider("test-key")
    calls = []

    async def fake_get_rows(endpoint, bas_dd):
        calls.append(bas_dd)
        if bas_dd == "20260908":
            return []
        return [{"BAS_DD": bas_dd, "ISU_CD": "005930", "ISU_NM": "삼성전자", "TDD_CLSPRC": "270000"}]

    monkeypatch.setattr(provider, "_get_rows", fake_get_rows)
    result = await provider.latest_stock_daily("KOSPI", "005930", date(2026, 9, 8))

    assert result["count"] == 1
    assert result["date"] == "20260907"
    assert result["fallback_used"] is True
    assert calls[:2] == ["20260908", "20260907"]


@pytest.mark.asyncio
async def test_dart_stock_code_mapping(monkeypatch):
    xml = """<?xml version='1.0' encoding='UTF-8'?><result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code></list></result>""".encode("utf-8")
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)

    class Response:
        status_code = 200
        content = buffer.getvalue()

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get(self, *args, **kwargs): return Response()

    monkeypatch.setattr("httpx.AsyncClient", lambda *args, **kwargs: Client())
    OpenDartProvider._stock_to_corp_cache = None
    provider = OpenDartProvider("test-key")
    corp_code = await provider.resolve_corp_code("005930")
    assert corp_code == "00126380"
