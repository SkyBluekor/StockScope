from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_simulation_workspace_has_core_user_actions():
    text = (ROOT / "src/components/SimulationWorkspace.tsx").read_text(encoding="utf-8")
    for token in ["Simulation 시작하기", "+ 종목 매수", "다음 거래일 →", "가상 매수", "매도"]:
        assert token in text


def test_simulation_workspace_uses_real_api_layer_not_mock_data():
    text = (ROOT / "src/components/SimulationWorkspace.tsx").read_text(encoding="utf-8")
    assert "../services/simulationApi" in text
    assert "setTimeout(" not in text
    assert "mock" not in text.lower()


def test_simulation_api_targets_api_simulation_routes():
    text = (ROOT / "src/services/simulationApi.ts").read_text(encoding="utf-8")
    assert '"/api/simulation/portfolios"' in text
    assert "/next-day" in text
    assert "/position-marks" in text


def test_simulation_css_consumes_existing_theme_tokens():
    text = (ROOT / "src/simulation.css").read_text(encoding="utf-8")
    assert "var(--bg-surface)" in text
    assert "var(--text-primary)" in text
    assert "var(--accent-primary)" in text
    assert "#fff" in text  # action text only
    assert "linear-gradient" not in text
