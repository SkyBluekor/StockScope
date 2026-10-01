from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_market_impact_frontend_uses_dedicated_read_only_client():
    client = (
        ROOT / "frontend/src/services/marketImpactApi.ts"
    ).read_text(encoding="utf-8")

    assert "MarketStockImpactResponse" in client
    assert "fetchMarketStockImpact" in client
    assert "/api/macro/market-stock-impact" in client
    assert 'query.set("cutoff"' not in client
    assert "end_date" in client
    assert "signal: options.signal" in client


def test_market_impact_hook_is_independent_and_aborts_stale_requests():
    hook = (
        ROOT / "frontend/src/hooks/useMarketStockImpact.ts"
    ).read_text(encoding="utf-8")

    assert "AbortController" in hook
    assert "generationRef" in hook
    assert "abortRef.current?.abort()" in hook
    assert "fetchMarketStockImpact" in hook
    assert "setImpact(null)" in hook
    assert "setError(" in hook

    for forbidden in (
        "setStock(",
        "setStrategyAnalysis(",
        "setDashboardError(",
        "setStockContextError(",
    ):
        assert forbidden not in hook


def test_stock_analysis_uses_confirmed_stock_data_date_for_impact():
    workspace = (
        ROOT / "frontend/src/components/StockAnalysisWorkspace.tsx"
    ).read_text(encoding="utf-8")

    assert "MarketStockImpactInline" in workspace
    assert "market={stock.market}" in workspace
    assert "ticker={stock.code}" in workspace
    assert "endDate={stock.data_date}" in workspace
    assert "new Date(" not in workspace[
        workspace.index("<MarketStockImpactInline"):
        workspace.index("<StockTrackingActions")
    ]


def test_market_impact_ui_is_descriptive_not_a_signal():
    panel = (
        ROOT / "frontend/src/components/MarketStockImpactInline.tsx"
    ).read_text(encoding="utf-8")

    assert "시장 대비 최근 움직임" in panel
    assert "시장 변동" in panel
    assert "종목 변동" in panel
    assert "시장 대비 차이" in panel
    assert '"%"' in panel
    assert '"%p"' in panel
    assert "같은 두 확정 거래일의 단순 수익률 차이입니다." in panel
    assert "원인 분석이나" in panel
    assert "매수·매도 판단을 의미하지 않습니다." in panel
    assert "동일한 두 확정 거래일 데이터가 부족해" in panel
    assert "시장 대비 비교 데이터가 아직 준비되지 않았습니다." in panel
    assert "과거 업종 소속의 시점 근거가 확보되지 않아" in panel

    for forbidden in (
        "context_id",
        "context_hash",
        "impact_hash",
        "common_dates_hash",
        "unlock_requirements",
        "AUTHORIZED_KRX_SOURCE",
        "KNOWN_AT_PROVEN",
        "S2_PIT_COMPATIBLE",
        "STRONG",
        "WEAK",
        "BUY",
        "SELL",
        "SAFE",
        "매수 우위",
        "시장보다 강",
        "방어력",
        "금리 수혜",
    ):
        assert forbidden not in panel


def test_market_impact_ui_keeps_neutral_editorial_style():
    css = (
        ROOT / "frontend/src/stock-analysis.css"
    ).read_text(encoding="utf-8")
    start = css.index(".market-stock-impact-inline")
    section = css[start:start + 4200]

    assert ".market-stock-impact-values" in section
    assert "font-variant-numeric: tabular-nums" in section
    assert "border-top: 1px solid var(--border-default)" in section
    assert "linear-gradient" not in section
    assert "box-shadow" not in section
    assert "var(--status-positive)" not in section
    assert "var(--status-negative)" not in section


def test_market_impact_ui_does_not_add_app_level_state_or_backend_product_logic():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    backend_api = (ROOT / "backend/app/api/macro.py").read_text(encoding="utf-8")

    assert "marketImpact" not in app
    assert "MarketStockImpactInline" not in app
    assert "NEXT-6C-S3.3" not in backend_api
