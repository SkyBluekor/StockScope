from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_scanner_session_store_separates_schema_from_algorithm_version():
    text = (ROOT / "src/components/scannerSession.ts").read_text(encoding="utf-8")
    assert "SCANNER_SESSION_SCHEMA_VERSION" in text
    assert "useSyncExternalStore" in text
    assert "subscribeScannerSession" in text
    assert "memorySnapshot" in text
    assert "algorithm version" in text
    assert "0.21.3.6" not in text


def test_scanner_panel_commits_completed_result_synchronously():
    text = (ROOT / "src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    assert "TRACK.1.9: commit completed Scanner result synchronously" in text
    completed = text.index('latest.status === "completed"')
    commit = text.index("writeScannerSession({", completed)
    set_result = text.index("setResult(latest.result)", completed)
    assert commit < set_result
