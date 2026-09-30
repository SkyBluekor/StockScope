from __future__ import annotations

from pathlib import Path

import pytest

from tools.dev.sync_macro_artifacts import (
    DEV_NAME,
    PROTOCOL_NAME,
    MacroArtifactSyncError,
    fixed_artifact_specs,
    sync_macro_artifacts,
)


def _write_seed(directory: Path, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text("{}\n", encoding="utf-8")


def test_macro_sync_fixed_chain_is_ordered_and_holdout_free(tmp_path: Path):
    specs = fixed_artifact_specs(tmp_path)

    assert [spec.key for spec in specs] == [
        "research",
        "diagnostic",
        "evidence",
        "reconstruction",
    ]
    assert all("holdout" not in spec.script.lower() for spec in specs)
    assert all(
        "holdout" not in argument.lower()
        for spec in specs
        for argument in spec.arguments
    )


def test_macro_sync_check_only_reports_missing_without_writes(tmp_path: Path):
    _write_seed(tmp_path, DEV_NAME)
    _write_seed(tmp_path, PROTOCOL_NAME)
    calls: list[tuple[str, tuple[str, ...]]] = []

    result = sync_macro_artifacts(
        calibration_dir=tmp_path,
        check_only=True,
        runner=lambda script, args: calls.append((script, args)),
    )

    assert calls == []
    assert result["ready"] is False
    assert result["blocked"] is False
    assert result["holdout_accessed"] is False
    assert result["network_requests"] == 0
    states = {item["key"]: item["state"] for item in result["statuses"]}
    assert states["development"] == "CURRENT"
    assert states["protocol"] == "CURRENT"
    assert states["research"] == "MISSING"
    assert states["diagnostic"] == "MISSING"
    assert states["evidence"] == "MISSING"
    assert states["reconstruction"] == "MISSING"


def test_macro_sync_blocks_when_seed_artifacts_are_missing(tmp_path: Path):
    result = sync_macro_artifacts(
        calibration_dir=tmp_path,
        check_only=False,
        runner=lambda *_: pytest.fail("runner must not be called"),
    )

    assert result["blocked"] is True
    assert result["ready"] is False
    assert sorted(result["missing_seeds"]) == sorted([DEV_NAME, PROTOCOL_NAME])
    assert result["holdout_accessed"] is False


def test_macro_sync_does_not_overwrite_invalid_immutable_artifact(tmp_path: Path):
    _write_seed(tmp_path, DEV_NAME)
    _write_seed(tmp_path, PROTOCOL_NAME)
    specs = fixed_artifact_specs(tmp_path)
    research = tmp_path / specs[0].filename
    research.write_text("{}\n", encoding="utf-8")

    with pytest.raises(MacroArtifactSyncError, match="immutable artifact is invalid"):
        sync_macro_artifacts(
            calibration_dir=tmp_path,
            check_only=False,
            runner=lambda *_: pytest.fail("runner must not be called"),
        )


def test_root_one_click_sync_invokes_macro_artifact_sync():
    root = Path(__file__).resolve().parents[2]
    script = (root / "sync_local.ps1").read_text(encoding="utf-8")

    assert "tools\\dev\\sync_macro_artifacts.py" in script
    assert "--check-only" in script


def test_root_one_click_sync_restarts_after_self_update():
    root = Path(__file__).resolve().parents[2]
    script = (root / "sync_local.ps1").read_text(encoding="utf-8")

    assert "AfterSelfUpdate" in script
    assert 'git diff --name-only "$BeforeHead..$AfterHead" -- "sync_local.ps1"' in script
    assert "UPDATED - restarting once" in script
    assert "-AfterSelfUpdate" in script


def test_macro_sync_source_includes_r21_evidence_stage():
    root = Path(__file__).resolve().parents[2]
    source = (root / "tools" / "dev" / "sync_macro_artifacts.py").read_text(
        encoding="utf-8"
    )

    assert "REFERENCE-ADEQUACY-EVIDENCE-" in source
    assert "build_macro_reference_adequacy_evidence_next6b_s4_2b16_r21.py" in source
    assert "adequacy_evidence" in source
    assert "--holdout-artifact" not in source


def test_macro_sync_requires_compact_v2_and_reports_metadata():
    root = Path(__file__).resolve().parents[2]
    source = (root / "tools" / "dev" / "sync_macro_artifacts.py").read_text(
        encoding="utf-8"
    )

    assert 'REFERENCE-ADEQUACY-EVIDENCE-*.json.gz' in source
    assert 'REFERENCE-ADEQUACY-EVIDENCE-*.json")' not in source
    assert "LEGACY_R21_V1_NAME" in source
    assert '"HISTORICAL"' in source
    assert "--legacy-v1-artifact" in source
    assert "evidence_summary" in source
    assert "Forward comparisons" in source
    assert "Macro DB writes" in source
    assert "Production" in source
