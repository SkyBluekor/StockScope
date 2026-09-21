from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "payload"

COPY_FILES = [
    "backend/app/tracking/models.py",
    "backend/app/tracking/performance.py",
    "backend/app/tracking/store.py",
    "backend/app/tracking/service.py",
    "backend/app/tracking/api.py",
    "backend/app/simulation/validation_period.py",
    "backend/app/api/simulation.py",
    "backend/tests/test_tracking_performance_track1.py",
    "backend/tests/test_tracking_integrity_track19.py",
    "backend/tests/test_tracking_api_track1.py",
    "backend/tests/test_simulation_validation_period_simval0.py",
    "frontend/src/services/trackingApi.ts",
    "frontend/src/services/simulationApi.ts",
    "frontend/src/components/RecommendationTracking.tsx",
    "frontend/src/components/TrackingWorkspace.tsx",
    "frontend/src/components/SimulationWorkspace.tsx",
    "frontend/src/tracking.css",
    "frontend/src/simulation.css",
    "frontend/tests/test_tracking_track1_source.py",
    "frontend/tests/test_tracking_performance_source.py",
    "frontend/tests/test_simulation_ui1_source.py",
    "frontend/tests/test_scanner_session_reactive_track19.py",
]


def run(cmd: list[str], *, check: bool = True):
    print("RUN ", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def require(rel: str) -> Path:
    path = ROOT / rel
    if not path.exists():
        raise RuntimeError(f"Required file missing: {rel}")
    return path


def detect_scanner_storage_key(text: str) -> str:
    patterns = [
        r'[A-Z_]*(?:STORAGE|SESSION)[A-Z_]*KEY\s*=\s*["\']([^"\']+)["\']',
        r'sessionStorage\.getItem\(\s*["\']([^"\']*scanner[^"\']*)["\']\s*\)',
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            if "scanner" in match.lower():
                return match
    print("WARNING: existing scanner session storage key could not be detected; using compatibility fallback.")
    return "stockscope-scanner-session"


def render_scanner_session(existing_text: str) -> str:
    template = (PAYLOAD / "frontend/src/components/scannerSession.ts").read_text(encoding="utf-8")
    key = detect_scanner_storage_key(existing_text)
    return template.replace("__STOCKSCOPE_SCANNER_SESSION_STORAGE_KEY__", key)


def patch_scanner_panel(text: str) -> str:
    if "TRACK.1.9: commit completed Scanner result synchronously" in text:
        return text
    pattern = re.compile(
        r'(if \(latest\.status === "completed" && latest\.result\) \{\s*)'
        r'(setResult\(latest\.result\);)',
        re.MULTILINE,
    )
    replacement = r'''\1const completedAtValue = Date.now();
        // TRACK.1.9: commit completed Scanner result synchronously so Tracking
        // sees the same result even if the user navigates before React effects run.
        writeScannerSession({
          scope,
          result: latest.result,
          completedAt: completedAtValue,
          scrollY: window.scrollY,
          showMore: false,
          expandedEvidenceIds: [],
          selectedCandidateKey: latest.result.candidates[0] ? candidateKey(latest.result.candidates[0]) : null,
        });
        \2'''
    patched, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError("Could not safely patch ScannerPanel completed-result block")
    if "setCompletedAt(Date.now());" not in patched:
        raise RuntimeError("ScannerPanel completedAt anchor was not found")
    patched = patched.replace("setCompletedAt(Date.now());", "setCompletedAt(completedAtValue);", 1)
    return patched


def patch_app_labels(text: str) -> str:
    changed = text
    changed = changed.replace("추천 추적", "종목 추적")
    changed = changed.replace("과거 성과 검증", "종목별 과거 근거")
    if changed == text:
        print("WARNING: App.tsx navigation labels were already changed or not found.")
    return changed


def verify_phase2() -> None:
    tracking = require("frontend/src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    store = require("backend/app/tracking/store.py").read_text(encoding="utf-8")
    if "최신 데이터 반영" not in tracking or "recommendation_performance" not in store:
        raise RuntimeError("TRACK.1 Phase 2 was not detected. Apply Phase 2 first.")


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"PYTHON      : {sys.executable}")
    verify_phase2()
    require("frontend/src/App.tsx")
    scanner_panel = require("frontend/src/components/ScannerPanel.tsx")
    scanner_session = require("frontend/src/components/scannerSession.ts")
    require("frontend/src/services/api.ts")
    require("frontend/package.json")
    require("backend/app/simulation/sim3_market_provider.py")
    require("backend/tests/test_recommendation_tracking_track1.py")
    require("backend/tests/test_simulation_ui1_api_integration.py")

    originals: dict[Path, bytes | None] = {}
    try:
        # Render scanner session using the repo's existing storage key so current
        # same-tab/session data can migrate instead of silently disappearing.
        originals[scanner_session] = scanner_session.read_bytes()
        existing_session_text = scanner_session.read_text(encoding="utf-8")
        scanner_session.write_text(render_scanner_session(existing_session_text), encoding="utf-8")
        print("UPDATE frontend/src/components/scannerSession.ts")

        originals[scanner_panel] = scanner_panel.read_bytes()
        scanner_panel.write_text(patch_scanner_panel(scanner_panel.read_text(encoding="utf-8")), encoding="utf-8")
        print("PATCH  frontend/src/components/ScannerPanel.tsx")

        app = require("frontend/src/App.tsx")
        originals[app] = app.read_bytes()
        app.write_text(patch_app_labels(app.read_text(encoding="utf-8")), encoding="utf-8")
        print("PATCH  frontend/src/App.tsx")

        for rel in COPY_FILES:
            src = PAYLOAD / rel
            if not src.exists():
                raise RuntimeError(f"Payload file missing: {rel}")
            dst = ROOT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst not in originals:
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
            "backend/app/simulation/validation_period.py",
            "backend/app/api/simulation.py",
        ])

        run([
            py, "-m", "pytest",
            "backend/tests/test_recommendation_tracking_track1.py",
            "backend/tests/test_tracking_performance_track1.py",
            "backend/tests/test_tracking_integrity_track19.py",
            "backend/tests/test_tracking_api_track1.py",
            "backend/tests/test_simulation_validation_period_simval0.py",
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
                    "TRACK.1.9/SIM.VAL.0 does not modify Scanner production algorithms."
                )

        print("\nTRACK.1.9 + SIM.VAL.0 applied successfully.")
        print("- Scanner -> stock tracking is reactive without tab round-trips.")
        print("- Scanner and manual tracking sources are server-separated.")
        print("- Closed tracking records are frozen and snapshots are integrity-checked.")
        print("- Historical Validation now starts explicitly with month/preset period preview and 60-day policy.")
        print("- Legacy simulation portfolios remain preserved and are no longer auto-activated.")
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
        print("TRACK.1.9 + SIM.VAL.0 apply failed; changed files were rolled back.", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
