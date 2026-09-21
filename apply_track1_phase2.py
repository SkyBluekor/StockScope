from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "track1_phase2_payload"

COPY_FILES = [
    "backend/app/tracking/models.py",
    "backend/app/tracking/performance.py",
    "backend/app/tracking/store.py",
    "backend/app/tracking/service.py",
    "backend/app/tracking/api.py",
    "backend/app/api/simulation.py",
    "backend/tests/test_tracking_performance_track1.py",
    "backend/tests/test_tracking_api_track1.py",
    "frontend/src/services/trackingApi.ts",
    "frontend/src/components/RecommendationTracking.tsx",
    "frontend/src/components/SimulationWorkspace.tsx",
    "frontend/src/tracking.css",
    "frontend/tests/test_tracking_performance_source.py",
    "frontend/tests/test_tracking_track1_source.py",
]


def run(cmd: list[str], *, check: bool = True):
    print("RUN ", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def require(rel: str) -> Path:
    path = ROOT / rel
    if not path.exists():
        raise RuntimeError(f"Required file missing: {rel}")
    return path


def verify_phase1() -> None:
    tracking = require("frontend/src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    store = require("backend/app/tracking/store.py").read_text(encoding="utf-8")
    if "추천 추적" not in tracking or "tracked_recommendation" not in store:
        raise RuntimeError("TRACK.1 Phase 1 was not detected. Apply TRACK.1 Phase 1 first.")


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"PYTHON      : {sys.executable}")

    verify_phase1()
    require("backend/app/simulation/sim3_market_provider.py")
    require("backend/tests/test_recommendation_tracking_track1.py")
    require("backend/tests/test_simulation_ui1_api_integration.py")
    require("frontend/tests/test_simulation_ui1_source.py")
    require("frontend/package.json")

    originals: dict[Path, bytes | None] = {}
    try:
        for rel in COPY_FILES:
            src = PAYLOAD / rel
            if not src.exists():
                raise RuntimeError(f"Payload file missing: {rel}")
            dst = ROOT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            originals[dst] = dst.read_bytes() if dst.exists() else None
            dst.write_bytes(src.read_bytes())
            print(f"UPDATE {rel}")

        py = sys.executable
        run([
            py, "-m", "py_compile",
            "backend/app/tracking/models.py",
            "backend/app/tracking/performance.py",
            "backend/app/tracking/store.py",
            "backend/app/tracking/service.py",
            "backend/app/tracking/api.py",
            "backend/app/api/simulation.py",
        ])

        run([
            py, "-m", "pytest",
            "backend/tests/test_recommendation_tracking_track1.py",
            "backend/tests/test_tracking_performance_track1.py",
            "backend/tests/test_tracking_api_track1.py",
            "backend/tests/test_simulation_ui1_api_integration.py",
            "frontend/tests/test_tracking_track1_source.py",
            "frontend/tests/test_tracking_performance_source.py",
            "frontend/tests/test_simulation_ui1_source.py",
            "-q", "-p", "no:cacheprovider",
        ])

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm was not found on PATH")
        run([npm, "--prefix", "frontend", "run", "build"])

        verifier = ROOT / "backend/tools/verify_scanner_production_baseline.py"
        if verifier.exists():
            print("\n[REPORT ONLY] Scanner production baseline")
            result = run([py, str(verifier.relative_to(ROOT))], check=False)
            if result.returncode != 0:
                print(
                    "WARNING: pre-existing Scanner baseline mismatch remains; "
                    "TRACK.1 Phase 2 does not modify Scanner production files."
                )

        print("\nTRACK.1 Phase 2 applied successfully.")
        print("Recommendation performance now tracks D+1+ closes, max rise/fall, 5D/10D/20D, and Entry/Stop/Target touches.")
        return 0

    except Exception:
        for path, data in reversed(list(originals.items())):
            if data is None:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            else:
                path.write_bytes(data)
        print("TRACK.1 Phase 2 apply failed; changed files were rolled back.", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
