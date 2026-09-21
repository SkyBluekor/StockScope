from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "payload"

UPDATE_FILES = [
    "backend/app/tracking/models.py",
    "backend/app/tracking/store.py",
    "backend/app/tracking/service.py",
    "backend/app/tracking/performance.py",
    "frontend/src/services/trackingApi.ts",
    "frontend/src/components/RecommendationTracking.tsx",
]
NEW_FILES = [
    "backend/tests/test_tracking_same_baseline_merge_track1104.py",
    "frontend/tests/test_same_baseline_merge_track1104.py",
]


def run(cmd: list[str], *, check: bool = True):
    print("RUN ", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def require(rel: str) -> Path:
    path = ROOT / rel
    if not path.exists():
        raise RuntimeError(f"Required file missing: {rel}")
    return path


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"PYTHON      : {sys.executable}")
    current = require("frontend/src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    # TRACK.1.10.3 did not embed a literal version marker in the component.
    # Detect the real applied feature surface instead of requiring a nonexistent comment.
    baseline_markers = [
        "previewManualTrackedItem",
        "EmbeddedScanner",
        "원하는 종목 직접 찾기",
        "최신 반영",
        "추적 종료",
    ]
    missing = [marker for marker in baseline_markers if marker not in current]
    if missing:
        raise RuntimeError(
            "Expected TRACK.1.10.3 feature markers missing: " + ", ".join(missing)
        )
    require("backend/app/tracking/store.py")
    require("backend/app/tracking/service.py")
    require("backend/tools/verify_scanner_production_baseline.py")
    require("frontend/package.json")

    backup = ROOT / ".track1104_backup"
    if backup.exists():
        shutil.rmtree(backup)
    originals: dict[Path, bytes | None] = {}

    try:
        for rel in UPDATE_FILES + NEW_FILES:
            src = PAYLOAD / rel
            if not src.exists():
                raise RuntimeError(f"Payload missing: {rel}")
            dst = ROOT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            originals[dst] = dst.read_bytes() if dst.exists() else None
            dst.write_bytes(src.read_bytes())
            print(("UPDATE " if originals[dst] is not None else "CREATE ") + rel)

        run([sys.executable, "-m", "py_compile",
             "backend/app/tracking/models.py", "backend/app/tracking/store.py",
             "backend/app/tracking/service.py", "backend/app/tracking/performance.py"])

        tests = [
            "backend/tests/test_recommendation_tracking_track1.py",
            "backend/tests/test_tracking_performance_track1.py",
            "backend/tests/test_tracking_integrity_track19.py",
            "backend/tests/test_tracking_usability_track110.py",
            "backend/tests/test_tracking_api_track1.py",
            "backend/tests/test_tracking_same_baseline_merge_track1104.py",
            "frontend/tests/test_tracking_track1_source.py",
            "frontend/tests/test_tracking_performance_source.py",
            "frontend/tests/test_scanner_session_reactive_track19.py",
            "frontend/tests/test_embedded_scanner_track1101.py",
            "frontend/tests/test_scanner_panel_shared_track1101.py",
            "frontend/tests/test_tracking_lifecycle_track1102.py",
            "frontend/tests/test_manual_tracking_completion_track1103.py",
            "frontend/tests/test_same_baseline_merge_track1104.py",
        ]
        run([sys.executable, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider"])

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm not found")
        run([npm, "--prefix", "frontend", "run", "build"])

        print("\n[REPORT ONLY] Scanner production baseline")
        baseline = run([sys.executable, "backend/tools/verify_scanner_production_baseline.py"], check=False)
        if baseline.returncode != 0:
            print("WARNING: pre-existing Scanner baseline mismatch remains; TRACK.1.10.4 does not modify Scanner production algorithms.")

        print("\nTRACK.1.10.4 applied successfully.")
        print("- Same market/ticker/reference-date/reference-price Scanner + Manual records merge into one tracking row.")
        print("- Existing duplicate same-baseline rows are migrated automatically without deleting distinct baselines.")
        print("- Combined rows preserve Scanner evidence and appear in both recommendation/direct filters while rendering once in All.")
        return 0
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("ROLLBACK TRACK.1.10.4 changes...")
        for dst, data in reversed(list(originals.items())):
            try:
                if data is None:
                    if dst.exists(): dst.unlink()
                else:
                    dst.write_bytes(data)
            except Exception as rollback_exc:
                print(f"ROLLBACK WARNING {dst}: {rollback_exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
