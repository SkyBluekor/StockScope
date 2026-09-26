from pathlib import Path


def test_ux_redesign1_header_uses_unified_data_status() -> None:
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    panel = Path("frontend/src/components/DataStatusPanel.tsx").read_text(encoding="utf-8")

    header_anchor = app.index('<div className="header-status">')
    header_end = app.index("</header>", header_anchor)
    header_block = app[header_anchor:header_end]
    assert "data-status-trigger" in header_block
    assert "dataSummary.label" in header_block
    assert ">KRX</span>" not in header_block
    assert ">DART</span>" not in header_block

    for provider in ("KRX", "DART", "NAVER NEWS", "KIS"):
        assert provider in panel
    assert "last_success" not in panel
    assert "lastSuccess" not in panel
    assert "사용 안 함" in panel


def test_ux_redesign1_scanner_data_task_is_resumable_and_visible() -> None:
    scanner = Path("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    task = Path("frontend/src/services/dataTask.ts").read_text(encoding="utf-8")

    assert "writeActiveDataTask" in scanner
    assert "readActiveDataTask" in scanner
    assert "clearActiveDataTask" in scanner
    assert "scrollIntoView" in scanner
    assert "시장 데이터 준비 진행 상황" in scanner
    assert "stockscope-active-data-task" in task
    assert "sessionStorage" in task
    assert "3년 검증 데이터 준비" in scanner
    assert "evidencePreparationAvailable" in scanner
    assert "evidence.preparation_available" in scanner
    assert "onPrepareEvidence={() => void prepareCandidateEvidence(selectedCandidate)}" in scanner


def test_ux_redesign1_global_task_poll_uses_existing_job_api() -> None:
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    api = Path("frontend/src/services/api.ts").read_text(encoding="utf-8")
    backend = Path("backend/app/api/backtest.py").read_text(encoding="utf-8")

    assert "fetchBacktestJob(activeDataTask.jobId)" in app
    assert "/api/backtest/jobs/" in api
    assert '@router.get("/jobs/{job_id}")' in backend
    assert "데이터 작업 중" in app
    assert "진행 보기" in app


def test_ux_redesign1_holding_history_recovery_exposes_real_counts() -> None:
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")
    holdings_api = Path("frontend/src/services/holdingsApi.ts").read_text(encoding="utf-8")

    assert "분석에 필요한 과거 가격 데이터가 부족합니다." in holdings
    assert "확보 {historyRecovery.currentRows}거래일 · 필요 {historyRecovery.requiredRows}거래일" in holdings
    assert "데이터 준비 후 분석" in holdings
    assert "current_rows" in holdings_api
    assert "required_rows" in holdings_api


def test_ux_redesign1_virtual_analysis_is_separate_from_ledger() -> None:
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "가상 분석 조건" in app
    assert "실제 보유 수량·평균단가와 원장을 변경하지 않습니다." in app


def test_ux_redesign1_does_not_change_protected_calculation_surfaces() -> None:
    panel = Path("frontend/src/components/DataStatusPanel.tsx").read_text(encoding="utf-8")
    task = Path("frontend/src/services/dataTask.ts").read_text(encoding="utf-8")

    for source in (panel, task):
        assert "fetchStrategyAnalysis" not in source
        assert "createScannerJob" not in source
        assert "registerHeldStock" not in source
        assert "applyHoldingManagementPlan" not in source



def test_ux_redesign1_provider_status_uses_real_kis_configuration() -> None:
    source = Path("backend/app/api/data_sources.py").read_text(encoding="utf-8")

    assert "settings.kis_app_key" in source
    assert "settings.kis_app_secret" in source
    assert "settings.kis_account_no" in source
    assert "settings.kis_account_product_code" in source
    assert '"enabled": False' not in source
    assert "실계좌 잔고 · 현재가 · 실시간 시세" in source


def test_ux_redesign1c_three_year_evidence_prepare_recalculates_scanner_result() -> None:
    scanner_ui = Path("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    api_client = Path("frontend/src/services/api.ts").read_text(encoding="utf-8")
    api_backend = Path("backend/app/api/backtest.py").read_text(encoding="utf-8")
    scanner_backend = Path("backend/app/backtest/scanner.py").read_text(encoding="utf-8")
    priority = Path("backend/app/backtest/candidate_priority.py").read_text(encoding="utf-8")

    assert "createScannerEvidenceJob" in api_client
    assert "/api/backtest/scanner/evidence/jobs" in api_client
    assert '@router.post("/scanner/evidence/jobs", status_code=202)' in api_backend
    assert "prepare_three_year_evidence_data" in scanner_backend
    assert "validation_start_for_years(end)" in scanner_backend
    assert "THREE_YEAR_WARMUP_DAYS" in scanner_backend
    assert "force_refresh=True" in api_backend
    assert "allow_large_sync=False" in api_backend

    assert "onPrepareEvidence={() => void prepareCandidateEvidence(selectedCandidate)}" in scanner_ui
    assert "onPrepareEvidence={() => void runScanner(true, true)}" not in scanner_ui
    assert "preferredCandidateKeyRef" in scanner_ui
    assert "<small>승률</small>" in scanner_ui
    assert "<small>기대수익</small>" in scanner_ui

    assert 'strengths.append("3년 과거 근거 양호")' in priority
    assert 'strengths.append("3년 과거 근거 보통")' in priority
    assert 'penalties.append("3년 과거 근거 약함")' in priority
    assert 'penalties.append("3년 과거 표본 부족")' in priority
    assert 'penalties.append("3년 유사 사례 없음")' in priority
    assert 'penalties.append("3년 검증 데이터 부족")' in priority


def test_ux_redesign1d_scanner_can_add_candidates_to_holdings_without_reanalysis() -> None:
    scanner = Path("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    assert "listHoldingStocks" in scanner
    assert "addWatchStock" in scanner
    assert "registerHeldStock" in scanner
    assert "managedStockMap" in scanner
    assert "holdingsReady" in scanner
    assert 'className="scanner-compare-manage"' in scanner
    assert '"☆ 관심"' in scanner
    assert "★ 관심" in scanner
    assert '"+ 기존 보유"' in scanner
    assert "보유 중" in scanner
    assert "event.stopPropagation()" in scanner

    assert "openHoldingRegistration" in scanner
    assert 'type="datetime-local"' in scanner
    assert "candidate.current_price" in scanner
    assert "quantity <= 0" in scanner
    assert "averagePrice <= 0" in scanner

    assert "onOpenHoldings" in scanner
    assert "내 종목 관리" in scanner
    assert "onOpenHoldings={(target) => openHoldingsForStock(target)}" in app
    assert "stockscope-holdings-target" in app

    assert ".scanner-holding-dialog-backdrop" in styles
    assert ".scanner-selected-action-buttons" in styles

    # Holdings actions must not rerun or rewrite Scanner analysis.
    add_watch_block = scanner[scanner.index("async function addCandidateToWatch"):scanner.index("function openHoldingRegistration")]
    assert "runScanner(" not in add_watch_block
    held_block = scanner[scanner.index("async function submitHoldingRegistration"):scanner.index("function openCandidateInHoldings")]
    assert "runScanner(" not in held_block

    # The dedicated three-year evidence recovery remains connected.
    assert "onPrepareEvidence={() => void prepareCandidateEvidence(selectedCandidate)}" in scanner


def test_ux_redesign1e_news_context_connects_scanner_and_holdings_without_changing_analysis() -> None:
    news_panel = Path("frontend/src/components/StockNewsPanel.tsx").read_text(encoding="utf-8")
    scanner = Path("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")
    analysis = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")
    api = Path("frontend/src/services/api.ts").read_text(encoding="utf-8")
    styles = Path("frontend/src/stock-analysis.css").read_text(encoding="utf-8")

    assert 'variant?: "full" | "compact"' in news_panel
    assert 'variant = "full"' in news_panel
    assert "requestLimit = compact ? 5 : 10" in news_panel
    assert "collapsedLimit = compact ? 3 : 5" in news_panel
    assert "expandedLimit = compact ? 5 : 10" in news_panel
    assert "AbortController" in news_panel
    assert "requestIdRef" in news_panel

    assert 'variant="compact"' in scanner
    assert "code={candidate.code}" in scanner
    assert "market={candidate.market}" in scanner
    assert 'variant="compact"' in holdings
    assert "code={detail.ticker}" in holdings
    assert 'market={detail.market === "KOSDAQ" ? "KOSDAQ" : "KOSPI"}' in holdings

    # Existing stock analysis keeps the default full-mode panel.
    assert "<StockNewsPanel" in analysis
    assert 'variant="compact"' not in analysis

    # Reuse the existing news API; no Scanner rerun is connected to news display.
    assert "fetchStockNews" in api
    assert "/news?" in api
    candidate_detail = scanner[scanner.index("function CandidateDetail"):scanner.index("export default function ScannerPanel")]
    assert "StockNewsPanel" in candidate_detail
    assert "runScanner(" not in candidate_detail

    assert ".stock-news-panel.compact" in styles
    assert "뉴스 검색 결과는 참고 정보이며 StockScope의 Strategy·Scanner·Ranking·Risk 계산을 변경하지 않습니다." in news_panel


def test_ux_redesign1f_watch_and_held_views_are_semantically_separated() -> None:
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/holdings.css").read_text(encoding="utf-8")

    # The list and detail perspective follow the active tab instead of reusing one layout.
    assert 'detailPerspective: "watch" | "held"' in holdings
    assert 'stockFilter === "watch"' in holdings
    assert 'stockFilter === "held"' in holdings
    assert 'perspective-${stockFilter}' in holdings
    assert "<th>현재 판단</th>" in holdings
    assert "<th>보유 수량</th>" in holdings
    assert "<th>평균단가</th>" in holdings

    # Interest view emphasizes observation and never renders the position/P&L block by default.
    assert 'detailPerspective === "watch"' in holdings
    assert 'className="holdings-watch-overview"' in holdings
    assert "현재 판단" in holdings
    assert "보유 관리 보기" in holdings
    assert "관심 해제" in holdings

    # Held view is anchored to the actual ledger and applied management state.
    assert 'detailPerspective === "held"' in holdings
    assert 'className="holdings-position-management"' in holdings
    assert 'aria-label="보유 손익"' in holdings
    assert 'aria-label="보유분 관리 기준"' in holdings
    assert "<strong>보유분 관리 기준</strong>" in holdings
    assert "적용 기준일" in holdings
    assert "최신 분석 제안" in holdings
    assert "현재 적용 중인 보유분 관리 기준이 없습니다." in holdings

    # New-entry analysis remains explicitly separate from held-position management.
    assert "추가 매수·신규 진입 관점" in holdings
    assert "기존 보유분의 매도 판단이나 적용 중인 관리 기준을 변경하지 않습니다." in holdings
    assert "실제 적용 중인 보유분 관리 기준" in holdings

    # Filter changes cannot leave a hidden stock selected in the detail pane.
    assert "visibleStocks.some((stock) => stock.stock_id === selectedStockId)" in holdings
    assert "setSelectedStockId(visibleStocks[0].stock_id)" in holdings

    # Interest removal remains a watch-state mutation only; ledger mutation APIs are separate.
    change_watch = holdings[holdings.index("async function changeWatch"):holdings.index("function requestListWatchChange")]
    assert "setWatchEnabled" in change_watch
    assert "recordManualSell" not in change_watch
    assert "recordManualCorrection" not in change_watch

    # UX-REDESIGN.1E news context is retained in the same workspace.
    assert "<StockNewsPanel" in holdings
    assert 'variant="compact"' in holdings

    assert ".holdings-watch-overview" in styles
    assert ".holdings-entry-guardrail" in styles
    assert ".holdings-management-proposal-kicker" in styles


def test_ux_redesign1g_past_performance_reuses_exact_session_result_without_reanalysis() -> None:
    backtest = Path("frontend/src/components/BacktestPanel.tsx").read_text(encoding="utf-8")
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    # Past performance is explicitly optional and can return to stock analysis.
    assert "선택적 과거 검증" in backtest
    assert "이 검증을 실행하지 않아도 종목 분석과 관심·보유 관리는 사용할 수 있습니다." in backtest
    assert "onBackToAnalysis?: () => void" in backtest
    assert 'onBackToAnalysis={() => navigateApp("analysis")}' in app

    # Completed results are keyed by the exact user-visible calculation config.
    assert "type BacktestCacheConfig" in backtest
    assert "backtestResultSignature" in backtest
    assert "config.startDate" in backtest
    assert "config.endDate" in backtest
    assert "config.initialCapital" in backtest
    assert "config.maxHoldingDays" in backtest
    assert "config.roundTripCostPct" in backtest
    assert "window.sessionStorage.setItem(resultStorageKey(entry.signature)" in backtest
    assert "readBacktestCache(currentSignature)" in backtest

    # Revisiting the screen may restore a completed cache result, but never starts a POST job.
    restore_effect_start = backtest.index("const restored = readLatestBacktestCache(market, code)")
    restore_effect = backtest[restore_effect_start:backtest.index("const selectedHolding", restore_effect_start)]
    assert "applyConfigToForm(restored.config)" in restore_effect
    assert 'setResultRestoreMode("auto-cache")' in restore_effect
    assert 'setView("result")' in restore_effect
    assert "createMultiStrategyBacktestJob" not in restore_effect
    assert "기존 결과 보기" not in backtest
    assert "재방문만으로 자동 계산하지 않습니다." in backtest

    # Starting a new calculation no longer clears the completed result.
    run_block = backtest[backtest.index("async function runBacktest"):backtest.index("async function runExitPolicyValidation")]
    assert "setResult(null)" not in run_block
    assert "const previousExact = readBacktestCache(runSignature)" in run_block
    assert "writeBacktestCache(entry)" in run_block
    assert "기존 완료 결과는 아래에 유지됩니다." in backtest
    assert "기존 완료 결과는 그대로 유지됩니다." in backtest

    # Requested period and actual prepared data window remain distinct.
    assert "요청한 검증 기간" in backtest
    assert "실제 종목 데이터" in backtest
    assert "result.data_window?.stock_rows" in backtest
    assert "result.data_window?.index_rows" in backtest
    assert "요청한 기간 전체와 실제 확보된 종목 데이터 범위가 다릅니다." in backtest

    # Existing Scanner context and advanced Exit research are still retained.
    assert "종목 찾기에서 넘어온 현재 판단" in backtest
    assert "scannerContextMatchesDate" in backtest
    assert "고급 검증 · Exit 정책 연구" in backtest
    assert "createExitPolicyValidationJob" in backtest

    # No backend calculation contract is reimplemented in this UX layer.
    assert "createMultiStrategyBacktestJob" in backtest
    assert ".backtest-cache-panel" in styles
    assert ".backtest-result-context" in styles


def test_ux_redesign1h_news1_is_compact_and_does_not_impersonate_news2_analysis() -> None:
    panel = Path("frontend/src/components/StockNewsPanel.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/stock-analysis.css").read_text(encoding="utf-8")
    workspace = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")
    scanner = Path("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")

    # Existing NEWS.1 result-count contracts remain intact.
    assert 'variant = "full"' in panel
    assert "requestLimit = compact ? 5 : 10" in panel
    assert "collapsedLimit = compact ? 3 : 5" in panel
    assert "expandedLimit = compact ? 5 : 10" in panel

    # Company-name search results are described accurately, not as validated relevance.
    assert "이름으로 조회한 최근 네이버 뉴스 검색 결과입니다." in panel
    assert "와 직접 관련된 네이버 검색 결과" not in panel
    assert "현재 조회된 최근 뉴스가 없습니다." in panel

    # NEWS.2-style interpretation is explicitly not fabricated in NEWS.1.
    assert "현재 뉴스 목록은 기사 검색 결과이며 호재·악재 또는 주가 방향을 판정하지 않습니다." in panel
    assert "현재 이 화면에서는 제공하지 않습니다." in panel
    assert 'className="stock-news-scope-details"' in panel
    assert "{!compact && (" in panel
    assert "fetchStockNews" in panel
    assert "fetchNewsAnalysis" not in panel
    assert "newsImpact" not in panel

    # Articles stay editorial, concise, and leave the full article at the source.
    assert "stock-news-item-copy" in panel
    assert "원문 ↗" in panel
    assert 'target="_blank"' in panel
    assert 'rel="noopener noreferrer"' in panel
    assert ".stock-news-item p" in styles
    assert "-webkit-line-clamp: 2" in styles
    assert "grid-template-columns: minmax(0, 1fr) auto" in styles

    # Full news remains after company analysis and before investor-style analysis.
    rendered_news = workspace.index("<StockNewsPanel", workspace.index("stock-analysis-company-summary"))
    assert workspace.index("stock-analysis-company-summary") < rendered_news
    assert rendered_news < workspace.index("stock-analysis-style-section")

    # Scanner and Holdings keep the compact NEWS.1 mode from UX-REDESIGN.1E.
    assert 'variant="compact"' in scanner
    assert 'variant="compact"' in holdings

    # The existing protected calculation disclaimer remains visible.
    assert "Strategy·Scanner·Ranking·Risk 계산을 변경하지 않습니다." in panel


def test_ux_redesign1i_data_status_does_not_claim_unverified_connectivity() -> None:
    panel = Path("frontend/src/components/DataStatusPanel.tsx").read_text(encoding="utf-8")
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    news = Path("frontend/src/components/StockNewsPanel.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    # Configuration is not presented as proven provider availability or freshness.
    assert '"사용 가능"' not in panel
    assert "데이터 상태 정상" not in panel
    assert "기본 데이터 설정됨" in panel
    assert "설정됨 · 연결 확인 전" in panel
    assert "실제 제공처 연결 성공과 데이터 최신성은 이 상태만으로 판단하지 않습니다." in panel
    assert "last_success" not in panel
    assert "lastSuccess" not in panel

    # Core and optional capabilities explain user impact separately.
    assert "시장 데이터 설정 필요" in panel
    assert "일부 기능 설정 필요" in panel
    assert "기업·공시 정보만 제한됩니다. 가격과 전략 분석은 계속 사용할 수 있습니다." in panel
    assert "최근 뉴스만 제한됩니다. 종목 분석과 전략 계산에는 영향을 주지 않습니다." in panel
    assert "사용 안 함" in panel
    assert "직접 등록한 관심·보유 종목은 계속 사용할 수 있습니다." in panel

    # Provider names are kept as technical details instead of the primary status surface.
    assert '<details className="data-status-providers">' in panel
    assert "<summary>기술 정보 보기</summary>" in panel
    for provider in ("KRX", "DART", "NAVER NEWS", "KIS"):
        assert provider in panel

    # Refresh wording accurately describes a configuration/status re-read, not a live probe.
    assert "설정 상태 다시 확인" in panel
    assert "연결 테스트" not in panel

    # The global header consumes the exact same summary.
    assert "const dataSummary = dataStatusSummary(apiStatus, providers)" in app
    assert "dataSummary.label" in app

    # Existing resumable data-task status stays visible and accessible.
    assert 'aria-live="polite"' in panel
    assert "진행 보기" in panel
    assert "결과 보기" in panel
    assert "진행 정보 확인 중" in panel

    # A news-provider failure stays local to NEWS.1.
    assert "최근 뉴스만 불러오지 못했습니다." in news
    assert "종목 분석과 전략 계산 결과에는 영향을 주지 않습니다." in news

    assert ".data-status-capability-row small" in styles
    assert ".data-status-providers > summary" in styles


def test_ux_redesign1j1_historical_evidence_separates_readiness_sample_and_performance() -> None:
    scanner = Path("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    api = Path("frontend/src/services/api.ts").read_text(encoding="utf-8")
    evidence_backend = Path("backend/app/backtest/historical_evidence.py").read_text(encoding="utf-8")
    priority = Path("backend/app/backtest/candidate_priority.py").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    # The UI explicitly separates validation completion from the performance assessment.
    assert "최근 3년 검증 완료" in scanner
    assert "최근 3년 검증 미완료" in scanner
    assert "과거 성과 근거 양호" in scanner
    assert "과거 성과 근거 보통" in scanner
    assert "과거 성과 근거 약함" in scanner
    assert "거래 표본 부족" in scanner
    assert "동일 전략 거래 사례 없음" in scanner
    assert "3년 검증에 필요한 데이터로 계산을 완료했습니다." in scanner

    # Compact metrics show sample quality without duplicating expectancy.
    summary_start = scanner.index('className="scanner-evidence-compact-metrics"')
    summary_end = scanner.index("</div>", summary_start)
    compact_summary = scanner[summary_start:summary_end]
    assert "거래 표본" in compact_summary
    assert "최소 기준" in compact_summary
    assert "승률" in compact_summary
    assert "평균 순수익" in compact_summary
    assert "최대 낙폭" in compact_summary
    assert "기대수익" not in compact_summary
    assert "formatPct(evidence.win_rate_pct)" in compact_summary
    assert "<small>기대수익</small>" in scanner

    # Recovery is offered only when the backend says preparation can help.
    assert "preparation_available?: boolean" in api
    assert "unavailable_reason?" in api
    assert '"unavailable_reason": unavailable_reason' in evidence_backend
    assert '"preparation_available": preparation_available' in evidence_backend
    assert 'unavailable_reason="UNSUPPORTED_STRATEGY"' in evidence_backend
    assert "preparation_available=False" in evidence_backend
    assert "canPrepareEvidence &&" in scanner
    assert "evidence.preparation_available" in scanner

    # Existing evidence calculation and Scanner ranking semantics stay untouched.
    assert "evaluate_historical_evidence(" in evidence_backend
    assert 'strengths.append("3년 과거 근거 양호")' in priority
    assert 'strengths.append("3년 과거 근거 보통")' in priority
    assert 'penalties.append("3년 과거 근거 약함")' in priority
    assert 'penalties.append("3년 과거 표본 부족")' in priority
    assert 'penalties.append("3년 유사 사례 없음")' in priority

    assert ".scanner-evidence-status-line" in styles
    assert ".scanner-evidence-compact-metrics > span.sample" in styles


def test_ux_redesign1j2_preserves_ui_context_and_rejects_stale_async_results() -> None:
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    api = Path("frontend/src/services/api.ts").read_text(encoding="utf-8")
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")
    holdings_api = Path("frontend/src/services/holdingsApi.ts").read_text(encoding="utf-8")
    tracking = Path("frontend/src/components/TrackingWorkspace.tsx").read_text(encoding="utf-8")
    session = Path("frontend/src/services/uiSession.ts").read_text(encoding="utf-8")

    # Lightweight UI context is session-only and explicitly excludes analysis/ledger payloads.
    assert "stockscope-analysis-context-v1" in session
    assert "stockscope-holdings-context-v1" in session
    assert "stockscope-tracking-mode-v1" in session
    assert "readAnalysisSelectionContext" in session
    assert "writeAnalysisSelectionContext" in session
    assert "readHoldingsViewContext" in session
    assert "writeHoldingsViewContext" in session
    assert "readTrackingMode" in session
    assert "writeTrackingMode" in session
    assert "strategyAnalysis" not in session
    assert "HoldingPerformanceResponse" not in session

    # Selecting the same stock preserves the already-rendered analysis state.
    assert "const sameStock = selectedStockKeyRef.current === nextKey" in app
    assert "if (!sameStock) {" in app
    same_stock_start = app.index("if (!sameStock) {")
    same_stock_block = app[same_stock_start:app.index("setStockMessage", same_stock_start)]
    assert "setStrategyAnalysis(null)" in same_stock_block
    assert "setReferencePriceInput" in same_stock_block
    assert "writeAnalysisSelectionContext" in app

    # Search, stock context, and strategy analysis all have abort + latest-request guards.
    assert "stockSearchRequestIdRef" in app
    assert "stockContextRequestIdRef" in app
    assert "strategyRequestIdRef" in app
    assert "stockContextAbortRef" in app
    assert "strategyAbortRef" in app
    assert "selectedStockKeyRef.current !== requestKey" in app
    assert "selectedStockKeyRef.current !== requestedStockKey" in app
    assert "analysisInputSignatureRef.current !== requestInputSignature" in app
    assert "isAbortError(error)" in app
    assert "searchStocks(query, { signal: controller.signal })" in app
    assert "fetchStockContext(normalizedCode, market, { signal: controller.signal })" in app

    # Direct/revisited analysis restores identity and only auto-loads basic context.
    assert "initialAnalysisSelection" in app
    assert 'appPage !== "analysis"' in app
    assert "loadStockContextForSelection" in app
    auto_start = app.index('if (appPage !== "analysis"')
    auto_load = app[auto_start:app.index("const strategyName", auto_start)]
    assert "runStrategyAnalysis" not in auto_load
    assert "fetchStrategyAnalysis" not in auto_load

    # Read APIs accept AbortSignal without changing backend routes.
    assert "options: { signal?: AbortSignal } = {}" in api
    assert "{ signal: options.signal }" in api
    assert "/api/stocks/search?" in api
    assert "/strategy-analysis?" in api
    assert "/context?" in api

    # Holdings explicit navigation target wins over restored view state.
    assert "initialViewContext" in holdings
    assert 'navigationTarget ? "all"' in holdings
    keep_start = holdings.index("const keep = navigationTargetId")
    keep_block = holdings[keep_start:holdings.index("setSelectedStockId(keep)", keep_start)]
    assert "navigationTargetId" in keep_block
    assert "preferredId" in keep_block
    assert "selectedStockId" in keep_block

    # Holdings detail and add-stock search reject stale results.
    assert "detailRequestIdRef" in holdings
    assert "detailAbortRef" in holdings
    assert "selectedStockIdRef.current !== stockId" in holdings
    assert "getHoldingStock(stockId, { signal: controller.signal })" in holdings
    assert "getHoldingTimeline(stockId, 100, { signal: controller.signal })" in holdings
    assert "getHoldingPerformance(stockId, { signal: controller.signal })" in holdings
    assert "getHoldingManagement(stockId, { signal: controller.signal })" in holdings
    assert "addSearchRequestIdRef" in holdings
    assert "searchStocks(text, { signal: controller.signal })" in holdings

    for read_fn in ("getHoldingStock", "getHoldingTimeline", "getHoldingPerformance", "getHoldingManagement"):
        read_start = holdings_api.index(f"export function {read_fn}")
        read_end = holdings_api.find("\n}\n", read_start) + 3
        read_block = holdings_api[read_start:read_end]
        assert "signal?: AbortSignal" in read_block
        assert "signal: options.signal" in read_block

    # Tracking returns to the user's last sub-view but never starts validation automatically.
    assert "useState<TrackingMode>(readTrackingMode)" in tracking
    assert "writeTrackingMode(next)" in tracking
    assert "create" not in tracking.lower()


def test_ux_redesign1j3_backtest_auto_restores_completed_result_without_new_job() -> None:
    backtest = Path("frontend/src/components/BacktestPanel.tsx").read_text(encoding="utf-8")

    # Exact config remains the seven user-visible calculation inputs.
    signature_start = backtest.index("function backtestResultSignature")
    signature_end = backtest.index("function resultStorageKey", signature_start)
    signature = backtest[signature_start:signature_end]
    for field in (
        "config.market",
        "config.code",
        "config.startDate",
        "config.endDate",
        "config.initialCapital",
        "config.maxHoldingDays",
        "config.roundTripCostPct",
    ):
        assert field in signature

    # Entry/stock change restores the most recent completed config/result locally.
    restore_start = backtest.index("const restored = readLatestBacktestCache(market, code)")
    restore_end = backtest.index("const selectedHolding", restore_start)
    restore = backtest[restore_start:restore_end]
    assert "restored.config.market === market" in restore
    assert "restored.config.code.trim().toUpperCase() === code.trim().toUpperCase()" in restore
    assert "applyConfigToForm(restored.config)" in restore
    assert "setResult(restored.result)" in restore
    assert "setResultConfig(restored.config)" in restore
    assert "setResultCompletedAt(restored.completedAt)" in restore
    assert 'setResultRestoreMode("auto-cache")' in restore
    assert 'setView("result")' in restore
    assert "createMultiStrategyBacktestJob" not in restore

    # Viewing a completed result no longer needs an extra exact-cache button.
    assert ">기존 결과 보기<" not in backtest
    assert "같은 조건으로 다시 계산" in backtest
    assert "이전 결과 보기" in backtest
    assert "새 계산 없이 이번 세션의 저장된 완료 결과를 복원했습니다." in backtest
    assert "최신 결과" not in backtest
    assert "최신 데이터 여부를 뜻하지 않습니다." in backtest

    # User edits only rediscover cache metadata; they are not forced back to result view.
    cache_refresh_start = backtest.index("setExactCachedResult(readBacktestCache(currentSignature))")
    cache_refresh_end = backtest.index("function showCachedResult", cache_refresh_start)
    cache_refresh = backtest[cache_refresh_start:cache_refresh_end]
    assert 'setView("result")' not in cache_refresh
    assert "createMultiStrategyBacktestJob" not in cache_refresh

    # New runs remain explicit and replace the cache-source marker only after completion.
    run_start = backtest.index("async function runBacktest")
    run_end = backtest.index("async function runExitPolicyValidation", run_start)
    run = backtest[run_start:run_end]
    assert "createMultiStrategyBacktestJob" in run
    assert "const previousExact = readBacktestCache(runSignature)" in run
    assert 'setResultRestoreMode("manual-cache")' in run
    assert "setResultRestoreMode(null)" in run
    assert "setResult(null)" not in run
    assert "기존 완료 결과는 아래에 유지됩니다." in backtest
    assert "기존 완료 결과는 그대로 유지됩니다." in backtest

    # Backtest stock search now follows J2 stale-response protection.
    assert "stockSearchRequestIdRef" in backtest
    assert "new AbortController()" in backtest
    assert "searchStocks(query, { signal: controller.signal })" in backtest
    assert "requestId !== stockSearchRequestIdRef.current" in backtest
    assert "controller?.abort()" in backtest
    assert "stockSearchRequestIdRef.current += 1" in backtest
    assert "isAbortError(error)" in backtest

    # Exit research/job lifecycle remains a separate explicit workflow.
    assert "createExitPolicyValidationJob" in backtest
    assert "cancelBacktestJob<ExitPolicyValidationReport>" in backtest


def test_ux_redesign1j4_prioritizes_held_management_and_separates_opening_balance_from_buy() -> None:
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")
    tracking = Path("frontend/src/components/StockTrackingActions.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/holdings.css").read_text(encoding="utf-8")

    # Watch -> held registration uses the OPENING_BALANCE registration path, never BUY.
    helper_start = holdings.index("function openExistingHoldingRegistration")
    helper_end = holdings.index("async function addSelectedAsWatch", helper_start)
    helper = holdings[helper_start:helper_end]
    assert 'setAddMode("held")' in helper
    assert "openManual" not in helper
    assert "recordManualBuy" not in helper

    register_start = holdings.index("async function addSelectedAsHeld")
    register_end = holdings.index("async function changeWatch", register_start)
    register_block = holdings[register_start:register_end]
    assert "registerHeldStock" in register_block
    assert "recordManualBuy" not in register_block
    assert "effective_at: toIso(addEffectiveAt)" in register_block
    assert "기존 보유 상태로 등록했습니다." in register_block

    assert "onClick={openExistingHoldingRegistration}" in holdings
    assert "기존 보유 등록" in holdings
    assert "새로운 매수 기록(BUY)을 생성하는 기능이 아닙니다." in holdings

    # Existing holdings keep explicit BUY / SELL / CORRECTION ledger mutations.
    assert "+ 추가 매수 기록" in holdings
    assert ">추가 매수 기록</button>" in holdings
    save_start = holdings.index("async function saveManual")
    save_end = holdings.index("const selectedAnalysis", save_start)
    save_block = holdings[save_start:save_end]
    assert 'manualMode === "buy"' in save_block
    assert "recordManualBuy" in save_block
    assert "recordManualSell" in save_block
    assert "recordManualCorrection" in save_block

    # Broker positions remain read-only from manual ledger controls.
    open_manual_start = holdings.index("async function openManual")
    open_manual_end = holdings.index("function adjustManualQuantity", open_manual_start)
    open_manual = holdings[open_manual_start:open_manual_end]
    assert 'position?.account_kind === "BROKER"' in open_manual
    assert "잔고 동기화로만 변경할 수 있습니다." in open_manual
    assert "증권사 연동 보유는 직접 수정하지 않습니다." in holdings

    # Held detail reads position/P&L/management before optional entry analysis.
    quickbar = holdings.index('className="holdings-position-quickbar"')
    pnl = holdings.index('className="holdings-pnl-block"', quickbar)
    management = holdings.index('className="holdings-management-block"', pnl)
    held_actions = holdings.index('className="holdings-position-actions-primary"', management)
    chart = holdings.index("<HoldingsPriceChart", held_actions)
    news = holdings.index("<StockNewsPanel", chart)
    disclosure = holdings.index("holdings-analysis-disclosure", news)
    assert quickbar < pnl < management < held_actions < chart < news < disclosure
    assert 'className="holdings-left-management"' not in holdings

    # Entry analysis is default-collapsed only for held perspective and is display-only.
    assert "추가 매수·신규 진입 관점 보기" in holdings
    assert "기존 보유분 관리와 분리된 보조 분석" in holdings
    assert 'open={detailPerspective === "watch" ? true : undefined}' in holdings
    assert "신규 진입 기준 가격" in holdings
    assert "현재 시점에 새 물량을 추가한다고 가정한 분석입니다." in holdings
    disclosure_start = holdings.index("<details", news)
    disclosure_end = holdings.index("</details>", disclosure_start)
    disclosure_block = holdings[disclosure_start:disclosure_end]
    # Opening the disclosure itself is display-only. A separate explicit "분석 실행"
    # button may exist only for the no-saved-analysis empty state.
    summary_end = holdings.index("</summary>", disclosure_start)
    disclosure_summary = holdings[disclosure_start:summary_end]
    assert "refreshSelected" not in disclosure_summary
    assert "applyLatestManagementPlan" not in disclosure_summary
    assert "registerHeldStock" not in disclosure_summary
    assert "recordManualBuy" not in disclosure_summary

    # Active management remains explicit and non-applicable proposals explain themselves.
    assert "현재 보유분에 실제 적용 중인 손절·목표 가격" in holdings
    assert "현재 적용 중인 보유분 관리 기준이 없습니다." in holdings
    assert "기술 정보 · 내부 기준" in holdings
    assert "현재 적용할 수 없는 제안입니다." in holdings
    assert "item.proposal.can_apply &&" in holdings
    assert "이 계획 적용" in holdings
    assert "applyLatestManagementPlan" in holdings

    # Stock analysis uses the same opening-balance language and guardrail.
    assert "기존 보유 등록" in tracking
    assert "보유종목으로 등록" not in tracking
    assert "보유종목 등록" not in tracking
    assert "registerHeldStock" in tracking
    assert "신규 매수 주문이나 BUY 이벤트를 생성하는 기능이 아닙니다." in tracking

    # Editorial disclosure and management layout are explicit.
    assert "UX-REDESIGN.1J-4" in styles
    assert ".holdings-analysis-disclosure.perspective-held" in styles
    assert ".holdings-position-management .holdings-positions" in styles
    assert "order: 6" in styles
    assert ".holdings-opening-balance-note" in styles


def test_ux_redesign1j5_scanner_defaults_to_reading_and_separates_explicit_work() -> None:
    scanner = Path("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    # Candidate rows remain the fast explicit mutation surface; nested buttons do not select rows.
    row_start = scanner.index("function CandidateCompareRow")
    row_end = scanner.index("function CandidateDetail", row_start)
    row = scanner[row_start:row_end]
    assert 'onClick={onSelect}' in row
    assert "event.stopPropagation()" in row
    assert '"☆ 관심"' in row
    assert '"+ 기존 보유"' in row
    assert "onAddWatch()" in row
    assert "onRegisterHeld()" in row

    # Selected detail is now a reading surface, not a duplicate mutation toolbar.
    detail_start = scanner.index("function CandidateDetail")
    detail_end = scanner.index("export default function ScannerPanel", detail_start)
    detail = scanner[detail_start:detail_end]
    assert "☆ 관심 추가" not in detail
    assert "+ 보유 등록" not in detail
    assert "onAddWatch" not in detail
    assert "onRegisterHeld" not in detail
    assert "전문 분석에서 더 보기 →" in detail
    assert "내 종목 관리 →" in detail
    assert "scanner-selected-management-summary" in detail

    # Data recovery that is actually actionable is visible without opening the evidence details.
    assert "scanner-evidence-recovery-inline" in detail
    assert "3년 근거 데이터 준비" in detail
    inline_recovery_start = detail.index("scanner-evidence-recovery-inline")
    details_start = detail.index('className="scanner-evidence-details"', inline_recovery_start)
    assert inline_recovery_start < details_start
    assert "evidence && !evidence.verified && canPrepareEvidence" in detail
    assert "evidencePreparationAvailable(candidate)" in scanner

    # Normal freshness/retry flows reuse cache; only the advanced option force-refreshes.
    assert "최신 확정 시세 확인" in scanner
    assert 'onClick={() => void runScanner(false)}' in scanner
    assert "분석 실행 옵션" in scanner
    assert ">강제 재계산</button>" in scanner
    force_option_start = scanner.index('className="scanner-run-options"')
    force_option_end = scanner.index("</details>", force_option_start)
    force_option = scanner[force_option_start:force_option_end]
    assert "runScanner(true)" in force_option
    assert "현재 저장된 Scanner 계산 결과를 사용하지 않고" in force_option
    assert ">다시 분석</button>" not in scanner
    assert "runScanner(Boolean(result))" not in scanner

    # Large missing-data preparation remains explicit and may bypass the partial cached result.
    assert "누락 시장 데이터 준비" in scanner
    assert "runScanner(true, true)" in scanner
    assert "allow_large_sync: allowLargeSync" in scanner

    # A normal Scanner rerun preserves the selected candidate without reusing Evidence intent.
    run_start = scanner.index("async function runScanner")
    run_end = scanner.index("async function prepareCandidateEvidence", run_start)
    run = scanner[run_start:run_end]
    assert "scannerSelectionToPreserveRef.current = result && selectedCandidateKey ? selectedCandidateKey : null" in run
    assert "preferredCandidateKeyRef.current = null" in run
    poll_start = scanner.index("async function poll")
    poll_end = scanner.index("async function runScanner", poll_start)
    poll = scanner[poll_start:poll_end]
    assert "const evidencePreferredKey = preferredCandidateKeyRef.current" in poll
    assert "const preferredKey = evidencePreferredKey ?? scannerSelectionToPreserveRef.current" in poll
    assert "latestCandidates.find" in poll
    assert "latest.result.candidates[0]" in poll

    # Evidence preparation still keeps its dedicated candidate and is not automatic.
    evidence_start = scanner.index("async function prepareCandidateEvidence")
    evidence_end = scanner.index("function upsertManagedStock", evidence_start)
    evidence = scanner[evidence_start:evidence_end]
    assert "createScannerEvidenceJob" in evidence
    assert "preferredCandidateKeyRef.current = selectionKey" in evidence
    assert "scannerSelectionToPreserveRef.current = null" in evidence

    # Holdings status is a local read dependency; retrying it must not rerun Scanner.
    load_holdings_start = scanner.index("async function loadManagedStocks")
    load_holdings_end = scanner.index("useEffect(() =>", load_holdings_start)
    load_holdings = scanner[load_holdings_start:load_holdings_end]
    assert "listHoldingStocks()" in load_holdings
    assert "runScanner(" not in load_holdings
    assert "createScannerJob" not in load_holdings
    assert "createScannerEvidenceJob" not in load_holdings
    assert "등록 상태 다시 확인" in scanner

    # Scanner's held registration is explicitly OPENING_BALANCE-style registration, not a BUY event.
    held_start = scanner.index("async function submitHoldingRegistration")
    held_end = scanner.index("function openCandidateInHoldings", held_start)
    held = scanner[held_start:held_end]
    assert "registerHeldStock" in held
    assert "recordManualBuy" not in held
    assert "기존 보유 상태로 등록했습니다." in held
    assert "보유 상태 기준 시각" in scanner
    assert "새로운 매수 기록(BUY)을 생성하는 기능이 아닙니다." in scanner

    # The visual hierarchy is restrained: text navigation + hidden advanced execution.
    assert "UX-REDESIGN.1J-5" in styles
    assert ".scanner-run-options" in styles
    assert ".scanner-text-action" in styles
    assert ".scanner-selected-management-summary" in styles
    assert ".scanner-evidence-recovery-inline" in styles


def test_ux_redesign1j7_full_news_uses_restrained_cards_and_preserves_compact_news() -> None:
    panel = Path("frontend/src/components/StockNewsPanel.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/stock-analysis.css").read_text(encoding="utf-8")
    scanner = Path("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")

    # NEWS.1 request/display counts are unchanged.
    assert "requestLimit = compact ? 5 : 10" in panel
    assert "collapsedLimit = compact ? 3 : 5" in panel
    assert "expandedLimit = compact ? 5 : 10" in panel
    assert "news?.items.slice(0, expanded ? expandedLimit : collapsedLimit)" in panel

    # Fetch isolation/race protection remains intact.
    assert "new AbortController()" in panel
    assert "requestIdRef" in panel
    assert "requestId !== requestIdRef.current" in panel
    assert "controller.signal.aborted" in panel
    assert "fetchStockNews(code, market, { limit: requestLimit, signal: controller.signal })" in panel

    # Full news presents source -> time -> linked title, while compact keeps time -> source.
    assert 'className="stock-news-source"' in panel
    assert 'className="stock-news-time"' in panel
    compact_meta = panel.index("{compact ? (")
    compact_source = panel.index('className="stock-news-source"', compact_meta)
    compact_time = panel.index('className="stock-news-time"', compact_meta)
    full_branch = panel.index(") : (", compact_meta)
    full_source = panel.index('className="stock-news-source"', full_branch)
    full_time = panel.index('className="stock-news-time"', full_branch)
    assert compact_time < compact_source < full_branch
    assert full_branch < full_source < full_time

    # The title remains the safe external link for every article.
    assert '<a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>' in panel

    # The separate "원문" affordance is compact-only; full cards do not reserve a right column for it.
    origin_start = panel.index('className="stock-news-origin"')
    compact_guard = panel.rfind("{compact && (", 0, origin_start)
    assert compact_guard != -1
    assert "원문 ↗" in panel

    # Full layout is a restrained two-column editorial grid, collapsing to one column when narrow.
    assert "UX-REDESIGN.1J-7" in styles
    assert ".stock-news-panel.full .stock-news-list" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in styles
    assert ".stock-news-panel.full .stock-news-item" in styles
    assert "border: 1px solid var(--border-subtle)" in styles
    assert "border-radius: 8px" in styles
    assert "@media (max-width: 860px)" in styles
    responsive_start = styles.index("@media (max-width: 860px)")
    responsive_end = styles.index("@media (max-width: 720px)", responsive_start)
    assert "grid-template-columns: 1fr" in styles[responsive_start:responsive_end]

    # Long full titles are bounded to three lines and descriptions remain at two.
    full_title_start = styles.index(".stock-news-panel.full .stock-news-item h4")
    full_title_end = styles.index(".stock-news-panel.full .stock-news-item p", full_title_start)
    full_title = styles[full_title_start:full_title_end]
    assert "-webkit-line-clamp: 3" in full_title
    full_description_start = full_title_end
    full_description_end = styles.index(".stock-news-origin", full_description_start)
    assert "-webkit-line-clamp: 2" in styles[full_description_start:full_description_end]

    # Compact Scanner/Holdings news keeps its existing row/list contract and separate origin link.
    assert 'variant="compact"' in scanner
    assert 'variant="compact"' in holdings
    compact_style_start = styles.index(".stock-news-panel.compact .stock-news-item")
    compact_style_end = styles.index(".stock-news-panel.compact .stock-news-item h4", compact_style_start)
    compact_style = styles[compact_style_start:compact_style_end]
    assert "display: grid" in compact_style
    assert "grid-template-columns: minmax(0, 1fr) auto" in compact_style
    assert ".stock-news-panel.compact .stock-news-origin" in styles

    # Missing metadata keeps explicit fallbacks; no synthetic article text is invented.
    assert 'sourceName || sourceDomain || "출처 확인"' in panel
    assert 'return "시각 정보 없음"' in panel
    assert "{item.description && <p>{item.description}</p>}" in panel

    # Expanding 5 -> 10 is local state only; it does not introduce another fetch path.
    assert 'onClick={() => setExpanded((value) => !value)}' in panel
    assert panel.count("fetchStockNews(") == 1

    # NEWS.1 interpretation boundary and local error isolation remain visible.
    assert "호재·악재 또는 주가 방향을 판정하지 않습니다." in panel
    assert "최근 뉴스만 불러오지 못했습니다." in panel
    assert "종목 분석과 전략 계산 결과에는 영향을 주지 않습니다." in panel


def test_ux_redesign1j6_separates_stock_reads_from_explicit_strategy_execution() -> None:
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    workspace = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")
    chart = Path("frontend/src/components/StockAnalysisPriceChart.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/stock-analysis.css").read_text(encoding="utf-8")

    # Direct/revisited analysis keeps the J2 automatic stock-context read.
    assert 'if (appPage !== "analysis" || !stockCode || !selectedStockName || stock || stockBusy) return' in app
    assert "void loadStockContextForSelection(stockCode, stockMarket, selectedStockName)" in app
    assert "fetchStockContext(normalizedCode, market, { signal: controller.signal })" in app

    # The normal UI no longer asks for a redundant basic-info load button.
    assert "기본 정보 불러오기" not in workspace
    assert "onLoadContext" not in workspace
    assert "onRetryContext" in workspace
    assert "stockContextError" in workspace
    assert "selectedStockName && !stockBusy && stockContextError" in workspace
    assert "다시 확인" in workspace

    # Retrying context remains a read-only stock-context action, never a strategy run.
    retry_prop = 'onRetryContext={() => void quickAnalyze()}'
    assert retry_prop in app
    quick_start = app.index("async function quickAnalyze")
    quick_end = app.index("useEffect(() =>", quick_start)
    quick = app[quick_start:quick_end]
    assert "loadStockContextForSelection" in quick
    assert "runStrategyAnalysis" not in quick
    assert "fetchStrategyAnalysis" not in quick

    # Confirmed-EOD chart renders as soon as stock context exists, before any Strategy result.
    assert workspace.count("<StockAnalysisPriceChart") == 1
    chart_index = workspace.index("<StockAnalysisPriceChart")
    execution_index = workspace.index("stock-analysis-execution")
    verdict_index = workspace.index("stock-analysis-verdict")
    assert chart_index < execution_index < verdict_index
    assert 'analysis={strategyAnalysis}' in workspace
    assert "analysis: StrategyAnalysis | null" in chart

    # Strategy-derived plan levels are absent naturally when analysis is null.
    assert "const plan = analysis?.risk_analysis.selected_plan ?? null" in chart
    assert "analysis?.data_freshness.eod_close ?? null" in chart
    assert "이 기간 데이터 준비" in chart
    assert "prepareStockChartWithProgress" in chart

    # There is one primary explicit execution stage.
    assert "전략 분석 실행" in workspace
    assert "변경값으로 다시 분석" in workspace
    assert "분석 실행 옵션" in workspace
    assert "같은 조건으로 다시 분석" in workspace
    assert "현재 세션의 분석 결과를 표시 중입니다." in workspace
    assert "최신 분석" not in workspace

    # The expert child no longer contains a duplicate run button.
    child_start = app.index('{stock && (', app.index("<StockAnalysisWorkspace"))
    child_end = app.index("</StockAnalysisWorkspace>", child_start)
    child = app[child_start:child_end]
    assert "분석 세부 설정" in child
    assert "runStrategyAnalysis()" not in child
    assert "실행은 기본 분석 영역에서 한 번만 합니다." in child

    # A new stock clears the previous result; same-stock selection does not.
    choose_start = app.index("function chooseStock")
    choose_end = app.index("function changeStockQuery", choose_start)
    choose = app[choose_start:choose_end]
    assert "const sameStock = selectedStockKeyRef.current === nextKey" in choose
    assert "if (!sameStock) {" in choose
    reset_start = choose.index("if (!sameStock) {")
    reset = choose[reset_start:choose.index("setStockMessage", reset_start)]
    assert "setStrategyAnalysis(null)" in reset
    assert "setLastAnalysisInputSignature" in reset

    # Rerun failure preserves an existing completed result and its input signature.
    run_start = app.index("async function runStrategyAnalysis")
    run_end = app.index("function navigateAnalysis", run_start)
    run = app[run_start:run_end]
    assert "const hadExistingResult = strategyAnalysis != null" in run
    assert "if (!hadExistingResult)" in run
    failure_branch_start = run.index("if (!hadExistingResult)")
    failure_branch = run[failure_branch_start:]
    assert "setStrategyAnalysis(null)" in failure_branch
    assert "setLastAnalysisInputSignature" in failure_branch
    assert "현재 표시 중인 이전 분석 결과는 유지됩니다." in failure_branch

    # Stale/racing strategy responses remain protected by request, stock, and input identity.
    assert "requestId !== strategyRequestIdRef.current" in run
    assert "selectedStockKeyRef.current !== requestedStockKey" in run
    assert "analysisInputSignatureRef.current !== requestInputSignature" in run
    assert "isAbortError(error)" in run

    # Official EOD and hypothetical inputs remain explicitly separate.
    assert "공식 확정 EOD 기준" in workspace
    assert "가상 분석 조건" in child
    assert "공식 확정 일봉 분석을 덮어쓰지 않습니다." in child
    assert "실제 보유 수량·평균단가와 원장을 변경하지 않습니다." in child

    # J6 styling keeps the flow editorial instead of adding another card system.
    assert "UX-REDESIGN.1J-6" in styles
    assert ".stock-analysis-chart-stage" in styles
    assert ".stock-analysis-execution" in styles
    assert ".stock-analysis-run-options" in styles
    assert ".stock-analysis-plan-section" in styles


def test_pre_j8_basis_and_async_safety_contracts() -> None:
    workspace = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")
    backtest = Path("frontend/src/components/BacktestPanel.tsx").read_text(encoding="utf-8")
    scanner = Path("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")

    # PRE-J8.1: the price plan label follows the actual response basis.
    assert 'const strategyBasis = plan?.basis' in workspace
    assert 'strategyAnalysis?.risk_analysis.basis' in workspace
    assert 'strategyAnalysis?.data_freshness.analysis_basis' in workspace
    assert 'const manualReferenceBasis = strategyBasis === "MANUAL_REFERENCE"' in workspace
    assert 'const confirmedEodBasis = strategyBasis === "CONFIRMED_EOD"' in workspace
    assert "SCENARIO PRICE PLAN" in workspace
    assert "가상 시나리오 가격 계획" in workspace
    assert "사용자 참고가격 기준" in workspace
    assert "공식 확정 EOD 가격 계획이 아닙니다." in workspace
    assert "확정 일봉을 기준으로 계산한 공식 가격 계획입니다." in workspace
    assert "참고가격 시나리오를 입력해도 이 영역의 공식 기준은 확정 일봉 분석입니다." not in workspace

    # No synthetic confirmed-EOD Risk plan is created for a manual-reference result.
    assert "const plan = strategyAnalysis?.risk_analysis.selected_plan ?? null" in workspace
    assert "MANUAL_REFERENCE" in workspace
    assert "selected_plan" in workspace

    # PRE-J8.2 Backtest: create and poll responses are accepted only for the same run identity.
    assert "const runGenerationRef = useRef(0)" in backtest
    assert "const activeRunRef = useRef<{" in backtest
    assert "signature: runSignature" in backtest
    assert "code: runCode" in backtest
    assert "market: runConfig.market" in backtest
    assert "const isCurrentRun = (jobId: string | null = null)" in backtest
    assert "runGenerationRef.current === generation" in backtest
    assert "active.jobId === jobId" in backtest
    create_index = backtest.index("const created = await createMultiStrategyBacktestJob")
    create_guard_index = backtest.index("if (!isCurrentRun())", create_index)
    create_state_index = backtest.index("setJob(created)", create_index)
    assert create_index < create_guard_index < create_state_index
    poll_index = backtest.index("const latest = await fetchBacktestJob<MultiStrategyBacktestResponse>")
    poll_guard_index = backtest.index("if (!isCurrentRun(created.job_id)", poll_index)
    poll_state_index = backtest.index("setJob(latest)", poll_index)
    cache_write_index = backtest.index("writeBacktestCache(entry)", poll_index)
    assert poll_index < poll_guard_index < poll_state_index < cache_write_index

    # PRE-J8.2 Scanner: navigation invalidates only the observer, not the server job.
    assert "const pollObserverGenerationRef = useRef(0)" in scanner
    assert "const mountedRef = useRef(true)" in scanner
    assert "mountedRef.current = false" in scanner
    assert "pollObserverGenerationRef.current += 1" in scanner
    assert "const observerIsCurrent = () => {" in scanner
    assert 'activeTask?.kind === "scanner"' in scanner
    assert "activeTask.jobId === jobId" in scanner
    scanner_poll_index = scanner.index("const latest = await fetchBacktestJob<ScannerResponse>(jobId)")
    scanner_guard_index = scanner.index("if (!observerIsCurrent()) return", scanner_poll_index)
    scanner_state_index = scanner.index("setJob(latest)", scanner_poll_index)
    scanner_task_write_index = scanner.index("writeActiveDataTask({", scanner_poll_index)
    assert scanner_poll_index < scanner_guard_index < scanner_state_index < scanner_task_write_index
    cleanup_start = scanner.index("mountedRef.current = false")
    cleanup_end = scanner.index("}, []);", cleanup_start)
    assert "cancelBacktestJob" not in scanner[cleanup_start:cleanup_end]

    # PRE-J8.2 Holdings: background work targets the captured stock but preserves live selection.
    assert 'selectionMode: "prefer-target" | "preserve-current" = "prefer-target"' in holdings
    assert "const currentSelection = selectedStockIdRef.current" in holdings
    assert 'selectionMode === "preserve-current"' in holdings
    assert "selectedStockIdRef.current = keep" in holdings
    assert "const targetStockId = selectedStockIdRef.current" in holdings
    assert 'await reloadStocks(targetStockId, "preserve-current")' in holdings
    assert "if (selectedStockIdRef.current === targetStockId)" in holdings
    assert 'await reloadStocks(null, "preserve-current")' in holdings
    assert "const currentStockId = selectedStockIdRef.current" in holdings

def test_j8_3_frontend_data_contract_integration() -> None:
    api = Path("frontend/src/services/api.ts").read_text(encoding="utf-8")
    hook = Path("frontend/src/hooks/useStockDataContract.ts").read_text(encoding="utf-8")
    helper = Path("frontend/src/services/dataContract.ts").read_text(encoding="utf-8")
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    workspace = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")
    stock_chart = Path("frontend/src/components/StockAnalysisPriceChart.tsx").read_text(encoding="utf-8")
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")
    holdings_chart = Path("frontend/src/components/HoldingsPriceChart.tsx").read_text(encoding="utf-8")

    # Public client consumes J-8.2 read-only contract and preserves the four-state vocabulary.
    assert 'export type DataContractResourceStatus = "ABSENT" | "UNVERIFIED" | "VALID" | "INVALID"' in api
    assert "export type StockDataContract =" in api
    assert "export async function fetchStockDataContract(" in api
    assert "/api/data-contract/stocks/" in api
    assert 'query.set("range", options.range)' in api
    assert 'query.set("job_id", options.jobId.trim())' in api
    assert "signal: options.signal" in api

    # Hook invalidates stale requests instead of allowing stock A to overwrite stock B.
    assert "const generationRef = useRef(0)" in hook
    assert "const abortRef = useRef<AbortController | null>(null)" in hook
    assert "const generation = ++generationRef.current" in hook
    assert "abortRef.current?.abort()" in hook
    assert "generation !== generationRef.current" in hook
    assert "controller.signal.aborted" in hook

    # UNVERIFIED remains a neutral currentness limitation, not an error or auto-refresh loop.
    assert 'case "UNVERIFIED": return "현재성 확인 제한"' in helper
    assert "저장 결과 있음 · 현재 입력 기준과 완전 일치 여부는 확인하지 않았습니다." in helper
    assert "refreshHoldingAnalysis" not in helper
    assert "prepareStockChartWithProgress" not in helper

    # App reads the contract independently from session Strategy results.
    assert "useStockDataContract({" in app
    assert "contract: stockDataContract" in app
    assert "strategyAnalysis" in app
    assert "dataContract={stockDataContract}" in app
    assert "setStrategyAnalysis(null)" not in app[app.index("contract: stockDataContract"):app.index("const analysisInputSignature")]

    # Analysis UI explicitly labels stored server analysis separately from the session Strategy result.
    assert "저장된 분석 상태" in workspace
    assert "서버에 저장된 Holdings 분석 상태를 별도로 확인합니다." in workspace
    assert "stock-analysis-data-state" in workspace
    assert "strategyAnalysis" in workspace

    # Chart preparation is contract-authorized and user initiated; no mount-time POST was added.
    assert 'contractAction(dataContract, "PREPARE_CHART")' in stock_chart
    assert "if (preparing || !prepareChartAction) return" in stock_chart
    assert 'onClick={() => void prepareRange()}' in stock_chart
    effect_start = stock_chart.index("useEffect(() => {")
    prepare_start = stock_chart.index("async function prepareRange")
    assert "prepareStockChartWithProgress" not in stock_chart[effect_start:prepare_start]

    # Late preparation responses are guarded by stock/range identity.
    assert "const prepareGenerationRef = useRef(0)" in stock_chart
    assert "const activeIdentityRef = useRef" in stock_chart
    assert "const isCurrent = () =>" in stock_chart
    assert "activeIdentityRef.current === identity" in stock_chart

    # Holdings reads a contract only for the selected detail; there is no list-wide N+1 fetch.
    assert "contract: selectedDataContract" in holdings
    assert 'code: detail?.ticker ?? ""' in holdings
    assert "enabled: Boolean(detail && selectedStockId === detail.stock_id)" in holdings
    reload_start = holdings.index("async function reloadStocks")
    load_selected_start = holdings.index("async function loadSelected")
    assert "fetchStockDataContract" not in holdings[reload_start:load_selected_start]
    assert "저장된 분석" in holdings
    assert "보유 원장" in holdings

    # Analysis refresh/history prepare/KIS sync re-read current contract without hijacking selection.
    assert "await contractRefreshRef.current()" in holdings
    assert "if (selectedStockIdRef.current === targetStockId)" in holdings
    assert "const currentStockId = selectedStockIdRef.current" in holdings

    # Holdings chart also requires explicit PREPARE_CHART and guards stale completion.
    assert 'contractAction(dataContract, "PREPARE_CHART")' in holdings_chart
    assert "if (!chart || preparingRange || !prepareChartAction) return" in holdings_chart
    assert "const prepareGenerationRef = useRef(0)" in holdings_chart
    assert "activeIdentityRef.current === identity" in holdings_chart
    assert 'onClick={() => void prepareSelectedRange()}' in holdings_chart

    # J-8.3 does not invent realtime data or alter Scanner/Backtest workflows.
    assert "REALTIME_BACKEND_NOT_IMPLEMENTED" not in app + workspace + stock_chart + holdings + holdings_chart
    assert "createScannerJob" not in hook + helper
    assert "createMultiStrategyBacktestJob" not in hook + helper

def test_realtime2_selected_quote_polling_and_domain_boundaries() -> None:
    api = Path("frontend/src/services/api.ts").read_text(encoding="utf-8")
    hook = Path("frontend/src/hooks/useStockQuote.ts").read_text(encoding="utf-8")
    helper = Path("frontend/src/services/quote.ts").read_text(encoding="utf-8")
    strip = Path("frontend/src/components/StockQuoteStrip.tsx").read_text(encoding="utf-8")
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    workspace = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")

    # REALTIME.1 product quote response is represented directly in the frontend contract.
    assert 'export type StockQuoteVenue = "INTEGRATED" | "KRX" | "NXT"' in api
    assert 'export type StockQuoteResponse = {' in api
    assert 'export async function fetchStockQuote(' in api
    assert "/api/quotes/stocks/" in api
    assert 'venue: options.venue ?? "INTEGRATED"' in api
    assert "{ signal: options.signal }" in api

    # Data Contract realtime typing follows the additive REALTIME.1 backend fields.
    for token in (
        "capability: boolean",
        "provider: string | null",
        "current_price: string | null",
        "received_at: string | null",
        "age_ms: number | null",
        "freshness_seconds: number | null",
    ):
        assert token in api

    # Polling is completion-driven, never setInterval-driven, and guards stale identities.
    assert "pollIntervalMs = 5_000" in hook
    assert "MAX_BACKOFF_MS = 30_000" in hook
    assert "window.setTimeout" in hook
    assert "setInterval" not in hook
    assert "const generationRef = useRef(0)" in hook
    assert "const abortRef = useRef<AbortController | null>(null)" in hook
    assert "const matchesIdentity =" in hook
    assert "incoming.resource_key === resourceKey" in hook
    assert "incoming.ticker === normalizedCode" in hook
    assert "incoming.venue === venue" in hook

    # Hidden/offline work is paused and resumes only when the page becomes usable.
    assert '"visibilitychange"' in hook
    assert 'document.visibilityState === "hidden"' in hook
    assert 'window.addEventListener("offline"' in hook
    assert 'window.addEventListener("online"' in hook
    assert "abortRef.current?.abort()" in hook

    # Success returns to 5 s; transient failures back off 10 -> 20 -> max 30 s.
    assert "2 ** failuresRef.current" in hook
    assert "failuresRef.current = 0" in hook
    assert "Math.min(" in hook
    assert "MAX_BACKOFF_MS" in hook

    # Configuration / validation failures pause automatic polling.
    assert 'apiError?.status === 409' in hook
    assert 'apiError?.code === "KIS_QUOTE_NOT_CONFIGURED"' in hook
    assert "permanentlyPaused = true" in hook
    assert 'apiError?.status === 422' in hook
    assert "if (!isCurrent() || permanentlyPaused) return" in hook

    # A transient failure preserves the last successful quote instead of clearing it.
    transient_start = hook.index("failuresRef.current += 1")
    transient_end = hook.index("} finally", transient_start)
    assert "setQuote(null)" not in hook[transient_start:transient_end]
    assert 'setState(quoteRef.current ? "DELAYED" : "ERROR")' in hook

    # Polling only calls the quote endpoint; it does not create a second Data Contract poll.
    assert "fetchStockDataContract" not in hook
    assert "fetchStrategyAnalysis" not in hook
    assert "createScannerJob" not in hook
    assert "createMultiStrategyBacktestJob" not in hook

    # Shared UI clearly labels the current quote while realtime transport stays secondary.
    assert 'aria-label="KIS 현재가"' in strip
    assert "현재가" in strip
    assert "새로고침" in strip
    assert "KIS 통합 시세" in helper
    assert "마지막 수신" in helper

    # Analysis page polls exactly the selected stock while that page is active.
    assert 'import useStockQuote from "./hooks/useStockQuote"' in app
    assert "quote: stockQuote" in app
    assert 'venue: "INTEGRATED"' in app
    assert 'enabled: appPage === "analysis"' in app
    assert "quote={stockQuote}" in app
    assert "<StockQuoteStrip" in workspace
    assert "최근 확정 종가" in workspace
    assert "분석 기준" in workspace

    # Quote arrival never writes the manual reference scenario or triggers Strategy automatically.
    quote_hook_start = app.index("quote: stockQuote")
    analysis_signature_start = app.index("const analysisInputSignature", quote_hook_start)
    quote_hook_block = app[quote_hook_start:analysis_signature_start]
    assert "setReferencePriceInput" not in quote_hook_block
    assert "runStrategyAnalysis" not in quote_hook_block
    assert "setStrategyAnalysis" not in quote_hook_block

    # Holdings polls only the selected detail, not every list row.
    assert 'import useStockQuote from "../hooks/useStockQuote"' in holdings
    assert "quote: selectedQuote" in holdings
    assert 'code: detail?.ticker ?? ""' in holdings
    assert "enabled: Boolean(detail && selectedStockId === detail.stock_id)" in holdings
    assert holdings.count("useStockQuote({") == 1
    reload_start = holdings.index("async function reloadStocks")
    load_selected_start = holdings.index("async function loadSelected")
    assert "fetchStockQuote" not in holdings[reload_start:load_selected_start]
    assert "<StockQuoteStrip" in holdings

    # REALTIME.2 is display-only: it does not feed quote values into holdings P&L or official analysis.
    assert "selectedQuote.current_price" not in holdings
    assert "getHoldingPerformance(selectedQuote" not in holdings
    assert "selectedAnalysis.reference_price = selectedQuote" not in holdings

def test_realtime3_live_holdings_valuation_boundaries() -> None:
    performance = Path("backend/app/holdings/performance.py").read_text(encoding="utf-8")
    live_backend = Path("backend/app/holdings/live_performance.py").read_text(encoding="utf-8")
    read_only_catalog = Path("backend/app/holdings/read_only_catalog.py").read_text(encoding="utf-8")
    holdings_api = Path("backend/app/api/holdings.py").read_text(encoding="utf-8")
    frontend_api = Path("frontend/src/services/holdingsApi.ts").read_text(encoding="utf-8")
    workspace = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")

    # Existing confirmed-EOD API keeps its original valuation path; live uses injected valuation.
    assert "def calculate_with_valuation(" in performance
    assert "return self.calculate_with_valuation(" in performance
    assert "self._valuation(stock)" in performance
    assert '@router.get("/stocks/{stock_id}/performance")' in holdings_api
    assert '@router.get("/stocks/{stock_id}/performance/live")' in holdings_api

    # Live backend is cache/read-only only: no KIS network/token and no schema initialization.
    assert "ReadOnlyHoldingsCatalog" in live_backend
    assert 'mode=ro' in read_only_catalog
    assert "PRAGMA query_only=ON" in read_only_catalog
    assert "observe_cached_quote" in live_backend
    for forbidden in (
        "inquire_domestic_price",
        "get_access_token",
        "issue_access_token",
        ".initialize(",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
    ):
        assert forbidden not in live_backend

    # The same Decimal performance result is reused instead of duplicating finance formulas.
    assert "calculate_with_valuation(" in live_backend
    assert 'source="KIS_REST_SNAPSHOT"' in live_backend
    assert "current_quantity *" not in live_backend
    assert "unrealized_pnl =" not in live_backend

    # Frontend receives backend-calculated performance and does not poll it independently.
    assert "export type LiveHoldingPerformanceResponse" in frontend_api
    assert "export function getLiveHoldingPerformance(" in frontend_api
    assert "/performance/live" in frontend_api
    assert "const [livePerformance, setLivePerformance]" in workspace
    assert "selectedQuote?.received_at" in workspace
    assert "getLiveHoldingPerformance(stockId" in workspace

    live_effect_start = workspace.index("void getLiveHoldingPerformance(stockId")
    live_effect_end = workspace.index("selectedStockIdRef.current = selectedStockId", live_effect_start)
    live_effect = workspace[live_effect_start:live_effect_end]
    assert "setInterval" not in live_effect
    assert "setTimeout" not in live_effect
    assert "livePerformanceRequestIdRef" in live_effect
    assert "livePerformanceAbortRef" in live_effect

    # Quote values are never multiplied into ledger values in React.
    assert "selectedQuote.current_price" not in workspace
    assert "selectedQuote?.current_price" not in workspace
    assert "quote.current_price *" not in workspace
    assert "current_price * quantity" not in workspace

    # Live performance is selected-detail only and preserves the confirmed fallback.
    assert "detail?.is_held" in workspace
    assert "detail.positions.length > 0" in workspace
    assert "const displayedPerformance = usingLivePerformance" in workspace
    assert ": performance;" in workspace
    assert "확정 종가" in workspace
    assert "KIS 현재가" in workspace
    assert "KIS Snapshot" in workspace

    # Ledger mutations refresh the local live calculation, while analysis/management semantics stay separate.
    assert workspace.count("setLivePerformanceRefreshKey((value) => value + 1)") >= 3
    assert "selectedAnalysis.reference_price = selectedQuote" not in workspace
    assert "management.valuation.price = selectedQuote" not in workspace

def test_realtime3b_live_management_proximity_boundaries() -> None:
    management = Path("backend/app/holdings/management.py").read_text(encoding="utf-8")
    live_backend = Path("backend/app/holdings/live_management.py").read_text(encoding="utf-8")
    readonly = Path("backend/app/holdings/read_only_catalog.py").read_text(encoding="utf-8")
    holdings_api = Path("backend/app/api/holdings.py").read_text(encoding="utf-8")
    frontend_api = Path("frontend/src/services/holdingsApi.ts").read_text(encoding="utf-8")
    workspace = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")

    # Existing management keeps the official EOD state calculation and shares only distance math.
    assert "def management_distance(" in management
    assert "return management_distance(level, price)" in management
    assert 'management_state": self._state(active, price)' in management
    assert "STOP_BREACHED" in management
    assert "TARGET1_REACHED" in management
    assert "TARGET2_REACHED" in management

    # Live proximity is explicitly distance-only: no live management_state or automatic decision.
    assert "management_distance(" in live_backend
    assert "management_state" not in live_backend
    assert "STOP_BREACHED" not in live_backend
    assert "TARGET1_REACHED" not in live_backend
    assert "TARGET2_REACHED" not in live_backend
    assert "apply_analysis_plan" not in live_backend

    # The live projection is read-only/cache-only.
    assert "ReadOnlyHoldingsCatalog" in live_backend
    assert "observe_cached_quote" in live_backend
    assert "mode=ro" in readonly
    assert "PRAGMA query_only=ON" in readonly
    for forbidden in (
        "inquire_domestic_price",
        "get_access_token",
        "issue_access_token",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        ".initialize(",
    ):
        assert forbidden not in live_backend

    assert '@router.get("/stocks/{stock_id}/management")' in holdings_api
    assert '@router.get("/stocks/{stock_id}/management/live-proximity")' in holdings_api

    # Frontend consumes backend-calculated distances; it does not compute stop/target math in React.
    assert "export type LiveHoldingManagementProximityResponse" in frontend_api
    assert "export function getLiveHoldingManagementProximity(" in frontend_api
    assert "/management/live-proximity" in frontend_api
    assert "const [liveManagementProximity, setLiveManagementProximity]" in workspace
    assert "selectedQuote?.received_at" in workspace
    assert "getLiveHoldingManagementProximity(stockId" in workspace
    assert "liveManagementRequestIdRef" in workspace
    assert "liveManagementAbortRef" in workspace

    live_start = workspace.index("void getLiveHoldingManagementProximity(stockId")
    live_end = workspace.index("selectedStockIdRef.current = selectedStockId", live_start)
    live_effect = workspace[live_start:live_end]
    assert "setInterval" not in live_effect
    assert "setTimeout" not in live_effect

    # Only held selected details with an already-applied plan request live proximity.
    assert "management?.positions.some((item) => item.active_plan != null)" in workspace
    assert "detail?.is_held" in workspace
    assert "selectedStockId === stockId" in workspace

    # UI preserves the EOD state label and shows only current-price distance metadata.
    assert "managementStateText(item.management_state)" in workspace
    assert "현재가 대비" in workspace
    assert "현재가 거리 · KIS" in workspace
    assert "갱신 지연" in workspace

    # No frontend distance formula or automatic plan mutation is introduced.
    assert "selectedQuote.current_price - item.active_plan" not in workspace
    assert "item.active_plan.stop_price - selectedQuote" not in workspace
    assert "applyHoldingManagementPlan(" in workspace
    assert "selectedQuote" not in workspace[workspace.index("async function applyLatestManagementPlan"):workspace.index("useEffect(() =>", workspace.index("async function applyLatestManagementPlan"))]

def test_realtime4_market_session_polling_boundaries() -> None:
    market_hook = Path("frontend/src/hooks/useDomesticMarketSession.ts").read_text(encoding="utf-8")
    quote_hook = Path("frontend/src/hooks/useStockQuote.ts").read_text(encoding="utf-8")
    market_helper = Path("frontend/src/services/marketSession.ts").read_text(encoding="utf-8")
    quote_strip = Path("frontend/src/components/StockQuoteStrip.tsx").read_text(encoding="utf-8")
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    analysis = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")
    holdings = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")
    data_contract = Path("frontend/src/services/api.ts").read_text(encoding="utf-8")

    # Market session has its own low-frequency lifecycle, not a quote-rate polling loop.
    assert "fetchDomesticMarketSession" in market_hook
    assert "DEFAULT_RECHECK_MS = 30 * 60 * 1000" in market_hook
    assert '"visibilitychange"' in market_hook
    assert 'window.addEventListener("offline"' in market_hook
    assert 'window.addEventListener("online"' in market_hook
    assert "next_transition_at" in market_hook
    assert "setInterval" not in market_hook

    # Session request failures degrade to UNKNOWN and keep quote capability alive.
    assert 'phase: "UNKNOWN"' in market_hook
    assert "quote_polling_allowed: true" in market_hook
    assert '"MARKET_SESSION_REQUEST_FAILED"' in market_hook

    # Automatic quote polling is allowed only by session policy.
    assert "marketSessionAllowsAutoQuote" in quote_hook
    assert "marketSessionIsPaused" in quote_hook
    assert "runNowRef.current?.(true)" in quote_hook  # manual refresh bypasses closed-session auto pause
    assert "if (!manual && !marketSessionAllowsAutoQuote(sessionRef.current)) return" in quote_hook
    assert "marketSessionIsPaused(marketSession.phase)" in quote_hook
    assert "window.clearTimeout(timerRef.current)" in quote_hook
    assert "abortRef.current?.abort()" in quote_hook
    assert "setInterval" not in quote_hook

    # Closed/intermission are the only automatic pause phases; UNKNOWN remains permissive.
    assert 'phase === "CLOSED" || phase === "INTERMISSION"' in market_helper
    assert 'session.quote_polling_allowed || session.phase === "UNKNOWN"' in market_helper

    # UI calls a closed/intermission observation a last quote, not a live stream.
    assert 'const priceLabel = pausedByMarket ? "마지막 시세" : "현재가"' in quote_strip
    assert '"장 마감"' in market_helper
    assert '"시장 전환 구간"' in market_helper
    assert '"프리마켓' in market_helper
    assert '"장중' in market_helper
    assert '"애프터마켓' in market_helper

    # Both selected-stock surfaces receive the session metadata.
    assert "marketSession: stockMarketSession" in app
    assert "marketSession={stockMarketSession}" in app
    assert "marketSession: DomesticMarketSessionResponse | null" in analysis
    assert "marketSession={marketSession}" in analysis
    assert "marketSession: selectedMarketSession" in holdings
    assert "marketSession={selectedMarketSession}" in holdings

    # Live P&L and management distance preserve the last snapshot label after market pause.
    assert "selectedMarketPaused" in holdings
    assert "마지막 KIS 시세" in holdings
    assert "selectedMarketPauseLabel" in holdings

    # Data Contract frontend typing carries session semantics without triggering a second poll.
    for token in (
        "session_phase: DomesticMarketSessionPhase | null",
        "trading_day: boolean | null",
        "market_active: boolean | null",
    ):
        assert token in data_contract
    assert "fetchStockDataContract" not in market_hook
    assert "fetchStockDataContract" not in quote_hook

    # REALTIME.4 remains REST-only; WebSocket transport is intentionally deferred.
    combined = market_hook + quote_hook + market_helper + quote_strip + holdings
    assert "H0STCNT0" not in combined
    assert "WebSocket(" not in combined



def test_realtime6_browser_sse_delivery_contract() -> None:
    stream = Path("frontend/src/services/quoteStream.ts").read_text(encoding="utf-8")
    hook = Path("frontend/src/hooks/useStockQuote.ts").read_text(encoding="utf-8")
    helper = Path("frontend/src/services/quote.ts").read_text(encoding="utf-8")
    strip = Path("frontend/src/components/StockQuoteStrip.tsx").read_text(encoding="utf-8")
    backend_api = Path("backend/app/api/quotes.py").read_text(encoding="utf-8")
    event_hub = Path("backend/app/quotes/event_hub.py").read_text(encoding="utf-8")
    ws_manager = Path("backend/app/quotes/websocket_manager.py").read_text(encoding="utf-8")

    assert "new EventSource" in stream
    assert 'addEventListener("status"' in stream
    assert 'addEventListener("quote"' in stream
    assert '"/stream?"' in stream

    assert 'streamStateRef.current === "LIVE"' in hook
    assert 'setStream("DEGRADED")' in hook
    assert "shouldApplyQuote" in hook
    assert "eventSourceRef.current?.close()" in hook
    assert 'document.visibilityState === "hidden"' in hook
    assert 'window.addEventListener("offline"' in hook

    assert "export function shouldApplyQuote" in helper
    assert 'delivery.source === "WEBSOCKET"' in helper
    assert "실시간 연결 복구 중 · REST 시세 사용" in helper
    assert "실시간 · KIS 통합 시세" in helper
    assert "streamState={quoteStreamState}" in Path(
        "frontend/src/components/StockAnalysisWorkspace.tsx"
    ).read_text(encoding="utf-8")
    assert "streamState={selectedQuoteStreamState}" in Path(
        "frontend/src/components/HoldingsWorkspace.tsx"
    ).read_text(encoding="utf-8")
    assert "streamState: StockQuoteStreamState" in strip

    assert '@router.get("/stocks/{ticker}/stream")' in backend_api
    assert 'media_type="text/event-stream"' in backend_api
    assert '"X-Accel-Buffering": "no"' in backend_api
    assert 'yield ": heartbeat\\n\\n"' in backend_api
    assert "asyncio.Queue(maxsize=1)" in event_hub
    assert "queue.get_nowait()" in event_hub
    assert "await self.event_hub.publish(key, snapshot)" in ws_manager

    protected = hook + stream + backend_api + event_hub
    assert "createScannerJob" not in protected
    assert "createMultiStrategyBacktestJob" not in protected
    assert "StrategyAnalysisService" not in protected
    assert "RiskEngine" not in protected
