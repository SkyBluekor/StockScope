from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_strategy_operations_is_integrated_without_new_top_level_tab():
    workspace = (
        ROOT / "src/components/SimulationWorkspace.tsx"
    ).read_text(encoding="utf-8")
    panel = (
        ROOT / "src/components/StrategyOperationsPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "StrategyOperationsPanel" in workspace
    assert "<StrategyOperationsPanel" in workspace
    assert "전략 운영" in panel
    assert "운영 변경 잠금" in panel
    assert "승격·강등 수치 기준(Q7)" in panel
    assert "최근 검증 결과가 자동으로 운영 전략을 바꾸지는 않습니다." in panel
    assert 'setMode("governance")' not in workspace
    assert '>전략 운영</button>' not in workspace


def test_scanner_version_is_server_owned_not_frontend_hardcoded():
    workspace = (
        ROOT / "src/components/SimulationWorkspace.tsx"
    ).read_text(encoding="utf-8")

    assert "PRODUCTION_SCANNER_VERSION" not in workspace
    assert 'const PRODUCTION_SCANNER_VERSION = "0.21.3.7"' not in workspace
    assert "governanceOverview?.scanner_baseline.scanner_version" in workspace
    assert "getStrategyGovernanceOverview" in workspace


def test_strategy_governance_client_preserves_explicit_mutation_contracts():
    text = (
        ROOT / "src/services/strategyGovernanceApi.ts"
    ).read_text(encoding="utf-8")

    for token in [
        "/api/simulation/strategy-governance/overview",
        "/api/simulation/strategy-governance/registry",
        "/api/simulation/strategy-governance/evidence",
        "/api/simulation/strategy-governance/proposals",
        "/api/simulation/strategy-governance/approvals",
        "/api/simulation/strategy-governance/production-policy",
        "approval_artifact_id",
        "expected_active_policy_id",
    ]:
        assert token in text

    assert "postJson({ strategies" not in text


def test_strategy_operations_style_is_editorial_not_card_grid():
    text = (ROOT / "src/simulation.css").read_text(encoding="utf-8")

    assert ".sim-strategy-ops" in text
    assert ".sim-strategy-ops-strip" in text
    assert "linear-gradient" not in text
