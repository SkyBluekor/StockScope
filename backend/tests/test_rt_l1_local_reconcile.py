from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tools.data.common import DataToolError
from tools.runtime.handoff import RuntimeLocations
from tools.runtime.local_reconcile import reconcile_local
from tools.runtime.transport import (
    configure_transport,
    disable_transport,
    post_sync,
    pre_sync,
    reconcile_remote,
)


def _machine(root: Path) -> RuntimeLocations:
    return RuntimeLocations(
        holdings=root / "holdings" / "holdings.db",
        simulation=root / "simulation" / "simulation.db",
        market=root / "market_history" / "market_history.db",
        tracking=root / "tracking" / "recommendation_tracking.db",
        macro=root / "macro" / "macro.db",
        strategy_selection=root / "strategy_selection",
        continuity_state=root / "continuity" / "runtime_state.json",
    )


def _add(db: Path, name: str) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS simulation_schema_meta("
            "key TEXT PRIMARY KEY,value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO simulation_schema_meta VALUES"
            "('schema_version','3')"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS simulation_portfolio(id TEXT PRIMARY KEY)"
        )
        conn.execute("INSERT INTO simulation_portfolio VALUES(?)", (name,))


def _rows(db: Path) -> set[str]:
    with sqlite3.connect(db) as conn:
        return {row[0] for row in conn.execute("SELECT id FROM simulation_portfolio")}


def _backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    backup = tmp_path / "backups" / "fixture"
    backup.mkdir(parents=True)
    (backup / "backup_manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "tools.runtime.local_reconcile.create_backup", lambda: backup
    )
    monkeypatch.setattr("tools.data.backup_runtime.create_backup", lambda: backup)
    return backup


def _diverged(tmp_path: Path) -> tuple[RuntimeLocations, RuntimeLocations, Path]:
    root = tmp_path / "GoogleDrive" / "StockScopeRuntime"
    remote = _machine(tmp_path / "remote")
    local = _machine(tmp_path / "local")
    configure_transport(root, locations=remote)
    configure_transport(root, locations=local)
    _add(remote.simulation, "base")
    post_sync(locations=remote)
    assert pre_sync(locations=local)["status"] == "FAST_FORWARD"
    _add(remote.simulation, "discard-me")
    post_sync(locations=remote)
    _add(local.simulation, "keep-me")
    disable_transport(locations=local)
    return local, remote, root


def test_local_dry_run_makes_no_persistent_changes(tmp_path: Path) -> None:
    local, remote, root = _diverged(tmp_path)
    state_before = local.continuity_state.read_bytes()
    heads_before = {p.name: p.read_bytes() for p in (root / "heads").iterdir()}
    bundles_before = {p.name for p in (root / "bundles").iterdir()}
    plan = reconcile_local(locations=local, dry_run=True, domains=["simulation"])
    assert plan["status"] == "PLANNED"
    assert plan["prefer_local"] == ["simulation"]
    assert plan["writes"] == 0
    assert _rows(local.simulation) == {"base", "keep-me"}
    assert local.continuity_state.read_bytes() == state_before
    assert {p.name: p.read_bytes() for p in (root / "heads").iterdir()} == heads_before
    assert {p.name for p in (root / "bundles").iterdir()} == bundles_before
    with pytest.raises(DataToolError, match="--confirm"):
        reconcile_local(locations=local, domains=["simulation"])
    assert _rows(remote.simulation) == {"base", "discard-me"}


def test_explicit_local_authority_round_trip_and_remote_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local, remote, root = _diverged(tmp_path)
    _backup(tmp_path, monkeypatch)
    current = _rows(local.simulation)
    result = reconcile_local(
        locations=local, domains=["simulation"], confirm=True,
    )
    assert result["status"] == "PUBLISHED"
    assert result["transport_enabled"] is False
    assert _rows(local.simulation) == current
    assert reconcile_local(
        locations=local, domains=["simulation"], dry_run=True
    )["status"] == "CURRENT"

    # Existing remote history is not silently modified.
    assert _rows(remote.simulation) == {"base", "discard-me"}
    # A writes additional unreviewed data: normal import must still block.
    _add(remote.simulation, "throw-away-later")
    with pytest.raises(DataToolError, match="RUNTIME_TRANSPORT_CONFLICT"):
        pre_sync(locations=remote)
    with pytest.raises(DataToolError, match="RUNTIME_TRANSPORT_CONFLICT"):
        reconcile_remote(
            prefer_remote=True, confirm=True, domains=["simulation"],
            locations=remote,
        )
    adopted = reconcile_remote(
        prefer_remote=True,
        confirm=True,
        replace_local_changes=True,
        domains=["simulation"],
        locations=remote,
    )
    assert adopted["status"] == "RECONCILED"
    assert _rows(remote.simulation) == current
    # Transport may be enabled again after the explicit swap.
    configure_transport(root, locations=local)
    assert pre_sync(locations=local)["status"] in {"CURRENT", "LOCAL_AHEAD"}
    assert post_sync(locations=local)["status"] == "CURRENT"


def test_reconcile_blocks_unapproved_domains_and_domain_overreach(
    tmp_path: Path
) -> None:
    local, remote, _ = _diverged(tmp_path)
    with pytest.raises(DataToolError, match="NOT_ALLOWED"):
        reconcile_local(locations=local, domains=["tracking"], dry_run=True)
    with pytest.raises(DataToolError, match="SELECTED_DOMAIN_MISSING"):
        reconcile_local(locations=local, domains=["holdings"], dry_run=True)


def test_reconcile_rejects_changed_remote_head_and_leaves_local_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.runtime import local_reconcile as module

    local, remote, root = _diverged(tmp_path)
    _backup(tmp_path, monkeypatch)
    before = local.continuity_state.read_bytes()
    original_publish = module._publish_bundle

    def publish_and_advance(**kwargs):
        # Model an independent machine updating its head during local publication.
        changed = original_publish(**kwargs)
        for path in (root / "heads").glob("*.json"):
            head = json.loads(path.read_text(encoding="utf-8"))
            if head["machine_id"] != json.loads(before)["machine_id"]:
                head["published_at"] = "changed-during-publish"
                path.write_text(json.dumps(head), encoding="utf-8")
                break
        return changed

    monkeypatch.setattr(module, "_publish_bundle", publish_and_advance)
    with pytest.raises(DataToolError, match="REMOTE_HEAD_CHANGED"):
        reconcile_local(locations=local, domains=["simulation"], confirm=True)
    assert _rows(local.simulation) == {"base", "keep-me"}
    assert local.continuity_state.read_bytes() == before
