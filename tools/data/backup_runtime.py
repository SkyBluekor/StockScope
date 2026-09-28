from __future__ import annotations

import argparse
import os
import sqlite3
import shutil
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.input_identity import (
    INPUT_IDENTITY_SCHEMA_VERSION,
    PROOF_TABLE,
    VALIDATION_PROOF_TABLE,
)
from app.horizon_context import (
    ANALYSIS_HORIZON_TABLE,
    EXECUTION_HORIZON_TABLE,
    HORIZON_SCHEMA_VERSION,
    PLAN_HORIZON_TABLE,
    VALIDATION_HORIZON_TABLE,
)
from app.feedback.models import FEEDBACK_SCHEMA_VERSION
from app.prospective.models import PROSPECTIVE_SCHEMA_VERSION
from app.holdings.decision_support import HOLDING_DECISION_SCHEMA_VERSION
from app.holdings.recovery import RECOVERY_SCHEMA_VERSION
from app.watch.policy import WATCH_POLICY_CONTRACT_VERSION
from app.watch.storage import WATCH_SCHEMA_VERSION
from app.simulation.strategy_governance import STRATEGY_GOVERNANCE_SCHEMA_VERSION
from app.strategy.production_selection_policy import (
    DEFAULT_RUNTIME_DIR as DEFAULT_STRATEGY_SELECTION_RUNTIME_DIR,
    SELECTION_POLICY_CONTRACT_VERSION,
)

from tools.data.strategy_selection_runtime import (
    copy_strategy_selection_runtime,
    state_file_paths as strategy_selection_state_file_paths,
    validate_strategy_selection_runtime,
)
from tools.data.common import (
    BACKUP_FORMAT_VERSION,
    DEFAULT_BACKUP_ROOT,
    DataToolError,
    git_commit,
    holdings_counts,
    holdings_db_path,
    iso_now,
    manifest_file_entry,
    market_db_path,
    simulation_db_path,
    tracking_db_path,
    project_version,
    secret_like_paths,
    sqlite_snapshot,
    utc_stamp,
    validate_holdings_db,
    validate_market_db,
    validate_simulation_db,
    validate_tracking_db,
    write_json_atomic,
)


def _table_exists(path: Path, table: str) -> bool:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    return row is not None


def _market_generation_ready(path: Path | None) -> bool:
    if path is None or not path.is_file():
        return False
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not {"input_identity_meta", "input_change_generation"}.issubset(tables):
            return False
        row = conn.execute(
            "SELECT value FROM input_identity_meta WHERE key='schema_version'"
        ).fetchone()
    return row is not None and str(row[0]) == INPUT_IDENTITY_SCHEMA_VERSION


def _input_identity_extension(
    holdings_copy: Path,
    market_copy: Path | None,
    simulation_copy: Path | None,
) -> dict[str, object]:
    explicit_proof_store = _table_exists(holdings_copy, PROOF_TABLE)
    revision_identity_metadata = _table_exists(holdings_copy, "stock_analysis_revision")
    market_generation = _market_generation_ready(market_copy)
    validation_proof_store = (
        simulation_copy is not None
        and simulation_copy.is_file()
        and _table_exists(simulation_copy, VALIDATION_PROOF_TABLE)
    )
    return {
        "schema_version": INPUT_IDENTITY_SCHEMA_VERSION,
        "revision_identity_metadata": revision_identity_metadata,
        "explicit_proof_store": explicit_proof_store,
        "market_generation_store": market_generation,
        "validation_input_proof_store": validation_proof_store,
        "current_identity_verification_capability_restorable": (
            revision_identity_metadata and market_generation
        ),
        "note": (
            "분석 revision 자체의 fingerprint/source_versions는 Holdings snapshot에 보존됩니다. "
            "현재 입력 동일성을 다시 판정하려면 같은 시점의 Market generation store도 함께 복원해야 합니다. "
            "explicit proof table은 과거 revision을 명시 검증한 이력을 추가로 보존합니다. "
            "Simulation snapshot이 포함되면 Historical Validation 입력 proof도 함께 보존됩니다."
        ),
    }


