from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "app" / "backtest" / "scanner_quality" / "strategy_integrity_audit.py"
RUNNER = ROOT / "tools" / "run_scanner_strategy_integrity_audit.py"


def test_c4g_sector_verification_remains_audit_only() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    assert 'AUDIT_VERSION = "v0.21.4-B.2.3.4c.4g"' in source
    assert 'RS_AUDIT_CURRENT = "RS_PRODUCTION_10_8_SECTOR_AWARE"' in source
    assert "_replace_input(data, relative_strength_sector_pct=audit_sector_value)" in source
    assert "sector_evals, resolver = _discover_revaluator" in source
    assert '"historical_sector_activation_authorized": False' in source
    assert "STATIC_CURRENT industry metadata remains audit-only" in source


def test_c4g_acceptance_requires_production_market10_sector8() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    assert "PRODUCTION_MARKET_RS_WEIGHT = 10.0" in source
    assert "EXPECTED_BREAKOUT_RS_WEIGHTS = (8.0,)" in source
    assert 'return "PRODUCTION_10_8"' in source
    assert '"c4g_production_rs_acceptance"' in source
    assert '"PRODUCTION_10_8_CONFIRMED"' in source
    assert '"PRODUCTION_10_8_ACTIVE"' in source


def test_runner_surfaces_c4g_acceptance_without_historical_sector_activation() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "c.4g Sector RS live verification enabled" in source
    assert "c.4g Production RS:" in source
    assert "historicalSectorActivation" in source
    assert "Legacy 6+4+8/KEEP_4/KEEP_8 comparison: not applicable" in source
