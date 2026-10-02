from __future__ import annotations

from pathlib import Path

import pytest

from tools.data.common import DataToolError
from tools.dev import sync_local


def _paths(tmp_path: Path) -> sync_local.RuntimePaths:
    return sync_local.RuntimePaths(
        holdings=tmp_path / "holdings.db",
        market=tmp_path / "market.db",
        simulation=tmp_path / "simulation.db",
    )


def _stub_final_verifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sync_local,
        "validate_holdings_db",
        lambda path: {"status": "PASS"},
    )
    monkeypatch.setattr(
        sync_local,
        "validate_market_db",
        lambda path: {"status": "PASS"},
    )
    monkeypatch.setattr(
        sync_local,
        "validate_simulation_db",
        lambda path: {"status": "PASS"},
    )
    monkeypatch.setattr(
        sync_local,
        "_verify_p5_p6",
        lambda paths: {
            "operating_strategies": 10,
            "no_trade_registered": False,
            "event_evidence": "CURRENT",
            "prediction_enabled": False,
        },
    )


def test_final_verify_accepts_optional_not_applicable_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_final_verifiers(monkeypatch)
    statuses = [
        sync_local.MigrationStatus(
            "VN-P1-S1",
            "Input Identity",
            sync_local.MigrationState.CURRENT,
        ),
        sync_local.MigrationStatus(
            "VN-P1-S3",
            "Selection Policy Pin",
            sync_local.MigrationState.NOT_APPLICABLE,
            "optional runtime domain not initialized",
        ),
    ]
    monkeypatch.setattr(sync_local, "inspect_all", lambda paths: statuses)

    paths = _paths(tmp_path)
    paths.simulation.touch()
    result = sync_local.final_verify(paths)

    assert result["governance"]["operating_strategies"] == 10


def test_final_verify_still_rejects_missing_required_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_final_verifiers(monkeypatch)
    statuses = [
        sync_local.MigrationStatus(
            "VN-P2-S1",
            "Feedback",
            sync_local.MigrationState.MISSING,
        )
    ]
    monkeypatch.setattr(sync_local, "inspect_all", lambda paths: statuses)

    with pytest.raises(DataToolError, match="VN-P2-S1=MISSING"):
        sync_local.final_verify(_paths(tmp_path))
