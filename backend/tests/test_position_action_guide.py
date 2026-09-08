import pytest

from app.strategy.service import StrategyAnalysisService


class FakeKrx:
    async def stock_history(self, market, code, as_of=None, points=60, lookback_days=120):
        rows = []
        price = 100.0
        for i in range(60):
            price += 0.8
            rows.append({
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
            })
        return rows

    async def latest_index_daily(self, market, as_of=None):
        return {"main_index": {"name": "코스피", "change_rate": 0.8}}


@pytest.mark.asyncio
async def test_holding_payload_has_action_guide():
    result = await StrategyAnalysisService(FakeKrx()).analyze(
        "005930",
        "KOSPI",
        position_mode="HOLDING",
        average_price=180.0,
        quantity=10,
    )

    guide = result["position_action_guide"]
    assert guide["available"] is True
    assert guide["primary_code"] in {"HOLD_OBSERVE", "REDUCE_RISK_REVIEW", "EXIT_REVIEW"}
    assert guide["hold"]["label"]
    assert guide["add_position"]["label"]
    assert guide["reduce_position"]["label"]
    assert isinstance(guide["triggers"], list)


@pytest.mark.asyncio
async def test_not_held_action_guide_is_not_applicable():
    result = await StrategyAnalysisService(FakeKrx()).analyze("005930", "KOSPI")
    assert result["position_action_guide"]["available"] is False
