import pytest

from app.market.providers.krx import KrxProvider


@pytest.mark.asyncio
async def test_stock_search_ranks_exact_name_and_returns_market(monkeypatch):
    provider = KrxProvider("test")

    async def fake_latest(market, as_of=None, lookback_days=14):
        rows = {
            "KOSPI": [
                {"code": "005930", "name": "삼성전자", "full_name": "삼성전자", "english_name": "Samsung Electronics", "market": "KOSPI"},
                {"code": "005935", "name": "삼성전자우", "full_name": "삼성전자우", "english_name": "Samsung Electronics Pref", "market": "KOSPI"},
            ],
            "KOSDAQ": [
                {"code": "123456", "name": "삼성테스트", "full_name": "삼성테스트", "english_name": "Samsung Test", "market": "KOSDAQ"},
            ],
        }[market]
        return {"date": "20260907", "count": len(rows), "rows": rows}

    monkeypatch.setattr(provider, "latest_basic_info", fake_latest)
    result = await provider.search_stocks("삼성전자")

    assert result["rows"][0]["code"] == "005930"
    assert result["rows"][0]["market"] == "KOSPI"


@pytest.mark.asyncio
async def test_stock_search_accepts_code_prefix(monkeypatch):
    provider = KrxProvider("test")

    async def fake_latest(market, as_of=None, lookback_days=14):
        rows = [{"code": "005930", "name": "삼성전자", "full_name": "삼성전자", "english_name": "Samsung Electronics", "market": market}] if market == "KOSPI" else []
        return {"date": "20260907", "count": len(rows), "rows": rows}

    monkeypatch.setattr(provider, "latest_basic_info", fake_latest)
    result = await provider.search_stocks("0059")
    assert result["count"] == 1
