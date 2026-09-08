from app.market.technical import TechnicalAnalyzer


def _rows(count: int = 30):
    rows = []
    price = 100.0
    for index in range(count):
        price += 1.0
        rows.append(
            {
                "date": f"202608{index + 1:02d}",
                "open": price - 0.5,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 1_000_000,
                "trade_value": 5_000_000_000,
            }
        )
    return rows


def test_reference_price_preview_does_not_mutate_history():
    rows = _rows()
    original_last = rows[-1]["close"]
    analyzer = TechnicalAnalyzer()
    base = analyzer.analyze(rows)

    preview = analyzer.preview_with_reference_price(rows, 150.0, base)

    assert rows[-1]["close"] == original_last
    assert preview["source"] == "USER_INPUT"
    assert preview["confirmed_close"] == original_last
    assert preview["reference_price"] == 150.0
    assert preview["estimated"]["ma20"] is not None
    assert preview["estimated"]["rsi14"] is not None


def test_large_reference_price_gap_is_extreme_move():
    rows = _rows()
    analyzer = TechnicalAnalyzer()
    base = analyzer.analyze(rows)

    preview = analyzer.preview_with_reference_price(rows, 200.0, base)

    assert preview["status"] == "EXTREME_MOVE"
    assert preview["is_stale"] is True
    assert preview["is_extreme_move"] is True
