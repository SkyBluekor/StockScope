"""SC-UX4-S2 Scanner compact UX checks: do not rewrite strategy or Risk."""
from pathlib import Path

ROOT = Path("frontend/src/components")


def test_candidate_rows_are_compact_without_losing_actions_or_detail() -> None:
    panel = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    css = (ROOT / "scannerUX.css").read_text(encoding="utf-8")
    assert '<strong>{candidate.conditions.passed}/{candidate.conditions.total} 충족</strong>' in panel
    assert '<span>{view.nextActionLabel}</span>' in panel
    assert 'aiStatusLabel !== "AI 검토 미제공"' in panel
    assert 'aiStatusLabel !== "AI 검토 미실행"' in panel
    assert 'onAddWatch={() => void addCandidateToWatch(candidate)}' in panel
    assert 'onRegisterHeld={() => openHoldingRegistration(candidate)}' in panel
    assert "전체 {result.candidates.length + result.more_candidates.length}개 후보" in panel
    assert 'grid-template-columns: 24px minmax(74px, .9fr) minmax(125px, 1.8fr) 108px' in css


def test_collapsing_more_candidates_does_not_reset_selection() -> None:
    panel = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    start = panel.index("function toggleMoreCandidates()")
    end = panel.index("async function cancel()", start)
    body = panel[start:end]
    assert "setShowMore(next)" in body
    assert "setSelectedCandidateKey" not in body
    assert "selectedIsExtra" in panel
    assert "scanner-ux5-pinned-extra" in panel
    assert 'key={"pinned-" + candidateKey(selectedCandidate)}' in panel
    assert "reviewFor(selectedCandidate, selectedSampleIndex)" in panel
    assert 'onSelect={() => selectCandidateForReview(selectedCandidate)}' in panel

    workspace = panel.index('className="scanner-decision-workspace"')
    compare = panel.index("<ScannerRankComparison result={result} />", workspace)
    expand = panel.index("{result.more_candidates.length > 0 && (", workspace)
    detail = panel.index("<CandidateDetail", compare)
    assert workspace < compare < expand < detail


def test_summary_prioritizes_main_decision_and_single_next_step() -> None:
    summary = (ROOT / "ScannerDecisionSummary.tsx").read_text(encoding="utf-8")
    panel = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    assert 'className="scanner-ux5-next"' in summary
    assert 'className="scanner-ux5-caution"' in summary
    assert 'view.missingConditions.map((condition, index)' in summary
    assert 'candidate.risk.warning || view.asOfPrice.state === "OUT_OF_RANGE"' in summary
    assert "조건 현황" in summary
    assert 'variant="summary"' in panel
    assert '<div className="scanner-ux3-statuses">' in panel
    assert 'className="scanner-ux3-prices"' in panel
    assert "scanner-ux3-guide" not in panel
    assert 'className="scanner-ux-decision-facts scanner-ux2-facts"' not in summary


def test_action_footer_has_full_width_buttons_without_dropping_callbacks() -> None:
    panel = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    css = (ROOT / "scannerUX.css").read_text(encoding="utf-8")
    assert 'className="scanner-selected-action scanner-ux5-action"' in panel
    assert 'className="scanner-ux5-primary-action" onClick={onAnalyze}' in panel
    assert 'className="scanner-ux5-secondary-action" onClick={onOpenHoldings}' in panel
    assert "min-height: 44px" in css
    assert ".scanner-workspace .scanner-ux5-action .scanner-selected-action-buttons.simplified" in css
    assert "@media (max-width: 520px)" in css
    assert "expanded-candidates" in css
    assert "overflow-y: auto" not in css[css.index("/* SC-UX4-S2:"):]


def test_changes_leave_baseline_and_jev_provider_disabled() -> None:
    panel = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    api = Path("backend/app/api/backtest.py").read_text(encoding="utf-8")
    jev = Path("backend/app/api/jev.py").read_text(encoding="utf-8")
    assert "createScannerJob(request)" in panel
    assert "getJevReviews(captureId)" in panel
    assert "readActiveDataTask()" in panel
    assert "<ScannerRankComparison result={result} />" in panel
    assert 'result["execution_mode"] = "BASELINE_ONLY"' in api
    assert '"available": False' in jev
