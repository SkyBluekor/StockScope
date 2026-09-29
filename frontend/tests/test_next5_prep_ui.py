from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_prospective_readiness_explains_why_policy_decision_is_blocked():
    panel = (
        ROOT / "src/components/ProspectiveEvaluationPanel.tsx"
    ).read_text(encoding="utf-8")
    client = (ROOT / "src/services/prospectiveApi.ts").read_text(encoding="utf-8")

    assert "근거 축적 상태" in panel
    assert "정책 판정 보류" in panel
    assert "정상 완료된 실제 추천 수집이 아직 없습니다." in panel
    assert "PARTIAL·실패·중지 기록은 보존하지만 평가 표본으로 사용하지 않습니다." in panel
    assert "최근 확인 필요" in panel
    assert "captureReasonText" in panel

    assert "evidence_accumulation" in client
    assert "recent_attention" in client
    assert "policy_criteria_defined: false" in client


def test_prospective_readiness_does_not_invent_policy_thresholds():
    panel = (
        ROOT / "src/components/ProspectiveEvaluationPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "최소 표본·승격/강등 기준은 아직 정의되지 않았습니다." in panel
    assert "30건이면" not in panel
    assert "자동 승격" not in panel
    assert "자동 강등" not in panel


def test_prospective_readiness_uses_editorial_status_layout():
    css = (ROOT / "src/simulation.css").read_text(encoding="utf-8")

    assert ".sim-prospective-readiness" in css
    assert ".sim-prospective-attention" in css
    assert "overflow-wrap: anywhere" in css


def test_scanner_structural_history_limit_is_explained_without_prepare_cta():
    panel = (
        ROOT / "src/components/ScannerPanel.tsx"
    ).read_text(encoding="utf-8")
    client = (ROOT / "src/services/api.ts").read_text(encoding="utf-8")

    assert "INSUFFICIENT_AVAILABLE_HISTORY" in panel
    assert "최근 3년 검증 제한" in panel
    assert "사용 가능한 종목 이력 부족" in panel
    assert "현재 후보 판단·Risk·순위에는 영향을 주지 않습니다." in panel
    assert "if (evidence.preparation_available != null) return evidence.preparation_available;" in panel

    assert "INSUFFICIENT_AVAILABLE_HISTORY" in client
