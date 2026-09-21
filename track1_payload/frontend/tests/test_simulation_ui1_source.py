from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def workspace_text() -> str:
    return (ROOT / "src/components/SimulationWorkspace.tsx").read_text(encoding="utf-8")


def test_simulation_workspace_has_low_input_user_actions():
    text = workspace_text()
    for token in ["과거 전략 검증 시작", "+ 종목 추가", "종목 찾기 추천에서 추가", "추천 종목", "직접 찾기", "다음 거래일 →", "가상 매수", "매도"]:
        assert token in text


def test_simulation_buy_identity_is_selected_not_free_text_name_code_pair():
    text = workspace_text()
    assert "buyChoice" in text
    assert "searchStocks" in text
    assert "readScannerSession" in text
    assert "getSimulationQuote" in text
    assert "종목명<input" not in text
    assert "종목코드<input" not in text
    assert "buyName" not in text
    assert "buyCode" not in text


def test_simulation_recommendations_are_date_aligned_to_prevent_lookahead():
    text = workspace_text()
    assert "candidate.data_date === session.current_date" in text
    assert "미래 정보를 섞지 않도록 바로 추가를 막았습니다" in text


def test_simulation_workspace_removes_unnecessary_english_section_labels():
    text = workspace_text()
    for token in ["HISTORICAL SIMULATION", "TIMELINE", "POSITIONS", ">BUY<", ">SELL<", "Main Simulation", "Session 시작"]:
        assert token not in text


def test_simulation_workspace_uses_real_api_layer_not_mock_data():
    text = workspace_text()
    assert "../services/simulationApi" in text
    assert "setTimeout(" not in text
    assert "mock" not in text.lower()


def test_simulation_api_targets_api_simulation_routes():
    text = (ROOT / "src/services/simulationApi.ts").read_text(encoding="utf-8")
    assert '"/api/simulation/portfolios"' in text
    assert "/next-day" in text
    assert "/position-marks" in text
    assert "/quote/" in text


def test_simulation_css_consumes_existing_theme_tokens():
    text = (ROOT / "src/simulation.css").read_text(encoding="utf-8")
    assert "var(--bg-surface)" in text
    assert "var(--text-primary)" in text
    assert "var(--accent-primary)" in text
    assert "#fff" in text  # action text only
    assert "linear-gradient" not in text


def test_historical_simulation_is_reclassified_as_research_tool():
    text = workspace_text()
    assert "과거 전략 검증 시작" in text
    assert "과거 전략 검증" in text
    assert "시뮬레이션 시작" not in text
