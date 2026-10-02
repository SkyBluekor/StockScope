from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from app.strategy.production_selection_policy import (
    DEFAULT_RUNTIME_DIR as DEFAULT_STRATEGY_SELECTION_RUNTIME_DIR,
)
from tools.data.common import (
    BACKEND_ROOT,
    PROJECT_ROOT,
    DataToolError,
    git_commit,
    holdings_db_path,
    iso_now,
    macro_db_path,
    market_db_path,
    secret_like_paths,
    sha256_file,
    simulation_db_path,
    sqlite_snapshot,
    tracking_db_path,
    utc_stamp,
    validate_holdings_db,
    validate_market_db,
    validate_simulation_db,
    validate_tracking_db,
    write_json_atomic,
)
from tools.data.macro_runtime import validate_macro_db
from tools.data.strategy_selection_runtime import (
    copy_strategy_selection_runtime,
    state_file_paths,
    validate_strategy_selection_runtime,
)


HANDOFF_FORMAT_VERSION = 1
HANDOFF_CONTRACT = "STOCKSCOPE_HANDOFF_V1"
CONTINUITY_STATE_VERSION = 1
DEFAULT_HANDOFF_ROOT = PROJECT_ROOT / "backups" / "handoff"
DEFAULT_CONTINUITY_STATE = (
    BACKEND_ROOT / "runtime" / "continuity" / "runtime_state.json"
)
DEFAULT_EXPORT_DOMAINS = (
    "holdings",
    "simulation",
    "tracking",
    "macro",
    "strategy_selection",
)
DB_DOMAINS = frozenset(
    {"holdings", "simulation", "market", "tracking", "macro"}
)
KNOWN_DOMAINS = DB_DOMAINS | {"strategy_selection"}

_DOMAIN_RELATIVE_PATHS = {
    "holdings": Path("holdings") / "holdings.db",
    "simulation": Path("simulation") / "simulation.db",
    "market": Path("market_history") / "market_history.db",
    "tracking": Path("tracking") / "recommendation_tracking.db",
    "macro": Path("macro") / "macro.db",
}


@dataclass(frozen=True, slots=True)
class RuntimeLocations:
    holdings: Path
    simulation: Path
    market: Path
    tracking: Path
    macro: Path
    strategy_selection: Path
    continuity_state: Path

    @classmethod
    def current(cls) -> "RuntimeLocations":
        return cls(
            holdings=Path(holdings_db_path()),
            simulation=Path(simulation_db_path()),
            market=Path(market_db_path()),
            tracking=Path(tracking_db_path()),
            macro=Path(macro_db_path()),
            strategy_selection=Path(DEFAULT_STRATEGY_SELECTION_RUNTIME_DIR),
            continuity_state=DEFAULT_CONTINUITY_STATE,
        )


def _validator(domain: str):
    validators = {
        "holdings": validate_holdings_db,
        "simulation": validate_simulation_db,
        "market": validate_market_db,
        "tracking": validate_tracking_db,
        "macro": validate_macro_db,
    }
    try:
        return validators[domain]
    except KeyError as exc:
        raise DataToolError(f"지원하지 않는 DB domain입니다: {domain}") from exc


def _db_path(locations: RuntimeLocations, domain: str) -> Path:
    try:
        return Path(getattr(locations, domain))
    except AttributeError as exc:
        raise DataToolError(f"지원하지 않는 runtime domain입니다: {domain}") from exc


