from app.market.service import MarketDataService


def test_market_regime_detects_broad_advance():
    label, note = MarketDataService._market_regime(1.2, 0.9, 0.66)
    assert label == "강한 상승"
    assert "상승" in note


def test_breadth_counts_rows():
    rows = [
        {"change_rate": 1.0},
        {"change_rate": -0.4},
        {"change_rate": 0.0},
        {"change_rate": None},
    ]
    result = MarketDataService._breadth(rows)
    assert result["total"] == 3
    assert result["up"] == 1
    assert result["down"] == 1
    assert result["flat"] == 1


def test_top_turnover_is_sorted_descending():
    rows = [
        {"code": "A", "close": 1, "trade_value": 100},
        {"code": "B", "close": 1, "trade_value": 300},
        {"code": "C", "close": 1, "trade_value": 200},
    ]
    result = MarketDataService._top_turnover(rows, 2)
    assert [row["code"] for row in result] == ["B", "C"]
