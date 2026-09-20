from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

FILES = (
    "backend/app/backtest/scanner_quality/candidate_quality_audit.py",
    "backend/tools/run_scanner_candidate_quality_audit.py",
    "backend/tests/test_scanner_candidate_quality_audit_v0214b26.py",
    "backend/tools/audit_inputs/b26_candidate_quality_baseline_75d.json",
    "backend/tools/audit_inputs/b26_target1_cap_validation_20d.json",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parent
    payload = root / "b26_payload"
    if not payload.exists():
        raise SystemExit(f"B.2.6 payload not found: {payload}")

    conflicts: list[str] = []
    copies: list[tuple[Path, Path]] = []
    for rel in FILES:
        src = payload / rel
        dst = root / rel
        if not src.exists():
            conflicts.append(f"missing payload: {rel}")
            continue
        if dst.exists():
            if sha256(src) == sha256(dst):
                continue
            conflicts.append(f"existing file differs; refusing to overwrite: {rel}")
            continue
        copies.append((src, dst))

    if conflicts:
        raise SystemExit("B.2.6-A/B preflight failed. No files changed.\n" + "\n".join(conflicts))

    for src, dst in copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"added: {dst.relative_to(root)}")

    env = dict(os.environ)
    backend = str(root / "backend")
    env["PYTHONPATH"] = backend + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    test = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "backend/tests/test_scanner_candidate_quality_audit_v0214b26.py"],
        cwd=root,
        env=env,
        check=False,
    )
    if test.returncode != 0:
        raise SystemExit(test.returncode)

    print("B.2.6-A/B audit tooling applied and focused tests passed.")
    print("Production Scanner/Ranking/Risk/Target files were not modified.")
    print(r"Run: python backend\tools\run_scanner_candidate_quality_audit.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
