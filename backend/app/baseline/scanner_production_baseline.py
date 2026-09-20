from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

BASELINE_SCHEMA_VERSION = "stockscope.sim0.v1"
EXPECTED_SCANNER_VERSION = "0.21.3.7"
BASELINE_FILENAME = f"scanner-production-baseline_{EXPECTED_SCANNER_VERSION}.json"

# These are the smallest stable production entry points we already know drive the
# Scanner path. Their local app.* imports are followed recursively, so Strategy,
# Risk, Entry/Stop/Target and settings modules actually used by Scanner are pulled
# into the fingerprint without hashing research/audit code.
PRODUCTION_ENTRYPOINTS = (
    "backend/app/backtest/scanner.py",
    "backend/app/backtest/candidate_priority.py",
    "backend/app/backtest/market_store.py",
)

EXCLUDED_PARTS = {
    "scanner_quality",
    "baseline",
    "simulation",
    "simulator",
    "runtime",
    "tests",
    "test",
    "__pycache__",
}

STATIC_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml"}

POLICY_SPEC: dict[str, Any] = {
    "scanner_version": EXPECTED_SCANNER_VERSION,
    "ma120": "NO_LOOKAHEAD",
    "historical_sector_rs": "TEMPORAL_GATE",
    "candidate_state": "READY_WATCH_RISK_CURRENT_PRODUCTION",
    "target1": "CAP_1_5R",
    "target1_explainability": True,
    "ranking_tie_break": "STRUCTURAL_TARGET_NEAREST_PROMOTE_ONE_EXACT_BASE_PRIORITY_TIE",
    "overextension_guard": "NOT_PRODUCTION",
    "volume_low_guard": "REJECTED_NOT_PRODUCTION",
}

RESEARCH_STATUS: dict[str, Any] = {
    "B.2.5": {
        "status": "CLOSED",
        "production": "STRUCTURAL_TARGET_TIE_BREAK_RETAINED",
    },
    "B.2.6": {
        "status": "CLOSED",
        "production": False,
        "result": "OVEREXTENSION_RESEARCH_ONLY",
    },
    "B.2.7": {
        "status": "CLOSED",
        "production": False,
        "result": "VOLUME_LOW_GUARD_REJECTED_FRESH_HOLDOUT",
    },
}


