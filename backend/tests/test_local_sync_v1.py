from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tools.data.common import DataToolError
from tools.dev import sync_local


def _fake_paths(tmp_path: Path) -> sync_local.RuntimePaths:
    return sync_local.RuntimePaths(
        holdings=tmp_path / "holdings.db",
        market=tmp_path / "market.db",
        simulation=tmp_path / "simulation.db",
    )


def test_registry_order_is_explicit_and_stable():
    assert [spec.key for spec in sync_local.MIGRATIONS] == [
        "VN-P1-S1",
        "VN-P1-S2",
        "VN-P2-S1",
        "VN-P2-S2",
        "VN-P3-S1",
        "VN-P3-S2",
        "VN-P4-S1",
        "VN-P5-S1",
        "VN-P6-S1",
    ]


def test_all_current_skips_backup_and_migration(monkeypatch, tmp_path: Path):
    paths = _fake_paths(tmp_path)
    calls = {"run": 0, "backup": 0}

    def detect(_):
        return sync_local.MigrationStatus(
            "TEST",
            "Test Migration",
            sync_local.MigrationState.CURRENT,
        )

    def run(_):
        calls["run"] += 1
        return {}

    spec = sync_local.MigrationSpec("TEST", "Test Migration", detect, run)
    monkeypatch.setattr(sync_local, "MIGRATIONS", (spec,))
    monkeypatch.setattr(
        sync_local,
        "final_verify",
        lambda _: {"governance": {"operating_strategies": 10}},
    )

    def backup():
        calls["backup"] += 1
        return tmp_path / "backup"

    result = sync_local.sync_runtime(
        paths=paths,
        backup_factory=backup,
    )

    assert calls == {"run": 0, "backup": 0}
    assert result["backup"] is None
    assert result["migrated"] == []
    assert result["statuses"][0]["state"] == "CURRENT"


def test_missing_migration_backs_up_once_then_migrates(monkeypatch, tmp_path: Path):
    paths = _fake_paths(tmp_path)
    state = {"current": False, "run": 0, "backup": 0}

    def detect(_):
        return sync_local.MigrationStatus(
            "TEST",
            "Test Migration",
            (
                sync_local.MigrationState.CURRENT
                if state["current"]
                else sync_local.MigrationState.MISSING
            ),
        )

    def run(_):
        state["run"] += 1
        state["current"] = True
        return {"safe": True}

    spec = sync_local.MigrationSpec("TEST", "Test Migration", detect, run)
    monkeypatch.setattr(sync_local, "MIGRATIONS", (spec,))
    monkeypatch.setattr(
        sync_local,
        "final_verify",
        lambda _: {"governance": {"operating_strategies": 10}},
    )

    def backup():
        state["backup"] += 1
        return tmp_path / "backup"

    result = sync_local.sync_runtime(
        paths=paths,
        backup_factory=backup,
    )

    assert state["backup"] == 1
    assert state["run"] == 1
    assert result["migrated"][0]["key"] == "TEST"
    assert result["statuses"][0]["state"] == "CURRENT"


def test_check_only_never_backs_up_or_migrates(monkeypatch, tmp_path: Path):
    paths = _fake_paths(tmp_path)
    calls = {"run": 0, "backup": 0}

    def detect(_):
        return sync_local.MigrationStatus(
            "TEST",
            "Test Migration",
            sync_local.MigrationState.MISSING,
        )

    def run(_):
        calls["run"] += 1
        return {}

    monkeypatch.setattr(
        sync_local,
        "MIGRATIONS",
        (sync_local.MigrationSpec("TEST", "Test Migration", detect, run),),
    )

    def backup():
        calls["backup"] += 1
        return tmp_path / "backup"

    result = sync_local.sync_runtime(
        paths=paths,
        check_only=True,
        backup_factory=backup,
    )

    assert calls == {"run": 0, "backup": 0}
    assert result["check_only"] is True
    assert result["statuses"][0]["state"] == "MISSING"


@pytest.mark.parametrize(
    "blocked_state",
    [
        sync_local.MigrationState.PARTIAL,
        sync_local.MigrationState.INCOMPATIBLE,
        sync_local.MigrationState.PREREQUISITE_MISSING,
    ],
)
def test_unsafe_state_blocks_before_backup(
    monkeypatch,
    tmp_path: Path,
    blocked_state: sync_local.MigrationState,
):
    paths = _fake_paths(tmp_path)
    calls = {"backup": 0, "run": 0}

    def detect(_):
        return sync_local.MigrationStatus(
            "TEST",
            "Test Migration",
            blocked_state,
            "fixture",
        )

    def run(_):
        calls["run"] += 1
        return {}

    monkeypatch.setattr(
        sync_local,
        "MIGRATIONS",
        (sync_local.MigrationSpec("TEST", "Test Migration", detect, run),),
    )

    def backup():
        calls["backup"] += 1
        return tmp_path / "backup"

    with pytest.raises(DataToolError, match="Local Sync blocked"):
        sync_local.sync_runtime(paths=paths, backup_factory=backup)

    assert calls == {"backup": 0, "run": 0}


