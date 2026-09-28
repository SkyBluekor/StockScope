from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_p6_event_evidence_uses_separate_read_only_frontend_contract():
    api = (ROOT / "src/services/api.ts").read_text(encoding="utf-8")
    panel = (ROOT / "src/components/StockNewsPanel.tsx").read_text(encoding="utf-8")

    assert "StockEventEvidenceResponse" in api
    assert "fetchStockEventEvidence" in api
    assert "/event-evidence?" in api
    assert "fetchStockEventEvidence" in panel
    assert "evidenceError" in panel
    assert "evidenceLoading" in panel
    assert "뉴스·이벤트 근거 범위 보기" in panel
    assert "검증된 이벤트 근거 없음 · 방향 예측 미제공" in panel
    assert "주가 방향 예측은 아직 검증되지 않아 제공하지 않습니다." in panel
    assert "예측·확률·Strategy 점수로 자동 변환하지 않습니다." in panel


def test_p6_product_status_is_not_requested_from_compact_scanner_or_holdings_views():
    panel = (ROOT / "src/components/StockNewsPanel.tsx").read_text(encoding="utf-8")
    holdings = (ROOT / "src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")
    scanner = (ROOT / "src/components/ScannerPanel.tsx").read_text(encoding="utf-8")

    assert "if (compact)" in panel
    assert "} else {" in panel
    assert "fetchStockEventEvidence" in panel
    assert 'variant="compact"' in holdings
    assert 'variant="compact"' in scanner


def test_p6_ui_does_not_add_prediction_badges_or_new_event_panel():
    panel = (ROOT / "src/components/StockNewsPanel.tsx").read_text(encoding="utf-8")
    css = (ROOT / "src/stock-analysis.css").read_text(encoding="utf-8")

    assert "EventEvidencePanel" not in panel
    assert "PredictionCard" not in panel
    assert "stock-news-evidence-state" in css
    assert "stock-news-evidence-detail-list" in css
    assert "linear-gradient" not in css[css.index("/* VN-P6-S1-G"):]


def test_news_and_event_evidence_errors_are_independent():
    panel = (ROOT / "src/components/StockNewsPanel.tsx").read_text(encoding="utf-8")

    assert "setError(" in panel
    assert "setEvidenceError(" in panel
    assert "최근 뉴스만 불러오지 못했습니다." in panel
    assert "이벤트 근거 상태를 현재 확인하지 못했습니다." in panel
    assert "최근 뉴스와 기존 종목 분석은 계속 이용할 수 있습니다." in panel
