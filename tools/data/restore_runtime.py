from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.strategy.production_selection_policy import (
    DEFAULT_RUNTIME_DIR as DEFAULT_STRATEGY_SELECTION_RUNTIME_DIR,
    SELECTION_POLICY_CONTRACT_VERSION,
)
from tools.data.strategy_selection_runtime import (
    copy_strategy_selection_runtime,
    replace_strategy_selection_state,
    state_file_paths as strategy_selection_state_file_paths,
    validate_strategy_selection_runtime,
)

from tools.data.common import (
    BACKUP_FORMAT_VERSION,
    DataToolError,
    assert_replaceable,
    holdings_db_path,
    market_db_path,
    simulation_db_path,
    tracking_db_path,
    secret_like_paths,
    sqlite_snapshot,
    utc_stamp,
    validate_holdings_db,
    validate_manifest_hash,
    validate_market_db,
    validate_simulation_db,
    validate_tracking_db,
)


def _load_manifest(backup_dir: Path) -> dict:
    manifest_path = backup_dir / "backup_manifest.json"
    if not manifest_path.is_file():
        raise DataToolError("backup_manifest.json이 없습니다.")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataToolError("backup_manifest.json을 읽을 수 없습니다.") from exc
    if int(payload.get("format_version") or 0) != BACKUP_FORMAT_VERSION:
        raise DataToolError(
            f"지원하지 않는 backup format입니다: {payload.get('format_version')}"
        )
    return payload


