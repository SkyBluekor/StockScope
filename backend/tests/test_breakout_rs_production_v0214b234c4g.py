from __future__ import annotations

from pathlib import Path

from app.backtest.scanner_quality.strategy_integrity_audit import (
    BREAKOUT_RS_CONDITION,
    _breakout_rs_definition_from_source,
)


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "app" / "strategy" / "engine.py"
SCANNER = ROOT / "app" / "backtest" / "scanner.py"
AUDIT = ROOT / "app" / "backtest" / "scanner_quality" / "strategy_integrity_audit.py"
FRONTEND_SESSION = ROOT.parent / "frontend" / "src" / "components" / "scannerSession.ts"


def test_c4g_production_breakout_definition_is_10_plus_8() -> None:
    definition = _breakout_rs_definition_from_source(ENGINE)
    assert definition is not None
    assert definition["condition_label"] == BREAKOUT_RS_CONDITION
    assert definition["market_weights"] == [10.0]
    assert definition["weights"] == [8.0]
    assert definition["duplicate_count"] == 1
    assert definition["predicate_equivalent"] is True


def test_c4g_scanner_cache_and_frontend_persistence_match_current_contract() -> None:
    scanner = SCANNER.read_text(encoding="utf-8")
    frontend = FRONTEND_SESSION.read_text(encoding="utf-8")
    assert 'VERSION = "0.21.3.7"' in scanner
    assert "SCANNER_DECISION_VERSION" not in frontend
    assert "SCANNER_SESSION_SCHEMA_VERSION = 1" in frontend
    assert "algorithm version belongs to the" in frontend


def test_c4g_audit_has_strict_production_gate_and_temporal_gate() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    assert 'AUDIT_VERSION = "v0.21.4-B.2.3.4c.4g"' in source
    assert "c.4g expects Production Breakout market 10 + exactly one sector 8" in source
    assert '"historical_sector_activation_allowed": False' in source
    assert '"future_boundary_violations": sector_future_violations' in source
