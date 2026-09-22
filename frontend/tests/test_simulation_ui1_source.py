from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def workspace_text() -> str:
    return (ROOT / "src/components/SimulationWorkspace.tsx").read_text(encoding="utf-8")


def test_historical_validation_has_explicit_draft_and_saved_management():
    text = workspace_text()
    assert "새 검증" in text
    assert "저장된 검증" in text
    assert "+ 새 검증" in text
    assert "검증 이름" in text
    assert "Production Scanner" in text
    assert "설정 저장" in text
    assert "열기" in text and "삭제" in text
    assert "stockscope-simulation-portfolio" not in text
    assert "localStorage" not in text


def test_validation_period_uses_presets_month_inputs_and_60_trading_days():
    text = workspace_text()
    for token in ["최근 6개월", "최근 1년", "최근 2년", "직접 선택", 'type="month"', "최소 60 실제 거래일", "검증 대상"]:
        assert token in text
    assert 'type="date"' not in text
    assert "시작 거래일" not in text
    assert "시뮬레이션 기간 설정" not in text


def test_legacy_is_explicitly_separate_and_manageable():
    text = workspace_text()
    assert "이전 수동 Simulation" in text
    assert "정보 없음" in text
    assert "자동 활성화" in text
    assert "removeLegacy" in text


def test_simulation_api_exposes_draft_and_delete_contracts():
    text = (ROOT / "src/services/simulationApi.ts").read_text(encoding="utf-8")
    for token in [
        "/api/simulation/validation-periods/preview",
        "/api/simulation/validations",
        "/api/simulation/validations/${encodeURIComponent(id)}/run",
        "/api/simulation/validations/${encodeURIComponent(id)}/cancel",
        "/api/simulation/validations/${encodeURIComponent(id)}/days",
        "/api/simulation/legacy-validations",
        "createValidationDraft",
        "runValidationReplay",
        "cancelValidationReplay",
        "listValidationDays",
        "deleteValidationDraft",
        "deleteLegacyValidation",
    ]:
        assert token in text


def test_historical_validation_exposes_replay_lifecycle_without_execution_simulation():
    text = workspace_text()
    for token in ["과거 Scanner 재생 시작", "이어 실행", "중지", "재생 중…", "processed_day_count", "candidate_count", "runtime_active"]:
        assert token in text
    assert "검증 실행 · 준비 중" not in text
    assert "D 신호 → D+1 체결" not in text
    assert "Gap·Slippage" not in text
    assert "buySimulationPosition" not in text
    assert "sellSimulationPosition" not in text


def test_simulation_css_consumes_existing_theme_tokens_without_gradients():
    text = (ROOT / "src/simulation.css").read_text(encoding="utf-8")
    assert "var(--bg-surface)" in text
    assert "var(--text-primary)" in text
    assert "var(--accent-primary)" in text
    assert "linear-gradient" not in text
