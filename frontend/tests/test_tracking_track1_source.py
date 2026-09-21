from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tracking_embeds_scanner_plus_manual_search_plus_visible_list():
    tracking = (ROOT / "src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    embedded = (ROOT / "src/components/EmbeddedScanner.tsx").read_text(encoding="utf-8")
    api = (ROOT / "src/services/trackingApi.ts").read_text(encoding="utf-8")
    assert 'import EmbeddedScanner from "./EmbeddedScanner"' in tracking
    assert "<EmbeddedScanner />" in tracking
    assert "Scanner 후보를 찾거나" in tracking
    assert "원하는 종목 직접 찾기" in tracking
    assert "searchStocks" in tracking
    assert "최근 추천 후보" in tracking
    assert "candidates.map" in tracking
    assert "candidates.slice" not in tracking
    assert "more_candidates" in tracking
    assert "후보 찾기" in embedded
    assert "createScannerJob" in embedded
    assert "fetchBacktestJob" in embedded
    assert "commitScannerSession" in embedded
    assert "추적 중인 종목과 기록" in tracking
    assert "deleteTrackedRecommendation" in tracking
    assert 'method: "DELETE"' in api


def test_tracking_subscribes_to_reactive_scanner_session():
    tracking = (ROOT / "src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    session = (ROOT / "src/components/scannerSession.ts").read_text(encoding="utf-8")
    assert "useScannerSession()" in tracking
    assert "useSyncExternalStore" in session
    assert "SCANNER_SESSION_SCHEMA_VERSION" in session
    assert "commitScannerSession" in session
    assert "0.21.3.6" not in session


def test_tracking_css_uses_existing_theme_tokens():
    css = (ROOT / "src/tracking.css").read_text(encoding="utf-8")
    assert "var(--accent-primary" in css
    assert "var(--text-muted" in css
    assert ".tracking-embedded-scanner" in css
    assert "linear-gradient" not in css
