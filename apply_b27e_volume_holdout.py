from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "b27e_payload"
PROJECT = Path.cwd()
FILES = (
    "backend/app/backtest/scanner_quality/entry_stability_volume_holdout.py",
    "backend/tools/run_scanner_entry_stability_volume_holdout.py",
    "backend/tools/audit_inputs/b27e_excluded_dates.json",
    "backend/tests/test_scanner_entry_stability_volume_holdout_v0214b27e.py",
    "WORKSPEC_v0.21.4-B.2.7-E.md",
    "IMPLEMENTATION_v0.21.4-B.2.7-E.md",
    "README_B27E.md",
)
PREREQUISITES = (
    "backend/app/backtest/scanner_quality/entry_stability_audit.py",
    "backend/app/backtest/scanner_quality/entry_stability_validation.py",
)


def main() -> int:
    if not (PROJECT / "backend").exists():
        print("Run this script from the StockScope repository root.")
        return 2
    missing = [rel for rel in PREREQUISITES if not (PROJECT / rel).exists()]
    if missing:
        print("B.2.7-E prerequisite missing. Apply B.2.7-A/B and B.2.7-C first:")
        for rel in missing:
            print(f"  - {rel}")
        return 2
    for rel in FILES:
        src, dst = PAYLOAD / rel, PROJECT / rel
        if not src.exists():
            print(f"overlay payload missing: {rel}")
            return 2
        if dst.exists() and not filecmp.cmp(src, dst, shallow=False):
            print(f"preflight refused overwrite: {rel}")
            return 2
    for rel in FILES:
        src, dst = PAYLOAD / rel, PROJECT / rel
        if dst.exists():
            print(f"unchanged: {rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"added: {rel}")

    env = dict(os.environ)
    backend = str(PROJECT / "backend")
    env["PYTHONPATH"] = backend + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    test = PROJECT / "backend/tests/test_scanner_entry_stability_volume_holdout_v0214b27e.py"
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(test)], cwd=PROJECT, env=env, check=False)
    if result.returncode != 0:
        print("B.2.7-E files were added, but focused tests failed. Do not run the holdout until fixed.")
        return result.returncode
    print("B.2.7-E frozen Volume-Low fresh-holdout tooling applied and focused tests passed.")
    print("Production Scanner/Ranking/Strategy/Risk/Entry/Stop/Target files were not modified.")
    print(r"Run: python backend\tools\run_scanner_entry_stability_volume_holdout.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
