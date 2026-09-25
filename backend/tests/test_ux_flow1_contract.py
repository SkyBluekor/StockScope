from pathlib import Path


def test_ux_flow1_scanner_routes_to_stock_analysis() -> None:
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    scanner_anchor = app.index("<ScannerPanel")
    scanner_block = app[scanner_anchor : scanner_anchor + 800]
    assert 'chooseStock(item, { loadContext: true, origin: "scanner" })' in scanner_block
    assert 'navigateApp("analysis")' in scanner_block
    assert 'navigateApp("backtest")' not in scanner_block


def test_ux_flow1_analysis_has_tracking_actions_without_strategy_coupling() -> None:
    workspace = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")
    actions = Path("frontend/src/components/StockTrackingActions.tsx").read_text(encoding="utf-8")

    tracking_position = workspace.index("<StockTrackingActions")
    verdict_position = workspace.index("strategyAnalysis && summary")
    assert tracking_position < verdict_position

    assert "listHoldingStocks" in actions
    assert "addWatchStock" in actions
    assert "registerHeldStock" in actions
    assert "관심종목에 추가" in actions
    assert "보유종목으로 등록" in actions
    assert "내 종목 관리" in actions
    assert "Strategy·Scanner·Risk 계산을 변경하지 않습니다." in actions
    assert "fetchStrategyAnalysis" not in actions
    assert "Scanner" not in actions.split("Strategy·Scanner·Risk 계산을 변경하지 않습니다.")[0]


def test_ux_flow1_holding_registration_preserves_opening_balance_contract() -> None:
    actions = Path("frontend/src/components/StockTrackingActions.tsx").read_text(encoding="utf-8")
    holdings_api = Path("frontend/src/services/holdingsApi.ts").read_text(encoding="utf-8")
    holdings_backend = Path("backend/app/api/holdings.py").read_text(encoding="utf-8")

    assert "registerHeldStock" in actions
    assert '"/api/holdings/held"' in holdings_api
    assert "OPENING_BALANCE" in holdings_backend
    assert "신규 매수 주문이나 BUY 이벤트를 생성하는 기능이 아닙니다." in actions


def test_ux_flow1_analysis_and_holdings_are_bidirectionally_linked() -> None:
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")
    workspace = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")

    assert "stockscope-holdings-target" in app
    assert "stockscope-holdings-target" in holdings
    assert "navigationTargetId" in holdings
    assert "종목 분석 보기" in holdings
    assert "onAnalyzeStock={openAnalysisFromHoldings}" in app
    assert "onOpenHoldings={openHoldingsForStock}" in app
    assert "후보 목록으로 돌아가기" in workspace


def test_ux_flow1_does_not_add_backend_or_database_surface() -> None:
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    actions = Path("frontend/src/components/StockTrackingActions.tsx").read_text(encoding="utf-8")

    assert "stockscope-holdings-target" in app
    assert "VITE_" not in actions
    assert "/api/holdings/watch" not in actions
    assert "/api/holdings/held" not in actions