FEEDBACK_TABLES = (
    "feedback_schema_meta",
    "feedback_source_ref",
    "feedback_cohort",
    "feedback_cohort_source",
    "feedback_cohort_member",
    "feedback_report",
)


def _feedback_extension(
    simulation_copy: Path | None,
) -> dict[str, object]:
    if simulation_copy is None or not simulation_copy.is_file():
        return {
            "schema_version": FEEDBACK_SCHEMA_VERSION,
            "present": False,
            "tables": [],
            "restorable": False,
        }
    present = [
        table for table in FEEDBACK_TABLES
        if _table_exists(simulation_copy, table)
    ]
    return {
        "schema_version": FEEDBACK_SCHEMA_VERSION,
        "present": bool(present),
        "tables": present,
        "restorable": len(present) == len(FEEDBACK_TABLES),
        "note": (
            "P2-S1 source refs/cohorts/reports live in Simulation DB. "
            "Tracking DB remains a separate read-only evidence source."
        ),
    }


PROSPECTIVE_TABLES = (
    "prospective_schema_meta",
    "prospective_capture_run",
    "prospective_recommendation_sample",
    "prospective_evaluation_protocol",
    "prospective_evaluation_run",
    "prospective_evaluation_unit",
    "prospective_evaluation_report",
)


def _prospective_extension(
    simulation_copy: Path | None,
) -> dict[str, object]:
    if simulation_copy is None or not simulation_copy.is_file():
        return {
            "schema_version": PROSPECTIVE_SCHEMA_VERSION,
            "present": False,
            "tables": [],
            "restorable": False,
        }
    present = [
        table for table in PROSPECTIVE_TABLES
        if _table_exists(simulation_copy, table)
    ]
    return {
        "schema_version": PROSPECTIVE_SCHEMA_VERSION,
        "present": bool(present),
        "tables": present,
        "restorable": len(present) == len(PROSPECTIVE_TABLES),
        "note": (
            "VN-P2-S2 prospective capture, immutable samples, protocols, "
            "evaluation runs/units/reports live in Simulation DB. "
            "Market Store remains the separate local evaluation input owner."
        ),
    }


HOLDING_DECISION_TABLES = (
    "holding_decision_schema_meta",
    "holding_decision_record",
    "holding_decision_resolution",
    "holding_management_plan_context_vnp3s1",
)


def _holding_decision_extension(
    holdings_copy: Path,
) -> dict[str, object]:
    present = [
        table
        for table in HOLDING_DECISION_TABLES
        if _table_exists(holdings_copy, table)
    ]
    return {
        "schema_version": HOLDING_DECISION_SCHEMA_VERSION,
        "present": bool(present),
        "tables": present,
        "restorable": len(present) == len(HOLDING_DECISION_TABLES),
        "note": (
            "P3-S1 decision/resolution/plan-context state lives in holdings.db. "
            "It is restored together with the Holdings ledger; this manifest entry "
            "verifies the optional family is complete."
        ),
    }


HOLDING_RECOVERY_TABLES = (
    "holding_recovery_schema_meta",
    "holding_recovery_review",
    "holding_recovery_assessment",
)


def _holding_recovery_extension(
    holdings_copy: Path,
) -> dict[str, object]:
    present = [
        table
        for table in HOLDING_RECOVERY_TABLES
        if _table_exists(holdings_copy, table)
    ]
    return {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "present": bool(present),
        "tables": present,
        "restorable": len(present) == len(HOLDING_RECOVERY_TABLES),
        "note": (
            "P3-S2 Recovery review and append-only assessment history live in holdings.db. "
            "They are restored with the Holdings ledger; this manifest entry verifies "
            "the optional Recovery family is complete."
        ),
    }


HOLDING_WATCH_TABLES = (
    "holding_watch_schema_meta",
    "holding_watch_setting",
    "holding_watch_rule",
    "holding_watch_episode",
    "holding_watch_coverage_gap",
    "holding_watch_notification_outbox",
)


