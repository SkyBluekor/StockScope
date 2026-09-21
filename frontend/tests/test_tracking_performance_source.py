from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tracking_performance_ui_contract():
    text = (ROOT / "src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    for token in [
        "최신 데이터 반영", "현재", "최대 상승", "최대 하락", "5D", "10D", "20D",
        "진입 참고", "손절 참고", "1차 목표", "2차 목표", "가격 대기", "판정 불가",
    ]:
        assert token in text
    assert "MFE" not in text
    assert "MAE" not in text


def test_tracking_api_has_source_safe_refresh_contracts():
    text = (ROOT / "src/services/trackingApi.ts").read_text(encoding="utf-8")
    assert '"/api/tracking/items/refresh-active"' in text
    assert "/api/tracking/items/${encodeURIComponent(id)}/refresh" in text
    assert "RecommendationPerformance" in text
    assert "addScannerTrackedItem" in text
    assert "addManualTrackedItem" in text


def test_tracking_css_remains_table_first_and_responsive():
    text = (ROOT / "src/tracking.css").read_text(encoding="utf-8")
    assert ".tracking-table" in text
    assert ".tracking-detail-grid" in text
    assert ".tracking-manual-search" in text
    assert "@media" in text
    assert "linear-gradient" not in text
