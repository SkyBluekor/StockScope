from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_macro_event_reference_frontend_uses_s3_read_only_client():
    client = (
        ROOT / "frontend/src/services/macroEventReferenceApi.ts"
    ).read_text(encoding="utf-8")

    assert "MacroEventReferenceResponse" in client
    assert "fetchMacroEventReference" in client
    assert "/api/macro/event-reference" in client
    assert "market" in client
    assert "ticker" in client
    assert "end_date" in client
    assert "cutoff" in client
    assert "signal: options.signal" in client
    assert "/api/macro/market-stock-impact" not in client


def test_macro_event_reference_hook_freezes_cutoff_and_aborts_stale_requests():
    hook = (
        ROOT / "frontend/src/hooks/useMacroEventReference.ts"
    ).read_text(encoding="utf-8")

    assert "AbortController" in hook
    assert "generationRef" in hook
    assert "abortRef.current?.abort()" in hook
    assert "fetchMacroEventReference" in hook
    assert "new Date().toISOString()" in hook
    assert "^[0-9A-Z]{6}$" in hook
    assert "setReference(null)" in hook
    assert "setError(" in hook

    for forbidden in (
        "setStock(",
        "setStrategyAnalysis(",
        "setDashboardError(",
        "setStockContextError(",
        "setHoldings(",
    ):
        assert forbidden not in hook


def test_stock_analysis_replaces_market_impact_with_macro_event_reference():
    workspace = (
        ROOT / "frontend/src/components/StockAnalysisWorkspace.tsx"
    ).read_text(encoding="utf-8")

    assert "MacroEventReferenceInline" in workspace
    assert "MarketStockImpactInline" not in workspace
    assert "market={stock.market}" in workspace
    assert "ticker={stock.code}" in workspace
    assert "endDate={stock.data_date}" in workspace
    assert "new Date(" not in workspace[
        workspace.index("<MacroEventReferenceInline"):
        workspace.index("<StockTrackingActions")
    ]


def test_macro_event_reference_ui_is_compact_and_non_predictive():
    panel = (
        ROOT / "frontend/src/components/MacroEventReferenceInline.tsx"
    ).read_text(encoding="utf-8")

    assert "시장 움직임과 확인된 근거" in panel
    assert "시장 변동" in panel
    assert "종목 변동" in panel
    assert "시장 대비 차이" in panel
    assert '"%"' in panel
    assert '"%p"' in panel
    assert "이벤트 근거" in panel
    assert "제한된 이벤트 참고" in panel
    assert "조회 시점까지 확인된 이벤트 근거 없음" in panel
    assert "무결성을 확인하지 못한 이벤트 근거는 참고에서 제외했습니다." in panel
    assert "이벤트 근거 상태를 현재 확인하지 못했습니다." in panel
    assert "동일한 두 확정 거래일 데이터가 부족해" in panel
    assert "과거 업종 소속의 시점 근거가 확보되지 않아" in panel
    assert "방향 예측이나" in panel
    assert "매수·매도 신호로 사용하지 않습니다." in panel

    for forbidden in (
        "composition_id",
        "composition_hash",
        "contract_version",
        "identity_policy",
        "claim_scope",
        "production_decision_approved",
        "strategy_input_approved",
        "scanner_input_approved",
        "risk_gate_input_approved",
        "holdings_plan_input_approved",
        "projection_mode",
        "product_scope",
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
        "호재",
        "악재",
    ):
        assert forbidden not in panel


def test_macro_event_reference_ui_keeps_neutral_editorial_style():
    css = (
        ROOT / "frontend/src/stock-analysis.css"
    ).read_text(encoding="utf-8")
    start = css.index(".macro-event-reference-inline")
    section = css[start:start + 5000]

    assert ".macro-event-reference-values" in section
    assert ".macro-event-reference-event" in section
    assert "font-variant-numeric: tabular-nums" in section
    assert "border-top: 1px solid var(--border-default)" in section
    assert "linear-gradient" not in section
    assert "box-shadow" not in section
    assert "var(--status-positive)" not in section
    assert "var(--status-negative)" not in section


def test_old_market_impact_frontend_files_are_removed():
    old_paths = (
        ROOT / "frontend/src/services/marketImpactApi.ts",
        ROOT / "frontend/src/hooks/useMarketStockImpact.ts",
        ROOT / "frontend/src/components/MarketStockImpactInline.tsx",
    )

    assert all(not path.exists() for path in old_paths)


def test_s4_keeps_news_event_detail_and_does_not_add_app_level_state():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    news = (
        ROOT / "frontend/src/components/StockNewsPanel.tsx"
    ).read_text(encoding="utf-8")
    backend_api = (
        ROOT / "backend/app/api/macro.py"
    ).read_text(encoding="utf-8")

    assert "MacroEventReferenceInline" not in app
    assert "macroEventReference" not in app
    assert "fetchStockEventEvidence" in news
    assert "검증된 이벤트 근거" in news
    assert "NEXT-6D-S4" not in backend_api
