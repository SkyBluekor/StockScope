from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

FILES = (
    "backend/app/backtest/scanner_quality/candidate_quality_validation.py",
    "backend/tools/run_scanner_candidate_quality_validation.py",
    "backend/tests/test_scanner_candidate_quality_validation_v0214b26c.py",
    "backend/tools/audit_inputs/b26c_validation_dates.txt",
)

REQUIRED_EXISTING = (
    "backend/app/backtest/scanner.py",
    "backend/app/backtest/candidate_priority.py",
    "backend/app/backtest/scanner_quality/early_pruning_audit.py",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parent
    payload = root / "b26c_payload"
    if not payload.exists():
        raise SystemExit(f"B.2.6-C payload not found: {payload}")

    missing_dependencies = [rel for rel in REQUIRED_EXISTING if not (root / rel).exists()]
    if missing_dependencies:
        raise SystemExit(
            "B.2.6-C preflight failed. Required current project files are missing. No files changed.\n"
            + "\n".join(missing_dependencies)
        )

    scanner_text = (root / "backend/app/backtest/scanner.py").read_text(encoding="utf-8-sig", errors="replace")
    if 'VERSION = "0.21.3.7"' not in scanner_text and "VERSION = '0.21.3.7'" not in scanner_text:
        raise SystemExit(
            "B.2.6-C preflight failed: scanner.py is not VERSION 0.21.3.7. "
            "Do not force apply; current-version validation requires the exact current Scanner."
        )

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
        raise SystemExit("B.2.6-C preflight failed. No files changed.\n" + "\n".join(conflicts))

    for src, dst in copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"added: {dst.relative_to(root)}")

    env = dict(os.environ)
    backend = str(root / "backend")
    env["PYTHONPATH"] = backend + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    test = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "backend/tests/test_scanner_candidate_quality_validation_v0214b26c.py"],
        cwd=root,
        env=env,
        check=False,
    )
    if test.returncode != 0:
        raise SystemExit(test.returncode)

    print("B.2.6-C current-version validation tooling applied and focused tests passed.")
    print("Production Scanner/Ranking/Strategy/Risk/Entry/Target files were not modified.")
    print(r"Run: python backend\tools\run_scanner_candidate_quality_validation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