def _load_state(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {
            "format_version": CONTINUITY_STATE_VERSION,
            "machine_id": uuid.uuid4().hex,
            "domains": {},
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataToolError(
            f"Runtime continuity state를 읽을 수 없습니다: {path}"
        ) from exc
    if int(payload.get("format_version") or 0) != CONTINUITY_STATE_VERSION:
        raise DataToolError(
            "지원하지 않는 runtime continuity state version입니다."
        )
    if not isinstance(payload.get("domains"), dict):
        raise DataToolError("Runtime continuity domains가 JSON object가 아닙니다.")
    if not str(payload.get("machine_id") or ""):
        raise DataToolError("Runtime continuity machine_id가 없습니다.")
    return payload


def _save_state(path: Path, payload: dict[str, Any]) -> None:
    write_json_atomic(Path(path), payload)


def _strategy_digest(runtime_dir: Path) -> str | None:
    files = state_file_paths(Path(runtime_dir))
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(runtime_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _manifest_file(path: Path) -> dict[str, Any]:
    return {
        "sha256": sha256_file(path),
        "size_bytes": int(path.stat().st_size),
    }


def _domain_identity(
    *,
    previous: dict[str, Any] | None,
    local_content_sha256: str,
    bundle_content_sha256: str,
    bundle_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    previous = dict(previous or {})
    domain_id = str(previous.get("domain_id") or uuid.uuid4().hex)
    parent_snapshot_id = (
        str(previous.get("snapshot_id"))
        if previous.get("snapshot_id")
        else None
    )
    snapshot_id = uuid.uuid4().hex
    manifest_identity = {
        "domain_id": domain_id,
        "snapshot_id": snapshot_id,
        "parent_snapshot_id": parent_snapshot_id,
    }
    receipt = {
        **manifest_identity,
        "local_content_sha256": local_content_sha256,
        "snapshot_content_sha256": bundle_content_sha256,
        "last_bundle_id": bundle_id,
        "updated_at": iso_now(),
    }
    return manifest_identity, receipt


def _normalize_domains(domains: Iterable[str] | None) -> list[str]:
    selected = list(domains or DEFAULT_EXPORT_DOMAINS)
    result: list[str] = []
    for raw in selected:
        domain = str(raw).strip().lower()
        if not domain:
            continue
        if domain not in KNOWN_DOMAINS:
            raise DataToolError(f"지원하지 않는 handoff domain입니다: {domain}")
        if domain not in result:
            result.append(domain)
    if not result:
        raise DataToolError("Handoff domain이 하나도 선택되지 않았습니다.")
    return result


def export_handoff(
    *,
    domains: Iterable[str] | None = None,
    destination: Path | None = None,
    locations: RuntimeLocations | None = None,
) -> dict[str, Any]:
    runtime = locations or RuntimeLocations.current()
    selected = _normalize_domains(domains)
    if "strategy_selection" in selected and "simulation" not in selected:
        raise DataToolError(
            "Strategy Selection handoff는 Simulation domain과 함께 export해야 합니다."
        )

    final_dir = Path(
        destination
        or (DEFAULT_HANDOFF_ROOT / f"StockScope_Handoff_{utc_stamp()}")
    )
    if final_dir.exists():
        raise DataToolError(f"Handoff 대상이 이미 존재합니다: {final_dir}")
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = final_dir.parent / f".{final_dir.name}.{uuid.uuid4().hex}.tmp"
    temp_dir.mkdir(parents=True, exist_ok=False)

    state = _load_state(runtime.continuity_state)
    state_updates: dict[str, dict[str, Any]] = {}
    bundle_id = uuid.uuid4().hex
    manifest_domains: dict[str, Any] = {}
    skipped: list[dict[str, str]] = []

    try:
        for domain in selected:
            if domain == "strategy_selection":
                source_simulation = runtime.simulation
                if not source_simulation.is_file():
                    skipped.append(
                        {
                            "domain": domain,
                            "reason": "SIMULATION_NOT_PRESENT",
                        }
                    )
                    continue
                selection_state = validate_strategy_selection_runtime(
                    runtime.strategy_selection,
                    simulation_db=(
                        source_simulation if source_simulation.is_file() else None
                    ),
                )
                if not selection_state["runtime_present"]:
                    skipped.append(
                        {
                            "domain": domain,
                            "reason": "RUNTIME_NOT_PRESENT",
                        }
                    )
                    continue
                target_dir = temp_dir / "strategy_selection"
                copied = copy_strategy_selection_runtime(
                    runtime.strategy_selection,
                    target_dir,
                    simulation_db=source_simulation,
                )
                files: list[dict[str, Any]] = []
                for path in state_file_paths(target_dir):
                    relative = path.relative_to(temp_dir).as_posix()
                    files.append(
                        {
                            "path": relative,
                            **_manifest_file(path),
                        }
                    )
                bundle_digest = _strategy_digest(target_dir)
                local_digest = _strategy_digest(runtime.strategy_selection)
                if bundle_digest is None or local_digest is None:
                    raise DataToolError(
                        "Strategy Selection handoff digest를 계산할 수 없습니다."
                    )
                identity, receipt = _domain_identity(
                    previous=state["domains"].get(domain),
                    local_content_sha256=local_digest,
                    bundle_content_sha256=bundle_digest,
                    bundle_id=bundle_id,
                )
                manifest_domains[domain] = {
                    "kind": "strategy_selection",
                    **identity,
                    "content_sha256": bundle_digest,
                    "files": files,
                    "state": copied,
                    "import_policy": "EXPLICIT_RECONCILIATION_ONLY",
                }
                state_updates[domain] = receipt
                continue

            source = _db_path(runtime, domain)
            if not source.is_file():
                skipped.append(
                    {
                        "domain": domain,
                        "reason": "DB_NOT_PRESENT",
                    }
                )
                continue
            validator = _validator(domain)
            validator(source)
            relative = _DOMAIN_RELATIVE_PATHS[domain]
            target = temp_dir / relative
            sqlite_snapshot(source, target)
            validation = validator(target)
            snapshot_sha = sha256_file(target)
            local_sha = sha256_file(source)
            identity, receipt = _domain_identity(
                previous=state["domains"].get(domain),
                local_content_sha256=local_sha,
                bundle_content_sha256=snapshot_sha,
                bundle_id=bundle_id,
            )
            manifest_domains[domain] = {
                "kind": "sqlite",
                **identity,
                "path": relative.as_posix(),
                "content_sha256": snapshot_sha,
                "file": _manifest_file(target),
                "validation": validation,
            }
            state_updates[domain] = receipt

        if not manifest_domains:
            raise DataToolError("Handoff bundle에 포함할 runtime domain이 없습니다.")

        manifest = {
            "format_version": HANDOFF_FORMAT_VERSION,
            "runtime_contract": HANDOFF_CONTRACT,
            "bundle_id": bundle_id,
            "created_at": iso_now(),
            "source_git_sha": git_commit(),
            "source_machine_id": state["machine_id"],
            "domains": manifest_domains,
            "skipped": skipped,
            "secrets_included": False,
        }
        write_json_atomic(temp_dir / "runtime_manifest.json", manifest)

        blocked = secret_like_paths(temp_dir)
        if blocked:
            raise DataToolError(
                "Handoff bundle에 민감 파일이 포함되어 중단했습니다: "
                + ", ".join(blocked)
            )

        write_json_atomic(
            temp_dir / "bundle_complete.json",
            {
                "runtime_contract": HANDOFF_CONTRACT,
                "bundle_id": bundle_id,
                "completed_at": iso_now(),
            },
        )
        try:
            os.replace(temp_dir, final_dir)
        except PermissionError:
            if final_dir.exists():
                raise
            try:
                shutil.copytree(temp_dir, final_dir)
            except Exception:
                shutil.rmtree(final_dir, ignore_errors=True)
                raise
            shutil.rmtree(temp_dir, ignore_errors=True)

        state["domains"].update(state_updates)
        _save_state(runtime.continuity_state, state)
        return {
            "status": "COMPLETE",
            "bundle": str(final_dir),
            "bundle_id": bundle_id,
            "domains": sorted(manifest_domains),
            "skipped": skipped,
            "secrets_included": False,
        }
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def inspect_handoff(bundle_dir: Path) -> dict[str, Any]:
    bundle = Path(bundle_dir)
    manifest_path = bundle / "runtime_manifest.json"
    complete_path = bundle / "bundle_complete.json"
    if not manifest_path.is_file() or not complete_path.is_file():
        raise DataToolError("완료된 Handoff bundle이 아닙니다.")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        complete = json.loads(complete_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataToolError("Handoff manifest를 읽을 수 없습니다.") from exc

    if int(manifest.get("format_version") or 0) != HANDOFF_FORMAT_VERSION:
        raise DataToolError("지원하지 않는 Handoff format입니다.")
    if manifest.get("runtime_contract") != HANDOFF_CONTRACT:
        raise DataToolError("지원하지 않는 Handoff runtime contract입니다.")
    if complete.get("bundle_id") != manifest.get("bundle_id"):
        raise DataToolError("Handoff completion marker와 manifest가 다릅니다.")

    blocked = secret_like_paths(bundle)
    if blocked:
        raise DataToolError(
            "Handoff bundle에 민감 파일이 포함되어 있습니다: "
            + ", ".join(blocked)
        )

    domains = manifest.get("domains")
    if not isinstance(domains, dict) or not domains:
        raise DataToolError("Handoff manifest domains가 비어 있습니다.")

    for domain, raw in domains.items():
        if domain not in KNOWN_DOMAINS or not isinstance(raw, dict):
            raise DataToolError(f"지원하지 않는 Handoff domain입니다: {domain}")
        if raw.get("kind") == "sqlite":
            expected_relative = _DOMAIN_RELATIVE_PATHS.get(domain)
            if expected_relative is None:
                raise DataToolError(f"DB path allowlist가 없습니다: {domain}")
            if raw.get("path") != expected_relative.as_posix():
                raise DataToolError(f"Handoff DB path가 allowlist와 다릅니다: {domain}")
            source = bundle / expected_relative
            if not source.is_file():
                raise DataToolError(f"Handoff DB가 없습니다: {domain}")
            file_entry = dict(raw.get("file") or {})
            expected_hash = str(file_entry.get("sha256") or "")
            if sha256_file(source) != expected_hash:
                raise DataToolError(f"Handoff DB hash가 다릅니다: {domain}")
            _validator(domain)(source)
        elif raw.get("kind") == "strategy_selection":
            files = raw.get("files")
            if not isinstance(files, list):
                raise DataToolError("Strategy Selection file manifest가 없습니다.")
            declared: set[str] = set()
            for entry in files:
                if not isinstance(entry, dict):
                    raise DataToolError("Strategy Selection file entry가 잘못되었습니다.")
                relative = str(entry.get("path") or "")
                relative_path = Path(relative)
                parts = relative_path.parts
                allowed = (
                    relative == "strategy_selection/active.json"
                    or (
                        len(parts) == 3
                        and parts[0] == "strategy_selection"
                        and parts[1] == "policies"
                        and relative_path.suffix == ".json"
                    )
                )
                if (
                    relative_path.is_absolute()
                    or ".." in parts
                    or not allowed
                ):
                    raise DataToolError("Strategy Selection path allowlist 위반입니다.")
                source = bundle / relative_path
                if not source.is_file():
                    raise DataToolError(
                        f"Strategy Selection file이 없습니다: {relative}"
                    )
                if sha256_file(source) != str(entry.get("sha256") or ""):
                    raise DataToolError(
                        f"Strategy Selection file hash가 다릅니다: {relative}"
                    )
                declared.add(relative)
            actual = {
                path.relative_to(bundle).as_posix()
                for path in state_file_paths(bundle / "strategy_selection")
            }
            if actual != declared:
                raise DataToolError(
                    "Strategy Selection 실제 파일 집합과 manifest가 다릅니다."
                )
            simulation_entry = domains.get("simulation")
            if not isinstance(simulation_entry, dict):
                raise DataToolError(
                    "Strategy Selection bundle에는 Simulation domain이 필요합니다."
                )
            validate_strategy_selection_runtime(
                bundle / "strategy_selection",
                simulation_db=bundle / _DOMAIN_RELATIVE_PATHS["simulation"],
            )
        else:
            raise DataToolError(f"지원하지 않는 Handoff kind입니다: {domain}")

    return manifest


def _plan_db_import(
    *,
    domain: str,
    incoming: dict[str, Any],
    target: Path,
    receipt: dict[str, Any] | None,
    is_ancestor: Callable[[str, str, str], bool] | None = None,
) -> dict[str, Any]:
    if not target.is_file():
        return {"domain": domain, "action": "INSTALL", "reason": "TARGET_ABSENT"}

    current_hash = sha256_file(target)
    incoming_hash = str(incoming.get("content_sha256") or "")
    if current_hash == incoming_hash:
        return {
            "domain": domain,
            "action": "NO_ACTION",
            "reason": "CONTENT_IDENTICAL",
            "current_hash": current_hash,
        }

    receipt = dict(receipt or {})
    local_domain_id = str(receipt.get("domain_id") or "")
    incoming_domain_id = str(incoming.get("domain_id") or "")
    local_snapshot = str(receipt.get("snapshot_id") or "")
    incoming_snapshot = str(incoming.get("snapshot_id") or "")
    local_unchanged = (
        str(receipt.get("local_content_sha256") or "") == current_hash
    )

    if not local_domain_id or not local_snapshot:
        return {
            "domain": domain,
            "action": "CONFLICT",
            "reason": "LOCAL_LINEAGE_UNKNOWN",
            "current_hash": current_hash,
        }
    if local_domain_id != incoming_domain_id:
        return {
            "domain": domain,
            "action": "CONFLICT",
            "reason": "DIFFERENT_HISTORY",
            "current_hash": current_hash,
        }

    if local_snapshot == incoming_snapshot:
        if local_unchanged:
            return {
                "domain": domain,
                "action": "NO_ACTION",
                "reason": "SNAPSHOT_IDENTICAL",
                "current_hash": current_hash,
            }
        return {
            "domain": domain,
            "action": "LOCAL_AHEAD",
            "reason": "LOCAL_CONTENT_CHANGED_AFTER_SNAPSHOT",
            "current_hash": current_hash,
        }

    parent_matches = (
        local_snapshot == str(incoming.get("parent_snapshot_id") or "")
    )
    incoming_descendant = parent_matches or (
        is_ancestor is not None
        and is_ancestor(incoming_domain_id, local_snapshot, incoming_snapshot)
    )
    if incoming_descendant:
        if local_unchanged:
            return {
                "domain": domain,
                "action": "FAST_FORWARD",
                "reason": "LINEAGE_DESCENDANT",
                "current_hash": current_hash,
            }
        return {
            "domain": domain,
            "action": "CONFLICT",
            "reason": "LOCAL_CHANGED_REMOTE_DESCENDANT",
            "current_hash": current_hash,
        }

    local_parent_matches = (
        incoming_snapshot == str(receipt.get("parent_snapshot_id") or "")
    )
    local_descendant = local_parent_matches or (
        is_ancestor is not None
        and is_ancestor(incoming_domain_id, incoming_snapshot, local_snapshot)
    )
    if local_descendant:
        return {
            "domain": domain,
            "action": "LOCAL_AHEAD",
            "reason": "LOCAL_LINEAGE_DESCENDANT",
            "current_hash": current_hash,
        }

    return {
        "domain": domain,
        "action": "CONFLICT",
        "reason": "LOCAL_OR_LINEAGE_DIVERGENCE",
        "current_hash": current_hash,
    }


def _install_db(
    *,
    domain: str,
    source: Path,
    target: Path,
) -> Path | None:
    validator = _validator(domain)
    target.parent.mkdir(parents=True, exist_ok=True)
    pre_restore: Path | None = None
    if target.is_file():
        pre_restore = target.with_name(
            f"{target.name}.pre_handoff_{utc_stamp()}_{uuid.uuid4().hex[:8]}.bak"
        )
        sqlite_snapshot(target, pre_restore)
        validator(pre_restore)

    temp = target.with_name(f".{target.name}.handoff.{uuid.uuid4().hex}.tmp")
    try:
        sqlite_snapshot(source, temp)
        validator(temp)
        os.replace(temp, target)
        validator(target)
        return pre_restore
    except Exception:
        if temp.exists():
            temp.unlink()
        if pre_restore is not None and pre_restore.is_file():
            rollback = target.with_name(
                f".{target.name}.rollback.{uuid.uuid4().hex}.tmp"
            )
            sqlite_snapshot(pre_restore, rollback)
            os.replace(rollback, target)
        elif target.exists():
            target.unlink()
        raise


def import_handoff(
    bundle_dir: Path,
    *,
    domains: Iterable[str] | None = None,
    locations: RuntimeLocations | None = None,
    strict: bool = False,
    dry_run: bool = False,
    is_ancestor: Callable[[str, str, str], bool] | None = None,
) -> dict[str, Any]:
    runtime = locations or RuntimeLocations.current()
    manifest = inspect_handoff(bundle_dir)
    available = list(manifest["domains"].keys())
    selected = _normalize_domains(domains) if domains is not None else available
    missing_from_bundle = sorted(set(selected) - set(available))
    if missing_from_bundle:
        raise DataToolError(
            "선택한 domain이 bundle에 없습니다: " + ", ".join(missing_from_bundle)
        )

    state = _load_state(runtime.continuity_state)
    plans: list[dict[str, Any]] = []
    for domain in selected:
        incoming = dict(manifest["domains"][domain])
        if domain == "strategy_selection":
            plans.append(
                {
                    "domain": domain,
                    "action": "RECONCILIATION_REQUIRED",
                    "reason": "PRODUCTION_SELECTION_POLICY_GUARD",
                }
            )
            continue
        target = _db_path(runtime, domain)
        plans.append(
            _plan_db_import(
                domain=domain,
                incoming=incoming,
                target=target,
                receipt=state["domains"].get(domain),
                is_ancestor=is_ancestor,
            )
        )

    conflicts = [
        item for item in plans
        if item["action"] in {"CONFLICT", "RECONCILIATION_REQUIRED"}
    ]
    if strict and conflicts:
        return {
            "status": "BLOCKED",
            "bundle_id": manifest["bundle_id"],
            "plans": plans,
            "installed": [],
            "conflicts": conflicts,
        }

    if dry_run:
        return {
            "status": "PARTIAL" if conflicts else "PLANNED",
            "bundle_id": manifest["bundle_id"],
            "plans": plans,
            "installed": [],
            "conflicts": conflicts,
            "production_selection_policy_changed": False,
        }

    installed: list[str] = []
    receipts_changed = False
    bundle = Path(bundle_dir)
    for item in plans:
        if item["action"] not in {"INSTALL", "FAST_FORWARD"}:
            continue
        domain = str(item["domain"])
        incoming = dict(manifest["domains"][domain])
        source = bundle / _DOMAIN_RELATIVE_PATHS[domain]
        target = _db_path(runtime, domain)
        _install_db(domain=domain, source=source, target=target)
        current_hash = sha256_file(target)
        state["domains"][domain] = {
            "domain_id": incoming["domain_id"],
            "snapshot_id": incoming["snapshot_id"],
            "parent_snapshot_id": incoming.get("parent_snapshot_id"),
            "local_content_sha256": current_hash,
            "snapshot_content_sha256": incoming["content_sha256"],
            "last_bundle_id": manifest["bundle_id"],
            "updated_at": iso_now(),
        }
        installed.append(domain)
        receipts_changed = True

    for item in plans:
        if item["action"] != "NO_ACTION":
            continue
        domain = str(item["domain"])
        incoming = dict(manifest["domains"][domain])
        target = _db_path(runtime, domain)
        state["domains"][domain] = {
            "domain_id": incoming["domain_id"],
            "snapshot_id": incoming["snapshot_id"],
            "parent_snapshot_id": incoming.get("parent_snapshot_id"),
            "local_content_sha256": sha256_file(target),
            "snapshot_content_sha256": incoming["content_sha256"],
            "last_bundle_id": manifest["bundle_id"],
            "updated_at": iso_now(),
        }
        receipts_changed = True

    if receipts_changed:
        _save_state(runtime.continuity_state, state)

    status = "PARTIAL" if conflicts else "COMPLETE"
    return {
        "status": status,
        "bundle_id": manifest["bundle_id"],
        "plans": plans,
        "installed": installed,
        "conflicts": conflicts,
        "production_selection_policy_changed": False,
    }

