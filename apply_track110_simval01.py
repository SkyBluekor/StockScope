from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "payload"

COPY_FILES = [
    "backend/app/tracking/store.py",
    "backend/app/tracking/service.py",
    "backend/app/tracking/api.py",
    "backend/app/simulation/validation_catalog.py",
    "backend/app/api/simulation.py",
    "backend/tests/test_tracking_api_track1.py",
    "backend/tests/test_tracking_usability_track110.py",
    "backend/tests/test_simulation_validation_catalog_simval01.py",
    "frontend/src/services/trackingApi.ts",
    "frontend/src/services/simulationApi.ts",
    "frontend/src/components/RecommendationTracking.tsx",
    "frontend/src/components/SimulationWorkspace.tsx",
    "frontend/src/tracking.css",
    "frontend/src/simulation.css",
    "frontend/tests/test_tracking_track1_source.py",
    "frontend/tests/test_simulation_ui1_source.py",
]


def run(cmd: list[str], *, check: bool = True):
    print("RUN ", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def require(rel: str) -> Path:
    path = ROOT / rel
    if not path.exists():
        raise RuntimeError(f"Required file missing: {rel}")
    return path


def verify_previous_phase() -> None:
    tracking = require("frontend/src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    session = require("frontend/src/components/scannerSession.ts").read_text(encoding="utf-8")
    sim = require("frontend/src/components/SimulationWorkspace.tsx").read_text(encoding="utf-8")
    backend = require("backend/app/tracking/store.py").read_text(encoding="utf-8")
    if "useScannerSession" not in tracking or "SCANNER_SESSION_SCHEMA_VERSION" not in session:
        raise RuntimeError("TRACK.1.9 reactive Scanner session was not detected. Apply TRACK.1.9/SIM.VAL.0 first.")
    if "검증 실행 · 준비 중" not in sim or "validation-periods/preview" not in require("frontend/src/services/simulationApi.ts").read_text(encoding="utf-8"):
        raise RuntimeError("SIM.VAL.0 validation foundation was not detected. Apply TRACK.1.9/SIM.VAL.0 first.")
    if "snapshot_hash" not in backend or "closed_market_date" not in backend:
        raise RuntimeError("TRACK.1.9 tracking integrity schema was not detected.")
    require("backend/app/simulation/validation_period.py")
    require("frontend/src/services/api.ts")


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"PYTHON      : {sys.executable}")
    verify_previous_phase()
    require("frontend/package.json")
    require("backend/app/simulation/sim3_market_provider.py")
    require("backend/tests/test_recommendation_tracking_track1.py")
    require("backend/tests/test_tracking_performance_track1.py")
    require("backend/tests/test_tracking_integrity_track19.py")
    require("backend/tests/test_simulation_validation_period_simval0.py")
    require("backend/tests/test_simulation_ui1_api_integration.py")
    require("frontend/tests/test_tracking_performance_source.py")
    require("frontend/tests/test_scanner_session_reactive_track19.py")

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
            "backend/app/tracking/store.py",
            "backend/app/tracking/service.py",
            "backend/app/tracking/api.py",
            "backend/app/simulation/validation_catalog.py",
            "backend/app/api/simulation.py",
        ])

        run([
            py, "-m", "pytest",
            "backend/tests/test_recommendation_tracking_track1.py",
            "backend/tests/test_tracking_performance_track1.py",
            "backend/tests/test_tracking_integrity_track19.py",
            "backend/tests/test_tracking_usability_track110.py",
            "backend/tests/test_tracking_api_track1.py",
            "backend/tests/test_simulation_validation_period_simval0.py",
            "backend/tests/test_simulation_validation_catalog_simval01.py",
            "backend/tests/test_simulation_ui1_api_integration.py",
            "frontend/tests/test_tracking_track1_source.py",
            "frontend/tests/test_tracking_performance_source.py",
            "frontend/tests/test_simulation_ui1_source.py",
            "frontend/tests/test_scanner_session_reactive_track19.py",
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
                    "TRACK.1.10/SIM.VAL.0.1 does not modify Scanner production algorithms."
                )

        print("\nTRACK.1.10 + SIM.VAL.0.1 applied successfully.")
        print("- Stock Tracking now has always-visible independent stock search, Scanner candidates, and tracked records.")
        print("- Scanner candidate UI no longer truncates results; the actual Scanner result count is shown.")
        print("- Closed tracking records can be explicitly deleted; active records must be closed first.")
        print("- Historical Validation settings can be saved as DRAFT records with target/market/period metadata.")
        print("- Saved validations can be opened and deleted; legacy Simulation records remain separate and safe-delete guarded.")
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
        print("TRACK.1.10 + SIM.VAL.0.1 apply failed; changed files were rolled back.", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
