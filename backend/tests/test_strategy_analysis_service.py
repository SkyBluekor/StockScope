import pytest

from app.strategy.service import StrategyAnalysisService


class FakeKrx:
    async def stock_history(self, market, code, as_of=None, points=30, lookback_days=60):
        rows = []
        price = 100.0
        for i in range(30):
            price += 1.0
            rows.append(
                {
                    "date": f"202608{i+1:02d}",
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
        return {
            "main_index": {
                "name": "코스피" if market == "KOSPI" else "코스닥",
                "change_rate": 1.5,
            }
        }


@pytest.mark.asyncio
async def test_strategy_analysis_service_returns_ranked_results():
    result = await StrategyAnalysisService(FakeKrx()).analyze("005930", "KOSPI")

    assert result["real_trading"] is False
    assert result["technical"]["ma20"] is not None
    assert result["market_context"]["regime"] == "TREND_UP"
    assert len(result["strategies"]) >= 1
    assert "score" in result["strategies"][0]
