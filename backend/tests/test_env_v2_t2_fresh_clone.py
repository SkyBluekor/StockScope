from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.holdings import HoldingsCatalog
from tools.data.bootstrap_runtime import bootstrap_runtime
from tools.data.common import DataToolError
from tools.runtime.bootstrap_state import domain_hash
from tools.runtime.handoff import (
    RuntimeLocations,
    export_handoff,
    import_handoff,
    sqlite_content_sha256,
)


def _locations(root: Path) -> RuntimeLocations:
    return RuntimeLocations(
        holdings=root / "holdings" / "holdings.db",
        simulation=root / "simulation" / "simulation.db",
        market=root / "market_history" / "market_history.db",
        tracking=root / "tracking" / "recommendation_tracking.db",
        macro=root / "macro" / "macro.db",
        strategy_selection=root / "strategy_selection",
        continuity_state=root / "continuity" / "runtime_state.json",
    )


def _bootstrap(root: Path) -> tuple[RuntimeLocations, dict]:
    locations = _locations(root)
    result = bootstrap_runtime(
        locations=locations,
        backup_root=root / "backups",
    )
    return locations, result


def _count(path: Path, table: str) -> int:
    with sqlite3.connect(path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_fresh_clone_bootstrap_creates_complete_empty_runtime(
    tmp_path: Path,
) -> None:
    locations, result = _bootstrap(tmp_path / "fresh")

    assert result["status"] == "COMPLETE"
    assert result["environment"] == "CURRENT"
    assert result["google_drive_required"] is False
    assert result["external_network_requests"] == 0
    assert result["market_data"]["status"] == "DATA_REQUIRED"
    assert result["application"] == "READY"

    for domain in ("holdings", "market", "simulation", "tracking", "macro"):
        path = Path(getattr(locations, domain))
        assert path.is_file()
        assert result["created"][domain] is True
        assert domain_hash(locations.continuity_state, domain) == (
            sqlite_content_sha256(path)
        )

    assert all(
        item["state"] in {"CURRENT", "NOT_APPLICABLE"}
        for item in result["runtime_migrations"]
    )
    assert _count(locations.holdings, "holding_position") == 0
    assert _count(locations.simulation, "simulation_portfolio") == 0
    assert _count(locations.simulation, "historical_validation_run") == 0
    assert _count(locations.simulation, "historical_execution_run") == 0
    assert _count(locations.tracking, "tracked_recommendation") == 0
    assert _count(locations.macro, "macro_observation_revision") == 0


def test_repeat_setup_preserves_user_data_and_does_not_relabel_it_pristine(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repeat"
    locations, _ = _bootstrap(root)
    pristine_hash = domain_hash(locations.continuity_state, "holdings")
    assert pristine_hash

    catalog = HoldingsCatalog(locations.holdings)
    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="user account",
    )
    changed_hash = sqlite_content_sha256(locations.holdings)
    assert changed_hash != pristine_hash

    second = bootstrap_runtime(
        locations=locations,
        backup_root=root / "backups",
    )

    assert second["status"] == "COMPLETE"
    assert second["environment"] == "CURRENT"
    assert second["created"]["holdings"] is False
    assert second["pre_setup_backup"] is not None
    assert catalog.get_position_account(account.id).id == account.id
    assert sqlite_content_sha256(locations.holdings) == changed_hash
    assert domain_hash(locations.continuity_state, "holdings") == pristine_hash


def test_fresh_setup_target_accepts_handoff_restore_without_manual_reconcile(
    tmp_path: Path,
) -> None:
    source, _ = _bootstrap(tmp_path / "source")
    source_catalog = HoldingsCatalog(source.holdings)
    account = source_catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="restored account",
    )
    bundle = tmp_path / "bundle"
    exported = export_handoff(
        domains=["holdings"],
        destination=bundle,
        locations=source,
    )
    assert exported["status"] == "COMPLETE"

    target, _ = _bootstrap(tmp_path / "target")
    result = import_handoff(
        bundle,
        domains=["holdings"],
        locations=target,
        strict=True,
    )

    assert result["status"] == "COMPLETE"
    assert result["installed"] == ["holdings"]
    plan = result["plans"][0]
    assert plan["action"] == "REPLACE_FRESH_BOOTSTRAP"
    assert plan["reason"] == "VERIFIED_EMPTY_BOOTSTRAP"
    assert HoldingsCatalog(target.holdings).get_position_account(account.id).id == account.id
    assert domain_hash(target.continuity_state, "holdings") is None


def test_user_modified_fresh_target_still_blocks_older_or_foreign_handoff(
    tmp_path: Path,
) -> None:
    source, _ = _bootstrap(tmp_path / "source")
    source_catalog = HoldingsCatalog(source.holdings)
    source_catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="source account",
    )
    bundle = tmp_path / "bundle"
    export_handoff(
        domains=["holdings"],
        destination=bundle,
        locations=source,
    )

    target, _ = _bootstrap(tmp_path / "target")
    target_catalog = HoldingsCatalog(target.holdings)
    local = target_catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="local account",
    )

    result = import_handoff(
        bundle,
        domains=["holdings"],
        locations=target,
        strict=True,
    )

    assert result["status"] == "BLOCKED"
    assert result["installed"] == []
    assert result["conflicts"][0]["reason"] == "LOCAL_LINEAGE_UNKNOWN"
    assert target_catalog.get_position_account(local.id).id == local.id


def test_bootstrap_requires_no_drive_transport_configuration(
    tmp_path: Path,
) -> None:
    locations, result = _bootstrap(tmp_path / "no-drive")

    transport_config = (
        locations.continuity_state.parent / "transport_config.json"
    )
    assert result["google_drive_required"] is False
    assert result["external_network_requests"] == 0
    assert not transport_config.exists()


def test_future_tracking_schema_fails_before_setup_writes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "future"
    locations, _ = _bootstrap(root)
    before_holdings = sqlite_content_sha256(locations.holdings)

    with sqlite3.connect(locations.tracking) as conn:
        conn.execute(
            "UPDATE tracking_meta SET value='999' WHERE key='schema_version'"
        )

    with pytest.raises(DataToolError, match="새로운 Tracking schema"):
        bootstrap_runtime(
            locations=locations,
            backup_root=root / "backups",
        )

    assert sqlite_content_sha256(locations.holdings) == before_holdings


def test_setup_launcher_is_fresh_clone_entry_point() -> None:
    root = Path(__file__).resolve().parents[2]
    setup = (root / "setup.ps1").read_text(encoding="utf-8")

    assert "Python 3.11 or newer is required" in setup
    assert "tools\\data\\bootstrap_runtime.py" in setup
    assert "tools\\data\\doctor.py" in setup
    assert "Google Drive is not required for a new project." in setup
    assert "Copy-Item \".env.example\" \".env\"" in setup
    assert "Existing .env preserved." in setup
    assert "-m pytest" not in setup
