from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.baseline.scanner_production_baseline import (
    BaselineError,
    load_manifest,
    manifest_path,
    verify_baseline,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify current Scanner source against the frozen Simulation baseline")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()
    path = args.manifest or manifest_path(args.project_root)
    try:
        manifest = load_manifest(path)
        result = verify_baseline(args.project_root, manifest)
    except BaselineError as exc:
        print(str(exc))
        return 2

    print("Scanner Production Baseline")
    print(f"Version: {result.scanner_version}")
    print(
        "Production fingerprint: "
        + ("MATCH" if result.production_fingerprint_current == result.production_fingerprint_expected else "MISMATCH")
    )
    print(
        "Policy fingerprint: "
        + ("MATCH" if result.policy_fingerprint_current == result.policy_fingerprint_expected else "MISMATCH")
    )
    if result.changed_files:
        print("Modified production files:")
        for item in result.changed_files:
            print(f"- {item['path']}")
            print(f"  expected: {item['expected']}")
            print(f"  current : {item['current']}")
    if result.missing_files:
        print("Missing production files:")
        for path_str in result.missing_files:
            print(f"- {path_str}")
    if result.extra_relevant_files:
        print("New relevant production dependencies:")
        for path_str in result.extra_relevant_files:
            print(f"- {path_str}")
    print(f"Status: {'BASELINE_VALID' if result.valid else 'BASELINE_MISMATCH'}")
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
