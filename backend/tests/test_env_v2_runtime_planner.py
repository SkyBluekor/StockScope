from __future__ import annotations

from pathlib import Path

import tools.dev.sync_local as sync
import tools.dev.sync_macro_artifacts as macro_sync


def _status(
    key: str,
    state: sync.MigrationState,
    *,
    label: str | None = None,
    detail: str = "",
) -> sync.MigrationStatus:
    return sync.MigrationStatus(
        key=key,
        label=label or key,
        state=state,
        detail=detail,
    )


def test_school_pc_plan_is_partial_not_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = sync.RuntimePaths(
        holdings=tmp_path / "holdings.db",
        market=tmp_path / "market.db",
        simulation=tmp_path / "missing-simulation.db",
    )
    statuses = [
        _status("VN-P2-S1", sync.MigrationState.PREREQUISITE_MISSING),
        _status("VN-P2-S2", sync.MigrationState.PREREQUISITE_MISSING),
        _status("VN-P3-S1", sync.MigrationState.MISSING),
        _status("VN-P3-S2", sync.MigrationState.PREREQUISITE_MISSING),
        _status("VN-P4-S1", sync.MigrationState.PREREQUISITE_MISSING),
        _status("VN-P4-S2", sync.MigrationState.MISSING),
        _status("VN-P5-S1", sync.MigrationState.PREREQUISITE_MISSING),
        _status("VN-P6-S1", sync.MigrationState.PREREQUISITE_MISSING),
        _status("NEXT-6E-S3", sync.MigrationState.PREREQUISITE_MISSING),
    ]
    monkeypatch.setattr(sync, "inspect_all", lambda _: statuses)

    plan = sync.build_runtime_plan(paths)
    by_key = {item["key"]: item for item in plan["statuses"]}

    assert plan["environment"] == "PARTIAL_RUNTIME"
    assert by_key["VN-P3-S1"]["plan"] == "APPLY"
    assert by_key["VN-P3-S2"]["plan"] == "APPLY_AFTER:VN-P3-S1"
    assert by_key["VN-P4-S1"]["plan"] == "APPLY_AFTER:VN-P3-S1"
    assert by_key["VN-P4-S2"]["plan"] == "APPLY_AFTER:VN-P4-S1"
    assert by_key["VN-P2-S1"]["plan"] == "WAITING_FOR_SIMULATION_RESTORE"
    assert by_key["VN-P2-S2"]["plan"] == "WAITING_FOR_SIMULATION_RESTORE"
    assert by_key["VN-P5-S1"]["plan"] == "WAITING_FOR_SIMULATION_RESTORE"
    assert by_key["VN-P6-S1"]["plan"] == "WAITING_FOR_SIMULATION_RESTORE"
    assert by_key["NEXT-6E-S3"]["plan"] == "WAITING_FOR_SIMULATION_RESTORE"


def test_sync_rechecks_prerequisite_after_earlier_migration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = {
        "VN-P3-S1": sync.MigrationState.MISSING,
        "VN-P3-S2": sync.MigrationState.PREREQUISITE_MISSING,
    }
    run_order: list[str] = []

    def detect_p3s1(paths: sync.RuntimePaths) -> sync.MigrationStatus:
        del paths
        return _status("VN-P3-S1", state["VN-P3-S1"])

    def run_p3s1(paths: sync.RuntimePaths) -> dict[str, object]:
        del paths
        run_order.append("VN-P3-S1")
        state["VN-P3-S1"] = sync.MigrationState.CURRENT
        state["VN-P3-S2"] = sync.MigrationState.MISSING
        return {"status": "MIGRATED"}

    def detect_p3s2(paths: sync.RuntimePaths) -> sync.MigrationStatus:
        del paths
        return _status("VN-P3-S2", state["VN-P3-S2"])

    def run_p3s2(paths: sync.RuntimePaths) -> dict[str, object]:
        del paths
        run_order.append("VN-P3-S2")
        state["VN-P3-S2"] = sync.MigrationState.CURRENT
        return {"status": "MIGRATED"}

    specs = (
        sync.MigrationSpec("VN-P3-S1", "Decision", detect_p3s1, run_p3s1),
        sync.MigrationSpec("VN-P3-S2", "Recovery", detect_p3s2, run_p3s2),
    )
    monkeypatch.setattr(sync, "MIGRATIONS", specs)
    monkeypatch.setattr(
        sync,
        "final_verify",
        lambda _: {"governance": {"operating_strategies": None}},
    )

    backups: list[Path] = []

    def backup_factory() -> Path:
        path = tmp_path / "backup"
        backups.append(path)
        return path

    result = sync.sync_runtime(
        paths=sync.RuntimePaths(
            holdings=tmp_path / "holdings.db",
            market=tmp_path / "market.db",
            simulation=tmp_path / "simulation.db",
        ),
        backup_factory=backup_factory,
    )

    assert run_order == ["VN-P3-S1", "VN-P3-S2"]
    assert len(backups) == 1
    assert [item["key"] for item in result["migrated"]] == run_order
    assert result["environment"] == "CURRENT"


