from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "track1_payload"
COPY_FILES = [
    "backend/app/tracking/__init__.py",
    "backend/app/tracking/models.py",
    "backend/app/tracking/store.py",
    "backend/app/tracking/service.py",
    "backend/app/tracking/api.py",
    "backend/app/api/simulation.py",
    "backend/tests/test_recommendation_tracking_track1.py",
    "frontend/src/services/trackingApi.ts",
    "frontend/src/components/RecommendationTracking.tsx",
    "frontend/src/components/TrackingWorkspace.tsx",
    "frontend/src/components/SimulationWorkspace.tsx",
    "frontend/src/tracking.css",
    "frontend/tests/test_tracking_track1_source.py",
    "frontend/tests/test_simulation_ui1_source.py",
]


def run(cmd: list[str], *, check: bool = True):
    print("RUN ", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def require(rel: str) -> Path:
    p = ROOT / rel
    if not p.exists():
        raise RuntimeError(f"Required file missing: {rel}")
    return p


def patch_app(text: str) -> str:
    original = text
    # Current SIM.UI.1 imports and renders SimulationWorkspace from App.tsx.
    text, import_count = re.subn(
        r'import\s+SimulationWorkspace\s+from\s+(["\'])\./components/SimulationWorkspace\1\s*;',
        'import TrackingWorkspace from "./components/TrackingWorkspace";',
        text,
        count=1,
    )
    text, render_count = re.subn(r'<SimulationWorkspace\s*/>', '<TrackingWorkspace />', text, count=1)
    # Sidebar/topnav label only; do not global-replace simulation terminology.
    label_patterns = [
        (r'(>\s*)시뮬레이션(\s*(?:<em>.*?</em>\s*)?<)', r'\1추천 추적\2'),
        (r'(["\'])시뮬레이션\1', '"추천 추적"'),
    ]
    label_count = 0
    for pattern, replacement in label_patterns:
        text, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
        label_count += count
        if count:
            break
    if import_count != 1 or render_count != 1:
        raise RuntimeError(
            "Could not safely patch frontend/src/App.tsx. Expected the applied SIM.UI.1 SimulationWorkspace import/render."
        )
    if label_count == 0:
        print("WARNING: App navigation label '시뮬레이션' was not found; workspace wiring was still updated.")
    if text == original:
        raise RuntimeError("App.tsx patch made no changes")
    return text


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"PYTHON      : {sys.executable}")
    require("frontend/src/App.tsx")
    require("frontend/src/components/SimulationWorkspace.tsx")
    require("frontend/src/components/scannerSession.ts")
    require("backend/app/api/simulation.py")
    require("backend/app/simulation/sim3_market_provider.py")
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

        app = ROOT / "frontend/src/App.tsx"
        originals[app] = app.read_bytes()
        app.write_text(patch_app(app.read_text(encoding="utf-8")), encoding="utf-8")
        print("PATCH  frontend/src/App.tsx")

        py = sys.executable
        run([py, "-m", "py_compile",
             "backend/app/tracking/models.py", "backend/app/tracking/store.py",
             "backend/app/tracking/service.py", "backend/app/tracking/api.py", "backend/app/api/simulation.py"])
        run([py, "-m", "pytest",
             "backend/tests/test_recommendation_tracking_track1.py",
             "backend/tests/test_simulation_ui1_api_integration.py",
             "frontend/tests/test_tracking_track1_source.py",
    "frontend/tests/test_simulation_ui1_source.py",
             "frontend/tests/test_simulation_ui1_source.py",
             "-q", "-p", "no:cacheprovider"])
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm was not found on PATH")
        run([npm, "--prefix", "frontend", "run", "build"])

        verifier = ROOT / "backend/tools/verify_scanner_production_baseline.py"
        if verifier.exists():
            print("\n[REPORT ONLY] Scanner production baseline")
            result = run([py, str(verifier.relative_to(ROOT))], check=False)
            if result.returncode != 0:
                print("WARNING: pre-existing Scanner baseline mismatch remains; TRACK.1 does not modify Scanner production files.")

        print("\nTRACK.1 Phase 1 applied: recommendation tracking foundation + Scanner snapshot storage + historical simulation reclassification.")
        return 0
    except Exception:
        for path, data in reversed(list(originals.items())):
            if data is None:
                try: path.unlink()
                except FileNotFoundError: pass
            else:
                path.write_bytes(data)
        print("TRACK.1 Phase 1 apply failed; changed files were rolled back.", file=sys.stderr)
        raise

if __name__ == "__main__":
    raise SystemExit(main())
