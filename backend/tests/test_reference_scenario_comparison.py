import pytest

from app.market.technical import TechnicalAnalyzer
from app.strategy.service import StrategyAnalysisService


def make_rows(count: int = 60):
    rows = []
    price = 100.0
    for i in range(count):
        price += 0.4
        rows.append({
            "date": f"2026{i//28+1:02d}{i%28+1:02d}",
            "open": price - 0.5,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "volume": 1_000_000 + i * 5000,
            "trade_value": 3_000_000_000,
        })
    return rows


def test_reference_price_preview_does_not_mutate_history():
    rows = make_rows()
    before = rows[-1]["close"]
    analyzer = TechnicalAnalyzer()
    base = analyzer.analyze(rows)
    preview = analyzer.preview_with_reference_price(rows, 150.0, base)

    assert rows[-1]["close"] == before
    assert preview["estimated"]["ma20"] is not None
    assert preview["estimated"]["rsi14"] is not None
    assert preview["estimated"]["atr_pct"] is None
    assert preview["estimated"]["volume_ratio_20"] is None


def test_reference_ohlcv_can_estimate_atr_and_volume():
    rows = make_rows()
    analyzer = TechnicalAnalyzer()
    base = analyzer.analyze(rows)
    preview = analyzer.preview_with_reference_price(
        rows,
        130.0,
        base,
        reference_high=132.0,
        reference_low=127.0,
        reference_volume=2_500_000,
    )

    assert preview["input_mode"] == "PRICE_OHLCV"
    assert preview["estimated"]["atr_pct"] is not None
    assert preview["estimated"]["volume_ratio_20"] is not None


class FakeKrx:
    async def stock_history(self, market, code, as_of=None, points=60, lookback_days=120):
        return make_rows(60)

    async def latest_index_daily(self, market, as_of=None):
        return {"main_index": {"name": "코스피", "change_rate": 1.2}}


@pytest.mark.asyncio
async def test_service_returns_eod_and_reference_layers():
    service = StrategyAnalysisService(FakeKrx())
    result = await service.analyze("005930", "KOSPI", reference_price=150.0)

    assert result["analysis_layers"]["confirmed_eod"]["immutable"] is True
    assert result["analysis_layers"]["current_reference"]["temporary"] is True
    assert result["reference_strategies"] is not None
    assert result["strategy_comparison"]
    assert result["analysis_layers"]["confirmed_eod"]["price"] != result["analysis_layers"]["current_reference"]["price"]
