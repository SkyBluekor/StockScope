from app.market.technical import TechnicalAnalyzer


def make_rows(count: int = 30):
    rows = []
    price = 100.0
    for i in range(count):
        price += 1.0
        rows.append(
            {
                "date": f"202601{i+1:02d}",
                "open": price - 0.5,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 1_000_000 + i * 10_000,
                "trade_value": 2_000_000_000,
            }
        )
    return rows


def test_technical_analyzer_computes_core_indicators():
    result = TechnicalAnalyzer().analyze(make_rows())

    assert result["data_points"] == 30
    assert result["ma5"] is not None
    assert result["ma20"] is not None
    assert result["rsi14"] is not None
    assert result["atr_pct"] is not None
    assert result["volume_ratio_20"] is not None
    assert result["higher_high"] is True
    assert result["higher_low"] is True


def test_technical_analyzer_requires_20_points():
    try:
        TechnicalAnalyzer().analyze(make_rows(10))
    except ValueError as exc:
        assert "최소 20거래일" in str(exc)
    else:
        raise AssertionError("20일 미만 데이터는 거부되어야 합니다.")
