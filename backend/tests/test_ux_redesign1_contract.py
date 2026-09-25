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
    assert 'evidence.status === "DATA_UNAVAILABLE"' in scanner
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
    assert 'className="scanner-compare-manage"' in scanner
    assert '"☆ 관심"' in scanner
    assert '"★ 관심"' in scanner
    assert '"+ 보유"' in scanner
    assert '"보유 중"' in scanner
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
