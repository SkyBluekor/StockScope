from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from tools.data.common import (
    BACKEND_ROOT,
    DataToolError,
    git_commit,
    iso_now,
    write_json_atomic,
)
from tools.runtime.handoff import (
    HANDOFF_CONTRACT,
    RuntimeLocations,
    _load_state,
    _save_state,
    export_handoff,
    import_handoff,
    inspect_handoff,
    sqlite_content_sha256,
)


TRANSPORT_CONFIG_CONTRACT = "STOCKSCOPE_RUNTIME_TRANSPORT_CONFIG_V1"
TRANSPORT_HEAD_CONTRACT = "STOCKSCOPE_RUNTIME_TRANSPORT_HEAD_V1"
TRANSPORT_PROVIDER = "GOOGLE_DRIVE_DESKTOP_FOLDER"
TRANSPORT_ENV = "STOCKSCOPE_RUNTIME_SYNC_DIR"
AUTO_DOMAINS = ("holdings", "simulation", "tracking", "macro")
DEFAULT_RETRY_COUNT = 5
DEFAULT_RETRY_DELAY_SECONDS = 0.4


def _config_path(locations: RuntimeLocations) -> Path:
    return locations.continuity_state.parent / "transport_config.json"


def _runtime_db_path(locations: RuntimeLocations, domain: str) -> Path:
    try:
        return Path(getattr(locations, domain))
    except AttributeError as exc:
        raise DataToolError(f"지원하지 않는 transport domain입니다: {domain}") from exc


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataToolError(f"{label} JSON을 읽을 수 없습니다: {path}") from exc
    if not isinstance(payload, dict):
        raise DataToolError(f"{label} JSON object가 아닙니다: {path}")
    return payload


def _load_config_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = _read_json(path, label="Runtime Transport Config")
    if payload.get("contract_version") != TRANSPORT_CONFIG_CONTRACT:
        raise DataToolError("지원하지 않는 Runtime Transport config입니다.")
    return payload


def resolve_transport_config(
    *,
    locations: RuntimeLocations | None = None,
) -> dict[str, Any]:
    runtime = locations or RuntimeLocations.current()
    config = _load_config_file(_config_path(runtime))
    env_root = (os.getenv(TRANSPORT_ENV) or "").strip()

    if env_root:
        return {
            "enabled": True,
            "provider": TRANSPORT_PROVIDER,
            "root": str(Path(env_root).expanduser()),
            "include_market": bool((config or {}).get("include_market", False)),
            "source": "ENVIRONMENT",
        }
    if config is None or not bool(config.get("enabled", False)):
        return {
            "enabled": False,
            "provider": TRANSPORT_PROVIDER,
            "root": str((config or {}).get("root") or ""),
            "include_market": bool((config or {}).get("include_market", False)),
            "source": "CONFIG" if config is not None else "NONE",
        }
    root = str(config.get("root") or "").strip()
    if not root:
        raise DataToolError("Runtime Transport root가 설정되지 않았습니다.")
    return {
        "enabled": True,
        "provider": str(config.get("provider") or TRANSPORT_PROVIDER),
        "root": root,
        "include_market": bool(config.get("include_market", False)),
        "source": "CONFIG",
    }


def _ensure_safe_transport_root(
    root: Path,
    *,
    locations: RuntimeLocations,
) -> Path:
    resolved = root.expanduser().resolve()
    runtime_root = (BACKEND_ROOT / "runtime").resolve()
    try:
        resolved.relative_to(runtime_root)
    except ValueError:
        pass
    else:
        raise DataToolError(
            "Runtime Transport root를 backend/runtime 내부에 둘 수 없습니다."
        )

    for domain in ("holdings", "simulation", "market", "tracking", "macro"):
        path = _runtime_db_path(locations, domain).expanduser().resolve()
        try:
            path.relative_to(resolved)
        except ValueError:
            continue
        raise DataToolError(
            "Runtime Transport root가 live Runtime DB를 포함할 수 없습니다: "
            + domain
        )
    return resolved


def _ensure_transport_dirs(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "bundles").mkdir(parents=True, exist_ok=True)
    (root / "heads").mkdir(parents=True, exist_ok=True)
    (root / ".staging").mkdir(parents=True, exist_ok=True)


