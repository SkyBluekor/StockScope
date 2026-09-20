from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
PAYLOAD_ROOT = PROJECT_ROOT / "b25d_payload"

FILES = (
    "backend/app/backtest/scanner_quality/no_trade_audit.py",
    "backend/tools/run_scanner_no_trade_audit.py",
    "backend/tests/test_scanner_no_trade_audit_v0214b25d.py",
)


def main() -> int:
    if not PAYLOAD_ROOT.exists():
        print(f"B.2.5-D payload를 찾지 못했습니다: {PAYLOAD_ROOT}")
        return 2

    for relative in FILES:
        source = PAYLOAD_ROOT / relative
        target = PROJECT_ROOT / relative
        if not source.exists():
            print(f"payload 파일이 없습니다: {source}")
            return 2
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"updated: {relative}")

    test_path = PROJECT_ROOT / "backend/tests/test_scanner_no_trade_audit_v0214b25d.py"
    env = dict(os.environ)
    backend_path = str(BACKEND_ROOT)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = backend_path if not existing_pythonpath else backend_path + os.pathsep + existing_pythonpath
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_path)],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        print("B.2.5-D focused tests failed.")
        return result.returncode

    print("B.2.5-D audit tooling applied and focused tests passed.")
    print("Run: python backend\\tools\\run_scanner_no_trade_audit.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
