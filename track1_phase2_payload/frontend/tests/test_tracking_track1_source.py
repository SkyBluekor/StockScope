from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_tracking_workspace_source_contract():
    tracking = (ROOT / "src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    shell = (ROOT / "src/components/TrackingWorkspace.tsx").read_text(encoding="utf-8")
    api = (ROOT / "src/services/trackingApi.ts").read_text(encoding="utf-8")
    assert "추천 추적" in tracking
    assert "추적 추가" in tracking
    assert "최신 데이터 반영" in tracking
    assert "readScannerSession" in tracking
    assert "과거 전략 검증" in shell
    assert "/api/tracking/recommendations" in api
