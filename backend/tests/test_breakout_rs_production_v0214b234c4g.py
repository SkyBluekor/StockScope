from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "tools" / "apply_c4g_breakout_rs_production_fix.py"
SCANNER = ROOT / "app" / "backtest" / "scanner.py"
AUDIT = ROOT / "app" / "backtest" / "scanner_quality" / "strategy_integrity_audit.py"
FRONTEND_SESSION = ROOT.parent / "frontend" / "src" / "components" / "scannerSession.ts"


def _load_patcher():
    spec = importlib.util.spec_from_file_location("c4g_patcher", PATCHER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_engine_source() -> str:
    return '''\nclass StrategyEngine:\n    def _breakout(self, d):\n        return self._evaluate("breakout", d, [\n            ("20일 고점과 2% 이내", 20, lambda x: True),\n            ("20일 시장 대비 상대강도 양호", 6, lambda x: x.relative_strength_market_pct is not None and x.relative_strength_market_pct > 0),\n            ("20일 업종 대비 상대강도 양호", 4, lambda x: (x.relative_strength_sector_pct > 0) if x.relative_strength_sector_pct is not None else (x.relative_strength_market_pct is not None and x.relative_strength_market_pct > 0)),\n            ("20일 업종 대비 상대강도 양호", 8, lambda x: (x.relative_strength_sector_pct > 0) if x.relative_strength_sector_pct is not None else (x.relative_strength_market_pct is not None and x.relative_strength_market_pct > 0)),\n            ("상승 시장", 5, lambda x: True),\n        ])\n'''


def test_c4g_patcher_converts_legacy_definition_and_is_idempotent(tmp_path: Path) -> None:
    module = _load_patcher()
    engine = tmp_path / "engine.py"
    engine.write_text(_legacy_engine_source(), encoding="utf-8")
    assert module.patch_engine(engine) == "patched"
    result = module._definition(engine.read_text(encoding="utf-8"))
    assert module._weights(result["market"]) == [10.0]
    assert module._weights(result["sector"]) == [8.0]
    assert module.patch_engine(engine) == "already-applied"


def test_c4g_patcher_rejects_unknown_strategy_shape(tmp_path: Path) -> None:
    module = _load_patcher()
    engine = tmp_path / "engine.py"
    engine.write_text(_legacy_engine_source().replace('"20일 시장 대비 상대강도 양호", 6', '"20일 시장 대비 상대강도 양호", 7'), encoding="utf-8")
    try:
        module.patch_engine(engine)
    except RuntimeError as exc:
        assert "Refusing to patch unexpected" in str(exc)
    else:
        raise AssertionError("unexpected strategy shape must fail closed")


def test_c4g_scanner_and_frontend_cache_versions_are_bumped() -> None:
    scanner = SCANNER.read_text(encoding="utf-8")
    frontend = FRONTEND_SESSION.read_text(encoding="utf-8")
    assert 'VERSION = "0.21.3.5"' in scanner
    assert 'SCANNER_DECISION_VERSION = "0.21.3.5"' in frontend


def test_c4g_audit_has_strict_production_gate_and_temporal_gate() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    assert 'AUDIT_VERSION = "v0.21.4-B.2.3.4c.4g"' in source
    assert "c.4g expects Production Breakout market 10 + exactly one sector 8" in source
    assert '"historical_sector_activation_allowed": False' in source
    assert '"future_boundary_violations": sector_future_violations' in source
