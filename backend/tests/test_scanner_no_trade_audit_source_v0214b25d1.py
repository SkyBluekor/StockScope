from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_runner():
    path = Path(__file__).resolve().parents[1] / "tools" / "run_scanner_no_trade_audit.py"
    spec = importlib.util.spec_from_file_location("run_scanner_no_trade_audit_b25d1", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_explicit_input_wins(tmp_path):
    module = _load_runner()
    explicit = tmp_path / "manual.json"
    explicit.write_text("{}", encoding="utf-8")
    source, mode = module.resolve_source(explicit)
    assert source == explicit
    assert mode == "EXPLICIT_INPUT"


def test_bundled_baseline_fallback_when_no_local(monkeypatch, tmp_path):
    module = _load_runner()
    backend = tmp_path / "backend"
    project = tmp_path
    baseline = backend / "runtime" / "quality_audit" / "no_trade" / "source" / "scanner-strategy-audit_b25d-baseline-80d.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(module, "BACKEND_ROOT", backend)
    monkeypatch.setattr(module, "PROJECT_ROOT", project)
    monkeypatch.setattr(module, "BUNDLED_BASELINE", baseline)

    source, mode = module.resolve_source(None)
    assert source == baseline
    assert mode == "BUNDLED_BASELINE_80D"


def test_local_history_beats_bundled_baseline(monkeypatch, tmp_path):
    module = _load_runner()
    backend = tmp_path / "backend"
    project = tmp_path
    local = backend / "runtime" / "quality_audit" / "strategy" / "scanner-strategy-audit_20260920-130000.json"
    local.parent.mkdir(parents=True)
    local.write_text("{}", encoding="utf-8")
    baseline = backend / "runtime" / "quality_audit" / "no_trade" / "source" / "scanner-strategy-audit_b25d-baseline-80d.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(module, "BACKEND_ROOT", backend)
    monkeypatch.setattr(module, "PROJECT_ROOT", project)
    monkeypatch.setattr(module, "BUNDLED_BASELINE", baseline)

    source, mode = module.resolve_source(None)
    assert source == local
    assert mode == "LOCAL_HISTORY"
