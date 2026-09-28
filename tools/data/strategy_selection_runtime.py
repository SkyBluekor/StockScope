from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.strategy.production_selection_policy import (
    LEGACY_POLICY_ID,
    ProductionStrategySelectionRegistry,
    SELECTION_POLICY_CONTRACT_VERSION,
)
from tools.data.common import DataToolError


STATE_DIR_NAME = "strategy_selection"


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataToolError(f"{label} JSON을 읽을 수 없습니다: {path}") from exc
    if not isinstance(payload, dict):
        raise DataToolError(f"{label} JSON object가 아닙니다: {path}")
    return payload


def state_file_paths(runtime_dir: Path) -> list[Path]:
    runtime_dir = Path(runtime_dir)
    result: list[Path] = []
    active = runtime_dir / "active.json"
    if active.is_file():
        result.append(active)
    policies = runtime_dir / "policies"
    if policies.is_dir():
        result.extend(sorted(path for path in policies.glob("*.json") if path.is_file()))
    return result


def validate_strategy_selection_runtime(
    runtime_dir: Path,
    *,
    simulation_db: Path | None = None,
) -> dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    files = state_file_paths(runtime_dir)
    runtime_present = bool(files)
    registry = ProductionStrategySelectionRegistry(
        runtime_dir=runtime_dir,
        simulation_db=simulation_db,
    )

    policy_files = [
        path
        for path in files
        if path.parent.name == "policies" and path.suffix == ".json"
    ]
    policy_ids: set[str] = set()
    for path in policy_files:
        payload = _read_json(path, label="Selection Policy")
        valid, reason = registry.validate_snapshot(payload)
        if not valid:
            raise DataToolError(
                f"Strategy Selection Policy 검증 실패: {path.name}: {reason}"
            )
        policy_id = str(payload.get("policy_id") or "")
        if path.stem != policy_id:
            raise DataToolError(
                f"Strategy Selection Policy 파일명과 policy_id가 다릅니다: {path.name}"
            )
        if policy_id in policy_ids:
            raise DataToolError(
                f"Strategy Selection Policy ID가 중복되었습니다: {policy_id}"
            )
        policy_ids.add(policy_id)

    active_path = runtime_dir / "active.json"
    reference: dict[str, Any] | None = None
    active_present = active_path.is_file()
    if active_present:
        reference = _read_json(active_path, label="Active Selection Reference")
        valid, reason = registry._validate_reference(reference)  # noqa: SLF001
        if not valid:
            raise DataToolError(
                f"Active Selection Reference 검증 실패: {reason}"
            )

        active, active_reason = registry._load_snapshot(  # noqa: SLF001
            str(reference.get("active_policy_id") or ""),
            str(reference.get("active_policy_hash") or ""),
        )
        if active is None:
            raise DataToolError(
                "Active Selection Policy 검증 실패: "
                + str(active_reason or "unknown")
            )

        rollback_id = reference.get("rollback_policy_id")
        rollback_hash = reference.get("rollback_policy_hash")
        if bool(rollback_id) != bool(rollback_hash):
            raise DataToolError(
                "Rollback Selection Policy ID/hash가 부분 상태입니다."
            )
        if rollback_id:
            rollback, rollback_reason = registry._load_snapshot(  # noqa: SLF001
                str(rollback_id),
                str(rollback_hash),
            )
            if rollback is None:
                raise DataToolError(
                    "Rollback Selection Policy 검증 실패: "
                    + str(rollback_reason or "unknown")
                )

    resolution = registry.resolve_active_selection_policy()
    if active_present and resolution.policy_source == "LEGACY_CURRENT_10_FALLBACK":
        raise DataToolError(
            "active.json이 존재하지만 유효한 active/rollback policy를 해석하지 못했습니다."
        )

    return {
        "contract_version": SELECTION_POLICY_CONTRACT_VERSION,
        "runtime_present": runtime_present,
        "active_reference_present": active_present,
        "policy_snapshot_count": len(policy_files),
        "resolved_policy_source": resolution.policy_source,
        "resolved_policy_id": str(
            resolution.policy.get("policy_id") or LEGACY_POLICY_ID
        ),
        "fallback_used": bool(resolution.fallback_used),
        "fallback_reason": resolution.fallback_reason,
        "state_files": [
            str(path.relative_to(runtime_dir)).replace("\\", "/")
            for path in files
        ],
    }


def copy_strategy_selection_runtime(
    source: Path,
    destination: Path,
    *,
    simulation_db: Path | None = None,
) -> dict[str, Any]:
    source = Path(source)
    destination = Path(destination)
    state = validate_strategy_selection_runtime(
        source,
        simulation_db=simulation_db,
    )
    if not state["runtime_present"]:
        return state
    if destination.exists():
        raise DataToolError(
            f"Strategy Selection 백업 대상이 이미 존재합니다: {destination}"
        )

    destination.mkdir(parents=True, exist_ok=False)
    source_active = source / "active.json"
    if source_active.is_file():
        shutil.copy2(source_active, destination / "active.json")

    source_policies = source / "policies"
    policy_files = sorted(
        path for path in source_policies.glob("*.json") if path.is_file()
    ) if source_policies.is_dir() else []
    if policy_files:
        target_policies = destination / "policies"
        target_policies.mkdir(parents=True, exist_ok=True)
        for path in policy_files:
            shutil.copy2(path, target_policies / path.name)

    copied = validate_strategy_selection_runtime(
        destination,
        simulation_db=simulation_db,
    )
    expected_files = set(state["state_files"])
    actual_files = set(copied["state_files"])
    if actual_files != expected_files:
        raise DataToolError(
            "Strategy Selection runtime 백업 파일 집합이 원본과 다릅니다."
        )
    return copied
