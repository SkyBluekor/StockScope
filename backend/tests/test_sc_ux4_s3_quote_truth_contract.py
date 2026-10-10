"""SC-UX4-S3: quote overlays are not Scanner decision or Risk revalidation."""
from pathlib import Path

ROOT = Path("frontend/src/components")


def test_quote_state_hoisted_above_tabs_and_scoped_to_analysis_execution() -> None:
    panel = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    hook = (ROOT / "useScannerQuote.ts").read_text(encoding="utf-8")
    view = (ROOT / "ScannerPriceStatus.tsx").read_text(encoding="utf-8")
    summary = (ROOT / "ScannerDecisionSummary.tsx").read_text(encoding="utf-8")
    assert "useScannerQuote(candidate)" in panel
    assert panel.index("useScannerQuote(candidate)") < panel.index('activeTab === "summary"')
    assert "quoteSnapshot={quoteSnapshot}" in panel
    assert 'onOpenPriceTab={() => setActiveTab("strategy")}' in panel
    assert "snapshot={quoteSnapshot}" in panel
    assert "onCheckPrice={() => void checkPrice()}" in panel
    assert 'key={candidateKey(selectedCandidate) + ":" + selectedCandidate.data_date + ":" + String(completedAt ?? "unconfirmed")}' in panel
    assert "controllerRef.current?.abort()" in hook
    assert "if (controller.signal.aborted) return" in hook
    assert "quoteMatchesCandidate(quoteResult.value, candidate)" in hook
    assert "fetchStockQuote(candidate.code, candidate.market" in hook
    assert "fetchDomesticMarketSession({ signal: controller.signal })" in hook
    assert "onClick={onCheckPrice}" in view
    assert "scannerQuoteTruth(candidate, quoteSnapshot)" in summary


def test_quote_traces_do_not_impersonate_current_strategy_validation() -> None:
    panel = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    view = (ROOT / "ScannerPriceStatus.tsx").read_text(encoding="utf-8")
    truth = (ROOT / "scannerQuoteTruth.ts").read_text(encoding="utf-8")
    summary = (ROOT / "ScannerDecisionSummary.tsx").read_text(encoding="utf-8")
    assert "분석일 · {simpleConditionStatus(candidate)}" in panel
    assert "asOfPriorityLabel(candidate)" in panel
    assert "분석일 기준 후보 순위" in panel
    assert "분석일에 선택된 전략" in panel
    assert "전략·위험: 재검증 전" in view
    assert "현재 전략·위험: 재검증 전" in summary
    assert "strategyRevalidated: false" in truth
    assert 'state: "NOT_CHECKED"' in truth
    assert 'state: "OUT_OF_RANGE"' not in panel
    assert "assessPriceRule(candidate.entry_risk_guide?.price_rule, numericPrice)" in truth
    assert "candidate.priority?.tier" in truth
    assert "quoteTimeText(quote.provider_timestamp)" in truth
    assert 'quote.delivery?.source === "CACHE"' in truth
    assert 'quote.environment === "virtual"' in truth
    assert "quoteMatchesCandidate(quote, candidate)" in truth


def test_risk_and_missing_conditions_remain_first_priority() -> None:
    summary = (ROOT / "ScannerDecisionSummary.tsx").read_text(encoding="utf-8")
    assert "keepAsOfNextStep" in summary
    assert 'candidate.priority?.tier === "RISK_HOLD"' in summary
    assert 'candidate.entry_risk_guide?.action.status === "RISK_BLOCKED"' in summary
    assert "candidate.conditions.missing > 0" in summary
    assert "keepAsOfNextStep ? view.next" in summary
    assert "view.missingConditions.map((condition, index)" in summary


def test_server_scanner_jev_and_quote_sources_are_unmodified_by_overlay() -> None:
    panel = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    jev = Path("backend/app/api/jev.py").read_text(encoding="utf-8")
    backtest = Path("backend/app/api/backtest.py").read_text(encoding="utf-8")
    assert "createScannerJob(request)" in panel
    assert "getJevReviews(captureId)" in panel
    assert "registerHeldStock({" in panel
    assert "addWatchStock({" in panel
    assert "<ScannerRankComparison result={result} />" in panel
    assert '"available": False' in jev
    assert 'result["execution_mode"] = "BASELINE_ONLY"' in backtest
