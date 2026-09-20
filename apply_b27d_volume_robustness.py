from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "b27d_payload"
PROJECT = Path.cwd()
FILES = (
    "backend/app/backtest/scanner_quality/entry_stability_volume_robustness.py",
    "backend/tools/run_scanner_entry_stability_volume_robustness.py",
    "backend/tests/test_scanner_entry_stability_volume_robustness_v0214b27d.py",
    "WORKSPEC_v0.21.4-B.2.7-D.md",
    "IMPLEMENTATION_v0.21.4-B.2.7-D.md",
    "README_B27D.md",
)


def main() -> int:
    if not (PROJECT / "backend").exists():
        print("Run this script from the StockScope repository root.")
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
    test = PROJECT / "backend/tests/test_scanner_entry_stability_volume_robustness_v0214b27d.py"
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(test)], cwd=PROJECT, env=env, check=False)
    if result.returncode != 0:
        print("B.2.7-D files were added, but focused tests failed. Do not run the audit until fixed.")
        return result.returncode
    print("B.2.7-D Volume robustness tooling applied and focused tests passed.")
    print("Production Scanner/Ranking/Strategy/Risk/Entry/Stop/Target files were not modified.")
    print("Run: python backend\\tools\\run_scanner_entry_stability_volume_robustness.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
