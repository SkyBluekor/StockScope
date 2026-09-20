from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ADD_ONLY_FILES = (
    "backend/app/backtest/scanner_quality/candidate_quality_final_confirmation.py",
    "backend/tools/run_scanner_candidate_quality_final_confirmation.py",
    "backend/tests/test_scanner_candidate_quality_final_confirmation_v0214b26e.py",
    "WORKSPEC_v0.21.4-B.2.6-E.md",
    "IMPLEMENTATION_v0.21.4-B.2.6-E.md",
    "README_B26E.md",
)
HOLDOUT_TEMPLATE = "backend/tools/audit_inputs/b26e_holdout_dates.txt"
REQUIRED_EXISTING = (
    "backend/app/backtest/scanner.py",
    "backend/app/backtest/scanner_quality/candidate_quality_validation.py",
    "backend/app/backtest/scanner_quality/overextension_context_audit.py",
    "backend/tools/audit_inputs/b26_candidate_quality_baseline_75d.json",
)
PROTECTED_PRODUCTION = (
    "backend/app/backtest/scanner.py",
    "backend/app/backtest/candidate_priority.py",
    "backend/app/strategy/engine.py",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parent
    payload = root / "b26e_payload"
    if not payload.exists():
        raise SystemExit(f"B.2.6-E payload not found: {payload}")

    missing = [rel for rel in REQUIRED_EXISTING if not (root / rel).exists()]
    if missing:
        raise SystemExit(
            "B.2.6-E preflight failed. Required B.2.6-C/D files are missing. No files changed.\n"
            + "\n".join(missing)
        )

    scanner_text = (root / "backend/app/backtest/scanner.py").read_text(encoding="utf-8-sig", errors="replace")
    if 'VERSION = "0.21.3.7"' not in scanner_text and "VERSION = '0.21.3.7'" not in scanner_text:
        raise SystemExit("B.2.6-E preflight failed: scanner.py is not VERSION 0.21.3.7. No files changed.")

    protected_before = {
        rel: sha256(root / rel)
        for rel in PROTECTED_PRODUCTION
        if (root / rel).exists()
    }

    conflicts: list[str] = []
    copies: list[tuple[Path, Path]] = []
    for rel in ADD_ONLY_FILES:
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

    template_src = payload / HOLDOUT_TEMPLATE
    template_dst = root / HOLDOUT_TEMPLATE
    if not template_src.exists():
        conflicts.append(f"missing payload: {HOLDOUT_TEMPLATE}")
    elif not template_dst.exists():
        copies.append((template_src, template_dst))
    else:
        print(f"preserved existing frozen holdout file: {HOLDOUT_TEMPLATE}")

    if conflicts:
        raise SystemExit("B.2.6-E preflight failed. No files changed.\n" + "\n".join(conflicts))

    for src, dst in copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"added: {dst.relative_to(root)}")

    env = dict(os.environ)
    backend = str(root / "backend")
    env["PYTHONPATH"] = backend + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    test = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "backend/tests/test_scanner_candidate_quality_final_confirmation_v0214b26e.py",
        ],
        cwd=root,
        env=env,
        check=False,
    )
    if test.returncode != 0:
        raise SystemExit(test.returncode)

    protected_after = {
        rel: sha256(root / rel)
        for rel in protected_before
    }
    changed = [rel for rel, before in protected_before.items() if protected_after.get(rel) != before]
    if changed:
        raise SystemExit(
            "B.2.6-E safety check failed: protected Production file changed unexpectedly:\n"
            + "\n".join(changed)
        )

    print("B.2.6-E frozen-rule final confirmation tooling applied and focused tests passed.")
    print("Protected Production files remained byte-identical.")
    print(r"Run: python backend\tools\run_scanner_candidate_quality_final_confirmation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
