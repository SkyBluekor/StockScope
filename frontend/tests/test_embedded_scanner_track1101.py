from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_embedded_scanner_reuses_existing_scanner_job_contract():
    text = (ROOT / "src/components/EmbeddedScanner.tsx").read_text(encoding="utf-8")
    assert "createScannerJob" in text
    assert "fetchBacktestJob" in text
    assert "cancelBacktestJob" in text
    assert "candidate_limit: 5" in text
    assert "known_data_date" in text
    assert "scannerProgressView" in text
    assert "progressStatusMark" in text


def test_embedded_scanner_commits_to_shared_reactive_session():
    text = (ROOT / "src/components/EmbeddedScanner.tsx").read_text(encoding="utf-8")
    assert "commitScannerSession" in text
    assert "useScannerSession" in text
    assert "useSyncExternalStore" in text
    assert "selectedCandidateKey" in text
    assert "more_candidates" in text


def test_embedded_scanner_polling_survives_component_unmount_by_module_runner():
    text = (ROOT / "src/components/EmbeddedScanner.tsx").read_text(encoding="utf-8")
    assert "let runnerState" in text
    assert "let runToken" in text
    assert "async function pollRunner" in text
    assert "while (token === runToken)" in text
    assert "useEffect(() => () =>" not in text
