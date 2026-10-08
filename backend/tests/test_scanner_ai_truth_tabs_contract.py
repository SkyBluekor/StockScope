"""Scanner P0/P1: independent AI truth and short tabbed candidate review."""
from pathlib import Path

ROOT = Path("frontend/src/components")


def test_scanner_tabs_keep_default_summary_small() -> None:
    scanner = (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    assert 'useState<"summary" | "strategy" | "ai" | "history" | "news">("summary")' in scanner
    assert 'role="tablist"' in scanner
    assert 'role="tabpanel"' in scanner
    for tab in ('"summary"', '"strategy"', '"ai"', '"history"', '"news"'):
        assert 'activeTab === ' + tab in scanner
    assert 'variant="summary"' in scanner
    assert 'variant="compact"' in scanner
    assert 'className="scanner-ux3-summary"' in scanner
    assert 'className="scanner-ux3-statuses"' in scanner
    assert 'historicalReviewStatus(candidate)' in scanner
    assert 'matchStoredJevReview(item, candidate, captureId, index)' in scanner
    assert 'requestJevReview(' not in scanner
    assert 'className="scanner-decision-workspace"' in scanner

    list_pos = scanner.index('className="scanner-compare-panel"', scanner.index('className="scanner-decision-workspace"'))
    rank_pos = scanner.index("<ScannerRankComparison result={result} />", list_pos)
    detail_pos = scanner.index("<CandidateDetail", rank_pos)
    assert list_pos < rank_pos < detail_pos


def test_scanner_ai_uses_local_evidence_distinct_from_model() -> None:
    ai = (ROOT / "scannerAiReviewStatus.ts").read_text(encoding="utf-8")
    panel = (ROOT / "ScannerAiReview.tsx").read_text(encoding="utf-8")
    progress = (ROOT / "AiReviewProgress.tsx").read_text(encoding="utf-8")
    server = Path("backend/app/jev/review_presentation.py").read_text(encoding="utf-8")

    assert 'provider_status": "NOT_REQUESTED"' in server
    assert 'provider_result": None' in server
    assert 'review.integrity_status === "MATCHED"' in ai
    assert 'review.model_identity_status === "MATCHED"' in ai
    assert 'record.capture_id === captureId' in ai
    assert 'record.sample_index === sampleIndex' in ai
    assert 'record.ticker === candidate.code' in ai
    assert 'record.market === candidate.market' in ai
    assert 'getJevReviews(captureId)' in (ROOT / "ScannerPanel.tsx").read_text(encoding="utf-8")
    assert '새로운 Jev 모델 호출은 실행하지 않습니다.' in panel
    assert 'scannerAiReviewStatus' in progress
    assert 'progress.provider_required === 0' not in progress
    assert 'AI 분석 완료' not in progress
    assert 'AI 검토 기능 준비 중' in ai


def test_scanner_summary_news_has_two_article_limit() -> None:
    news = (ROOT / "StockNewsPanel.tsx").read_text(encoding="utf-8")
    assert 'variant?: "full" | "compact" | "summary"' in news
    assert 'variant === "summary" ? 2' in news
    assert 'variant !== "summary" && (news?.count ?? 0) > collapsedLimit' in news


def test_scanner_backtest_keeps_provider_disabled_by_default() -> None:
    api = Path("backend/app/api/backtest.py").read_text(encoding="utf-8")
    jev = Path("backend/app/api/jev.py").read_text(encoding="utf-8")
    service = Path("backend/app/jev/review_service.py").read_text(encoding="utf-8")
    assert 'result["execution_mode"] = "BASELINE_ONLY"' in api
    assert 'result["jev_review"] = {' in api
    assert 'JEV_USER_FEATURE_DISABLED' in jev
    assert '"available": False' in jev
    assert "if self.feature_status != JEV_USER_FEATURE_ACTIVE:" in service
    assert "if self.provider_override is None:" in service
