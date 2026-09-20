from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.baseline.scanner_production_baseline import (
    BASELINE_SCHEMA_VERSION,
    EXPECTED_SCANNER_VERSION,
    BaselineError,
    aggregate_production_fingerprint,
    baseline_id,
    build_manifest,
    detect_scanner_version,
    discover_production_files,
    file_manifest,
    fingerprint_object,
    freeze_baseline,
    policy_fingerprint,
    verify_baseline,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "StockScope"
    _write(root / "backend/app/__init__.py", "")
    _write(root / "backend/app/backtest/__init__.py", "")
    _write(root / "backend/app/core/__init__.py", "")
    _write(root / "backend/app/core/risk.py", "RISK='stable'\n")
    _write(root / "backend/app/core/target.py", "TARGET='CAP_1_5R'\n")
    _write(
        root / "backend/app/backtest/scanner.py",
        "from app.core.risk import RISK\n"
        "from app.core import target\n"
        "class StockScannerService:\n"
        f"    VERSION = '{EXPECTED_SCANNER_VERSION}'\n",
    )
    _write(
        root / "backend/app/backtest/candidate_priority.py",
        "from app.core.target import TARGET\n"
        "def rank_candidates(rows):\n"
        "    return rows\n",
    )
    _write(root / "backend/app/backtest/market_store.py", "class HistoricalMarketStore: pass\n")
    _write(root / "backend/app/settings/scanner.json", '{"mode":"production"}\n')
    _write(root / "backend/app/backtest/scanner_quality/research.py", "SHOULD_NOT_HASH=True\n")
    _write(root / "backend/app/simulation/engine.py", "SHOULD_NOT_HASH=True\n")
    _write(root / "README.md", "non-production\n")
    return root


def _fake_git() -> dict:
    return {
        "available": True,
        "head": "a" * 40,
        "branch": "main",
        "working_tree_dirty": True,
        "status_porcelain": [" M backend/app/backtest/scanner.py"],
    }


def test_detects_static_scanner_version(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert detect_scanner_version(root) == EXPECTED_SCANNER_VERSION


def test_import_graph_discovers_production_dependencies(tmp_path: Path) -> None:
    root = _project(tmp_path)
    rel = {p.relative_to(root).as_posix() for p in discover_production_files(root)}
    assert "backend/app/backtest/scanner.py" in rel
    assert "backend/app/backtest/candidate_priority.py" in rel
    assert "backend/app/backtest/market_store.py" in rel
    assert "backend/app/core/risk.py" in rel
    assert "backend/app/core/target.py" in rel
    assert "backend/app/settings/scanner.json" in rel


def test_research_and_simulation_are_excluded(tmp_path: Path) -> None:
    root = _project(tmp_path)
    rel = {p.relative_to(root).as_posix() for p in discover_production_files(root)}
    assert "backend/app/backtest/scanner_quality/research.py" not in rel
    assert "backend/app/simulation/engine.py" not in rel


def test_file_hashes_and_aggregate_are_deterministic(tmp_path: Path) -> None:
    root = _project(tmp_path)
    files = discover_production_files(root)
    rows1 = file_manifest(root, files)
    rows2 = file_manifest(root, reversed(files))
    assert rows1 == rows2
    assert aggregate_production_fingerprint(rows1) == aggregate_production_fingerprint(rows2)


def test_policy_fingerprint_is_deterministic() -> None:
    assert policy_fingerprint() == policy_fingerprint()


def test_baseline_id_is_deterministic() -> None:
    a = baseline_id(EXPECTED_SCANNER_VERSION, "a" * 64, "b" * 64)
    b = baseline_id(EXPECTED_SCANNER_VERSION, "a" * 64, "b" * 64)
    assert a == b
    assert a.startswith(f"SS-SCANNER-{EXPECTED_SCANNER_VERSION}-")


def test_manifest_records_research_only_rules_as_not_production(tmp_path: Path) -> None:
    root = _project(tmp_path)
    manifest = build_manifest(root, created_at="2026-09-20T21:00:00+09:00", git=_fake_git())
    assert manifest["schema_version"] == BASELINE_SCHEMA_VERSION
    assert manifest["production_changed"] is False
    assert manifest["policies"]["overextension_guard"] == "NOT_PRODUCTION"
    assert manifest["policies"]["volume_low_guard"] == "REJECTED_NOT_PRODUCTION"
    assert manifest["git"]["working_tree_dirty"] is True


def test_manifest_build_is_deterministic_given_fixed_metadata(tmp_path: Path) -> None:
    root = _project(tmp_path)
    kwargs = {"created_at": "2026-09-20T21:00:00+09:00", "git": _fake_git()}
    assert build_manifest(root, **kwargs) == build_manifest(root, **kwargs)


def test_verify_match_then_source_change_mismatch(tmp_path: Path) -> None:
    root = _project(tmp_path)
    manifest = build_manifest(root, created_at="x", git=_fake_git())
    assert verify_baseline(root, manifest).valid is True
    scanner = root / "backend/app/backtest/scanner.py"
    scanner.write_text(scanner.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    result = verify_baseline(root, manifest)
    assert result.valid is False
    assert any(item["path"].endswith("scanner.py") for item in result.changed_files)


def test_nonproduction_change_does_not_change_fingerprint(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = build_manifest(root, created_at="x", git=_fake_git())["production_fingerprint"]
    (root / "README.md").write_text("changed outside production\n", encoding="utf-8")
    (root / "backend/app/simulation/engine.py").write_text("changed simulation only\n", encoding="utf-8")
    after = build_manifest(root, created_at="x", git=_fake_git())["production_fingerprint"]
    assert before == after


def test_verify_detects_missing_recorded_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    manifest = build_manifest(root, created_at="x", git=_fake_git())
    (root / "backend/app/core/risk.py").unlink()
    result = verify_baseline(root, manifest)
    assert result.valid is False
    assert "backend/app/core/risk.py" in result.missing_files


def test_verify_detects_new_imported_dependency(tmp_path: Path) -> None:
    root = _project(tmp_path)
    manifest = build_manifest(root, created_at="x", git=_fake_git())
    _write(root / "backend/app/core/new_policy.py", "VALUE=1\n")
    scanner = root / "backend/app/backtest/scanner.py"
    scanner.write_text("from app.core.new_policy import VALUE\n" + scanner.read_text(encoding="utf-8"), encoding="utf-8")
    result = verify_baseline(root, manifest)
    assert result.valid is False
    assert "backend/app/core/new_policy.py" in result.extra_relevant_files


def test_freeze_refuses_overwrite(tmp_path: Path) -> None:
    root = _project(tmp_path)
    target = root / "backend/runtime/baseline/scanner-production-baseline_0.21.3.7.json"
    freeze_baseline(root, target)
    with pytest.raises(BaselineError, match="BASELINE_ALREADY_EXISTS"):
        freeze_baseline(root, target)


def test_wrong_scanner_version_is_blocked(tmp_path: Path) -> None:
    root = _project(tmp_path)
    scanner = root / "backend/app/backtest/scanner.py"
    scanner.write_text(scanner.read_text(encoding="utf-8").replace(EXPECTED_SCANNER_VERSION, "0.21.3.8"), encoding="utf-8")
    with pytest.raises(BaselineError, match="SCANNER_VERSION_MISMATCH"):
        build_manifest(root, created_at="x", git=_fake_git())


def test_static_config_change_is_detected(tmp_path: Path) -> None:
    root = _project(tmp_path)
    manifest = build_manifest(root, created_at="x", git=_fake_git())
    cfg = root / "backend/app/settings/scanner.json"
    cfg.write_text('{"mode":"changed"}\n', encoding="utf-8")
    assert verify_baseline(root, manifest).valid is False