def _ensure_continuity_state(locations: RuntimeLocations) -> dict[str, Any]:
    state = _load_state(locations.continuity_state)
    if not locations.continuity_state.is_file():
        _save_state(locations.continuity_state, state)
    return state


def configure_transport(
    root: Path,
    *,
    include_market: bool = False,
    locations: RuntimeLocations | None = None,
) -> dict[str, Any]:
    runtime = locations or RuntimeLocations.current()
    safe_root = _ensure_safe_transport_root(Path(root), locations=runtime)
    _ensure_transport_dirs(safe_root)
    state = _ensure_continuity_state(runtime)
    payload = {
        "contract_version": TRANSPORT_CONFIG_CONTRACT,
        "enabled": True,
        "provider": TRANSPORT_PROVIDER,
        "root": str(safe_root),
        "include_market": bool(include_market),
        "configured_at": iso_now(),
    }
    write_json_atomic(_config_path(runtime), payload)
    return {
        "status": "CONFIGURED",
        "provider": TRANSPORT_PROVIDER,
        "root": str(safe_root),
        "include_market": bool(include_market),
        "machine_id": state["machine_id"],
    }


def disable_transport(
    *,
    locations: RuntimeLocations | None = None,
) -> dict[str, Any]:
    runtime = locations or RuntimeLocations.current()
    path = _config_path(runtime)
    previous = _load_config_file(path) or {
        "contract_version": TRANSPORT_CONFIG_CONTRACT,
        "provider": TRANSPORT_PROVIDER,
        "root": "",
        "include_market": False,
    }
    previous["enabled"] = False
    previous["disabled_at"] = iso_now()
    write_json_atomic(path, previous)
    return {
        "status": "DISABLED",
        "root": str(previous.get("root") or ""),
        "environment_override_active": bool((os.getenv(TRANSPORT_ENV) or "").strip()),
    }


def _load_head(path: Path) -> dict[str, Any]:
    payload = _read_json(path, label="Runtime Transport Head")
    if payload.get("contract_version") != TRANSPORT_HEAD_CONTRACT:
        raise DataToolError(f"지원하지 않는 Runtime Transport head입니다: {path}")
    machine_id = str(payload.get("machine_id") or "")
    if not machine_id or path.stem != machine_id:
        raise DataToolError(f"Runtime Transport head machine_id가 잘못되었습니다: {path}")
    if not isinstance(payload.get("domains"), dict):
        raise DataToolError(f"Runtime Transport head domains가 잘못되었습니다: {path}")
    if not str(payload.get("bundle_id") or ""):
        raise DataToolError(f"Runtime Transport head bundle_id가 없습니다: {path}")
    return payload


def _heads(root: Path) -> list[dict[str, Any]]:
    heads_dir = root / "heads"
    if not heads_dir.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(heads_dir.glob("*.json")):
        if path.is_file():
            result.append(_load_head(path))
    return result


def _head_signature(head: dict[str, Any]) -> tuple[tuple[str, str, str], ...]:
    result: list[tuple[str, str, str]] = []
    for domain, raw in sorted(dict(head.get("domains") or {}).items()):
        if not isinstance(raw, dict):
            continue
        result.append(
            (
                str(domain),
                str(raw.get("domain_id") or ""),
                str(raw.get("snapshot_id") or ""),
            )
        )
    return tuple(result)


