import pytest

from app.market.service import MarketDataService


class FakeKrx:
    async def latest_index_daily(self, market, as_of=None):
        return {
            "date": "20260907",
            "requested_date": "20260908",
            "fallback_used": True,
            "main_index": {"name": "코스피" if market == "KOSPI" else "코스닥", "change_rate": 1.0},
            "rows": [],
        }

    async def stock_daily(self, market, bas_date, code=None):
        return {"rows": [], "count": 0, "date": str(bas_date)}


class FakeDart:
    pass


@pytest.mark.asyncio
async def test_dashboard_explains_fallback_reason():
    result = await MarketDataService(FakeKrx(), FakeDart()).market_dashboard()

    assert result["fallback_used"] is True
    assert result["data_freshness"]["status"] == "FALLBACK"
    assert "2026.09.08" in result["data_freshness"]["message"]
    assert "2026.09.07" in result["data_freshness"]["message"]
    assert "5분" in result["data_freshness"]["retry_note"]
