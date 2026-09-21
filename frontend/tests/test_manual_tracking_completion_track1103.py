from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "frontend" / "src" / "components" / "RecommendationTracking.tsx"
CSS = ROOT / "frontend" / "src" / "tracking.css"


def source() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_manual_tracking_preview_shows_confirmed_reference_and_lifecycle_state():
    text = source()
    assert "확정 종가 ·" in text
    assert "selectedManualActive" in text
    assert "selectedManualSameDayClosed" in text
    assert "다음 거래일부터 가능" in text
    assert "새로운 확정 거래일이 생긴 뒤 다시 추적할 수 있습니다." in text


def test_manual_tracking_add_keeps_search_context_and_updates_rows_immediately():
    text = source()
    assert "setRows((current) => upsertTrackedRow(current, response.item))" in text
    assert "이미 직접 추적 중입니다." in text
    # TRACK.1.10.2 used to clear the search immediately after an add. Keeping
    # it visible lets the same result render as '추적 중' without a reload.
    assert 'setManualRows([]); setManualSelected(null); setManualPreview(null); setManualQuery("");' not in text


def test_tracking_management_labels_are_explicit():
    text = source()
    assert ">최신 반영</button>" in text
    assert ">추적 종료</button>" in text
    assert ">기록 삭제</button>" in text
    assert "현재가</dt>" in text
    assert "현재 성과</dt>" in text


def test_manual_completion_css_keeps_management_actions_readable():
    text = CSS.read_text(encoding="utf-8")
    assert "TRACK.1.10.3" in text
    assert ".tracking-manual-policy-note" in text
    assert "min-width:180px" in text