def _light_manifest(bundle: Path) -> dict[str, Any] | None:
    manifest_path = bundle / "runtime_manifest.json"
    complete_path = bundle / "bundle_complete.json"
    if not manifest_path.is_file() or not complete_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        complete = json.loads(complete_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or not isinstance(complete, dict):
        return None
    if manifest.get("runtime_contract") != HANDOFF_CONTRACT:
        return None
    if str(complete.get("bundle_id") or "") != str(manifest.get("bundle_id") or ""):
        return None
    return manifest


def _ancestry_resolver(
    root: Path,
    *,
    state: dict[str, Any],
) -> Callable[[str, str, str], bool]:
    parent_by_snapshot: dict[tuple[str, str], str | None] = {}

    bundles_dir = root / "bundles"
    if bundles_dir.is_dir():
        for bundle in sorted(bundles_dir.iterdir()):
            if not bundle.is_dir():
                continue
            manifest = _light_manifest(bundle)
            if manifest is None:
                continue
            for raw in dict(manifest.get("domains") or {}).values():
                if not isinstance(raw, dict):
                    continue
                domain_id = str(raw.get("domain_id") or "")
                snapshot_id = str(raw.get("snapshot_id") or "")
                if not domain_id or not snapshot_id:
                    continue
                parent = str(raw.get("parent_snapshot_id") or "") or None
                parent_by_snapshot[(domain_id, snapshot_id)] = parent

    for raw in dict(state.get("domains") or {}).values():
        if not isinstance(raw, dict):
            continue
        domain_id = str(raw.get("domain_id") or "")
        snapshot_id = str(raw.get("snapshot_id") or "")
        if not domain_id or not snapshot_id:
            continue
        parent = str(raw.get("parent_snapshot_id") or "") or None
        parent_by_snapshot[(domain_id, snapshot_id)] = parent

    def is_ancestor(domain_id: str, ancestor: str, descendant: str) -> bool:
        if not domain_id or not ancestor or not descendant or ancestor == descendant:
            return False
        current = descendant
        visited: set[str] = set()
        for _ in range(10000):
            if current in visited:
                return False
            visited.add(current)
            parent = parent_by_snapshot.get((domain_id, current))
            if not parent:
                return False
            if parent == ancestor:
                return True
            current = parent
        return False

    return is_ancestor


def _head_dominates(
    newer: dict[str, Any],
    older: dict[str, Any],
    *,
    is_ancestor: Callable[[str, str, str], bool],
) -> bool:
    newer_domains = dict(newer.get("domains") or {})
    older_domains = dict(older.get("domains") or {})
    if not older_domains:
        return False
    strict = bool(set(newer_domains) - set(older_domains))
    for domain, older_raw in older_domains.items():
        newer_raw = newer_domains.get(domain)
        if not isinstance(older_raw, dict) or not isinstance(newer_raw, dict):
            return False
        older_domain_id = str(older_raw.get("domain_id") or "")
        newer_domain_id = str(newer_raw.get("domain_id") or "")
        if older_domain_id != newer_domain_id or not older_domain_id:
            return False
        older_snapshot = str(older_raw.get("snapshot_id") or "")
        newer_snapshot = str(newer_raw.get("snapshot_id") or "")
        if older_snapshot == newer_snapshot:
            continue
        if not is_ancestor(older_domain_id, older_snapshot, newer_snapshot):
            return False
        strict = True
    return strict


def _select_remote_head(
    remote_heads: list[dict[str, Any]],
    *,
    is_ancestor: Callable[[str, str, str], bool],
) -> dict[str, Any] | None:
    if not remote_heads:
        return None
    if len(remote_heads) == 1:
        return remote_heads[0]

    survivors: list[dict[str, Any]] = []
    for head in remote_heads:
        dominated = any(
            other is not head
            and _head_dominates(other, head, is_ancestor=is_ancestor)
            for other in remote_heads
        )
        if not dominated:
            survivors.append(head)

    if len(survivors) == 1:
        return survivors[0]
    signatures = {_head_signature(item) for item in survivors}
    if len(signatures) == 1:
        return sorted(survivors, key=lambda item: str(item["machine_id"]))[-1]
    raise DataToolError(
        "REMOTE_HEAD_CONFLICT: 여러 PC의 Runtime head가 서로 다른 lineage입니다."
    )


def _wait_for_bundle(
    root: Path,
    bundle_id: str,
    *,
    retry_count: int,
    retry_delay_seconds: float,
) -> tuple[Path, dict[str, Any]]:
    bundle = root / "bundles" / bundle_id
    last_error: Exception | None = None
    attempts = max(1, int(retry_count))
    for attempt in range(attempts):
        try:
            if not bundle.is_dir():
                raise FileNotFoundError(str(bundle))
            manifest = inspect_handoff(bundle)
            return bundle, manifest
        except (DataToolError, OSError) as exc:
            last_error = exc
            if attempt + 1 < attempts and retry_delay_seconds > 0:
                time.sleep(retry_delay_seconds)

    if not bundle.is_dir() or not (bundle / "bundle_complete.json").is_file():
        raise DataToolError(
            f"REMOTE_NOT_READY: Google Drive bundle 동기화가 아직 완료되지 않았습니다: "
            f"{bundle_id}"
        ) from last_error
    message = str(last_error or "")
    if "없습니다" in message or "찾을 수" in message:
        raise DataToolError(
            f"REMOTE_NOT_READY: Google Drive bundle 파일이 아직 모두 도착하지 않았습니다: "
            f"{bundle_id}"
        ) from last_error
    raise DataToolError(
        f"CORRUPT_REMOTE_BUNDLE: Runtime bundle 검증에 실패했습니다: {bundle_id}: "
        f"{message}"
    ) from last_error


def _auto_domains(config: dict[str, Any]) -> list[str]:
    domains = list(AUTO_DOMAINS)
    if bool(config.get("include_market", False)):
        domains.append("market")
    return domains


def _head_from_manifest(
    manifest: dict[str, Any],
    *,
    machine_id: str,
    adopted_from: str | None = None,
    selected_domains: list[str] | None = None,
) -> dict[str, Any]:
    domains: dict[str, Any] = {}
    bundle_id = str(manifest["bundle_id"])
    allowed = set(selected_domains) if selected_domains is not None else None
    for domain, raw in dict(manifest.get("domains") or {}).items():
        if not isinstance(raw, dict) or domain == "strategy_selection":
            continue
        if allowed is not None and domain not in allowed:
            continue
        domains[str(domain)] = {
            "domain_id": str(raw.get("domain_id") or ""),
            "snapshot_id": str(raw.get("snapshot_id") or ""),
            "parent_snapshot_id": raw.get("parent_snapshot_id"),
            "content_sha256": str(raw.get("content_sha256") or ""),
            "bundle_id": bundle_id,
        }
    payload: dict[str, Any] = {
        "contract_version": TRANSPORT_HEAD_CONTRACT,
        "machine_id": machine_id,
        "published_at": iso_now(),
        "source_git_sha": git_commit(),
        "bundle_id": bundle_id,
        "domains": domains,
    }
    if adopted_from:
        payload["adopted_from_machine_id"] = adopted_from
    return payload


def _write_head(root: Path, head: dict[str, Any]) -> None:
    machine_id = str(head.get("machine_id") or "")
    if not machine_id:
        raise DataToolError("Runtime Transport head machine_id가 없습니다.")
    write_json_atomic(root / "heads" / f"{machine_id}.json", head)


def _own_head(root: Path, machine_id: str) -> dict[str, Any] | None:
    path = root / "heads" / f"{machine_id}.json"
    return _load_head(path) if path.is_file() else None


def transport_status(
    *,
    locations: RuntimeLocations | None = None,
) -> dict[str, Any]:
    runtime = locations or RuntimeLocations.current()
    config = resolve_transport_config(locations=runtime)
    state = (
        _load_state(runtime.continuity_state)
        if runtime.continuity_state.is_file()
        else None
    )
    machine_id = str((state or {}).get("machine_id") or "")
    if not config["enabled"]:
        return {
            "status": "DISABLED",
            "configured": False,
            "provider": config["provider"],
            "root": config["root"],
            "machine_id": machine_id or None,
            "writes": 0,
        }

    root = Path(str(config["root"])).expanduser()
    accessible = root.is_dir()
    heads: list[dict[str, Any]] = []
    if accessible:
        heads = _heads(root)
    remote = [
        item for item in heads
        if not machine_id or str(item.get("machine_id")) != machine_id
    ]

    bundle_count = 0
    total_size = 0
    bundles_dir = root / "bundles"
    if accessible and bundles_dir.is_dir():
        for bundle in bundles_dir.iterdir():
            if not bundle.is_dir():
                continue
            bundle_count += 1
            for path in bundle.rglob("*"):
                if path.is_file():
                    try:
                        total_size += int(path.stat().st_size)
                    except OSError:
                        pass

    return {
        "status": "READY" if accessible else "UNAVAILABLE",
        "configured": True,
        "provider": config["provider"],
        "root": str(root),
        "accessible": accessible,
        "machine_id": machine_id or None,
        "remote_machines": len(remote),
        "bundle_count": bundle_count,
        "total_size_bytes": total_size,
        "include_market": bool(config["include_market"]),
        "writes": 0,
    }


def _prepare_enabled_transport(
    *,
    locations: RuntimeLocations,
) -> tuple[dict[str, Any], Path, dict[str, Any]] | None:
    config = resolve_transport_config(locations=locations)
    if not config["enabled"]:
        return None
    root = _ensure_safe_transport_root(
        Path(str(config["root"])),
        locations=locations,
    )
    try:
        _ensure_transport_dirs(root)
    except OSError as exc:
        raise DataToolError(
            f"TRANSPORT_UNAVAILABLE: Google Drive transport에 접근할 수 없습니다: {root}"
        ) from exc
    state = _ensure_continuity_state(locations)
    return config, root, state


def pre_sync(
    *,
    locations: RuntimeLocations | None = None,
    retry_count: int = DEFAULT_RETRY_COUNT,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> dict[str, Any]:
    runtime = locations or RuntimeLocations.current()
    prepared = _prepare_enabled_transport(locations=runtime)
    if prepared is None:
        return {"status": "DISABLED", "changed": False}
    config, root, state = prepared
    machine_id = str(state["machine_id"])
    resolver = _ancestry_resolver(root, state=state)
    remote_heads = [
        item for item in _heads(root)
        if str(item.get("machine_id")) != machine_id
    ]
    candidate = _select_remote_head(remote_heads, is_ancestor=resolver)
    if candidate is None:
        return {
            "status": "NO_REMOTE",
            "changed": False,
            "machine_id": machine_id,
        }

    bundle_id = str(candidate["bundle_id"])
    bundle, manifest = _wait_for_bundle(
        root,
        bundle_id,
        retry_count=retry_count,
        retry_delay_seconds=retry_delay_seconds,
    )
    selected = [
        domain
        for domain in _auto_domains(config)
        if domain in dict(manifest.get("domains") or {})
    ]
    if not selected:
        return {
            "status": "NO_REMOTE_DOMAIN",
            "changed": False,
            "remote_machine_id": candidate["machine_id"],
            "bundle_id": bundle_id,
        }

    plan = import_handoff(
        bundle,
        domains=selected,
        locations=runtime,
        strict=True,
        dry_run=True,
        is_ancestor=resolver,
    )
    if plan["status"] == "BLOCKED":
        raise DataToolError(
            "RUNTIME_TRANSPORT_CONFLICT: "
            + " | ".join(
                f"{item['domain']}={item['reason']}"
                for item in plan["conflicts"]
            )
        )

    remote_actions = [
        item for item in plan["plans"]
        if item["action"] in {
            "INSTALL",
            "FAST_FORWARD",
            "REPLACE_FRESH_BOOTSTRAP",
        }
    ]
    local_actions = [
        item for item in plan["plans"]
        if item["action"] == "LOCAL_AHEAD"
    ]
    if remote_actions and local_actions:
        raise DataToolError(
            "RUNTIME_TRANSPORT_CONFLICT: domain별 lineage 방향이 서로 다릅니다."
        )

    if local_actions:
        return {
            "status": "LOCAL_AHEAD",
            "changed": False,
            "remote_machine_id": candidate["machine_id"],
            "bundle_id": bundle_id,
            "plans": plan["plans"],
        }

    applied = import_handoff(
        bundle,
        domains=selected,
        locations=runtime,
        strict=True,
        is_ancestor=resolver,
    )
    if applied["status"] == "BLOCKED":
        raise DataToolError("RUNTIME_TRANSPORT_CONFLICT: import가 차단되었습니다.")

    adopted = _head_from_manifest(
        manifest,
        machine_id=machine_id,
        adopted_from=str(candidate["machine_id"]),
    )
    _write_head(root, adopted)
    return {
        "status": "FAST_FORWARD" if remote_actions else "CURRENT",
        "changed": bool(applied["installed"]),
        "remote_machine_id": candidate["machine_id"],
        "bundle_id": bundle_id,
        "installed": applied["installed"],
        "plans": applied["plans"],
    }


def reconcile_remote(
    *,
    prefer_remote: bool,
    confirm: bool,
    domains: list[str] | None = None,
    locations: RuntimeLocations | None = None,
    retry_count: int = DEFAULT_RETRY_COUNT,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> dict[str, Any]:
    runtime = locations or RuntimeLocations.current()
    if not prefer_remote:
        raise DataToolError(
            "초기 Runtime 정렬은 현재 --prefer-remote 방식만 지원합니다."
        )
    if not confirm:
        raise DataToolError(
            "기존 local Runtime을 remote 기준으로 정렬하려면 --confirm이 필요합니다."
        )

    prepared = _prepare_enabled_transport(locations=runtime)
    if prepared is None:
        raise DataToolError("Runtime Transport가 설정되지 않았습니다.")
    config, root, state = prepared
    machine_id = str(state["machine_id"])
    resolver = _ancestry_resolver(root, state=state)
    remote_heads = [
        item for item in _heads(root)
        if str(item.get("machine_id")) != machine_id
    ]
    candidate = _select_remote_head(remote_heads, is_ancestor=resolver)
    if candidate is None:
        raise DataToolError("정렬할 remote Runtime head가 없습니다.")

    bundle_id = str(candidate["bundle_id"])
    bundle, manifest = _wait_for_bundle(
        root,
        bundle_id,
        retry_count=retry_count,
        retry_delay_seconds=retry_delay_seconds,
    )

    allowed = _auto_domains(config)
    if domains is None:
        selected = [
            domain
            for domain in allowed
            if domain in dict(manifest.get("domains") or {})
        ]
    else:
        requested = []
        for raw in domains:
            domain = str(raw).strip().lower()
            if not domain:
                continue
            if domain not in allowed:
                raise DataToolError(
                    f"자동 transport 정렬 대상이 아닌 domain입니다: {domain}"
                )
            if domain not in requested:
                requested.append(domain)
        selected = [
            domain
            for domain in requested
            if domain in dict(manifest.get("domains") or {})
        ]

    if not selected:
        raise DataToolError("정렬할 remote Runtime domain이 없습니다.")

    plan = import_handoff(
        bundle,
        domains=selected,
        locations=runtime,
        strict=True,
        dry_run=True,
        is_ancestor=resolver,
        allow_unknown_lineage_replace=True,
    )
    if plan["status"] == "BLOCKED":
        raise DataToolError(
            "RUNTIME_TRANSPORT_CONFLICT: "
            + " | ".join(
                f"{item['domain']}={item['reason']}"
                for item in plan["conflicts"]
            )
        )

    local_ahead = [
        item
        for item in plan["plans"]
        if item["action"] == "LOCAL_AHEAD"
    ]
    if local_ahead:
        raise DataToolError(
            "RUNTIME_TRANSPORT_CONFLICT: known local lineage가 remote보다 최신입니다: "
            + " | ".join(
                f"{item['domain']}={item['reason']}"
                for item in local_ahead
            )
        )

    applied = import_handoff(
        bundle,
        domains=selected,
        locations=runtime,
        strict=True,
        is_ancestor=resolver,
        allow_unknown_lineage_replace=True,
    )
    if applied["status"] == "BLOCKED":
        raise DataToolError("RUNTIME_TRANSPORT_CONFLICT: 초기 정렬이 차단되었습니다.")

    adopted = _head_from_manifest(
        manifest,
        machine_id=machine_id,
        adopted_from=str(candidate["machine_id"]),
        selected_domains=selected,
    )
    _write_head(root, adopted)
    reconciled = [
        item["domain"]
        for item in plan["plans"]
        if item["action"] == "REPLACE_UNKNOWN_LINEAGE"
    ]
    return {
        "status": "RECONCILED",
        "changed": bool(applied["installed"]),
        "remote_machine_id": candidate["machine_id"],
        "bundle_id": bundle_id,
        "installed": applied["installed"],
        "reconciled": reconciled,
        "plans": plan["plans"],
        "production_selection_policy_changed": False,
    }



def _local_domain_hashes(
    *,
    locations: RuntimeLocations,
    domains: list[str],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for domain in domains:
        path = _runtime_db_path(locations, domain)
        if path.is_file():
            result[domain] = sqlite_content_sha256(path)
    return result


def _publish_needed(
    *,
    locations: RuntimeLocations,
    root: Path,
    state: dict[str, Any],
    domains: list[str],
) -> tuple[bool, list[str]]:
    current = _local_domain_hashes(locations=locations, domains=domains)
    own = _own_head(root, str(state["machine_id"]))
    reasons: list[str] = []

    own_domains = dict((own or {}).get("domains") or {})
    for domain in own_domains:
        if domain in domains and domain not in current:
            raise DataToolError(
                f"LOCAL_DOMAIN_MISSING: published durable domain이 로컬에서 사라졌습니다: "
                f"{domain}"
            )

    for domain, current_hash in current.items():
        receipt = dict(state.get("domains", {}).get(domain) or {})
        if not receipt:
            reasons.append(f"{domain}:NO_LOCAL_LINEAGE")
            continue
        if str(receipt.get("local_content_sha256") or "") != current_hash:
            reasons.append(f"{domain}:CONTENT_CHANGED")
            continue
        head_domain = own_domains.get(domain)
        if not isinstance(head_domain, dict):
            reasons.append(f"{domain}:HEAD_MISSING")
            continue
        if (
            str(head_domain.get("domain_id") or "")
            != str(receipt.get("domain_id") or "")
            or str(head_domain.get("snapshot_id") or "")
            != str(receipt.get("snapshot_id") or "")
        ):
            reasons.append(f"{domain}:HEAD_STALE")

    return bool(reasons), reasons


def _publish_bundle(
    *,
    root: Path,
    local_bundle: Path,
    manifest: dict[str, Any],
    machine_id: str,
) -> Path:
    bundle_id = str(manifest["bundle_id"])
    final = root / "bundles" / bundle_id
    if final.exists():
        existing = inspect_handoff(final)
        if str(existing.get("bundle_id")) != bundle_id:
            raise DataToolError("기존 Transport bundle ID가 일치하지 않습니다.")
        return final

    staging = root / ".staging" / (
        f"{bundle_id}.{machine_id}.{os.getpid()}.tmp"
    )
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    try:
        shutil.copytree(local_bundle, staging)
        staged = inspect_handoff(staging)
        if str(staged.get("bundle_id")) != bundle_id:
            raise DataToolError("Staged Transport bundle ID가 일치하지 않습니다.")
        try:
            os.replace(staging, final)
        except PermissionError:
            if final.exists():
                raise
            shutil.copytree(staging, final)
            inspect_handoff(final)
            shutil.rmtree(staging, ignore_errors=True)
        inspect_handoff(final)
        return final
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def post_sync(
    *,
    locations: RuntimeLocations | None = None,
    force_checkpoint: bool = False,
) -> dict[str, Any]:
    runtime = locations or RuntimeLocations.current()
    prepared = _prepare_enabled_transport(locations=runtime)
    if prepared is None:
        return {"status": "DISABLED", "published": False}
    config, root, state = prepared
    domains = _auto_domains(config)
    needed, reasons = _publish_needed(
        locations=runtime,
        root=root,
        state=state,
        domains=domains,
    )
    if not needed and not force_checkpoint:
        return {
            "status": "CURRENT",
            "published": False,
            "reason": "RUNTIME_UNCHANGED",
        }
    if force_checkpoint and not reasons:
        reasons = ["MANUAL_CHECKPOINT"]

    exported = export_handoff(
        domains=domains,
        locations=runtime,
    )
    local_bundle = Path(str(exported["bundle"]))
    manifest = inspect_handoff(local_bundle)
    final = _publish_bundle(
        root=root,
        local_bundle=local_bundle,
        manifest=manifest,
        machine_id=str(state["machine_id"]),
    )
    refreshed_state = _load_state(runtime.continuity_state)
    head = _head_from_manifest(
        manifest,
        machine_id=str(refreshed_state["machine_id"]),
    )
    _write_head(root, head)
    return {
        "status": "PUBLISHED",
        "published": True,
        "bundle_id": manifest["bundle_id"],
        "bundle": str(final),
        "domains": sorted(dict(manifest.get("domains") or {})),
        "reasons": reasons,
    }
