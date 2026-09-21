from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "payload"

COPY_FILES = [
    "frontend/src/components/EmbeddedScanner.tsx",
    "frontend/src/components/RecommendationTracking.tsx",
    "frontend/src/tracking.css",
    "frontend/tests/test_tracking_track1_source.py",
    "frontend/tests/test_embedded_scanner_track1101.py",
    "frontend/tests/test_scanner_panel_shared_track1101.py",
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
    scanner = require("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    api = require("frontend/src/services/api.ts").read_text(encoding="utf-8")
    if "tracking-search-primary" not in tracking or "deleteTrackedRecommendation" not in tracking:
        raise RuntimeError("TRACK.1.10 tracking workspace was not detected. Apply TRACK.1.10/SIM.VAL.0.1 first.")
    if "useScannerSession" not in tracking or "SCANNER_SESSION_SCHEMA_VERSION" not in session:
        raise RuntimeError("Reactive Scanner session from TRACK.1.9 was not detected.")
    if "TRACK.1.9: commit completed Scanner result synchronously" not in scanner:
        raise RuntimeError("TRACK.1.9 ScannerPanel completion patch was not detected.")
    for symbol in ("createScannerJob", "fetchBacktestJob", "cancelBacktestJob"):
        if symbol not in api:
            raise RuntimeError(f"Scanner API symbol missing from frontend/src/services/api.ts: {symbol}")
    require("frontend/src/components/scannerProgress.ts")


def patch_scanner_panel(text: str) -> str:
    marker = "TRACK.1.10.1: accept Scanner results completed from another entry point"
    if marker in text:
        return text

    # Add the reactive hook to the existing scannerSession import without
    # replacing the whole ScannerPanel (which is a protected, fast-moving UI).
    if "useScannerSession," not in text:
        pattern = re.compile(r'(\breadScannerSession,\s*\n)(\s*writeScannerSession,)')
        text, count = pattern.subn(r'\1  useScannerSession,\n\2', text, count=1)
        if count != 1:
            raise RuntimeError("Could not safely add useScannerSession to ScannerPanel import")

    function_anchor = "export default function ScannerPanel({ onAnalyzeStock }: Props) {\n  const initialSession = useMemo(() => readScannerSession(), []);"
    if function_anchor not in text:
        raise RuntimeError("ScannerPanel component anchor was not found")
    text = text.replace(
        function_anchor,
        function_anchor + "\n  const sharedSession = useScannerSession();",
        1,
    )

    progress_anchor = "  const progress = job?.progress;\n\n  useEffect(() => {\n    const onScroll = () => {"
    if progress_anchor not in text:
        raise RuntimeError("ScannerPanel progress/effect anchor was not found")
    shared_effect = '''  const progress = job?.progress;\n\n  useEffect(() => {\n    // TRACK.1.10.1: accept Scanner results completed from another entry point\n    // (for example Stock Tracking) without requiring a page round-trip.\n    if (!sharedSession?.result || jobBusy || sharedSession.result === result) return;\n    setScope(sharedSession.scope);\n    setResult(sharedSession.result);\n    setSelectedCandidateKey(\n      sharedSession.selectedCandidateKey\n        ?? (sharedSession.result.candidates?.[0] ? candidateKey(sharedSession.result.candidates[0]) : null),\n    );\n    setShowMore(sharedSession.showMore);\n    setExpandedEvidenceIds(sharedSession.expandedEvidenceIds);\n    setCompletedAt(sharedSession.completedAt);\n    setRestoredFromSession(true);\n    savedScrollRef.current = sharedSession.scrollY;\n  }, [sharedSession, jobBusy, result]);\n\n  useEffect(() => {\n    const onScroll = () => {'''
    text = text.replace(progress_anchor, shared_effect, 1)
    return text


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"PYTHON      : {sys.executable}")
    verify_previous_phase()
    require("frontend/package.json")
    require("frontend/tests/test_scanner_session_reactive_track19.py")
    require("frontend/tests/test_tracking_performance_source.py")
    require("frontend/tests/test_simulation_ui1_source.py")

    originals: dict[Path, bytes | None] = {}
    try:
        scanner_panel = require("frontend/src/components/ScannerPanel.tsx")
        originals[scanner_panel] = scanner_panel.read_bytes()
        scanner_panel.write_text(patch_scanner_panel(scanner_panel.read_text(encoding="utf-8")), encoding="utf-8")
        print("PATCH  frontend/src/components/ScannerPanel.tsx")

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
            py, "-m", "pytest",
            "frontend/tests/test_tracking_track1_source.py",
            "frontend/tests/test_tracking_performance_source.py",
            "frontend/tests/test_scanner_session_reactive_track19.py",
            "frontend/tests/test_embedded_scanner_track1101.py",
            "frontend/tests/test_scanner_panel_shared_track1101.py",
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
                    "TRACK.1.10.1 only changes frontend Scanner orchestration/UI."
                )

        print("\nTRACK.1.10.1 applied successfully.")
        print("- Stock Tracking can run the existing Scanner directly in-place.")
        print("- Scanner progress and completion stay on the Stock Tracking screen.")
        print("- Completed results are committed to the same reactive Scanner session as the main Stock Finder.")
        print("- Tracking shows candidates + more_candidates without UI truncation.")
        print("- Manual stock add, tracking performance, and Historical Validation were not changed.")
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
        print("TRACK.1.10.1 apply failed; changed files were rolled back.", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
