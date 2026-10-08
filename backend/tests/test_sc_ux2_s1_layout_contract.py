"""SC-UX2-S1: the Scanner default view is a candidate-first decision workspace.

The calculation, persistent session, and registration contracts remain owned by
existing tests. These assertions cover the new presentation boundary only.
"""
from pathlib import Path

ROOT = Path("frontend/src/components")


def test_sc_ux2_s1_candidate_list_is_primary_and_summary_is_compact() -> None:
    panel = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    summary = (ROOT / "ScannerDecisionSummary.tsx").read_text(encoding="utf-8")

    assert 'className="scanner-result-summary scanner-ux2-result-strip"' in panel
    assert 'className="scanner-ux2-analysis-details"' in panel
    assert '<section className="scanner-section-head">' not in panel
    assert 'className="scanner-decision-workspace"' in panel
    assert 'className="scanner-compare-panel"' in panel
    assert 'className="scanner-ux2-row-next"' in panel
    assert "순서는 살펴볼 순서이며 매수 추천이 아니에요." in panel
    assert 'className="scanner-ux-decision scanner-ux2-decision"' in summary
    assert 'className="scanner-ux2-decision-why"' in summary
    assert 'className="scanner-ux-decision-facts scanner-ux2-facts"' in summary

    workspace = panel.index('className="scanner-decision-workspace"')
    list_start = panel.index('className="scanner-compare-panel"', workspace)
    detail = panel.index("<CandidateDetail", list_start)
    rank = panel.index("<ScannerRankComparison", detail)
    assert workspace < list_start < detail < rank


def test_sc_ux2_s1_responsive_columns_and_explicit_quote_loading() -> None:
    styles = (ROOT / "scannerUX.css").read_text(encoding="utf-8")
    price = (ROOT / "ScannerPriceStatus.tsx").read_text(encoding="utf-8")

    assert "SC-UX2-S1: candidate-first workspace" in styles
    assert "minmax(0, 1.16fr) minmax(390px, .84fr)" in styles
    assert "@media (max-width: 800px)" in styles
    assert "grid-template-areas:" in styles
    assert "SC-UX2-S1: one primary answer" in styles
    assert "<h4>분석일 가격과 새 시세</h4>" in price
    assert 'onClick={() => void checkPrice()}' in price
    check_start = price.index("async function checkPrice()")
    api_call = price.index("fetchStockQuote(candidate.code", check_start)
    return_start = price.index("return (", check_start)
    assert check_start < api_call < return_start
    assert "assessPriceRule(priceRule, candidate.current_price)" in price


def test_sc_ux2_s1_existing_scanner_and_management_paths_remain() -> None:
    panel = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    assert "createScannerJob(request)" in panel
    assert "createScannerEvidenceJob({" in panel
    assert "writeScannerSession({" in panel
    assert "readActiveDataTask()" in panel
    assert "listHoldingStocks()" in panel
    assert "addWatchStock({" in panel
    assert "registerHeldStock({" in panel
    assert "<ScannerRankComparison result={result} />" in panel
    assert "onAnalyze={() => analyzeCandidate(selectedCandidate)}" in panel
    assert "onAddWatch={() => void addCandidateToWatch(candidate)}" in panel
    assert "onRegisterHeld={() => openHoldingRegistration(candidate)}" in panel
