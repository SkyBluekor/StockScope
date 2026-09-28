from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from tools.data.backup_runtime import create_backup
from tools.data.common import (
    DataToolError,
    holdings_db_path,
    market_db_path,
    simulation_db_path,
    sqlite_readonly,
    validate_holdings_db,
    validate_market_db,
    validate_simulation_db,
)
from tools.data.event_evidence_runtime import inspect_event_evidence_store
from tools.data import migrate_input_identity_vnp1s1 as p1s1
from tools.data import migrate_horizon_context_vnp1s2 as p1s2
from tools.data import migrate_feedback_vnp2s1 as p2s1
from tools.data import migrate_prospective_vnp2s2 as p2s2
from tools.data import migrate_holdings_decision_vnp3s1 as p3s1
from tools.data import migrate_holdings_recovery_vnp3s2 as p3s2
from tools.data import migrate_watch_vnp4s1 as p4s1
from tools.data import migrate_strategy_governance_vnp5s1 as p5s1
from tools.data import migrate_event_evidence_vnp6s1 as p6s1
from tools.data import migrate_policy_identity_next1 as next1


SYNC_VERSION = "LOCAL_SYNC_V1"
LOG_DIR = ROOT / "logs" / "local_sync"


class MigrationState(str, Enum):
    CURRENT = "CURRENT"
    MISSING = "MISSING"
    PARTIAL = "PARTIAL"
    INCOMPATIBLE = "INCOMPATIBLE"
    PREREQUISITE_MISSING = "PREREQUISITE_MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    holdings: Path
    market: Path
    simulation: Path

    @classmethod
    def current(cls) -> "RuntimePaths":
        return cls(
            holdings=Path(holdings_db_path()),
            market=Path(market_db_path()),
            simulation=Path(simulation_db_path()),
        )


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    key: str
    label: str
    state: MigrationState
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MigrationSpec:
    key: str
    label: str
    detect: Callable[[RuntimePaths], MigrationStatus]
    run: Callable[[RuntimePaths], dict[str, Any]]