def test_missing_simulation_is_deferred_while_other_domain_migrates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = {
        "VN-P2-S1": sync.MigrationState.PREREQUISITE_MISSING,
        "VN-P3-S1": sync.MigrationState.MISSING,
    }
    ran: list[str] = []

    def detect_feedback(paths: sync.RuntimePaths) -> sync.MigrationStatus:
        del paths
        return _status("VN-P2-S1", state["VN-P2-S1"])

    def detect_decision(paths: sync.RuntimePaths) -> sync.MigrationStatus:
        del paths
        return _status("VN-P3-S1", state["VN-P3-S1"])

    def run_feedback(paths: sync.RuntimePaths) -> dict[str, object]:
        raise AssertionError("Simulation migration must not run without simulation DB")

    def run_decision(paths: sync.RuntimePaths) -> dict[str, object]:
        del paths
        ran.append("VN-P3-S1")
        state["VN-P3-S1"] = sync.MigrationState.CURRENT
        return {"status": "MIGRATED"}

    specs = (
        sync.MigrationSpec("VN-P2-S1", "Feedback", detect_feedback, run_feedback),
        sync.MigrationSpec("VN-P3-S1", "Decision", detect_decision, run_decision),
    )
    monkeypatch.setattr(sync, "MIGRATIONS", specs)
    monkeypatch.setattr(
        sync,
        "final_verify",
        lambda _: {"governance": {"operating_strategies": None}},
    )

    result = sync.sync_runtime(
        paths=sync.RuntimePaths(
            holdings=tmp_path / "holdings.db",
            market=tmp_path / "market.db",
            simulation=tmp_path / "missing.db",
        ),
        backup_factory=lambda: tmp_path / "backup",
    )

    assert ran == ["VN-P3-S1"]
    assert result["deferred"] == ["VN-P2-S1"]
    assert result["environment"] == "PARTIAL_RUNTIME"


def test_check_only_never_invokes_backup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sync,
        "inspect_all",
        lambda _: [_status("VN-P3-S1", sync.MigrationState.MISSING)],
    )

    def forbidden_backup() -> Path:
        raise AssertionError("check-only must not create a backup")

    result = sync.sync_runtime(
        paths=sync.RuntimePaths(
            holdings=tmp_path / "holdings.db",
            market=tmp_path / "market.db",
            simulation=tmp_path / "missing.db",
        ),
        check_only=True,
        backup_factory=forbidden_backup,
    )
    assert result["check_only"] is True
    assert result["statuses"][0]["plan"] == "APPLY"


def test_next6e_s3_is_registered_in_local_sync() -> None:
    by_key = {spec.key: spec for spec in sync.MIGRATIONS}
    assert "NEXT-6E-S3" in by_key
    assert sync.MIGRATION_DEPENDENCIES["NEXT-6E-S3"] == ("VN-P2-S2",)
    assert "NEXT-6E-S3" in sync.SIMULATION_REQUIRED_MIGRATIONS


def test_macro_check_only_does_not_create_directory(tmp_path: Path) -> None:
    missing = tmp_path / "calibration-does-not-exist"

    result = macro_sync.sync_macro_artifacts(
        calibration_dir=missing,
        check_only=True,
    )

    assert result["check_only"] is True
    assert not missing.exists()