def _holding_watch_extension(
    holdings_copy: Path,
) -> dict[str, object]:
    present = [
        table
        for table in HOLDING_WATCH_TABLES
        if _table_exists(holdings_copy, table)
    ]
    return {
        "schema_version": WATCH_SCHEMA_VERSION,
        "policy_contract_version": WATCH_POLICY_CONTRACT_VERSION,
        "present": bool(present),
        "tables": present,
        "restorable": len(present) == len(HOLDING_WATCH_TABLES),
        "note": (
            "P4-S1 Watch settings/rules/episodes/coverage gaps/notification outbox "
            "live in holdings.db. Quotes themselves are not backed up; restored Watch "
            "must reacquire live coverage instead of replaying a missing interval."
        ),
    }


STRATEGY_GOVERNANCE_TABLES = (
    "strategy_governance_schema_meta",
    "strategy_registry_version",
    "strategy_evaluation_artifact",
    "strategy_change_proposal",
    "strategy_change_proposal_evidence",
    "strategy_approval_artifact",
)


def _strategy_governance_extension(
    simulation_copy: Path | None,
) -> dict[str, object]:
    if simulation_copy is None or not simulation_copy.is_file():
        return {
            "schema_version": STRATEGY_GOVERNANCE_SCHEMA_VERSION,
            "present": False,
            "tables": [],
            "restorable": False,
        }

    present = [
        table
        for table in STRATEGY_GOVERNANCE_TABLES
        if _table_exists(simulation_copy, table)
    ]
    if present and len(present) != len(STRATEGY_GOVERNANCE_TABLES):
        missing = sorted(set(STRATEGY_GOVERNANCE_TABLES) - set(present))
        raise DataToolError(
            "P5 Strategy Governance가 부분 migration 상태입니다: "
            + ", ".join(missing)
        )

    if present:
        uri = f"file:{simulation_copy.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            row = conn.execute(
                """
                SELECT value FROM strategy_governance_schema_meta
                WHERE key='schema_version'
                """
            ).fetchone()
        if row is None or str(row[0]) != STRATEGY_GOVERNANCE_SCHEMA_VERSION:
            raise DataToolError(
                "P5 Strategy Governance schema version이 현재 코드와 다릅니다."
            )

    return {
        "schema_version": STRATEGY_GOVERNANCE_SCHEMA_VERSION,
        "present": bool(present),
        "tables": present,
        "restorable": len(present) == len(STRATEGY_GOVERNANCE_TABLES),
    }


def _strategy_selection_extension_absent() -> dict[str, object]:
    return {
        "contract_version": SELECTION_POLICY_CONTRACT_VERSION,
        "runtime_present": False,
        "active_reference_present": False,
        "policy_snapshot_count": 0,
        "resolved_policy_source": "LEGACY_CURRENT_10_FALLBACK",
        "resolved_policy_id": "LEGACY_CURRENT_10_FALLBACK",
        "fallback_used": True,
        "fallback_reason": "ACTIVE_REFERENCE_MISSING",
        "state_files": [],
        "paired_with_simulation_db": True,
    }


def _horizon_context_extension(
    holdings_copy: Path,
    simulation_copy: Path | None,
) -> dict[str, object]:
    analysis_context = _table_exists(holdings_copy, ANALYSIS_HORIZON_TABLE)
    plan_context = _table_exists(holdings_copy, PLAN_HORIZON_TABLE)
    validation_context = (
        simulation_copy is not None
        and simulation_copy.is_file()
        and _table_exists(simulation_copy, VALIDATION_HORIZON_TABLE)
    )
    execution_context = (
        simulation_copy is not None
        and simulation_copy.is_file()
        and _table_exists(simulation_copy, EXECUTION_HORIZON_TABLE)
    )
    return {
        "schema_version": HORIZON_SCHEMA_VERSION,
        "analysis_context_store": analysis_context,
        "management_plan_context_store": plan_context,
        "validation_context_store": validation_context,
        "execution_context_store": execution_context,
        "holdings_context_restorable": analysis_context and plan_context,
        "simulation_context_restorable": validation_context and execution_context,
        "numeric_policy_approved": False,
        "note": (
            "Horizon side tables preserve explicit decision intent without backfilling "
            "legacy rows. Numeric SHORT/MEDIUM/LONG policy remains separately gated."
        ),
    }


