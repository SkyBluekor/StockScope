from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
PROJECT = Path.cwd()
TARGET_REL = Path("backend/app/backtest/scanner_quality/entry_stability_volume_holdout.py")
TEST_REL = Path("backend/tests/test_scanner_entry_stability_volume_holdout_v0214b27e1.py")
OLD_SHA256 = "3038dbd6aebbc02159048b8fa6716364480f8b4d04d9ee4614edd3b5694936ae"
NEW_SHA256 = "2461ec06dce17031d0525d6962c9217018d995d1861045f4be38065c3d852205"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not (PROJECT / "backend").exists():
        print("Run this script from the StockScope repository root.")
        return 2

    src = PAYLOAD / TARGET_REL
    dst = PROJECT / TARGET_REL
    test_src = PAYLOAD / TEST_REL
    test_dst = PROJECT / TEST_REL
    if not src.exists() or not test_src.exists():
        print("hotfix payload is incomplete")
        return 2
    if not dst.exists():
        print("B.2.7-E module is missing. Apply B.2.7-E first.")
        return 2

    current_hash = sha256(dst)
    if current_hash not in {OLD_SHA256, NEW_SHA256}:
        print("preflight refused overwrite: B.2.7-E module differs from the known E/E.1 versions")
        print(f"current sha256: {current_hash}")
        return 2

    if current_hash == NEW_SHA256:
        print(f"unchanged: {TARGET_REL}")
    else:
        shutil.copy2(src, dst)
        print(f"patched: {TARGET_REL}")

    if test_dst.exists():
        if sha256(test_dst) != sha256(test_src):
            print(f"preflight refused overwrite: {TEST_REL}")
            return 2
        print(f"unchanged: {TEST_REL}")
    else:
        test_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(test_src, test_dst)
        print(f"added: {TEST_REL}")

    env = dict(os.environ)
    backend = str(PROJECT / "backend")
    env["PYTHONPATH"] = backend + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    tests = [
        PROJECT / "backend/tests/test_scanner_entry_stability_volume_holdout_v0214b27e.py",
        test_dst,
    ]
    args = [sys.executable, "-m", "pytest", "-q"] + [str(path) for path in tests if path.exists()]
    result = subprocess.run(args, cwd=PROJECT, env=env, check=False)
    if result.returncode != 0:
        print("E.1 CSV hotfix applied, but focused tests failed. Do not rerun holdout until fixed.")
        return result.returncode

    print("B.2.7-E.1 output/READY-scope hotfix applied; focused tests passed.")
    print("Holdout selection, ranking rule, Scanner, Strategy, Risk, Entry, Stop and Target logic were not changed.")
    print(r"Rerun: python backend\tools\run_scanner_entry_stability_volume_holdout.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
