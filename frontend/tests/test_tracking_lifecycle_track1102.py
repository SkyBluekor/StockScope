from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tracking_updates_rows_immediately_after_add_and_close():
    source = (ROOT / "src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    assert "function upsertTrackedRow" in source
    assert "setRows((current) => upsertTrackedRow(current, response.item))" in source
    assert "setRows((current) => upsertTrackedRow(current, updated))" in source
    assert "현재 확보된 거래일까지의 성과가 고정됩니다." in source


def test_tracking_candidate_state_distinguishes_active_and_closed():
    source = (ROOT / "src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    assert "scannerTrackingStatus" in source
    assert 'trackedStatus === "ACTIVE" ? "추적 중"' in source
    assert 'trackedStatus === "CLOSED" ? "추적 종료됨"' in source


def test_tracking_filters_show_counts_and_active_rows_sort_first():
    source = (ROOT / "src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    assert "const sourceCounts" in source
    assert "const statusCounts" in source
    assert "sourceCounts[value]" in source
    assert "statusCounts[value]" in source
    assert 'if (a.status !== b.status) return a.status === "ACTIVE" ? -1 : 1' in source


def test_tracking_waiting_state_and_delete_warning_are_explicit():
    source = (ROOT / "src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    assert "다음 거래일부터 성과가 계산됩니다." in source
    assert "Scanner 추천 성과 분석 자료에 사용될 수 있습니다." in source
    assert "추천 당시 정보와 누적 성과도 함께 삭제" in source
    assert "새로운 확정 거래일이 없습니다." in source


def test_tracking_empty_state_tells_user_how_to_start():
    source = (ROOT / "src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    assert "아직 추적 중인 종목이 없습니다." in source
    assert "추천 후보를 선택하거나 원하는 종목을 직접 추가" in source


def test_tracking_lifecycle_css_is_compact_and_uses_tokens():
    css = (ROOT / "src/tracking.css").read_text(encoding="utf-8")
    assert "TRACK.1.10.2" in css
    assert ".tracking-waiting-note" in css
    assert "var(--accent-primary" in css
    assert "linear-gradient" not in css
