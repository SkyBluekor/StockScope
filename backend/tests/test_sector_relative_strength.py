from app.market.sector_relative_strength import SectorRelativeStrengthAnalyzer


def _period_rows(count=61, stock_start=100.0, stock_step=1.0, sector_start=100.0, sector_step=0.6):
    stock = []
    sector = []
    for i in range(count):
        day = f"2026{i // 28 + 1:02d}{i % 28 + 1:02d}"
        stock.append({"date": day, "close": stock_start + i * stock_step})
        sector.append({"date": day, "close": sector_start + i * sector_step})
    return stock, sector


def test_industry_code_26_maps_to_electronics_and_matches_krx_index():
    analyzer = SectorRelativeStrengthAnalyzer()
    mapping = analyzer.map_industry_code("264")
    assert mapping["available"] is True
    assert mapping["sector_group"] == "전기·전자"

    matched = analyzer.match_index_row(
        [
            {"class": "KOSPI", "name": "코스피", "close": 7000.0},
            {"class": "KOSPI 업종지수", "name": "전기·전자", "close": 35100.0},
        ],
        mapping["aliases"],
    )
    assert matched is not None
    assert matched["name"] == "전기·전자"
    assert matched["match_confidence"] == "HIGH"


def test_combined_decision_detects_sector_laggard():
    result = SectorRelativeStrengthAnalyzer._combined_decision(
        market_excess=6.0,
        sector_excess=-3.0,
        sector_name="전기·전자",
        market_name="코스피",
        position_mode="NOT_HELD",
    )
    assert result["archetype"] == "SECTOR_LAGGARD"
    assert "더 강한 종목" in result["user_response"]["action"]
    assert "추격 돌파" in result["deprioritized_strategies"]


def test_combined_decision_detects_dual_leader():
    result = SectorRelativeStrengthAnalyzer._combined_decision(
        market_excess=5.0,
        sector_excess=3.0,
        sector_name="전기·전자",
        market_name="코스피",
        position_mode="HOLDING",
    )
    assert result["archetype"] == "DUAL_LEADER"
    assert result["user_response"]["perspective"] == "보유 관리"
    assert "돌파" in result["preferred_strategies"]


def test_sector_relative_analysis_returns_20d_excess_and_combined_result():
    stock, sector = _period_rows()
    analyzer = SectorRelativeStrengthAnalyzer()
    mapping = analyzer.map_industry_code("264")
    mapping["benchmark_name"] = "전기·전자"
    market_relative = {
        "primary_excess_pct": 4.0,
        "benchmark": {"name": "코스피"},
    }
    result = analyzer.analyze(
        stock,
        sector,
        market="KOSPI",
        industry_code="264",
        mapping=mapping,
        benchmark_name="전기·전자",
        market_relative=market_relative,
        position_mode="NOT_HELD",
    )
    assert result["available"] is True
    assert result["primary_period"] == 20
    assert result["primary_excess_pct"] is not None
    assert result["benchmark"]["name"] == "전기·전자"
    assert result["decision"]["archetype"] in {"DUAL_LEADER", "INDEPENDENT_LEADER", "SECTOR_DRIVEN"}
