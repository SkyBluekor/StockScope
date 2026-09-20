from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "b27c_payload"
PROJECT = Path.cwd()

FILES = (
    "backend/app/backtest/scanner_quality/entry_stability_validation.py",
    "backend/tools/run_scanner_entry_stability_validation.py",
    "backend/tests/test_scanner_entry_stability_validation_v0214b27c.py",
    "backend/tools/audit_inputs/b27c_validation_dates.txt",
)
DEPENDENCY = PROJECT / "backend/app/backtest/scanner_quality/entry_stability_audit.py"


def main() -> int:
    if not (PROJECT / "backend").exists():
        print("Run this script from the StockScope repository root.")
        return 2
    if not DEPENDENCY.exists():
        print("B.2.7-C prerequisite missing: backend/app/backtest/scanner_quality/entry_stability_audit.py")
        print("Apply B.2.7-A/B first, then retry.")
        return 2

    for rel in FILES:
        src = PAYLOAD / rel
        dst = PROJECT / rel
        if not src.exists():
            print(f"overlay payload missing: {rel}")
            return 2
        if dst.exists() and not filecmp.cmp(src, dst, shallow=False):
            print(f"preflight refused overwrite: {rel}")
            return 2

    for rel in FILES:
        src = PAYLOAD / rel
        dst = PROJECT / rel
        if dst.exists():
            print(f"unchanged: {rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"added: {rel}")

    test = PROJECT / "backend/tests/test_scanner_entry_stability_validation_v0214b27c.py"
    env = dict(os.environ)
    backend = str(PROJECT / "backend")
    env["PYTHONPATH"] = backend + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test)],
        cwd=PROJECT,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        print("B.2.7-C files were added, but focused tests failed. Do not run the audit until fixed.")
        return result.returncode

    print("B.2.7-C current-version Entry Stability validation tooling applied and focused tests passed.")
    print("Production Scanner/Ranking/Strategy/Risk/Entry/Stop/Target files were not modified.")
    print("Run: python backend\\tools\\run_scanner_entry_stability_validation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