class BaselineError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    scanner_version: str
    production_fingerprint_expected: str
    production_fingerprint_current: str
    policy_fingerprint_expected: str
    policy_fingerprint_current: str
    changed_files: tuple[dict[str, Any], ...]
    missing_files: tuple[str, ...]
    extra_relevant_files: tuple[str, ...]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_object(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def policy_fingerprint(spec: dict[str, Any] | None = None) -> str:
    return fingerprint_object(POLICY_SPEC if spec is None else spec)


def _is_excluded(path: Path, app_root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(app_root.resolve())
    except ValueError:
        return True
    return any(part in EXCLUDED_PARTS for part in rel.parts)


def _module_candidates(app_root: Path, module_name: str) -> list[Path]:
    if not module_name.startswith("app"):
        return []
    tail = module_name.split(".")[1:]
    base = app_root.joinpath(*tail)
    result: list[Path] = []
    py = base.with_suffix(".py")
    init = base / "__init__.py"
    if py.is_file():
        result.append(py)
    if init.is_file():
        result.append(init)
    return result


def _package_name_for_path(path: Path, app_root: Path) -> str:
    rel = path.resolve().relative_to(app_root.resolve())
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        module_parts = parts[:-1]
    else:
        module_parts = parts[:-1]
    return ".".join(["app", *module_parts])


def _resolve_from_module(current: Path, app_root: Path, node: ast.ImportFrom) -> str | None:
    module = node.module or ""
    if node.level <= 0:
        return module or None
    package = _package_name_for_path(current, app_root)
    package_parts = package.split(".") if package else ["app"]
    # level=1 means current package, level=2 means parent package, etc.
    up = max(0, node.level - 1)
    if up:
        package_parts = package_parts[:-up] if up < len(package_parts) else ["app"]
    base = ".".join(package_parts)
    return f"{base}.{module}" if module else base


def _parent_init_files(path: Path, app_root: Path) -> list[Path]:
    result: list[Path] = []
    parent = path.parent
    root = app_root.resolve()
    while True:
        try:
            parent.resolve().relative_to(root)
        except ValueError:
            break
        init = parent / "__init__.py"
        if init.is_file():
            result.append(init)
        if parent.resolve() == root:
            break
        parent = parent.parent
    return result


def _local_imports(path: Path, app_root: Path) -> list[Path]:
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise BaselineError(f"Unable to parse production source {path}: {exc}") from exc

    found: set[Path] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for candidate in _module_candidates(app_root, alias.name):
                    found.add(candidate)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from_module(path, app_root, node)
            if not base:
                continue
            for candidate in _module_candidates(app_root, base):
                found.add(candidate)
            # `from app.foo import bar` may import app.foo.bar as a module.
            for alias in node.names:
                if alias.name == "*":
                    continue
                for candidate in _module_candidates(app_root, f"{base}.{alias.name}"):
                    found.add(candidate)
    return sorted(found)


def discover_production_files(project_root: Path) -> list[Path]:
    root = project_root.resolve()
    app_root = root / "backend" / "app"
    if not app_root.is_dir():
        raise BaselineError(f"Missing backend/app under project root: {root}")

    seeds = [root / rel for rel in PRODUCTION_ENTRYPOINTS]
    missing = [str(path.relative_to(root)) for path in seeds if not path.is_file()]
    if missing:
        raise BaselineError(f"Missing required production entrypoints: {', '.join(missing)}")

    queue: list[Path] = list(seeds)
    seen: set[Path] = set()
    while queue:
        path = queue.pop(0).resolve()
        if path in seen or _is_excluded(path, app_root):
            continue
        seen.add(path)
        for init in _parent_init_files(path, app_root):
            if init.resolve() not in seen and not _is_excluded(init, app_root):
                queue.append(init)
        if path.suffix == ".py":
            for dep in _local_imports(path, app_root):
                if dep.resolve() not in seen and not _is_excluded(dep, app_root):
                    queue.append(dep)

    # Include static configuration that lives inside the production app package.
    # This avoids missing a scanner/risk/target JSON/YAML loaded dynamically.
    for candidate in app_root.rglob("*"):
        if not candidate.is_file() or candidate.suffix.lower() not in STATIC_CONFIG_SUFFIXES:
            continue
        if not _is_excluded(candidate, app_root):
            seen.add(candidate.resolve())

    return sorted(seen, key=lambda p: p.relative_to(root).as_posix())


def file_manifest(project_root: Path, files: Iterable[Path]) -> list[dict[str, str]]:
    root = project_root.resolve()
    rows: list[dict[str, str]] = []
    for path in sorted((p.resolve() for p in files), key=lambda p: p.relative_to(root).as_posix()):
        rows.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    return rows


def aggregate_production_fingerprint(rows: Iterable[dict[str, str]]) -> str:
    canonical_rows = [
        {"path": str(row["path"]), "sha256": str(row["sha256"])}
        for row in sorted(rows, key=lambda row: str(row["path"]))
    ]
    return fingerprint_object(canonical_rows)


def detect_scanner_version(project_root: Path) -> str:
    scanner_path = project_root.resolve() / "backend" / "app" / "backtest" / "scanner.py"
    if not scanner_path.is_file():
        raise BaselineError(f"Missing scanner source: {scanner_path}")
    try:
        tree = ast.parse(scanner_path.read_text(encoding="utf-8-sig"), filename=str(scanner_path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise BaselineError(f"Unable to parse scanner version: {exc}") from exc

    def literal_string(node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "StockScannerService":
            for stmt in node.body:
                if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                    targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                    if any(isinstance(target, ast.Name) and target.id == "VERSION" for target in targets):
                        value = literal_string(stmt.value)
                        if value:
                            return value
    # Defensive fallback for a module-level VERSION.
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "VERSION" for target in targets):
                value = literal_string(node.value)
                if value:
                    return value
    raise BaselineError("Could not statically locate StockScannerService.VERSION in scanner.py")


def _run_git(project_root: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=project_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        return 127, str(exc)
    return proc.returncode, proc.stdout.strip()


def git_snapshot(project_root: Path) -> dict[str, Any]:
    code, inside = _run_git(project_root, "rev-parse", "--is-inside-work-tree")
    if code != 0 or inside.lower() != "true":
        return {
            "available": False,
            "head": None,
            "branch": None,
            "working_tree_dirty": None,
            "status_porcelain": [],
        }
    _, head = _run_git(project_root, "rev-parse", "HEAD")
    _, branch = _run_git(project_root, "branch", "--show-current")
    _, status = _run_git(project_root, "status", "--porcelain=v1", "--untracked-files=all")
    entries = [line for line in status.splitlines() if line]
    return {
        "available": True,
        "head": head or None,
        "branch": branch or None,
        "working_tree_dirty": bool(entries),
        "status_porcelain": entries,
    }


def baseline_id(scanner_version: str, production_fp: str, policy_fp: str) -> str:
    seed = fingerprint_object(
        {
            "scanner_version": scanner_version,
            "production_fingerprint": production_fp,
            "policy_fingerprint": policy_fp,
        }
    )
    return f"SS-SCANNER-{scanner_version}-{seed[:16]}"


def build_manifest(
    project_root: Path,
    *,
    created_at: str | None = None,
    git: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    scanner_version = detect_scanner_version(root)
    if scanner_version != EXPECTED_SCANNER_VERSION:
        raise BaselineError(
            f"SCANNER_VERSION_MISMATCH: expected {EXPECTED_SCANNER_VERSION}, actual {scanner_version}"
        )
    files = discover_production_files(root)
    rows = file_manifest(root, files)
    prod_fp = aggregate_production_fingerprint(rows)
    pol_fp = policy_fingerprint()
    git_info = git_snapshot(root) if git is None else git
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "baseline_id": baseline_id(scanner_version, prod_fp, pol_fp),
        "scanner_version": scanner_version,
        "created_at": created_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "production_changed": False,
        "git": git_info,
        "production_scope": {
            "discovery": "recursive local app.* import graph from production entrypoints + static app configs",
            "entrypoints": list(PRODUCTION_ENTRYPOINTS),
            "excluded_parts": sorted(EXCLUDED_PARTS),
            "file_count": len(rows),
        },
        "production_files": rows,
        "production_fingerprint": prod_fp,
        "policies": POLICY_SPEC,
        "policy_fingerprint": pol_fp,
        "research_status": RESEARCH_STATUS,
        "simulation_contract": {
            "required_reference": "scanner_baseline_id",
            "recommended_fields": [
                "scanner_version",
                "scanner_baseline_id",
                "production_fingerprint",
                "policy_fingerprint",
            ],
        },
    }


def freeze_baseline(project_root: Path, manifest_path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    root = project_root.resolve()
    target = manifest_path or (root / "backend" / "runtime" / "baseline" / BASELINE_FILENAME)
    target = target.resolve()
    if target.exists():
        raise BaselineError(f"BASELINE_ALREADY_EXISTS: {target}")
    manifest = build_manifest(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target, manifest


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"Unable to read baseline manifest {path}: {exc}") from exc


def _hash_current_recorded_files(project_root: Path, recorded: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[str]]:
    root = project_root.resolve()
    rows: list[dict[str, str]] = []
    missing: list[str] = []
    for row in recorded:
        rel = str(row.get("path") or "")
        if not rel:
            continue
        path = root / rel
        if not path.is_file():
            missing.append(rel)
            continue
        rows.append({"path": rel, "sha256": sha256_file(path)})
    return rows, sorted(missing)


def verify_baseline(project_root: Path, manifest: dict[str, Any]) -> VerificationResult:
    root = project_root.resolve()
    expected_rows = list(manifest.get("production_files") or [])
    expected_map = {str(row.get("path")): str(row.get("sha256")) for row in expected_rows}
    current_rows, missing = _hash_current_recorded_files(root, expected_rows)
    current_map = {row["path"]: row["sha256"] for row in current_rows}
    changed: list[dict[str, Any]] = []
    for rel, expected in sorted(expected_map.items()):
        current = current_map.get(rel)
        if current is not None and current != expected:
            changed.append({"path": rel, "expected": expected, "current": current})

    # Rediscover to catch a newly imported production dependency. A scanner.py
    # change would already mismatch, but reporting the extra dependency is useful.
    try:
        rediscovered = discover_production_files(root)
        rediscovered_rel = {path.relative_to(root).as_posix() for path in rediscovered}
    except BaselineError:
        rediscovered_rel = set()
    extra = sorted(rediscovered_rel - set(expected_map))

    current_prod_fp = aggregate_production_fingerprint(current_rows) if not missing else "MISSING_FILES"
    expected_prod_fp = str(manifest.get("production_fingerprint") or "")
    current_policy_fp = policy_fingerprint()
    expected_policy_fp = str(manifest.get("policy_fingerprint") or "")
    try:
        version = detect_scanner_version(root)
    except BaselineError:
        version = "<unavailable>"

    valid = (
        version == str(manifest.get("scanner_version") or "")
        and not missing
        and not changed
        and not extra
        and current_prod_fp == expected_prod_fp
        and current_policy_fp == expected_policy_fp
    )
    return VerificationResult(
        valid=valid,
        scanner_version=version,
        production_fingerprint_expected=expected_prod_fp,
        production_fingerprint_current=current_prod_fp,
        policy_fingerprint_expected=expected_policy_fp,
        policy_fingerprint_current=current_policy_fp,
        changed_files=tuple(changed),
        missing_files=tuple(missing),
        extra_relevant_files=tuple(extra),
    )


def manifest_path(project_root: Path) -> Path:
    return project_root.resolve() / "backend" / "runtime" / "baseline" / BASELINE_FILENAME
