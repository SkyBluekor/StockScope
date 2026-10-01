from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_macro_reference_frontend_uses_separate_read_only_client():
    client = (
        ROOT / "frontend/src/services/macroReferenceApi.ts"
    ).read_text(encoding="utf-8")

    assert "MacroReferenceDiagnosticResponse" in client
    assert "MacroReferenceHorizon" in client
    assert "fetchMacroReferenceDiagnostic" in client
    assert "/api/macro/reference-diagnostic" in client
    assert "delta_bp_1obs" in client
    assert "delta_bp_5obs" in client
    assert "delta_bp_10obs" in client
    assert "observation_refs:" not in client
    assert 'projection_mode: "AS_OF"' in client
    assert 'reference_adequacy: "UNRESOLVED"' in client
    assert 'rate_spike_state: "UNCALIBRATED"' in client


def test_macro_reference_loading_does_not_block_market_dashboard():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "loadMacroReference" in app
    assert "void loadMacroReference();" in app
    assert "const result = await fetchMarketDashboard();" in app
    assert "fetchMacroReferenceDiagnostic" in app
    assert 'setMacroReferenceError("금리 참고 데이터가 아직 준비되지 않았습니다.")' in app
    assert "setDashboardError" not in app[
        app.index("async function loadMacroReference"):
        app.index("async function loadDashboard")
    ]


def test_market_overview_exposes_only_descriptive_macro_reference():
    panel = (
        ROOT / "frontend/src/components/MarketOverviewWorkspace.tsx"
    ).read_text(encoding="utf-8")

    assert "미국 10년물 최근 변화" in panel
    assert "1관측 변화" in panel
    assert "5관측 변화" in panel
    assert "10관측 변화" in panel
    assert "금리 데이터 기준" in panel
    assert "급등 여부를 판정하는 기준은 아직 확정되지 않았습니다." in panel
    assert "current_feature_value" in panel

    for forbidden in (
        "ecdf_sup_drift_from_previous",
        "normalized_median_shift_from_previous",
        "relative_mad_change_from_previous",
        "diagnostic_hash",
        "observation_refs_hash",
        "신뢰도",
        "안전합니다",
        "위험합니다",
        "정상입니다",
    ):
        assert forbidden not in panel


def test_macro_reference_ui_keeps_editorial_non_signal_style():
    css = (ROOT / "frontend/src/styles.css").read_text(encoding="utf-8")
    start = css.index(".macro-reference-inline")
    section = css[start:start + 4200]

    assert ".macro-reference-values" in section
    assert "border-top: 1px solid var(--line-soft)" in section
    assert "font-variant-numeric: tabular-nums" in section
    assert "linear-gradient" not in section
    assert "box-shadow" not in section
