from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Mapping

from tools.data.common import (
    DataToolError,
    iso_now,
    sha256_file,
    sqlite_snapshot,
    write_json_atomic,
)


FRESH_BOOTSTRAP_STATE_CONTRACT = "STOCKSCOPE_FRESH_BOOTSTRAP_STATE_V1"
FRESH_BOOTSTRAP_STATE_FILE = "fresh_bootstrap_state.json"


def state_path(continuity_state: Path) -> Path:
    return Path(continuity_state).parent / FRESH_BOOTSTRAP_STATE_FILE


def sqlite_content_sha256(path: Path) -> str:
    source = Path(path)
    if not source.is_file():
        raise DataToolError(
            f"Fresh bootstrap fingerprint 대상 DB가 없습니다: {source}"
        )
    with tempfile.TemporaryDirectory(
        prefix="stockscope-fresh-bootstrap-fingerprint-"
    ) as raw:
        snapshot = Path(raw) / "snapshot.db"
        sqlite_snapshot(source, snapshot)
        return sha256_file(snapshot)


def load_state(continuity_state: Path) -> dict:
    path = state_path(continuity_state)
    if not path.is_file():
        return {
            "contract_version": FRESH_BOOTSTRAP_STATE_CONTRACT,
            "domains": {},
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataToolError(
            f"Fresh bootstrap state를 읽을 수 없습니다: {path}"
        ) from exc
    if payload.get("contract_version") != FRESH_BOOTSTRAP_STATE_CONTRACT:
        raise DataToolError("지원하지 않는 Fresh bootstrap state입니다.")
    if not isinstance(payload.get("domains"), dict):
        raise DataToolError("Fresh bootstrap domains가 JSON object가 아닙니다.")
    return payload


def pristine_candidates(
    *,
    continuity_state: Path,
    domain_paths: Mapping[str, Path],
) -> set[str]:
    """Return domains that may safely keep/receive a pristine-bootstrap marker.

    A missing DB is eligible. An existing DB is eligible only when a previous
    bootstrap marker exists and still matches the exact SQLite snapshot hash.
    User-modified or unknown existing DBs are never newly marked pristine.
    """

    state = load_state(continuity_state)
    domains = dict(state.get("domains") or {})
    eligible: set[str] = set()
    for domain, raw_path in domain_paths.items():
        path = Path(raw_path)
        if not path.is_file():
            eligible.add(domain)
            continue
        entry = domains.get(domain)
        expected = (
            str(entry.get("content_sha256") or "")
            if isinstance(entry, dict)
            else ""
        )
        if expected and sqlite_content_sha256(path) == expected:
            eligible.add(domain)
    return eligible


def record_pristine_domains(
    *,
    continuity_state: Path,
    domain_paths: Mapping[str, Path],
    eligible_domains: set[str],
) -> dict:
    state = load_state(continuity_state)
    domains = dict(state.get("domains") or {})
    changed = False

    for domain in sorted(eligible_domains):
        path = Path(domain_paths[domain])
        if not path.is_file():
            continue
        domains[domain] = {
            "content_sha256": sqlite_content_sha256(path),
            "state": "VERIFIED_EMPTY_BOOTSTRAP",
            "updated_at": iso_now(),
        }
        changed = True

    if changed:
        payload = {
            "contract_version": FRESH_BOOTSTRAP_STATE_CONTRACT,
            "domains": domains,
            "updated_at": iso_now(),
        }
        write_json_atomic(state_path(continuity_state), payload)
        return payload
    return {
        "contract_version": FRESH_BOOTSTRAP_STATE_CONTRACT,
        "domains": domains,
    }


def domain_hash(continuity_state: Path, domain: str) -> str | None:
    state = load_state(continuity_state)
    entry = dict((state.get("domains") or {}).get(domain) or {})
    value = str(entry.get("content_sha256") or "").strip()
    return value or None


def consume_domain(continuity_state: Path, domain: str) -> None:
    path = state_path(continuity_state)
    if not path.is_file():
        return
    state = load_state(continuity_state)
    domains = dict(state.get("domains") or {})
    if domain not in domains:
        return
    domains.pop(domain, None)
    write_json_atomic(
        path,
        {
            "contract_version": FRESH_BOOTSTRAP_STATE_CONTRACT,
            "domains": domains,
            "updated_at": iso_now(),
        },
    )
