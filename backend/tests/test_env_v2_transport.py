from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tools.data.common import DataToolError
from tools.runtime.handoff import RuntimeLocations
from tools.runtime.transport import (
    AUTO_DOMAINS,
    TRANSPORT_HEAD_CONTRACT,
    configure_transport,
    post_sync,
    pre_sync,
    transport_status,
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


def _make_simulation(path: Path, *portfolio_ids: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS simulation_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO simulation_schema_meta(key,value)
            VALUES('schema_version','3')
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS simulation_portfolio(
                id TEXT PRIMARY KEY
            )
            """
        )
        for portfolio_id in portfolio_ids:
            conn.execute(
                "INSERT OR IGNORE INTO simulation_portfolio(id) VALUES(?)",
                (portfolio_id,),
            )


def _ids(path: Path) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {
            str(row[0])
            for row in conn.execute(
                "SELECT id FROM simulation_portfolio ORDER BY id"
            ).fetchall()
        }


def _machine_id(locations: RuntimeLocations) -> str:
    payload = json.loads(
        locations.continuity_state.read_text(encoding="utf-8")
    )
    return str(payload["machine_id"])


def test_transport_round_trip_without_manual_handoff(tmp_path: Path) -> None:
    shared = tmp_path / "GoogleDrive" / "StockScopeRuntime"
    a = _locations(tmp_path / "pc-a")
    b = _locations(tmp_path / "pc-b")

    configure_transport(shared, locations=a)
    configure_transport(shared, locations=b)
    _make_simulation(a.simulation, "a-1")

    first_publish = post_sync(locations=a)
    assert first_publish["status"] == "PUBLISHED"
    assert first_publish["published"] is True

    first_import = pre_sync(
        locations=b,
        retry_count=1,
        retry_delay_seconds=0,
    )
    assert first_import["status"] == "FAST_FORWARD"
    assert first_import["installed"] == ["simulation"]
    assert _ids(b.simulation) == {"a-1"}

    _make_simulation(b.simulation, "b-1")
    second_publish = post_sync(locations=b)
    assert second_publish["status"] == "PUBLISHED"

    second_import = pre_sync(
        locations=a,
        retry_count=1,
        retry_delay_seconds=0,
    )
    assert second_import["status"] == "FAST_FORWARD"
    assert second_import["installed"] == ["simulation"]
    assert _ids(a.simulation) == {"a-1", "b-1"}


def test_transport_fast_forwards_multiple_snapshot_steps(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "GoogleDrive" / "StockScopeRuntime"
    a = _locations(tmp_path / "pc-a")
    b = _locations(tmp_path / "pc-b")

    configure_transport(shared, locations=a)
    configure_transport(shared, locations=b)
    _make_simulation(a.simulation, "base")
    post_sync(locations=a)
    pre_sync(locations=b, retry_count=1, retry_delay_seconds=0)

    _make_simulation(b.simulation, "step-1")
    post_sync(locations=b)
    _make_simulation(b.simulation, "step-2")
    post_sync(locations=b)
    _make_simulation(b.simulation, "step-3")
    post_sync(locations=b)

    result = pre_sync(
        locations=a,
        retry_count=1,
        retry_delay_seconds=0,
    )

    assert result["status"] == "FAST_FORWARD"
    assert result["plans"][0]["action"] == "FAST_FORWARD"
    assert _ids(a.simulation) == {
        "base",
        "step-1",
        "step-2",
        "step-3",
    }


def test_transport_blocks_diverged_runtime_histories(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "GoogleDrive" / "StockScopeRuntime"
    a = _locations(tmp_path / "pc-a")
    b = _locations(tmp_path / "pc-b")

    configure_transport(shared, locations=a)
    configure_transport(shared, locations=b)
    _make_simulation(a.simulation, "base")
    post_sync(locations=a)
    pre_sync(locations=b, retry_count=1, retry_delay_seconds=0)

    _make_simulation(a.simulation, "a-branch")
    post_sync(locations=a)

    # Simulate PC-B working offline from the same parent, then publishing.
    _make_simulation(b.simulation, "b-branch")
    post_sync(locations=b)

    with pytest.raises(DataToolError, match="RUNTIME_TRANSPORT_CONFLICT"):
        pre_sync(
            locations=a,
            retry_count=1,
            retry_delay_seconds=0,
        )

    assert _ids(a.simulation) == {"base", "a-branch"}


def test_transport_detects_committed_wal_changes(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "GoogleDrive" / "StockScopeRuntime"
    a = _locations(tmp_path / "pc-a")
    configure_transport(shared, locations=a)
    _make_simulation(a.simulation, "base")
    post_sync(locations=a)

    conn = sqlite3.connect(a.simulation)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute(
            "INSERT INTO simulation_portfolio(id) VALUES('wal-change')"
        )
        conn.commit()

        result = post_sync(locations=a)
    finally:
        conn.close()

    assert result["status"] == "PUBLISHED"
    assert "simulation:CONTENT_CHANGED" in result["reasons"]
    bundles = [
        path for path in (shared / "bundles").iterdir()
        if path.is_dir()
    ]
    assert len(bundles) == 2


def test_transport_does_not_publish_when_runtime_is_unchanged(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "GoogleDrive" / "StockScopeRuntime"
    a = _locations(tmp_path / "pc-a")
    configure_transport(shared, locations=a)
    _make_simulation(a.simulation, "base")

    first = post_sync(locations=a)
    second = post_sync(locations=a)

    assert first["status"] == "PUBLISHED"
    assert second == {
        "status": "CURRENT",
        "published": False,
        "reason": "RUNTIME_UNCHANGED",
    }
    bundles = [
        path for path in (shared / "bundles").iterdir()
        if path.is_dir()
    ]
    assert len(bundles) == 1


def test_transport_blocks_head_whose_bundle_has_not_arrived(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "GoogleDrive" / "StockScopeRuntime"
    local = _locations(tmp_path / "pc-local")
    configure_transport(shared, locations=local)

    remote_machine = "remote-machine"
    head = {
        "contract_version": TRANSPORT_HEAD_CONTRACT,
        "machine_id": remote_machine,
        "published_at": "2026-10-02T00:00:00+00:00",
        "source_git_sha": "test",
        "bundle_id": "missing-bundle",
        "domains": {
            "simulation": {
                "domain_id": "domain-1",
                "snapshot_id": "snapshot-1",
                "parent_snapshot_id": None,
                "content_sha256": "a" * 64,
                "bundle_id": "missing-bundle",
            }
        },
    }
    (shared / "heads" / f"{remote_machine}.json").write_text(
        json.dumps(head),
        encoding="utf-8",
    )

    with pytest.raises(DataToolError, match="REMOTE_NOT_READY"):
        pre_sync(
            locations=local,
            retry_count=1,
            retry_delay_seconds=0,
        )


def test_transport_status_is_read_only_when_not_configured(
    tmp_path: Path,
) -> None:
    local = _locations(tmp_path / "pc-local")

    result = transport_status(locations=local)

    assert result["status"] == "DISABLED"
    assert result["writes"] == 0
    assert not local.continuity_state.exists()
    assert not (local.continuity_state.parent / "transport_config.json").exists()


def test_transport_heads_are_machine_specific(tmp_path: Path) -> None:
    shared = tmp_path / "GoogleDrive" / "StockScopeRuntime"
    a = _locations(tmp_path / "pc-a")
    b = _locations(tmp_path / "pc-b")
    configure_transport(shared, locations=a)
    configure_transport(shared, locations=b)
    _make_simulation(a.simulation, "base")
    post_sync(locations=a)
    pre_sync(locations=b, retry_count=1, retry_delay_seconds=0)

    assert (shared / "heads" / f"{_machine_id(a)}.json").is_file()
    assert (shared / "heads" / f"{_machine_id(b)}.json").is_file()
    assert _machine_id(a) != _machine_id(b)


def test_auto_transport_never_includes_strategy_selection() -> None:
    assert "strategy_selection" not in AUTO_DOMAINS
    assert set(AUTO_DOMAINS) == {
        "holdings",
        "simulation",
        "tracking",
        "macro",
    }


def test_sync_launcher_has_pre_and_post_transport_hooks() -> None:
    root = Path(__file__).resolve().parents[2]
    sync_source = (root / "sync_local.ps1").read_text(encoding="utf-8")
    entry_source = (root / "stockscope.ps1").read_text(encoding="utf-8")

    assert "transport pre-sync" in sync_source
    assert "transport post-sync" in sync_source
    assert "transport status" in sync_source
    assert '"transport"' in entry_source
    assert "tools\\runtime\\cli.py" in entry_source