def _tables(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    with sqlite_readonly(path) as conn:
        return {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }


def _meta_value(path: Path, table: str, key: str = "schema_version") -> str | None:
    if not path.is_file():
        return None
    with sqlite_readonly(path) as conn:
        try:
            row = conn.execute(
                f"SELECT value FROM {table} WHERE key=?",
                (key,),
            ).fetchone()
        except sqlite3.Error:
            return None
    return None if row is None else str(row[0])


def _one_db_state(
    *,
    path: Path,
    expected_tables: set[str],
    required_base: set[str],
    meta_table: str | None,
    expected_version: str | None,
) -> tuple[MigrationState, str]:
    if not path.is_file():
        return (
            MigrationState.PREREQUISITE_MISSING,
            f"DB missing: {path}",
        )
    names = _tables(path)
    missing_base = sorted(required_base - names)
    if missing_base:
        return (
            MigrationState.PREREQUISITE_MISSING,
            "missing base tables: " + ", ".join(missing_base),
        )

    present = expected_tables & names
    if not present:
        return MigrationState.MISSING, ""
    if present != expected_tables:
        missing = sorted(expected_tables - names)
        return (
            MigrationState.PARTIAL,
            "partial tables; missing: " + ", ".join(missing),
        )
    if meta_table and expected_version:
        actual = _meta_value(path, meta_table)
        if actual != expected_version:
            return (
                MigrationState.INCOMPATIBLE,
                f"{meta_table}.schema_version={actual!r}, expected={expected_version!r}",
            )
    return MigrationState.CURRENT, ""


def _optional_db_state(
    *,
    path: Path,
    expected_tables: set[str],
    required_base: set[str],
    meta_table: str | None,
    expected_version: str | None,
) -> tuple[MigrationState, str]:
    """Inspect a migration component whose owning runtime domain is optional.

    If no migration tables exist and the domain's full base schema is not
    initialized on this PC, the component is not applicable rather than
    broken. Any partial migration artifacts still fail closed.
    """
    if not path.is_file():
        return MigrationState.NOT_APPLICABLE, f"optional DB missing: {path}"

    names = _tables(path)
    present = expected_tables & names
    if present:
        if present != expected_tables:
            missing = sorted(expected_tables - names)
            return (
                MigrationState.PARTIAL,
                "partial tables; missing: " + ", ".join(missing),
            )
        if meta_table and expected_version:
            actual = _meta_value(path, meta_table)
            if actual != expected_version:
                return (
                    MigrationState.INCOMPATIBLE,
                    f"{meta_table}.schema_version={actual!r}, expected={expected_version!r}",
                )
        return MigrationState.CURRENT, ""

    missing_base = sorted(required_base - names)
    if missing_base:
        return (
            MigrationState.NOT_APPLICABLE,
            "optional runtime domain not initialized; missing base tables: "
            + ", ".join(missing_base),
        )
    return MigrationState.MISSING, ""


def _combine(
    key: str,
    label: str,
    parts: list[tuple[str, tuple[MigrationState, str]]],
) -> MigrationStatus:
    states = [state for _, (state, _) in parts]
    details = [
        f"{name}: {detail}"
        for name, (state, detail) in parts
        if detail and state is not MigrationState.CURRENT
    ]
    if any(state is MigrationState.PREREQUISITE_MISSING for state in states):
        state = MigrationState.PREREQUISITE_MISSING
    elif any(state is MigrationState.INCOMPATIBLE for state in states):
        state = MigrationState.INCOMPATIBLE
    elif any(state is MigrationState.PARTIAL for state in states):
        state = MigrationState.PARTIAL
    else:
        applicable = [
            state for state in states
            if state is not MigrationState.NOT_APPLICABLE
        ]
        if not applicable:
            state = MigrationState.NOT_APPLICABLE
        elif any(state is MigrationState.MISSING for state in applicable):
            state = MigrationState.MISSING
        elif all(state is MigrationState.CURRENT for state in applicable):
            state = MigrationState.CURRENT
        else:
            state = MigrationState.PARTIAL
            if not details:
                details.append("migration state differs across runtime DBs")
    return MigrationStatus(key, label, state, "; ".join(details))


def _component_result(
    state: tuple[MigrationState, str],
    migrate: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    migration_state, detail = state
    if migration_state is MigrationState.MISSING:
        return migrate()
    if migration_state is MigrationState.CURRENT:
        return {"status": "CURRENT"}
    if migration_state is MigrationState.NOT_APPLICABLE:
        return {"status": "SKIPPED_NOT_APPLICABLE", "detail": detail}
    raise DataToolError(
        f"Migration component state is not safe to run: "
        f"{migration_state.value} {detail}"
    )


def _p1s1_parts(paths: RuntimePaths) -> dict[str, tuple[MigrationState, str]]:
    return {
        "market": _one_db_state(
            path=paths.market,
            expected_tables={"input_identity_meta", "input_change_generation"},
            required_base={"stock_daily", "main_index_daily", "day_status"},
            meta_table="input_identity_meta",
            expected_version=p1s1.INPUT_IDENTITY_SCHEMA_VERSION,
        ),
        "holdings": _one_db_state(
            path=paths.holdings,
            expected_tables={p1s1.PROOF_TABLE},
            required_base={
                "stock_analysis_day", "stock_analysis_revision", "monitored_stock"
            },
            meta_table=None,
            expected_version=None,
        ),
        "simulation": _optional_db_state(
            path=paths.simulation,
            expected_tables={p1s1.VALIDATION_PROOF_TABLE},
            required_base={"historical_validation_run", "historical_validation_day"},
            meta_table=None,
            expected_version=None,
        ),
    }


def _p1s2_parts(paths: RuntimePaths) -> dict[str, tuple[MigrationState, str]]:
    return {
        "holdings": _one_db_state(
            path=paths.holdings,
            expected_tables={
                p1s2.HORIZON_META_TABLE,
                p1s2.ANALYSIS_HORIZON_TABLE,
                p1s2.PLAN_HORIZON_TABLE,
            },
            required_base={"stock_analysis_revision", "holding_management_plan"},
            meta_table=p1s2.HORIZON_META_TABLE,
            expected_version=p1s2.HORIZON_SCHEMA_VERSION,
        ),
        "simulation": _optional_db_state(
            path=paths.simulation,
            expected_tables={
                p1s2.HORIZON_META_TABLE,
                p1s2.VALIDATION_HORIZON_TABLE,
                p1s2.EXECUTION_HORIZON_TABLE,
            },
            required_base={"historical_validation_run", "historical_execution_run"},
            meta_table=p1s2.HORIZON_META_TABLE,
            expected_version=p1s2.HORIZON_SCHEMA_VERSION,
        ),
    }


def _run_p1s1(paths: RuntimePaths) -> dict[str, Any]:
    parts = _p1s1_parts(paths)
    return {
        "market": _component_result(
            parts["market"], lambda: p1s1.migrate_market_store(paths.market)
        ),
        "holdings": _component_result(
            parts["holdings"], lambda: p1s1.migrate_holdings(paths.holdings)
        ),
        "simulation": _component_result(
            parts["simulation"], lambda: p1s1.migrate_simulation(paths.simulation)
        ),
    }


def _run_p1s2(paths: RuntimePaths) -> dict[str, Any]:
    parts = _p1s2_parts(paths)
    return {
        "holdings": _component_result(
            parts["holdings"], lambda: p1s2.migrate_holdings_horizon(paths.holdings)
        ),
        "simulation": _component_result(
            parts["simulation"],
            lambda: p1s2.migrate_simulation_horizon(paths.simulation),
        ),
    }



def _detect_p1s1(paths: RuntimePaths) -> MigrationStatus:
    parts = _p1s1_parts(paths)
    return _combine(
        "VN-P1-S1",
        "Input Identity",
        [(name, state) for name, state in parts.items()],
    )


def _detect_p1s2(paths: RuntimePaths) -> MigrationStatus:
    parts = _p1s2_parts(paths)
    return _combine(
        "VN-P1-S2",
        "Horizon Context",
        [(name, state) for name, state in parts.items()],
    )


def _simple_detector(
    key: str,
    label: str,
    *,
    db_attr: str,
    expected_tables: set[str],
    required_base: set[str],
    meta_table: str,
    expected_version: str,
) -> Callable[[RuntimePaths], MigrationStatus]:
    def detect(paths: RuntimePaths) -> MigrationStatus:
        path = Path(getattr(paths, db_attr))
        state, detail = _one_db_state(
            path=path,
            expected_tables=expected_tables,
            required_base=required_base,
            meta_table=meta_table,
            expected_version=expected_version,
        )
        return MigrationStatus(key, label, state, detail)

    return detect


def _detect_p6(paths: RuntimePaths) -> MigrationStatus:
    if not paths.simulation.is_file():
        return MigrationStatus(
            "VN-P6-S1",
            "Event Evidence",
            MigrationState.PREREQUISITE_MISSING,
            f"DB missing: {paths.simulation}",
        )
    try:
        state = inspect_event_evidence_store(paths.simulation)
    except DataToolError as exc:
        message = str(exc)
        kind = (
            MigrationState.PARTIAL
            if "부분 migration" in message or "schema" in message
            else MigrationState.INCOMPATIBLE
        )
        return MigrationStatus("VN-P6-S1", "Event Evidence", kind, message)
    if not state.get("present"):
        return MigrationStatus(
            "VN-P6-S1",
            "Event Evidence",
            MigrationState.MISSING,
        )
    return MigrationStatus(
        "VN-P6-S1",
        "Event Evidence",
        MigrationState.CURRENT,
    )


def _detect_next1(paths: RuntimePaths) -> MigrationStatus:
    state = next1.inspect_policy_identity(paths.simulation)
    if not state.get("applicable"):
        return MigrationStatus(
            "NEXT-1",
            "Policy Identity",
            MigrationState.CURRENT,
            str(state.get("reason") or "optional runtime domain not initialized"),
        )
    if state.get("current"):
        return MigrationStatus(
            "NEXT-1",
            "Policy Identity",
            MigrationState.CURRENT,
        )
    validation_missing = list(state.get("validation_missing_columns") or [])
    execution_missing = list(state.get("execution_missing_columns") or [])
    partial = (
        (0 < len(validation_missing) < len(next1.PIN_COLUMNS))
        or (0 < len(execution_missing) < len(next1.PIN_COLUMNS))
    )
    return MigrationStatus(
        "NEXT-1",
        "Policy Identity",
        MigrationState.PARTIAL if partial else MigrationState.MISSING,
        (
            f"validation missing={validation_missing}; "
            f"execution missing={execution_missing}; "
            f"meta_current={state.get('meta_current')}"
        ),
    )


def _run_p2s1(paths: RuntimePaths) -> dict[str, Any]:
    return p2s1.migrate_feedback(simulation_db=paths.simulation)


def _run_p2s2(paths: RuntimePaths) -> dict[str, Any]:
    return p2s2.migrate_prospective(simulation_db=paths.simulation)


def _run_p3s1(paths: RuntimePaths) -> dict[str, Any]:
    return p3s1.migrate_holdings_decision(holdings_db=paths.holdings)


def _run_p3s2(paths: RuntimePaths) -> dict[str, Any]:
    return p3s2.migrate_holdings_recovery(holdings_db=paths.holdings)


def _run_p4s1(paths: RuntimePaths) -> dict[str, Any]:
    return p4s1.migrate_watch(holdings_db=paths.holdings)


def _run_p5s1(paths: RuntimePaths) -> dict[str, Any]:
    result = p5s1.migrate_strategy_governance(simulation_db=paths.simulation)
    if result.get("production_selection_policy_changed") is not False:
        raise DataToolError(
            "VN-P5-S1 migration이 Production Selection Policy를 변경했습니다."
        )
    if result.get("performance_validation_backfill_performed") is not False:
        raise DataToolError(
            "VN-P5-S1 migration이 성능 검증 backfill을 수행했습니다."
        )
    if result.get("no_trade_registered") is not False:
        raise DataToolError("VN-P5-S1 migration이 NO_TRADE를 Strategy로 등록했습니다.")
    return result


def _run_next1(paths: RuntimePaths) -> dict[str, Any]:
    result = next1.migrate_policy_identity(paths.simulation)
    if result.get("historical_policy_backfill_performed") is not False:
        raise DataToolError(
            "NEXT-1 migration이 legacy Selection Policy를 backfill했습니다."
        )
    if result.get("completed_run_rewrite_performed") is not False:
        raise DataToolError(
            "NEXT-1 migration이 완료된 Historical run을 rewrite했습니다."
        )
    if int(result.get("external_network_requests", -1)) != 0:
        raise DataToolError("NEXT-1 migration에서 외부 network request가 발생했습니다.")
    return result


def _run_p6s1(paths: RuntimePaths) -> dict[str, Any]:
    result = p6s1.migrate_event_evidence(simulation_db=paths.simulation)
    forbidden_true = (
        "historical_backfill_performed",
        "news_backfill_performed",
        "dart_eventrisk_backfill_performed",
        "real_corpus_evaluation_performed",
    )
    for key in forbidden_true:
        if result.get(key) is not False:
            raise DataToolError(f"VN-P6-S1 safety invariant 위반: {key}")
    if int(result.get("external_network_requests", -1)) != 0:
        raise DataToolError("VN-P6-S1 migration에서 외부 network request가 발생했습니다.")
    return result


MIGRATIONS: tuple[MigrationSpec, ...] = (
    MigrationSpec("VN-P1-S1", "Input Identity", _detect_p1s1, _run_p1s1),
    MigrationSpec("VN-P1-S2", "Horizon Context", _detect_p1s2, _run_p1s2),
    MigrationSpec(
        "VN-P2-S1",
        "Feedback",
        _simple_detector(
            "VN-P2-S1",
            "Feedback",
            db_attr="simulation",
            expected_tables={
                "feedback_schema_meta",
                "feedback_source_ref",
                "feedback_cohort",
                "feedback_cohort_source",
                "feedback_cohort_member",
                "feedback_report",
            },
            required_base=set(),
            meta_table="feedback_schema_meta",
            expected_version=p2s1.FEEDBACK_SCHEMA_VERSION,
        ),
        _run_p2s1,
    ),
    MigrationSpec(
        "VN-P2-S2",
        "Prospective",
        _simple_detector(
            "VN-P2-S2",
            "Prospective",
            db_attr="simulation",
            expected_tables={"prospective_schema_meta", *p2s2.TABLE_COLUMNS.keys()},
            required_base=set(),
            meta_table="prospective_schema_meta",
            expected_version=p2s2.PROSPECTIVE_SCHEMA_VERSION,
        ),
        _run_p2s2,
    ),
    MigrationSpec(
        "VN-P3-S1",
        "Holdings Decision",
        _simple_detector(
            "VN-P3-S1",
            "Holdings Decision",
            db_attr="holdings",
            expected_tables=set(p3s1.DECISION_TABLES),
            required_base=set(p3s1.REQUIRED_BASE_TABLES),
            meta_table="holding_decision_schema_meta",
            expected_version=p3s1.HOLDING_DECISION_SCHEMA_VERSION,
        ),
        _run_p3s1,
    ),
    MigrationSpec(
        "VN-P3-S2",
        "Holdings Recovery",
        _simple_detector(
            "VN-P3-S2",
            "Holdings Recovery",
            db_attr="holdings",
            expected_tables=set(p3s2.RECOVERY_TABLES),
            required_base=set(p3s2.REQUIRED_BASE_TABLES),
            meta_table="holding_recovery_schema_meta",
            expected_version=p3s2.RECOVERY_SCHEMA_VERSION,
        ),
        _run_p3s2,
    ),
    MigrationSpec(
        "VN-P4-S1",
        "Holding Watch",
        _simple_detector(
            "VN-P4-S1",
            "Holding Watch",
            db_attr="holdings",
            expected_tables=set(p4s1.WATCH_TABLES),
            required_base=set(p4s1.REQUIRED_BASE_TABLES),
            meta_table="holding_watch_schema_meta",
            expected_version=p4s1.WATCH_SCHEMA_VERSION,
        ),
        _run_p4s1,
    ),
    MigrationSpec(
        "VN-P5-S1",
        "Strategy Governance",
        _simple_detector(
            "VN-P5-S1",
            "Strategy Governance",
            db_attr="simulation",
            expected_tables=set(p5s1.STRATEGY_GOVERNANCE_TABLES),
            required_base=set(p5s1.PROSPECTIVE_REQUIRED_TABLES),
            meta_table="strategy_governance_schema_meta",
            expected_version=p5s1.STRATEGY_GOVERNANCE_SCHEMA_VERSION,
        ),
        _run_p5s1,
    ),
    MigrationSpec("VN-P6-S1", "Event Evidence", _detect_p6, _run_p6s1),
    MigrationSpec("NEXT-1", "Policy Identity", _detect_next1, _run_next1),
)


def inspect_all(paths: RuntimePaths) -> list[MigrationStatus]:
    return [spec.detect(paths) for spec in MIGRATIONS]


def _blocking(statuses: list[MigrationStatus]) -> list[MigrationStatus]:
    return [
        item
        for item in statuses
        if item.state
        in {
            MigrationState.PARTIAL,
            MigrationState.INCOMPATIBLE,
            MigrationState.PREREQUISITE_MISSING,
        }
    ]


def _verify_p5_p6(paths: RuntimePaths) -> dict[str, Any]:
    with sqlite_readonly(paths.simulation) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "strategy_governance_schema_meta" not in names:
            raise DataToolError("Strategy Governance schema가 없습니다.")
        operating = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM strategy_registry_version
                WHERE operational_status='OPERATING'
                """
            ).fetchone()[0]
        )
        no_trade = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM strategy_registry_version
                WHERE UPPER(strategy_key)='NO_TRADE'
                """
            ).fetchone()[0]
        )
        if operating != 10:
            raise DataToolError(
                f"Strategy Governance OPERATING 전략 수가 10이 아닙니다: {operating}"
            )
        if no_trade != 0:
            raise DataToolError("NO_TRADE가 Strategy Registry에 등록되어 있습니다.")

        prediction_enabled = 0
        if "event_evidence_value_gate_decision" in names:
            prediction_enabled = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM event_evidence_value_gate_decision
                    WHERE prediction_eligible<>0
                    """
                ).fetchone()[0]
            )
        if prediction_enabled:
            raise DataToolError(
                "P6 Value Gate에 prediction_eligible=True Decision이 있습니다."
            )
    p6 = inspect_event_evidence_store(paths.simulation)
    if not p6.get("present"):
        raise DataToolError("Event Evidence schema가 없습니다.")
    return {
        "operating_strategies": operating,
        "no_trade_registered": False,
        "event_evidence": "CURRENT",
        "prediction_enabled": False,
    }


def final_verify(paths: RuntimePaths) -> dict[str, Any]:
    holdings = validate_holdings_db(paths.holdings)
    market = validate_market_db(paths.market)
    simulation = validate_simulation_db(paths.simulation)
    governance = _verify_p5_p6(paths)
    statuses = inspect_all(paths)
    not_current = [s for s in statuses if s.state is not MigrationState.CURRENT]
    if not_current:
        raise DataToolError(
            "Migration final verification 실패: "
            + ", ".join(f"{s.key}={s.state.value}" for s in not_current)
        )
    return {
        "holdings": holdings,
        "market": market,
        "simulation": simulation,
        "governance": governance,
    }


def sync_runtime(
    *,
    paths: RuntimePaths | None = None,
    check_only: bool = False,
    backup_factory: Callable[..., Path] = create_backup,
) -> dict[str, Any]:
    runtime = paths or RuntimePaths.current()
    statuses = inspect_all(runtime)
    blocked = _blocking(statuses)
    if blocked:
        raise DataToolError(
            "Local Sync blocked: "
            + " | ".join(
                f"{item.key} {item.state.value}"
                + (f" ({item.detail})" if item.detail else "")
                for item in blocked
            )
        )

    missing = [
        spec
        for spec, status in zip(MIGRATIONS, statuses)
        if status.state is MigrationState.MISSING
    ]
    if check_only:
        return {
            "sync_version": SYNC_VERSION,
            "check_only": True,
            "backup": None,
            "migrated": [],
            "statuses": [
                {
                    "key": item.key,
                    "label": item.label,
                    "state": item.state.value,
                    "detail": item.detail,
                }
                for item in statuses
            ],
        }

    backup_path: Path | None = None
    migrated: list[dict[str, Any]] = []
    if missing:
        backup_path = backup_factory()
        for spec in missing:
            before = spec.detect(runtime)
            if before.state is MigrationState.CURRENT:
                continue
            if before.state is not MigrationState.MISSING:
                raise DataToolError(
                    f"{spec.key} migration 직전 상태가 안전하지 않습니다: "
                    f"{before.state.value} {before.detail}"
                )
            result = spec.run(runtime)
            after = spec.detect(runtime)
            if after.state is not MigrationState.CURRENT:
                raise DataToolError(
                    f"{spec.key} migration 후 CURRENT가 아닙니다: "
                    f"{after.state.value} {after.detail}"
                )
            migrated.append(
                {
                    "key": spec.key,
                    "label": spec.label,
                    "result": result,
                }
            )

    verification = final_verify(runtime)
    final_statuses = inspect_all(runtime)
    return {
        "sync_version": SYNC_VERSION,
        "check_only": False,
        "backup": str(backup_path) if backup_path else None,
        "migrated": migrated,
        "statuses": [
            {
                "key": item.key,
                "label": item.label,
                "state": item.state.value,
                "detail": item.detail,
            }
            for item in final_statuses
        ],
        "verification": verification,
        "secrets": "UNCHANGED",
        "external_network_requests": 0,
    }


def _print_statuses(statuses: list[dict[str, Any]], migrated: set[str]) -> None:
    for item in statuses:
        suffix = ""
        if item["key"] in migrated:
            suffix = " / MIGRATED"
        detail = f"  {item['detail']}" if item.get("detail") else ""
        print(
            f"  {item['key']:<10} {item['label']:<22} "
            f"{item['state']}{suffix}{detail}"
        )


def _print_result(result: dict[str, Any]) -> None:
    print("=" * 78)
    print("STOCKSCOPE LOCAL SYNC")
    print("=" * 78)
    print(f"Mode                    {'CHECK ONLY' if result['check_only'] else 'SYNC'}")
    migrated = {item["key"] for item in result.get("migrated", [])}
    print("")
    print("Runtime migrations")
    _print_statuses(result["statuses"], migrated)
    print("")
    if result["check_only"]:
        missing = [
            item for item in result["statuses"] if item["state"] == "MISSING"
        ]
        print(
            "Action required         "
            + ("YES" if missing else "NO")
        )
        print("DB writes               0")
        print("Backup                  SKIPPED")
        return

    print(
        "Backup                  "
        + (result["backup"] if result.get("backup") else "SKIPPED (all CURRENT)")
    )
    print("Secrets                 UNCHANGED")
    print("External network        0")
    gov = result["verification"]["governance"]
    print(f"Operating strategies    {gov['operating_strategies']}")
    print("NO_TRADE registered     NO")
    print("Prediction              DISABLED")
    print("")
    print("LOCAL ENVIRONMENT READY")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="StockScope existing-PC runtime schema sync/check tool."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="DB를 변경하지 않고 migration 상태만 확인합니다.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = sync_runtime(check_only=args.check_only)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            _print_result(result)
        return 0
    except (DataToolError, sqlite3.Error, OSError) as exc:
        print("=" * 78, file=sys.stderr)
        print("STOCKSCOPE LOCAL SYNC FAILED", file=sys.stderr)
        print("=" * 78, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print("", file=sys.stderr)
        print("No automatic reset/rebase/stash was performed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
