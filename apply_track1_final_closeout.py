from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "payload"

NEW_OR_OWNED_FILES = [
    "docs/TRACKING_BASELINE.md",
    "backend/tools/verify_tracking_baseline.py",
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

    # TRACK.1.10.4 precondition: check concrete behavior markers, not a version comment.
    store = require("backend/app/tracking/store.py").read_text(encoding="utf-8")
    models = require("backend/app/tracking/models.py").read_text(encoding="utf-8")
    component = require("frontend/src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    markers = {
        "backend/app/tracking/store.py": [
            "SCHEMA_VERSION = 4",
            "_merge_existing_same_baseline",
            "has_scanner_source",
            "has_manual_source",
        ],
        "backend/app/tracking/models.py": [
            "has_scanner_source",
            "has_manual_source",
            "scanner_snapshot",
        ],
        "frontend/src/components/RecommendationTracking.tsx": [
            "추천 · 직접",
            "최신 반영",
            "추적 종료",
        ],
    }
    contents = {
        "backend/app/tracking/store.py": store,
        "backend/app/tracking/models.py": models,
        "frontend/src/components/RecommendationTracking.tsx": component,
    }
    for rel, expected in markers.items():
        missing = [marker for marker in expected if marker not in contents[rel]]
        if missing:
            raise RuntimeError(
                f"TRACK.1.10.4 baseline markers missing in {rel}: " + ", ".join(missing)
            )

    require("backend/tools/verify_scanner_production_baseline.py")
    require("frontend/package.json")

    originals: dict[Path, bytes | None] = {}
    try:
        for rel in NEW_OR_OWNED_FILES:
            src = PAYLOAD / rel
            if not src.exists():
                raise RuntimeError(f"Payload missing: {rel}")
            dst = ROOT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            originals[dst] = dst.read_bytes() if dst.exists() else None
            dst.write_bytes(src.read_bytes())
            print(("UPDATE " if originals[dst] is not None else "CREATE ") + rel)

        run([sys.executable, "-m", "py_compile", "backend/tools/verify_tracking_baseline.py"])

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

        print("\n[REQUIRED] TRACK.1 runtime baseline")
        run([sys.executable, "backend/tools/verify_tracking_baseline.py"])

        print("\n[REPORT ONLY] Scanner production baseline")
        baseline = run(
            [sys.executable, "backend/tools/verify_scanner_production_baseline.py"],
            check=False,
        )
        if baseline.returncode != 0:
            print(
                "WARNING: pre-existing Scanner baseline mismatch remains; "
                "TRACK.1 FINAL does not modify Scanner production algorithms."
            )

        print("\nTRACK.1 FINAL closeout completed successfully.")
        print("- STATUS: CLOSED / FROZEN")
        print("- No TRACK product behavior was changed by this closeout overlay.")
        print("- Existing TRACK regression suite and frontend production build passed.")
        print("- Runtime tracking database passed the frozen-baseline verifier.")
        print("- Next feature work should move to the next scoped phase unless a reproducible TRACK defect appears.")
        return 0
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("ROLLBACK TRACK.1 FINAL closeout files...")
        for dst, data in reversed(list(originals.items())):
            try:
                if data is None:
                    if dst.exists():
                        dst.unlink()
                else:
                    dst.write_bytes(data)
            except Exception as rollback_exc:
                print(f"ROLLBACK WARNING {dst}: {rollback_exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
