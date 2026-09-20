from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.baseline.scanner_production_baseline import BaselineError, freeze_baseline


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze StockScope Scanner Production baseline for Simulation")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    try:
        path, manifest = freeze_baseline(args.project_root)
    except BaselineError as exc:
        print(str(exc))
        return 2

    git = manifest.get("git") or {}
    scope = manifest.get("production_scope") or {}
    print("Scanner Production Baseline Freeze")
    print(f"Scanner: {manifest.get('scanner_version')}")
    print(f"Production files: {scope.get('file_count')}")
    print(f"Git: {git.get('head') or '<unavailable>'}")
    print(f"Branch: {git.get('branch') or '<detached/unavailable>'}")
    dirty = git.get("working_tree_dirty")
    print(f"Working tree: {'DIRTY' if dirty else ('CLEAN' if dirty is False else 'UNKNOWN')}")
    print(f"Production fingerprint: {manifest.get('production_fingerprint')}")
    print(f"Policy fingerprint: {manifest.get('policy_fingerprint')}")
    print(f"Baseline: {manifest.get('baseline_id')}")
    print("Production changed: False")
    print("Result: BASELINE_FROZEN")
    print(f"Manifest: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
