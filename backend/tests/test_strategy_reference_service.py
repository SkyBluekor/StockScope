import pytest

from app.strategy.service import StrategyAnalysisService


class FakeKrxReference:
    async def stock_history(self, market, code, as_of=None, points=60, lookback_days=120):
        rows = []
        price = 100.0
        for index in range(30):
            price += 1.0
            rows.append(
                {
                    "date": f"202608{index + 1:02d}",
                    "code": code,
                    "name": "테스트",
                    "market": market,
                    "open": price - 0.5,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price,
                    "volume": 1_000_000,
                    "trade_value": 5_000_000_000,
                }
            )
        return rows

    async def latest_index_daily(self, market, as_of=None):
        return {"main_index": {"name": "코스피", "change_rate": 1.2}}


@pytest.mark.asyncio
async def test_service_keeps_eod_and_manual_reference_separate():
    result = await StrategyAnalysisService(FakeKrxReference()).analyze(
        "005930", "KOSPI", reference_price=160.0
    )

    freshness = result["data_freshness"]
    assert freshness["price_source"] == "USER_INPUT"
    assert freshness["eod_close"] == 130.0
    assert freshness["reference"]["reference_price"] == 160.0
    assert result["effective"]["price"] == 160.0
    assert result["technical"]["current_price"] == 130.0