def _prepare_restore_copy(
    source: Path,
    target: Path,
    *,
    validator,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.restore.{uuid4().hex}.tmp")
    sqlite_snapshot(source, temp)
    validator(temp)
    return temp


def restore_backup(
    backup_dir: Path,
    *,
    restore_market: bool = False,
    restore_simulation: bool = False,
    restore_tracking: bool = False,
    target_holdings: Path | None = None,
    target_market: Path | None = None,
    target_simulation: Path | None = None,
    target_tracking: Path | None = None,
    target_strategy_selection_runtime: Path | None = None,
) -> dict[str, object]:
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        raise DataToolError(f"백업 디렉터리를 찾을 수 없습니다: {backup_dir}")

    blocked = secret_like_paths(backup_dir)
    if blocked:
        raise DataToolError(
            "백업 폴더에 민감 파일이 포함되어 복원을 차단했습니다: "
            + ", ".join(blocked)
        )

    manifest = _load_manifest(backup_dir)
    contents = dict(manifest.get("contents") or {})
    files = dict(manifest.get("files") or {})
    extensions = dict(manifest.get("extensions") or {})
    strategy_selection_manifest = dict(
        extensions.get("strategy_selection_v1") or {}
    )

    if not contents.get("holdings_db"):
        raise DataToolError("백업에 holdings.db가 없습니다.")

    source_holdings = backup_dir / "holdings.db"
    if not source_holdings.is_file():
        raise DataToolError("백업 holdings.db 파일이 없습니다.")
    validate_manifest_hash(
        source_holdings,
        dict(files.get("holdings.db") or {}),
        "holdings.db",
    )
    validate_holdings_db(source_holdings)

    source_market: Path | None = None
    if restore_market:
        if not contents.get("market_history_db"):
            raise DataToolError(
                "이 백업에는 Market Store가 없습니다. --restore-market을 제거하세요."
            )
        source_market = backup_dir / "market_history.db"
        if not source_market.is_file():
            raise DataToolError("백업 market_history.db 파일이 없습니다.")
        validate_manifest_hash(
            source_market,
            dict(files.get("market_history.db") or {}),
            "market_history.db",
        )
        validate_market_db(source_market)

    source_simulation: Path | None = None
    if restore_simulation:
        if not contents.get("simulation_db"):
            raise DataToolError(
                "이 백업에는 Simulation DB가 없습니다. --restore-simulation을 제거하세요."
            )
        source_simulation = backup_dir / "simulation.db"
        if not source_simulation.is_file():
            raise DataToolError("백업 simulation.db 파일이 없습니다.")
        validate_manifest_hash(
            source_simulation,
            dict(files.get("simulation.db") or {}),
            "simulation.db",
        )
        validate_simulation_db(source_simulation)

        if strategy_selection_manifest:
            if (
                strategy_selection_manifest.get("contract_version")
                != SELECTION_POLICY_CONTRACT_VERSION
            ):
                raise DataToolError(
                    "지원하지 않는 Strategy Selection backup contract입니다."
                )
            if not strategy_selection_manifest.get(
                "paired_with_simulation_db", False
            ):
                raise DataToolError(
                    "Strategy Selection backup이 Simulation DB와 묶여 있지 않습니다."
                )

            runtime_present = bool(
                strategy_selection_manifest.get("runtime_present")
            )
            content_present = bool(
                contents.get("strategy_selection_runtime")
            )
            if runtime_present != content_present:
                raise DataToolError(
                    "Strategy Selection manifest와 contents 상태가 일치하지 않습니다."
                )

            source_selection = backup_dir / "strategy_selection"
            if runtime_present:
                if not source_selection.is_dir():
                    raise DataToolError(
                        "백업 Strategy Selection runtime 디렉터리가 없습니다."
                    )
                declared_files = {
                    str(item)
                    for item in (
                        strategy_selection_manifest.get("state_files") or []
                    )
                }
                actual_files = {
                    path.relative_to(source_selection).as_posix()
                    for path in strategy_selection_state_file_paths(
                        source_selection
                    )
                }
                if actual_files != declared_files:
                    raise DataToolError(
                        "Strategy Selection state file 집합이 manifest와 다릅니다."
                    )
                for relative in sorted(declared_files):
                    relative_path = Path(relative)
                    if (
                        relative_path.is_absolute()
                        or ".." in relative_path.parts
                    ):
                        raise DataToolError(
                            "Strategy Selection manifest에 안전하지 않은 경로가 있습니다."
                        )
                    source_path = source_selection / relative_path
                    validate_manifest_hash(
                        source_path,
                        dict(
                            files.get(
                                "strategy_selection/"
                                + relative_path.as_posix()
                            )
                            or {}
                        ),
                        "strategy_selection/" + relative_path.as_posix(),
                    )
                source_state = validate_strategy_selection_runtime(
                    source_selection,
                    simulation_db=source_simulation,
                )
                for key in (
                    "active_reference_present",
                    "policy_snapshot_count",
                    "resolved_policy_source",
                    "resolved_policy_id",
                ):
                    if source_state[key] != strategy_selection_manifest.get(
                        key
                    ):
                        raise DataToolError(
                            "Strategy Selection backup metadata가 실제 상태와 다릅니다: "
                            + key
                        )
            else:
                if strategy_selection_state_file_paths(source_selection):
                    raise DataToolError(
                        "Legacy fallback backup에 Strategy Selection state file이 존재합니다."
                    )

    source_tracking: Path | None = None
    if restore_tracking:
        if not contents.get("tracking_db"):
            raise DataToolError(
                "이 백업에는 Tracking DB가 없습니다. --restore-tracking을 제거하세요."
            )
        source_tracking = backup_dir / "recommendation_tracking.db"
        if not source_tracking.is_file():
            raise DataToolError("백업 recommendation_tracking.db 파일이 없습니다.")
        validate_manifest_hash(
            source_tracking,
            dict(files.get("recommendation_tracking.db") or {}),
            "recommendation_tracking.db",
        )
        validate_tracking_db(source_tracking)

    holdings_target = Path(target_holdings or holdings_db_path())
    market_target = Path(target_market or market_db_path())
    simulation_target = Path(target_simulation or simulation_db_path())
    tracking_target = Path(target_tracking or tracking_db_path())
    strategy_selection_target = Path(
        target_strategy_selection_runtime
        or (
            DEFAULT_STRATEGY_SELECTION_RUNTIME_DIR
            if target_simulation is None
            else simulation_target.parent / "strategy_selection"
        )
    )
    restore_strategy_selection = bool(
        restore_simulation and strategy_selection_manifest
    )
    source_strategy_selection = (
        backup_dir / "strategy_selection"
        if restore_strategy_selection
        and strategy_selection_manifest.get("runtime_present")
        else None
    )

    targets: list[tuple[str, Path, Path, object]] = [
        ("holdings", source_holdings, holdings_target, validate_holdings_db)
    ]
    if restore_market and source_market is not None:
        targets.append(
            ("market", source_market, market_target, validate_market_db)
        )
    if restore_simulation and source_simulation is not None:
        targets.append(
            ("simulation", source_simulation, simulation_target, validate_simulation_db)
        )
    if restore_tracking and source_tracking is not None:
        targets.append(
            ("tracking", source_tracking, tracking_target, validate_tracking_db)
        )

    for _, _, target, _ in targets:
        assert_replaceable(target)

    stamp = utc_stamp()
    pre_restore: dict[str, Path | None] = {}
    existed_before: dict[str, bool] = {}
    temps: dict[str, Path] = {}

    strategy_selection_touched = False
    strategy_selection_result: dict[str, object] | None = None

    try:
        for label, _, target, validator in targets:
            existed = target.exists()
            existed_before[label] = existed
            if existed:
                backup_path = target.with_name(
                    f"{target.name}.pre_restore_{stamp}.bak"
                )
                if backup_path.exists():
                    raise DataToolError(
                        f"복원 전 안전 백업 경로가 이미 존재합니다: {backup_path}"
                    )
                sqlite_snapshot(target, backup_path)
                validator(backup_path)
                pre_restore[label] = backup_path
            else:
                pre_restore[label] = None

        if restore_strategy_selection:
            current_state = validate_strategy_selection_runtime(
                strategy_selection_target,
                simulation_db=(
                    simulation_target if simulation_target.is_file() else None
                ),
            )
            if current_state["runtime_present"]:
                backup_path = strategy_selection_target.with_name(
                    f"{strategy_selection_target.name}.pre_restore_{stamp}"
                )
                if backup_path.exists():
                    raise DataToolError(
                        "복원 전 Strategy Selection 안전 백업 경로가 이미 존재합니다: "
                        + str(backup_path)
                    )
                copy_strategy_selection_runtime(
                    strategy_selection_target,
                    backup_path,
                    simulation_db=(
                        simulation_target
                        if simulation_target.is_file()
                        else None
                    ),
                )
                pre_restore["strategy_selection"] = backup_path
            else:
                pre_restore["strategy_selection"] = None
            existed_before["strategy_selection"] = bool(
                current_state["runtime_present"]
            )

        for label, source, target, validator in targets:
            temps[label] = _prepare_restore_copy(
                source,
                target,
                validator=validator,
            )

        replaced: list[str] = []
        try:
            for label, _, target, validator in targets:
                os.replace(temps[label], target)
                replaced.append(label)
                validator(target)

            if restore_strategy_selection:
                strategy_selection_touched = True
                strategy_selection_result = replace_strategy_selection_state(
                    source_strategy_selection,
                    strategy_selection_target,
                    simulation_db=simulation_target,
                )
        except Exception as restore_error:
            selection_rollback_error: Exception | None = None
            if restore_strategy_selection and strategy_selection_touched:
                safe_selection = pre_restore.get("strategy_selection")
                try:
                    replace_strategy_selection_state(
                        safe_selection,
                        strategy_selection_target,
                        simulation_db=(
                            simulation_target
                            if simulation_target.is_file()
                            else None
                        ),
                    )
                except Exception as exc:
                    selection_rollback_error = exc

            for label, _, target, validator in reversed(targets):
                if label not in replaced:
                    continue
                safe = pre_restore.get(label)
                if safe is not None and safe.exists():
                    rollback_temp = _prepare_restore_copy(
                        safe,
                        target,
                        validator=validator,
                    )
                    os.replace(rollback_temp, target)
                    validator(target)
                elif not existed_before.get(label, False) and target.exists():
                    target.unlink()

            if selection_rollback_error is not None:
                raise DataToolError(
                    "Strategy Selection 복원 실패 후 기존 상태 원복에도 실패했습니다: "
                    + str(selection_rollback_error)
                ) from restore_error
            raise

        identity_manifest = dict(extensions.get("input_identity_v1") or {})
        horizon_manifest = dict(extensions.get("horizon_context_v1") or {})
        feedback_manifest = dict(extensions.get("feedback_v1") or {})
        prospective_manifest = dict(
            extensions.get("prospective_evaluation_v1") or {}
        )
        holding_decision_manifest = dict(
            extensions.get("holding_decision_v1") or {}
        )
        holding_recovery_manifest = dict(
            extensions.get("holding_recovery_v1") or {}
        )
        holding_watch_manifest = dict(
            extensions.get("holding_watch_v1") or {}
        )
        revision_identity_restored = bool(
            identity_manifest.get("revision_identity_metadata")
        )
        explicit_proof_restored = bool(
            identity_manifest.get("explicit_proof_store")
        )
        generation_restored = bool(
            restore_market and identity_manifest.get("market_generation_store")
        )
        validation_proof_restored = bool(
            restore_simulation
            and identity_manifest.get("validation_input_proof_store")
        )

        return {
            "holdings_db": str(holdings_target),
            "market_history_db": (
                str(market_target) if restore_market else None
            ),
            "simulation_db": (
                str(simulation_target) if restore_simulation else None
            ),
            "tracking_db": (
                str(tracking_target) if restore_tracking else None
            ),
            "strategy_selection_runtime": (
                str(strategy_selection_target)
                if restore_strategy_selection
                else None
            ),
            "pre_restore_backups": {
                key: (str(value) if value else None)
                for key, value in pre_restore.items()
            },
            "input_identity": {
                "revision_identity_metadata_restored": revision_identity_restored,
                "explicit_proof_store_restored": explicit_proof_restored,
                "market_generation_store_restored": generation_restored,
                "validation_input_proof_store_restored": validation_proof_restored,
                "current_identity_verification_capability_restored": (
                    revision_identity_restored and generation_restored
                ),
            },
            "horizon_context": {
                "analysis_context_store_restored": bool(
                    horizon_manifest.get("analysis_context_store")
                ),
                "management_plan_context_store_restored": bool(
                    horizon_manifest.get("management_plan_context_store")
                ),
                "validation_context_store_restored": bool(
                    restore_simulation
                    and horizon_manifest.get("validation_context_store")
                ),
                "execution_context_store_restored": bool(
                    restore_simulation
                    and horizon_manifest.get("execution_context_store")
                ),
                "numeric_policy_approved": bool(
                    horizon_manifest.get("numeric_policy_approved")
                ),
            },
            "feedback": {
                "schema_version": feedback_manifest.get("schema_version"),
                "store_present_in_backup": bool(
                    feedback_manifest.get("present")
                ),
                "store_restored": bool(
                    restore_simulation
                    and feedback_manifest.get("restorable")
                ),
                "tables": list(feedback_manifest.get("tables") or []),
            },
            "prospective_evaluation": {
                "schema_version": prospective_manifest.get("schema_version"),
                "store_present_in_backup": bool(
                    prospective_manifest.get("present")
                ),
                "store_restored": bool(
                    restore_simulation
                    and prospective_manifest.get("restorable")
                ),
                "tables": list(prospective_manifest.get("tables") or []),
            },
            "holding_decision": {
                "schema_version": holding_decision_manifest.get("schema_version"),
                "store_present_in_backup": bool(
                    holding_decision_manifest.get("present")
                ),
                "store_restored": bool(
                    holding_decision_manifest.get("restorable")
                ),
                "tables": list(holding_decision_manifest.get("tables") or []),
            },
            "holding_recovery": {
                "schema_version": holding_recovery_manifest.get("schema_version"),
                "store_present_in_backup": bool(
                    holding_recovery_manifest.get("present")
                ),
                "store_restored": bool(
                    holding_recovery_manifest.get("restorable")
                ),
                "tables": list(holding_recovery_manifest.get("tables") or []),
            },
            "strategy_selection": {
                "contract_version": strategy_selection_manifest.get(
                    "contract_version"
                ),
                "store_present_in_backup": bool(
                    strategy_selection_manifest.get("runtime_present")
                ),
                "store_restored": bool(restore_strategy_selection),
                "active_reference_present": (
                    bool(
                        strategy_selection_result.get(
                            "active_reference_present"
                        )
                    )
                    if strategy_selection_result is not None
                    else False
                ),
                "policy_snapshot_count": (
                    int(
                        strategy_selection_result.get(
                            "policy_snapshot_count", 0
                        )
                    )
                    if strategy_selection_result is not None
                    else 0
                ),
                "resolved_policy_source": (
                    strategy_selection_result.get(
                        "resolved_policy_source"
                    )
                    if strategy_selection_result is not None
                    else None
                ),
                "resolved_policy_id": (
                    strategy_selection_result.get("resolved_policy_id")
                    if strategy_selection_result is not None
                    else None
                ),
            },
            "holding_watch": {
                "schema_version": holding_watch_manifest.get("schema_version"),
                "policy_contract_version": holding_watch_manifest.get(
                    "policy_contract_version"
                ),
                "store_present_in_backup": bool(
                    holding_watch_manifest.get("present")
                ),
                "store_restored": bool(
                    holding_watch_manifest.get("restorable")
                ),
                "tables": list(holding_watch_manifest.get("tables") or []),
                "live_quote_replay_performed": False,
            },
        }
    finally:
        for temp in temps.values():
            if temp.exists():
                try:
                    temp.unlink()
                except OSError:
                    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="StockScope 백업을 검증한 뒤 안전하게 복원합니다."
    )
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument(
        "--restore-market",
        action="store_true",
        help="백업에 포함된 market_history.db도 복원합니다.",
    )
    parser.add_argument(
        "--restore-simulation",
        action="store_true",
        help="백업에 포함된 simulation.db도 복원합니다.",
    )
    parser.add_argument(
        "--restore-tracking",
        action="store_true",
        help="백업에 포함된 recommendation_tracking.db도 복원합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = restore_backup(
            args.backup_dir,
            restore_market=args.restore_market,
            restore_simulation=args.restore_simulation,
            restore_tracking=args.restore_tracking,
        )
        print("=" * 78)
        print("STOCKSCOPE RESTORE")
        print("=" * 78)
        print("Manifest          PASS")
        print("Backup Hash       PASS")
        print("Integrity         PASS")
        print("Foreign Keys      PASS")
        print("Domain Check      PASS")
        print("Holdings Restore  PASS")
        print("Market Restore    " + ("PASS" if args.restore_market else "SKIPPED"))
        print("Simulation Restore " + ("PASS" if args.restore_simulation else "SKIPPED"))
        print("Tracking Restore   " + ("PASS" if args.restore_tracking else "SKIPPED"))
        print("")
        for label, path in result["pre_restore_backups"].items():
            if path:
                print(f"Pre-restore {label} backup:", path)
        return 0
    except DataToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
