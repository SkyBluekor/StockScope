from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "payload"

UPDATE_FILES = [
    "frontend/src/components/RecommendationTracking.tsx",
    "frontend/src/tracking.css",
    "frontend/tests/test_tracking_lifecycle_track1102.py",
]


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("RUN ", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def require(path: str) -> Path:
    target = ROOT / path
    if not target.exists():
        raise RuntimeError(f"Required file missing: {path}")
    return target


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"PYTHON      : {sys.executable}")

    tracking = require("frontend/src/components/RecommendationTracking.tsx")
    css = require("frontend/src/tracking.css")
    api = require("frontend/src/services/trackingApi.ts")
    require("frontend/src/components/EmbeddedScanner.tsx")
    require("frontend/src/components/scannerSession.ts")
    require("frontend/package.json")
    require("backend/tools/verify_scanner_production_baseline.py")

    current_tracking = tracking.read_text(encoding="utf-8")
    current_css = css.read_text(encoding="utf-8")
    current_api = api.read_text(encoding="utf-8")
    if 'import EmbeddedScanner from "./EmbeddedScanner"' not in current_tracking or "<EmbeddedScanner />" not in current_tracking:
        raise RuntimeError("TRACK.1.10.1 Embedded Scanner baseline was not detected. Apply TRACK.1.10.1 first.")
    if "TRACK.1.10.1" not in current_css:
        raise RuntimeError("TRACK.1.10.1 tracking CSS baseline was not detected.")
    if "deleteTrackedRecommendation" not in current_api or 'method: "DELETE"' not in current_api:
        raise RuntimeError("TRACK.1.10 tracking lifecycle API baseline was not detected.")

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
        ]
        run([sys.executable, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider"])

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm was not found in PATH")
        run([npm, "--prefix", "frontend", "run", "build"])

        print("\n[REPORT ONLY] Scanner production baseline")
        baseline = run([sys.executable, "backend/tools/verify_scanner_production_baseline.py"], check=False)
        if baseline.returncode != 0:
            print("WARNING: pre-existing Scanner baseline mismatch remains; TRACK.1.10.2 does not modify Scanner production algorithms.")

    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("ROLLBACK TRACK.1.10.2 changes...")
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

    print("\nTRACK.1.10.2 applied successfully.")
    print("- Tracking additions immediately update the saved-record list and active count.")
    print("- Candidate buttons distinguish active tracking from already-closed recommendation records.")
    print("- Filters show counts and active records sort before closed history.")
    print("- Close/delete confirmations protect frozen evidence; Scanner deletion warns about analysis evidence loss.")
    print("- Waiting records explain D+1 performance timing and refresh reports when no new confirmed day exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
