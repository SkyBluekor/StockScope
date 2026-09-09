import pytest

from app.strategy.service import StrategyAnalysisService


class FakeDart:
    async def company_by_stock_code(self, stock_code):
        return {"stock_code": stock_code, "industry_code": "264"}


class FakeKrx:
    async def stock_history(self, market, code, as_of=None, points=61, lookback_days=120, concurrency=5):
        rows = []
        for i in range(70):
            close = 100 + i * 1.0
            rows.append({
                "date": f"2026{i // 28 + 1:02d}{i % 28 + 1:02d}",
                "code": code,
                "name": "테스트",
                "market": market,
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 2_000_000,
                "trade_value": 2_000_000_000,
            })
        return rows[-points:]

    async def latest_index_daily(self, market, as_of=None, lookback_days=14):
        return {
            "date": "20260314",
            "rows": [
                {"date": "20260314", "class": "KOSPI", "name": "코스피", "close": 200.0, "change_rate": 0.5},
                {"date": "20260314", "class": "KOSPI 업종지수", "name": "전기·전자", "close": 150.0, "change_rate": 0.7},
            ],
            "main_index": {"date": "20260314", "name": "코스피", "close": 200.0, "change_rate": 0.5},
        }

    async def index_history(self, market, as_of=None, points=61, lookback_days=120, concurrency=5):
        rows = []
        for i in range(70):
            rows.append({"date": f"2026{i // 28 + 1:02d}{i % 28 + 1:02d}", "name": "코스피", "close": 100 + i * 0.5})
        return rows[-points:]

    async def index_alias_history(self, market, aliases, as_of=None, points=61, lookback_days=140, concurrency=5):
        rows = []
        for i in range(70):
            rows.append({"date": f"2026{i // 28 + 1:02d}{i % 28 + 1:02d}", "name": "전기·전자", "close": 100 + i * 0.3})
        return rows[-points:]


@pytest.mark.asyncio
async def test_strategy_analysis_includes_sector_relative_strength():
    service = StrategyAnalysisService(FakeKrx(), FakeDart())
    service.event = None
    result = await service.analyze("005930", "KOSPI")

    sector = result["sector_relative_strength"]
    assert sector["available"] is True
    assert sector["benchmark"]["name"] == "전기·전자"
    assert sector["primary_excess_pct"] is not None
    assert sector["decision"]["archetype"] in {"DUAL_LEADER", "INDEPENDENT_LEADER", "SECTOR_DRIVEN"}

    breakout = next(item for item in result["strategies"] if item["strategy"] == "breakout")
    assert any(check["key"] == "relative_strength_sector" for check in breakout["auto_checks"])
