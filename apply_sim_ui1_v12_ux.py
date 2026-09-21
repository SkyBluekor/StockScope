from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "sim_ui1_v12_payload"

UPDATE_FILES = [
    "backend/app/api/simulation.py",
    "backend/tests/test_simulation_ui1_api_integration.py",
    "frontend/src/services/simulationApi.ts",
    "frontend/src/components/SimulationWorkspace.tsx",
    "frontend/src/simulation.css",
    "frontend/tests/test_simulation_ui1_source.py",
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
    # Run from the StockScope project root.
    # ROOT follows the current working directory, so this works on:
    #   D:\Projects\StockScope
    # as well as other machines without hard-coded paths.
    print(f"PROJECT ROOT: {ROOT}")
    print(f"PYTHON      : {sys.executable}")

    workspace = require("frontend/src/components/SimulationWorkspace.tsx")
    require("frontend/src/services/simulationApi.ts")
    require("frontend/src/components/scannerSession.ts")
    require("frontend/src/services/api.ts")
    require("frontend/src/simulation.css")
    require("backend/app/api/simulation.py")
    require("backend/tools/verify_scanner_production_baseline.py")
    require("frontend/package.json")

    current_workspace = workspace.read_text(encoding="utf-8")
    if "SimulationWorkspace" not in current_workspace or "buySimulationPosition" not in current_workspace:
        raise RuntimeError("SIM.UI.1 workspace was not detected. Apply SIM.UI.1 v1.1 first.")

    env_python = sys.executable

    # Baseline verification is informative for this UI hotfix.
    # v1.2 does not modify Scanner production files, so an already-existing
    # baseline mismatch must not roll back an otherwise valid UI/API patch.
    print("\n[PRECHECK] Scanner production baseline")
    baseline = run(
        [env_python, "backend/tools/verify_scanner_production_baseline.py"],
        check=False,
    )
    baseline_mismatch = baseline.returncode != 0
    if baseline_mismatch:
        print(
            "WARNING: Scanner production baseline is already mismatched in this checkout.\n"
            "SIM.UI.1 v1.2 does not modify Scanner production files, so the patch will continue.\n"
            "The baseline mismatch must be handled separately."
        )

    originals: dict[Path, bytes] = {}

    try:
        for rel in UPDATE_FILES:
            src = PAYLOAD / rel
            dst = require(rel)

            if not src.exists():
                raise RuntimeError(f"Payload file missing: {rel}")

            originals[dst] = dst.read_bytes()
            dst.write_bytes(src.read_bytes())
            print(f"UPDATE {rel}")

        run([env_python, "-m", "py_compile", "backend/app/api/simulation.py"])

        tests = [
            "backend/tests/test_scanner_production_baseline_sim0.py",
            "backend/tests/test_simulation_domain_sim1.py",
            "backend/tests/test_simulation_trading_sim2.py",
            "backend/tests/test_simulation_playback_sim3.py",
            "backend/tests/test_simulation_ui1_api_integration.py",
            "frontend/tests/test_simulation_ui1_source.py",
        ]
        run([env_python, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider"])

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm was not found on PATH")

        run([npm, "--prefix", "frontend", "run", "build"])

        # Run again only as a report. It must not roll back this UI-only patch.
        print("\n[POSTCHECK] Scanner production baseline")
        baseline_after = run(
            [env_python, "backend/tools/verify_scanner_production_baseline.py"],
            check=False,
        )

        if baseline_after.returncode != 0:
            print(
                "WARNING: Scanner production baseline remains mismatched.\n"
                "This did not block SIM.UI.1 v1.2 because this patch does not modify Scanner production files."
            )
        else:
            print("Scanner production baseline: VALID")

        print("\nSIM.UI.1 v1.2 UX hotfix applied.")
        print("Focused regression tests + frontend build passed.")
        print(
            "Stock identity is selection-based, Scanner recommendations are date-aligned, "
            "and simulation-day close is auto-filled from the local Market Store."
        )
        return 0

    except Exception:
        for path, data in originals.items():
            path.write_bytes(data)

        print(
            "SIM.UI.1 v1.2 apply failed; updated files were rolled back.",
            file=sys.stderr,
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
