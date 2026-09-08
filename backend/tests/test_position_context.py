import pytest

from app.strategy.service import StrategyAnalysisService


class FakeKrx:
    async def stock_history(self, market, code, as_of=None, points=60, lookback_days=120):
        rows = []
        price = 100.0
        for i in range(60):
            price += 0.8
            rows.append(
                {
                    "date": f"20260{1 + (i // 28)}{(i % 28) + 1:02d}",
                    "code": code,
                    "name": "테스트",
                    "market": market,
                    "open": price - 0.4,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price,
                    "volume": 1_200_000,
                    "trade_value": 5_000_000_000,
                }
            )
        return rows

    async def latest_index_daily(self, market, as_of=None):
        return {"main_index": {"name": "코스피", "change_rate": 0.8}}


@pytest.mark.asyncio
async def test_holding_context_calculates_return_and_checks():
    result = await StrategyAnalysisService(FakeKrx()).analyze(
        "005930",
        "KOSPI",
        position_mode="HOLDING",
        average_price=120.0,
        quantity=10,
    )

    position = result["position_context"]
    assert position["mode"] == "HOLDING"
    assert position["average_price"] == 120.0
    assert position["quantity"] == 10
    assert position["return_pct"] is not None
    assert position["unrealized_pnl"] is not None
    assert len(position["checks"]) >= 3
    assert all("status" in item for item in position["checks"])


@pytest.mark.asyncio
async def test_holding_requires_average_price():
    with pytest.raises(ValueError, match="평균 매수가"):
        await StrategyAnalysisService(FakeKrx()).analyze(
            "005930",
            "KOSPI",
            position_mode="HOLDING",
        )


@pytest.mark.asyncio
async def test_strategy_payload_contains_automatic_checks():
    result = await StrategyAnalysisService(FakeKrx()).analyze("005930", "KOSPI")
    regular = next(item for item in result["strategies"] if item["strategy"] != "no_trade")
    assert "auto_checks" in regular
    assert len(regular["auto_checks"]) >= 4
    statuses = {item["status"] for item in regular["auto_checks"]}
    assert statuses <= {"PASS", "WARN", "FAIL", "UNKNOWN"}
