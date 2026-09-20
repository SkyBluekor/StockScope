from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

EXPECTED_HASH = "32e2c3176c494cb9dd151d1974d21d3bd6b2fc6a3b6693bbcfe7aad7bc679fb8"
NEW_HASH = "7789fdc81871163df6d939301035dd9a9da92363d9bcf7938fb187f19261ff2d"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    target = root / "backend/app/backtest/scanner_quality/decision_quality_audit.py"
    source = root / "b25c2_payload/backend/app/backtest/scanner_quality/decision_quality_audit.py"
    test_target = root / "backend/tests/test_decision_quality_audit_v0214b25c2.py"
    test_source = root / "b25c2_payload/backend/tests/test_decision_quality_audit_v0214b25c2.py"

    if not target.exists() or not source.exists():
        print("B.2.5-C.2 apply failed: required files not found.", file=sys.stderr)
        return 2

    current = sha256(target)
    if current == NEW_HASH:
        print("B.2.5-C.2 audit guard already applied.")
    elif current != EXPECTED_HASH:
        print("B.2.5-C.2 apply aborted: decision_quality_audit.py differs from the expected B.2.5-C file.", file=sys.stderr)
        print(f"current sha256: {current}", file=sys.stderr)
        print("No production/scanner file was changed.", file=sys.stderr)
        return 3
    else:
        shutil.copy2(source, target)
        print("updated: backend/app/backtest/scanner_quality/decision_quality_audit.py")

    shutil.copy2(test_source, test_target)
    print("updated: backend/tests/test_decision_quality_audit_v0214b25c2.py")

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/test_decision_quality_audit_v0214b25c2.py", "-q"],
        cwd=root,
    )
    if proc.returncode != 0:
        return proc.returncode
    print("B.2.5-C.2 stale-source guard applied and focused tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
