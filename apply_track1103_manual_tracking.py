from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "payload"

UPDATE_FILES = [
    "frontend/src/components/RecommendationTracking.tsx",
    "frontend/src/tracking.css",
    "frontend/tests/test_manual_tracking_completion_track1103.py",
]

EXPECTED_SHA256 = {
    "frontend/src/components/RecommendationTracking.tsx": "59c6eedc83b96c33b4f389ff83aac9d779b913fb68a8d811e6cb21fe932438a9",
    "frontend/src/tracking.css": "a6fa687e064d4e623858797982756deb514f7f4e2d541f397cdb7e9d99888f51",
}


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("RUN ", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def require(path: str) -> Path:
    target = ROOT / path
    if not target.exists():
        raise RuntimeError(f"Required file missing: {path}")
    return target


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"PYTHON      : {sys.executable}")

    require("frontend/src/services/trackingApi.ts")
    require("frontend/src/components/EmbeddedScanner.tsx")
    require("frontend/package.json")
    require("backend/tools/verify_scanner_production_baseline.py")

    for rel, expected in EXPECTED_SHA256.items():
        target = require(rel)
        current = sha256(target)
        if current != expected:
            raise RuntimeError(
                f"TRACK.1.10.2 baseline mismatch: {rel}\n"
                f"expected: {expected}\n"
                f"current : {current}\n"
                "Do not overwrite unknown local changes."
            )

    originals: dict[Path, bytes | None] = {}
    try:
        for rel in UPDATE_FILES:
            src = PAYLOAD / rel
            if not src.exists():
                raise RuntimeError(f"Payload file missing: {rel}")
            dst = ROOT / rel
            originals[dst] = dst.read_bytes() if dst.exists() else None
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            print(f"UPDATE {rel}")

        tests = [
            "backend/tests/test_recommendation_tracking_track1.py",
            "backend/tests/test_tracking_performance_track1.py",
            "backend/tests/test_tracking_integrity_track19.py",
            "backend/tests/test_tracking_usability_track110.py",
            "backend/tests/test_tracking_api_track1.py",
            "frontend/tests/test_tracking_track1_source.py",
            "frontend/tests/test_tracking_performance_source.py",
            "frontend/tests/test_scanner_session_reactive_track19.py",
            "frontend/tests/test_embedded_scanner_track1101.py",
            "frontend/tests/test_scanner_panel_shared_track1101.py",
            "frontend/tests/test_tracking_lifecycle_track1102.py",
            "frontend/tests/test_manual_tracking_completion_track1103.py",
        ]
        run([sys.executable, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider"])

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm was not found in PATH")
        run([npm, "--prefix", "frontend", "run", "build"])

        print("\n[REPORT ONLY] Scanner production baseline")
        baseline = run([sys.executable, "backend/tools/verify_scanner_production_baseline.py"], check=False)
        if baseline.returncode != 0:
            print("WARNING: pre-existing Scanner baseline mismatch remains; TRACK.1.10.3 does not modify Scanner production algorithms.")

    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("ROLLBACK TRACK.1.10.3 changes...")
        for dst, data in reversed(list(originals.items())):
            try:
                if data is None:
                    if dst.exists():
                        dst.unlink()
                else:
                    dst.write_bytes(data)
                print(f"RESTORE {dst.relative_to(ROOT)}")
            except Exception as restore_error:
                print(f"WARNING: failed to restore {dst}: {restore_error}")
        return 1

    print("\nTRACK.1.10.3 applied successfully.")
    print("- Manual search remains usable without running Scanner first.")
    print("- The selected stock shows its confirmed reference date/close before tracking starts.")
    print("- Manual ACTIVE/same-day CLOSED lifecycle states are visible without reloads.")
    print("- Expanded details separate current price from current return and keep Scanner-only fields out of manual records.")
    print("- Row actions now say latest refresh / stop tracking / delete record explicitly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
