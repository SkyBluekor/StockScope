from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from tools.data.backup_runtime import create_backup
from tools.data.common import DataToolError
from tools.runtime.handoff import (
    RuntimeLocations,
    _load_state,
    _save_state,
    _validator,
    export_handoff,
    inspect_handoff,
    sqlite_content_sha256,
)
from tools.runtime.transport import (
    _ancestry_resolver,
    _auto_domains,
    _head_dominates,
    _head_from_manifest,
    _heads,
    _own_head,
    _publish_bundle,
    _runtime_db_path,
    _select_remote_head,
    _wait_for_bundle,
    _write_head,
    _ensure_safe_transport_root,
    resolve_transport_config,
)

LOCAL_OVERRIDE_DOMAINS = ("holdings", "simulation")
RECONCILIATION_VERSION = "RT_L1_LOCAL_AUTHORITY_V1"


def _head_tokens(root: Path) -> str:
    """Detect any remote/own head change before publication."""
    return json.dumps(
        sorted(_heads(root), key=lambda h: str(h["machine_id"])),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _inspect(
    *,
    locations: RuntimeLocations,
    domains: Iterable[str] | None,
) -> dict[str, Any]:
    requested = tuple(dict.fromkeys(domains or LOCAL_OVERRIDE_DOMAINS))
    if not requested or set(requested) - set(LOCAL_OVERRIDE_DOMAINS):
        raise DataToolError("LOCAL_RECONCILE_DOMAIN_NOT_ALLOWED: holdings,simulation only")

    config = resolve_transport_config(locations=locations)
    if not config["root"]:
        raise DataToolError("Runtime Transport root를 먼저 configure 해야 합니다.")
    root = _ensure_safe_transport_root(
        Path(str(config["root"])), locations=locations
    )
    if not root.is_dir():
        raise DataToolError("Runtime Transport root가 접근 불가능합니다.")
    if not locations.continuity_state.is_file():
        raise DataToolError("LOCAL_RECONCILE_CONTINUITY_MISSING")
    state = _load_state(locations.continuity_state)
    machine_id = str(state["machine_id"])
    resolver = _ancestry_resolver(root, state=state)
    remote = _select_remote_head(
        [h for h in _heads(root) if str(h["machine_id"]) != machine_id],
        is_ancestor=resolver,
    )
    if remote is None:
        raise DataToolError("LOCAL_RECONCILE_NO_REMOTE_HEAD")
    bundle, manifest = _wait_for_bundle(
        root, str(remote["bundle_id"]),
        retry_count=5, retry_delay_seconds=0.4,
    )
    remote_domains = dict(remote.get("domains") or {})
    manifest_domains = dict(manifest.get("domains") or {})
    for domain, raw in remote_domains.items():
        entry = manifest_domains.get(domain)
        if not isinstance(raw, dict) or not isinstance(entry, dict) or any((
            raw.get("domain_id") != entry.get("domain_id"),
            raw.get("snapshot_id") != entry.get("snapshot_id"),
            raw.get("content_sha256") != entry.get("content_sha256"),
        )):
            raise DataToolError("LOCAL_RECONCILE_REMOTE_HEAD_BUNDLE_MISMATCH")
    allowed = set(_auto_domains(config))
    if set(remote_domains) - allowed:
        raise DataToolError("LOCAL_RECONCILE_REMOTE_DOMAIN_OUT_OF_SCOPE")
    if set(requested) - allowed:
        raise DataToolError("LOCAL_RECONCILE_DOMAIN_DISABLED")

    active = {
        d for d in allowed if _runtime_db_path(locations, d).is_file()
    }
    missing_remote = set(remote_domains) - active
    if missing_remote:
        raise DataToolError(
            "LOCAL_RECONCILE_REMOTE_DOMAIN_MISSING_LOCALLY: "
            + ", ".join(sorted(missing_remote))
        )
    missing_selected = set(requested) - active
    if missing_selected:
        raise DataToolError(
            "LOCAL_RECONCILE_SELECTED_DOMAIN_MISSING: "
            + ", ".join(sorted(missing_selected))
        )

    all_domains = sorted(active | set(remote_domains))
    local_hashes: dict[str, str] = {}
    for domain in all_domains:
        path = _runtime_db_path(locations, domain)
        _validator(domain)(path)
        local_hashes[domain] = sqlite_content_sha256(path)

    own = _own_head(root, machine_id)
    if (
        own is not None
        and _head_dominates(own, remote, is_ancestor=resolver)
        and all(
            isinstance(info, dict)
            and info.get("content_sha256") == local_hashes.get(domain)
            for domain, info in dict(own.get("domains") or {}).items()
        )
        and set(own.get("domains") or {}) == set(all_domains)
    ):
        return {
            "status": "CURRENT",
            "changed": False,
            "remote_machine_id": remote["machine_id"],
            "bundle_id": own["bundle_id"],
            "domains": all_domains,
            "writes": 0,
        }

    remote_conflicts = [
        domain for domain in all_domains
        if domain not in requested
        and domain in remote_domains
        and str(remote_domains[domain]["content_sha256"]) != local_hashes[domain]
    ]
    if remote_conflicts:
        raise DataToolError(
            "LOCAL_RECONCILE_UNAPPROVED_DOMAIN_CONFLICT: "
            + ", ".join(remote_conflicts)
        )

    return {
        "status": "PLANNED",
        "writes": 0,
        "changed": False,
        "remote_machine_id": remote["machine_id"],
        "remote_bundle_id": remote["bundle_id"],
        "domains": all_domains,
        "prefer_local": list(requested),
        "preserve_equal": sorted(set(all_domains) - set(requested)),
        "_root": root,
        "_state": state,
        "_remote": remote,
        "_remote_manifest": manifest,
        "_local_hashes": local_hashes,
        "_head_tokens": _head_tokens(root),
        "_config": config,
    }


def reconcile_local(
    *,
    domains: Iterable[str] | None = None,
    confirm: bool = False,
    dry_run: bool = False,
    locations: RuntimeLocations | None = None,
) -> dict[str, Any]:
    """Explicitly prefer local holdings/simulation without ever replacing local DBs.

    Dry-run does not create directories, bundles, receipts, backups or heads.
    Execute only while automatic transport is disabled and the other PC is idle.
    """
    runtime = locations or RuntimeLocations.current()
    plan = _inspect(locations=runtime, domains=domains)
    if plan["status"] == "CURRENT":
        return plan
    public = {
        k: v for k, v in plan.items() if not k.startswith("_")
    }
    if dry_run:
        return public
    if not confirm:
        raise DataToolError("로컬 우선 게시에는 --confirm이 필요합니다.")
    if plan["_config"]["enabled"]:
        raise DataToolError(
            "LOCAL_RECONCILE_REQUIRES_DISABLED_TRANSPORT: 먼저 transport disable"
        )

    backup = create_backup()
    if not (Path(backup) / "backup_manifest.json").is_file():
        raise DataToolError("LOCAL_RECONCILE_BACKUP_REQUIRED")

    root: Path = plan["_root"]
    state: dict[str, Any] = plan["_state"]
    old_state = json.loads(json.dumps(state))
    selected = set(plan["prefer_local"])
    remote_domains = dict(plan["_remote"]["domains"])
    identity_overrides = {
        domain: {
            "domain_id": raw["domain_id"],
            "snapshot_id": raw["snapshot_id"],
            "parent_snapshot_id": raw.get("parent_snapshot_id"),
        }
        for domain, raw in remote_domains.items()
    }
    exported = export_handoff(
        domains=plan["domains"],
        locations=runtime,
        identity_overrides=identity_overrides,
        defer_state_update=True,
        reconciliation_record={
            "contract_version": RECONCILIATION_VERSION,
            "policy": "EXPLICIT_PREFER_LOCAL_WITHOUT_MERGE",
            "superseded_machine_id": plan["remote_machine_id"],
            "superseded_bundle_id": plan["remote_bundle_id"],
            "overridden_domains": sorted(selected),
            "preserved_equal_domains": plan["preserve_equal"],
        },
    )
    manifest = inspect_handoff(Path(str(exported["bundle"])))
    new_domains = dict(manifest["domains"])
    for domain in plan["domains"]:
        if (
            domain not in new_domains
            or new_domains[domain]["content_sha256"] != plan["_local_hashes"][domain]
        ):
            raise DataToolError("LOCAL_RECONCILE_INPUT_CHANGED_DURING_EXPORT")

    def verify_fence() -> None:
        if _head_tokens(root) != plan["_head_tokens"]:
            raise DataToolError("LOCAL_RECONCILE_REMOTE_HEAD_CHANGED")
        if _load_state(runtime.continuity_state) != old_state:
            raise DataToolError("LOCAL_RECONCILE_CONTINUITY_CHANGED")
        for domain, expected in plan["_local_hashes"].items():
            if sqlite_content_sha256(_runtime_db_path(runtime, domain)) != expected:
                raise DataToolError("LOCAL_RECONCILE_LOCAL_DB_CHANGED: " + domain)

    verify_fence()
    final = _publish_bundle(
        root=root,
        local_bundle=Path(str(exported["bundle"])),
        manifest=manifest,
        machine_id=str(state["machine_id"]),
    )
    verify_fence()

    updates = dict(exported["state_updates"])
    state["domains"].update(updates)
    head = _head_from_manifest(
        manifest, machine_id=str(state["machine_id"])
    )
    resolver = _ancestry_resolver(root, state=state)
    if not _head_dominates(head, plan["_remote"], is_ancestor=resolver):
        raise DataToolError("LOCAL_RECONCILE_LINEAGE_NOT_DESCENDANT")

    try:
        _save_state(runtime.continuity_state, state)
        _write_head(root, head)
    except Exception:
        # No head was intentionally published until after state was durable.
        own = _own_head(root, str(state["machine_id"]))
        if own is None or own.get("bundle_id") != manifest["bundle_id"]:
            _save_state(runtime.continuity_state, old_state)
        raise
    return {
        "status": "PUBLISHED",
        "published": True,
        "bundle_id": manifest["bundle_id"],
        "bundle": str(final),
        "remote_machine_id": plan["remote_machine_id"],
        "prefer_local": sorted(selected),
        "domains": plan["domains"],
        "backup": str(backup),
        "transport_enabled": False,
        "production_selection_policy_changed": False,
    }
