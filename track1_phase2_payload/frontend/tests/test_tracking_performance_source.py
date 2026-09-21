from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tracking_performance_ui_contract():
    text = (ROOT / "src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    for token in [
        "최신 데이터 반영", "현재", "최대 상승", "최대 하락", "5D", "10D", "20D",
        "진입 참고가", "손절 참고가", "1차 목표", "2차 목표", "추적 종료", "가격 대기",
    ]:
        assert token in text
    assert "MFE" not in text
    assert "MAE" not in text


def test_tracking_api_has_refresh_contracts():
    text = (ROOT / "src/services/trackingApi.ts").read_text(encoding="utf-8")
    assert '"/api/tracking/recommendations/refresh"' in text
    assert "/refresh`" in text
    assert "RecommendationPerformance" in text


def test_tracking_css_remains_table_first_and_responsive():
    text = (ROOT / "src/tracking.css").read_text(encoding="utf-8")
    assert ".tracking-table" in text
    assert ".tracking-detail-grid" in text
    assert "@media" in text
    assert "linear-gradient" not in text


def test_historical_validation_copy_is_reclassified():
    text = (ROOT / "src/components/SimulationWorkspace.tsx").read_text(encoding="utf-8")
    assert "검증 기간 설정" in text
    assert "과거 확정 일봉으로 전략의 매수·매도 결과를 검증합니다." in text
    assert "시뮬레이션 기간 설정" not in text
