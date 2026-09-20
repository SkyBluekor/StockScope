from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

FILES = (
    "backend/app/backtest/scanner_quality/overextension_context_audit.py",
    "backend/tools/run_scanner_overextension_context_audit.py",
    "backend/tests/test_scanner_overextension_context_audit_v0214b26d.py",
    "WORKSPEC_v0.21.4-B.2.6-D.md",
    "IMPLEMENTATION_v0.21.4-B.2.6-D.md",
    "README_B26D.md",
)

REQUIRED_EXISTING = (
    "backend/app/backtest/scanner.py",
    "backend/app/backtest/scanner_quality/candidate_quality_validation.py",
    "backend/tools/audit_inputs/b26_candidate_quality_baseline_75d.json",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parent
    payload = root / "b26d_payload"
    if not payload.exists():
        raise SystemExit(f"B.2.6-D payload not found: {payload}")

    missing = [rel for rel in REQUIRED_EXISTING if not (root / rel).exists()]
    if missing:
        raise SystemExit(
            "B.2.6-D preflight failed. Required B.2.6-A/B/C files are missing. No files changed.\n"
            + "\n".join(missing)
        )

    scanner_text = (root / "backend/app/backtest/scanner.py").read_text(encoding="utf-8-sig", errors="replace")
    if 'VERSION = "0.21.3.7"' not in scanner_text and "VERSION = '0.21.3.7'" not in scanner_text:
        raise SystemExit(
            "B.2.6-D preflight failed: scanner.py is not VERSION 0.21.3.7. "
            "No files changed."
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
        raise SystemExit("B.2.6-D preflight failed. No files changed.\n" + "\n".join(conflicts))

    for src, dst in copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"added: {dst.relative_to(root)}")

    env = dict(os.environ)
    backend = str(root / "backend")
    env["PYTHONPATH"] = backend + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    test = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "backend/tests/test_scanner_overextension_context_audit_v0214b26d.py"],
        cwd=root,
        env=env,
        check=False,
    )
    if test.returncode != 0:
        raise SystemExit(test.returncode)

    print("B.2.6-D overextension context audit tooling applied and focused tests passed.")
    print("Production Scanner/Ranking/Strategy/Risk/Entry/Target files were not modified.")
    print(r"Run: python backend\tools\run_scanner_overextension_context_audit.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
