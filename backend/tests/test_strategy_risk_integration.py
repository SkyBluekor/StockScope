import pytest

from app.strategy.service import StrategyAnalysisService


class FakeKrx:
    async def stock_history(self, market, code, as_of=None, points=60, lookback_days=120):
        rows = []
        price = 70000.0
        for i in range(60):
            price += 250.0
            rows.append({
                "date": f"20260{(i // 28) + 7:02d}{(i % 28) + 1:02d}",
                "code": code,
                "name": "테스트",
                "market": market,
                "open": price - 200,
                "high": price + 500,
                "low": price - 500,
                "close": price,
                "volume": 2_000_000,
                "trade_value": 5_000_000_000,
            })
        return rows

    async def latest_index_daily(self, market, as_of=None):
        return {"main_index": {"name": "코스피", "change_rate": 1.2}}


@pytest.mark.asyncio
async def test_strategy_analysis_contains_risk_analysis():
    result = await StrategyAnalysisService(FakeKrx()).analyze("005930", "KOSPI")

    assert result["risk_analysis"]["policy"]["real_trading"] is False
    assert result["risk_analysis"]["policy"]["order_execution"] is False
    assert "plans" in result["risk_analysis"]
    assert len(result["risk_analysis"]["plans"]) >= 1
