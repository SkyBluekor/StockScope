from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_prospective_report_exposes_explicit_p5_evidence_handoff():
    panel = (
        ROOT / "src/components/ProspectiveEvaluationPanel.tsx"
    ).read_text(encoding="utf-8")
    client = (
        ROOT / "src/services/strategyGovernanceApi.ts"
    ).read_text(encoding="utf-8")

    assert "getStrategyEvidenceEligibility" in panel
    assert "createStrategyEvidenceArtifact" in panel
    assert "P5 근거로 등록" in panel
    assert "근거 등록은 승격·강등·Proposal·Production Policy를 자동 실행하지 않습니다." in panel
    assert "strategy_version_id: row.strategy_version_id" in panel

    assert "/api/simulation/strategy-governance/evidence/eligibility" in client
    assert 'source_kind: "PROSPECTIVE_REPORT"' in client
    assert "/api/simulation/strategy-governance/evidence" in client


def test_p5_handoff_is_identity_gated_and_not_an_auto_promotion_ui():
    panel = (
        ROOT / "src/components/ProspectiveEvaluationPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "strategyIdentityLabel" in panel
    assert "row.creation_allowed" in panel
    assert "row.existing_artifact_id" in panel
    assert "최소 표본 기준은 아직 정의되지 않았습니다." in panel
    assert "자동 승격" not in panel
    assert "자동 강등" not in panel


def test_p5_handoff_style_remains_editorial_table_not_card_grid():
    css = (ROOT / "src/simulation.css").read_text(encoding="utf-8")

    assert ".sim-prospective-p5-table" in css
    assert ".sim-prospective-p5-head" in css
    assert "linear-gradient" not in css


def test_p5_evidence_section_remains_visible_before_report_exists():
    panel = (
        ROOT / "src/components/ProspectiveEvaluationPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "아직 등록할 평가 근거가 없습니다." in panel
    assert "평가 Report 없음" in panel
    assert "Prospective 평가가 완료되면 Strategy Version을 확인한 뒤" in panel
    assert "{latestDetail?.report && (" not in panel.split("P5 평가 근거", 1)[0][-120:]
