from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "app" / "backtest" / "scanner_quality" / "strategy_integrity_audit.py"
RUNNER = ROOT / "tools" / "run_scanner_strategy_integrity_audit.py"


def test_audit_passes_prefetched_sector_input_into_signal_snapshot() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    assert 'AUDIT_VERSION = "v0.21.4-B.2.3.4c.4g"' in source
    assert "sector_prefetcher.prepare(" in source
    assert "sector_input=sector_inputs.get(code)" in source
    assert 'snapshot.get("sector_input_audit")' in source
    assert '"sector_20d_available"' in source
    assert '"future_boundary_violations"' in source
    assert '"production_activation_allowed"' in source


def test_live_sector_audit_is_explicit_opt_in_and_static_current_is_not_production() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert '"--sector-rs-audit-live"' in source
    assert "OpenDartProvider" in source
    assert "sector_company_provider=dart" in source
    assert "STATIC_CURRENT" in source
    assert "Production strategy input is not activated" in source
