from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tools.dev import sync_local
from tools.runtime.handoff import (
    RuntimeLocations,
    export_handoff,
    import_handoff,
    inspect_handoff,
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


def _portfolio_ids(path: Path) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {
            str(row[0])
            for row in conn.execute(
                "SELECT id FROM simulation_portfolio ORDER BY id"
            ).fetchall()
        }


def _manifest(bundle: Path) -> dict:
    return json.loads(
        (bundle / "runtime_manifest.json").read_text(encoding="utf-8")
    )


def test_simulation_only_handoff_does_not_touch_holdings(tmp_path: Path) -> None:
    source = _locations(tmp_path / "source")
    target = _locations(tmp_path / "target")
    _make_simulation(source.simulation, "source-1")

    target.holdings.parent.mkdir(parents=True, exist_ok=True)
    target.holdings.write_bytes(b"holdings-must-not-change")
    before_holdings = target.holdings.read_bytes()

    bundle = tmp_path / "bundle"
    exported = export_handoff(
        domains=["simulation"],
        destination=bundle,
        locations=source,
    )
    imported = import_handoff(
        bundle,
        domains=["simulation"],
        locations=target,
    )

    assert exported["status"] == "COMPLETE"
    assert imported["status"] == "COMPLETE"
    assert imported["installed"] == ["simulation"]
    assert _portfolio_ids(target.simulation) == {"source-1"}
    assert target.holdings.read_bytes() == before_holdings


def test_handoff_fast_forwards_same_lineage_then_blocks_local_divergence(
    tmp_path: Path,
) -> None:
    source = _locations(tmp_path / "source")
    target = _locations(tmp_path / "target")
    _make_simulation(source.simulation, "source-1")

    bundle1 = tmp_path / "bundle-1"
    export_handoff(
        domains=["simulation"],
        destination=bundle1,
        locations=source,
    )
    first = import_handoff(
        bundle1,
        domains=["simulation"],
        locations=target,
    )
    assert first["installed"] == ["simulation"]

    _make_simulation(source.simulation, "source-2")
    bundle2 = tmp_path / "bundle-2"
    export_handoff(
        domains=["simulation"],
        destination=bundle2,
        locations=source,
    )

    first_manifest = _manifest(bundle1)["domains"]["simulation"]
    second_manifest = _manifest(bundle2)["domains"]["simulation"]
    assert second_manifest["domain_id"] == first_manifest["domain_id"]
    assert second_manifest["parent_snapshot_id"] == first_manifest["snapshot_id"]

    second = import_handoff(
        bundle2,
        domains=["simulation"],
        locations=target,
    )
    assert second["status"] == "COMPLETE"
    assert second["plans"][0]["action"] == "FAST_FORWARD"
    assert _portfolio_ids(target.simulation) == {"source-1", "source-2"}

    _make_simulation(target.simulation, "target-local")
    _make_simulation(source.simulation, "source-3")
    bundle3 = tmp_path / "bundle-3"
    export_handoff(
        domains=["simulation"],
        destination=bundle3,
        locations=source,
    )

    third = import_handoff(
        bundle3,
        domains=["simulation"],
        locations=target,
    )

    assert third["status"] == "PARTIAL"
    assert third["installed"] == []
    assert third["conflicts"][0]["action"] == "CONFLICT"
    assert _portfolio_ids(target.simulation) == {
        "source-1",
        "source-2",
        "target-local",
    }


def test_unknown_existing_simulation_is_never_silently_overwritten(
    tmp_path: Path,
) -> None:
    source = _locations(tmp_path / "source")
    target = _locations(tmp_path / "target")
    _make_simulation(source.simulation, "incoming")
    _make_simulation(target.simulation, "local")

    bundle = tmp_path / "bundle"
    export_handoff(
        domains=["simulation"],
        destination=bundle,
        locations=source,
    )

    result = import_handoff(
        bundle,
        domains=["simulation"],
        locations=target,
        strict=True,
    )

    assert result["status"] == "BLOCKED"
    assert result["installed"] == []
    assert result["conflicts"][0]["action"] == "CONFLICT"
    assert _portfolio_ids(target.simulation) == {"local"}


def test_handoff_manifest_is_completed_and_verified(tmp_path: Path) -> None:
    source = _locations(tmp_path / "source")
    _make_simulation(source.simulation, "source-1")
    bundle = tmp_path / "bundle"

    export_handoff(
        domains=["simulation"],
        destination=bundle,
        locations=source,
    )
    manifest = inspect_handoff(bundle)

    assert manifest["runtime_contract"] == "STOCKSCOPE_HANDOFF_V1"
    assert manifest["secrets_included"] is False
    assert set(manifest["domains"]) == {"simulation"}
    assert (bundle / "bundle_complete.json").is_file()


def test_migration_write_set_includes_market_for_input_identity() -> None:
    plan = {
        "statuses": [
            {"key": "VN-P1-S1", "plan": "APPLY"},
            {"key": "VN-P3-S1", "plan": "APPLY_AFTER:BASE"},
            {"key": "VN-P6-S1", "plan": "NO_ACTION"},
        ]
    }

    assert sync_local._planned_write_domains(plan) == {
        "holdings",
        "market",
        "simulation",
    }


def test_stockscope_entrypoint_exposes_handoff_and_bootstrap() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "stockscope.ps1").read_text(encoding="utf-8")

    assert '"handoff"' in source
    assert '"bootstrap"' in source
    assert "tools\\runtime\\cli.py" in source
