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
    assert '"+ 보유"' in scanner
    assert "보유 중" in scanner
    assert "event.stopPropagation()" in scanner

    assert "openHoldingRegistration" in scanner
    assert 'type="datetime-local"' in scanner
    assert "candidate.current_price" in scanner
    assert "quantity <= 0" in scanner
    assert "averagePrice <= 0" in scanner

    assert "onOpenHoldings" in scanner
    assert "내 종목에서 보기" in scanner
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
    assert "적용된 보유분 관리 기준이 없습니다." in holdings

    # New-entry analysis must not be presented as a held-position sell instruction.
    assert "신규 진입 관점 분석" in holdings
    assert "현재 보유분에 대한 매도 판단이 아닙니다." in holdings
    assert "현재 보유분의 매도를 지시하지 않습니다." in holdings

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