def test_backup_failure_prevents_migration(monkeypatch, tmp_path: Path):
    paths = _fake_paths(tmp_path)
    state = {"run": 0}

    def detect(_):
        return sync_local.MigrationStatus(
            "TEST",
            "Test Migration",
            sync_local.MigrationState.MISSING,
        )

    def run(_):
        state["run"] += 1
        return {}

    monkeypatch.setattr(
        sync_local,
        "MIGRATIONS",
        (sync_local.MigrationSpec("TEST", "Test Migration", detect, run),),
    )

    def fail_backup():
        raise DataToolError("backup fixture failed")

    with pytest.raises(DataToolError, match="backup fixture failed"):
        sync_local.sync_runtime(paths=paths, backup_factory=fail_backup)

    assert state["run"] == 0


def test_schema_detector_distinguishes_missing_partial_and_incompatible(tmp_path: Path):
    db = tmp_path / "schema.db"
    sqlite3.connect(db).close()

    state, _ = sync_local._one_db_state(
        path=db,
        expected_tables={"meta", "data"},
        required_base=set(),
        meta_table="meta",
        expected_version="V1",
    )
    assert state is sync_local.MigrationState.MISSING

    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        conn.execute("INSERT INTO meta VALUES('schema_version','V1')")

    state, _ = sync_local._one_db_state(
        path=db,
        expected_tables={"meta", "data"},
        required_base=set(),
        meta_table="meta",
        expected_version="V1",
    )
    assert state is sync_local.MigrationState.PARTIAL

    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE data(id INTEGER)")
        conn.execute(
            "UPDATE meta SET value='OLD' WHERE key='schema_version'"
        )

    state, _ = sync_local._one_db_state(
        path=db,
        expected_tables={"meta", "data"},
        required_base=set(),
        meta_table="meta",
        expected_version="V1",
    )
    assert state is sync_local.MigrationState.INCOMPATIBLE


def test_dorm_pc_case_p5_missing_p6_current_is_repaired_without_rewriting_p6(
    tmp_path: Path,
):
    simulation = tmp_path / "simulation.db"
    sqlite3.connect(simulation).close()

    sync_local.p2s2.migrate_prospective(simulation_db=simulation)
    sync_local.p6s1.migrate_event_evidence(simulation_db=simulation)

    paths = sync_local.RuntimePaths(
        holdings=tmp_path / "unused-holdings.db",
        market=tmp_path / "unused-market.db",
        simulation=simulation,
    )
    p5 = next(spec for spec in sync_local.MIGRATIONS if spec.key == "VN-P5-S1")
    p6 = next(spec for spec in sync_local.MIGRATIONS if spec.key == "VN-P6-S1")

    assert p5.detect(paths).state is sync_local.MigrationState.MISSING
    assert p6.detect(paths).state is sync_local.MigrationState.CURRENT

    with sqlite3.connect(simulation) as conn:
        before_p6_tables = {
            row[0]: conn.execute(f"SELECT COUNT(*) FROM {row[0]}").fetchone()[0]
            for row in conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name LIKE 'event_evidence_%'
                ORDER BY name
                """
            ).fetchall()
        }

    result = p5.run(paths)
    assert result["production_selection_policy_changed"] is False
    assert result["no_trade_registered"] is False
    assert p5.detect(paths).state is sync_local.MigrationState.CURRENT
    assert p6.detect(paths).state is sync_local.MigrationState.CURRENT

    with sqlite3.connect(simulation) as conn:
        after_p6_tables = {
            row[0]: conn.execute(f"SELECT COUNT(*) FROM {row[0]}").fetchone()[0]
            for row in conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name LIKE 'event_evidence_%'
                ORDER BY name
                """
            ).fetchall()
        }
        operating = conn.execute(
            """
            SELECT COUNT(*) FROM strategy_registry_version
            WHERE operational_status='OPERATING'
            """
        ).fetchone()[0]

    assert before_p6_tables == after_p6_tables
    assert operating == 10


def test_launcher_contracts_are_safe_and_one_click():
    root = Path(__file__).resolve().parents[2]
    ps = (root / "sync_local.ps1").read_text(encoding="utf-8")
    cmd = (root / "sync_local.cmd").read_text(encoding="utf-8")

    assert 'if ($branch -ne "main")' in ps
    assert "git status --porcelain --untracked-files=no" in ps
    assert "git ls-files --others --exclude-standard" in ps
    assert "git fetch origin main" in ps
    assert "git pull --ff-only origin main" in ps
    assert ".venv\\Scripts\\python.exe" in ps
    assert "tools\\dev\\sync_local.py" in ps
    assert "git stash" not in ps
    assert "reset --hard" not in ps
    assert "git rebase" not in ps
    assert "--force" not in ps.lower()

    assert "sync_local.ps1" in cmd
    assert "ExecutionPolicy Bypass" in cmd
    assert "pause" in cmd.lower()
