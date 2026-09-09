import pytest

from app.market.relative_strength import RelativeStrengthAnalyzer
from app.strategy.service import StrategyAnalysisService


def _rows(values: list[float], *, volume: int = 1_000_000) -> list[dict]:
    rows = []
    for index, close in enumerate(values):
        rows.append({
            "date": f"2026{index + 1:04d}",
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
            "trade_value": 5_000_000_000,
        })
    return rows


def test_relative_strength_calculates_5_20_60_day_excess_returns() -> None:
    analyzer = RelativeStrengthAnalyzer()
    market_values = [100 + index * 0.1 for index in range(61)]
    stock_values = [100 + index * 1.0 for index in range(61)]

    result = analyzer.analyze(
        _rows(stock_values),
        _rows(market_values),
        market="KOSPI",
        benchmark_name="코스피",
    )

    assert result["available"] is True
    assert result["primary_period"] == 20
    assert result["primary_excess_pct"] > 0
    periods = {row["days"]: row for row in result["periods"]}
    assert periods[5]["available"] is True
    assert periods[20]["available"] is True
    assert periods[60]["available"] is True
    assert periods[60]["stock_return_pct"] > periods[60]["market_return_pct"]


def test_relative_strength_uses_only_matching_dates() -> None:
    analyzer = RelativeStrengthAnalyzer()
    stock = _rows([100 + index for index in range(25)])
    market = _rows([100 + index * 0.2 for index in range(25)])
    market = market[3:]  # remove the first three benchmark dates

    result = analyzer.analyze(stock, market, market="KOSPI", benchmark_name="코스피")

    assert result["aligned_points"] == 22
    assert result["primary_period"] == 20
    assert result["periods"][2]["available"] is False  # 60-day window


class FakeKrxRelative:
    async def stock_history(self, market, code, as_of=None, points=60, lookback_days=120, concurrency=5):
        values = [100 + index * 1.2 for index in range(61)]
        rows = _rows(values, volume=1_500_000)
        for row in rows:
            row["code"] = code
            row["name"] = "테스트"
            row["market"] = market
        return rows[-points:]

    async def latest_index_daily(self, market, as_of=None, lookback_days=14):
        return {
            "main_index": {"name": "코스피", "change_rate": 0.8},
            "date": "20260061",
            "count": 1,
        }

    async def index_history(self, market, as_of=None, points=61, lookback_days=120, concurrency=5):
        return _rows([100 + index * 0.1 for index in range(61)])[-points:]


@pytest.mark.asyncio
async def test_strategy_service_wires_market_relative_strength_into_strategy_input() -> None:
    result = await StrategyAnalysisService(FakeKrxRelative()).analyze("005930", "KOSPI")

    relative = result["relative_strength"]
    assert relative["available"] is True
    assert relative["primary_excess_pct"] > 0
    assert len(relative["strategy_effects"]) == 4

    trend = next(item for item in result["strategies"] if item["strategy"] == "trend_following")
    assert "시장 대비 상대강도 양호" in " ".join(trend["reasons"])
    auto = next(check for check in trend["auto_checks"] if check["key"] == "relative_strength_market")
    assert auto["status"] in {"PASS", "WARN"}