def create_backup(
    *,
    destination: Path | None = None,
    include_market: bool = False,
    holdings_db: Path | None = None,
    market_db: Path | None = None,
    simulation_db: Path | None = None,
    tracking_db: Path | None = None,
    include_simulation: bool = True,
    include_tracking: bool = True,
    strategy_selection_runtime: Path | None = None,
) -> Path:
    source_holdings = Path(holdings_db or holdings_db_path())
    source_market = Path(market_db or market_db_path())
    source_simulation = Path(simulation_db or simulation_db_path())
    source_tracking = Path(tracking_db or tracking_db_path())
    source_strategy_selection = Path(
        strategy_selection_runtime
        or (
            DEFAULT_STRATEGY_SELECTION_RUNTIME_DIR
            if simulation_db is None
            else source_simulation.parent / "strategy_selection"
        )
    )

    validate_holdings_db(source_holdings)
    if include_market:
        validate_market_db(source_market)
    if include_simulation and source_simulation.is_file():
        validate_simulation_db(source_simulation)
    if include_tracking and source_tracking.is_file():
        validate_tracking_db(source_tracking)

    final_dir = Path(
        destination
        or (DEFAULT_BACKUP_ROOT / f"StockScope_{utc_stamp()}")
    )
    if final_dir.exists():
        raise DataToolError(f"백업 대상이 이미 존재합니다: {final_dir}")

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = final_dir.parent / f".{final_dir.name}.{uuid4().hex}.tmp"
    temp_dir.mkdir(parents=True, exist_ok=False)

    try:
        holdings_copy = temp_dir / "holdings.db"
        sqlite_snapshot(source_holdings, holdings_copy)
        holdings_validation = validate_holdings_db(holdings_copy)

        files: dict[str, dict[str, object]] = {
            "holdings.db": manifest_file_entry(holdings_copy),
        }
        contents = {
            "holdings_db": True,
            "market_history_db": False,
            "simulation_db": False,
            "tracking_db": False,
            "strategy_selection_runtime": False,
        }

        market_summary = None
        market_copy: Path | None = None
        if include_market:
            market_copy = temp_dir / "market_history.db"
            sqlite_snapshot(source_market, market_copy)
            market_summary = validate_market_db(market_copy)
            files["market_history.db"] = manifest_file_entry(market_copy)
            contents["market_history_db"] = True

        simulation_summary = None
        simulation_copy: Path | None = None
        if include_simulation and source_simulation.is_file():
            simulation_copy = temp_dir / "simulation.db"
            sqlite_snapshot(source_simulation, simulation_copy)
            simulation_summary = validate_simulation_db(simulation_copy)
            files["simulation.db"] = manifest_file_entry(simulation_copy)
            contents["simulation_db"] = True

        tracking_summary = None
        tracking_copy: Path | None = None
        if include_tracking and source_tracking.is_file():
            tracking_copy = temp_dir / "recommendation_tracking.db"
            sqlite_snapshot(source_tracking, tracking_copy)
            tracking_summary = validate_tracking_db(tracking_copy)
            files["recommendation_tracking.db"] = manifest_file_entry(tracking_copy)
            contents["tracking_db"] = True

        strategy_governance_extension = _strategy_governance_extension(
            simulation_copy
        )
        strategy_selection_extension = _strategy_selection_extension_absent()
        if (
            include_simulation
            and simulation_copy is not None
            and strategy_governance_extension["restorable"]
        ):
            source_selection_state = validate_strategy_selection_runtime(
                source_strategy_selection,
                simulation_db=source_simulation,
            )
            if source_selection_state["runtime_present"]:
                selection_copy = temp_dir / "strategy_selection"
                strategy_selection_extension = copy_strategy_selection_runtime(
                    source_strategy_selection,
                    selection_copy,
                    simulation_db=simulation_copy,
                )
                strategy_selection_extension["paired_with_simulation_db"] = True
                for path in strategy_selection_state_file_paths(selection_copy):
                    relative = path.relative_to(temp_dir).as_posix()
                    files[relative] = manifest_file_entry(path)
                contents["strategy_selection_runtime"] = True
            else:
                strategy_selection_extension = {
                    **source_selection_state,
                    "paired_with_simulation_db": True,
                }
        elif include_simulation and simulation_copy is not None:
            source_selection_state = validate_strategy_selection_runtime(
                source_strategy_selection,
                simulation_db=source_simulation,
            )
            if source_selection_state["runtime_present"]:
                raise DataToolError(
                    "Strategy Selection runtime은 존재하지만 P5 Strategy Governance "
                    "schema가 없어 일관된 백업을 만들 수 없습니다."
                )

        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "created_at": iso_now(),
            "stockscope_version": project_version(),
            "git_commit": git_commit(),
            "contents": contents,
            "counts": holdings_validation["counts"],
            "files": files,
            "validation": {
                "holdings": {
                    "integrity": holdings_validation["integrity"],
                    "foreign_keys": holdings_validation["foreign_keys"],
                    "domain": holdings_validation["domain"],
                },
                "market_history": market_summary,
                "simulation": simulation_summary,
                "tracking": tracking_summary,
            },
            "extensions": {
                "input_identity_v1": _input_identity_extension(
                    holdings_copy,
                    market_copy,
                    simulation_copy,
                ),
                "horizon_context_v1": _horizon_context_extension(
                    holdings_copy,
                    simulation_copy,
                ),
                "feedback_v1": _feedback_extension(
                    simulation_copy,
                ),
                "prospective_evaluation_v1": _prospective_extension(
                    simulation_copy,
                ),
                "holding_decision_v1": _holding_decision_extension(
                    holdings_copy,
                ),
                "holding_recovery_v1": _holding_recovery_extension(
                    holdings_copy,
                ),
                "holding_watch_v1": _holding_watch_extension(
                    holdings_copy,
                ),
                "strategy_governance_v1": strategy_governance_extension,
                "strategy_selection_v1": strategy_selection_extension,
            },
            "secret_files_included": [],
        }
        write_json_atomic(temp_dir / "backup_manifest.json", manifest)

        blocked = secret_like_paths(temp_dir)
        if blocked:
            raise DataToolError(
                "백업에 민감 파일이 포함되어 중단했습니다: " + ", ".join(blocked)
            )

        try:
            os.replace(temp_dir, final_dir)
        except PermissionError:
            # Some managed Windows/EDR environments allow creating and reading
            # the validated snapshot directory but block directory rename.
            # Fall back to a copy-only publish. The destination is unique and
            # removed again if the copy fails, so a partial backup is never
            # returned as successful.
            if final_dir.exists():
                raise
            try:
                shutil.copytree(temp_dir, final_dir)
            except Exception:
                shutil.rmtree(final_dir, ignore_errors=True)
                raise
            shutil.rmtree(temp_dir, ignore_errors=True)
        return final_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="StockScope 사용자 상태를 일관된 SQLite snapshot으로 백업합니다."
    )
    parser.add_argument(
        "--include-market",
        action="store_true",
        help="재수집 가능한 market_history.db도 함께 백업합니다.",
    )
    parser.add_argument(
        "--exclude-simulation",
        action="store_true",
        help="simulation.db가 존재해도 백업에서 제외합니다.",
    )
    parser.add_argument(
        "--exclude-tracking",
        action="store_true",
        help="recommendation_tracking.db가 존재해도 백업에서 제외합니다.",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        help="생성할 백업 디렉터리. 생략하면 backups/ 아래에 시간별 폴더를 만듭니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        path = create_backup(
            destination=args.destination,
            include_market=args.include_market,
            include_simulation=not args.exclude_simulation,
            include_tracking=not args.exclude_tracking,
        )
        manifest_path = path / "backup_manifest.json"
        print("=" * 78)
        print("STOCKSCOPE BACKUP")
        print("=" * 78)
        print("Holdings DB      PASS")
        print("Integrity        PASS")
        print("Foreign Keys     PASS")
        print("Domain Check     PASS")
        print("Market Store     " + ("INCLUDED" if args.include_market else "SKIPPED"))
        print("Simulation DB    " + ("AUTO" if not args.exclude_simulation else "SKIPPED"))
        print("Tracking DB      " + ("AUTO" if not args.exclude_tracking else "SKIPPED"))
        print("Secrets          EXCLUDED")
        print("Manifest         PASS")
        print("")
        print("Backup:", path)
        print("Manifest:", manifest_path)
        return 0
    except DataToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
