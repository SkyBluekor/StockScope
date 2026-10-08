from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tools.data.common import DataToolError, REQUIRED_HOLDINGS_TABLES
from tools.runtime.handoff import RuntimeLocations
from tools.runtime.local_reconcile import reconcile_local
from tools.runtime.transport import configure_transport, disable_transport, post_sync, pre_sync


def _pc(path: Path) -> RuntimeLocations:
    return RuntimeLocations(
        holdings=path / "holdings" / "holdings.db",
        simulation=path / "simulation" / "simulation.db",
        market=path / "market_history" / "market_history.db",
        tracking=path / "tracking" / "recommendation_tracking.db",
        macro=path / "macro" / "macro.db",
        strategy_selection=path / "strategy_selection",
        continuity_state=path / "continuity" / "runtime_state.json",
    )


def _holding(path: Path, stock: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        for table in REQUIRED_HOLDINGS_TABLES:
            if table == "holding_position":
                cols = "id TEXT PRIMARY KEY, monitored_stock_id TEXT, position_account_id TEXT, status TEXT"
            elif table == "holding_management_plan":
                cols = "id TEXT PRIMARY KEY,position_id TEXT,status TEXT"
            elif table == "stock_analysis_day":
                cols = "id TEXT PRIMARY KEY,current_revision_id TEXT"
            elif table == "stock_analysis_revision":
                cols = "id TEXT PRIMARY KEY,analysis_day_id TEXT"
            else:
                cols = "id TEXT PRIMARY KEY"
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table}({cols})")
        conn.execute("INSERT INTO monitored_stock(id) VALUES(?)", (stock,))


def _sim(path: Path, item: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS simulation_schema_meta(key TEXT PRIMARY KEY,value TEXT)")
        conn.execute("INSERT OR REPLACE INTO simulation_schema_meta VALUES('schema_version','3')")
        conn.execute("CREATE TABLE IF NOT EXISTS simulation_portfolio(id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO simulation_portfolio VALUES(?)", (item,))


def _tracking(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS tracking_meta(key TEXT PRIMARY KEY,value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS tracked_recommendation(id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS recommendation_performance(id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO tracked_recommendation(id) VALUES(?)", (name,))


def _ids(path: Path, table: str) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {str(x[0]) for x in conn.execute(f"SELECT id FROM {table}")}


def _fake_backup(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = root / "backup"
    folder.mkdir(parents=True)
    (folder / "backup_manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("tools.runtime.local_reconcile.create_backup", lambda: folder)


def test_both_approved_domains_survive_and_are_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = tmp_path / "drive"
    a, b = _pc(tmp_path / "remote"), _pc(tmp_path / "chosen")
    configure_transport(shared, locations=a)
    configure_transport(shared, locations=b)
    _holding(a.holdings, "base-stock")
    _sim(a.simulation, "base-sim")
    post_sync(locations=a)
    assert set(pre_sync(locations=b)["installed"]) == {"holdings", "simulation"}
    _holding(a.holdings, "discard-stock")
    _sim(a.simulation, "discard-sim")
    post_sync(locations=a)
    _holding(b.holdings, "keep-stock")
    _sim(b.simulation, "keep-sim")
    disable_transport(locations=b)
    _fake_backup(tmp_path, monkeypatch)

    result = reconcile_local(locations=b, dry_run=True)
    assert result["prefer_local"] == ["holdings", "simulation"]
    finished = reconcile_local(locations=b, confirm=True)
    assert finished["status"] == "PUBLISHED"
    assert _ids(b.holdings, "monitored_stock") == {"base-stock", "keep-stock"}
    assert _ids(b.simulation, "simulation_portfolio") == {"base-sim", "keep-sim"}
    imported = pre_sync(locations=a)
    assert set(imported["installed"]) == {"holdings", "simulation"}
    assert _ids(a.holdings, "monitored_stock") == {"base-stock", "keep-stock"}
    assert _ids(a.simulation, "simulation_portfolio") == {"base-sim", "keep-sim"}


def test_tracking_difference_blocks_unapproved_override(tmp_path: Path) -> None:
    shared = tmp_path / "drive"
    a, b = _pc(tmp_path / "remote"), _pc(tmp_path / "chosen")
    configure_transport(shared, locations=a)
    configure_transport(shared, locations=b)
    _sim(a.simulation, "base")
    _tracking(a.tracking, "same")
    post_sync(locations=a)
    assert set(pre_sync(locations=b)["installed"]) == {"tracking", "simulation"}
    _sim(a.simulation, "remote")
    post_sync(locations=a)
    _sim(b.simulation, "chosen")
    _tracking(b.tracking, "different")
    disable_transport(locations=b)
    with pytest.raises(DataToolError, match="UNAPPROVED_DOMAIN_CONFLICT"):
        reconcile_local(locations=b, domains=["simulation"], dry_run=True)
    assert _ids(b.tracking, "tracked_recommendation") == {"same", "different"}
