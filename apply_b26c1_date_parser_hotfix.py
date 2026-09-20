from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

OLD_RUNNER_HASH = "c2c068dc5986c4e7129885892a7c6201e86d1f8b5399cd5c2ecfb619dd8ee17f"
NEW_RUNNER_HASH = "9081189ae93ca6a6cd233f93dfc5afc1ea786519cea0ad126befd76197a41028"
RUNNER = Path("backend/tools/run_scanner_candidate_quality_validation.py")
TEST = Path("backend/tests/test_scanner_candidate_quality_validation_dates_v0214b26c1.py")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parent
    payload = root / "b26c1_payload"
    src_runner = payload / RUNNER
    src_test = payload / TEST
    dst_runner = root / RUNNER
    dst_test = root / TEST

    if not src_runner.exists() or not src_test.exists():
        raise SystemExit("B.2.6-C.1 payload is incomplete. No files changed.")
    if not dst_runner.exists():
        raise SystemExit("B.2.6-C.1 requires B.2.6-C to be applied first. No files changed.")

    current = sha256(dst_runner)
    if current == NEW_RUNNER_HASH:
        print("runner already patched: backend/tools/run_scanner_candidate_quality_validation.py")
    elif current == OLD_RUNNER_HASH:
        shutil.copy2(src_runner, dst_runner)
        print("updated: backend/tools/run_scanner_candidate_quality_validation.py")
    else:
        raise SystemExit(
            "B.2.6-C.1 preflight failed: current runner differs from the expected B.2.6-C file. "
            "No files changed."
        )

    if dst_test.exists() and sha256(dst_test) != sha256(src_test):
        raise SystemExit("B.2.6-C.1 preflight failed: date-parser regression test already exists but differs.")
    if not dst_test.exists():
        dst_test.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_test, dst_test)
        print("added: backend/tests/test_scanner_candidate_quality_validation_dates_v0214b26c1.py")

    env = dict(os.environ)
    backend = str(root / "backend")
    env["PYTHONPATH"] = backend + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "backend/tests/test_scanner_candidate_quality_validation_v0214b26c.py",
            "backend/tests/test_scanner_candidate_quality_validation_dates_v0214b26c1.py",
        ],
        cwd=root,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    print("B.2.6-C.1 date parser hotfix applied and focused tests passed.")
    print("Production Scanner/Ranking/Strategy/Risk/Entry/Target files were not modified.")
    print(r"Run: python backend\tools\run_scanner_candidate_quality_validation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
