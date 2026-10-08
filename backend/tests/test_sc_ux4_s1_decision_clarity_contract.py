"""SC-UX4-S1: scanner decision UI must expose real missing facts without changing policy."""
from pathlib import Path

ROOT = Path("frontend/src/components")


def test_sc_ux4_asof_decision_facts_and_no_fabricated_missing_conditions() -> None:
    presenter = (ROOT / "scannerDecisionPresentation.ts").read_text(encoding="utf-8")
    summary = (ROOT / "ScannerDecisionSummary.tsx").read_text(encoding="utf-8")
    scanner = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    assert '전체 투자 조건 " + total + "개 중 " + passed + "개를 충족했어요.' in presenter
    assert "missingConditionDetails(candidate)" in presenter
    assert 'firstMissing?.label ?? "부족한 조건의 상세 정보 없음"' in presenter
    assert 'headline: "분석일 기준 진입 조건을 모두 충족했어요."' in presenter
    assert "if (blocked)" in presenter and "if (missing > 0)" in presenter
    assert presenter.index("if (blocked)") < presenter.index("if (missing > 0)")
    assert "if (items.length >= 3) break" in presenter
    assert 'view.missingConditions.map((condition, index)' in summary
    assert "{condition.current}" in summary
    assert "{condition.required}" in summary
    assert 'view.missingConditions.length < view.missingCount' in summary
    assert "{view.nextActionLabel}" in scanner
    assert "{view.nextActionContext}" in scanner
    assert 'className="scanner-ux4-missing"' in summary


def test_sc_ux4_disabled_provider_is_not_an_active_ui_toggle() -> None:
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    status = (ROOT / "scannerAiReviewStatus.ts").read_text(encoding="utf-8")
    server = Path("backend/app/api/jev.py").read_text(encoding="utf-8")
    scanner_backend = Path("backend/app/api/backtest.py").read_text(encoding="utf-8")
    assert 'disabled={jevFeatureLoading || jevFeatureError' in app
    assert '"미제공"' in app
    assert '"상태 확인 실패"' in app
    assert '"STATUS_LOADING"' in app and '"STATUS_ERROR"' in app
    assert 'setJevFeatureError(true)' in app
    assert 'setJevFeatureLoading(false)' in app
    assert 'label: "AI 검토 미제공"' in status
    assert 'state: "FEATURE_LOADING"' in status
    assert 'state: "FEATURE_ERROR"' in status
    assert '"available": False' in server
    assert 'result["execution_mode"] = "BASELINE_ONLY"' in scanner_backend
    assert "requestJevReview(" not in app
    assert "requestJevReview(" not in (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")


def test_sc_ux4_preserves_scanner_registration_recovery_and_jev_read_only_paths() -> None:
    scanner = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    quote = (ROOT / "ScannerPriceStatus.tsx").read_text(encoding="utf-8")
    assert "createScannerJob(request)" in scanner
    assert "registerHeldStock({" in scanner
    assert "addWatchStock({" in scanner
    assert "readActiveDataTask()" in scanner
    assert "getJevReviews(captureId)" in scanner
    assert '<ScannerRankComparison result={result} />' in scanner
    assert "onPrepareEvidence={() => void prepareCandidateEvidence(selectedCandidate)}" in scanner
    assert 'onClick={() => void checkPrice()}' in quote
    assert "assessPriceRule(priceRule, candidate.current_price)" in quote
